"""s.180 — restrictions on the powers of the Board. The borrowing limb, computed.

Grounded in the corpus text of s.180. The Board may exercise certain powers ONLY
with the company's consent by a SPECIAL RESOLUTION:
  (a) sell/lease/dispose the whole or substantially the whole of an undertaking;
  (b) invest the compensation from a merger/amalgamation otherwise than in trust
      securities;
  (c) BORROW money where the money to be borrowed, with money already borrowed,
      will EXCEED the aggregate of paid-up share capital + free reserves +
      securities premium — apart from temporary loans from the company's bankers
      in the ordinary course of business;
  (d) remit or give time for the repayment of a debt due by a director.

This module computes limb (c) — the arithmetic one — and flags (a)/(b)/(d) as not
modelled (they turn on undertaking valuation, merger compensation, and director
debt, which this data does not carry). Same money discipline as s.186: figures are
whole rupees, an unknown figure is never treated as "under" the limit, and a
temporary bankers' loan in the ordinary course is excluded from the test.
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.company_profile import Money

WITHIN_BORROWING_LIMIT = "WITHIN_BORROWING_LIMIT"
EXCEEDS_NEEDS_SPECIAL_RESOLUTION = "EXCEEDS_NEEDS_SPECIAL_RESOLUTION"
EXEMPT = "EXEMPT"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

PROVISION = "Companies Act 2013, s.180(1)(c)"
_LIMBS_NOT_MODELLED = (
    "s.180(1)(a) sale/disposal of an undertaking, (b) investment of merger "
    "compensation, and (d) remission of a director's debt are not evaluated here")


@dataclass(frozen=True)
class BorrowingFacts:
    company: str
    proposed_borrowing: Money
    existing_borrowings: Money | None = None
    paid_up_capital: Money | None = None
    free_reserves: Money | None = None
    securities_premium: Money | None = None
    # the proviso: a temporary loan from the company's bankers in the ordinary
    # course is excluded from the s.180(1)(c) test. Tri-valued (None = unknown).
    temporary_bankers_loan: bool | None = None


@dataclass(frozen=True)
class Determination:
    status: str
    reason: str
    limit_rupees: int | None = None
    total_rupees: int | None = None
    conditions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return self.status in (EXCEEDS_NEEDS_SPECIAL_RESOLUTION, CANNOT_DETERMINE)


def _limit(f: BorrowingFacts) -> int | None:
    """paid-up capital + free reserves + securities premium, or None if any unknown."""
    parts = (f.paid_up_capital, f.free_reserves, f.securities_premium)
    if any(p is None for p in parts):
        return None
    return sum(p.rupees for p in parts)               # type: ignore[union-attr]


def assess(facts: BorrowingFacts) -> Determination:
    notes = (_LIMBS_NOT_MODELLED,)

    # The proviso: a temporary bankers' loan in the ordinary course is outside (c).
    if facts.temporary_bankers_loan is True:
        return Determination(EXEMPT,
                             "a temporary loan from the company's bankers in the ordinary "
                             "course of business is outside s.180(1)(c)", notes=notes)

    limit = _limit(facts)
    if limit is None:
        missing = [name for name, v in (
            ("paid-up share capital", facts.paid_up_capital),
            ("free reserves", facts.free_reserves),
            ("securities premium", facts.securities_premium)) if v is None]
        return Determination(CANNOT_DETERMINE,
                             "the s.180(1)(c) borrowing limit cannot be computed while a "
                             "balance-sheet figure is unknown (an unknown figure is not zero)",
                             missing=tuple(missing), notes=notes)
    if facts.existing_borrowings is None:
        return Determination(CANNOT_DETERMINE,
                             "the limit is known but existing borrowings are not, so the total "
                             "cannot be tested",
                             limit_rupees=limit,
                             missing=("the money already borrowed by the company",), notes=notes)

    total = facts.existing_borrowings.rupees + facts.proposed_borrowing.rupees
    if total > limit:
        return Determination(EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
                             f"total borrowing {Money(total)} would exceed the s.180(1)(c) limit "
                             f"{Money(limit)} (paid-up capital + free reserves + securities premium)",
                             limit_rupees=limit, total_rupees=total,
                             conditions=("prior consent of the company by a special resolution "
                                         "(s.180(1))",), notes=notes)
    return Determination(WITHIN_BORROWING_LIMIT,
                         f"total borrowing {Money(total)} is within the s.180(1)(c) limit "
                         f"{Money(limit)}",
                         limit_rupees=limit, total_rupees=total, notes=notes)


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

    print("s180")
    # limit = 2cr capital + 1cr reserves + 0 premium = 3cr
    puc, fr, sp = Money.crore(2), Money.crore(1), Money(0)

    # ── within the limit ────────────────────────────────────────────────────
    d = assess(BorrowingFacts("CO", Money.crore(1), existing_borrowings=Money.crore(1),
                              paid_up_capital=puc, free_reserves=fr, securities_premium=sp))
    check(d.status == WITHIN_BORROWING_LIMIT, f"2cr total within 3cr limit ({d.status})")
    check(d.limit_rupees == Money.crore(3).rupees, f"the limit is 3cr ({Money(d.limit_rupees)})")

    # ── exceeds -> special resolution ───────────────────────────────────────
    d2 = assess(BorrowingFacts("CO", Money.crore(3), existing_borrowings=Money.crore(1),
                               paid_up_capital=puc, free_reserves=fr, securities_premium=sp))
    check(d2.status == EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
          f"4cr total over 3cr limit needs a special resolution ({d2.status})")
    check(any("special resolution" in c for c in d2.conditions),
          "...naming the special-resolution condition")

    # ── the temporary bankers' loan proviso ─────────────────────────────────
    d3 = assess(BorrowingFacts("CO", Money.crore(100), temporary_bankers_loan=True))
    check(d3.status == EXEMPT, "a temporary bankers' loan is outside s.180(1)(c)")

    # ── unknown figure -> CANNOT_DETERMINE, never 'under' ───────────────────
    d4 = assess(BorrowingFacts("CO", Money.crore(1), existing_borrowings=Money.crore(1),
                               paid_up_capital=puc, free_reserves=None, securities_premium=sp))
    check(d4.status == CANNOT_DETERMINE and "free reserves" in d4.missing,
          "an unknown free-reserves figure refuses, naming it")
    d5 = assess(BorrowingFacts("CO", Money.crore(1), existing_borrowings=None,
                               paid_up_capital=puc, free_reserves=fr, securities_premium=sp))
    check(d5.status == CANNOT_DETERMINE and d5.limit_rupees is not None,
          "a known limit but unknown existing borrowings still refuses")

    # ── an unknown proviso flag does not exempt ─────────────────────────────
    d6 = assess(BorrowingFacts("CO", Money.crore(3), existing_borrowings=Money.crore(1),
                               paid_up_capital=puc, free_reserves=fr, securities_premium=sp,
                               temporary_bankers_loan=None))
    check(d6.status == EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
          "an unknown temporary-loan flag does not exempt an over-limit borrowing")

    # ── the other limbs are flagged, never assumed satisfied ────────────────
    check(any("undertaking" in n for n in d.notes),
          "every determination notes the (a)/(b)/(d) limbs are not modelled")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
