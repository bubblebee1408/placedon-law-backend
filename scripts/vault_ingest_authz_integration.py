#!/usr/bin/env python3
"""Regression: a vault ingest job reads only the bytes of the document it writes to.

The file store is content-addressed and shared, so a sha256 alone would serve any file to
anyone holding it (gateway/access.content_allowed). An ingest job used to take its sha256,
name and matter_id from the job's ARGS, and `runs.submit` let a lawyer queue one. So a
caller could name their OWN document and SOMEONE ELSE's hash, and the worker wrote that
file's text into the caller's searchable chunks.

On a THROWAWAY database, through the real verbs, queue and worker, with two firms:
  * firm B cannot queue `vault_ingest` through runs.submit at all (internal intent);
  * a forged ingest job naming firm A's hash on firm B's document does not put A's text in
    B's search -- the job reads the bytes recorded on B's own row;
  * a lawyer whose matter grant was revoked cannot pull that matter's document into their
    own unfiled document the same way;
  * a DELETED document is not brought back by an ingest job, including one deleted
    while its ingest is already running;
  * a filed document is not moved out of its matter by a job that omits matter_id;
  * the normal upload -> ingest path still reaches INGESTED.

    python3 scripts/vault_ingest_authz_integration.py --run     # live, throwaway DB
    python3 scripts/vault_ingest_authz_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database on a LOCAL server only.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")

SECRET_A = "Clause 4. ZEPHYRQUARTZ settlement figure is confidential to firm A."
SECRET_M = "Clause 6. OBLONGMARROW privileged advice on the matter."
SECRET_D = "Clause 2. VELLUMTHRUSH terms, since deleted at the client's request."
SECRET_R = "Clause 3. MARBLEWREN terms, deleted while they were still being read."


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
    from gateway.verbs import (Context, _runs_submit, _vault_delete, _vault_find,
                               _vault_upload)
    from gateway.worker import postgres_job_bindings, run_one

    if not (HOST.startswith("/") or HOST in ("localhost", "127.0.0.1", "::1")):
        print(f"REFUSED: PLACEDON_PGHOST={HOST!r} is not a local server.")
        return 1
    scratch = f"{PREFIX}vault_authz_{os.getpid()}"
    assert scratch.startswith(PREFIX), "scratch-name guard"
    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    admin_db = f"postgresql:///{scratch}?host={HOST}&user={ADMIN}"
    app_url = f"postgresql:///{scratch}?host={HOST}&user={APP}"
    TA, TB = str(uuid.uuid4()), str(uuid.uuid4())
    A1, A2, ADM, B1 = (str(uuid.uuid4()) for _ in range(4))
    tenant_of = {A1: TA, A2: TA, ADM: TA, B1: TB}
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
                for tenant, actors in ((TA, ((A1, "lawyer"), (A2, "lawyer"),
                                             (ADM, "admin"))),
                                       (TB, ((B1, "lawyer"),))):
                    c.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
                    c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,'va')",
                              (tenant,))
                    for actor, role in actors:
                        c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                                  "VALUES (%s,%s,'va',%s)", (actor, tenant, role))
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            # ONE file store for both firms: the content-addressed store is shared.
            files = LocalFileStore(tmp)

            def store(actor):
                return PostgresBackend(app_url, tenant_id=tenant_of[actor], actor_id=actor)

            def ctx(actor, role="lawyer"):
                t = tenant_of[actor]
                return Context(tenant=t, actor=actor, role=role, store=store(actor),
                               queue=q.PostgresQueue(app_url, tenant_id=t, actor_id=actor),
                               files=files)

            def drain(tenant):
                anyone = A1 if tenant == TA else B1
                wq = q.PostgresQueue(app_url, tenant_id=tenant, actor_id=anyone)
                bind = postgres_job_bindings(app_url, tenant_id=tenant, files=files)
                while True:
                    sql("UPDATE jobs SET not_before = NULL WHERE status = 'QUEUED'")
                    if run_one(queue=wq, store=store(anyone), handlers={}, worker="w",
                               bind_job=bind) is None:
                        return

            def forge(actor, args):
                """A job row written by any path other than vault.upload: the handler
                must hold on its own, not rely on runs.submit refusing first."""
                c = ctx(actor)
                run_id = str(uuid.uuid4())
                c.store.write({"id": run_id, "intent": "vault_ingest", "status": "PLANNED",
                               "actor_id": actor, "matter_id": None, "refusal_code": None,
                               "steps": [], "propositions": []})
                c.queue.enqueue(run_id=run_id, intent="vault_ingest", args=args,
                                lane=q.BULK)
                return run_id

            def hits(actor, word):
                res = _vault_find({"query": word}, ctx(actor))
                return [h for h in res.get("hits", res.get("results", []))
                        if word.lower() in str(h).lower()]

            # 0. Normal path still works.
            up_a = _vault_upload({"name": "a-secret.txt", "text": SECRET_A}, ctx(A1))
            drain(TA)
            row = store(A1).read_vault_document(up_a["document_id"]) or {}
            check(row.get("state") == "INGESTED" and hits(A1, "ZEPHYRQUARTZ"),
                  f"the normal upload -> ingest path reaches INGESTED and is searchable "
                  f"({row.get('state')})")
            sha_a = up_a["sha256"]

            # 1. Cross-tenant via runs.submit.
            up_b = _vault_upload({"name": "b-decoy.txt", "text": "Clause 1. Decoy B."},
                                 ctx(B1))
            drain(TB)
            sub = _runs_submit({"intent": "vault_ingest",
                                "args": {"document_id": up_b["document_id"],
                                         "sha256": sha_a, "name": "x"}}, ctx(B1))
            check(sub.get("status") == "REFUSED",
                  f"runs.submit refuses the internal vault_ingest intent "
                  f"({sub.get('status')}, {sub.get('code')})")
            drain(TB)
            check(not hits(B1, "ZEPHYRQUARTZ"),
                  "...and firm A's text is not in firm B's search")

            # 2. Cross-tenant via a forged job (handler guard on its own).
            forge(B1, {"document_id": up_b["document_id"], "sha256": sha_a, "name": "x"})
            drain(TB)
            b_chunks = sql("SELECT text FROM vault_chunks WHERE document_id = %s",
                           (up_b["document_id"],))
            check(not hits(B1, "ZEPHYRQUARTZ")
                  and not any("ZEPHYRQUARTZ" in t for (t,) in b_chunks),
                  f"a forged job naming firm A's hash on firm B's document reads B's own "
                  f"bytes, not A's ({[t[:30] for (t,) in b_chunks]})")

            # 3. Revoked member of a matter in firm A.
            mid = str(uuid.uuid4())
            store(A1).write_matter({"matter_id": mid, "name": "M"}, owner=A1)
            store(ADM).grant_matter_access(matter_id=mid, actor_id=A2, role="member",
                                           granted_by=ADM, reason="staffed")
            up_m = _vault_upload({"name": "m.txt", "text": SECRET_M, "matter_id": mid},
                                 ctx(A1))
            drain(TA)
            check(hits(A2, "OBLONGMARROW"), "a member of the matter can search its document")
            sha_m = up_m["sha256"]          # vault.list hands this to every reader
            store(ADM).revoke_matter_access(matter_id=mid, actor_id=A2, revoked_by=ADM,
                                            reason="left the matter")
            check(not hits(A2, "OBLONGMARROW"), "...and cannot once the grant is revoked")
            up_a2 = _vault_upload({"name": "a2-decoy.txt", "text": "Clause 1. Decoy A2."},
                                  ctx(A2))
            drain(TA)
            sub = _runs_submit({"intent": "vault_ingest",
                                "args": {"document_id": up_a2["document_id"],
                                         "sha256": sha_m, "name": "x"}}, ctx(A2))
            check(sub.get("status") == "REFUSED",
                  f"a revoked member cannot queue an ingest through runs.submit "
                  f"({sub.get('status')})")
            forge(A2, {"document_id": up_a2["document_id"], "sha256": sha_m, "name": "x"})
            drain(TA)
            check(not hits(A2, "OBLONGMARROW"),
                  "...nor pull the matter's text into their own document with a forged job")

            # 4. A deleted document is not resurrected.
            up_d = _vault_upload({"name": "d.txt", "text": SECRET_D}, ctx(A1))
            drain(TA)
            _vault_delete({"document_id": up_d["document_id"]}, ctx(A1))
            forge(A1, {"document_id": up_d["document_id"], "sha256": up_d["sha256"],
                       "name": "d.txt"})
            drain(TA)
            row = store(A1).read_vault_document(up_d["document_id"]) or {}
            d_chunks = sql("SELECT count(*) FROM vault_chunks WHERE document_id = %s",
                           (up_d["document_id"],))[0][0]
            check(row.get("state") == "DELETED" and row.get("deleted_at") and d_chunks == 0
                  and not hits(A1, "VELLUMTHRUSH"),
                  f"an ingest job does not bring a DELETED document back "
                  f"({row.get('state')}, chunks={d_chunks})")

            # 4b. Deleted WHILE its ingest is running: the job has already re-read the row
            # (still live), the person deletes it, then the ingest's final writes land.
            # The bytes are read after the row, so the delete happens on that read.
            up_r = _vault_upload({"name": "r.txt", "text": SECRET_R}, ctx(A1))

            class _DeleteOnRead:
                def __init__(self, inner):
                    self.inner, self.fired = inner, False

                def __getattr__(self, name):
                    return getattr(self.inner, name)

                def get(self, sha):
                    if sha == up_r["sha256"] and not self.fired:
                        self.fired = True
                        _vault_delete({"document_id": up_r["document_id"]}, ctx(A1))
                    return self.inner.get(sha)

            racing = _DeleteOnRead(files)
            wq = q.PostgresQueue(app_url, tenant_id=TA, actor_id=A1)
            sql("UPDATE jobs SET not_before = NULL WHERE status = 'QUEUED'")
            run_one(queue=wq, store=store(A1), handlers={}, worker="w",
                    bind_job=postgres_job_bindings(app_url, tenant_id=TA, files=racing))
            row = store(A1).read_vault_document(up_r["document_id"]) or {}
            r_chunks = sql("SELECT count(*) FROM vault_chunks WHERE document_id = %s",
                           (up_r["document_id"],))[0][0]
            check(racing.fired and row.get("state") == "DELETED" and row.get("deleted_at")
                  and row.get("text_chars") is None and r_chunks == 0
                  and not hits(A1, "MARBLEWREN"),
                  f"a document deleted MID-INGEST stays DELETED: the ingest's final write "
                  f"does not flip it back ({row.get('state')}, chunks={r_chunks}, "
                  f"delete fired={racing.fired})")

            # 5. A job that omits matter_id does not unfile a filed document.
            forge(A1, {"document_id": up_m["document_id"], "sha256": sha_m, "name": "m"})
            drain(TA)
            row = store(A1).read_vault_document(up_m["document_id"]) or {}
            check(row.get("matter_id") == mid,
                  f"a job omitting matter_id leaves the document in its matter "
                  f"({row.get('matter_id')})")

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
    """Offline: runs.submit refuses the internal intent, and the handler re-reads the row."""
    import inspect
    from gateway import verbs
    check, counts = _checker()
    check("vault_ingest" in verbs.INTERNAL_INTENTS,
          "vault_ingest is declared internal")
    r = verbs._runs_submit({"intent": "vault_ingest", "args": {}}, verbs.Context())
    check(r.get("code") == "BAD_REQUEST", f"runs.submit refuses it by name ({r.get('code')})")
    src = inspect.getsource(verbs._vault_ingest_job)
    check("read_vault_document" in src and "document_allowed" in src,
          "the ingest handler resolves the document row and its access before reading bytes")
    print(f"\n{counts['ok']}/{counts['ok'] + counts['fail']} passed")
    return 1 if counts["fail"] else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
