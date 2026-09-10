"""Point-in-time benchmark: does the engine serve the law in force on a given date?

## Why this exists, and why it is not LegalBench

LegalBench is 162 tasks built almost entirely on American law; none of them encode
Indian corporate law, and its rule-recall tasks are jurisdiction-locked by
construction. LegalBench-RAG scores topical relevance over a single-snapshot
corpus and is silent on versioning. Quoting either as our number would invite the
obvious objection: you benchmarked against tasks that do not apply to you.

The template that DOES apply is the versioned-corpus design used on French tax
law (arXiv:2608.09393): a corpus of article *versions* with explicit validity
dates, questions anchored to specific past dates where the applicable version
differs from today's, and deterministic scoring -- no LLM judge, because a judge
inherits the recency bias under test. That study found static retrieval returned
the date-applicable version 0% of the time. No Indian equivalent exists.

This is the Indian equivalent, at the scale of the corpus we actually hold.

## What it measures, and the distinction that matters

Four outcomes, not two. Accuracy alone would score a system that refuses
everything the same as one that answers everything wrongly.

    CORRECT_ANSWER    served the amount in force on that date
    CORRECT_REFUSAL   refused, and refusing was right
    WRONG_ANSWER      served an amount that was not in force  <- the dangerous one
    WRONG_REFUSAL     refused when the amount was knowable    <- the annoying one

WRONG_ANSWER is the failure the product exists to prevent. WRONG_REFUSAL is the
failure that makes a practitioner stop using it. A system is only useful if both
are low, which is why they are reported separately and never netted off.

## The baseline it is measured against

`naive_latest` models what a tool without a currency layer does: return the most
recent servable amount, whatever date it was asked about. That is not a straw
man -- it is what four of the most-read Indian compliance sites were doing nine
months after G.S.R. 880(E), and one of them published a figure that never existed.

## Honest limits

The corpus holds one prescribed chain (small company) across two instruments.
Every case below is derived from instruments on disk with their own effective
dates -- none is invented -- but a two-instrument chain is a narrow test, and the
score should be read as "the mechanism works on what we hold", not as a coverage
claim. The set grows as instruments are acquired, and the scorer is frozen so a
later run is comparable to this one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.company_profile import Money
from checker.prescribed_thresholds import (
    ThresholdUnavailable, all_thresholds, lookup)

# ── outcomes ──────────────────────────────────────────────────────────────────
CORRECT_ANSWER = "CORRECT_ANSWER"
CORRECT_REFUSAL = "CORRECT_REFUSAL"
WRONG_ANSWER = "WRONG_ANSWER"
WRONG_REFUSAL = "WRONG_REFUSAL"
CORRECT = (CORRECT_ANSWER, CORRECT_REFUSAL)


@dataclass(frozen=True)
class Case:
    """One dated question. `expect` is None where a refusal is the right answer."""
    case_id: str
    key: str
    as_of: date
    expect: Money | None
    why: str


CAP = "small_company.paid_up_capital.prescribed"
TURN = "small_company.turnover.prescribed"

# Frozen. Every date is a boundary of an instrument we hold, or a point inside
# one; nothing here is a round number chosen for convenience.
CASES: tuple[Case, ...] = (
    Case("C1", CAP, date(2022, 9, 14), None,
         "the day before G.S.R. 700(E) commenced: no prescribed amount covers it"),
    Case("C2", CAP, date(2022, 9, 15), Money.crore(4),
         "G.S.R. 700(E)'s own commencement date -- inclusive"),
    Case("C3", CAP, date(2024, 6, 1), Money.crore(4),
         "squarely inside the 2022 window"),
    Case("C4", CAP, date(2025, 11, 30), Money.crore(4),
         "the last day before G.S.R. 880(E) -- still the 2022 figure"),
    Case("C5", CAP, date(2025, 12, 1), None,
         "880(E) commences and is unacquired: refuse, do NOT fall back to ₹4 crore"),
    Case("C6", CAP, date(2026, 9, 10), None,
         "today: still unacquired, still a refusal"),
    Case("C7", TURN, date(2022, 9, 14), None, "turnover, before 700(E)"),
    Case("C8", TURN, date(2024, 6, 1), Money.crore(40), "turnover, inside 2022 window"),
    Case("C9", TURN, date(2025, 12, 1), None, "turnover, 880(E) window, unacquired"),
)

# The same dates, scored against a corpus where 880(E) HAS been attested. This is
# the arm that proves the refusals above are about acquisition, not about the
# engine being unable to answer.
CASES_ACQUIRED: tuple[Case, ...] = (
    Case("A1", CAP, date(2024, 6, 1), Money.crore(4), "2022 window, unchanged"),
    Case("A2", CAP, date(2025, 11, 30), Money.crore(4), "last day of the 2022 window"),
    Case("A3", CAP, date(2025, 12, 1), Money.crore(10), "880(E) in force and held"),
    Case("A4", CAP, date(2026, 9, 10), Money.crore(10), "today, once acquired"),
    Case("A5", TURN, date(2026, 9, 10), Money.crore(100), "turnover, once acquired"),
)


@dataclass(frozen=True)
class Result:
    case_id: str
    outcome: str
    served: Money | None
    expected: Money | None
    detail: str


# ── the systems under test ────────────────────────────────────────────────────
def engine(key: str, as_of: date) -> Money | None:
    """Placedon: date-conditioned lookup. Raises -> refusal."""
    try:
        return lookup(key, as_of).amount
    except ThresholdUnavailable:
        return None


def naive_latest(key: str, as_of: date) -> Money | None:
    """The baseline: the most recent servable amount, ignoring the date asked about.

    No refusal path -- that is the point. A tool with no currency layer has
    nothing to refuse WITH.
    """
    servable = [t for t in all_thresholds() if t.key == key and t.servable]
    if not servable:
        return None
    return max(servable, key=lambda t: t.effective_from).amount


def score(cases: tuple[Case, ...], system) -> list[Result]:
    out: list[Result] = []
    for c in cases:
        served = system(c.key, c.as_of)
        if c.expect is None:
            outcome = CORRECT_REFUSAL if served is None else WRONG_ANSWER
        elif served is None:
            outcome = WRONG_REFUSAL
        else:
            outcome = CORRECT_ANSWER if served == c.expect else WRONG_ANSWER
        out.append(Result(c.case_id, outcome, served, c.expect, c.why))
    return out


def tally(results: list[Result]) -> dict[str, int]:
    t = {CORRECT_ANSWER: 0, CORRECT_REFUSAL: 0, WRONG_ANSWER: 0, WRONG_REFUSAL: 0}
    for r in results:
        t[r.outcome] += 1
    return t


def accuracy(results: list[Result]) -> float:
    return sum(1 for r in results if r.outcome in CORRECT) / len(results) if results else 0.0


def report_text() -> str:
    from checker.prescribed_thresholds import all_acquired
    lines = ["POINT-IN-TIME BENCHMARK — Companies Act 2013, s.2(85) prescribed limits",
             f"{len(CASES)} dated cases against instruments held on disk", ""]

    for label, system in (("Placedon (date-conditioned)", engine),
                          ("Baseline: latest servable figure", naive_latest)):
        res = score(CASES, system)
        t = tally(res)
        lines.append(f"  {label}")
        lines.append(f"    accuracy      {accuracy(res):.2f}   "
                     f"correct answer {t[CORRECT_ANSWER]} · correct refusal {t[CORRECT_REFUSAL]}")
        lines.append(f"    WRONG ANSWER  {t[WRONG_ANSWER]}      "
                     f"WRONG REFUSAL {t[WRONG_REFUSAL]}")
        for r in res:
            if r.outcome not in CORRECT:
                lines.append(f"      {r.case_id} {r.outcome}: served {r.served}, "
                             f"in force {r.expected} — {r.detail}")
        lines.append("")

    with all_acquired():
        res = score(CASES_ACQUIRED, engine)
        lines.append("  Placedon, with G.S.R. 880(E) attested")
        lines.append(f"    accuracy      {accuracy(res):.2f}   "
                     f"({len(CASES_ACQUIRED)} cases)")
        for r in res:
            if r.outcome not in CORRECT:
                lines.append(f"      {r.case_id} {r.outcome}: served {r.served}, "
                             f"in force {r.expected}")
        lines.append("")

    lines.append("WRONG ANSWER is the failure this product exists to prevent.")
    lines.append("WRONG REFUSAL is the failure that makes a practitioner stop using it.")
    lines.append("They are never netted off.")
    return "\n".join(lines)


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

    print("pit_bench")
    from checker.prescribed_thresholds import all_acquired

    ours = score(CASES, engine)
    t_ours = tally(ours)
    check(t_ours[WRONG_ANSWER] == 0,
          f"the engine never serves a figure that was not in force "
          f"({[r.case_id for r in ours if r.outcome == WRONG_ANSWER]})")
    check(accuracy(ours) == 1.0, f"...and is correct on every dated case ({accuracy(ours):.2f})")

    naive = score(CASES, naive_latest)
    t_naive = tally(naive)
    check(t_naive[WRONG_ANSWER] > 0,
          f"the latest-figure baseline DOES serve figures not in force "
          f"({t_naive[WRONG_ANSWER]} of {len(CASES)})")
    check(accuracy(naive) < accuracy(ours),
          f"...and scores below the engine ({accuracy(naive):.2f} vs {accuracy(ours):.2f})")
    # the specific failure that matters: serving the superseded amount today
    c6 = [r for r in naive if r.case_id == "C6"][0]
    check(c6.outcome == WRONG_ANSWER and c6.served == Money.crore(4),
          f"the baseline serves ₹4 crore on today's date ({c6.served})")

    # ── acquisition changes refusals into answers, and nothing else ──────────
    with all_acquired():
        acq = score(CASES_ACQUIRED, engine)
        check(accuracy(acq) == 1.0,
              f"with 880(E) attested every case is answered correctly ({accuracy(acq):.2f})")
        check(tally(acq)[WRONG_ANSWER] == 0, "...and still nothing not-in-force is served")
        a2 = [r for r in acq if r.case_id == "A2"][0]
        check(a2.served == Money.crore(4),
              f"...and the 2022 window still answers ₹4 crore, not ₹10 ({a2.served})")

    # ── the benchmark must be able to fail: mutation ─────────────────────────
    def broken(key: str, as_of: date) -> Money | None:
        return naive_latest(key, as_of)          # a system with no currency layer
    check(accuracy(score(CASES, broken)) < 1.0,
          "a system without a currency layer scores below 1.0 — the benchmark bites")

    def always_refuse(key: str, as_of: date) -> Money | None:
        return None
    r_ref = score(CASES, always_refuse)
    check(tally(r_ref)[WRONG_REFUSAL] > 0,
          "a system that refuses everything is penalised, not rewarded")
    check(accuracy(r_ref) < 1.0,
          f"...and cannot reach 1.0 by abstaining ({accuracy(r_ref):.2f})")

    # ── the cases themselves are honest ──────────────────────────────────────
    check(all(c.why.strip() for c in CASES + CASES_ACQUIRED),
          "every case states why that date was chosen")
    check(len({c.case_id for c in CASES + CASES_ACQUIRED}) == len(CASES + CASES_ACQUIRED),
          "case ids are unique")
    check("never netted off" in report_text(),
          "the report states that wrong answers and wrong refusals are reported apart")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
