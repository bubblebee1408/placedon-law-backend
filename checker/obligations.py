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
from datetime import date, timedelta
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
    first_financial_year_end: date | None = None   # s.96(1) first proviso
    aoc4_filed_on: date | None = None              # s.137(1)
    annual_return_filed_on: date | None = None     # s.92(4)
    resident_director_days: int | None = None      # s.149(3): max days-in-India
                                                   # among the directors, this FY
    incorporated_this_financial_year: bool | None = None  # s.149(3) proviso


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
    # Limbs of the provision this system does NOT decide. A duty with any
    # undecided limb can never render APPLIES_SATISFIED, because a partial pass
    # under a green badge reads as a full pass -- which is how a tool tells a
    # director their year is fine when it is not.
    limbs_not_decided: tuple[str, ...] = ()


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


# s.135(1) thresholds, verbatim from our corpus: "net worth of rupees five
# hundred crore or more, or turnover of rupees one thousand crore or more or a
# net profit of rupees five crore or more during the immediately preceding
# financial year". Held here as amounts because they are stated in the Act
# itself, not delegated to a rule -- the first threshold obligation this system
# can decide today, and the reason it is not blocked like s.203 or s.177.
from checker.company_profile import Money as _Money
_CSR_TESTS = (("net_worth", _Money.crore(500)),
              ("turnover", _Money.crore(1000)),
              ("net_profit", _Money.crore(5)))


def _csr_applies(p: CompanyProfile) -> tuple[Result, str]:
    """s.135(1): the CSR committee duty attaches on ANY of three thresholds.

    The disjunction governs how an unknown is handled, and it is the opposite of
    a conjunction. One threshold met -> APPLIES, whatever else is unknown. But if
    none of the KNOWN figures reaches its threshold and ANY figure is unknown,
    we cannot say the duty does not apply -- an unknown could be the one that
    crosses. Only when every figure is known and all are below does it not apply.
    """
    met, unknown = [], []
    for field_name, limit in _CSR_TESTS:
        fig = getattr(p, field_name, None)
        if fig is None:
            unknown.append(field_name)
            continue
        # Each threshold reads the immediately preceding financial year; the
        # figure carries its own year and amount_for would refuse a mismatch,
        # but applicability here only needs the amount, so read it directly.
        amount = fig.amount.rupees
        if amount >= limit.rupees:
            met.append(f"{field_name.replace('_', ' ')} {fig.amount} reaches {limit}")
    if met:
        return Result.APPLIES, "; ".join(met)
    if unknown:
        return (Result.INSUFFICIENT_DATA,
                f"no known figure reaches its s.135(1) threshold, but "
                f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} "
                f"unknown -- any one could cross, so applicability cannot be ruled out")
    return (Result.DOES_NOT_APPLY,
            "net worth, turnover and net profit are all below the s.135(1) "
            "thresholds of Rs 500 crore, Rs 1000 crore and Rs 5 crore")


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


