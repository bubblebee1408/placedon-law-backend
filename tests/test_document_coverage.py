"""Position coverage and source fidelity for bounded extractive overviews."""
import unittest
from gateway.document_evidence import collect, MAX_PASSAGES


class DocumentCoverageTests(unittest.TestCase):
    def test_overview_includes_beginning_middle_and_end(self):
        text = '\n\n'.join(f'Clause {i}: supplied terms.' for i in range(40))
        got = collect('Summarize this document', {'a': {'text': text}})
        shown = got['passages']
        self.assertEqual(shown[0]['start'], 0)
        self.assertEqual(shown[-1]['end'], len(text))
        self.assertTrue(any(len(text)*.35 < p['start'] < len(text)*.65 for p in shown))
        self.assertEqual(len(shown), MAX_PASSAGES)
        for p in shown:
            self.assertEqual(p['text'], text[p['start']:p['end']])
        doc = got['documents'][0]
        self.assertEqual(doc['total_passages'], 40)
        self.assertEqual(doc['shown_passages'], 8)
        self.assertEqual(doc['excerpt_chars'], sum(len(p['text']) for p in shown))
        self.assertAlmostEqual(doc['excerpt_coverage_ratio'], doc['excerpt_chars']/len(text))

    def test_short_document_spare_budget_is_used_by_long_document(self):
        got = collect('Summarize these files', {'short': {'text': 'Short text.'},
            'long': {'text': '\n\n'.join(f'Clause {i}.' for i in range(20))}})
        self.assertEqual([d['shown_passages'] for d in got['documents']], [1, 7])
        self.assertEqual(len(got['passages']), 8)

    def test_documents_omitted_by_output_budget_have_zero_coverage(self):
        got = collect('Summarize these files', {str(i): {'text': f'Text {i}.'} for i in range(10)})
        self.assertEqual([d['shown_passages'] for d in got['documents']], [1]*8+[0]*2)
        self.assertEqual(got['documents'][-1]['excerpt_coverage_ratio'], 0)

    def test_disabled_or_unreadable_has_no_claimed_coverage(self):
        for enabled in (True, False):
            got = collect('Summarize this file', {'a': {'cannot_read': 'missing'}}, enabled=enabled)
            row = got['documents'][0]
            self.assertIsNone(row['excerpt_coverage_ratio'])
            self.assertEqual(row['shown_passages'], 0)

    def test_question_keeps_match_ranking_and_reports_excerpt_size(self):
        text = 'Opening.\n\nPayment is due tomorrow.\n\nEnd.'
        got = collect('What is the payment?', {'a': {'text': text}})
        self.assertEqual(got['passages'][0]['text'], 'Payment is due tomorrow.')
        self.assertEqual(got['documents'][0]['total_passages'], 3)
        self.assertEqual(got['documents'][0]['shown_passages'], 1)
