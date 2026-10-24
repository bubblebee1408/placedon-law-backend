"""Opt-in live PostgreSQL conversation tests, restricted to throwaway databases.

Set PLACEDON_CONVERSATION_TEST_DATABASE_URL and
PLACEDON_CONVERSATION_TEST_ADMIN_URL explicitly. This never reads deployment DB settings.
Migrations must already be applied; the tests assert the application role cannot bypass RLS.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from urllib.parse import urlparse
import uuid

from gateway.jobs import PostgresQueue
from gateway.store import PostgresBackend
from gateway.verbs import Context, _conversation_get, _conversation_send
from gateway.worker import run_one

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")
QUESTION = "What is the quorum under section 174 of the Companies Act?"


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class PostgresConversationReliability(unittest.TestCase):
    def setUp(self):
        import psycopg
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only an explicitly named throwaway database may be used")
        self.tenant, self.actor = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'conversation test')", (self.tenant,))
            c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) VALUES (%s,%s,'test lawyer','lawyer')", (self.actor, self.tenant))
        with psycopg.connect(APP_URL) as c:
            privileged = c.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]
            self.assertFalse(privileged, "App tests must run without superuser or RLS bypass")
        self.store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.actor)
        self.queue = PostgresQueue(APP_URL, tenant_id=self.tenant, actor_id=self.actor)
        self.ctx = Context(tenant=self.tenant, actor=self.actor, store=self.store, queue=self.queue,
                           clock=lambda: "2026-10-10T00:00:00Z")

    def send(self, **changes):
        return _conversation_send({"text": QUESTION, "request_id": str(uuid.uuid4()), **changes}, self.ctx)

    def counts(self):
        with self.store._conn() as c:
            return {table: c.execute("SELECT count(*) FROM " + table).fetchone()[0]
                    for table in ("conversations", "messages", "runs", "jobs")}

    def test_duplicate_request_is_one_transaction_across_connections(self):
        args = {"text": QUESTION, "request_id": "concurrent-same-request"}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: _conversation_send(args, self.ctx), range(36)))
        self.assertEqual(len({r["message_id"] for r in results}), 1)
        self.assertEqual(len({r["run_id"] for r in results}), 1)
        self.assertEqual(self.counts(), {"conversations": 1, "messages": 2, "runs": 1, "jobs": 1})
        self.assertEqual(self.send(request_id="concurrent-same-request", text="changed")["code"], "IDEMPOTENCY_CONFLICT")

    def test_concurrent_turn_pairs_do_not_collide(self):
        first = self.send()
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.send(conversation_id=first["conversation_id"]), range(20)))
        self.assertTrue(all(r.get("run_id") for r in results))
        messages = self.store.read_messages(first["conversation_id"])
        self.assertEqual([m["ordinal"] for m in messages], list(range(42)))
        self.assertTrue(all(m["role"] == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(messages)))

    def test_capacity_rejection_rolls_back_run_conversation_and_messages(self):
        self.queue.max_pending = 2
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.send(), range(20)))
        self.assertEqual(sum(bool(r.get("run_id")) for r in results), 2)
        self.assertEqual(sum(r.get("code") == "BUSY" for r in results), 18)
        self.assertEqual(self.counts(), {"conversations": 2, "messages": 4, "runs": 2, "jobs": 2})

    def test_worker_result_metadata_survives_new_connections(self):
        result = self.send()
        report = {"picked": ["held"], "searched": ["held"], "report": [], "note": "test"}
        run_one(queue=self.queue, store=self.store, handlers={"research_question":
            lambda _: ([], {"status": "PARTIAL", "answer": "Partial evidence.", "sources": report})})
        reopened = _conversation_get({"conversation_id": result["conversation_id"]}, self.ctx)["messages"][1]
        self.assertEqual(reopened["envelope"]["status"], "PARTIAL")
        self.assertEqual(reopened["metadata"]["sources"], report)
        other = PostgresBackend(APP_URL, tenant_id=str(uuid.uuid4()), actor_id=str(uuid.uuid4()))
        self.assertIsNone(other.read_conversation(result["conversation_id"]))
        self.assertEqual(other.read_messages(result["conversation_id"]), [])

    def test_database_rejects_one_sided_idempotency_columns(self):
        import psycopg
        result = self.send()
        for request_id, digest in ((None, "a" * 64), ("request-only-001", None)):
            with self.subTest(request_id=request_id), self.store._conn() as c:
                with self.assertRaises(psycopg.errors.CheckViolation):
                    c.execute("INSERT INTO messages (message_id, conversation_id, tenant_id, ordinal, role, request_id, payload_digest) VALUES (%s,%s,%s,2,'assistant',%s,%s)",
                              (str(uuid.uuid4()), result["conversation_id"], self.tenant, request_id, digest))
        self.assertEqual(len(self.store.read_messages(result["conversation_id"])), 2)

    def test_bounded_catalog_obeys_real_rls_and_matter_scope(self):
        from gateway.verbs import _vault_list
        matter = str(uuid.uuid4())
        self.store.write_matter({"matter_id": matter, "name": "Court matter"})
        for i, (name, scope, state) in enumerate([
            ("Unfiled order.pdf", None, "INGESTED"), ("100%_draft.docx", None, "PENDING"),
            ("Matter order.pdf", matter, "INGESTED"), ("Deleted.pdf", None, "DELETED"),
        ]):
            self.store.write_vault_document({"document_id": str(uuid.uuid4()), "sha256": f"{i:064x}",
                "name": name, "matter_id": scope, "state": state, "byte_count": 40})
        first = _vault_list({"limit": "1"}, self.ctx)
        second = _vault_list({"limit": "1", "offset": str(first["next_offset"])}, self.ctx)
        self.assertEqual(len(first["documents"] + second["documents"]), 2)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(_vault_list({"query": "%_"}, self.ctx)["documents"][0]["name"], "100%_draft.docx")
        self.assertEqual(len(_vault_list({"matter_id": matter}, self.ctx)["documents"]), 1)
        other = PostgresBackend(APP_URL, tenant_id=str(uuid.uuid4()), actor_id=str(uuid.uuid4()))
        self.assertEqual(other.browse_vault_documents(matter_id=None, query="", limit=30, offset=0), [])
        self.assertEqual(other.browse_vault_documents(matter_id=matter, query="", limit=30, offset=0), [])

    def test_draft_create_race_cannot_replace_existing_revision(self):
        from gateway.verbs import _draft_create, _draft_revise, _draft_versions
        did = str(uuid.uuid4())
        args = {"draft_id": did, "title": "Concurrent draft", "body": "Initial text"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: _draft_create(args, self.ctx), range(8)))
        self.assertEqual(sum(r.get("draft_id") == did for r in results), 1)
        self.assertEqual(sum(r.get("code") == "CREATE_CONFLICT" for r in results), 7)
        _draft_revise({"draft_id": did, "base_version": 1, "body": "Changed"}, self.ctx)
        self.assertEqual(_draft_create(args, self.ctx)["code"], "CREATE_CONFLICT")
        history = _draft_versions({"draft_id": did}, self.ctx)["versions"]
        self.assertEqual(len(history), 2)
        self.assertFalse(history[-1]["ready"])

    def test_legacy_draft_list_matches_current_review_policy(self):
        from gateway.verbs import _draft_versions
        did = str(uuid.uuid4())
        self.store.write_draft({"draft_id": did, "title": "Legacy"})
        self.store.append_draft_version({"draft_id": did, "title": "Legacy", "body": "",
            "slots": [], "blocking_count": 0, "approved_by": "historical reviewer",
            "approved_at": "2026-10-01T00:00:00Z"})
        detail = _draft_versions({"draft_id": did}, self.ctx)["versions"][0]
        row = self.store.list_drafts(limit=20)[0]
        self.assertEqual(row["blocking_count"], len(detail["blocking"]))
        self.assertFalse(row["approved"])
        self.assertTrue(detail["historical_approval"])

    def test_first_version_database_failure_rolls_back_metadata(self):
        from unittest.mock import patch
        from gateway import store as store_module
        from gateway.verbs import _draft_create
        did = str(uuid.uuid4())
        insert = store_module._insert_draft_version
        def invalid_version(connection, tenant, version, number):
            # Trigger the real version-number CHECK after the draft row was inserted.
            return insert(connection, tenant, version, 0)
        args = {"draft_id": did, "title": "Rollback test", "body": "Text"}
        with patch.object(store_module, "_insert_draft_version", invalid_version):
            refused = _draft_create(args, self.ctx)
        self.assertEqual(refused["status"], "REFUSED")
        self.assertIsNone(self.store.read_draft(did))
        self.assertEqual(self.store.read_draft_versions(did), [])
        self.assertEqual(_draft_create(args, self.ctx)["version"], 1)


if __name__ == "__main__":
    unittest.main()