def _add_months(d: date, months: int) -> date:
    """d plus n calendar months. Statutory periods are months, not day counts."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    last = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


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

    # s.96(1) requires an AGM "in each year". Two meetings can sit inside the
    # fifteen-month gap and still skip a calendar year entirely -- 31-12-2023 to
    # 31-01-2025 is 397 days and holds no AGM in 2024 at all. Checking the gap
    # alone reported that as compliant.
    years = {d.year for d in ds}
    span = range(min(years), max(years) + 1)
    missed = [y for y in span if y not in years]
    if missed:
        return False, (f"no annual general meeting was held in "
                       f"{', '.join(str(y) for y in missed)}; s.96(1) requires "
                       f"one in each year")

    # s.96(1) first proviso, verbatim from our corpus: the first AGM "shall be
    # held within a period of nine months from the date of closing of the first
    # financial year", and "in any other case, within a period of six months,
    # from the date of closing of the financial year".
    fy_end = ev.financial_year_end
    first_end = ev.first_financial_year_end
    latest = ds[-1]
    is_first = len(ds) == 1 and first_end is not None

    # Every limb is evaluated before anything is returned. A limb that cannot be
    # decided must not short-circuit one that can: a company whose gap plainly
    # exceeds fifteen months has failed s.96 whether or not we know its
    # financial year end, and an earlier version returned UNDETERMINED there.
    undecided: list[str] = []

    if is_first:
        limit = _add_months(first_end, 9)
        if latest > limit:
            return False, (f"the first annual general meeting was held on "
                           f"{latest}, past the nine-month limit of {limit} "
                           f"from the close of the first financial year")
    elif fy_end is not None:
        limit = _add_months(fy_end, 6)
        if latest > limit:
            return False, (f"the annual general meeting was held on {latest}, "
                           f"past the six-month limit of {limit} from the close "
                           f"of the financial year")
    else:
        undecided.append("the six-month deadline, which runs from the close of "
                         "the financial year and was not supplied")

    if len(ds) < 2:
        note = ("only one AGM date is on record; the fifteen-month gap needs "
                "the previous one as well")
        return None, (f"{note}; also {'; '.join(undecided)}" if undecided else note)
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
        passed = (f"gap of {gap} days from {prev} to {ds[-1]}, within the "
                  f"fifteen-month limit of {limit}")
        if undecided:
            return None, f"{passed}; but {'; '.join(undecided)}"
        return True, passed
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


def _decide_aoc4(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.137(1) — financial statements filed "within thirty days of the date of
    annual general meeting". Thirty days, not a month: the section says days."""
    if not ev.agm_dates:
        return None, "the thirty days run from the AGM, and no AGM date was given"
    agm = sorted(ev.agm_dates)[-1]
    due = agm + timedelta(days=30)
    if ev.aoc4_filed_on is None:
        return None, (f"the filing was due by {due} (thirty days from the AGM on "
                      f"{agm}); we were not told whether it was filed")
    if ev.aoc4_filed_on <= due:
        return True, (f"filed {ev.aoc4_filed_on}, within thirty days of the AGM "
                      f"on {agm} (due {due})")
    late = (ev.aoc4_filed_on - due).days
    return False, (f"filed {ev.aoc4_filed_on}, {late} day{'s' if late != 1 else ''} "
                   f"after the thirty-day limit of {due}")


