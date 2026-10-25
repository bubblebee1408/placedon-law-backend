"""Deterministic routing for passage commands over selected documents."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from gateway import verbs
from gateway.filestore import LocalFileStore
from gateway.jobs import MemoryQueue
from gateway.store import MemoryBackend

from agents import intake


class DocumentSearchIntentTests(unittest.TestCase):
    def test_explicit_passage_commands_use_research_without_a_model(self):
        for message in (
            'Find the payment clause',
            'Show me the termination paragraph.',
            'Please locate the arbitration provision in this file.',
            'Find the related party clause in this agreement',
            'Show the section on borrowing',
            'Locate the payment terms in the attached document',
            'Find the payment clause and quote it',
        ):
            with self.subTest(message=message):
                result = intake.classify(
                    message, files=[{'name': 'agreement.pdf'}],
                    model_provider=lambda: self.fail('explicit retrieval must not call a model'),
                )
                self.assertEqual(result.task, intake.RESEARCH_QUESTION)
                self.assertEqual(result.rule, 'attachment+passage_command')

    def test_other_document_workflows_keep_their_routes(self):
        for message, files, expected in (
            ('Find the payment clause and review the agreement', ['agreement.pdf'], intake.REVIEW_CONTRACT),
            ('Locate the clause and draft a notice', ['agreement.pdf'], intake.DRAFT),
            ('Show the payment clauses side by side', ['a.pdf', 'b.pdf'], intake.REVIEW_TABLE),
            ('Summarize my document', ['scan.pdf'], intake.NEEDS_CLARIFICATION),
            ('', ['scan.pdf'], intake.NEEDS_CLARIFICATION),
            ('Find something', ['scan.pdf'], intake.NEEDS_CLARIFICATION),
        ):
            with self.subTest(message=message):
                self.assertEqual(intake.classify(message, files=files).task, expected)

    def test_external_search_and_non_commands_do_not_use_document_rule(self):
        for message in (
            'Find the current Tata case and its payment clause',
            'Find judgments about arbitration clauses',
            'Search the web for the payment clause',
            'Find the latest news about this section',
            'The lawyer will locate the payment clause tomorrow',
            'Do not find the payment clause',
            'Find the payment clause on Google',
        ):
            with self.subTest(message=message):
                self.assertNotEqual(
                    intake.classify(message, files=['agreement.pdf']).rule,
                    'attachment+passage_command',
                )

    def test_find_payment_clause_reaches_selected_document_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            files = LocalFileStore(Path(directory))
            store = MemoryBackend()
            content = b"Payment is due within thirty days of invoice receipt."
            store.write_vault_document({"uploaded_by": "unknown",
                'document_id': 'payment-contract', 'name': 'agreement.txt',
                'sha256': files.put(content), 'byte_count': len(content),
                'state': 'INGESTED',
            })
            model = Mock(side_effect=AssertionError('retrieval must not invoke a model'))
            queue = MemoryQueue()
            result = verbs._conversation_send({
                'text': 'Find the payment clause', 'request_id': 'find-payment-001',
                'file_ids': ['payment-contract'],
            }, verbs.Context(store=store, files=files, queue=queue, model_for=model))
            self.assertEqual(result['envelope']['status'], 'PARTIAL')
            evidence = result['metadata']['document_evidence']
            self.assertEqual(evidence['status'], 'EXCERPTS_FOUND')
            self.assertEqual(evidence['searched_document_ids'], ['payment-contract'])
            self.assertEqual(evidence['passages'][0]['text'], content.decode())
            model.assert_not_called()
            self.assertFalse(queue.jobs)

    def test_no_attachment_does_not_claim_document_scope(self):
        self.assertNotEqual(intake.classify('Find the payment clause').rule,
                            'attachment+passage_command')


if __name__ == '__main__':
    unittest.main()
