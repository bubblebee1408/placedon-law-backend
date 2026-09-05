"""s.173 board meetings — the second workflow, under the release gate.

Authorised only after E4 learned floor-from-ceiling and E5 learned within-clause
role binding, because both failures land squarely on this section:

- s.173(1) sets a **ceiling**: "not more than one hundred and twenty days shall
  intervene between two consecutive meetings".
- s.173(5) sets a **floor**: "the gap between the two meetings is not less than
  ninety days".

Same section, same unit, opposite direction. A verifier blind to direction reads
the relaxed regime as satisfied by meetings held thirty days apart — which is
the single most dangerous thing this workflow could get wrong, because it turns
a defect into a clean bill of health.

## Quorum is surfaced, never assumed

s.173(5)'s proviso disapplies both this section **and s.174** for a One Person
Company with a single director. For every other company, whether a meeting was
validly held depends on s.174 quorum — one-third of total strength or two
directors, whichever is higher — and this module does not compute that. It
records the dependency as an open question on the card rather than reporting a
meeting as compliant on count and gap alone. A board-meeting engine that stays
silent about quorum produces confident answers about validity it has not
established.

## What is deliberately not built

Notice periods (s.173(3)), video-conferencing eligibility (s.173(2) and the
excluded-matters rules), and the s.8 relaxation. Each is a separate rule with
its own instrument, and the instruction was to build this section only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# s.173(1) — the standard regime.
FIRST_MEETING_DAYS = 30
MIN_MEETINGS_PER_YEAR = 4
MAX_GAP_DAYS = 120                 # CEILING
# s.173(5) — the relaxed regime.
MIN_GAP_DAYS_RELAXED = 90          # FLOOR. Not a ceiling. See module docstring.
RELAXED_CLASSES = ("one_person_company", "small_company", "dormant_company")

CEILING = "ceiling"
FLOOR = "floor"

COMPLIANT = "COMPLIANT"
NOT_COMPLIANT = "NOT_COMPLIANT"
INDETERMINATE = "INDETERMINATE"


@dataclass
class Finding:
    rule: str
    direction: str | None
    limit: int | None
    observed: str
    satisfied: bool | None          # None where it cannot be determined
    citation: str
    note: str = ""


@dataclass
class BoardMeetingReview:
    company_class: str
    calendar_year: int
    meetings: list[date]
    regime: str
    findings: list[Finding] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    status: str = INDETERMINATE

    def render(self) -> str:
        L = ["=" * 72,
             f"EVIDENCE CARD — s.173  Meetings of Board",
             "=" * 72,
             f"  company class   : {self.company_class}",
             f"  calendar year   : {self.calendar_year}",
             f"  regime          : {self.regime}",
             f"  meetings held   : {', '.join(d.isoformat() for d in self.meetings) or '(none recorded)'}",
             "", "  FINDINGS"]
        for f in self.findings:
            mark = "ok " if f.satisfied else ("XX " if f.satisfied is False else "?? ")
            d = f" [{f.direction}]" if f.direction else ""
            L.append(f"    {mark}{f.rule}{d}")
            L.append(f"       limit    : {f.limit if f.limit is not None else '-'}")
            L.append(f"       observed : {f.observed}")
            L.append(f"       citation : {f.citation}")
            if f.note:
                L.append(f"       note     : {f.note}")
        if self.missing_facts:
            L += ["", "  MISSING FACTS"] + [f"    - {m}" for m in self.missing_facts]
        L += ["", "  OPEN — not decided by this workflow"]
        L += [f"    - {q}" for q in self.open_questions]
        L += ["", f"  STATUS          : {self.status}", "  REVIEW          : PENDING", ""]
        if self.status != COMPLIANT:
            L += ["  This card does not certify compliance. Where a finding is",
                  "  unsatisfied or undetermined, the position must be established",
                  "  by a reviewer.", ""]
        return "\n".join(L)


def _halves(year: int) -> tuple[tuple[date, date], tuple[date, date]]:
    return ((date(year, 1, 1), date(year, 6, 30)),
            (date(year, 7, 1), date(year, 12, 31)))


def review(*, company_class: str, calendar_year: int, meetings: list[date],
           incorporation_date: date | None = None,
           single_director_opc: bool = False,
           total_board_strength: int | None = None,
           source_text: str | None = None) -> BoardMeetingReview:
    """Assess s.173 for one company and one calendar year."""
    # Meetings outside the year do not count toward that year's minimum. Without
    # this filter two meetings in 2024 and two in 2025 satisfied "four meetings
    # in the year" for 2025 -- a false pass built out of the wrong year's work.
    # The GAP limb still sees every date, because s.173(1) bounds the interval
    # "between two consecutive meetings" and that interval crosses year ends.
    all_dates = sorted(meetings)
    ms = [d for d in all_dates if d.year == calendar_year]
    outside = [d for d in all_dates if d.year != calendar_year]
    relaxed = company_class in RELAXED_CLASSES
    regime = ("s.173(5) relaxed — OPC, small or dormant company" if relaxed
              else "s.173(1) standard")
    r = BoardMeetingReview(company_class=company_class, calendar_year=calendar_year,
                           meetings=ms, regime=regime)

    if outside:
        r.open_questions.append(
            f"{len(outside)} supplied meeting date(s) fall outside {calendar_year} "
            f"({', '.join(str(d) for d in outside[:4])}"
            f"{'…' if len(outside) > 4 else ''}) and were not counted toward this "
            f"year's minimum; they are still used for the interval between "
            f"consecutive meetings")

    # The proviso disapplies s.173 AND s.174 entirely for a single-director OPC.
    if single_director_opc:
        if company_class != "one_person_company":
            r.missing_facts.append(
                "single_director_opc was asserted for a company that is not an OPC; "
                "the s.173(5) proviso reaches only a One Person Company")
        else:
            r.findings.append(Finding(
                "s.173 and s.174 do not apply", None, None,
                "One Person Company with one director", True,
                "s.173(5) proviso",
                "a resolution entered and signed in the minutes book under s.118 is "
                "deemed a Board meeting (s.122(4)); nothing here is computed"))
            r.status = COMPLIANT
            r.open_questions.append(
                "whether the company had only one director throughout the year is a "
                "fact this workflow takes as given, not one it verifies")
            return r

    if incorporation_date and incorporation_date.year == calendar_year:
        first = ms[0] if ms else None
        due = date.fromordinal(incorporation_date.toordinal() + FIRST_MEETING_DAYS)
        r.findings.append(Finding(
            "first Board meeting after incorporation", CEILING, FIRST_MEETING_DAYS,
            f"{first.isoformat() if first else 'no meeting recorded'} "
            f"(due {due.isoformat()})",
            (first is not None and first <= due),
            "s.173(1)"))

    if relaxed:
        h1, h2 = _halves(calendar_year)
        in_h1 = [d for d in ms if h1[0] <= d <= h1[1]]
        in_h2 = [d for d in ms if h2[0] <= d <= h2[1]]
        r.findings.append(Finding(
            "one meeting in each half of the calendar year", FLOOR, 1,
            f"H1: {len(in_h1)}, H2: {len(in_h2)}",
            bool(in_h1) and bool(in_h2), "s.173(5)"))

        if in_h1 and in_h2:
            gap = (in_h2[0] - in_h1[-1]).days
            r.findings.append(Finding(
                "gap between the two meetings", FLOOR, MIN_GAP_DAYS_RELAXED,
                f"{gap} days",
                gap >= MIN_GAP_DAYS_RELAXED, "s.173(5)",
                note=("this is a MINIMUM. The gap must be not less than ninety "
                      "days; a shorter gap fails, a longer one does not")))
        else:
            r.findings.append(Finding(
                "gap between the two meetings", FLOOR, MIN_GAP_DAYS_RELAXED,
                "cannot be computed — a meeting is missing from one half",
                None, "s.173(5)"))
    else:
        r.findings.append(Finding(
            "minimum number of Board meetings in the year", FLOOR,
            MIN_MEETINGS_PER_YEAR, f"{len(ms)} recorded",
            len(ms) >= MIN_MEETINGS_PER_YEAR, "s.173(1)"))
        if len(ms) >= 2:
            gaps = [(ms[i + 1] - ms[i]).days for i in range(len(ms) - 1)]
            worst = max(gaps)
            r.findings.append(Finding(
                "gap between two consecutive meetings", CEILING, MAX_GAP_DAYS,
                f"longest gap {worst} days",
                worst <= MAX_GAP_DAYS, "s.173(1)",
                note=("this is a MAXIMUM, the inverse of the s.173(5) floor. The "
                      "two must not be compared with the same operator")))
        else:
            r.findings.append(Finding(
                "gap between two consecutive meetings", CEILING, MAX_GAP_DAYS,
                "fewer than two meetings recorded", None, "s.173(1)"))

    # Quorum. Surfaced, never assumed.
    r.open_questions.append(
        "whether each meeting was quorate is governed by s.174 — one-third of "
        "total strength or two directors, whichever is higher — and is NOT "
        "computed here. A meeting that satisfies s.173 on count and gap may "
        "still have been inquorate.")
    if total_board_strength is None:
        r.missing_facts.append(
            "total board strength, without which s.174 quorum cannot be assessed "
            "even in principle")

    if any(f.satisfied is False for f in r.findings):
        r.status = NOT_COMPLIANT
    elif any(f.satisfied is None for f in r.findings) or r.missing_facts:
        r.status = INDETERMINATE
    else:
        # Never COMPLIANT while quorum is unestablished: s.173 compliance on
        # count and gap is not a finding that the meetings were valid.
        r.status = INDETERMINATE
        r.open_questions.append(
            "count and gap are satisfied; the status stays INDETERMINATE because "
            "quorum has not been established")
    return r


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

    print("s173_slice")

    # THE trap: 90 days is a floor. Meetings 30 days apart must FAIL.
    close = review(company_class="small_company", calendar_year=2025,
                   meetings=[date(2025, 6, 20), date(2025, 7, 20)],
                   total_board_strength=4)
    gap = next(f for f in close.findings if "gap" in f.rule)
    check(gap.direction == FLOOR, "the relaxed gap is recorded as a floor")
    check(gap.satisfied is False,
          f"meetings 30 days apart FAIL the ninety-day minimum ({gap.observed})")
    check(close.status == NOT_COMPLIANT, "...and the review is NOT_COMPLIANT")

    far = review(company_class="small_company", calendar_year=2025,
                 meetings=[date(2025, 3, 10), date(2025, 9, 10)],
                 total_board_strength=4)
    g2 = next(f for f in far.findings if "gap" in f.rule)
    check(g2.satisfied is True,
          f"meetings 184 days apart satisfy the minimum ({g2.observed})")

    # The inverse rule, same section, opposite operator.
    std = review(company_class="private_company", calendar_year=2025,
                 meetings=[date(2025, 1, 5), date(2025, 2, 5),
                           date(2025, 3, 5), date(2025, 4, 5)],
                 total_board_strength=5)
    sg = next(f for f in std.findings if "consecutive" in f.rule)
    check(sg.direction == CEILING, "the standard gap is recorded as a ceiling")
    check(sg.satisfied is True, "short gaps SATISFY the standard ceiling")
    check(gap.direction != sg.direction,
          "the two gap rules in one section carry opposite directions")

    spread = review(company_class="private_company", calendar_year=2025,
                    meetings=[date(2025, 1, 5), date(2025, 6, 30),
                              date(2025, 8, 1), date(2025, 12, 1)],
                    total_board_strength=5)
    sg2 = next(f for f in spread.findings if "consecutive" in f.rule)
    check(sg2.satisfied is False,
          f"a gap over 120 days fails the ceiling ({sg2.observed})")

    # Count rule.
    few = review(company_class="private_company", calendar_year=2025,
                 meetings=[date(2025, 1, 5), date(2025, 4, 5)],
                 total_board_strength=5)
    cnt = next(f for f in few.findings if "minimum number" in f.rule)
    check(cnt.satisfied is False and cnt.direction == FLOOR,
          "fewer than four meetings fails the count floor")

    # Half-year rule.
    onehalf = review(company_class="dormant_company", calendar_year=2025,
                     meetings=[date(2025, 2, 1), date(2025, 5, 1)],
                     total_board_strength=3)
    hf = next(f for f in onehalf.findings if "half" in f.rule)
    check(hf.satisfied is False, "both meetings in H1 fails the half-year rule")

    # Quorum must be surfaced on every card, and never assumed satisfied.
    for r in (close, far, std, spread, few, onehalf):
        assert any("s.174" in q for q in r.open_questions), r.company_class
    check(True, "every card surfaces the s.174 quorum dependency")
    check(far.status == INDETERMINATE,
          "a company passing count and gap is still INDETERMINATE without quorum")
    check(any("quorum has not been established" in q for q in far.open_questions),
          "...and the card says that is why")

    nostrength = review(company_class="small_company", calendar_year=2025,
                        meetings=[date(2025, 3, 10), date(2025, 9, 10)])
    check(any("total board strength" in m for m in nostrength.missing_facts),
          "missing board strength is recorded as a missing fact")

    # The single-director OPC proviso disapplies s.173 AND s.174.
    opc = review(company_class="one_person_company", calendar_year=2025,
                 meetings=[], single_director_opc=True)
    check(opc.status == COMPLIANT, "a single-director OPC is outside s.173 entirely")
    check(any("s.174" in f.rule for f in opc.findings),
          "...and the card records that s.174 is disapplied too")
    bad = review(company_class="private_company", calendar_year=2025, meetings=[],
                 single_director_opc=True)
    check(any("reaches only a One Person Company" in m for m in bad.missing_facts),
          "the proviso is refused for a company that is not an OPC")

    # First-meeting rule only fires in the year of incorporation.
    inc = review(company_class="private_company", calendar_year=2025,
                 meetings=[date(2025, 3, 1)], incorporation_date=date(2025, 1, 1),
                 total_board_strength=3)
    fm = next(f for f in inc.findings if "first Board meeting" in f.rule)
    check(fm.satisfied is False, "a first meeting 59 days after incorporation fails")

    r = close.render()
    check("s.174" in r and "not certify compliance" in r,
          "the rendered card names s.174 and declines to certify")
    check("[floor]" in r, "the card shows the direction of each rule")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
