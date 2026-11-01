"""No real provider routing when the gateway cannot establish its budget guard."""
import unittest
from unittest.mock import patch, Mock
import tempfile
from datetime import date, timedelta
from pathlib import Path

from backend.budget import DAILY_CAP_INR, TENANT_MONTHLY_CAP_INR, BudgetTracker, FileStore
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


class TenantSpendCapTests(unittest.TestCase):
    """Audit backend/budget.py:scoped-caps-never-attributed: every gateway model call is
    charged to the caller's firm, so one firm cannot drain the shared month."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.store = FileStore(Path(self._dir.name) / "budget.json")
        # Fill firm-a to its monthly cap day by day: the global daily cap is below it.
        day, spent = date(2026, 11, 1), 0.0
        while spent < TENANT_MONTHLY_CAP_INR - 0.5:
            chunk = min(DAILY_CAP_INR - 0.5, TENANT_MONTHLY_CAP_INR - 0.5 - spent)
            BudgetTracker(self.store, today=day).record_call(chunk, tenant_id="firm-a")
            spent, day = spent + chunk, day + timedelta(days=1)
        self.today = day

    def _serve(self, ctx):
        """The ledger `serve()` would gate and reserve on, for this request context."""
        with patch("gateway.verbs._ledger",
                   return_value=BudgetTracker(self.store, today=self.today)), \
                patch("gateway.models.serve", return_value=object()) as serve:
            _served_or_refusal((), name="ask", purpose="NARRATION", ctx=ctx)
        return serve.call_args.kwargs["budget"]

    def test_tenant_at_cap_refused_while_other_tenant_proceeds(self):
        a = self._serve(Context(tenant="firm-a", actor="u1"))
        b = self._serve(Context(tenant="firm-b", actor="u2"))
        self.assertFalse(a.can_make_call(1.0).allowed)
        self.assertIsNone(a.reserve(input_tokens=0, max_tokens=0, amount_inr=1.0).id)
        self.assertTrue(b.can_make_call(1.0).allowed)
        self.assertIsNotNone(b.reserve(input_tokens=0, max_tokens=0, amount_inr=1.0).id)

    def test_unattributed_gateway_call_refused(self):
        for tenant in ("", "unknown"):
            ledger = self._serve(Context(tenant=tenant))
            self.assertFalse(ledger.can_make_call(0.0).allowed)
            self.assertIsNone(ledger.reserve(input_tokens=0, max_tokens=0, amount_inr=0.1).id)
