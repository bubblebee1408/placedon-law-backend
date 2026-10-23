"""Queue identity simulations: no provider calls, no real customer data."""
import unittest
from unittest.mock import patch

from gateway.jobs import Job, MemoryQueue, PostgresQueue
from gateway.store import MemoryBackend
from gateway.worker import run_one, postgres_job_bindings


class ScopedStore(MemoryBackend):
    kind = "postgres"

    def __init__(self, tenant, actor, disabled=False):
        super().__init__()
        self.kind = "postgres"
        self.tenant_id = tenant
        self.actor_id = actor
        self.write_actor({"actor_id": actor, "role": "lawyer",
                          "disabled_at": "2026-10-19" if disabled else None})


class ActorIdentityTests(unittest.TestCase):
    def test_postgres_projection_retains_identity(self):
        job = PostgresQueue._job(("j", "r", "ask", {"actor_id": "spoof"},
                                 "QUEUED", 0, False, "BULK", "", "tenant", "alice"))
        self.assertEqual((job.tenant_id, job.actor_id), ("tenant", "alice"))

    def test_memory_default_remains_compatible(self):
        queue, store = MemoryQueue(), MemoryBackend()
        store.write_run({"id": "r", "intent": "ask", "status": "PLANNED"})
        queue.enqueue(run_id="r", intent="ask", args={})
        outcome = run_one(queue=queue, store=store,
                          handlers={"ask": lambda a: ([], {"status": "ANSWERED"})})
        self.assertEqual(outcome.status, "ANSWERED")

    def make_bound(self, actor="alice", disabled=False):
        queue = MemoryQueue(tenant_id="tenant", actor_id=actor)
        store = ScopedStore("tenant", actor, disabled)
        store.write_run({"id": "r", "intent": "ask", "status": "PLANNED"})
        queue.enqueue(run_id="r", intent="ask", args={"actor_id": "mallory"})
        return queue, store

    def test_fixed_wrong_actor_never_invokes_handler_or_writes_other_store(self):
        queue, alice = self.make_bound()
        bob = ScopedStore("tenant", "bob")
        called = []
        outcome = run_one(queue=queue, store=bob,
                          handlers={"ask": lambda a: called.append(a)})
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(called, [])
        self.assertEqual(bob.runs, {})
        self.assertEqual(queue.get("r").status, "DEAD")
        self.assertEqual(alice.read_run("r")["status"], "PLANNED")

    def test_bound_factory_receives_row_identity_not_untrusted_args(self):
        queue, alice = self.make_bound()
        seen = []
        def bind(job):
            seen.append((job.tenant_id, job.actor_id))
            return alice, {"ask": lambda args: ([], {"status": "ANSWERED"})}
        outcome = run_one(queue=queue, store=ScopedStore("tenant", "worker"),
                          handlers={}, bind_job=bind)
        self.assertEqual(seen, [("tenant", "alice")])
        self.assertEqual(outcome.status, "ANSWERED")
        self.assertEqual(alice.read_run("r")["status"], "ANSWERED")

    def test_disabled_actor_is_rechecked_before_handler(self):
        queue, store = self.make_bound(disabled=True)
        calls = []
        outcome = run_one(queue=queue, store=store,
                          handlers={"ask": lambda a: calls.append(a)})
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(calls, [])
        self.assertEqual(queue.get("r").status, "DEAD")
        self.assertEqual(store.read_run("r")["status"], "FAILED")

    def test_missing_identity_on_durable_worker_fails_closed(self):
        queue, store = MemoryQueue(), ScopedStore("tenant", "alice")
        queue.enqueue(run_id="r", intent="ask", args={})
        calls = []
        outcome = run_one(queue=queue, store=store,
                          handlers={"ask": lambda a: calls.append(a)})
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(calls, [])
        self.assertEqual(queue.get("r").status, "DEAD")

    def test_factory_failure_is_retryable_without_handler(self):
        queue, store = self.make_bound()
        def bind(job):
            raise ConnectionError("private database address")
        outcome = run_one(queue=queue, store=store, handlers={}, bind_job=bind)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(queue.get("r").status, "QUEUED")
        self.assertNotIn("private database", outcome.error)

    def test_factory_constructs_context_for_each_authenticated_actor(self):
        import uuid
        tenant = str(uuid.uuid4())
        actors = (str(uuid.uuid4()), str(uuid.uuid4()))
        observed = []
        def handlers(ctx):
            observed.append((ctx.tenant, ctx.actor, ctx.store.actor_id, ctx.queue.actor_id))
            return {}
        with patch("gateway.verbs.queue_handlers", side_effect=handlers):
            bind = postgres_job_bindings("postgresql:///unused", tenant_id=tenant)
            for actor in actors:
                bind(Job("j", "r", "ask", {"actor_id": "spoof"},
                         tenant_id=tenant, actor_id=actor))
        self.assertEqual(observed, [(tenant, a, a, a) for a in actors])

    def test_missing_and_demoted_actors_are_blocked(self):
        for role in (None, "viewer"):
            with self.subTest(role=role):
                queue, store = self.make_bound()
                if role is None:
                    store.actors.clear()
                else:
                    store.write_actor({"actor_id": "alice", "role": role})
                calls = []
                outcome = run_one(queue=queue, store=store,
                                  handlers={"ask": lambda a: calls.append(a)})
                self.assertEqual(outcome.status, "FAILED")
                self.assertEqual(calls, [])
                self.assertEqual(queue.get("r").status, "DEAD")

    def test_cross_tenant_metadata_never_reaches_binding(self):
        queue, store = self.make_bound()
        queue.jobs[next(iter(queue.jobs))]["tenant_id"] = "other"
        calls = []
        outcome = run_one(queue=queue, store=store, handlers={},
                          bind_job=lambda job: calls.append(job))
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(calls, [])
        self.assertEqual(queue.get("r").status, "DEAD")

    def test_actor_lookup_outage_records_failure_and_retries(self):
        queue, store = self.make_bound()
        with patch.object(store, "read_actor", side_effect=ConnectionError("private address")):
            outcome = run_one(queue=queue, store=store, handlers={})
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(store.read_run("r")["status"], "FAILED")
        self.assertEqual(queue.get("r").status, "QUEUED")
        self.assertNotIn("private address", str(store.read_run("r")))

    def test_binding_outage_exhausts_retries_without_wrong_store_write(self):
        queue, store = self.make_bound()
        def bind(job):
            raise ConnectionError("private address")
        for _ in range(3):
            run_one(queue=queue, store=store, handlers={}, bind_job=bind)
            queue.jobs[next(iter(queue.jobs))]["not_before"] = None
        self.assertEqual(queue.get("r").status, "DEAD")
        self.assertEqual(store.read_run("r")["status"], "PLANNED")
        self.assertIn("context could not be restored", queue.get("r").dead_reason)


if __name__ == "__main__":
    unittest.main()
