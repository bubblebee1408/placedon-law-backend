"""Client text -- typed questions, attached documents, contract text -- never reaches Azure
(UAE North) unless an operator has accepted that region for client data
(PLACEDON_ACCEPT_REGION). A task's name authorizes nothing: every path goes through the
REAL Azure adapter here, and only its network call (`azure_model._call`) is replaced by a
recorder. If a marker from client text appears in a recorded request, it would have left.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from checker import azure_model, router
from gateway import verbs

MARKER = "KESTREL-CONFIDENTIAL-7731"
QUESTION = f"Under Section 173, what notice is needed for our client's board meeting? {MARKER}"
DOCUMENT = (f"SERVICES AGREEMENT between Kestrel Analytics and Marlowe Textiles. {MARKER}. "
            "Either party may terminate on ninety days' written notice.")


class _Budget:
    class _Ok:
        allowed, reason, id = True, "", 1
        verdict = None

    def can_make_call(self, *_a, **_k):
        return self._Ok()

    def reserve(self, **_k):
        return self._Ok()

    def settle(self, *_a, **_k):
        return self._Ok()


class ClientTextNeverReachesAzure(unittest.TestCase):
    def setUp(self):
        self.sent = []

        def record(body, key, timeout):
            self.sent.append(str(body))
            return {"choices": [{"message": {"content": "NONE"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        env = {"AZURE_AI_API_KEY": "test-key", "AZURE_AI_ENDPOINT": "https://example.services.ai.azure.com"}
        for p in (patch.dict(os.environ, env), patch("checker.azure_model._call", side_effect=record),
                  patch("gateway.verbs._ledger", return_value=_Budget()),
                  patch("gateway.models.available_providers", return_value=(router.AZURE,))):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop(azure_model.ACCEPT_REGION_ENV, None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        from gateway.filestore import LocalFileStore
        from gateway.store import MemoryBackend
        self.ctx = verbs.Context(store=MemoryBackend(), files=LocalFileStore(tmp.name), actor="lawyer-a")

    def leaked(self):
        return [s for s in self.sent if MARKER in s]

    def test_research_question_is_refused_not_sent(self):
        out = verbs._ask({"question": QUESTION}, self.ctx)
        self.assertEqual(self.leaked(), [])
        self.assertEqual(self.sent, [], "no Azure request at all")
        self.assertEqual(out.get("code"), "NOT_PERMITTED", out)

    def test_an_accepted_region_is_the_only_thing_that_lets_a_question_go(self):
        with patch.dict(os.environ, {azure_model.ACCEPT_REGION_ENV: azure_model.DEPLOYMENT_REGION}):
            verbs._ask({"question": QUESTION}, self.ctx)
        self.assertTrue(self.sent, "with the region accepted, the question is sent")
        self.assertTrue(all("<source> the question" in s for s in self.sent),
                        "...inside a delimited, checked block")

    def test_research_with_an_attached_document_never_sends_the_document(self):
        doc = verbs._vault_upload({"name": "services.txt", "text": DOCUMENT}, self.ctx)
        with patch.dict(os.environ, {azure_model.ACCEPT_REGION_ENV: azure_model.DEPLOYMENT_REGION}):
            verbs.by_name()["conversation.send"].run(
                {"conversation_id": "c1", "text": "What notice is needed under Section 173?",
                 "file_ids": [doc["document_id"]], "task_override": "RESEARCH_QUESTION"}, self.ctx)
        # With files attached, research answers from local excerpts: no model call at all.
        self.assertEqual(self.sent, [], "attachments are searched locally; nothing is sent")

    def answered_run(self):
        """A REAL answered research run (retrieval + quote verification, stand-in model)."""
        from agents import research_question as rq
        from gateway.store import MemoryBackend
        q = "What notice is needed to call a board meeting under Section 173?"
        srcs = tuple(s for s, _o in rq.evidence(q))
        out = verbs._ask({"question": q}, verbs.Context(store=MemoryBackend(),
                                                        model_for=lambda _o: rq.quoting_model(srcs)))
        self.assertEqual(out["status"], "ANSWERED")
        return dict(out, question=QUESTION)

    def test_draft_prose_does_not_send_the_typed_question(self):
        prose, note = verbs._draft_prose("research_memo", self.answered_run(), self.ctx)
        self.assertEqual((self.leaked(), self.sent, prose), ([], [], []), note)
        self.assertIn("UAE North", note, "the draft says why no prose was written")

    def test_draft_prose_goes_only_once_the_region_is_accepted(self):
        with patch.dict(os.environ, {azure_model.ACCEPT_REGION_ENV: azure_model.DEPLOYMENT_REGION}):
            verbs._draft_prose("research_memo", self.answered_run(), self.ctx)
        self.assertTrue(self.sent, "the path really reaches the adapter")
        self.assertTrue(all("<source> the question" in s for s in self.leaked()),
                        "...with the question inside a delimited, checked block")

    def test_contract_review_of_a_real_contract_is_refused_before_any_call(self):
        out = verbs._review_contract({"text": DOCUMENT, "name": "services.txt"}, self.ctx)
        self.assertEqual((out.get("code"), self.sent), ("NOT_PERMITTED", []))

    def test_a_review_grid_cell_never_sends_the_document(self):
        answer = verbs._cell_answerer(self.ctx)
        with self.assertRaises(Exception):
            answer(f"What is the notice period? {MARKER}", "text", DOCUMENT)
        self.assertEqual(self.leaked(), [])


if __name__ == "__main__":
    unittest.main()
