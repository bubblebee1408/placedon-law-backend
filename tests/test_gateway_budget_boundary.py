"""No real provider routing when the gateway cannot establish its budget guard."""
import unittest
from unittest.mock import patch, Mock
from gateway.verbs import Context, _served_or_refusal


class GatewayBudgetBoundaryTests(unittest.TestCase):
    def test_missing_ledger_refuses_before_provider_selection(self):
        with patch('gateway.verbs._ledger', return_value=None), patch('gateway.models.serve') as serve:
            served, refusal = _served_or_refusal((), name='ask', purpose='NARRATION', ctx=Context())
        self.assertIsNone(served)
        self.assertEqual(refusal['code'], 'NO_BUDGET')
        serve.assert_not_called()

    def test_available_guard_is_passed_to_model_router(self):
        guard, model = object(), object()
        with patch('gateway.verbs._ledger', return_value=guard), patch('gateway.models.serve', return_value=model) as serve:
            served, refusal = _served_or_refusal((), name='ask', purpose='NARRATION', ctx=Context())
        self.assertIs(served, model)
        self.assertIsNone(refusal)
        self.assertIs(serve.call_args.kwargs['budget'], guard)

    def test_injected_offline_model_does_not_open_real_budget_or_provider(self):
        model = Mock(return_value='test')
        with patch('gateway.verbs._ledger') as ledger, patch('gateway.models.serve') as serve:
            served, refusal = _served_or_refusal((), name='ask', purpose='NARRATION', ctx=Context(model_for=lambda _: model))
        self.assertIsNone(refusal)
        self.assertEqual(served.call('prompt'), 'test')
        ledger.assert_not_called()
        serve.assert_not_called()
