"""Which provider may serve which task is declared per task, never inferred from which
credentials happen to be present.

Adding AWS credentials used to move research narration from Azure to Bedrock silently,
because router.py's NARRATION table lists Bedrock first. And most call sites clear their
text for ONE named provider (public_only.clear_matter(..., provider=...)) while the router
could pick another. TASK_PROVIDERS pins each task to the provider(s) its text is cleared
for; an unavailable provider is a refusal, never a substitute.
"""
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from checker import router
from gateway import verbs

AZ, BR, OL = router.AZURE, router.BEDROCK, router.OLLAMA


def serve_with(available, name, purpose, consequence=router.LOW, accept_azure=False):
    """Run the REAL router and serve() with stubbed adapters; return (provider|None, refusal)."""
    stub = lambda **_: (lambda prompt: "stub")                  # noqa: E731
    with patch("gateway.verbs._ledger", return_value=_Budget()), \
         patch("checker.azure_model.region_accepted", return_value=accept_azure), \
         patch("gateway.models.available_providers", return_value=available), \
         patch("checker.bedrock_model.as_text_model", side_effect=stub), \
         patch("checker.azure_model.as_text_model", side_effect=stub), \
         patch.dict("os.environ", {"OLLAMA_MODEL": "llama3:latest",
                                   "OLLAMA_BASE_URL": "http://127.0.0.1:11434"}):
        served, refusal = verbs._served_or_refusal((), name=name, purpose=purpose,
                                                   consequence=consequence, ctx=verbs.Context())
    return (served.provider if served else None), refusal


class _Budget:
    def can_make_call(self, *_a, **_k):
        class V:
            allowed, reason = True, ""
        return V()


class TaskProviderRouting(unittest.TestCase):
    def test_every_model_call_site_declares_its_providers(self):
        src = Path(verbs.__file__).read_text()
        names = set(re.findall(r'_served_or_refusal\([^)]*?name="([^"]+)"', src, re.S))
        self.assertTrue(names, "found the call sites")
        self.assertEqual(names - set(verbs.TASK_PROVIDERS), set(), "a model call with no declared provider")

    def test_both_providers_configured_research_on_bedrock_summary_on_bedrock(self):
        # Ask carries the user's typed question, so it goes to India, never Azure UAE.
        self.assertEqual(serve_with((AZ, BR), "ask", router.NARRATION), (BR, None))
        self.assertEqual(serve_with((AZ, BR), "draft_prose", router.NARRATION), (AZ, None))
        self.assertEqual(serve_with((AZ, BR), "document_summary", router.EXTRACTION, router.HIGH), (BR, None))

    def test_azure_alone_never_serves_ask(self):
        provider, refusal = serve_with((AZ,), "ask", router.NARRATION)
        self.assertIsNone(provider)
        self.assertEqual(refusal["code"], "NO_MODEL")

    def test_ask_falls_back_to_the_on_device_model_last(self):
        self.assertEqual(serve_with((OL,), "ask", router.NARRATION), (OL, None))
        self.assertEqual(serve_with((BR, OL), "ask", router.NARRATION), (BR, None))

    def test_azure_tasks_never_reach_the_on_device_model(self):
        provider, refusal = serve_with((OL,), "draft_prose", router.NARRATION)
        self.assertIsNone(provider)
        self.assertEqual(refusal["code"], "NO_MODEL")

    def test_missing_aws_credentials_refuse_summaries_rather_than_moving_them_to_azure(self):
        provider, refusal = serve_with((AZ,), "document_summary", router.EXTRACTION, router.HIGH)
        self.assertIsNone(provider)
        self.assertEqual(refusal["code"], "NO_MODEL")

    def test_no_credentials_at_all_is_a_refusal(self):
        self.assertEqual(serve_with((), "ask", router.NARRATION)[1]["code"], "NO_MODEL")

    def test_an_undeclared_task_is_refused_before_any_provider_is_chosen(self):
        with patch("gateway.models.serve") as serve, patch("gateway.verbs._ledger", return_value=_Budget()):
            served, refusal = verbs._served_or_refusal((), name="something_new", purpose=router.NARRATION,
                                                       ctx=verbs.Context())
        self.assertIsNone(served)
        self.assertEqual(refusal["code"], "NO_MODEL")
        serve.assert_not_called()

    def test_client_document_tasks_never_list_a_provider_outside_the_matter_set(self):
        from checker.public_only import MATTER_PROVIDERS
        for name, providers in verbs.TASK_PROVIDERS.items():
            allowed = MATTER_PROVIDERS | ({OL} if name in verbs.ON_DEVICE_TASKS else set())
            self.assertTrue(set(providers) <= allowed, name)
        self.assertEqual(verbs.ON_DEVICE_TASKS, {"ask"}, "only Ask may use the on-device model")
        self.assertNotIn(OL, MATTER_PROVIDERS, "never a global grant: contract review stays refused")
        self.assertEqual(verbs.TASK_PROVIDERS["document_summary"], (BR,), "summaries: India region only")