def _decide_annual_return(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.92(4) — annual return within sixty days of the AGM, "or where no annual
    general meeting is held in any year within sixty days from the date on which
    the annual general meeting should have been held".

    That second limb is the one a company in default most needs and most often
    misses: missing the AGM does not postpone the return, it starts the clock
    from the date the AGM was due. It is only computable when the financial year
    end is known, so it refuses rather than assuming one.
    """
    if ev.agm_dates:
        agm = sorted(ev.agm_dates)[-1]
        due = agm + timedelta(days=60)
        basis = f"sixty days from the AGM on {agm}"
    elif ev.agm_dates is not None and ev.financial_year_end is not None:
        # Told there was none. The clock runs from when it should have been held.
        should = _add_months(ev.financial_year_end, 6)
        due = should + timedelta(days=60)
        basis = (f"no AGM was held, so s.92(4) runs sixty days from {should}, "
                 f"the date it should have been held")
    else:
        return None, ("the sixty days run from the AGM, or from the date one "
                      "should have been held; neither is established")

    if ev.annual_return_filed_on is None:
        return None, f"the annual return was due by {due} ({basis}); we were " \
                     f"not told whether it was filed"
    if ev.annual_return_filed_on <= due:
        return True, f"filed {ev.annual_return_filed_on}, within {basis} (due {due})"
    late = (ev.annual_return_filed_on - due).days
    return False, (f"filed {ev.annual_return_filed_on}, {late} day"
                   f"{'s' if late != 1 else ''} after the limit of {due} ({basis})")


def _decide_resident_director(p: CompanyProfile, ev: Evidence) -> tuple[bool | None, str]:
    """s.149(3), verbatim from our corpus: "Every company shall have at least
    one director who stays in India for a total period of not less than one
    hundred and eighty-two days during the financial year".

    The proviso is not silently dropped: "in case of a newly incorporated
    company the requirement ... shall apply proportionately at the end of the
    financial year in which it is incorporated". A day count against a flat 182
    is the wrong test for a company that did not exist for the whole year, so
    this refuses rather than applying the full-year figure to a part year.
    """
    days = ev.resident_director_days
    if days is None:
        return None, ("no director's days-in-India were supplied; s.149(3) needs "
                      "at least one director present 182 days in the year")
    if ev.incorporated_this_financial_year is True:
        return None, (f"the most-present director was in India {days} days, but "
                      f"this company was incorporated during the financial year, "
                      f"so s.149(3)'s proviso applies the requirement "
                      f"PROPORTIONATELY -- a flat 182-day test would be wrong and "
                      f"the proportionate figure is not computed here")
    if days >= 182:
        return True, (f"a director was resident in India {days} days, at or above "
                      f"the 182-day minimum")
    return False, (f"the most-present director was in India {days} days, short of "
                   f"the 182-day minimum in s.149(3)")


REGISTER: tuple[Obligation, ...] = (
    Obligation(
        "CA13-S96-AGM",
        "Hold an annual general meeting, and within the statutory gap",
        "Companies Act 2013, s.96(1)",
        _agm_applies,
        evidence_needed=("date of the last AGM", "date of this AGM",
                         "date of closing of the financial year",
                         "date of closing of the first financial year, for a "
                         "company holding its first AGM"),
        note="the first AGM has its own deadline; the gap between successive "
             "AGMs and the Registrar's extension are separate limbs",
        decided_by=_decide_agm,
        limbs_not_decided=(
            "any extension of up to three months granted by the Registrar under "
            "the third proviso, which we cannot see",)),
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
        decided_by=_decide_board_size,
        limbs_not_decided=(
            "whether a woman director is required, which the second proviso "
            "delegates to rules this system does not hold",)),
    Obligation(
        "CA13-S149-3-RESIDENT",
        "Have at least one director resident in India for 182 days",
        "Companies Act 2013, s.149(3)",
        _every_company,
        evidence_needed=("days in India this financial year of the most-present "
                         "director",
                         "whether the company was incorporated during this "
                         "financial year"),
        note="a flat 182-day test, except for a company incorporated during the "
             "year, where the proviso applies it proportionately -- which this "
             "row surfaces rather than computes",
        decided_by=_decide_resident_director),
    Obligation(
        "CA13-S137-AOC4",
        "File the financial statements with the Registrar in time",
        "Companies Act 2013, s.137(1)",
        _every_company,
        evidence_needed=("date of the annual general meeting",
                         "date the financial statements were filed"),
        note="thirty days, counted in days rather than months because the "
             "section says days; the additional-fee regime for a late filing is "
             "a separate consequence this row does not compute",
        decided_by=_decide_aoc4),
    Obligation(
        "CA13-S92-RETURN",
        "File the annual return with the Registrar in time",
        "Companies Act 2013, s.92(4)",
        _every_company,
        evidence_needed=("date of the annual general meeting, or the date one "
                         "should have been held",
                         "date the annual return was filed"),
        note="missing the AGM does not postpone the return: where none is held, "
             "the sixty days run from the date it should have been held",
        decided_by=_decide_annual_return),
    Obligation(
        "CA13-S135-CSR",
        "Constitute a CSR committee, if the company crosses a CSR threshold",
        "Companies Act 2013, s.135(1)",
        _csr_applies,
        evidence_needed=("net worth, turnover or net profit for the immediately "
                         "preceding financial year",
                         "number of directors, and whether one is independent"),
        note="applicability turns on three thresholds joined by 'or', all stated "
             "in the Act itself; whether the committee was actually constituted, "
             "and its composition, is a separate limb this row does not decide",
        limbs_not_decided=(
            "whether the CSR committee was in fact constituted",
            "its composition, including the independent-director requirement",
            "the s.135(5) spend of two per cent of average net profits")),
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
            # What THIS obligation needs to be decided -- its own evidence_needed
            # -- not every unknown field on the profile. Dumping all unknowns
            # buried the one fact that mattered under a dozen that did not, which
            # in a diligence pack is noise where a reader needs a checklist.
            need = ob.evidence_needed or tuple(profile.unknowns())
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            CANNOT_DETERMINE, basis,
                            missing_facts=need,
                            blocked_by=blocked))
            continue

        # The duty attaches. Whether it is MET is a separate question, answered
        # only by evidence the user supplied. A decider returning None does NOT
        # mean satisfied — it means the evidence did not settle it, and that
        # distinction is the whole failure mode this product exists to avoid.
        met, why = (ob.decided_by(profile, ev) if ob.decided_by
                    else (None, "no decision procedure is registered for this duty"))

        if met is True and ob.limbs_not_decided:
            # Everything we CAN check passed. That is not the same as compliance,
            # and the row must not say it is.
            rows.append(Row(ob.obligation_id, ob.duty, ob.provision,
                            APPLIES_UNDETERMINED,
                            f"{basis}. {why} — but this system does not decide "
                            f"{'; '.join(ob.limbs_not_decided)}, so compliance "
                            f"with the whole provision is not established",
                            missing_facts=ob.limbs_not_decided,
                            evidence=(why,)))
        elif met is True:
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
    check(opc_row.evidence and "1 director" in opc_row.evidence[0],
          f"one director meets the OPC minimum ({opc_row.evidence})")
    check(opc_row.state == APPLIES_UNDETERMINED,
          f"...but the row is not SATISFIED, because the woman-director limb is "
          f"delegated to rules we do not hold ({opc_row.state})")

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
    check("within the fifteen-month limit" in agm_row.basis,
          "an AGM inside the gap passes that limb")
    check(agm_row.state == APPLIES_UNDETERMINED,
          f"...and the row stays undetermined, because the six-month and "
          f"first-AGM deadlines are not decided ({agm_row.state})")

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
    filed = [r for r in build(
        CompanyProfile(company_class="public", **common),
        evidence=Evidence(agm_dates=(date(2025, 9, 15),),
                          aoc4_filed_on=date(2025, 10, 10)))
        if r.obligation_id == "CA13-S137-AOC4"][0]
    check(filed.state == APPLIES_SATISFIED and filed.evidence and filed.evidence[0],
          f"a satisfied row carries the evidence that settled it ({filed.evidence})")

    # ── a partial pass may never render as a full pass ──────────────────────
    # Found by adversarial review: AGMs on 2023-12-31 and 2025-01-31 are 397
    # days apart, inside the fifteen-month gap, and the company held NO AGM in
    # 2024 at all. The gap limb alone reported that as satisfied, under a green
    # badge, with the caveat in body text.
    skipped = [r for r in build(CompanyProfile(company_class="private", **common),
                                evidence=Evidence(agm_dates=(date(2023, 12, 31),
                                                             date(2025, 1, 31))))
               if r.obligation_id == "CA13-S96-AGM"][0]
    check(skipped.state == APPLIES_NOT_SATISFIED,
          f"a year with no AGM fails even inside the gap ({skipped.state})")
    check("2024" in skipped.basis and "each year" in skipped.basis,
          "...naming the year missed and the limb it breached")

    # And a clean gap is still not a full pass, because limbs remain undecided.
    clean = [r for r in build(CompanyProfile(company_class="private", **common),
                              evidence=Evidence(agm_dates=(date(2024, 8, 20),
                                                           date(2025, 9, 15))))
             if r.obligation_id == "CA13-S96-AGM"][0]
    check(clean.state == APPLIES_UNDETERMINED,
          f"a clean gap is not compliance with the whole provision ({clean.state})")
    check("six-month deadline" in clean.basis or "does not decide" in clean.basis,
          f"...and the row says which limb was not reached ({clean.basis[-70:]})")

    check(all(all(x.strip() for x in o.limbs_not_decided) for o in REGISTER),
          "a declared undecided limb is never an empty string")
    check(any(o.limbs_not_decided for o in REGISTER),
          "at least one obligation declares a limb it cannot reach")

    # THE INVARIANT: no obligation with an undecided limb may ever be SATISFIED.
    partial = [o.obligation_id for o in REGISTER if o.limbs_not_decided]
    for prof in (bare, priv, pub, opc, CompanyProfile(**LIMITS_OK)):
        for e in (None, Evidence(agm_dates=(date(2024, 8, 20), date(2025, 9, 15)))):
            for r in build(prof, evidence=e):
                if r.obligation_id in partial and r.state == APPLIES_SATISFIED:
                    check(False, f"{r.obligation_id} rendered a partial pass as full")
                    break
    check(True, "no obligation with an undecided limb renders APPLIES_SATISFIED")

    # ── s.96 deadline limbs, s.137 and s.92 ─────────────────────────────────
    PUB = dict(company_class="public", **common)

    def row(oid, **ev):
        return [r for r in build(CompanyProfile(**PUB), evidence=Evidence(**ev))
                if r.obligation_id == oid][0]

    # First AGM: nine months from the close of the FIRST financial year.
    late_first = row("CA13-S96-AGM", agm_dates=(date(2025, 2, 1),),
                     first_financial_year_end=date(2024, 3, 31))
    check(late_first.state == APPLIES_NOT_SATISFIED,
          f"a first AGM past nine months fails ({late_first.state})")
    check("nine-month limit of 2024-12-31" in late_first.basis,
          f"...on a calendar-month limit ({late_first.basis[-60:]})")
    ok_first = row("CA13-S96-AGM", agm_dates=(date(2024, 12, 1),),
                   first_financial_year_end=date(2024, 3, 31))
    check(ok_first.state != APPLIES_NOT_SATISFIED,
          "a first AGM inside nine months does not fail")

    # Any other AGM: six months from the close of the financial year.
    late_other = row("CA13-S96-AGM", agm_dates=(date(2024, 8, 20), date(2025, 11, 5)),
                     financial_year_end=date(2025, 3, 31))
    check(late_other.state == APPLIES_NOT_SATISFIED,
          f"an AGM past six months fails ({late_other.state})")
    check("six-month limit of 2025-09-30" in late_other.basis,
          f"...naming the limit ({late_other.basis[-55:]})")

    no_fy = row("CA13-S96-AGM", agm_dates=(date(2024, 8, 20), date(2025, 9, 15)))
    check(no_fy.state == APPLIES_UNDETERMINED,
          "without the financial year end the six-month limb is not decided")

    # s.137 — thirty DAYS, not a month.
    check(row("CA13-S137-AOC4", agm_dates=(date(2025, 9, 15),),
              aoc4_filed_on=date(2025, 10, 15)).state == APPLIES_SATISFIED,
          "filing on the thirtieth day is in time")
    check(row("CA13-S137-AOC4", agm_dates=(date(2025, 9, 15),),
              aoc4_filed_on=date(2025, 10, 16)).state == APPLIES_NOT_SATISFIED,
          "filing on the thirty-first day is late")
    due_only = row("CA13-S137-AOC4", agm_dates=(date(2025, 9, 15),))
    check(due_only.state == APPLIES_UNDETERMINED and "due by" in due_only.basis,
          "with no filing date the row states the deadline and waits")

    # s.92(4) — and the limb that matters: no AGM does not postpone the return.
    none_held = row("CA13-S92-RETURN", agm_dates=(),
                    financial_year_end=date(2025, 3, 31),
                    annual_return_filed_on=date(2026, 1, 10))
    check(none_held.state == APPLIES_NOT_SATISFIED,
          f"no AGM does not postpone the annual return ({none_held.state})")
    check("should have been held" in none_held.basis,
          f"...and the row says the clock ran from the date it was due")
    check("2025-09-30" in none_held.basis,
          "...computed from six months after the financial year end")

    silent = row("CA13-S92-RETURN", financial_year_end=date(2025, 3, 31))
    check(silent.state == APPLIES_UNDETERMINED,
          "saying nothing about AGMs is not the same as saying none was held")

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
    check("minimum of 2" in size("private", 2).basis
          and size("private", 2).state != APPLIES_NOT_SATISFIED,
          "two directors meets the private-company minimum")
    check(size("public", 2).state != size("private", 2).state,
          "the same board size passes or fails on company class")

    # The maximum is gated by a proviso, so it is NOT decided without it.
    over = size("public", 16)
    check(over.state == APPLIES_UNDETERMINED,
          f"sixteen directors is not decided without the proviso ({over.state})")
    check("special resolution" in over.basis,
          "...and the basis names the special resolution that would settle it")
    check("permitted by the special resolution" in size("public", 16, sr=True).basis,
          "a recorded special resolution permits the excess")
    check(size("public", 16, sr=False).state == APPLIES_NOT_SATISFIED,
          "no special resolution and sixteen directors is a failure")

    # The delegated limb must never be decided.
    reg149 = [o for o in REGISTER if o.obligation_id == "CA13-S149-BOARD-SIZE"][0]
    check("woman director" in reg149.note and "never decided" in reg149.note,
          "the woman-director prescription is surfaced, never decided")
    check("numbers limbs only" in size("private", 2).basis,
          "a pass says which limbs it covered")
    check("woman director" in size("private", 2).basis,
          "...and which limb it could not reach")

    # ── s.149(3): resident director, and the proviso that must not be ignored ─
    def res(**ev):
        return [r for r in build(CompanyProfile(company_class="private", **common),
                                 evidence=Evidence(**ev))
                if r.obligation_id == "CA13-S149-3-RESIDENT"][0]

    check(res(resident_director_days=182).state == APPLIES_SATISFIED,
          "exactly 182 days meets the minimum")
    check(res(resident_director_days=181).state == APPLIES_NOT_SATISFIED,
          "181 days is short by one")
    check("182-day minimum" in res(resident_director_days=90).basis,
          "a failure names the statutory minimum")

    # The proviso: a company incorporated this year is NOT judged on a flat 182.
    newco = res(resident_director_days=300, incorporated_this_financial_year=True)
    check(newco.state == APPLIES_UNDETERMINED,
          f"a company incorporated this year is not judged on the flat 182 "
          f"({newco.state})")
    check("proportionate" in newco.basis.lower(),
          "...and the row names the proviso rather than dropping it")
    check(res().state == APPLIES_UNDETERMINED,
          "no days supplied, no decision")

    # It applies to EVERY company, so it is not blocked by any threshold.
    r149 = [o for o in REGISTER if o.obligation_id == "CA13-S149-3-RESIDENT"][0]
    check(r149.applies_when is _every_company,
          "s.149(3) reaches every company, with no delegated threshold")

    # ── s.135(1) CSR: a disjunction, decided from Act-stated thresholds ──────
    def csr(**figs):
        prof = CompanyProfile(company_class="public", **common, **figs)
        return [r for r in build(prof) if r.obligation_id == "CA13-S135-CSR"][0]

    # One threshold crossed: the duty attaches. UNDETERMINED, not SATISFIED,
    # because whether the committee was constituted is a separate limb.
    crossed = csr(net_profit=Figure(Money.crore(6), "2024-25"))
    check(crossed.state == APPLIES_UNDETERMINED,
          f"a net profit over Rs 5 crore attaches the CSR duty ({crossed.state})")
    check("net profit" in crossed.basis and "reaches" in crossed.basis,
          "...naming the threshold it crossed")

    # Every figure known and all below: it genuinely does not apply.
    below = csr(net_worth=Figure(Money.crore(10), "2024-25"),
                turnover=Figure(Money.crore(20), "2024-25"),
                net_profit=Figure(Money.crore(2), "2024-25"))
    check(below.state == DOES_NOT_APPLY,
          f"all three figures below all three thresholds does not apply ({below.state})")

    # THE DISJUNCTION: below on the known figure, but another unknown, cannot be
    # ruled out -- the opposite of how a conjunction treats an unknown.
    maybe = csr(net_profit=Figure(Money.crore(2), "2024-25"))
    check(maybe.state == CANNOT_DETERMINE,
          f"below on profit but net worth unknown cannot rule the duty out "
          f"({maybe.state})")
    check("could cross" in maybe.basis or "cannot be ruled out" in maybe.basis,
          "...and the basis explains why an unknown blocks a negative here")

    # The Act's thresholds, not a rule's, so this row is never blocked on S-002.
    r135 = [o for o in REGISTER if o.obligation_id == "CA13-S135-CSR"][0]
    check(r135.applies_when.__name__ == "_csr_applies",
          "s.135 decides applicability from thresholds stated in the Act")
    check(len(r135.limbs_not_decided) == 3
          and any("constituted" in x for x in r135.limbs_not_decided)
          and any("spend" in x for x in r135.limbs_not_decided),
          "the constitution, composition and spend limbs are surfaced, not decided")

    out = render(pub, build(pub))
    check("No row claims compliance" in out, "the render says what it does not claim")
    check("need attention" in out, "...and counts what a reviewer must read")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
