#!/usr/bin/env python3
"""Regression: a vault document whose ingest gives up is FAILED, and a retry runs it ONCE.

Before 030 a document whose ingest job used up its attempts stayed PENDING ("queued; not
searchable yet") although nothing would ever read it again. Now the worker marks it FAILED
with the reason, `vault.retry` puts it back to PENDING with its DEAD job requeued, and
uploading the same bytes again does the same (repairing bytes that had gone missing).

On a THROWAWAY database, through the real verbs, queue and worker:
  * the stored bytes go missing, the real ingest fails all three attempts: job DEAD,
    run FAILED, document FAILED with a reason, counted as unsearchable;
  * the database itself refuses a FAILED row with no reason (030's CHECK);
  * vault.retry while the bytes are still missing is refused and changes nothing;
  * uploading the same bytes again requeues the ONE job, and the worker reaches INGESTED;
  * two retries racing: exactly one requeues, the other is refused, and the document is
    read once;
  * another lawyer cannot retry a document that is not theirs;
  * no PENDING document is left with a DEAD job.

Between attempts the test clears `not_before` with a superuser UPDATE. That only skips the
5 s / 30 s backoff WAIT; the attempt counting and the DEAD decision are the queue's own.

    python3 scripts/vault_failed_retry_integration.py --run     # live, throwaway DB
    python3 scripts/vault_failed_retry_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database on a LOCAL server only.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import threading
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")


def _checker():
    counts = {"ok": 0, "fail": 0}

    def check(cond, label):
        counts["ok" if cond else "fail"] += 1
        print(f"  [{'ok' if cond else 'FAIL'}]   {label}")
    return check, counts


def _run() -> int:
    import psycopg
    from gateway import jobs as q
    from gateway.filestore import LocalFileStore
    from gateway.store import PostgresBackend
    from gateway.verbs import Context, _vault_retry, _vault_upload
    from gateway.worker import postgres_job_bindings, run_one

    if not (HOST.startswith("/") or HOST in ("localhost", "127.0.0.1", "::1")):
        print(f"REFUSED: PLACEDON_PGHOST={HOST!r} is not a local server.")
        return 1
    scratch = f"{PREFIX}vault_failed_{os.getpid()}"
    assert scratch.startswith(PREFIX), "scratch-name guard"
    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    admin_db = f"postgresql:///{scratch}?host={HOST}&user={ADMIN}"
    app_url = f"postgresql:///{scratch}?host={HOST}&user={APP}"
    T, A, B = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    check, counts = _checker()

    def sql(statement, params=()):
        with psycopg.connect(admin_db, autocommit=True, connect_timeout=10) as c:
            cur = c.execute(statement, params)
            return cur.fetchall() if cur.description else cur.rowcount

    try:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
                c.execute(f'CREATE DATABASE "{scratch}" OWNER "{APP}"')
            with psycopg.connect(app_url, autocommit=True, connect_timeout=10) as c:
                for p in sorted((ROOT / "gateway" / "migrations").glob("[0-9]*.sql"),
                                key=lambda p: int(p.name.split("_")[0])):
                    c.execute(p.read_text())
                c.execute("SELECT set_config('app.tenant_id', %s, false)", (T,))
                c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,'vf')", (T,))
                for actor in (A, B):
                    c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                              "VALUES (%s,%s,'vf','lawyer')", (actor, T))
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            files = LocalFileStore(tmp)

            def ctx(actor=A):
                return Context(tenant=T, actor=actor,
                               store=PostgresBackend(app_url, tenant_id=T, actor_id=actor),
                               queue=q.PostgresQueue(app_url, tenant_id=T, actor_id=actor),
                               files=files)

            worker_q = q.PostgresQueue(app_url, tenant_id=T, actor_id=A)
            bind = postgres_job_bindings(app_url, tenant_id=T, files=files)
            store = PostgresBackend(app_url, tenant_id=T, actor_id=A)

            def drain():
                while True:
                    sql("UPDATE jobs SET not_before = NULL WHERE status = 'QUEUED'")
                    if run_one(queue=worker_q, store=store, handlers={}, worker="w",
                               bind_job=bind) is None:
                        return

            def doc(did):
                return store.read_vault_document(did) or {}

            # 1. Bytes go missing; the real ingest fails all three attempts.
            text = "Clause 7. This Agreement may be terminated on thirty days' notice."
            up = _vault_upload({"name": "missing.txt", "text": text}, ctx())
            did, sha = up["document_id"], up["sha256"]
            files._path(sha).unlink()
            drain()
            job = worker_q.get(did)
            row = doc(did)
            check(job.status == q.DEAD and job.attempts == q.MAX_ATTEMPTS,
                  f"the ingest job gives up after {q.MAX_ATTEMPTS} attempts "
                  f"({job.status}, {job.attempts})")
            check(row.get("state") == "FAILED" and row.get("failure_reason"),
                  f"...and the document is FAILED with the reason, not left PENDING "
                  f"({row.get('state')}, {str(row.get('failure_reason'))[:60]})")
            run = sql("SELECT status FROM runs WHERE run_id = %s", (did,))
            check(run == [("FAILED",)], f"...its run is FAILED ({run})")
            check(store.vault_counts()["unsearchable"] == 1,
                  "...and it is counted as unsearchable")

            # 2. 030's CHECK: a FAILED row must say why.
            try:
                sql("UPDATE vault_documents SET failure_reason = NULL WHERE document_id = %s",
                    (did,))
                refused = False
            except psycopg.errors.CheckViolation:
                refused = True
            check(refused, "the database refuses a FAILED document with no reason")

            # 3. Retry while the bytes are still missing: refused, nothing changed.
            r = _vault_retry({"document_id": did}, ctx())
            check(r.get("code") == "BYTES_MISSING" and doc(did).get("state") == "FAILED"
                  and worker_q.get(did).status == q.DEAD,
                  f"retrying while the bytes are missing is refused and changes nothing "
                  f"({r.get('code')})")

            # 4. Another lawyer cannot retry it.
            r = _vault_retry({"document_id": did}, ctx(B))
            check(r.get("code") == "NOT_FOUND" and doc(did).get("state") == "FAILED",
                  f"another lawyer cannot retry a document that is not theirs ({r.get('code')})")

            # 5. Re-upload the same bytes: one job requeued, read once.
            again = _vault_upload({"name": "missing (again).txt", "text": text}, ctx())
            jobs = sql("SELECT status, attempts FROM jobs WHERE run_id = %s", (did,))
            check(again.get("retried") and again.get("document_id") == did
                  and jobs == [("QUEUED", 0)],
                  f"uploading the same bytes again requeues the ONE job ({jobs})")
            drain()
            row = doc(did)
            chunks = sql("SELECT count(*) FROM vault_chunks WHERE document_id = %s", (did,))
            check(row.get("state") == "INGESTED" and not row.get("failure_reason")
                  and chunks[0][0] > 0,
                  f"...and the worker reads it: INGESTED, reason cleared ({row.get('state')}, "
                  f"chunks={chunks[0][0]})")
            check(sql("SELECT status, attempts FROM jobs WHERE run_id = %s", (did,))
                  == [("DONE", 1)], "...in exactly one attempt")
            steps = sql("SELECT status FROM run_steps WHERE run_id = %s", (did,))
            check(all(st != "FAILED" for (st,) in steps),
                  f"...and no FAILED step from the earlier attempt is left in the trace ({steps})")

            # 6. Two retries racing: exactly one requeues.
            text2 = "Clause 8. Each party bears its own costs."
            up2 = _vault_upload({"name": "race.txt", "text": text2}, ctx())
            did2, sha2 = up2["document_id"], up2["sha256"]
            saved = files._path(sha2).read_bytes()
            files._path(sha2).unlink()
            drain()
            files.put(saved)
            check(doc(did2).get("state") == "FAILED", "a second document fails the same way")
            results, barrier = [], threading.Barrier(2)

            def racer():
                barrier.wait()
                results.append(_vault_retry({"document_id": did2}, ctx()))
            threads = [threading.Thread(target=racer) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            won = [r for r in results if r.get("retried")]
            lost = [r for r in results if r.get("code") == "CONFLICT"]
            check(len(won) == 1 and len(lost) == 1,
                  f"two racing retries: one requeues, one is refused "
                  f"({[r.get('retried') or r.get('code') for r in results]})")
            drain()
            check(doc(did2).get("state") == "INGESTED"
                  and sql("SELECT status, attempts FROM jobs WHERE run_id = %s", (did2,))
                  == [("DONE", 1)],
                  "...and the document is read exactly once")

            # 7. A crash between "job DEAD" and "document FAILED" leaves PENDING over a DEAD
            # job. vault.retry finishes the marking and retries, rather than refusing.
            up3 = _vault_upload({"name": "gap.txt", "text": "Clause 9. Severability."}, ctx())
            did3 = up3["document_id"]
            sql("UPDATE jobs SET status = 'DEAD', dead_reason = 'simulated crash after DEAD' "
                "WHERE run_id = %s", (did3,))
            sql("UPDATE runs SET status = 'FAILED' WHERE run_id = %s", (did3,))
            r = _vault_retry({"document_id": did3}, ctx())
            check(r.get("retried") and worker_q.get(did3).status == q.QUEUED,
                  f"PENDING over a DEAD job (a crash mid-marking) can still be retried "
                  f"({r.get('retried') or r.get('code')})")
            drain()
            check(doc(did3).get("state") == "INGESTED", "...and is then read")

            # 8. A FAILED document can be deleted (030's CHECK must not block it).
            up4 = _vault_upload({"name": "gone.txt", "text": "Clause 10. Entire agreement."},
                                ctx())
            did4 = up4["document_id"]
            files._path(up4["sha256"]).unlink()
            drain()
            from gateway.verbs import _vault_delete
            d = _vault_delete({"document_id": did4}, ctx())
            check(doc(did4).get("state") == "DELETED" and d.get("deleted"),
                  f"a FAILED document can be deleted ({d.get('deleted') or d.get('code')})")

            # 9. The invariant.
            stuck = sql("SELECT count(*) FROM vault_documents d JOIN jobs j "
                        "ON j.run_id = d.document_id WHERE d.state = 'PENDING' "
                        "AND j.status = 'DEAD'")[0][0]
            check(stuck == 0, f"no PENDING document is left with a DEAD job ({stuck})")

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
    """Offline: the pieces are wired -- migration, worker hook, guarded retry."""
    import inspect
    from gateway import jobs, store, worker
    check, counts = _checker()
    sql = (ROOT / "gateway" / "migrations" / "030_vault_failed.sql").read_text()
    check("'FAILED'" in sql and "vault_documents_failed_has_reason" in sql,
          "030 admits FAILED and requires its reason")
    check("_fail_bound(queue, store, job" in inspect.getsource(worker.run_one),
          "the worker marks a dead-lettered ingest's document through _fail_bound")
    check("status = 'DEAD'" in inspect.getsource(jobs.PostgresQueue.requeue_dead)
          and "state = 'FAILED'" in inspect.getsource(store.PostgresBackend.retry_vault_document),
          "requeue and retry are guarded on DEAD and FAILED, so a retry cannot run twice")
    print(f"\n{counts['ok']}/{counts['ok'] + counts['fail']} passed")
    return 1 if counts["fail"] else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
