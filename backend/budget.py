"""
Runtime budget enforcement — the check that runs before every LLM call.

This is the master spec's best idea (§4.3), with three corrections:

  * **The numbers.** The spec pairs "Rs 150-250/day" with a Rs 3,500/month cap. ₹150×30 = ₹4,500,
    ₹250×30 = ₹7,500 — both breach the cap, so `can_make_call()` would pass every daily check and
    then hit the monthly wall around day 14-23 with no warning. The derived daily figure is
    ₹3,500/30 = **₹116**.

  * **The cost model.** The spec's ₹3-5/call prices a mid-tier model at Opus rates. Measured on
    Haiku 4.5 (~6,700 in / ~700 out) an answer is **~₹0.97**, so the real ceiling is ~120
    answers/day, not the spec's 50.

  * **Persistence.** The spec's tracker holds counters on `self`. On serverless every invocation
    may be a fresh process, so an in-memory tracker resets to zero on each request and enforces
    nothing. This one persists to a JSON file, and `Store` is an interface so the same logic runs
    against Supabase or Redis when there is more than one instance.

Exhaustion is not an error. The product degrades to template mode and says so — never a silent
failure, never a guess.

Run:  python3 backend/budget.py
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

# ── The numbers. Change these here, nowhere else. ────────────────────────────
MONTHLY_CAP_INR = 3_500.0
DAILY_CAP_INR = round(MONTHLY_CAP_INR / 30, 2)      # ₹116.67 — derived, not asserted
USD_INR = 95.23                                      # 2026-08-06

# Anthropic pricing, USD per million tokens. LIST price, deliberately — see below.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5":  (3.00, 15.00),
    "claude-opus-5":    (5.00, 25.00),
}

# Sonnet 5 carries introductory pricing of $2.00/$10.00 through 2026-08-31 — today it actually
# costs ₹1.94/answer, not the ₹2.91 this table computes. The list price is kept anyway, on the
# rule that **a budget guard must only ever be wrong in the expensive direction**. Encoding the
# discount would make every estimate too low, and on 2026-09-01 the cap would silently start
# admitting calls it should refuse. Over-estimating costs us headroom; under-estimating costs us
# the guarantee. So the ₹1.94 is a discount we receive without spending against it.
DEFAULT_MODEL = "claude-sonnet-5"

Mode = Literal["normal", "budget", "offline"]

# ── BUD-2: four counters, not two (PLAN_16 §5.2) ─────────────────────────────
# A usage event has FOUR billable categories, not two: `input_tokens`,
# `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`.
#
# The trap is `input_tokens`: it counts **only the tokens after the last cache
# breakpoint**. Read as "total input" it under-bills a cached call by up to 90%, and the
# statutory prefix — the thing we cache — is nearly the whole request. That is the largest
# single error this file could contain, because it is invisible: the ledger simply runs
# slow and the cap admits calls it should have refused.
#
# Cache write is 1.25x the base input rate at the 5-minute TTL and 2x at the 1-hour TTL.
# Cache read is 0.1x.
CACHE_WRITE_MULTIPLIER: dict[str, float] = {"5m": 1.25, "1h": 2.00}
CACHE_READ_MULTIPLIER = 0.10

# The default is the 1-HOUR multiplier — the expensive one — even though the API's own
# default TTL is 5 minutes. Deliberate, and the same rule as the list price above: a caller
# that asks the API for `ttl: "1h"` and forgets to say so here under-bills 37.5% of its
# write, silently, for as long as nobody notices. A caller on the 5-minute default that
# forgets over-bills 60% of its write and loses headroom. Only one of those two mistakes
# can admit a call the cap should have refused.
DEFAULT_CACHE_TTL = "1h"

# Cache reads are cheaper still on some models (0.05x is documented for Opus 5.5). That is
# NOT encoded here, for the same reason the Sonnet 5 introductory price is not: a
# model-specific discount makes every estimate for that model too low the moment the
# discount changes, and §5.5 names this exact failure shape. 0.1x everywhere over-estimates
# where the discount is real, which is the safe direction.

_USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens",
                 "cache_read_input_tokens", "output_tokens")


def cost_inr(model: str, input_tokens: int = 0, output_tokens: int = 0, *,
             cache_creation_input_tokens: int = 0, cache_read_input_tokens: int = 0,
             cache_ttl: str = DEFAULT_CACHE_TTL, batch: bool = False) -> float:
    """Rupee cost of one call across all four billable counters. Batch API is 50% off.

    `input_tokens` and `output_tokens` stay positional so every existing two-argument call
    keeps working unchanged; the two cache counters are keyword-only, so there is no
    argument order in which they can be confused for each other. A two-argument call now
    means exactly one thing — "no cache was in play" — and `cost_of_usage()` exists so the
    cached path never has to be spelled out by hand.
    """
    if model not in PRICING:
        raise ValueError(f"unknown model {model!r} — add it to PRICING with its published rates")
    if cache_ttl not in CACHE_WRITE_MULTIPLIER:
        raise ValueError(f"unknown cache TTL {cache_ttl!r} — one of {sorted(CACHE_WRITE_MULTIPLIER)}")
    counts = (input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens)
    if any(c < 0 for c in counts):
        # A negative counter would credit the ledger, i.e. manufacture budget out of a
        # malformed usage record. Refuse it at the boundary.
        raise ValueError(f"token counts must be >= 0, got {counts}")

    inp, out = PRICING[model]
    usd = (
        (input_tokens / 1_000_000) * inp
        + (cache_creation_input_tokens / 1_000_000) * inp * CACHE_WRITE_MULTIPLIER[cache_ttl]
        + (cache_read_input_tokens / 1_000_000) * inp * CACHE_READ_MULTIPLIER
        + (output_tokens / 1_000_000) * out
    )
    if batch:
        usd *= 0.5
    return round(usd * USD_INR, 4)


def cost_of_usage(model: str, usage: object, *, cache_ttl: str = DEFAULT_CACHE_TTL,
                  batch: bool = False) -> float:
    """Cost of a call from the provider's own `response.usage`, dict or object.

    The correct path made the short one. Every field the response reports is read, so a
    cached call cannot be costed as though its prefix were free. A usage body carrying none
    of the four known fields raises rather than costing 0.0 — a silent zero is how a
    ledger stops counting.
    """
    def field(name: str) -> object:
        if isinstance(usage, Mapping):
            return usage.get(name)
        return getattr(usage, name, None)

    got = {name: field(name) for name in _USAGE_FIELDS}
    if all(v is None for v in got.values()):
        raise ValueError(
            f"usage carries none of {_USAGE_FIELDS} — refusing to cost it as zero")
    return cost_inr(model,
                    int(got["input_tokens"] or 0),
                    int(got["output_tokens"] or 0),
                    cache_creation_input_tokens=int(got["cache_creation_input_tokens"] or 0),
                    cache_read_input_tokens=int(got["cache_read_input_tokens"] or 0),
                    cache_ttl=cache_ttl, batch=batch)


# ── BUD-1: the 429 that must never be retried (PLAN_16 §5.3) ─────────────────
# Anthropic returns `rate_limit_error` for two different things, and only one of them is
# worth a second attempt:
#
#   429 WITH `retry-after`                         ordinary rate limit — back off exactly
#                                                  that long and try again.
#   429, no `retry-after`, and `error.details
#   .error_code == "enforced_spend_limit_reached"` the organisation's monthly spend cap —
#                                                  **stop**. Every retry fails, including
#                                                  the SDK's own automatic ones, until the
#                                                  cap resets at 00:00 UTC on the 1st.
#
# Treating the second like the first spends the whole month's retry budget against a wall,
# and — worse for this file — leaves the tracker believing a call is still possible.
SPEND_CAP_ERROR_CODE = "enforced_spend_limit_reached"


@dataclass(frozen=True)
class Rejection:
    """What a 429 actually was. `retryable` is the only question the caller has."""

    kind: Literal["rate_limit", "spend_cap"]
    retry_after_s: float | None
    # None for an ordinary rate limit: waiting is not a budget state, and the ledger is
    # untouched by it. A spend cap is `offline`, not `budget` — see below.
    mode: Mode | None
    reason: str

    @property
    def retryable(self) -> bool:
        return self.kind == "rate_limit"


def _retry_after_seconds(headers: Mapping[str, str] | None) -> float | None:
    """delta-seconds from `retry-after`, or None.

    None where the header is absent, or an HTTP-date, or anything else this does not
    understand. Never 0.0 — a fabricated zero is an instant retry, which is the one
    behaviour a missing header must not produce.
    """
    if not headers:
        return None
    for k, v in headers.items():
        if k.lower() != "retry-after":
            continue
        try:
            secs = float(v)
        except (TypeError, ValueError):
            return None
        return secs if secs >= 0 else None
    return None


def _error_code(body: Mapping[str, object] | None) -> str | None:
    """`error.details.error_code`, tolerating every shape a wire body can arrive in.

    This reads data from the network. It may not raise on a malformed body — a parse
    failure here would be indistinguishable from a rate limit, and would be retried.
    """
    if not isinstance(body, Mapping):
        return None
    err = body.get("error")
    if not isinstance(err, Mapping):
        return None
    details = err.get("details")
    if not isinstance(details, Mapping):
        return None
    code = details.get("error_code")
    return code if isinstance(code, str) else None


def classify_429(headers: Mapping[str, str] | None = None,
                 body: Mapping[str, object] | None = None) -> Rejection:
    """Which kind of `rate_limit_error` this is. Pure — no SDK import, no network.

    The spend-cap code decides even when a `retry-after` header is also present. The code
    is the specific signal and a header can be added by anything in the path; believing
    the header instead would resume retrying against a wall, which is the exact failure
    this function exists to prevent.

    A 429 with neither signal is an ordinary rate limit with an unknown delay. It is NOT
    inferred to be a spend cap: "no retry-after" alone is absence of evidence.
    """
    if _error_code(body) == SPEND_CAP_ERROR_CODE:
        return Rejection(
            "spend_cap", None, "offline",
            f"provider monthly spend cap ({SPEND_CAP_ERROR_CODE}) — retrying cannot succeed "
            f"before {spend_cap_resets_at():%Y-%m-%d %H:%M UTC}",
        )
    secs = _retry_after_seconds(headers)
    if secs is None:
        return Rejection("rate_limit", None, None,
                         "rate limit, no usable retry-after — back off on your own schedule")
    return Rejection("rate_limit", secs, None, f"rate limit — retry after {secs:g}s")


def spend_cap_resets_at(today: date | None = None) -> datetime:
    """00:00 UTC on the 1st of the next month, when provider access returns."""
    d = today or date.today()
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    mode: Mode
    reason: str
    spent_today: float
    spent_month: float

    @property
    def remaining_month(self) -> float:
        return round(MONTHLY_CAP_INR - self.spent_month, 2)


class Store(Protocol):
    def read(self) -> dict: ...
    def write(self, data: dict) -> None: ...


class FileStore:
    """Good enough for one instance. Swap for Supabase/Redis when there are several."""

    def __init__(self, path: Path | str = "corpus/.budget.json") -> None:
        self.path = Path(path)

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must not authorise spending. Treat as fully spent.
            return {"corrupt": True}

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)


class BudgetTracker:
    def __init__(self, store: Store | None = None, *, today: date | None = None) -> None:
        self.store = store or FileStore()
        self._today = today or date.today()

    # ── state ────────────────────────────────────────────────────────────
    def _state(self) -> dict:
        raw = self.store.read()
        if raw.get("corrupt"):
            return {"corrupt": True, "day": "", "month": "", "day_inr": 0.0, "month_inr": 0.0}
        day_key, month_key = self._today.isoformat(), self._today.strftime("%Y-%m")
        return {
            "corrupt": False,
            "day": day_key,
            "month": month_key,
            # Counters reset when the calendar rolls over, not by a cron job nobody runs.
            "day_inr": float(raw.get("day_inr", 0.0)) if raw.get("day") == day_key else 0.0,
            "month_inr": float(raw.get("month_inr", 0.0)) if raw.get("month") == month_key else 0.0,
            "calls_today": int(raw.get("calls_today", 0)) if raw.get("day") == day_key else 0,
            # Scoped to the month, so it clears itself exactly when the provider's cap does.
            "spend_cap": raw.get("spend_cap_month") == month_key,
        }

    # ── the gate ─────────────────────────────────────────────────────────
    def can_make_call(self, estimated_inr: float | None = None, *, model: str = DEFAULT_MODEL,
                      input_tokens: int = 6_700, output_tokens: int = 700) -> Verdict:
        if estimated_inr is None:
            estimated_inr = cost_inr(model, input_tokens, output_tokens)

        s = self._state()
        if s["corrupt"]:
            return Verdict(False, "offline",
                           "budget ledger unreadable — refusing to spend against an unknown balance",
                           0.0, 0.0)

        # Before our own caps: this one is not ours to raise. `offline`, not `budget`,
        # because a spend cap blocks every model — a caller reading `budget` might retry
        # on Haiku, and that fails too.
        if s["spend_cap"]:
            return Verdict(False, "offline",
                           f"provider spend cap reached — no call succeeds before "
                           f"{spend_cap_resets_at(self._today):%Y-%m-%d %H:%M UTC}",
                           s["day_inr"], s["month_inr"])

        if s["month_inr"] + estimated_inr > MONTHLY_CAP_INR:
            return Verdict(False, "budget",
                           f"monthly cap reached: ₹{s['month_inr']:.2f} spent of ₹{MONTHLY_CAP_INR:.0f}",
                           s["day_inr"], s["month_inr"])

        if s["day_inr"] + estimated_inr > DAILY_CAP_INR:
            return Verdict(False, "budget",
                           f"daily cap reached: ₹{s['day_inr']:.2f} of ₹{DAILY_CAP_INR:.2f}. "
                           f"Monthly still has ₹{MONTHLY_CAP_INR - s['month_inr']:.2f}.",
                           s["day_inr"], s["month_inr"])

        return Verdict(True, "normal", "within budget", s["day_inr"], s["month_inr"])

    def _persist(self, s: dict, **overrides) -> None:
        """Every write goes through here.

        A write that omits a field silently clears it, and the field most costly to
        clear is `spend_cap_month` — losing it re-admits calls the provider will refuse.
        """
        row = {
            "day": s["day"], "month": s["month"],
            "day_inr": s["day_inr"], "month_inr": s["month_inr"],
            "calls_today": s["calls_today"],
        }
        if s["spend_cap"]:
            row["spend_cap_month"] = s["month"]
        row.update(overrides)
        self.store.write(row)

    def record_call(self, actual_inr: float) -> Verdict:
        s = self._state()
        day = round(s["day_inr"] + actual_inr, 4)
        month = round(s["month_inr"] + actual_inr, 4)
        self._persist(s, day_inr=day, month_inr=month, calls_today=s["calls_today"] + 1)
        return Verdict(True, "normal", "recorded", day, month)

    def record_provider_spend_cap(self) -> Verdict:
        """The provider said `enforced_spend_limit_reached`. Remember it.

        Without this the tracker keeps saying `allowed=True` while every call 429s, and
        the retry path keeps paying for the privilege. Exhaustion is not an error: the
        product degrades to template mode and says so.
        """
        s = self._state()
        if s["corrupt"]:
            # Nothing can be written against an unreadable ledger. The corrupt path already
            # refuses every call, so the flag would change nothing.
            return self.can_make_call()
        self._persist(s, spend_cap_month=s["month"])
        return Verdict(False, "offline",
                       f"provider spend cap recorded — access returns "
                       f"{spend_cap_resets_at(self._today):%Y-%m-%d %H:%M UTC}",
                       s["day_inr"], s["month_inr"])

    def mode(self) -> Mode:
        return self.can_make_call().mode


# Env override for a manual kill switch (spec §12, adopted).
def forced_mode() -> Mode | None:
    v = os.getenv("LLM_MODE")
    return v if v in ("normal", "budget", "offline") else None  # type: ignore[return-value]


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    class Mem:
        def __init__(self) -> None: self.d: dict = {}
        def read(self) -> dict: return dict(self.d)
        def write(self, data: dict) -> None: self.d = dict(data)

    failures = 0
    total = 0

    def check(name: str, got, want) -> None:
        global failures, total
        ok = got == want
        failures += (not ok)
        total += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r} want={want!r}"))

    def attempt(fn):
        """fn()'s value, or a string naming the exception it raised.

        A check written against a function that does not exist yet must FAIL with a
        count, not crash the suite before the count line is printed. The harness reads
        `N/M passed`; a traceback gives it nothing to read.
        """
        try:
            return fn()
        except Exception as e:                      # noqa: BLE001 - the exception IS the result
            return f"{type(e).__name__}: {e}"

    # The correction that motivated this file.
    check("daily cap is derived, not the spec's 150-250", DAILY_CAP_INR, 116.67)
    check("spec's Rs150/day would breach the monthly cap", 150 * 30 > MONTHLY_CAP_INR, True)

    haiku = cost_inr("claude-haiku-4-5", 6_700, 700)
    opus = cost_inr("claude-opus-5", 6_700, 700)
    print(f"       measured: haiku ₹{haiku}  opus ₹{opus}  "
          f"→ {int(MONTHLY_CAP_INR / haiku):,} vs {int(MONTHLY_CAP_INR / opus):,} answers/month")
    check("haiku answer under ₹1", haiku < 1.0, True)
    check("opus is ~5x haiku", round(opus / haiku) == 5, True)
    check("batch API halves it", cost_inr("claude-opus-5", 6_700, 700, batch=True), round(opus / 2, 4))

    t = BudgetTracker(Mem(), today=date(2026, 8, 8))
    check("fresh tracker allows a call", t.can_make_call().allowed, True)

    for _ in range(120):
        t.record_call(haiku)
    v = t.can_make_call()
    check("~120 haiku answers exhausts the day", v.allowed, False)
    check("  ...and reports budget mode", v.mode, "budget")
    check("  ...month still has headroom", v.remaining_month > 3_000, True)

    # Month nearly spent over previous days; today is fresh. The daily gate would happily
    # allow this call — only the monthly gate should stop it.
    near = Mem()
    near.d = {"day": "2026-08-08", "month": "2026-08",
              "day_inr": 0.0, "month_inr": MONTHLY_CAP_INR - 0.5, "calls_today": 0}
    v2 = BudgetTracker(near, today=date(2026, 8, 8)).can_make_call()
    check("monthly cap blocks even with the day untouched", v2.allowed, False)
    check("  ...names the monthly cap, not the daily one", "monthly" in v2.reason, True)
    check("  ...and the daily gate would have allowed it", 0.0 + haiku < DAILY_CAP_INR, True)

    class Corrupt:
        def read(self) -> dict: return {"corrupt": True}
        def write(self, data: dict) -> None: ...
    v3 = BudgetTracker(Corrupt()).can_make_call()
    check("unreadable ledger refuses to spend", v3.allowed, False)
    check("  ...goes offline, not budget", v3.mode, "offline")

    rolled = Mem()
    rolled.d = {"day": "2026-08-07", "month": "2026-08", "day_inr": 116.0,
                "month_inr": 200.0, "calls_today": 120}
    v4 = BudgetTracker(rolled, today=date(2026, 8, 8)).can_make_call()
    check("new day resets the daily counter", v4.allowed, True)
    check("  ...but carries the month forward", v4.spent_month, 200.0)

    try:
        cost_inr("claude-3-5-sonnet-20241022", 100, 100)
        check("retired model rejected", False, True)
    except ValueError:
        check("retired model rejected", True, True)


    # ── BUD-1: the 429 that must never be retried (PLAN_16 §5.3) ─────────────
    ordinary = attempt(lambda: classify_429(headers={"retry-after": "30"}))
    check("a 429 carrying retry-after is an ordinary rate limit",
          getattr(ordinary, "kind", ordinary), "rate_limit")
    check("  ...it is retryable", getattr(ordinary, "retryable", None), True)
    check("  ...and it carries the delay the header asked for",
          getattr(ordinary, "retry_after_s", None), 30.0)
    check("  ...and it does not touch the budget mode",
          getattr(ordinary, "mode", "unset"), None)

    cap_body = {"type": "error", "error": {"type": "rate_limit_error",
                "details": {"error_code": "enforced_spend_limit_reached"}}}
    cap = attempt(lambda: classify_429(headers={}, body=cap_body))
    check("a spend-cap 429 is NOT an ordinary rate limit",
          getattr(cap, "kind", cap), "spend_cap")
    check("  ...and retrying it is refused outright",
          getattr(cap, "retryable", None), False)
    check("  ...it falls to offline, not to a cheaper model",
          getattr(cap, "mode", None), "offline")

    both = attempt(lambda: classify_429(headers={"Retry-After": "5"}, body=cap_body))
    check("the spend-cap code wins even when a retry-after header is present",
          getattr(both, "retryable", None), False)

    bare = attempt(lambda: classify_429(headers={}, body={"error": {"type": "rate_limit_error"}}))
    check("a 429 with neither signal is never GUESSED to be a spend cap",
          getattr(bare, "kind", bare), "rate_limit")
    check("  ...and its delay is None, not a fabricated zero",
          getattr(bare, "retry_after_s", "unset"), None)
    check("an unparseable retry-after yields None rather than an immediate retry",
          getattr(attempt(lambda: classify_429(headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})),
                  "retry_after_s", "unset"), None)

    check("the cap resets at 00:00 UTC on the 1st, across a year boundary",
          attempt(lambda: spend_cap_resets_at(date(2026, 12, 31)).isoformat()),
          "2027-01-01T00:00:00+00:00")

    capped = Mem()
    tc = BudgetTracker(capped, today=date(2026, 8, 8))
    attempt(lambda: tc.record_provider_spend_cap())
    v5 = tc.can_make_call()
    check("a recorded provider spend cap refuses the next call", v5.allowed, False)
    check("  ...in offline mode", v5.mode, "offline")
    check("  ...and says when access returns", "2026-09-01" in v5.reason, True)
    tc.record_call(haiku)
    check("  ...and recording a call does not silently clear it",
          tc.can_make_call().allowed, False)
    check("  ...but next month the flag is gone",
          BudgetTracker(capped, today=date(2026, 9, 1)).can_make_call().allowed, True)


    def refused(fn) -> bool:
        """True only when fn() raised ValueError.

        `isinstance(attempt(fn), str)` is not enough: a NameError from a function that
        does not exist yet is also a string, so such a check passes before the code is
        written and proves nothing.
        """
        r = attempt(fn)
        return isinstance(r, str) and r.startswith("ValueError")

    # ── BUD-2: four counters, not two (PLAN_16 §5.2) ─────────────────────────
    M = 1_000_000
    check("the two-argument call is unchanged by the four-counter signature",
          cost_inr("claude-haiku-4-5", 6_700, 700), 0.9713)
    check("a cache READ is a tenth of an input token",
          attempt(lambda: cost_inr("claude-haiku-4-5", 0, 0, cache_read_input_tokens=M)), 9.523)
    check("a cache WRITE at the 5-minute TTL is 1.25x",
          attempt(lambda: cost_inr("claude-haiku-4-5", 0, 0,
                                   cache_creation_input_tokens=M, cache_ttl="5m")), 119.0375)
    check("a cache WRITE at the 1-hour TTL is 2x",
          attempt(lambda: cost_inr("claude-haiku-4-5", 0, 0,
                                   cache_creation_input_tokens=M, cache_ttl="1h")), 190.46)
    # Stated as the literal 1-hour figure, not as "equals the 1h call": comparing two
    # calls to the same missing function is a check that passes before the code exists.
    check("the DEFAULT write multiplier is the expensive one (1h, not the API's 5m)",
          attempt(lambda: cost_inr("claude-haiku-4-5", 0, 0, cache_creation_input_tokens=M)),
          190.46)
    check("an unknown TTL is refused rather than guessed",
          refused(lambda: cost_inr("claude-haiku-4-5", 0, 0,
                                   cache_creation_input_tokens=M, cache_ttl="7d")), True)
    check("a negative counter is refused — it would credit the ledger",
          refused(lambda: cost_inr("claude-haiku-4-5", -1, 0)), True)

    # The failure §5.2 names: `input_tokens` counts only what follows the last cache
    # breakpoint, so a cached call passed through the two-argument door under-bills badly.
    naive = cost_inr("claude-haiku-4-5", 700, 700)
    true_cost = attempt(lambda: cost_inr("claude-haiku-4-5", 700, 700,
                                         cache_read_input_tokens=200_000))
    check("a 200k cached prefix costs real money the two-arg call cannot see",
          isinstance(true_cost, float) and true_cost > naive, True)
    check("  ...and the two-arg call under-bills it by more than 80%",
          isinstance(true_cost, float) and (1 - naive / true_cost) > 0.80, True)

    check("the four counters sum rather than collapse",
          attempt(lambda: cost_inr("claude-opus-5", 1_000, 2_000,
                                   cache_creation_input_tokens=3_000,
                                   cache_read_input_tokens=4_000, cache_ttl="5m")),
          round(((1_000 * 5.0) + (2_000 * 25.0) + (3_000 * 5.0 * 1.25)
                 + (4_000 * 5.0 * 0.10)) / 1_000_000 * USD_INR, 4))
    # Within one unit of the ledger's own 4-decimal rounding: the halving happens in USD
    # before the conversion, so `batch * 2 == full` only up to that last place.
    check("batch still halves the whole four-counter bill",
          attempt(lambda: abs(cost_inr("claude-opus-5", 1_000, 2_000,
                                       cache_read_input_tokens=4_000, batch=True) * 2
                              - cost_inr("claude-opus-5", 1_000, 2_000,
                                         cache_read_input_tokens=4_000)) < 1e-3), True)

    usage = {"input_tokens": 700, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 200_000, "output_tokens": 700}
    check("cost_of_usage reads all four counters off a usage dict",
          attempt(lambda: cost_of_usage("claude-haiku-4-5", usage)), true_cost)

    class _Usage:                       # what the SDK actually hands back
        input_tokens = 700
        cache_creation_input_tokens = 0
        cache_read_input_tokens = 200_000
        output_tokens = 700
    check("  ...and off the SDK's usage object, not only a dict",
          attempt(lambda: cost_of_usage("claude-haiku-4-5", _Usage())), true_cost)
    check("  ...and refuses a usage body carrying none of the four",
          refused(lambda: cost_of_usage("claude-haiku-4-5", {"tokens": 5})), True)

    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)
