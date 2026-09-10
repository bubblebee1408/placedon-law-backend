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

# ── ground truth ──────────────────────────────────────────────────────────────
# THE LAW, not our holdings. `expect` is what the prescribed limit WAS on that
# date, decided by the instruments' own commencement dates -- G.S.R. 700(E) of
# 15-09-2022 and G.S.R. 880(E) of 01-12-2025, both read from the Gazette.
#
# This distinction is the whole design, and the first version got it wrong: the
# cases encoded "we cannot serve this" as ground truth, so the moment 880(E) was
# attested the benchmark scored a CORRECT engine at 0.67. A benchmark whose
# expected answers move when you acquire an instrument is measuring your holdings,
# not the law. Acquisition state belongs in the HARNESS, not the expectations.
CASES: tuple[Case, ...] = (
    Case("C1", CAP, date(2022, 9, 14), None,
         "the day before G.S.R. 700(E): no amount was prescribed yet"),
    Case("C2", CAP, date(2022, 9, 15), Money.crore(4),
         "G.S.R. 700(E)'s own commencement date -- inclusive"),
    Case("C3", CAP, date(2024, 6, 1), Money.crore(4), "inside the 2022 window"),
    Case("C4", CAP, date(2025, 11, 30), Money.crore(4),
         "the last day before G.S.R. 880(E)"),
    Case("C5", CAP, date(2025, 12, 1), Money.crore(10),
         "G.S.R. 880(E)'s own commencement date -- inclusive"),
    Case("C6", CAP, date(2026, 9, 10), Money.crore(10), "today"),
    Case("C7", TURN, date(2022, 9, 14), None, "turnover, before 700(E)"),
    Case("C8", TURN, date(2024, 6, 1), Money.crore(40), "turnover, 2022 window"),
    Case("C9", TURN, date(2025, 12, 1), Money.crore(100), "turnover, 880(E) window"),
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
    from checker.prescribed_thresholds import all_acquired, none_acquired
    lines = ["POINT-IN-TIME BENCHMARK — Companies Act 2013, s.2(85) prescribed limits",
             f"{len(CASES)} dated cases. Ground truth is the LAW on that date,",
             "decided by each instrument's own commencement, not by what we hold.", ""]

    with all_acquired():
        res = score(CASES, engine)
        t = tally(res)
        lines.append("  Placedon, holding both instruments")
        lines.append(f"    accuracy      {accuracy(res):.2f}   "
                     f"WRONG ANSWER {t[WRONG_ANSWER]}   WRONG REFUSAL {t[WRONG_REFUSAL]}")
        for r in res:
            if r.outcome not in CORRECT:
                lines.append(f"      {r.case_id} {r.outcome}: served {r.served}, "
                             f"in force {r.expected} — {r.detail}")
        lines.append("")

        res_b = score(CASES, naive_latest)
        t_b = tally(res_b)
        lines.append("  Baseline: latest figure, ignoring the date asked about")
        lines.append(f"    accuracy      {accuracy(res_b):.2f}   "
                     f"WRONG ANSWER {t_b[WRONG_ANSWER]}   WRONG REFUSAL {t_b[WRONG_REFUSAL]}")
        lines.append(f"      serves one figure for every date in a 4-year span")
        lines.append("")

    with none_acquired():
        res_u = score(CASES, engine)
        t_u = tally(res_u)
        lines.append("  Placedon, holding NEITHER instrument (the abstention arm)")
        lines.append(f"    WRONG ANSWER  {t_u[WRONG_ANSWER]}   "
                     f"— it must never invent a figure it does not hold")
        lines.append(f"    wrong refusal {t_u[WRONG_REFUSAL]}   "
                     f"— refusing what it cannot serve is correct, and is not free: "
                     f"accuracy {accuracy(res_u):.2f}")
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
    from checker.prescribed_thresholds import all_acquired, none_acquired

    # ── the correctness arm: holding both instruments, get the law right ─────
    with all_acquired():
        ours = score(CASES, engine)
        t = tally(ours)
        check(t[WRONG_ANSWER] == 0,
              f"holding both instruments, never serves a figure not in force "
              f"({[r.case_id for r in ours if r.outcome == WRONG_ANSWER]})")
        check(accuracy(ours) == 1.0,
              f"...and is correct on every dated case ({accuracy(ours):.2f})")
        c3 = [r for r in ours if r.case_id == "C3"][0]
        c6 = [r for r in ours if r.case_id == "C6"][0]
        check(c3.served == Money.crore(4) and c6.served == Money.crore(10),
              f"...answering ₹4 crore for 2024 and ₹10 crore for today "
              f"({c3.served} / {c6.served})")

        # ── the baseline, scored against the same ground truth ──────────────
        naive = score(CASES, naive_latest)
        check(tally(naive)[WRONG_ANSWER] > 0,
              f"the latest-figure baseline serves figures not in force "
              f"({tally(naive)[WRONG_ANSWER]} of {len(CASES)})")
        check(accuracy(naive) < accuracy(ours),
              f"...and scores below the engine ({accuracy(naive):.2f} vs {accuracy(ours):.2f})")
        nc3 = [r for r in naive if r.case_id == "C3"][0]
        check(nc3.outcome == WRONG_ANSWER and nc3.served == Money.crore(10),
              f"...serving today's ₹10 crore for a 2024 date ({nc3.served}) — the "
              f"mirror image of serving ₹4 crore today, and just as wrong")

    # ── the abstention arm: holding neither, never invent ────────────────────
    with none_acquired():
        unheld = score(CASES, engine)
        check(tally(unheld)[WRONG_ANSWER] == 0,
              "holding neither instrument, it never invents a figure")
        check(tally(unheld)[WRONG_REFUSAL] > 0,
              "...and refusing is scored as a cost, not scored as free")
        check(accuracy(unheld) < 1.0,
              f"...so abstaining cannot buy a good score ({accuracy(unheld):.2f})")

    # ── the benchmark must be able to fail ───────────────────────────────────
    with all_acquired():
        def always_refuse(key: str, as_of: date) -> Money | None:
            return None
        check(accuracy(score(CASES, always_refuse)) < 1.0,
              "a system that refuses everything cannot reach 1.0 — the benchmark bites")

        def latest_only(key: str, as_of: date) -> Money | None:
            return naive_latest(key, as_of)
        check(accuracy(score(CASES, latest_only)) < 1.0,
              "a system with no currency layer scores below 1.0")

    # ── ground truth must not depend on what we hold ─────────────────────────
    # The failure this guards is the one the first version of this file had: the
    # cases encoded "we cannot serve this" as the law, so attesting an instrument
    # scored a CORRECT engine at 0.67.
    with all_acquired():
        a = [(c.case_id, c.expect) for c in CASES]
    with none_acquired():
        b = [(c.case_id, c.expect) for c in CASES]
    check(a == b, "the expected answers are identical under both acquisition states")
    check(all(c.why.strip() for c in CASES), "every case states why that date was chosen")
    check(len({c.case_id for c in CASES}) == len(CASES), "case ids are unique")
    check("never netted off" in report_text(),
          "the report keeps wrong answers and wrong refusals apart")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
