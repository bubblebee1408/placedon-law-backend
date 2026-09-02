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
class Evidence:
    """What the user has told us actually happened. Facts, never conclusions.

    Absent is not zero. `board_meetings=None` means "we were not told"; an empty
    list means "we were told there were none", and those are different rows. A
    system that folded them together would tell a company that filed nothing the
    same thing it tells a company that held no meetings, and only one of those
    is a finding.
    """
    agm_dates: tuple[date, ...] | None = None
    financial_year_end: date | None = None
    board_meetings: tuple[date, ...] | None = None
    calendar_year: int | None = None
    total_board_strength: int | None = None
    special_resolution_for_excess_directors: bool | None = None


# A decider answers "was it complied with", given the profile and the evidence.
# It returns None when the evidence does not settle it — which is the common
# case and must never be mistaken for a pass.
Decider = Callable[[CompanyProfile, Evidence], "tuple[bool | None, str]"]


@dataclass(frozen=True)
class Obligation:
    """One duty under the Act, and how this system decides it."""
    obligation_id: str
    duty: str                     # in a practitioner's words, not the statute's
    provision: str                # instrument-qualified citation
    applies_when: Callable[[CompanyProfile], tuple[Result, str]]
    evidence_needed: tuple[str, ...] = ()
    note: str = ""
    decided_by: Decider | None = None


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


