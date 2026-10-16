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
        self.assertNotIn("Invented court conclusion", result["answer"])
        self.assertIn("summary referenced a source", result["answer"])
        self.assertEqual(len(result["citations"]), 1)

    def test_out_of_range_or_truncated_source_reference_withholds_prose(self):
        for reference in (0, 9, 999):
            result = self.search({
                "answer": f"Invented court conclusion [{reference}].",
                "citations": [self.source(f"https://example.org/{n}") for n in range(9)],
            })
            self.assertNotIn("Invented court conclusion", result["answer"])
            self.assertEqual(len(result["citations"]), public_web.MAX_CITATIONS)

    def test_grouped_ranged_and_oversized_references_withhold_summary(self):
        for reference in ("1, 2", " 1, 2", "1-2", "1–2", "1; 2", "100000", "9" * 5000):
            with self.subTest(reference=reference[:20]):
                result = self.search({
                    "answer": f"Unsupported conclusion [{reference}].",
                    "citations": [self.source(), self.source("javascript:bad")],
                })
                self.assertNotIn("Unsupported conclusion", result["answer"])
                self.assertIn("summary referenced a source", result["answer"])
                self.assertEqual(len(result["citations"]), 1)


    def test_live_docket_question_never_appends_provider_status_narrative(self):
        result = self.search({
            "answer": "The court matter has been listed for next week [1]. The companies disagree over governance [2].",
            "citations": [self.source(), self.source("https://example.org/report-2", "Report 2")],
        }, query="What is the current status of the Tata court case?")
        self.assertEqual(result["status"], "ANSWERED")
        self.assertIn("cannot confirm a live court", result["answer"])
        self.assertNotIn("listed for next week", result["answer"])
        self.assertNotIn("disagree over governance", result["answer"])
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(len(result["portals"]), 2)

    def test_plain_provider_summary_remains_explicitly_unverified(self):
        # Citation presence is not semantic support or a correctness guarantee.
        result = self.search({"answer": "A provider summary.", "citations": [self.source()]})
        self.assertEqual(result["status"], "ANSWERED")
        self.assertIn("not verified law", result["note"])


if __name__ == "__main__":
    unittest.main()
