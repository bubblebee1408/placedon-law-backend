"""What a person is told when a summary cannot run, and when they upload a file twice."""
import tempfile
import unittest

from gateway import verbs


class SummaryRefusalWording(unittest.TestCase):
    def test_no_permitted_summary_model_is_not_a_transient_try_again(self):
        result = {"status": "REFUSED", "code": "NO_MODEL", "document_summary_refused": True,
                  "detail": "No permitted document-summary model is available. No summary was generated."}
        env = verbs._envelope_for("RESEARCH_QUESTION", result, as_of="2026-10-26", ctx=verbs.Context())
        text = " ".join(b["text"] for b in env["text_blocks"])
        self.assertIn("No permitted document-summary model is available", text)
        self.assertNotIn("Try again", text)

    def test_a_research_answer_without_a_model_keeps_its_own_wording(self):
        env = verbs._envelope_for("RESEARCH_QUESTION", {"status": "REFUSED", "code": "NO_MODEL"},
                                  as_of="2026-10-26", ctx=verbs.Context())
        self.assertIn("Try again", " ".join(b["text"] for b in env["text_blocks"]))


class DuplicateUploadWording(unittest.TestCase):
    def test_a_repeat_upload_says_it_is_your_own_earlier_copy(self):
        from gateway.filestore import LocalFileStore
        from gateway.store import MemoryBackend
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        ctx = verbs.Context(store=MemoryBackend(), files=LocalFileStore(tmp.name), actor="lawyer-a")
        first = verbs._vault_upload({"name": "nda.txt", "text": "Synthetic NDA text."}, ctx)
        again = verbs._vault_upload({"name": "nda-renamed.txt", "text": "Synthetic NDA text."}, ctx)
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["document_id"], first["document_id"])
        self.assertIn("You already uploaded these bytes as 'nda.txt'", again["note"])
        self.assertNotIn("workspace's vault", again["note"])


class DuplicateWordingByScope(unittest.TestCase):
    """Reproduced in review of #119: the duplicate note assumed every duplicate was the
    caller's own unfiled upload."""
    def setUp(self):
        from gateway.filestore import LocalFileStore
        from gateway.store import MemoryBackend
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store, self.files = MemoryBackend(), LocalFileStore(tmp.name)
        self.store.write_matter({"matter_id": "m1", "name": "Acme"}, owner="lawyer-a")
        self.store.grant_matter_access(matter_id="m1", actor_id="lawyer-b", role="member",
                                       granted_by="admin", reason="joined the deal team")

    def ctx(self, actor):
        return verbs.Context(store=self.store, files=self.files, actor=actor)

    def test_a_colleagues_filed_copy_is_not_called_your_upload(self):
        verbs._vault_upload({"name": "spa.txt", "text": "Synthetic SPA.", "matter_id": "m1"}, self.ctx("lawyer-a"))
        again = verbs._vault_upload({"name": "spa-b.txt", "text": "Synthetic SPA.", "matter_id": "m1"}, self.ctx("lawyer-b"))
        self.assertTrue(again["duplicate"])
        self.assertNotIn("You already uploaded", again["note"])
        self.assertIn("This matter already holds these bytes as 'spa.txt'", again["note"])

    def test_re_uploading_a_deleted_unfiled_file_says_what_happened(self):
        first = verbs._vault_upload({"name": "nda.txt", "text": "Synthetic NDA."}, self.ctx("lawyer-a"))
        verbs._vault_delete({"document_id": first["document_id"]}, self.ctx("lawyer-a"))
        again = verbs._vault_upload({"name": "nda.txt", "text": "Synthetic NDA."}, self.ctx("lawyer-a"))
        self.assertEqual(again.get("code"), "CONFLICT")
        self.assertNotIn("in this matter", again["detail"])
        self.assertIn("deleted", again["detail"])


if __name__ == "__main__":
    unittest.main()
