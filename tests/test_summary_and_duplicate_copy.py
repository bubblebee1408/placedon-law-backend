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


if __name__ == "__main__":
    unittest.main()
