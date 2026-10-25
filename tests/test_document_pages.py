"""Page references for uploaded PDFs: pages travel as form feeds (\\f) in the stored text.

The frontend reads a PDF page by page and joins the pages with \\f, the same convention
pdftotext uses. Everything downstream counts pages from the offsets it already keeps, so
a passage or a summary quote names the page it came from -- and text with no page breaks
(a .docx, a .txt) says that it has none rather than calling everything page 1.
"""
import json
import unittest
import uuid

from gateway import document_evidence as de
from gateway import document_summary as ds

PAGED = ("SERVICES AGREEMENT\n\n1. Term. Twenty-four months from 1 April 2026.\n\n"
         "2. Fees. INR 3,50,000 per month."
         "\f"
         "Schedule 1. Monthly demand-forecasting reports.\n\n"
         "Termination on ninety days' written notice.")


class PageOf(unittest.TestCase):
    def test_offsets_map_to_one_indexed_pages(self):
        second = PAGED.index("Schedule 1")
        self.assertEqual(de.page_of(PAGED, 0), 1)
        self.assertEqual(de.page_of(PAGED, PAGED.index("2. Fees")), 1)
        self.assertEqual(de.page_of(PAGED, second), 2)

    def test_text_without_page_breaks_has_no_pages(self):
        self.assertIsNone(de.page_of("A .docx has no pages.", 3))


class EvidencePages(unittest.TestCase):
    def test_passages_name_their_page_and_never_span_a_page_break(self):
        ev = de.collect("termination notice", {"d1": {"name": "sa.pdf", "text": PAGED}})
        self.assertEqual(ev["status"], "EXCERPTS_FOUND")
        hit = ev["passages"][0]
        self.assertIn("Termination", hit["text"])
        self.assertEqual(hit["page"], 2)
        for start, end in de._spans(PAGED):
            self.assertNotIn("\f", PAGED[start:end], "a passage never crosses a page break")

    def test_unpaginated_text_says_pages_are_unknown(self):
        ev = de.collect("fees", {"d1": {"name": "sa.docx", "text": PAGED.replace("\f", "\n\n")}})
        self.assertIsNone(ev["passages"][0]["page"])
        self.assertTrue(any("not original PDF pages" in x for x in ev["limitations"]))

    def test_paginated_text_states_where_page_numbers_come_from(self):
        ev = de.collect("fees", {"d1": {"name": "sa.pdf", "text": PAGED}})
        self.assertTrue(any("page breaks" in x for x in ev["limitations"]))


class SummaryPages(unittest.TestCase):
    def test_summary_quotes_carry_the_page_they_were_found_on(self):
        ev = ds.prepare({"d1": {"name": "sa.pdf", "text": PAGED}})
        late = next(p for p in ev["passages"] if "Termination" in p["text"])
        self.assertEqual(late["page"], 2)
        raw = json.dumps({"sections": [{"kind": "obligations", "items": [{
            "text": "Either party may end the agreement on notice.",
            "citations": [{"passage_id": late["id"],
                           "quote": "Termination on ninety days' written notice."}]}]}]})
        summary = ds.parse(raw, ev)
        self.assertEqual(summary["sections"][0]["items"][0]["quotes"][0]["page"], 2)
        self.assertFalse(any("Page numbers are not available" in x for x in summary["limitations"]))


class IngestPages(unittest.TestCase):
    def _ingest(self, text):
        import tempfile
        from gateway import verbs
        from gateway.filestore import LocalFileStore
        from gateway.store import MemoryBackend
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store, files = MemoryBackend(), LocalFileStore(tmp.name)
        sha = files.put(text.encode("utf-8"))
        did = str(uuid.uuid4())
        store.write_vault_document({"document_id": did, "sha256": sha, "name": "x.pdf",
                                    "byte_count": 1, "state": "PENDING", "uploaded_by": "a"})
        ctx = verbs.Context(store=store, files=files, actor="a")
        return verbs._vault_ingest_job({"document_id": did, "sha256": sha, "name": "x.pdf"}, ctx)

    def test_a_page_with_no_text_layer_makes_the_document_partial_and_is_named(self):
        out = self._ingest("Page one has words about indemnity.\f   \fPage three has words too.")
        self.assertEqual(out["state"], "PARTIAL")
        self.assertEqual(out["failed_pages"], [2])

    def test_every_page_without_text_is_a_scan_not_an_empty_document(self):
        out = self._ingest("\f \f\n")
        self.assertEqual((out["state"], out["ocr_state"]), ("CANNOT_READ", "BLOCKED"))

    def test_unpaginated_text_is_ingested_as_before(self):
        self.assertEqual(self._ingest("A plain text agreement.")["state"], "INGESTED")


if __name__ == "__main__":
    unittest.main()


class QuoteLocation(unittest.TestCase):
    def test_a_summary_quote_locates_itself_not_its_whole_passage(self):
        ev = ds.prepare({"d1": {"name": "sa.pdf", "text": PAGED}})
        passage = next(p for p in ev["passages"] if "Termination" in p["text"])
        quote = "ninety days' written notice"
        raw = json.dumps({"sections": [{"kind": "obligations", "items": [{
            "text": "Notice is required to terminate.",
            "citations": [{"passage_id": passage["id"], "quote": quote}]}]}]})
        q = ds.parse(raw, ev)["sections"][0]["items"][0]["quotes"][0]
        self.assertEqual(PAGED[q["start"]:q["end"]], quote)
        self.assertEqual((q["passage_start"], q["passage_end"]), (passage["start"], passage["end"]))
        self.assertEqual(q["page"], 2)
