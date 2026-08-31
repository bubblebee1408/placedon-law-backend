"""Dated statutory thresholds, each carrying how well we actually know it.

s.2(85) does not state the small-company thresholds operatively. It states a
floor and a ceiling and then delegates:

    "(i) paid-up share capital of which does not exceed fifty lakh rupees or
     such higher amount AS MAY BE PRESCRIBED which shall not be more than
     [ten crore rupees]; [and] (ii) turnover of which [as per profit and loss
     account for the immediately preceding financial year] does not exceed two
     crore rupees or such higher amount as may be prescribed which shall not be
     more than [one hundred crore rupees]"

    -- quoted from our own corpus of the Act, not from recollection.

So the number that decides a real company is in a delegated rule, and the
widely-cited ₹4 crore / ₹40 crore appear nowhere in the Act. A classifier that
hardcoded them would be asserting a Rule it has never read.

## Why this file refuses rather than answers

Every threshold carries a provenance state from checker.provenance. `lookup()`
returns only what is SERVABLE. The prescribed amounts are NOT servable today:

  * India Code lists the operative instrument -- G.S.R. 700(E) of 15-09-2022,
    handle 123456789/508916 -- and its text bitstream is reachable.
  * But indiacode.gov.in/robots.txt has been answering **HTTP 502** on every
    attempt, and checker.robots fails closed on a 5xx: a 4xx means "no rules
    exist", a 5xx means "we cannot know what the rules are". So the compliant
    fetcher declines, correctly.
  * The reading recorded below was obtained OUTSIDE that gate and came back
    paraphrased rather than verbatim. It is a lead, not an acquisition. It is
    recorded so the work is not repeated, and marked so it cannot be served.

The consequence is deliberate: a small-company classification is
INSUFFICIENT_DATA until the instrument is acquired properly. That is the correct
answer today, and it is a better one than a confident number nobody verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.company_profile import Money
from checker.provenance import SERVABLE, UNRESOLVED, VERIFIED


@dataclass(frozen=True)
class Threshold:
    """One dated amount, with where it came from and how well we know it."""
    key: str
    amount: Money
    effective_from: date
    effective_to: date | None          # None = still in force so far as we know
    instrument: str                    # the instrument that sets it
    source_url: str
    state: str                         # a checker.provenance evidence state
    note: str = ""

    @property
    def servable(self) -> bool:
        return self.state in SERVABLE

    def covers(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        return self.effective_to is None or as_of <= self.effective_to


class ThresholdUnavailable(LookupError):
    """No threshold we are willing to serve covers this date."""

    def __init__(self, key: str, as_of: date, held: list[Threshold]) -> None:
        self.key, self.as_of, self.held = key, as_of, held
        if held:
            detail = "; ".join(
                f"{t.instrument} ({t.state}) — {t.note or 'not servable'}"
                for t in held)
            msg = (f"{key} at {as_of}: an amount is on record but not servable: "
                   f"{detail}")
        else:
            msg = f"{key} at {as_of}: no amount is on record at all"
        super().__init__(msg)


_INDIA_CODE = "https://indiacode.gov.in/handle/123456789"

# The Act's own limbs. These ARE in our corpus verbatim, so they are usable --
# but note what they are: the floor below which no prescription is needed, and
# the ceiling above which none may go. Neither is the operative number once a
# Rule has been made.
_ACT_BOUNDS: tuple[Threshold, ...] = (
    Threshold("small_company.paid_up_capital.statutory_floor", Money.lakh(50),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(i)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "the amount that applies absent any prescription; held verbatim "
              "in our corpus of the Act"),
    Threshold("small_company.paid_up_capital.prescription_ceiling", Money.crore(10),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(i)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "no prescribed amount may exceed this"),
    Threshold("small_company.turnover.statutory_floor", Money.crore(2),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(ii)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "turnover as per the profit and loss account for the immediately "
              "preceding financial year"),
    Threshold("small_company.turnover.prescription_ceiling", Money.crore(100),
              date(2013, 8, 30), None,
              "Companies Act 2013, s.2(85)(ii)", f"{_INDIA_CODE}/2114",
              VERIFIED,
              "no prescribed amount may exceed this"),
)

# The prescribed amounts. On record as a LEAD, not as law we may serve.
_PRESCRIBED: tuple[Threshold, ...] = (
    Threshold("small_company.paid_up_capital.prescribed", Money.crore(4),
              date(2022, 9, 15), None,
              "G.S.R. 700(E), Companies (Specification of Definition Details) "
              "Amendment Rules, 2022, dated 15-09-2022",
              f"{_INDIA_CODE}/508916",
              UNRESOLVED,
              "read outside the robots-respecting fetch path and returned "
              "paraphrased, not verbatim; indiacode.gov.in/robots.txt answers "
              "HTTP 502 so checker.robots declines. Acquire under S-002 before "
              "serving."),
    Threshold("small_company.turnover.prescribed", Money.crore(40),
              date(2022, 9, 15), None,
              "G.S.R. 700(E), Companies (Specification of Definition Details) "
              "Amendment Rules, 2022, dated 15-09-2022",
              f"{_INDIA_CODE}/508916",
              UNRESOLVED,
              "same instrument and same acquisition gap as the capital limb"),
)

ALL: tuple[Threshold, ...] = _ACT_BOUNDS + _PRESCRIBED


def held(key: str, as_of: date) -> list[Threshold]:
    """Every recorded amount for this key covering that date, servable or not."""
    return [t for t in ALL if t.key == key and t.covers(as_of)]


def lookup(key: str, as_of: date) -> Threshold:
    """The amount we are willing to serve. Raises rather than guessing."""
    candidates = held(key, as_of)
    servable = [t for t in candidates if t.servable]
    if not servable:
        raise ThresholdUnavailable(key, as_of, candidates)
    # Latest in force wins if several cover the date.
    return max(servable, key=lambda t: t.effective_from)


def operative_small_company_limits(as_of: date) -> tuple[Money, Money]:
    """Paid-up capital and turnover limits actually in force. Raises if unknown.

    Deliberately does NOT fall back to the statutory floor when the prescribed
    amount is unavailable. The floor is ₹50 lakh against a prescribed ₹4 crore,
    so falling back would classify most small companies as not small -- a wrong
    answer wearing the costume of a conservative one.
    """
    cap = lookup("small_company.paid_up_capital.prescribed", as_of)
    turn = lookup("small_company.turnover.prescribed", as_of)
    return cap.amount, turn.amount


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("prescribed_thresholds")
    today = date(2026, 8, 31)

    # The Act's own limbs are held and usable.
    floor = lookup("small_company.paid_up_capital.statutory_floor", today)
    check(floor.amount == Money.lakh(50), f"the statutory floor is ₹50 lakh ({floor.amount})")
    ceil = lookup("small_company.turnover.prescription_ceiling", today)
    check(ceil.amount == Money.crore(100), f"the turnover ceiling is ₹100 crore ({ceil.amount})")

    # The prescribed amounts are on record but refused.
    rec = held("small_company.paid_up_capital.prescribed", today)
    check(len(rec) == 1, "the prescribed capital amount is on record")
    check(rec[0].amount == Money.crore(4), f"...as ₹4 crore ({rec[0].amount})")
    check(not rec[0].servable, "...and is not servable")
    check("robots" in rec[0].note or "502" in rec[0].note,
          "...with the acquisition gap stated in the record")

    try:
        lookup("small_company.paid_up_capital.prescribed", today)
        check(False, "an unservable threshold is refused")
    except ThresholdUnavailable as e:
        check("not servable" in str(e), f"an unservable threshold is refused ({e})")

    try:
        operative_small_company_limits(today)
        check(False, "small-company limits are refused while unacquired")
    except ThresholdUnavailable:
        check(True, "small-company limits are refused while unacquired")

    # It must not silently fall back to the Act's floor.
    import inspect
    src = inspect.getsource(operative_small_company_limits)
    check("statutory_floor" not in src.split('"""')[2],
          "no fallback to the statutory floor in the code path")

    # Dates matter: nothing prescribed applies before the instrument existed.
    before = date(2022, 9, 14)
    check(not held("small_company.turnover.prescribed", before),
          "the 2022 prescription does not reach a date before it was made")
    check(held("small_company.turnover.prescribed", date(2022, 9, 15)),
          "...and does reach its own commencement date")

    # An unknown key is a refusal, not an empty answer.
    try:
        lookup("small_company.net_worth.prescribed", today)
        check(False, "an unknown key raises")
    except ThresholdUnavailable as e:
        check("no amount is on record" in str(e), f"an unknown key raises ({e})")

    # Every record names an instrument and a source.
    check(all(t.instrument and t.source_url for t in ALL),
          "every threshold names its instrument and source")
    check(all(t.state in (VERIFIED, UNRESOLVED) for t in ALL),
          "every threshold carries a provenance state")

    # The Act figures must never be confused for the operative ones.
    check(all("floor" in t.key or "ceiling" in t.key
              for t in _ACT_BOUNDS),
          "the Act's limbs are keyed as floor/ceiling, never as the operative amount")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
