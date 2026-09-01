"""The obligation register — rows generated from a company, not from documents.

This is the inversion the whole product rests on, and it is worth stating
before the code:

    In tabular contract review a row is A DOCUMENT YOU HAVE.
    In a compliance matrix a row is AN OBLIGATION THE LAW IMPOSES.

The consequence is that the most valuable rows are the ones with NO document
behind them. A company that has held no board meeting all year still gets a
row saying so, and that row is the one a director needs. A document-mass
architecture cannot generate it: a corpus can only be asked about what is in
it. This register is generated from a `CompanyProfile` alone, so a company that
has uploaded nothing still gets a complete matrix.

## Every row is one of five things, and they are not interchangeable

    APPLIES_SATISFIED       the duty attaches and the evidence shows it met
    APPLIES_NOT_SATISFIED   the duty attaches and the evidence shows it unmet
    APPLIES_UNDETERMINED    the duty attaches; we cannot say whether it is met
    DOES_NOT_APPLY          the duty does not attach to this company
    CANNOT_DETERMINE        we cannot say whether the duty even attaches

The last two are the ones a careless system collapses. "This does not apply to
you" and "I cannot tell whether this applies to you" are different sentences,
and only one of them is safe to act on. `applicability.Result` already keeps
INSUFFICIENT_DATA distinct from DOES_NOT_APPLY; this module keeps that
distinction all the way to the row.

## No obligation states its own threshold

An obligation names its provision and the checker that answers it. Amounts and
dates come from `prescribed_thresholds`, which refuses what it has not
acquired. So a register row can be blocked by a missing Rule, and it says which
one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from applicability import Result
from checker.company_profile import CompanyProfile

# Row states. Deliberately five, not three.
APPLIES_SATISFIED = "APPLIES_SATISFIED"
APPLIES_NOT_SATISFIED = "APPLIES_NOT_SATISFIED"
APPLIES_UNDETERMINED = "APPLIES_UNDETERMINED"
DOES_NOT_APPLY = "DOES_NOT_APPLY"
CANNOT_DETERMINE = "CANNOT_DETERMINE"

ROW_STATES = (APPLIES_SATISFIED, APPLIES_NOT_SATISFIED, APPLIES_UNDETERMINED,
              DOES_NOT_APPLY, CANNOT_DETERMINE)

# States in which a reviewer must look. A row nobody has to read is a row that
# can be wrong quietly.
NEEDS_ATTENTION = (APPLIES_NOT_SATISFIED, APPLIES_UNDETERMINED, CANNOT_DETERMINE)


@dataclass(frozen=True)
class Obligation:
    """One duty under the Act, and how this system decides it."""
    obligation_id: str
    duty: str                     # in a practitioner's words, not the statute's
    provision: str                # instrument-qualified citation
    applies_when: Callable[[CompanyProfile], tuple[Result, str]]
    evidence_needed: tuple[str, ...] = ()
    note: str = ""


@dataclass
class Row:
    """One obligation against one company at one date."""
    obligation_id: str
    duty: str
    provision: str
    state: str
    basis: str                            # why the row says what it says
    missing_facts: tuple[str, ...] = ()
    blocked_by: str = ""                  # a task id, where a source is missing
    evidence: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_attention(self) -> bool:
        return self.state in NEEDS_ATTENTION


def _small_company(p: CompanyProfile) -> tuple[Result, str]:
    from checker.classify import small_company
    verdict, trace = small_company(p)
    return verdict, trace.detail


def _every_company(p: CompanyProfile) -> tuple[Result, str]:
    return Result.APPLIES, "applies to every company registered under the Act"


def _not_opc_single_director(p: CompanyProfile) -> tuple[Result, str]:
    # s.173(5) proviso disapplies s.173 for a one-person company with a single
    # director. We do not hold director counts for every profile, so this
    # refuses rather than assuming a board exists.
    if p.company_class != "opc":
        return Result.APPLIES, "not a one-person company, so s.173 applies in full"
    if p.director_count is None:
        return (Result.INSUFFICIENT_DATA,
                "a one-person company with only one director is outside s.173; "
                "the director count is not on the profile")
    if p.director_count == 1:
        return Result.DOES_NOT_APPLY, "one-person company with a single director"
    return Result.APPLIES, "one-person company with more than one director"


def _agm_applies(p: CompanyProfile) -> tuple[Result, str]:
    # s.96(1) opens "Every company other than a One Person Company".
    if p.company_class == "opc":
        return Result.DOES_NOT_APPLY, "s.96(1) excludes a One Person Company"
    return Result.APPLIES, "s.96(1) reaches every company other than an OPC"


REGISTER: tuple[Obligation, ...] = (
    Obligation(
        "CA13-S96-AGM",
        "Hold an annual general meeting, and within the statutory gap",
        "Companies Act 2013, s.96(1)",
        _agm_applies,
        evidence_needed=("date of the last AGM", "date of this AGM",
                         "date of closing of the financial year"),
        note="the first AGM has its own deadline; the gap between successive "
             "AGMs and the Registrar's extension are separate limbs"),
    Obligation(
        "CA13-S173-BOARD",
        "Hold the minimum number of board meetings, correctly spaced",
        "Companies Act 2013, s.173(1)",
        _not_opc_single_director,
        evidence_needed=("dates of every board meeting in the year",),
        note="the s.173(5) relaxed regime turns on small-company status, so "
             "this row can be blocked by an unacquired Rule"),
    Obligation(
        "CA13-S2-85-SMALL",
        "Establish whether the company is a small company",
        "Companies Act 2013, s.2(85)",
        _small_company,
        evidence_needed=("paid-up share capital", "turnover for the "
                         "immediately preceding financial year",
                         "holding or subsidiary status"),
        note="a classification, not a duty — but it gates the regime of "
             "several duties, so it earns a row"),
)


def build(profile: CompanyProfile,
          register: tuple[Obligation, ...] = REGISTER) -> list[Row]:
    """The matrix for one company. Generated from facts, not from documents."""
    rows: list[Row] = []
    for ob in register:
        verdict, basis = ob.applies_when(profile)

        if verdict is Result.DOES_NOT_APPLY:
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            DOES_NOT_APPLY, basis))
            continue

        if verdict is Result.INSUFFICIENT_DATA:
            blocked = "S-002" if "servable" in basis or "S-002" in basis else ""
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            CANNOT_DETERMINE, basis,
                            missing_facts=tuple(profile.unknowns()),
                            blocked_by=blocked))
            continue

        # The duty attaches. Whether it is MET is a separate question, and this
        # register does not hold the meeting dates or notices that would answer
        # it — the slices do. Saying APPLIES_SATISFIED here without that
        # evidence would be the whole failure mode this product exists to avoid.
        rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                        APPLIES_UNDETERMINED,
                        f"{basis}; whether it was complied with is not "
                        f"determined by the register alone",
                        missing_facts=ob.evidence_needed))
    return rows


def render(profile: CompanyProfile, rows: list[Row]) -> str:
    L = ["=" * 74,
         "COMPLIANCE MATRIX — generated from company facts, not from documents",
         "=" * 74,
         f"  company class : {profile.company_class}",
         f"  as of         : {profile.as_of}",
         f"  financial year: {profile.latest_financial_year or 'not set'}",
         ""]
    for r in rows:
        flag = "!" if r.needs_attention else " "
        L.append(f" {flag} {r.obligation_id}")
        L.append(f"     duty      : {r.duty}")
        L.append(f"     provision : {r.provision}")
        L.append(f"     state     : {r.state}")
        L.append(f"     basis     : {r.basis[:150]}")
        if r.missing_facts:
            L.append(f"     needs     : {', '.join(r.missing_facts[:4])}")
        if r.blocked_by:
            L.append(f"     BLOCKED   : {r.blocked_by}")
        L.append("")
    n = sum(1 for r in rows if r.needs_attention)
    L += [f"  {n} of {len(rows)} rows need attention.",
          "  No row claims compliance. Establishing that a duty was MET needs",
          "  the documents, and that is the workflow, not the register.",
          "=" * 74]
    return "\n".join(L)


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

    print("obligations")
    from checker.company_profile import Figure, Money

    common = dict(incorporation_date=date(2019, 6, 1), as_of=date(2026, 8, 31),
                  latest_financial_year="2024-25", is_holding_company=False,
                  is_subsidiary_company=False, is_section_8=False,
                  governed_by_special_act=False)

    # A company that has uploaded nothing still gets a full matrix. This is the
    # inversion: rows come from the law, not from a corpus.
    bare = CompanyProfile(company_class="private", **common)
    rows = build(bare)
    check(len(rows) == len(REGISTER),
          f"a company with no documents still gets every row ({len(rows)})")
    check(all(r.provision for r in rows), "every row carries its provision")
    check(all(r.state in ROW_STATES for r in rows), "every row state is known")
    check(all(r.basis for r in rows), "every row says why")

    # DOES_NOT_APPLY and CANNOT_DETERMINE must never collapse into each other.
    opc = CompanyProfile(company_class="opc", director_count=1, **common)
    agm = [r for r in build(opc) if r.obligation_id == "CA13-S96-AGM"][0]
    check(agm.state == DOES_NOT_APPLY,
          f"an OPC is definitively outside s.96 ({agm.state})")
    check(not agm.needs_attention, "...and a definitive exclusion needs no attention")

    board = [r for r in build(opc) if r.obligation_id == "CA13-S173-BOARD"][0]
    check(board.state == DOES_NOT_APPLY,
          f"a single-director OPC is outside s.173 ({board.state})")

    opc_unknown = CompanyProfile(company_class="opc", **common)   # no director count
    b2 = [r for r in build(opc_unknown) if r.obligation_id == "CA13-S173-BOARD"][0]
    check(b2.state == CANNOT_DETERMINE,
          f"an OPC with unknown director count cannot be decided ({b2.state})")
    check(b2.needs_attention, "...and that row needs attention")
    check(b2.state != DOES_NOT_APPLY,
          "'cannot tell if it applies' never becomes 'does not apply'")

    # A blocked source must be named on the row, not hidden in a basis string.
    priv = CompanyProfile(company_class="private",
                          paid_up_capital=Figure(Money.crore(2), "2024-25"),
                          turnover=Figure(Money.crore(30), "2024-25"), **common)
    small = [r for r in build(priv) if r.obligation_id == "CA13-S2-85-SMALL"][0]
    check(small.state == CANNOT_DETERMINE,
          f"small-company status refuses while the Rule is unacquired ({small.state})")
    check(small.blocked_by == "S-002",
          f"...and the row names the blocking task ({small.blocked_by!r})")

    # A public company resolves without any threshold.
    pub = CompanyProfile(company_class="public", **common)
    s2 = [r for r in build(pub) if r.obligation_id == "CA13-S2-85-SMALL"][0]
    check(s2.state == DOES_NOT_APPLY,
          f"a public company is definitively not small ({s2.state})")
    check(not s2.blocked_by, "...and is not blocked on the unacquired Rule")

    # NO row may claim compliance. The register does not hold the evidence.
    for prof in (bare, priv, pub, opc):
        for r in build(prof):
            if r.state == APPLIES_SATISFIED:
                check(False, f"{r.obligation_id} claimed compliance without evidence")
                break
    else:
        check(True, "no row claims compliance — the register holds no evidence")

    # An applicable duty must say what evidence would settle it.
    appl = [r for r in build(pub) if r.state == APPLIES_UNDETERMINED]
    check(bool(appl), "some duties do attach to a public company")
    check(all(r.missing_facts for r in appl),
          "every undetermined duty names the evidence that would settle it")

    out = render(pub, build(pub))
    check("No row claims compliance" in out, "the render says what it does not claim")
    check("need attention" in out, "...and counts what a reviewer must read")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
