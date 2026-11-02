"""The spend ledger on Postgres (migration 035), for any deployment with a database.

`BudgetTracker` keeps its whole state in one JSON row, which is right for one process on one
disk and wrong on App Service: a restart loses it and each instance has its own, so each
enforces the full caps. This subclass keeps the same caps, messages and public methods and
moves the state into `model_spend` (counters) and `model_spend_holds` (reservations).

Admission is one conditional upsert per scope, in a fixed order, inside one transaction:

    INSERT ... ON CONFLICT (scope, period, day) DO UPDATE
       SET spent_inr = spent_inr + x WHERE spent_inr + x <= cap RETURNING ...

A scope that returns no row is over its cap; the transaction rolls back and nothing is held.
Postgres row locks make each upsert atomic; there is no application lock. The fixed order
(global first) means two reservations can never wait on each other in opposite orders.

Reads (`can_make_call`, `usage`, `credit_exhausted`) go through the inherited code on a
snapshot built in the same shape as the JSON ledger's state, so the cap arithmetic and the
refusal messages still have one implementation. A database that cannot be read is treated
like a corrupt ledger: every call is refused.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend import budget as B
from backend.budget import BudgetTracker, Reservation, Verdict, _reserved_total, _who

GLOBAL = "global"
SPEND_CAP_FLAG = "flag:provider_spend_cap"      # month-scoped, like the JSON flag
CREDIT_FLAG = "flag:credit_exhausted"           # day-scoped, like the JSON flag

_TAKE = """
INSERT INTO model_spend (scope, period, day, spent_inr, requests)
VALUES (%(scope)s, %(period)s, %(day)s, %(x)s, %(n)s)
ON CONFLICT (scope, period, day) DO UPDATE
   SET spent_inr = model_spend.spent_inr + EXCLUDED.spent_inr,
       requests  = model_spend.requests + EXCLUDED.requests
 WHERE (%(cap)s::numeric IS NULL OR model_spend.spent_inr + EXCLUDED.spent_inr <= %(cap)s::numeric)
   AND (%(rcap)s::integer IS NULL OR model_spend.requests + EXCLUDED.requests <= %(rcap)s::integer)
RETURNING spent_inr
"""

_ADJUST = """
UPDATE model_spend
   SET spent_inr = GREATEST(spent_inr + %(dx)s, 0),
       requests  = GREATEST(requests + %(dn)s, 0),
       held_inr  = held_inr + %(held)s
 WHERE scope = %(scope)s AND period = %(period)s AND day = %(day)s
