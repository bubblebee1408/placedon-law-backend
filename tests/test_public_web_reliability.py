"""Provider-boundary regressions, with synthetic responses and no network calls."""
import unittest
from unittest.mock import patch

from checker import public_web


class PublicWebReliability(unittest.TestCase):
    def search(self, response, query="Tata governance dispute"):
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            return public_web.search(
                query, mode="GENERAL_WEB", consent=True,
                transport=lambda body, key: response,
            )

    def source(self, url="https://example.org/report", title="Report"):
        return {"url": url, "title": title, "text": "Source excerpt"}

    def test_malformed_transport_response_does_not_crash(self):
        for response in (None, [], "not an object", 42):
            with self.subTest(response=response):
                self.assertEqual(self.search(response)["status"], "UNAVAILABLE")

    def test_malformed_urls_are_rejected_without_crashing(self):
        for url in ("https://[invalid", "https://example.org:bad/path",
                    "https://exa mple.org/path", "https://example.org/\npath",
                    "https://user:password@example.org", "javascript:alert(1)"):
            with self.subTest(url=url):
                result = self.search({"answer": "A claim [1].", "citations": [self.source(url)]})
                self.assertEqual(result["status"], "NO_RESULTS")
                self.assertIsNone(result["answer"])

    def test_sourceless_prose_is_never_returned_as_answered(self):
        for citations in ([], None, {}, [{"title": "Missing URL"}]):
            result = self.search({"answer": "Unsupported prose.", "citations": citations})
            self.assertEqual(result["status"], "NO_RESULTS")
            self.assertIsNone(result["answer"])

    def test_deduplication_preserves_reference_identity(self):
        result = self.search({
            "answer": "First report [2]. Another report [3].",
            "citations": [self.source(), self.source(), self.source("https://example.org/other")],
        })
        self.assertEqual(result["answer"], "First report [1]. Another report [2].")
        self.assertEqual(len(result["citations"]), 2)

    def test_removed_unused_source_does_not_renumber_a_claim_incorrectly(self):
        result = self.search({
            "answer": "Public reporting [2].",
            "citations": [self.source("javascript:bad"), self.source()],
        })
        self.assertEqual(result["answer"], "Public reporting [1].")
        self.assertEqual(result["citations"][0]["url"], "https://example.org/report")

    def test_removed_cited_source_withholds_prose_but_retains_leads(self):
        result = self.search({
            "answer": "Invented court conclusion [1].",
            "citations": [self.source("javascript:bad"), self.source()],
        })
        self.assertEqual(result["status"], "SUMMARY_UNAVAILABLE")
        self.assertIsNone(result["answer"])
        self.assertIn("summary referenced a source", result["message"])
        self.assertEqual(len(result["citations"]), 1)

    def test_out_of_range_or_truncated_source_reference_withholds_prose(self):
        for reference in (0, 9, 999):
            result = self.search({
                "answer": f"Invented court conclusion [{reference}].",
                "citations": [self.source(f"https://example.org/{n}") for n in range(9)],
            })
            self.assertEqual(result["status"], "SUMMARY_UNAVAILABLE")
            self.assertIsNone(result["answer"])
            self.assertEqual(len(result["citations"]), public_web.MAX_CITATIONS)

    def test_grouped_ranged_and_oversized_references_withhold_summary(self):
        for reference in ("1, 2", " 1, 2", "1-2", "1–2", "1; 2", "100000", "9" * 5000):
            with self.subTest(reference=reference[:20]):
                result = self.search({
                    "answer": f"Unsupported conclusion [{reference}].",
                    "citations": [self.source(), self.source("javascript:bad")],
                })
                self.assertEqual(result["status"], "SUMMARY_UNAVAILABLE")
                self.assertIsNone(result["answer"])
                self.assertIn("summary referenced a source", result["message"])
                self.assertEqual(len(result["citations"]), 1)


    def test_provider_docket_claim_is_withheld_as_official_status_lead(self):
        result = self.search({
            "answer": "A court case is pending [1]. The companies disagree over governance [2].",
            "citations": [self.source(), self.source("https://example.org/report-2", "Report 2")],
        }, query="Tata governance dispute")
        self.assertEqual(result["status"], "OFFICIAL_STATUS_REQUIRED")
        self.assertIsNone(result["answer"])
        self.assertIn("not a live court record", result["message"])
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(len(result["portals"]), 2)

    def test_natural_current_situation_of_case_asks_for_details_without_search(self):
        query = "What is the current situation of the Tata court case?"
        calls = []
        with patch.dict(public_web.os.environ, {"PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key"}):
            result = public_web.search(query, mode="GENERAL_WEB", consent=True,
                                       transport=lambda body, key: calls.append((body, key)))
        self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
        self.assertIsNone(result["answer"])
        self.assertEqual(calls, [])

    def test_current_case_wording_asks_for_details_before_external_search(self):
        calls = []
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            result = public_web.search(
                "Tata case study on current case between Tata Sons and Tata Trusts",
                mode="GENERAL_WEB", consent=True,
                transport=lambda body, key: calls.append((body, key)),
            )
        self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
        self.assertIsNone(result["answer"])
        self.assertEqual(calls, [])

    def test_case_discovery_mode_can_search_for_reporting_leads(self):
        calls = []
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            result = public_web.search(
                "Tata case between Tata Sons and Tata Trusts",
                mode="CASE_DISCOVERY", consent=True,
                transport=lambda body, key: calls.append((body, key)) or {
                    "answer": "Public reports discuss a corporate dispute [1].",
                    "citations": [self.source()],
                },
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "ANSWERED")
        self.assertEqual(len(result["citations"]), 1)

    def test_case_study_words_are_not_mistaken_for_a_case_number(self):
        query = "What is the current status of the Supreme Court case study?"
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            result = public_web.search(query, mode="GENERAL_WEB", consent=True,
                                       transport=lambda *_: self.fail("provider must not be called"))
        self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
        self.assertNotIn("provider", result)

    def test_ambiguous_live_case_status_is_clarified_before_provider_call(self):
        calls = []
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            result = public_web.search(
                "crime case status", mode="GENERAL_WEB", consent=True,
                transport=lambda body, key: calls.append((body, key)),
            )
        self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
        self.assertIsNone(result["answer"])
        self.assertNotIn("provider", result)
        self.assertEqual(calls, [])
        self.assertIn("court", result["message"])

    def test_live_case_paraphrases_are_clarified_before_provider_call(self):
        for query in (
            "latest update on Tata Trusts lawsuit",
            "Is the Tata dispute before the Supreme Court?",
            "Has Tata moved court?",
        ):
            with self.subTest(query=query), patch.dict(public_web.os.environ, {
                "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
            }):
                calls = []
                result = public_web.search(
                    query, mode="GENERAL_WEB", consent=True,
                    transport=lambda body, key: calls.append((body, key)),
                )
            self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
            self.assertEqual(calls, [])

    def test_identified_live_case_status_routes_to_official_portal_without_provider_call(self):
        calls = []
        with patch.dict(public_web.os.environ, {
            "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
        }):
            result = public_web.search(
                "Current status CNR ABC1234567890123 Supreme Court",
                mode="GENERAL_WEB", consent=True,
                transport=lambda body, key: calls.append((body, key)),
            )
        self.assertEqual(result["status"], "OFFICIAL_STATUS_REQUIRED")
        self.assertIsNone(result["answer"])
        self.assertNotIn("provider", result)
        self.assertEqual(len(result["portals"]), 2)
        self.assertEqual(calls, [])

    def test_case_number_placeholder_words_are_not_treated_as_identifiers(self):
        for query in (
            "What is current status of the case number please check at Supreme Court?",
            "What is current status of the case number pending at Supreme Court?",
        ):
            with self.subTest(query=query), patch.dict(public_web.os.environ, {
                "PLACEDON_EXA_WEB_ENABLED": "1", "EXA_API_KEY": "synthetic-test-key",
            }):
                calls = []
                result = public_web.search(
                    query, mode="GENERAL_WEB", consent=True,
                    transport=lambda body, key: calls.append((body, key)),
                )
            self.assertEqual(result["status"], "NEEDS_CASE_DETAILS")
            self.assertEqual(calls, [])

    def test_unmatched_citation_returns_leads_without_answered_summary(self):
        result = self.search({
            "answer": "Unsupported conclusion [2].",
            "citations": [self.source()],
        })
        self.assertEqual(result["status"], "SUMMARY_UNAVAILABLE")
        self.assertIsNone(result["answer"])
        self.assertEqual(len(result["citations"]), 1)
        self.assertIn("research leads", result["message"])

    def test_preflight_outcomes_do_not_claim_exa_was_used(self):
        with patch.dict(public_web.os.environ, {}, clear=True):
            consent = public_web.search("Tata governance update", mode="GENERAL_WEB", consent=False)
            disabled = public_web.search("Tata governance update", mode="GENERAL_WEB", consent=True)
        self.assertEqual(consent["status"], "CONSENT_REQUIRED")
        self.assertEqual(disabled["status"], "NOT_CONFIGURED")
        self.assertNotIn("provider", consent)
        self.assertNotIn("provider", disabled)

    def test_plain_provider_summary_remains_explicitly_unverified(self):
        # Citation presence is not semantic support or a correctness guarantee.
        result = self.search({"answer": "A provider summary.", "citations": [self.source()]})
        self.assertEqual(result["status"], "ANSWERED")
        self.assertIn("not verified law", result["note"])


if __name__ == "__main__":
    unittest.main()
