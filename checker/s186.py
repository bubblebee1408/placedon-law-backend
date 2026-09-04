"""s.186 — loan and investment by a company: is a proposed transaction over the limit?

A transaction-scoped decider grounded in the corpus text of s.186 (read, not
recalled). Its headline commercial limb is s.186(2)/(3):

  (2) A company shall not give a loan/guarantee/security, or acquire securities of
      a body corporate, EXCEEDING
          60% of (paid-up share capital + free reserves + securities premium), OR
          100% of (free reserves + securities premium),
      WHICHEVER IS MORE.
  (3) Where the aggregate of loans/investments/guarantees already made PLUS the
      proposed one exceeds the (2) limit, it may not be made unless previously
      authorised by a SPECIAL RESOLUTION in general meeting. Proviso: this does
      not apply to a loan/guarantee/security to a wholly-owned subsidiary or a
      joint venture, or a holding company acquiring its wholly-owned subsidiary's
      securities.

## Two honest boundaries

1. The ceiling needs free reserves and securities premium — figures the corpus'
   `CompanyProfile` does not carry — so this decider takes the balance-sheet
   figures directly and, per the project's money discipline, REFUSES (returns
   CANNOT_DETERMINE naming the field) when any is unknown. An unknown figure is
   never treated as zero: a zero free-reserve would understate the ceiling and
   make an over-limit transaction look within limit.

2. It decides the (2)/(3) financial ceiling only. The s.186(1) "not more than two
   layers of investment companies" limb is structural and NOT modelled here; a
   note records it so its absence is visible, not silently assumed satisfied.
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.company_profile import Money

WITHIN_LIMIT = "WITHIN_LIMIT"
EXCEEDS_NEEDS_SPECIAL_RESOLUTION = "EXCEEDS_NEEDS_SPECIAL_RESOLUTION"
EXEMPT = "EXEMPT"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

PROVISION = "Companies Act 2013, s.186"

# The 2(85)-style constants, but stated in the Act itself, so usable.
_PCT_60 = 60
_PCT_100 = 100
_LAYERS_LIMB_NOT_MODELLED = (
    "s.186(1) (investment through not more than two layers of investment "
    "companies) is not evaluated here")


@dataclass(frozen=True)
class InvestmentFacts:
    company: str
    proposed_amount: Money                     # the loan/guarantee/security/acquisition
    # balance-sheet figures the ceiling needs; None = unknown (never treated as 0)
    paid_up_capital: Money | None = None
    free_reserves: Money | None = None
    securities_premium: Money | None = None
    # aggregate of loans/investments/guarantees already made to all bodies corporate
    existing_aggregate: Money | None = None
    # s.186(3) proviso exemptions, tri-valued (None = unknown)
    to_wholly_owned_subsidiary: bool | None = None
    to_joint_venture: bool | None = None
    holding_acquiring_wos_securities: bool | None = None


@dataclass(frozen=True)
class Determination:
    status: str
    reason: str
    ceiling_rupees: int | None = None
    aggregate_rupees: int | None = None
    conditions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return self.status in (EXCEEDS_NEEDS_SPECIAL_RESOLUTION, CANNOT_DETERMINE)


def _ceiling(f: InvestmentFacts) -> int | None:
    """The s.186(2) limit in whole rupees, or None if a figure is unknown.

    Both branches need free reserves and securities premium; the 60% branch also
    needs paid-up capital. Any unknown makes the ceiling unknown — we do not
    compute one branch and pretend it is the maximum.
    """
    if f.free_reserves is None or f.securities_premium is None or f.paid_up_capital is None:
        return None
    fr_sp = f.free_reserves.rupees + f.securities_premium.rupees
    branch_60 = (_PCT_60 * (f.paid_up_capital.rupees + fr_sp)) // 100
    branch_100 = (_PCT_100 * fr_sp) // 100
    return max(branch_60, branch_100)


def assess(facts: InvestmentFacts) -> Determination:
    notes = (_LAYERS_LIMB_NOT_MODELLED,)

    # ── (3) proviso exemptions, only when POSITIVELY established ─────────────
    if facts.to_wholly_owned_subsidiary is True:
        return Determination(EXEMPT,
                             "a loan/guarantee/security to a wholly-owned subsidiary "
                             "(s.186(3) proviso); the sub-section limit does not apply",
                             conditions=("disclose the particulars in the financial "
                                         "statement (s.186(4))",), notes=notes)
    if facts.to_joint_venture is True:
        return Determination(EXEMPT,
                             "a loan/guarantee/security to a joint venture company "
                             "(s.186(3) proviso)",
                             conditions=("disclose in the financial statement (s.186(4))",),
                             notes=notes)
    if facts.holding_acquiring_wos_securities is True:
        return Determination(EXEMPT,
                             "a holding company acquiring its wholly-owned subsidiary's "
                             "securities (s.186(3) proviso)",
                             conditions=("disclose in the financial statement (s.186(4))",),
                             notes=notes)

    # ── the ceiling arithmetic; refuse on any unknown figure ────────────────
    ceiling = _ceiling(facts)
    if ceiling is None:
        missing = [name for name, v in (
            ("paid-up share capital", facts.paid_up_capital),
            ("free reserves", facts.free_reserves),
            ("securities premium", facts.securities_premium)) if v is None]
        return Determination(CANNOT_DETERMINE,
                             "the s.186(2) ceiling cannot be computed while a balance-sheet "
                             "figure is unknown (an unknown figure is not zero)",
                             missing=tuple(missing), notes=notes)
    if facts.existing_aggregate is None:
        return Determination(CANNOT_DETERMINE,
                             "the ceiling is known but the existing aggregate of loans/"
                             "investments/guarantees is not, so the total cannot be tested",
                             ceiling_rupees=ceiling,
                             missing=("the aggregate already made to all bodies corporate",),
                             notes=notes)

    total = facts.existing_aggregate.rupees + facts.proposed_amount.rupees
    if total <= ceiling:
        return Determination(WITHIN_LIMIT,
                             f"the aggregate {Money(total)} does not exceed the s.186(2) "
                             f"limit {Money(ceiling)}",
                             ceiling_rupees=ceiling, aggregate_rupees=total,
                             conditions=("consent of the Board by resolution with all "
                                         "directors present (s.186(5))",),
                             notes=notes)
    return Determination(EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
                         f"the aggregate {Money(total)} exceeds the s.186(2) limit "
                         f"{Money(ceiling)}",
                         ceiling_rupees=ceiling, aggregate_rupees=total,
                         conditions=("prior authorisation by a special resolution in "
                                     "general meeting (s.186(3))",
                                     "consent of the Board with all directors present "
                                     "(s.186(5))"),
                         notes=notes)


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

    print("s186")

    # paid-up 1cr, free reserves 2cr, securities premium 0 -> ceiling =
    #   max(60% of 3cr = 1.8cr, 100% of 2cr = 2cr) = 2cr
    puc, fr, sp = Money.crore(1), Money.crore(2), Money(0)

    # ── within limit ────────────────────────────────────────────────────────
    d = assess(InvestmentFacts("CO", Money.crore(0.5), paid_up_capital=puc,
                               free_reserves=fr, securities_premium=sp,
                               existing_aggregate=Money.crore(1)))
    check(d.status == WITHIN_LIMIT, f"aggregate 1.5cr <= 2cr ceiling is WITHIN_LIMIT ({d.status})")
    check(d.ceiling_rupees == Money.crore(2).rupees,
          f"the ceiling is the 100% branch = 2cr ({Money(d.ceiling_rupees)})")

    # ── exceeds -> special resolution ───────────────────────────────────────
    d2 = assess(InvestmentFacts("CO", Money.crore(1.5), paid_up_capital=puc,
                                free_reserves=fr, securities_premium=sp,
                                existing_aggregate=Money.crore(1)))
    check(d2.status == EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
          f"aggregate 2.5cr > 2cr ceiling needs a special resolution ({d2.status})")
    check(any("special resolution" in c for c in d2.conditions),
          "...naming the special-resolution condition")

    # ── the 60% branch wins when capital is large ───────────────────────────
    # puc 10cr, fr 1cr, sp 0 -> max(60% of 11cr = 6.6cr, 100% of 1cr = 1cr) = 6.6cr
    d3 = assess(InvestmentFacts("CO", Money.crore(1), paid_up_capital=Money.crore(10),
                                free_reserves=Money.crore(1), securities_premium=Money(0),
                                existing_aggregate=Money.crore(5)))
    check(d3.ceiling_rupees == Money.lakh(660).rupees,
          f"the 60% branch (6.6cr) is the higher ceiling ({Money(d3.ceiling_rupees)})")
    check(d3.status == WITHIN_LIMIT, "6cr aggregate is within the 6.6cr ceiling")

    # ── unknown figure -> CANNOT_DETERMINE, never zero ──────────────────────
    d4 = assess(InvestmentFacts("CO", Money.crore(1), paid_up_capital=puc,
                                free_reserves=None, securities_premium=sp,
                                existing_aggregate=Money.crore(1)))
    check(d4.status == CANNOT_DETERMINE, "an unknown free-reserves figure refuses")
    check("free reserves" in d4.missing, "...and names the missing figure")

    # ── unknown existing aggregate -> refuse (ceiling known, total not) ─────
    d5 = assess(InvestmentFacts("CO", Money.crore(1), paid_up_capital=puc,
                                free_reserves=fr, securities_premium=sp,
                                existing_aggregate=None))
    check(d5.status == CANNOT_DETERMINE and d5.ceiling_rupees is not None,
          "a known ceiling but unknown aggregate still refuses")

    # ── proviso exemption: loan to a wholly-owned subsidiary ────────────────
    d6 = assess(InvestmentFacts("CO", Money.crore(100), to_wholly_owned_subsidiary=True))
    check(d6.status == EXEMPT, f"a loan to a WOS is EXEMPT regardless of size ({d6.status})")
    check(any("financial statement" in c for c in d6.conditions),
          "...but still names the s.186(4) disclosure condition")

    # ── an unknown exemption flag does not exempt ───────────────────────────
    d7 = assess(InvestmentFacts("CO", Money.crore(1.5), paid_up_capital=puc,
                                free_reserves=fr, securities_premium=sp,
                                existing_aggregate=Money.crore(1),
                                to_wholly_owned_subsidiary=None))
    check(d7.status == EXCEEDS_NEEDS_SPECIAL_RESOLUTION,
          "an unknown WOS flag does not exempt an over-limit transaction")

    # ── the layers limb is flagged as not modelled, never assumed satisfied ─
    check(any("two layers" in n for n in d.notes),
          "every determination notes the s.186(1) layers limb is not modelled")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
