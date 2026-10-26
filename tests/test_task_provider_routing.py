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

AZ, BR = router.AZURE, router.BEDROCK


def serve_with(available, name, purpose, consequence=router.LOW):
    """Run the REAL router and serve() with stubbed adapters; return (provider|None, refusal)."""
    stub = lambda **_: (lambda prompt: "stub")                  # noqa: E731
    with patch("gateway.verbs._ledger", return_value=_Budget()), \
         patch("gateway.models.available_providers", return_value=available), \
         patch("checker.bedrock_model.as_text_model", side_effect=stub), \
         patch("checker.azure_model.as_text_model", side_effect=stub):
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

    def test_both_providers_configured_research_stays_on_azure_summary_on_bedrock(self):
        self.assertEqual(serve_with((AZ, BR), "ask", router.NARRATION), (AZ, None))
        self.assertEqual(serve_with((AZ, BR), "draft_prose", router.NARRATION), (AZ, None))
        self.assertEqual(serve_with((AZ, BR), "document_summary", router.EXTRACTION, router.HIGH), (BR, None))

    def test_missing_azure_credentials_refuse_research_rather_than_moving_it_to_bedrock(self):
        provider, refusal = serve_with((BR,), "ask", router.NARRATION)
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
            self.assertTrue(set(providers) <= MATTER_PROVIDERS, name)
        self.assertEqual(verbs.TASK_PROVIDERS["document_summary"], (BR,), "summaries: India region only")


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
