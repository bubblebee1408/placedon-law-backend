"""The company facts a Companies Act obligation is decided against.

The existing `CompanyProfile` in applicability.py is labour-law shaped —
employee_count, establishment_type, ESI wage ceilings, hazardous process. None
of it decides a Companies Act question. This is the corporate profile.

It holds **facts only**. No statutory threshold appears in this file, and that is
a deliberate line: a threshold is dated law that changes by amendment and by
delegated rule, so it belongs in a sourced rule table, not baked into a schema.
A profile that knew the thresholds would silently keep answering with last
year's law.

## Unknown is a value, not a zero

Every field may be None, and None means "we were not told". applicability.evaluate
already maps a None field to INSUFFICIENT_DATA with a trace naming the field, so
an unknown turnover produces "need this to decide" rather than a quiet
DOES_NOT_APPLY. Nothing here may default a missing figure to 0: for a threshold
of the form "does not exceed X", zero is the strongest possible pass, so
defaulting an unknown to zero converts ignorance into a favourable answer.

## Money is whole rupees, and it says what it is worth

Indian thresholds are quoted in lakhs and crores while figures arrive in rupees,
and the mis-scaling is silent — ₹4 crore entered as "4" passes every "does not
exceed" test ever written. `Money` stores whole rupees as an int and offers
`lakh()` and `crore()` constructors so the unit is stated at the point of entry
rather than assumed at the point of comparison.

## A figure without its financial year is not a figure

s.2(85)(ii) does not ask for turnover. It asks for turnover "as per profit and
loss account for the **immediately preceding financial year**" — text quoted from
our own corpus, not from memory. A turnover carried without the year it belongs
to cannot answer that question, so `Figure` binds the amount to its financial
year and a comparison against the wrong year is refused rather than computed.

## Derived status is computed, never stored

There is no `is_small_company` field. Small-company status is a function of
capital, turnover, company class and three exclusions, every one of which can be
unknown — and a stored flag drifts from its inputs the moment one changes.
Classification lives in `classify.py` and returns a Result with a trace.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields
from datetime import date
from typing import Any, Literal

# Company classes that change which obligations attach at all.
CompanyClass = Literal["private", "public", "opc"]

# A financial year in the Indian form, e.g. "2024-25". s.2(41) fixes the year as
# ending 31 March, with a longer first year for companies incorporated on or
# after 1 January — so a financial year is not derivable from a date alone and is
# carried explicitly.
FinancialYear = str


@dataclass(frozen=True)
class Money:
    """A rupee amount. Whole rupees only — never lakhs, never crores."""
    rupees: int

    def __post_init__(self) -> None:
        if not isinstance(self.rupees, int) or isinstance(self.rupees, bool):
            raise TypeError(f"Money takes whole rupees as an int, got "
                            f"{type(self.rupees).__name__}")
        if self.rupees < 0:
            raise ValueError("a negative rupee amount is not a figure this decides on")

    @classmethod
    def lakh(cls, n: float) -> "Money":
        return cls(int(round(n * 100_000)))

    @classmethod
    def crore(cls, n: float) -> "Money":
        return cls(int(round(n * 10_000_000)))

    def __str__(self) -> str:
        if self.rupees >= 10_000_000:
            return f"₹{self.rupees / 10_000_000:g} crore"
        if self.rupees >= 100_000:
            return f"₹{self.rupees / 100_000:g} lakh"
        return f"₹{self.rupees:,}"


@dataclass(frozen=True)
class Figure:
    """An amount bound to the financial year it speaks to."""
    amount: Money
    financial_year: FinancialYear

    def __str__(self) -> str:
        return f"{self.amount} (FY {self.financial_year})"


class FigureYearError(ValueError):
    """A figure was compared against a year it does not speak to."""


@dataclass(frozen=True)
class CompanyProfile:
    """Aggregate corporate facts. No person-level data — nothing here is PII.

    Every field beyond the four that identify the company may be None, and None
    means unknown. See the module docstring: unknown is never treated as zero.
    """
    # ── what the company is ─────────────────────────────────────────────────
    company_class: CompanyClass
    incorporation_date: date
    as_of: date                                   # the date this profile speaks to
    cin: str | None = None

    # ── status flags that switch whole obligation sets on or off ────────────
    is_listed: bool | None = None
    is_section_8: bool | None = None               # s.2(85) proviso (B)
    is_government_company: bool | None = None
    is_nidhi: bool | None = None
    is_producer_company: bool | None = None
    governed_by_special_act: bool | None = None    # s.2(85) proviso (C)
    is_holding_company: bool | None = None         # s.2(85) proviso (A)
    is_subsidiary_company: bool | None = None      # s.2(85) proviso (A)
    is_dormant: bool | None = None                 # s.455 — conferred by the ROC

    # ── figures, each bound to its financial year ───────────────────────────
    paid_up_capital: Figure | None = None
    turnover: Figure | None = None                 # s.2(85)(ii): preceding FY
    net_worth: Figure | None = None
    borrowings: Figure | None = None
    deposits_accepted: Figure | None = None

    # ── counts ──────────────────────────────────────────────────────────────
    member_count: int | None = None
    director_count: int | None = None
    independent_director_count: int | None = None
    women_director_count: int | None = None

    # ── the year the figures above are stated for ───────────────────────────
    latest_financial_year: FinancialYear | None = None

    notes: tuple[str, ...] = field(default_factory=tuple)

    # ── evaluator interface ─────────────────────────────────────────────────
    def get(self, name: str) -> Any:
        """Field access for applicability.evaluate.

        A Figure is returned as its rupee amount so a numeric comparator works
        on it, but ONLY through `amount_for()`, which checks the year. Returning
        a bare Figure here would let a comparator compare a dataclass to an int
        and raise deep inside the evaluator.
        """
        v = getattr(self, name, None)
        if isinstance(v, Figure):
            return v.amount.rupees
        if isinstance(v, Money):
            return v.rupees
        return v

    def amount_for(self, name: str, financial_year: FinancialYear) -> int | None:
        """A figure's rupee amount, refusing if it speaks to a different year."""
        v = getattr(self, name, None)
        if v is None:
            return None
        if not isinstance(v, Figure):
            raise TypeError(f"{name!r} is not a Figure")
        if v.financial_year != financial_year:
            raise FigureYearError(
                f"{name} is stated for FY {v.financial_year}, but the test asks "
                f"for FY {financial_year} — a figure from the wrong year cannot "
                f"answer this")
        return v.amount.rupees

    def unknowns(self) -> tuple[str, ...]:
        """Fields we were not told. What a reviewer must supply to get further."""
        return tuple(f.name for f in dc_fields(self)
                     if f.name != "notes" and getattr(self, f.name) is None)

    def known(self, *names: str) -> bool:
        return all(getattr(self, n, None) is not None for n in names)


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

    print("company_profile")

    # ── Money states its unit at entry ──────────────────────────────────────
    check(Money.crore(4).rupees == 40_000_000, "4 crore is 40,000,000 rupees")
    check(Money.lakh(50).rupees == 5_000_000, "50 lakh is 5,000,000 rupees")
    check(str(Money.crore(4)) == "₹4 crore", f"crore renders back ({Money.crore(4)})")
    check(str(Money.lakh(50)) == "₹50 lakh", f"lakh renders back ({Money.lakh(50)})")
    check(Money.crore(4).rupees != 4,
          "the scaling bug this exists to prevent: 4 crore is not 4")

    try:
        Money(4.0)  # type: ignore[arg-type]
        check(False, "a float rupee amount is refused")
    except TypeError:
        check(True, "a float rupee amount is refused, not silently truncated")
    try:
        Money(True)  # type: ignore[arg-type]
        check(False, "a bool is refused as an amount")
    except TypeError:
        check(True, "a bool is refused as an amount")

    p = CompanyProfile(
        company_class="private",
        incorporation_date=date(2019, 6, 1),
        as_of=date(2026, 8, 31),
        paid_up_capital=Figure(Money.crore(2), "2024-25"),
        turnover=Figure(Money.crore(30), "2024-25"),
        latest_financial_year="2024-25",
    )

    # ── unknown is unknown, never zero ──────────────────────────────────────
    check(p.net_worth is None, "an unsupplied figure is None")
    check(p.get("net_worth") is None, "...and reads as None, not 0")
    check("net_worth" in p.unknowns(), "...and is listed as an unknown")
    check("paid_up_capital" not in p.unknowns(), "a supplied figure is not unknown")

    # The evaluator must see INSUFFICIENT_DATA, not a false negative.
    from applicability import evaluate, Result
    res, tr = evaluate({"op": "lte", "field": "net_worth", "value": 1}, p)
    check(res is Result.INSUFFICIENT_DATA,
          f"an unknown figure yields INSUFFICIENT_DATA ({res})")
    check("net_worth" in tr.detail, f"...naming the field ({tr.detail})")

    # A known figure compares on rupees.
    res2, tr2 = evaluate({"op": "lte", "field": "paid_up_capital",
                          "value": Money.crore(4).rupees}, p)
    check(res2 is Result.APPLIES,
          f"₹2 crore is within a ₹4 crore ceiling ({res2})")

    # Had the ceiling been written as the number 4, the test would invert.
    res3, _ = evaluate({"op": "lte", "field": "paid_up_capital", "value": 4}, p)
    check(res3 is Result.DOES_NOT_APPLY,
          "a ceiling written as '4' fails — which is why Money exists")

    # ── a figure must speak to the year the test asks about ─────────────────
    check(p.amount_for("turnover", "2024-25") == 300_000_000,
          "turnover reads for its own financial year")
    try:
        p.amount_for("turnover", "2023-24")
        check(False, "a figure from the wrong year is refused")
    except FigureYearError as e:
        check("wrong year" in str(e) or "cannot answer" in str(e),
              "a figure from the wrong year is refused, not compared")
    check(p.amount_for("net_worth", "2024-25") is None,
          "an unknown figure returns None rather than raising")

    # ── no threshold lives in this module ───────────────────────────────────
    import inspect
    src = inspect.getsource(CompanyProfile)
    for banned in ("50_00_000", "5_000_000", "40_000_000", "10_000_000",
                   "2_00_00_000"):
        if banned in src:
            check(False, f"a statutory threshold leaked into the schema ({banned})")
            break
    else:
        check(True, "no statutory threshold appears in the profile schema")

    check(not any(f.name == "is_small_company" for f in dc_fields(CompanyProfile)),
          "there is no stored is_small_company flag to drift from its inputs")

    # ── no person-level data ────────────────────────────────────────────────
    names = {f.name for f in dc_fields(CompanyProfile)}
    personal = {"director_names", "member_names", "email", "phone", "address",
                "pan", "aadhaar", "din"}
    check(not (names & personal),
          f"the profile carries no person-level field ({names & personal})")

    # ── the exclusions s.2(85) names all have a home ─────────────────────────
    for f in ("is_holding_company", "is_subsidiary_company", "is_section_8",
              "governed_by_special_act"):
        if f not in names:
            check(False, f"s.2(85) proviso field missing: {f}")
            break
    else:
        check(True, "every s.2(85) proviso exclusion has a field")

    check(p.known("paid_up_capital", "turnover"), "known() reports supplied facts")
    check(not p.known("paid_up_capital", "net_worth"),
          "...and is false when any is missing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