class AzureOptIn(unittest.TestCase):
    """Azure may serve Ask and summaries only after the operator accepts its region."""

    def test_accepted_region_serves_ask_and_summaries_on_azure(self):
        self.assertEqual(serve_with((AZ, OL), "ask", router.NARRATION, accept_azure=True), (AZ, None))
        self.assertEqual(serve_with((AZ,), "document_summary", router.EXTRACTION, router.HIGH,
                                    accept_azure=True), (AZ, None))

    def test_bedrock_still_comes_first_when_azure_is_accepted(self):
        self.assertEqual(serve_with((AZ, BR, OL), "ask", router.NARRATION, accept_azure=True), (BR, None))
        self.assertEqual(serve_with((AZ, BR), "document_summary", router.EXTRACTION, router.HIGH,
                                    accept_azure=True), (BR, None))

    def test_unaccepted_region_leaves_the_declared_routes_unchanged(self):
        with patch("checker.azure_model.region_accepted", return_value=False):
            for task in verbs.TASK_PROVIDERS:
                self.assertEqual(verbs.task_providers(task), verbs.TASK_PROVIDERS[task], task)
        self.assertEqual(serve_with((AZ, OL), "ask", router.NARRATION), (OL, None))

    def test_acceptance_widens_only_the_opt_in_tasks(self):
        with patch("checker.azure_model.region_accepted", return_value=True):
            for task in set(verbs.TASK_PROVIDERS) - verbs.AZURE_OPT_IN_TASKS:
                self.assertEqual(verbs.task_providers(task), verbs.TASK_PROVIDERS[task], task)
            self.assertEqual(verbs.task_providers("ask"), (BR, AZ, OL))
            self.assertEqual(verbs.task_providers("document_summary"), (BR, AZ))

    def test_summary_job_routes_through_the_opt_in(self):
        src = Path(verbs.__file__).read_text()
        self.assertIn('allowed_providers=task_providers("document_summary")', src)
        self.assertNotIn("allowed_providers=(router.BEDROCK,)", src)


class CallerCannotWidenProviders(unittest.TestCase):
    def test_ask_available_input_is_narrowed_to_the_declared_providers(self):
        from agents import research_question as rq
        from gateway.store import MemoryBackend
        q = "What notice is needed to call a board meeting under Section 173?"
        srcs = tuple(s for s, _o in rq.evidence(q))
        seen = {}
        real = rq.answer

        def spy(question, **kw):
            seen["available"] = kw.get("available")
            return real(question, **kw)
        ctx = verbs.Context(store=MemoryBackend(), model_for=lambda _o: rq.quoting_model(srcs))
        with patch.object(rq, "answer", side_effect=spy):
            verbs._ask({"question": q, "available": ["gemini", "ollama", "bedrock", "azure"]}, ctx)
        self.assertEqual(tuple(seen["available"]), ("bedrock", "ollama"), "gemini and azure dropped")


class ProviderFailureStates(unittest.TestCase):
    """What the summary task does when its one provider fails. (Research's own failure
    handling is unchanged: it never reaches Bedrock now.)"""

    def test_access_denied_and_operation_not_allowed_are_unavailable_not_retry(self):
        from checker.bedrock_model import ProviderNotReady, converse

        class AccessDeniedException(Exception):
            pass

        class ValidationException(Exception):
            pass
        for error in (AccessDeniedException("User is not authorized"), ValidationException("Operation not allowed")):
            with self.subTest(error=type(error).__name__):
                class Runtime:
                    def converse(self, **_):
                        raise error
                with self.assertRaises(ProviderNotReady):
                    converse("p", system="s", model_id="m", runtime=Runtime())
                out = verbs._summary_call_failure(ProviderNotReady(str(error)))
                self.assertFalse(out["document_summary_unavailable"]["retryable"])

    def test_a_timeout_is_a_retryable_failure(self):
        from checker.bedrock_model import BedrockUnavailable, converse

        class ReadTimeoutError(Exception):
            pass

        class Runtime:
            def converse(self, **_):
                raise ReadTimeoutError("Read timeout on endpoint URL")
        with self.assertRaises(BedrockUnavailable) as caught:
            converse("p", system="s", model_id="m", runtime=Runtime())
        out = verbs._summary_call_failure(caught.exception)
        self.assertEqual((out["status"], out["code"]), ("FAILED", "SUMMARY_PROVIDER_FAILED"))


if __name__ == "__main__":
    unittest.main()


