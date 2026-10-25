"""Draft saves cannot silently reuse readiness after their evidence changes."""
import unittest

from checker.draft_versions import Version, VersionError, to_text, REVISION_REVIEW
from checker.provenance_slots import Slot, USER_FACT
from gateway.store import MemoryBackend
from gateway.verbs import Context, _draft_create, _draft_revise, _draft_versions, _draft_export


class DraftReviewIntegrity(unittest.TestCase):
    def setUp(self):
        self.ctx = Context(store=MemoryBackend())

    def create(self, body="Confirmed meeting date", slots=None):
        return _draft_create({"title": "Client note", "body": body,
                              "slots": slots or []}, self.ctx)

    def test_empty_and_unsourced_bodies_need_review_in_status_history_and_export(self):
        for body in ("", "   ", "A statement with no provenance"):
            with self.subTest(body=body):
                result = self.create(body)
                self.assertFalse(result["ready_for_approval"])
                self.assertTrue(result["review_items"])
                versions = _draft_versions({"draft_id": result["draft_id"]}, self.ctx)
                self.assertFalse(versions["versions"][0]["ready"])
                exported = _draft_export({"draft_id": result["draft_id"], "format": "text"}, self.ctx)
                self.assertIn("NOT APPROVABLE", exported["text"])
                self.assertNotIn("APPROVAL: available", exported["text"])
                stored = self.ctx.store.read_draft_versions(result["draft_id"])[0]
                self.assertEqual(stored["blocking_count"], len(result["blocking"]))

    def test_edit_invalidates_provenance_and_cannot_erase_gate(self):
        made = self.create(slots=[{"name": "date", "value": "Confirmed meeting date", "type": USER_FACT}])
        self.assertTrue(made["ready_for_approval"])
        revised = _draft_revise({"draft_id": made["draft_id"], "base_version": 1,
                                 "body": "An unsupported legal conclusion"}, self.ctx)
        self.assertIn(REVISION_REVIEW, revised["blocking"])
        erased = _draft_revise({"draft_id": made["draft_id"], "base_version": 2,
                                "slots": [{"name": REVISION_REVIEW, "value": "approved", "type": USER_FACT}]}, self.ctx)
        self.assertIn(REVISION_REVIEW, erased["blocking"])
        self.assertFalse(erased["approved"])
        before = _draft_versions({"draft_id": made["draft_id"]}, self.ctx)["versions"][0]
        self.assertEqual(before["body"], "Confirmed meeting date")
        self.assertTrue(before["ready"])

    def test_title_only_edit_does_not_invalidate_text_and_stale_edit_conflicts(self):
        made = self.create(slots=[{"name": "date", "value": "Confirmed meeting date", "type": USER_FACT}])
        revised = _draft_revise({"draft_id": made["draft_id"], "base_version": 1,
                                 "title": "Updated title"}, self.ctx)
        self.assertTrue(revised["ready_for_approval"])
        stale = _draft_revise({"draft_id": made["draft_id"], "base_version": 1,
                               "body": "stale edit"}, self.ctx)
        self.assertEqual(stale["code"], "CONFLICT")

    def test_create_cannot_overwrite_a_blocked_revision(self):
        made = self.create()
        _draft_revise({"draft_id": made["draft_id"], "base_version": 1,
                       "body": "Changed text"}, self.ctx)
        duplicate = _draft_create({"draft_id": made["draft_id"], "title": "Overwrite",
                                   "body": "New fact", "slots": [
                                       {"name": "fact", "value": "New fact", "type": USER_FACT}]}, self.ctx)
        self.assertEqual(duplicate["code"], "CREATE_CONFLICT")
        history = _draft_versions({"draft_id": made["draft_id"]}, self.ctx)
        self.assertEqual(len(history["versions"]), 2)
        self.assertEqual(history["title"], "Client note")
        self.assertIn(REVISION_REVIEW, history["versions"][-1]["blocking"])

    def test_legacy_approval_remains_readable_but_needs_current_review(self):
        import uuid
        did = str(uuid.uuid4())
        self.ctx.store.write_draft({"draft_id": did, "title": "Legacy", "actor_id": "unknown"})
        self.ctx.store.append_draft_version({"draft_id": did, "title": "Legacy",
            "body": "Old text", "slots": [], "blocking_count": 0,
            "approved_by": "historical reviewer", "approved_at": "2026-10-01T00:00:00Z"})
        v = _draft_versions({"draft_id": did}, self.ctx)["versions"][0]
        self.assertFalse(v["ready"])
        self.assertFalse(v["approved"])
        self.assertTrue(v["historical_approval"])
        self.assertEqual(v["approved_by"], "historical reviewer")
        row = self.ctx.store.list_drafts(limit=20)[0]
        self.assertEqual(row["blocking_count"], len(v["blocking"]))
        self.assertFalse(row["approved"])
        self.assertIn("NOT APPROVABLE", _draft_export({"draft_id": did, "format": "text"}, self.ctx)["text"])
        from checker.draft_versions import docx_text
        import base64
        export = _draft_export({"draft_id": did}, self.ctx)
        self.assertIn("NOT APPROVABLE", docx_text(base64.b64decode(export["docx_base64"])))

    def test_create_failure_leaves_no_metadata_and_same_id_can_retry(self):
        import uuid
        did = str(uuid.uuid4())
        store = self.ctx.store
        from gateway.store import StoreError
        with self.assertRaises(StoreError):
            store.create_draft({"draft_id": did, "title": "New"},
                               {"title": "", "body": "Text", "slots": []})
        self.assertIsNone(store.read_draft(did))
        self.assertEqual(store.read_draft_versions(did), [])
        self.assertEqual(store.create_draft({"draft_id": did, "title": "New"},
                         {"title": "New", "body": "Text", "slots": []}), 1)

    def test_concurrent_memory_creates_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        import uuid
        did = str(uuid.uuid4())
        args = {"draft_id": did, "title": "Concurrent", "body": "Text"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: _draft_create(args, self.ctx), range(12)))
        self.assertEqual(sum(r.get("draft_id") == did for r in results), 1)
        self.assertEqual(len(self.ctx.store.read_draft_versions(did)), 1)

    def test_non_array_citations_are_refused_without_writing(self):
        for value in (1, "source", {"id": "source"}, False):
            with self.subTest(value=value):
                result = _draft_create({"title": "Test", "body": "Text", "citations": value}, self.ctx)
                self.assertEqual(result["code"], "BAD_REQUEST")
        self.assertEqual(self.ctx.store.drafts, {})

    def test_blank_body_blocks_even_with_supported_slots(self):
        v = Version("draft", 1, "Title", " ", (Slot("fact", "fact", USER_FACT),),
                    created_at="2026-10-23T00:00:00+00:00")
        self.assertFalse(v.ready)
        with self.assertRaises(VersionError):
            v.approve("reviewer", "2026-10-23T00:00:00+00:00")
        self.assertIn("NOT APPROVABLE", to_text(v))


if __name__ == "__main__":
    unittest.main()
