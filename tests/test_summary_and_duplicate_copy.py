"""What a person is told when a summary cannot run, and when they upload a file twice."""
import tempfile
import unittest

from gateway import verbs


class SummaryRefusalWording(unittest.TestCase):
    def test_no_permitted_summary_model_is_not_a_transient_try_again(self):
        env = verbs._envelope_for("RESEARCH_QUESTION", verbs._summary_unavailable("NO_PERMITTED_PROVIDER"),
                                  as_of="2026-10-26", ctx=verbs.Context())
        text = " ".join(b["text"] for b in env["text_blocks"])
        self.assertIn("No document-summary model permitted for client documents is configured", text)
        self.assertNotIn("Try again", text)

    def test_a_research_answer_without_a_model_keeps_its_own_wording(self):
        env = verbs._envelope_for("RESEARCH_QUESTION", {"status": "REFUSED", "code": "NO_MODEL"},
                                  as_of="2026-10-26", ctx=verbs.Context())
        self.assertIn("Try again", " ".join(b["text"] for b in env["text_blocks"]))


class SummaryUnavailableIsNotRetryable(unittest.TestCase):
    """A known configuration/access block is its own state, kept on the turn so a reopened
    conversation shows it too; a transient provider failure stays a retryable FAILED."""

    def test_bedrocks_operation_not_allowed_is_an_access_state_not_a_failure(self):
        from checker.bedrock_model import _is_not_ready
        class ValidationException(Exception):
            pass
        self.assertTrue(_is_not_ready(ValidationException(
            "An error occurred (ValidationException) when calling the Converse operation: Operation not allowed")))
        class AccessDeniedException(Exception):
            pass
        self.assertTrue(_is_not_ready(AccessDeniedException("explicit deny in a service control policy")))
        class ThrottlingException(Exception):
            pass
        self.assertFalse(_is_not_ready(ThrottlingException("Too many requests")))

    def test_an_access_refusal_during_the_call_is_unavailable_not_retry(self):
        from checker.bedrock_model import ProviderNotReady, Throttled
        blocked = verbs._summary_call_failure(ProviderNotReady("ValidationException: Operation not allowed"))
        self.assertEqual((blocked["code"], blocked["document_summary_unavailable"]["retryable"]),
                         ("SUMMARY_UNAVAILABLE", False))
        self.assertEqual(blocked["document_summary_unavailable"]["reason"], "PROVIDER_REFUSED_ACCESS")
        for transient in (Throttled("slow down"), TimeoutError("read timed out"), RuntimeError("HTTP 503")):
            with self.subTest(transient=type(transient).__name__):
                out = verbs._summary_call_failure(transient)
                self.assertEqual((out["status"], out["code"]), ("FAILED", "SUMMARY_PROVIDER_FAILED"))
                self.assertNotIn("document_summary_unavailable", out)

    def test_the_unavailable_state_rides_the_turn_and_says_what_happened(self):
        result = verbs._summary_unavailable("NO_PERMITTED_PROVIDER")
        env = verbs._envelope_for("RESEARCH_QUESTION", result, as_of="2026-10-26", ctx=verbs.Context())
        text = " ".join(b["text"] for b in env["text_blocks"])
        self.assertIn("Document summarization is unavailable", text)
        self.assertIn("Retrying will not help", text)
        self.assertNotIn("Try again", text)
        meta = verbs._turn_metadata({}, result)
        self.assertEqual(meta["document_summary_unavailable"],
                         {"reason": "NO_PERMITTED_PROVIDER", "retryable": False})
        self.assertNotIn("document_summary_unavailable",
                         verbs._turn_metadata({}, {"status": "FAILED", "code": "SUMMARY_PROVIDER_FAILED"}))


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