class OnDeviceRoute(unittest.TestCase):
    """The on-device provider is only ever this machine, and only an operator's named model."""

    def _serve(self, env):
        from gateway import models
        with patch.dict("os.environ", env, clear=False):
            return models.serve((), name="ask", purpose=router.NARRATION, available=(OL,))

    def test_loopback_endpoint_is_served_on_device_at_zero_billed_cost(self):
        from gateway import models
        env = {"OLLAMA_MODEL": "llama3:latest", "OLLAMA_BASE_URL": "http://127.0.0.1:11434"}
        with patch("checker.ollama_runner.OllamaRunner.__call__", return_value="text"):
            served = self._serve(env)
            self.assertEqual((served.provider, served.region), (OL, models.ON_DEVICE))
            self.assertEqual(served.call("p"), "text")
        cost, note = served.cost()
        self.assertEqual(cost, 0.0)
        self.assertIn("on-device", note)
        self.assertTrue(served.degraded, "the on-device row is never the first choice")

    def test_remote_endpoint_is_refused_before_any_call(self):
        from gateway import models
        for url in ("http://10.0.0.5:11434", "https://ollama.example.com", "",
                    "http://evil.com?@127.0.0.1", "http://evil.com#@localhost:1",
                    "http://127.0.0.1@evil.com", "http://localhost.evil.com",
                    "https://127.0.0.1:11434"):
            with self.subTest(url=url), self.assertRaises(models.NotServed):
                self._serve({"OLLAMA_MODEL": "llama3:latest", "OLLAMA_BASE_URL": url})

    def test_cloud_model_is_refused_even_on_loopback(self):
        from gateway import models
        with self.assertRaises(models.NotServed):
            self._serve({"OLLAMA_MODEL": "kimi-k2.6:cloud",
                         "OLLAMA_BASE_URL": "http://127.0.0.1:11434"})

    def test_operator_can_narrow_providers_but_never_widen(self):
        from gateway import models
        with patch("checker.router.providers_available", return_value=(BR, OL)):
            with patch.dict("os.environ", {models.PROVIDERS_ENV: "ollama"}):
                self.assertEqual(models.available_providers(), (OL,))
            with patch.dict("os.environ", {models.PROVIDERS_ENV: "ollama,gemini"}):
                self.assertEqual(models.available_providers(), (OL,), "gemini is not added")
            with patch.dict("os.environ", {models.PROVIDERS_ENV: ""}):
                self.assertEqual(models.available_providers(), (BR, OL))


class ExclusionAppliesToResolvedModel(unittest.TestCase):
    def test_an_excluded_local_model_is_not_handed_back(self):
        with patch.dict("os.environ", {"OLLAMA_MODEL": "llama3:latest"}):
            task = router.Task("narrate", router.TEXT, router.LOW, purpose=router.NARRATION)
            with self.assertRaises(router.NoRoute):
                router.route(task, available=(OL,), exclude_models=frozenset({"llama3:latest"}))


class RecordedProviderIsTheOneThatServed(unittest.TestCase):
    def test_on_device_answer_is_not_recorded_as_bedrock(self):
        from agents import research_question as rq
        from gateway import models
        from gateway.store import MemoryBackend
        seen = {}
        real = rq.answer

        def spy(question, **kw):
            seen["available"] = kw.get("available")
            return real(question, **kw)
        served = models.Served(call=lambda p: "", provider=OL, model="llama3:latest",
                               region=models.ON_DEVICE, degraded=True, requires_review=False,
                               est_cost_inr=0.0)
        with patch.object(rq, "answer", side_effect=spy), \
             patch("gateway.verbs._typed_text_origin",
                   side_effect=lambda q, **_: (__import__("checker.public_only", fromlist=["x"])
                                               .clear_matter(q, name="q", provider="bedrock"),
                                               None)), \
             patch("gateway.verbs._served_or_refusal", return_value=(served, None)):
            verbs._ask({"question": "What notice is needed to call a board meeting under "
                                    "Section 173?"}, verbs.Context(store=MemoryBackend()))
        self.assertEqual(tuple(seen["available"]), (OL,))


class OnDeviceTimeout(unittest.TestCase):
    def test_timeout_comes_from_env_and_bad_values_fall_back(self):
        from gateway import models
        from checker import ollama_runner
        for raw, want in (("600", 600), ("", ollama_runner.DEFAULT_TIMEOUT_S),
                          ("abc", ollama_runner.DEFAULT_TIMEOUT_S), ("0", ollama_runner.DEFAULT_TIMEOUT_S)):
            with self.subTest(raw=raw), patch.dict("os.environ", {"OLLAMA_TIMEOUT_S": raw}):
                self.assertEqual(models._on_device_timeout(), want)
