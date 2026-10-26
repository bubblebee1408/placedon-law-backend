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


ACCEPTED = {azure_model.ACCEPT_REGION_ENV: azure_model.DEPLOYMENT_REGION}


class _Recorder(ClientTextNeverReachesAzure):
    """The harness alone: subclasses must not re-run the parent's tests."""


for _n in [n for n in vars(ClientTextNeverReachesAzure) if n.startswith("test_")]:
    setattr(_Recorder, _n, None)


class TestDataIsNotARequestFlag(_Recorder):
    """`test_data` used to exempt a document from the region rule on the caller's word: any
    API or UI request could send a real contract to UAE North by saying "fixture". Only an
    in-process test (Context.synthetic_fixtures) may now mark a document as synthetic."""

    def http(self):
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        keys = KeyStore()
        import uuid
        key, _ = keys.mint(tenant_id=str(uuid.uuid4()), actor=str(uuid.uuid4()), role="lawyer")
        client = TestClient(create_app(keys=keys, db_url=""))
        return lambda path, body: client.post(path, json=body, headers={"Authorization": "Bearer " + key})

    def test_no_request_value_of_test_data_sends_a_contract(self):
        post = self.http()
        for flag in (True, "yes", "true", "fixture", "synthetic"):
            body = post("/v2/review-contract", {"text": DOCUMENT, "name": "services.txt", "test_data": flag}).json()
            self.assertEqual(body.get("code"), "NOT_PERMITTED", (flag, body))
            self.assertIn("UAE North", body.get("detail", ""), "refused by the region rule, not something else")
        self.assertEqual(self.sent, [], "zero outbound requests")

    def test_conversation_dispatch_cannot_mark_a_contract_as_test_data(self):
        out = verbs.by_name()["conversation.send"].run(
            {"conversation_id": "c1", "text": DOCUMENT, "task_override": "REVIEW_CONTRACT",
             "test_data": "fixture"}, self.ctx)
        self.assertEqual(self.sent, [], out)
        self.assertIn("UAE North", str(out), "the region rule refused it")

    def test_a_request_cannot_inject_a_model_or_the_fixture_switch(self):
        post = self.http()
        body = post("/v2/ask", {"question": QUESTION, "model_for": "stub",
                                "synthetic_fixtures": True}).json()
        self.assertEqual((body.get("code"), self.sent), ("NOT_PERMITTED", []), body)
        body = post("/v2/review-contract", {"text": DOCUMENT, "test_data": "fixture", "model_for": "stub",
                                            "synthetic_fixtures": True}).json()
        self.assertEqual(body.get("code"), "NOT_PERMITTED", body)
        self.assertIn("UAE North", body.get("detail", ""))
        self.assertEqual(self.sent, [])

    def test_an_in_process_test_may_still_send_a_synthetic_fixture(self):
        from agents import review_contract as rc
        fx = rc.fixtures()[0]
        self.ctx.synthetic_fixtures = True
        verbs._review_contract({"text": fx.text, "name": fx.id, "test_data": "fixture"}, self.ctx)
        self.assertTrue(self.sent, "positive control: the permitted path reaches the adapter")
        line = next(x for x in fx.text.splitlines() if len(x) > 40)[:60]
        self.assertTrue(any(line in s for s in self.sent), "...carrying the fixture text")
        self.sent.clear()
        verbs._review_contract({"text": DOCUMENT, "name": "services.txt"}, self.ctx)
        self.assertEqual(self.sent, [], "...and the switch alone does not exempt an unmarked document")


class CallersMayOnlyNarrowProviders(_Recorder):
    """`ask` took a caller's provider list, but an empty list fell back to the default and
    the narrowing never reached the call that chose the provider."""

    def ask(self, available):
        with patch.dict(os.environ, ACCEPTED):
            return verbs._ask({"question": QUESTION, "available": available}, self.ctx)

    def test_empty_invalid_and_disallowed_lists_refuse_with_no_call(self):
        for available in ([], ["bedrock"], ["no-such-provider"]):
            out = self.ask(available)
            self.assertEqual(out.get("code"), "NO_MODEL", (available, out))
        self.assertEqual(self.sent, [], "no list restores the default route")

    def test_the_narrowing_reaches_the_call_that_picks_the_provider(self):
        seen = []
        real = verbs._served_or_refusal

        def spy(*a, **k):
            seen.append(k.get("allowed_providers"))
            return real(*a, **k)
        with patch("gateway.verbs._served_or_refusal", side_effect=spy):
            for available in ([], ["bedrock"], ["no-such-provider"], None):
                self.ask(available)
        self.assertEqual(seen, [(), (), (), ("azure",)])

    def test_a_malformed_list_is_a_bad_request(self):
        self.assertEqual(self.ask("azure").get("code"), "BAD_REQUEST")
        self.assertEqual(self.sent, [])

    def test_a_list_naming_the_declared_provider_still_works(self):
        self.ask(["azure", "bedrock"])
        self.assertTrue(self.sent, "positive control: narrowing to the declared provider")


if __name__ == "__main__":
    unittest.main()