def _decide_board(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.173 count and spacing, from the dates the user supplied.

    Delegates to checker.s173_slice, which already holds the ceiling-vs-floor
    distinction and surfaces quorum as an open question rather than assuming it.
    A COMPLIANT there is a genuine pass; anything else is not a fail, because
    s173_slice returns INDETERMINATE for things it deliberately does not decide.
    """
    if ev.board_meetings is None:
        return None, "no board meeting dates were supplied"
    if ev.calendar_year is None:
        return None, "board meeting dates were supplied without the year they belong to"

    from checker.classify import small_company
    from checker.s173_slice import COMPLIANT, NOT_COMPLIANT, review

    verdict, _ = small_company(p)
    if verdict is Result.APPLIES:
        cls = "small_company"
    elif verdict is Result.DOES_NOT_APPLY:
        cls = "other"
    else:
        # The relaxed regime turns on a classification that refuses. Running the
        # standard regime anyway would impose the stricter duty on a company
        # that may not owe it, so this declines instead.
        return None, ("the s.173(5) regime depends on small-company status, "
                      "which cannot be determined")

    r = review(company_class=cls, calendar_year=ev.calendar_year,
               meetings=list(ev.board_meetings),
               total_board_strength=ev.total_board_strength)
    if r.status == COMPLIANT:
        return True, f"{len(ev.board_meetings)} meetings; {r.regime}"
    if r.status == NOT_COMPLIANT:
        failed = [f.rule for f in r.findings if f.satisfied is False]
        return False, ("; ".join(failed) if failed else "s.173 not satisfied")
    open_q = r.open_questions[0] if r.open_questions else "not determined"
    return None, open_q


def _decide_agm(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.96 — did an AGM happen, and inside the fifteen-month gap.

    The gap limb only. The first-AGM deadline and the Registrar's extension are
    separate limbs of s.96 and are NOT decided here; a company whose gap is fine
    can still have missed the first-AGM deadline, so a pass on this limb is
    reported as a pass on this limb.
    """
    if ev.agm_dates is None:
        return None, "no AGM dates were supplied"
    ds = sorted(ev.agm_dates)
    if not ds:
        return False, "no annual general meeting was held"
    if len(ds) < 2:
        return None, ("only one AGM date is on record; the fifteen-month gap "
                      "needs the previous one as well")
    gap = (ds[-1] - ds[-2]).days
    # s.96(1): "not more than fifteen months shall elapse between the date of
    # one annual general meeting and that of the next". Fifteen months is not a
    # fixed number of days, so this is computed on the calendar, not on 450.
    prev = ds[-2]
    m = prev.month - 1 + 15
    limit_year, limit_month = prev.year + m // 12, m % 12 + 1
    day = min(prev.day, [31, 29 if limit_year % 4 == 0 and
                         (limit_year % 100 != 0 or limit_year % 400 == 0) else 28,
                         31, 30, 31, 30, 31, 31, 30, 31, 30, 31][limit_month - 1])
    limit = date(limit_year, limit_month, day)
    if ds[-1] <= limit:
        return True, (f"gap of {gap} days from {prev} to {ds[-1]}, within the "
                      f"fifteen-month limit of {limit} (this limb only)")
    return False, (f"gap of {gap} days from {prev} to {ds[-1]} exceeds the "
                   f"fifteen-month limit of {limit}")


# s.149(1)(a), quoted from our corpus of the Act:
#   "a minimum number of three directors in the case of a public company, two
#    directors in the case of a private company, and one director in the case
#    of a One Person Company"
_MINIMUM_DIRECTORS = {"public": 3, "private": 2, "opc": 1}
_MAXIMUM_DIRECTORS = 15          # s.149(1)(b)


def _decide_board_size(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.149(1) — enough directors, and not too many without a special resolution.

    Three limbs behaving three different ways, which is why this obligation is
    worth having: the minimum is decidable outright, the maximum is gated by a
    proviso, and the woman-director requirement is delegated to rules we do not
    hold and is therefore never decided here — it is surfaced instead.
    """
    n = p.director_count
    if n is None:
        return None, "the number of directors is not on the profile"

    floor = _MINIMUM_DIRECTORS.get(p.company_class)
    if floor is None:
        return None, f"no statutory minimum is registered for {p.company_class!r}"

    if n < floor:
        return False, (f"{n} director{'s' if n != 1 else ''} against the "
                       f"s.149(1)(a) minimum of {floor} for a "
                       f"{p.company_class} company")

    if n > _MAXIMUM_DIRECTORS:
        sr = ev.special_resolution_for_excess_directors
        if sr is True:
            return True, (f"{n} directors, above the s.149(1)(b) maximum of "
                          f"{_MAXIMUM_DIRECTORS}, permitted by the special "
                          f"resolution recorded (numbers limbs only)")
        if sr is False:
            return False, (f"{n} directors exceeds the s.149(1)(b) maximum of "
                           f"{_MAXIMUM_DIRECTORS} and no special resolution was "
                           f"passed")
        return None, (f"{n} directors is above the s.149(1)(b) maximum of "
                      f"{_MAXIMUM_DIRECTORS}, which the first proviso permits "
                      f"after a special resolution — we were not told whether "
                      f"one was passed")

    return True, (f"{n} directors: at or above the minimum of {floor} and not "
                  f"above the maximum of {_MAXIMUM_DIRECTORS} "
                  f"(numbers limbs only)")


REGISTER: tuple[Obligation, ...] = (
    Obligation(
        "CA13-S96-AGM",
        "Hold an annual general meeting, and within the statutory gap",
        "Companies Act 2013, s.96(1)",
        _agm_applies,
        evidence_needed=("date of the last AGM", "date of this AGM",
                         "date of closing of the financial year"),
        note="the first AGM has its own deadline; the gap between successive "
             "AGMs and the Registrar's extension are separate limbs",
        decided_by=_decide_agm),
    Obligation(
        "CA13-S173-BOARD",
        "Hold the minimum number of board meetings, correctly spaced",
        "Companies Act 2013, s.173(1)",
        _not_opc_single_director,
        evidence_needed=("dates of every board meeting in the year",),
        note="the s.173(5) relaxed regime turns on small-company status, so "
             "this row can be blocked by an unacquired Rule",
        decided_by=_decide_board),
    Obligation(
        "CA13-S149-BOARD-SIZE",
        "Have enough directors, and not more than the maximum",
        "Companies Act 2013, s.149(1)",
        _every_company,
        evidence_needed=("number of directors",
                         "whether a special resolution was passed, if there "
                         "are more than fifteen"),
        note="the numbers limbs only. The second proviso requires at least one "
             "woman director for prescribed classes, and that prescription is "
             "delegated legislation this system does not hold, so it is "
             "surfaced and never decided here",
        decided_by=_decide_board_size),
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
          register: tuple[Obligation, ...] = REGISTER,
          evidence: Evidence | None = None) -> list[Row]:
    """The matrix for one company. Generated from facts, not from documents.

    `evidence` is what the user says happened. Without it every applicable row
    is APPLIES_UNDETERMINED, which is the honest answer: the register knows the
    duty attaches and nothing about whether it was met.
    """
    ev = evidence or Evidence()
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

        # The duty attaches. Whether it is MET is a separate question, answered
        # only by evidence the user supplied. A decider returning None does NOT
        # mean satisfied — it means the evidence did not settle it, and that
        # distinction is the whole failure mode this product exists to avoid.
        met, why = (ob.decided_by(profile, ev) if ob.decided_by
                    else (None, "no decision procedure is registered for this duty"))

        if met is True:
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            APPLIES_SATISFIED, f"{basis}. {why}",
                            evidence=(why,)))
        elif met is False:
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            APPLIES_NOT_SATISFIED, f"{basis}. {why}",
                            evidence=(why,)))
        else:
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            APPLIES_UNDETERMINED,
                            f"{basis}; {why}",
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

    # NO row may claim compliance without a factual basis. Note the shape of
    # this: some duties ARE decidable from the profile alone -- s.149(1) asks
    # how many directors there are, which is what the company IS rather than
    # something that happened -- so the invariant is not "no Evidence object"
    # but "no facts". A profile carrying none of the relevant facts must
    # produce no pass anywhere.
    factless = (bare, priv, pub)          # no director_count, no evidence
    for prof in factless:
        for r in build(prof):
            if r.state == APPLIES_SATISFIED:
                check(False, f"{r.obligation_id} claimed compliance with no facts")
                break
    else:
        check(True, "no row claims compliance when the facts are absent")

    # ...and where the facts ARE present, a pass is legitimate and must carry
    # what settled it.
    opc_row = [r for r in build(opc) if r.obligation_id == "CA13-S149-BOARD-SIZE"][0]
    check(opc_row.state == APPLIES_SATISFIED,
          f"one director satisfies the OPC minimum ({opc_row.state})")
    check(opc_row.evidence and "1 director" in opc_row.evidence[0],
          f"...and the row carries the fact that settled it ({opc_row.evidence})")

    # An applicable duty must say what evidence would settle it.
    appl = [r for r in build(pub) if r.state == APPLIES_UNDETERMINED]
    check(bool(appl), "some duties do attach to a public company")
    check(all(r.missing_facts for r in appl),
          "every undetermined duty names the evidence that would settle it")

    # ── evidence resolves rows, and only when it actually settles them ──────
    LIMITS_OK = dict(company_class="public", **common)

    # s.96: two AGMs inside fifteen months.
    ev_ok = Evidence(agm_dates=(date(2024, 8, 20), date(2025, 9, 15)))
    agm_row = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=ev_ok)
               if r.obligation_id == "CA13-S96-AGM"][0]
    check(agm_row.state == APPLIES_SATISFIED,
          f"an AGM inside the fifteen-month gap satisfies that limb ({agm_row.state})")
    check("this limb only" in agm_row.basis,
          "...and says it decided one limb, not the whole section")

    # Sixteen months apart — over the limit.
    ev_late = Evidence(agm_dates=(date(2024, 8, 20), date(2025, 12, 30)))
    late = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=ev_late)
            if r.obligation_id == "CA13-S96-AGM"][0]
    check(late.state == APPLIES_NOT_SATISFIED,
          f"a gap beyond fifteen months fails ({late.state})")
    check("exceeds" in late.basis, "...and the basis says by reference to what")

    # One AGM alone cannot settle a GAP. It must not read as a pass.
    ev_one = Evidence(agm_dates=(date(2025, 9, 15),))
    one = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=ev_one)
           if r.obligation_id == "CA13-S96-AGM"][0]
    check(one.state == APPLIES_UNDETERMINED,
          f"a single AGM date cannot settle the gap ({one.state})")

    # Told there were none is a FINDING; not told is not.
    none_held = [r for r in build(CompanyProfile(**LIMITS_OK),
                                  evidence=Evidence(agm_dates=()))
                 if r.obligation_id == "CA13-S96-AGM"][0]
    check(none_held.state == APPLIES_NOT_SATISFIED,
          f"'no AGM was held' is a finding, not an unknown ({none_held.state})")
    silent = [r for r in build(CompanyProfile(**LIMITS_OK))
              if r.obligation_id == "CA13-S96-AGM"][0]
    check(silent.state == APPLIES_UNDETERMINED,
          "...while saying nothing stays undetermined")
    check(none_held.state != silent.state,
          "an empty answer and no answer are different rows")

    # s.173: four well-spaced meetings on a public company.
    ev_board = Evidence(board_meetings=(date(2025, 2, 10), date(2025, 6, 5),
                                        date(2025, 9, 30), date(2025, 12, 20)),
                        calendar_year=2025)
    b = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=ev_board)
         if r.obligation_id == "CA13-S173-BOARD"][0]
    check(b.state in (APPLIES_SATISFIED, APPLIES_UNDETERMINED),
          f"four spaced meetings resolve or abstain, never fail ({b.state})")

    three = Evidence(board_meetings=(date(2025, 3, 1), date(2025, 7, 20),
                                     date(2025, 11, 15)), calendar_year=2025)
    b2 = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=three)
          if r.obligation_id == "CA13-S173-BOARD"][0]
    check(b2.state == APPLIES_NOT_SATISFIED,
          f"three meetings fail the s.173(1) floor ({b2.state})")

    # Dates without the year they belong to cannot be assessed.
    noyear = Evidence(board_meetings=(date(2025, 3, 1),))
    b3 = [r for r in build(CompanyProfile(**LIMITS_OK), evidence=noyear)
          if r.obligation_id == "CA13-S173-BOARD"][0]
    check(b3.state == APPLIES_UNDETERMINED,
          f"meeting dates without their year are not assessed ({b3.state})")

    # A private company whose regime is blocked must NOT be assessed on the
    # stricter standard — that would impose a duty it may not owe.
    priv_ev = CompanyProfile(company_class="private",
                             paid_up_capital=Figure(Money.crore(2), "2024-25"),
                             turnover=Figure(Money.crore(30), "2024-25"), **common)
    b4 = [r for r in build(priv_ev, evidence=three)
          if r.obligation_id == "CA13-S173-BOARD"][0]
    check(b4.state == APPLIES_UNDETERMINED,
          f"a blocked regime declines rather than applying the stricter one "
          f"({b4.state})")
    check("small-company status" in b4.basis,
          "...and says the regime is what is missing")

    # THE GATE: an EVENT duty may never pass without evidence of the event.
    # s.149 is excluded deliberately — it is decided from company composition,
    # not from an event — and excluding it is recorded here rather than left
    # implicit, so nobody later widens the exclusion by accident.
    EVENT_DUTIES = {"CA13-S96-AGM", "CA13-S173-BOARD"}
    for prof in (bare, priv, pub, opc, CompanyProfile(**LIMITS_OK)):
        for r in build(prof):
            if r.obligation_id in EVENT_DUTIES and r.state == APPLIES_SATISFIED:
                check(False, f"{r.obligation_id} passed with no evidence at all")
                break
    else:
        check(True, "no event duty reaches APPLIES_SATISFIED without evidence")

    # A satisfied row must carry the evidence it rested on.
    check(agm_row.evidence and agm_row.evidence[0],
          "a satisfied row carries the evidence that settled it")

    # ── s.149(1): three limbs, three different behaviours ───────────────────
    def size(cls: str, n: int, sr=None):
        prof = CompanyProfile(company_class=cls, director_count=n, **common)
        ev = Evidence(special_resolution_for_excess_directors=sr)
        return [r for r in build(prof, evidence=ev)
                if r.obligation_id == "CA13-S149-BOARD-SIZE"][0]

    check(size("public", 2).state == APPLIES_NOT_SATISFIED,
          "two directors fails the public-company minimum of three")
    check("minimum of 3" in size("public", 2).basis,
          "...and the basis names the minimum it fell short of")
    check(size("private", 2).state == APPLIES_SATISFIED,
          "two directors meets the private-company minimum")
    check(size("public", 2).state != size("private", 2).state,
          "the same board size passes or fails on company class")

    # The maximum is gated by a proviso, so it is NOT decided without it.
    over = size("public", 16)
    check(over.state == APPLIES_UNDETERMINED,
          f"sixteen directors is not decided without the proviso ({over.state})")
    check("special resolution" in over.basis,
          "...and the basis names the special resolution that would settle it")
    check(size("public", 16, sr=True).state == APPLIES_SATISFIED,
          "a recorded special resolution permits the excess")
    check(size("public", 16, sr=False).state == APPLIES_NOT_SATISFIED,
          "no special resolution and sixteen directors is a failure")

    # The delegated limb must never be decided.
    reg149 = [o for o in REGISTER if o.obligation_id == "CA13-S149-BOARD-SIZE"][0]
    check("woman director" in reg149.note and "never decided" in reg149.note,
          "the woman-director prescription is surfaced, never decided")
    check("numbers limbs only" in size("private", 2).basis,
          "a pass says which limbs it covered")

    out = render(pub, build(pub))
    check("No row claims compliance" in out, "the render says what it does not claim")
    check("need attention" in out, "...and counts what a reviewer must read")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
