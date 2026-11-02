"""Per-firm daily cap, per-user default, env overrides, and the ledger the gateway picks.

Offline: the JSON ledger and the store selection. The Postgres ledger's atomicity is proved
live by scripts/spend_ledger_integration.py --run.
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend import budget
from backend.budget import BudgetTracker, FileStore


class CapNumbers(unittest.TestCase):
    def test_firm_daily_cap_is_a_quarter_of_the_global_daily_cap(self):
        self.assertEqual(budget.TENANT_DAILY_CAP_INR, round(budget.DAILY_CAP_INR * 0.25, 2))

    def test_user_daily_default_does_not_exceed_the_firm_cap(self):
        self.assertLessEqual(budget.USER_DAILY_CAP_INR, budget.TENANT_DAILY_CAP_INR)

    def test_env_override_is_read_and_validated(self):
        self.assertEqual(budget._cap_from_env("X_CAP", 5.0, env={}), 5.0)
        self.assertEqual(budget._cap_from_env("X_CAP", 5.0, env={"X_CAP": "40"}), 40.0)
        self.assertEqual(budget._cap_from_env("X_CAP", 5.0, env={"X_CAP": " "}), 5.0)
        for bad in ("abc", "-1", "nan", "inf"):
            with self.assertRaises(ValueError, msg=bad):
                budget._cap_from_env("X_CAP", 5.0, env={"X_CAP": bad})


class FirmAndUserCaps(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tracker = BudgetTracker(FileStore(Path(d.name) / "b.json"), today=date(2026, 11, 2))

    def hold(self, firm, user, amount):
        return self.tracker.attributed(firm, user).reserve(
            input_tokens=0, max_tokens=0, amount_inr=amount).id

    def test_firm_daily_cap_refuses_one_firm_and_not_another(self):
        cap = budget.TENANT_DAILY_CAP_INR
        admitted = sum(self.hold("firm-a", f"u{i}", 1.0) is not None for i in range(int(cap) + 5))
        self.assertEqual(admitted, int(cap))
        refused = self.tracker.attributed("firm-a", "u99").reserve(
            input_tokens=0, max_tokens=0, amount_inr=1.0)
        self.assertIsNone(refused.id)
        self.assertIn("daily", refused.verdict.reason)
        self.assertIsNotNone(self.hold("firm-b", "u1", 1.0))

    def test_user_daily_cap_binds_inside_the_firm(self):
        with patch.object(budget, "USER_DAILY_CAP_INR", 3.0):
            self.assertEqual([self.hold("firm-a", "u1", 1.0) is not None for _ in range(4)],
                             [True, True, True, False])
            self.assertIsNotNone(self.hold("firm-a", "u2", 1.0))

    def test_settle_refunds_the_firm_day(self):
        rid = self.hold("firm-a", "u1", 10.0)
        self.tracker.settle(rid, 2.0)
        self.assertEqual(self.tracker.usage(tenant_id="firm-a")["tenant"]["day_inr"], 2.0)

    def test_usage_reports_the_firm_daily_cap(self):
        u = self.tracker.usage(tenant_id="firm-a", user_id="u1")
        self.assertEqual(u["tenant"]["day_cap_inr"], budget.TENANT_DAILY_CAP_INR)
        self.assertTrue(u["user"]["cap_binds"])


class LedgerSelection(unittest.TestCase):
    def test_no_database_falls_back_to_the_json_ledger(self):
        with patch.dict("os.environ", {"PLACEDON_DATABASE_URL": ""}):
            t = budget.default_tracker()
        self.assertIsInstance(t.store, FileStore)

    def test_a_database_selects_the_postgres_ledger_without_connecting(self):
        from backend.budget_pg import PostgresBudget
        with patch.dict("os.environ", {"PLACEDON_DATABASE_URL": "postgresql:///nowhere"}):
            t = budget.default_tracker()
        self.assertIsInstance(t, PostgresBudget)
        self.assertIsInstance(t.attributed("firm-a", "u1"), PostgresBudget)

    def test_unreachable_database_refuses_rather_than_spends(self):
        from backend.budget_pg import PostgresBudget
        t = PostgresBudget("postgresql:///placedon_nonexistent_db?host=/nonexistent&connect_timeout=1")
        self.assertFalse(t.can_make_call(0.0).allowed)
        r = t.attributed("firm-a", "u1").reserve(input_tokens=0, max_tokens=0, amount_inr=1.0)
        self.assertIsNone(r.id)
        self.assertFalse(t.credit_exhausted())

    def test_gateway_ledger_uses_the_selected_store(self):
        from gateway import verbs
        with patch.dict("os.environ", {"PLACEDON_DATABASE_URL": "postgresql:///nowhere"}):
            self.assertEqual(type(verbs._ledger()).__name__, "PostgresBudget")


if __name__ == "__main__":
    unittest.main()
