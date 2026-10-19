"""Opt-in evidence persistence and tenant isolation on a throwaway PostgreSQL database.

Uses the same explicit test URLs and non-privileged application role as the conversation
integration suite. No provider calls, production data, or production migrations.
"""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import urlparse
import uuid

from gateway.filestore import LocalFileStore
from gateway.store import PostgresBackend
from gateway.verbs import Context, _conversation_get, _conversation_send

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class DocumentEvidencePostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only explicitly named throwaway databases may be used")
        self.tenant, self.actor = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'synthetic evidence test')", (self.tenant,))
            conn.execute("INSERT INTO actors (actor_id, tenant_id, label) VALUES (%s,%s,'test')", (self.actor, self.tenant))
        with psycopg.connect(APP_URL) as conn:
            self.assertFalse(conn.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()[0])
        self.store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.actor)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.files = LocalFileStore(Path(temp.name))
        self.model = Mock(side_effect=AssertionError("Document evidence must not call a model"))
        self.ctx = Context(store=self.store, files=self.files, tenant=self.tenant,
                           actor=self.actor, model_for=self.model,
                           clock=lambda: "2026-10-19T00:00:00Z")

    def test_upload_evidence_reconnect_and_cross_tenant_denial(self):
        text = "Synthetic agreement 📖\n\nTermination requires thirty days’ written notice.\n\nNo real client data."
        document_id = str(uuid.uuid4())
        sha = self.files.put(text.encode())
        self.store.write_vault_document({"document_id": document_id, "name": "Synthetic.txt",
            "sha256": sha, "byte_count": len(text.encode()), "state": "INGESTED"})
        args = {"text": "What does the document say about termination?", "file_ids": [document_id],
                "sources": ["vault"], "request_id": str(uuid.uuid4())}
        first = _conversation_send(args, self.ctx)
        evidence = first["metadata"]["document_evidence"]
        self.assertEqual(evidence["status"], "EXCERPTS_FOUND")
        for passage in evidence["passages"]:
            self.assertEqual(passage["text"], text[passage["start"]:passage["end"]])
            self.assertEqual(passage["sha256"], sha)
        fresh_store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.actor)
        fresh_ctx = replace(self.ctx, store=fresh_store, documents={})
        replay = _conversation_send(args, fresh_ctx)
        self.assertEqual(first["message_id"], replay["message_id"])
        reopened = _conversation_get({"conversation_id": first["conversation_id"]}, fresh_ctx)
        self.assertEqual(len(reopened["messages"]), 2)
        self.assertEqual(reopened["messages"][1]["metadata"]["document_evidence"], evidence)
        other = replace(fresh_ctx, tenant=str(uuid.uuid4()), actor=str(uuid.uuid4()))
        other = replace(other, store=PostgresBackend(APP_URL, tenant_id=other.tenant, actor_id=other.actor))
        self.assertEqual(_conversation_get({"conversation_id": first["conversation_id"]}, other)["code"], "NOT_FOUND")
        self.assertIsNone(other.store.read_vault_document(document_id))
        self.model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
