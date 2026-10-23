"""Opt-in real Postgres/HTTP job identity checks; synthetic, isolated tenants only."""
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
import uuid

from gateway.jobs import PostgresQueue
from gateway.store import PostgresBackend
from gateway.worker import postgres_job_bindings, run_one

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class WorkerActorPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only explicitly named throwaway databases may be used")
        self.tenant = str(uuid.uuid4())
        self.actors = [str(uuid.uuid4()), str(uuid.uuid4())]
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'worker identity test')", (self.tenant,))
            for actor in self.actors:
                conn.execute("INSERT INTO actors (actor_id, tenant_id, label, role) VALUES (%s,%s,'synthetic lawyer','lawyer')", (actor, self.tenant))
        with psycopg.connect(APP_URL) as conn:
            self.assertFalse(conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0])
        self.store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.actors[0])
        self.queue = PostgresQueue(APP_URL, tenant_id=self.tenant, actor_id=self.actors[0])

    def enqueue(self, actor):
        store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=actor)
        queue = PostgresQueue(APP_URL, tenant_id=self.tenant, actor_id=actor)
        run_id = str(uuid.uuid4())
        store.write_run({"id": run_id, "intent": "research_question", "status": "PLANNED"})
        queue.enqueue(run_id=run_id, intent="research_question", args={"actor_id": "spoof"})
        return run_id

    def test_same_tenant_http_upload_queues_authenticated_actor(self):
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        from gateway.filestore import LocalFileStore
        keys = KeyStore()
        key, _ = keys.mint(tenant_id=self.tenant, actor=self.actors[1], label="synthetic", role="lawyer")
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_url=APP_URL, queue=self.queue, keys=keys, files=LocalFileStore(directory))
            with TestClient(app) as client:
                response = client.post("/v2/vault/upload", headers={"Authorization": "Bearer " + key},
                                       json={"name": "synthetic.txt", "text": "Synthetic agreement for the identity test."})
            self.assertEqual(response.status_code, 200, response.text)
        with self.store._conn() as conn:
            rows = conn.execute("SELECT actor_id FROM jobs").fetchall()
        self.assertEqual([str(row[0]) for row in rows], [self.actors[1]])

    def test_one_tenant_worker_restores_each_actor_and_blocks_disabled_actor(self):
        runs = [self.enqueue(actor) for actor in self.actors]
        seen = []
        def handlers(ctx):
            def execute(args):
                seen.append((ctx.tenant, ctx.actor, ctx.store.actor_id, ctx.queue.actor_id))
                return [], {"status": "ANSWERED", "actor": ctx.actor}
            return {"research_question": execute}
        with patch("gateway.verbs.queue_handlers", side_effect=handlers):
            bind = postgres_job_bindings(APP_URL, tenant_id=self.tenant)
            for _ in runs:
                outcome = run_one(queue=self.queue, store=self.store, handlers={}, bind_job=bind)
                self.assertEqual(outcome.status, "ANSWERED")
        self.assertEqual(seen, [(self.tenant, a, a, a) for a in self.actors])
        for run_id, actor in zip(runs, self.actors):
            self.assertEqual(self.store.read_run(run_id)["result"]["actor"], actor)
            self.assertEqual(self.queue.get(run_id).actor_id, actor)
        disabled_run = self.enqueue(self.actors[1])
        with self.store._conn() as conn:
            conn.execute("UPDATE actors SET disabled_at=now() WHERE actor_id=%s", (self.actors[1],))
        with patch("gateway.verbs.queue_handlers", side_effect=handlers):
            outcome = run_one(queue=self.queue, store=self.store, handlers={},
                              bind_job=postgres_job_bindings(APP_URL, tenant_id=self.tenant))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.queue.get(disabled_run).status, "DEAD")
        self.assertEqual(self.store.read_run(disabled_run)["status"], "FAILED")

    def test_exhausted_binding_failure_reconciles_only_persisted_job_owner(self):
        run_id = self.enqueue(self.actors[1])
        def failed_binding(job):
            raise ConnectionError("private database address")
        for _ in range(3):
            run_one(queue=self.queue, store=self.store, handlers={}, bind_job=failed_binding)
            with self.store._conn() as conn:
                conn.execute("UPDATE jobs SET not_before=NULL WHERE run_id=%s", (run_id,))
        self.assertEqual(self.queue.get(run_id).status, "DEAD")
        run = self.store.read_run(run_id)
        self.assertEqual(run["status"], "FAILED")
        self.assertNotIn("private database", str(run))

        mismatched_run = self.enqueue(self.actors[1])
        with self.store._conn() as conn:
            conn.execute("UPDATE jobs SET actor_id=%s WHERE run_id=%s", (self.actors[0], mismatched_run))
        job = self.queue.claim(worker="synthetic")
        self.queue.fail(job.job_id, "mismatched actor regression", retryable=False)
        self.assertEqual(self.store.read_run(mismatched_run)["status"], "PLANNED")

    def test_dead_job_reconciliation_preserves_completed_run(self):
        run_id = self.enqueue(self.actors[0])
        job = self.queue.claim(worker="synthetic")
        self.store.set_run(run_id, status="ANSWERED", result={"answer": "preserved"})
        self.queue.fail(job.job_id, "late failure", retryable=False)
        self.assertEqual(self.store.read_run(run_id)["status"], "ANSWERED")
        self.assertEqual(self.store.read_run(run_id)["result"], {"answer": "preserved"})


if __name__ == "__main__":
    unittest.main()
