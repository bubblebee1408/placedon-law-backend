"""The composer catalog exposes bounded metadata, scoped exactly like attachment reads."""
import hashlib
import unittest
import uuid
from gateway import verbs
from gateway.store import MemoryBackend


class VaultCatalog(unittest.TestCase):
    def setUp(self):
        self.store = MemoryBackend()
        self.ctx = verbs.Context(store=self.store)
        self.matter = str(uuid.uuid4())
        self.store.write_matter({"matter_id": self.matter, "name": "Matter A"})
        self.ids = []
        for i, (name, scope, state) in enumerate([
            ("Court order.pdf", None, "INGESTED"),
            ("Court scanned.pdf", None, "CANNOT_READ"),
            ("Awaiting.docx", None, "PENDING"),
            ("Matter order.pdf", self.matter, "INGESTED"),
            ("Deleted.pdf", None, "DELETED"),
            ("100%_draft.docx", None, "INGESTED"),
        ]):
            did = str(uuid.uuid4()); self.ids.append(did)
            self.store.write_vault_document({"document_id": did, "name": name,
                "matter_id": scope, "state": state, "sha256": hashlib.sha256(str(i).encode()).hexdigest(),
                "deleted_at": "2026-10-11T00:00:00Z" if state == "DELETED" else None})

    def test_unfiled_does_not_mean_all_matters(self):
        result = verbs._vault_list({}, self.ctx)
        self.assertEqual(result["scope"], "unfiled")
        self.assertEqual(len(result["documents"]), 4)
        self.assertTrue(all(d["matter_id"] is None for d in result["documents"]))
        self.assertTrue(all(len(d["sha256"]) == 64 for d in result["documents"]))
        self.assertNotIn(self.ids[4], [d["document_id"] for d in result["documents"]])
        self.assertTrue(all(set(d) == {"document_id", "sha256", "name", "state", "matter_id", "byte_count", "doc_class"}
                            for d in result["documents"]))

    def test_matter_and_filename_filter(self):
        result = verbs._vault_list({"matter_id": self.matter, "query": "ORDER"}, self.ctx)
        self.assertEqual([d["document_id"] for d in result["documents"]], [self.ids[3]])
        self.assertEqual(verbs._vault_list({"query": "%_"}, self.ctx)["documents"][0]["document_id"], self.ids[5])

    def test_pagination_has_no_overlap_and_includes_unready_states(self):
        first = verbs._vault_list({"limit": "2"}, self.ctx)
        second = verbs._vault_list({"limit": 2, "offset": first["next_offset"]}, self.ctx)
        self.assertIsNone(second["next_offset"])
        combined = first["documents"] + second["documents"]
        self.assertEqual(len({d["document_id"] for d in combined}), 4)
        self.assertEqual({d["state"] for d in combined}, {"INGESTED", "PENDING", "CANNOT_READ"})

    def test_unknown_matter_and_invalid_input_are_refused(self):
        self.assertEqual(verbs._vault_list({"matter_id": str(uuid.uuid4())}, self.ctx)["code"], "NOT_FOUND")
        for args in ({"matter_id": ""}, {"matter_id": []}, {"query": None}, {"query": "x"*121},
                     {"limit": True}, {"limit": 0}, {"limit": 51}, {"limit": 2.5}, {"offset": -1}, {"offset": 10001}):
            with self.subTest(args=args):
                self.assertEqual(verbs._vault_list(args, self.ctx)["code"], "BAD_REQUEST")

    def test_other_tenant_cannot_browse_first_tenants_rows(self):
        other = verbs.Context(store=MemoryBackend(tenant_id=str(uuid.uuid4())))
        self.assertEqual(verbs._vault_list({}, other)["documents"], [])
        self.assertEqual(verbs._vault_list({"matter_id": self.matter}, other)["code"], "NOT_FOUND")

    def test_route_is_read_only_and_not_mcp_exposed(self):
        verb = verbs.by_name()["vault.list"]
        self.assertTrue(verb.read_only)
        self.assertFalse(verb.mcp)
        self.assertEqual(verbs.rest_spec()["vault.list"]["path"], "/v2/vault/list")


class VaultCatalogHttp(unittest.TestCase):
    def test_authenticated_viewer_can_browse_and_unknown_tenant_cannot(self):
        from starlette.testclient import TestClient
        from gateway.auth import KeyStore
        from gateway.app import create_app
        keys = KeyStore()
        key, _ = keys.mint(tenant_id=str(uuid.uuid4()), actor=str(uuid.uuid4()), role="viewer")
        other_key, _ = keys.mint(tenant_id=str(uuid.uuid4()), actor=str(uuid.uuid4()), role="viewer")
        app = create_app(keys=keys, db_url="")
        with TestClient(app) as client:
            self.assertEqual(client.post("/v2/vault/list", json={}).status_code, 401)
            # A first call initialises this tenant's in-memory store.
            response = client.post("/v2/vault/list", json={}, headers={"Authorization": "Bearer " + key})
            self.assertEqual(response.status_code, 200, response.text)
            store = app.state.memory_backend
            store.write_vault_document({"document_id": str(uuid.uuid4()), "name": "Court order.pdf", "state": "INGESTED", "sha256": "a"*64})
            listed = client.post("/v2/vault/list", json={"limit": "30", "offset": "0", "query": "order"}, headers={"Authorization": "Bearer " + key})
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(listed.json()["documents"][0]["name"], "Court order.pdf")
            other = client.post("/v2/vault/list", json={}, headers={"Authorization": "Bearer " + other_key})
            self.assertEqual(other.status_code, 503, other.text)
            self.assertNotIn("Court order.pdf", other.text)


if __name__ == "__main__":
    unittest.main()
