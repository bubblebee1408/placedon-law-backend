"""Grid creation and completion refuse unconfirmed budget accounting."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gateway.verbs import Context, _review_grid_cell, _review_table_create


class ReviewGridBudgetBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.did = 'a' * 64
        self.store = Mock()
        self.queue = Mock()
        self.ctx = Context(store=self.store, queue=self.queue,
                           documents={self.did: {'text': 'Payment in thirty days.'}},
                           model_for=lambda _: lambda *_: ('thirty days', 'Payment in thirty days.'))
        self.create_args = {'name': 'Review', 'document_ids': [self.did],
                            'columns': [{'name': 'payment', 'kind': 'text', 'question': 'When?'}]}
        self.cell_args = {'grid_id': 'grid', 'document_id': self.did, 'column': 'payment',
                          'kind': 'text', 'question': 'When?', 'reservation_id': 'held'}

    def test_missing_ledger_prevents_create_and_enqueue(self):
        with patch('gateway.verbs._ledger', return_value=None):
            result = _review_table_create(self.create_args, self.ctx)
        self.assertEqual(result['code'], 'NO_BUDGET')
        self.store.write_grid.assert_not_called()
        self.queue.enqueue.assert_not_called()

    def test_available_ledger_reaches_scheduler(self):
        from agents.review_grid import Scheduled
        ledger = Mock()
        ledger.can_make_call.return_value = SimpleNamespace(allowed=True)
        with patch('gateway.verbs._ledger', return_value=ledger), patch(
                'agents.review_grid.schedule', return_value=Scheduled('grid')) as schedule:
            result = _review_table_create(self.create_args, self.ctx)
        self.assertIn('grid_id', result)
        self.store.write_grid.assert_called_once()
        self.assertIs(schedule.call_args.kwargs['budget'], ledger)

    def test_missing_settlement_ledger_withholds_cell(self):
        with patch('gateway.verbs._ledger', return_value=None):
            result = _review_grid_cell(self.cell_args, self.ctx)
        self.assertEqual(result['code'], 'BUDGET_RECONCILIATION_REQUIRED')
        self.assertFalse(result['reservation_settled'])
        self.store.write_grid_cell.assert_not_called()
        self.assertEqual(self.ctx.last_steps, [])

    def test_refused_settlement_is_not_retried_at_zero(self):
        ledger = Mock()
        ledger.settle.return_value = SimpleNamespace(allowed=False)
        with patch('gateway.verbs._ledger', return_value=ledger):
            result = _review_grid_cell(self.cell_args, self.ctx)
        self.assertEqual(result['code'], 'BUDGET_RECONCILIATION_REQUIRED')
        ledger.settle.assert_called_once()
        self.store.write_grid_cell.assert_not_called()

    def test_settlement_exception_withholds_cell(self):
        ledger = Mock()
        ledger.settle.side_effect = OSError('ledger unavailable')
        with patch('gateway.verbs._ledger', return_value=ledger):
            result = _review_grid_cell(self.cell_args, self.ctx)
        self.assertEqual(result['code'], 'BUDGET_RECONCILIATION_REQUIRED')
        ledger.settle.assert_called_once()
        self.store.write_grid_cell.assert_not_called()

    def test_successful_settlement_allows_publish(self):
        ledger = Mock()
        ledger.settle.return_value = SimpleNamespace(allowed=True)
        with patch('gateway.verbs._ledger', return_value=ledger):
            result = _review_grid_cell(self.cell_args, self.ctx)
        self.assertEqual(result['status'], 'ANSWERED')
        self.assertTrue(result['reservation_settled'])
        ledger.settle.assert_called_once_with('held', 0.0)
        self.store.write_grid_cell.assert_called_once()

    def test_unknown_provider_usage_settles_full_hold(self):
        ledger = Mock()
        ledger.settle.return_value = SimpleNamespace(allowed=True)
        self.ctx.model_for = None
        def answerer(_ctx, debits):
            debits.append({'provider': 'azure', 'cost_inr': None, 'cost_note': 'UNPRICED'})
            return lambda *_: ('thirty days', 'Payment in thirty days.')
        with patch('gateway.verbs._ledger', return_value=ledger), patch(
                'gateway.verbs._cell_answerer', side_effect=answerer):
            result = _review_grid_cell(self.cell_args, self.ctx)
        self.assertTrue(result['reservation_settled'])
        ledger.settle.assert_called_once_with('held', None)

    def test_malformed_job_reports_actual_settlement_failure(self):
        args = {**self.cell_args, 'question': ''}
        with patch('gateway.verbs._ledger', return_value=None):
            result = _review_grid_cell(args, self.ctx)
        self.assertEqual(result['code'], 'BUDGET_RECONCILIATION_REQUIRED')
        self.assertFalse(result['reservation_settled'])
        self.store.write_grid_cell.assert_not_called()


if __name__ == '__main__':
    unittest.main()