"""


def _d(x: float | None) -> Decimal | None:
    return None if x is None else Decimal(str(round(float(x), 4)))


class _NoFile:
    """In place of the JSON store, so nothing here can quietly fall back to a local file."""

    def read(self) -> dict:
        raise RuntimeError("PostgresBudget has no file store")

    def write(self, data: dict) -> None:
        raise RuntimeError("PostgresBudget has no file store")


class _Over(Exception):
    def __init__(self, scope: str, period: str) -> None:
        super().__init__(scope)
        self.scope, self.period = scope, period


class _Duplicate(Exception):
    pass


def scopes(day: date, tenant: str | None, user: str | None, model: str | None,
           per_model_cap: int | None = None) -> list[tuple]:
    """(scope, period, day, rupee cap, request cap) for one call, in the one lock order."""
    month = day.replace(day=1)
    rows = [(GLOBAL, "month", month, B.MONTHLY_CAP_INR, None),
            (GLOBAL, "day", day, B.DAILY_CAP_INR, B.DAILY_REQUEST_CAP)]
    if tenant:
        rows += [(f"tenant:{tenant}", "month", month, B.TENANT_MONTHLY_CAP_INR, None),
                 (f"tenant:{tenant}", "day", day, B.TENANT_DAILY_CAP_INR, None)]
    if user:
        rows.append((f"user:{user}", "day", day, B.USER_DAILY_CAP_INR, None))
    if model:
        rows.append((f"model:{model}", "day", day, None, per_model_cap))
    return sorted(rows, key=lambda r: r[:3])


def _take(c, scope: str, period: str, day: date, x: float, n: int,
          cap: float | None, rcap: int | None) -> bool:
    """Add x rupees and n requests to one counter if both stay within their caps."""
    # The first row of a period is a plain INSERT, which the WHERE does not guard.
    if (cap is not None and x > cap + 1e-9) or (rcap is not None and n > rcap):
        return False
    return c.execute(_TAKE, {"scope": scope, "period": period, "day": day, "x": _d(x),
                             "n": n, "cap": _d(cap), "rcap": rcap}).fetchone() is not None


class PostgresBudget(BudgetTracker):
    def __init__(self, url: str, *, today: date | None = None, tenant_id: str | None = None,
                 user_id: str | None = None, require_tenant: bool = False) -> None:
        super().__init__(_NoFile(), today=today, tenant_id=tenant_id, user_id=user_id,
                         require_tenant=require_tenant)
        self._url = url

    def attributed(self, tenant_id: str | None, user_id: str | None = None) -> "PostgresBudget":
        return PostgresBudget(self._url, today=self._today, tenant_id=tenant_id,
                              user_id=user_id, require_tenant=True)

    def _connect(self):
        import psycopg
        return psycopg.connect(self._url, autocommit=True, connect_timeout=5)

    # ── state: the JSON ledger's shape, read from the two tables ─────────────
    def _state(self) -> dict:
        try:
            with self._connect() as c:
                return self._snapshot(c)
        except Exception:  # noqa: BLE001 - an unreadable ledger refuses, never admits
            return self._normalise({"corrupt": True})

    def _snapshot(self, c) -> dict:
        day, month = self._today, self._today.replace(day=1)
        counters = {(s, p): (float(x), int(n), float(h)) for s, p, x, n, h in c.execute(
            "SELECT scope, period, spent_inr, requests, held_inr FROM model_spend "
            "WHERE (period = 'day' AND day = %s) OR (period = 'month' AND day = %s)",
            (day, month)).fetchall()}
        holds = c.execute(
            "SELECT reservation_id, amount_inr, requests, model, tenant, actor, claim_id "
            "FROM model_spend_holds WHERE day = %s AND settled_at IS NULL", (day,)).fetchall()
        reservations, calls, claims = {}, {}, {}
        for rid, amount, n, model, tenant, actor, claim in holds:
            reservations[rid] = float(amount)
            calls[rid] = {"count": int(n), "model": model,
                          **({"tenant": tenant} if tenant else {}),
                          **({"user": actor} if actor else {})}
            if claim:
                claims[rid] = claim

        def held(**match) -> tuple[float, int]:
            hit = [rid for rid, info in calls.items()
                   if all(info.get(k) == v for k, v in match.items())]
            return sum(reservations[r] for r in hit), sum(calls[r]["count"] for r in hit)

        def net(scope: str, period: str, **match) -> tuple[float, int]:
            spent, n, _ = counters.get((scope, period), (0.0, 0, 0.0))
            h_inr, h_n = held(**match)
            return max(0.0, round(spent - h_inr, 4)), max(0, n - h_n)

        def per(prefix: str, period: str, key: str) -> dict:
            return {s[len(prefix):]: net(s, period, **{key: s[len(prefix):]})[0]
                    for (s, p) in counters if p == period and s.startswith(prefix)}

        day_inr, calls_today = net(GLOBAL, "day")
        return {
            "corrupt": False, "day": day.isoformat(), "month": day.strftime("%Y-%m"),
            "day_inr": day_inr, "month_inr": net(GLOBAL, "month")[0],
            "month_held_inr": counters.get((GLOBAL, "month"), (0, 0, 0.0))[2],
            "month_unresolved_inr": 0.0,
            "calls_today": calls_today,
            "calls_by_model": {s[6:]: net(s, "day", model=s[6:])[1]
                               for (s, p) in counters if p == "day" and s.startswith("model:")},
            "tenant_month_inr": per("tenant:", "month", "tenant"),
            "tenant_day_inr": per("tenant:", "day", "tenant"),
            "user_day_inr": per("user:", "day", "user"),
            "spend_cap": (SPEND_CAP_FLAG, "month") in counters,
            "credit_exhausted": (CREDIT_FLAG, "day") in counters,
            "reservations": reservations, "reservation_claims": claims,
            "reservation_calls": calls, "settled_reservations": {},
        }

    # ── reserve ──────────────────────────────────────────────────────────────
    def _hold(self, *, worst: float, rid: str, model: str, tenant_id: str | None,
              user_id: str | None, call_info: dict, request_count: int,
              per_model_cap: int | None) -> Reservation:
        def gate() -> Verdict:
            return self.can_make_call(worst, model=model, per_model_cap=per_model_cap,
                                      tenant_id=tenant_id, user_id=user_id,
                                      _snapshot=self._state(),
                                      _additional_requests=request_count)

        # A cheap read first, for the refusals that are not a race (no firm, provider cap,
        # unreadable ledger, an obviously spent cap) and for their exact messages.
        pre = gate()
        if not pre.allowed:
            return Reservation(None, worst, pre)
        try:
            with self._connect() as c, c.transaction():
                if c.execute(
                        "INSERT INTO model_spend_holds (reservation_id, day, amount_inr, "
                        "requests, model, tenant, actor) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (reservation_id) DO NOTHING RETURNING 1",
                        (rid, self._today, _d(worst), request_count, model, tenant_id,
                         user_id)).fetchone() is None:
                    raise _Duplicate(rid)
                for scope, period, day, cap, rcap in scopes(self._today, tenant_id, user_id,
                                                            model, per_model_cap):
                    if not _take(c, scope, period, day, worst, request_count, cap, rcap):
                        raise _Over(scope, period)
        except _Duplicate:
            raise ValueError(f"reservation id {rid!r} was already used; choose a fresh id") from None
        except _Over as over:
            verdict = gate()
            if verdict.allowed:   # a concurrent call took the room between read and write
                kind = over.scope.split(":", 1)[0]
                verdict = Verdict(False, "budget",
                                  f"the {kind} {over.period} cap was reached by a call made "
                                  f"at the same moment", verdict.spent_today,
                                  verdict.spent_month, verdict.reserved)
            return Reservation(None, worst, verdict)
        except Exception:  # noqa: BLE001 - a failed transaction cannot admit provider work
            return Reservation(None, worst, Verdict(
                False, "offline", "atomic budget reservation failed; no call was admitted",
                pre.spent_today, pre.spent_month, pre.reserved))
        return Reservation(rid, worst, Verdict(True, "normal", "within budget",
                                               pre.spent_today, pre.spent_month,
                                               round(pre.reserved + worst, 4)))

    # ── settle ───────────────────────────────────────────────────────────────
    def _settle(self, reservation_id: str, actual_inr: float | None,
                actual_calls: int | None) -> Verdict:
        try:
            with self._connect() as c, c.transaction():
                outcome = self._settle_in(c, reservation_id, actual_inr, actual_calls)
        except Exception:  # noqa: BLE001 - the commit may have landed; look before answering
            outcome = self._receipt(reservation_id)
            if outcome is None:
                s = self._state()
                return Verdict(False, "offline", "atomic settlement outcome is unknown; no "
                               "retry should be made until the reservation is reconciled",
                               s["day_inr"], s["month_inr"], _reserved_total(s["reservations"]))
        s = self._state()
        here = (s["day_inr"], s["month_inr"], _reserved_total(s["reservations"]))
        kind = outcome[0]
        if kind == "unknown_unheld":
            return Verdict(False, "offline",
                           f"cannot settle unknown cost for reservation {reservation_id!r}: "
                           "there is no held amount to commit", *here)
        if kind == "duplicate":
            return Verdict(True, "normal", "duplicate settlement ignored; prior receipt is final",
                           *here)
        if kind == "unheld":
            return Verdict(True, "normal",
                           f"settled ₹{outcome[1]} against unknown reservation "
                           f"{reservation_id!r}; the spend is recorded once", *here)
        _, held, amount, count = outcome
        return Verdict(True, "normal", f"settled: held {held!r}, actual ₹{amount}, "
                       f"recorded {count} provider request(s)", *here)

    def _settle_in(self, c, rid: str, actual: float | None, calls: int | None) -> tuple:
        row = c.execute(
            "UPDATE model_spend_holds SET settled_at = now(), "
            "settled_inr = COALESCE(%(a)s::numeric, amount_inr), "
            "settled_requests = COALESCE(%(n)s::integer, requests), "
            "basis = CASE WHEN %(a)s::numeric IS NULL THEN 'held' ELSE 'measured' END "
            "WHERE reservation_id = %(rid)s AND settled_at IS NULL "
            "RETURNING day, amount_inr, requests, model, tenant, actor, settled_inr, "
            "settled_requests", {"a": _d(actual), "n": calls, "rid": rid}).fetchone()
        if row is not None:
            day, held, n, model, tenant, actor, amount, count = row
            dx, dn = amount - held, count - n
            for scope, period, d, _, _ in scopes(day, tenant, actor, model):
                held_add = held if actual is None and (scope, period) == (GLOBAL, "month") else 0
                c.execute(_ADJUST, {"dx": dx, "dn": dn, "held": held_add, "scope": scope,
                                    "period": period, "day": d})
            return ("settled", float(held), float(amount), int(count))
        if c.execute("SELECT 1 FROM model_spend_holds WHERE reservation_id = %s",
                     (rid,)).fetchone():
            return ("duplicate",)
        if actual is None:
            return ("unknown_unheld",)
        # No hold to settle against: record the spend once, with a receipt so a retry is a
        # duplicate rather than a second charge.
        count = 1 if calls is None else calls
        if c.execute("INSERT INTO model_spend_holds (reservation_id, day, amount_inr, requests, "
                     "tenant, actor, settled_inr, settled_requests, basis, settled_at) "
                     "VALUES (%s,%s,0,0,%s,%s,%s,%s,'measured',now()) "
                     "ON CONFLICT (reservation_id) DO NOTHING RETURNING 1",
                     (rid, self._today, self._tenant_id, self._user_id, _d(actual),
                      count)).fetchone() is None:
            return ("duplicate",)
        for scope, period, d, _, _ in scopes(self._today, self._tenant_id, self._user_id, None):
            _take(c, scope, period, d, actual, count, None, None)
        return ("unheld", float(actual))

    def _receipt(self, rid: str) -> tuple | None:
        try:
            with self._connect() as c:
                row = c.execute("SELECT amount_inr, settled_inr, settled_requests FROM "
                                "model_spend_holds WHERE reservation_id = %s AND settled_at "
                                "IS NOT NULL", (rid,)).fetchone()
        except Exception:  # noqa: BLE001
            return None
        return None if row is None else ("settled", float(row[0]), float(row[1]), int(row[2]))

    # ── the rest of the write paths ──────────────────────────────────────────
    def record_call(self, actual_inr: float, *, model: str | None = None,
                    tenant_id: str | None = None, user_id: str | None = None) -> Verdict:
        if actual_inr < 0:
            raise ValueError(f"actual cost must be >= 0, got {actual_inr}")
        tenant = _who(tenant_id) or self._tenant_id
        user = _who(user_id) or self._user_id
        try:
            with self._connect() as c, c.transaction():
                for scope, period, d, _, _ in scopes(self._today, tenant, user, model):
                    _take(c, scope, period, d, actual_inr, 1, None, None)
        except Exception:  # noqa: BLE001
            return self._unrecordable(actual_inr)
        s = self._state()
        return Verdict(True, "normal", "recorded", s["day_inr"], s["month_inr"],
                       _reserved_total(s["reservations"]))

    def _flag(self, scope: str, period: str) -> bool:
        day = self._today if period == "day" else self._today.replace(day=1)
        try:
            with self._connect() as c:
                _take(c, scope, period, day, 0.0, 0, None, None)
            return True
        except Exception:  # noqa: BLE001
            return False

    def record_credit_exhausted(self) -> bool:
        return self._flag(CREDIT_FLAG, "day")

    def record_provider_spend_cap(self) -> Verdict:
        if not self._flag(SPEND_CAP_FLAG, "month"):
            return self.can_make_call()
        s = self._state()
        return Verdict(False, "offline",
                       f"provider spend cap recorded — access returns "
                       f"{B.spend_cap_resets_at(self._today):%Y-%m-%d %H:%M UTC}",
                       s["day_inr"], s["month_inr"], _reserved_total(s["reservations"]))

    def claim_reservations(self, reservation_ids: tuple[str, ...], claim_id: str,
                           minimum_amount: float) -> bool:
        ids = set(reservation_ids)
        if not ids or not claim_id or minimum_amount < 0:
            return False
        try:
            with self._connect() as c, c.transaction():
                n = c.execute(
                    "UPDATE model_spend_holds SET claim_id = %s WHERE reservation_id = ANY(%s) "
                    "AND day = %s AND settled_at IS NULL AND claim_id IS NULL "
                    "AND amount_inr >= %s", (claim_id, list(ids), self._today,
                                              _d(minimum_amount))).rowcount
                if n != len(ids):
                    raise _Over("claim", "day")       # all or none: roll the partial claim back
        except Exception:  # noqa: BLE001 - an uncertain claim never admits work
            return False
        return True
