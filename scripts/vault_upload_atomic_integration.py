#!/usr/bin/env python3
"""Regression: a vault upload never leaves a PENDING document without an ingest job.

`vault.upload` wrote the document row, then the run row, then the job, each on its own
connection. A full queue (QueueFull was caught and reported in a note) or a crash between
the writes left a PENDING document that no worker would ever read, with nothing to recover
it. `PostgresBackend.write_vault_document(..., run=, queue=, queued=)` now commits all three
in one transaction, the same pattern `reserve_turn` uses for conversation turns.

On a THROWAWAY database this checks, through the real verb, queue and worker:
  * a normal upload commits document + run + job, and returns the real job id;
  * a full queue refuses BUSY and registers nothing;
  * a crash after the job insert but before commit registers nothing;
  * the same bytes then upload cleanly (no residue blocks the retry);
  * a worker that dies holding the lease: the job is reclaimed after the lease expires and
    the document reaches INGESTED once;
  * duplicate delivery: a second job for the same run is refused, and running the ingest
    handler twice leaves one INGESTED document with the same chunks;
  * finally, no PENDING document anywhere lacks a job.

    python3 scripts/vault_upload_atomic_integration.py --run     # live, throwaway DB
    python3 scripts/vault_upload_atomic_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database and refuses any other name.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")
LEASE_SECONDS = 1


def _checker():
    counts = {"ok": 0, "fail": 0}

    def check(cond, label):
        counts["ok" if cond else "fail"] += 1
        print(f"  [{'ok' if cond else 'FAIL'}]   {label}")
    return check, counts


def _provision(admin_url: str, app_url: str, scratch: str, T: str, A: str) -> None:
    import psycopg
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
        assert scratch.startswith(PREFIX)
        c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{scratch}" OWNER "{APP}"')
    with psycopg.connect(app_url, autocommit=True, connect_timeout=10) as c:
        for p in sorted((ROOT / "gateway" / "migrations").glob("[0-9]*.sql"),
                        key=lambda p: int(p.name.split("_")[0])):
            c.execute(p.read_text())
        c.execute("SELECT set_config('app.tenant_id', %s, false)", (T,))
        c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,'vault-atomic')", (T,))
        c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                  "VALUES (%s,%s,'vault-atomic','lawyer')", (A, T))


def _rows(admin_db_url: str, name: str) -> dict:
    """Counts seen by a superuser, so RLS cannot hide a leftover row from the check."""
    import psycopg
    with psycopg.connect(admin_db_url, connect_timeout=10) as c:
        docs = [str(r[0]) for r in c.execute(
            "SELECT document_id FROM vault_documents WHERE name = %s", (name,))]
        runs = c.execute("SELECT count(*) FROM runs WHERE run_id::text = ANY(%s)",
                         (docs,)).fetchone()[0]
        jobs = c.execute("SELECT count(*) FROM jobs WHERE run_id::text = ANY(%s)",
                         (docs,)).fetchone()[0]
    return {"docs": len(docs), "runs": runs, "jobs": jobs, "ids": docs}


def _run() -> int:
    import psycopg
    from gateway import jobs as q
    from gateway.filestore import LocalFileStore
    from gateway.store import PostgresBackend
    from gateway.verbs import Context, _vault_upload, queue_handlers
    from gateway.worker import postgres_job_bindings, run_one
    from agents.vault_ingest import INTENT

    if not (HOST.startswith("/") or HOST in ("localhost", "127.0.0.1", "::1")):
        print(f"REFUSED: PLACEDON_PGHOST={HOST!r} is not a local server; this script creates "
              f"and drops databases and only runs against a local one.")
        return 1
    scratch = f"{PREFIX}vault_atomic_{os.getpid()}"
    assert scratch.startswith(PREFIX), "scratch-name guard"
    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    admin_db = f"postgresql:///{scratch}?host={HOST}&user={ADMIN}"
    app_url = f"postgresql:///{scratch}?host={HOST}&user={APP}"
    T, A = str(uuid.uuid4()), str(uuid.uuid4())
    check, counts = _checker()
    try:
        try:
            _provision(admin_url, app_url, scratch, T, A)
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            files = LocalFileStore(tmp)

            def ctx(queue):
                return Context(tenant=T, actor=A,
                               store=PostgresBackend(app_url, tenant_id=T, actor_id=A),
                               queue=queue, files=files)

            def upload(name, text, queue):
                return _vault_upload({"name": name, "text": text}, ctx(queue))

            # 1. normal upload: document + run + job, real job id.
            queue = q.PostgresQueue(app_url, tenant_id=T, actor_id=A, max_pending=1)
            up = upload("ok.txt", "This Agreement is governed by the laws of India.", queue)
            r = _rows(admin_db, "ok.txt")
            check(up.get("state") == "PENDING" and r == {**r, "docs": 1, "runs": 1, "jobs": 1},
                  f"a normal upload commits document, run and job together ({r})")
            with psycopg.connect(admin_db, connect_timeout=10) as c:
                critic = c.execute("SELECT critic_enabled FROM runs WHERE run_id::text = %s",
                                   (up.get("document_id"),)).fetchone()
            check(critic is not None and critic[0] is not None,
                  f"...and the run records critic_enabled, as write_run does ({critic})")
            live = queue.get(up.get("document_id") or "")
            check(live is not None and up.get("job_id") == live.job_id,
                  f"...and returns the real job id ({up.get('job_id')})")

            # 2. queue full (max_pending=1 and one job waits): BUSY, nothing registered.
            full = upload("full.txt", "Clause 9. The courts at Mumbai have jurisdiction.", queue)
            r = _rows(admin_db, "full.txt")
            check(full.get("code") == "BUSY", f"a full queue refuses BUSY ({full.get('code')})")
            check(r["docs"] == 0 and r["runs"] == 0,
                  f"...and registers no document and no run ({r})")

            # 3. crash after the job INSERT, before commit: nothing registered.
            crashing = q.PostgresQueue(app_url, tenant_id=T, actor_id=A)
            real_enqueue = crashing.enqueue

            def enqueue_then_crash(**kw):
                real_enqueue(**kw)
                raise RuntimeError("simulated crash before commit")
            crashing.enqueue = enqueue_then_crash
            text3 = "Clause 4. Confidentiality survives for three years."
            crash = upload("crash.txt", text3, crashing)
            r = _rows(admin_db, "crash.txt")
            check(crash.get("code") == "STORAGE_UNAVAILABLE",
                  f"a crash mid-registration is refused, not reported as stored ({crash.get('code')})")
            check(r["docs"] == 0 and r["runs"] == 0 and r["jobs"] == 0,
                  f"...and the transaction leaves no document, run or job ({r})")

            # 4. the same bytes again: no residue blocks the retry.
            again = upload("crash.txt", text3, q.PostgresQueue(app_url, tenant_id=T, actor_id=A))
            r = _rows(admin_db, "crash.txt")
            check(again.get("state") == "PENDING" and not again.get("duplicate")
                  and r["docs"] == 1 and r["jobs"] == 1,
                  f"retrying the same bytes registers them once, with a job ({r})")

            # 5. a worker dies holding the lease; the job is reclaimed after expiry.
            worker_q = q.PostgresQueue(app_url, tenant_id=T, actor_id=A)
            bind = postgres_job_bindings(app_url, tenant_id=T, files=files)
            store = PostgresBackend(app_url, tenant_id=T, actor_id=A)
            dead = worker_q.claim(worker="dies", lease_seconds=LEASE_SECONDS)
            check(dead is not None, "a worker claims an ingest job, then dies without finishing")
            time.sleep(LEASE_SECONDS + 0.5)
            outcomes = []
            while (o := run_one(queue=worker_q, store=store, handlers={}, worker="w2",
                                bind_job=bind)) is not None:
                outcomes.append(o)
            doc = store.read_vault_document(dead.run_id) if dead else None
            check(doc is not None and doc.get("state") == "INGESTED",
                  f"...after the lease expires another worker finishes it: INGESTED "
                  f"({doc and doc.get('state')})")
            job = worker_q.get(dead.run_id) if dead else None
            check(job is not None and job.status == q.DONE and job.attempts == 2,
                  f"...in exactly one more attempt ({job and job.status}, attempts "
                  f"{job and job.attempts})")

            # 6. duplicate delivery.
            try:
                worker_q.enqueue(run_id=dead.run_id, intent=INTENT, args=dead.args)
                refused = False
            except q.QueueError:
                refused = True
            check(refused, "a second job for the same run is refused by the queue")
            with psycopg.connect(admin_db, connect_timeout=10) as c:
                before = c.execute("SELECT count(*) FROM vault_chunks WHERE document_id = %s",
                                   (dead.run_id,)).fetchone()[0]
            handler = queue_handlers(ctx(worker_q))[INTENT]
            handler(dict(dead.args))
            handler(dict(dead.args))
            with psycopg.connect(admin_db, connect_timeout=10) as c:
                after = c.execute("SELECT count(*) FROM vault_chunks WHERE document_id = %s",
                                  (dead.run_id,)).fetchone()[0]
                docs = c.execute("SELECT count(*), min(state) FROM vault_documents "
                                 "WHERE sha256 = %s", (dead.args["sha256"],)).fetchone()
            check(before > 0 and after == before and docs == (1, "INGESTED"),
                  f"running the ingest twice more leaves one INGESTED document with the same "
                  f"chunks ({before} -> {after}, {docs})")

            # 7. the invariant itself.
            with psycopg.connect(admin_db, connect_timeout=10) as c:
                orphans = c.execute(
                    "SELECT count(*) FROM vault_documents d WHERE d.state = 'PENDING' AND "
                    "NOT EXISTS (SELECT 1 FROM jobs j WHERE j.run_id = d.document_id)"
                ).fetchone()[0]
            check(orphans == 0, f"no PENDING document anywhere lacks a job ({orphans})")

        print(f"\n{counts['ok']}/{counts['ok'] + counts['fail']} passed")
        return 1 if counts["fail"] else 0
    finally:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                assert scratch.startswith(PREFIX)
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            print(f"dropped {scratch}")
        except Exception as e:                                       # noqa: BLE001
            print(f"WARNING: could not drop {scratch}: {e}", file=sys.stderr)


def _test() -> int:
    """Offline: the upload registers through ONE store call that carries the queue."""
    import inspect
    from gateway import store, verbs
    check, counts = _checker()
    src = inspect.getsource(verbs._vault_upload)
    check("ctx.queue.enqueue(" not in src,
          "vault.upload no longer enqueues on its own connection")
    check("write_vault_document(doc, **atomic)" in src,
          "...it registers document, run and job in one store call")
    pg = inspect.getsource(store.PostgresBackend.write_vault_document)
    check("c.transaction()" in pg and "connection=c" in pg,
          "PostgresBackend writes them in one transaction, enqueueing on that connection")
    print(f"\n{counts['ok']}/{counts['ok'] + counts['fail']} passed")
    return 1 if counts["fail"] else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
