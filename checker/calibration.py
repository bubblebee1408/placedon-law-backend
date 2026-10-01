#!/usr/bin/env python3
"""Conformal thresholds per (task, body of law) — which change nothing until the labels exist.

CAL-1. A threshold computed from lawyer approve/reject decisions, with a finite-sample
guarantee, per (task, body of law). Below `MIN_LABELS` it returns **nothing**, and that is
the normal state today: the gold set has no human labels and the decisions in the database
are this repository's own synthetic seeds.

## What this may never become, and why that is not a limitation to fix

`checker/ask_contract.py` states the rule as **"C4: no confidence, ever"**, and refuses a
`confidence` or `coverage` key anywhere in a served answer. `checker/rings.py` enforces the
same thing structurally: a probability may never reach a legal decision.

So a threshold out of this module **cannot gate whether an answer is served.** Doing that
would make a number computed from past decisions decide a present legal question, which is
exactly what both rules exist to prevent. What it CAN inform is a **human review policy** --
which (task, body) pairs deserve a second reviewer, where the review effort is worth
spending. That is a decision about PEOPLE, and it is the only use this module is built for.

`scripts/calibration_report.py` prints it; no served module imports this file, and a test
asserts that by parsing imports rather than trusting it.

## The score is injected, and this module will not invent one

Split conformal needs a nonconformity score per labelled item. **Nothing in this system
records one today** -- by the same C4 rule -- so `calibrate()` takes scores from its caller
and refuses to manufacture a stand-in. An admissible score is CODE-DERIVED and ordinal (the
cascade stage that produced an answer, the number of propositions that verified, the share
of sentences carrying a quoted span). A model's self-reported confidence is not admissible
and never will be: PLAN_23 §1.5 rules it out even as a spending decision.

## The guarantee, stated honestly

With `n` calibration scores from REJECTED items, the threshold at level alpha is the
`ceil((n+1)(1-alpha))`-th smallest of them. Under EXCHANGEABILITY, at most alpha of future
rejected items score at or above it.

Lawyer-reviewed items are **not obviously exchangeable**: a reviewer looks at what they were
sent, and what they are sent is chosen by the system being calibrated. `Readiness.note` says
so every time, because a conformal guarantee quoted without its assumption is a number
pretending to be a promise.

Run: PYTHONPATH=. python3 checker/calibration.py --test
"""
from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["MIN_LABELS", "APPROVED", "REJECTED", "Label", "bucket_labels",
           "nonconformity", "ESCALATION_WEIGHT",
           "calibrate", "Readiness", "CalibrationError"]

# PLAN_23 CAL-1. Below this, nothing is computed and nothing changes. 100 is the brief's
# number; it is also roughly where a split-conformal quantile at alpha=0.1 stops being
# dominated by where the single largest score happened to land.
MIN_LABELS = 100

APPROVED = "APPROVED"
REJECTED = "REJECTED"


class CalibrationError(ValueError):
    """A calibration that cannot be formed. Never a threshold from thin air."""


@dataclass(frozen=True)
class Label:
    """One lawyer decision, with the code-derived score the item had at the time."""
    task: str
    body: str
    decision: str
    score: float | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.task or "(task not recorded)", self.body or "(body not recorded)")


@dataclass(frozen=True)
class Readiness:
    """What one (task, body) bucket can and cannot support. Never an accuracy figure."""
    task: str
    body: str
    labels: int = 0
    rejected: int = 0
    scored: int = 0
    threshold: float | None = None
    alpha: float = 0.1
    note: str = ""

    @property
    def ready(self) -> bool:
        return self.threshold is not None

    def to_dict(self) -> dict:
        return {"task": self.task, "body": self.body, "labels": self.labels,
                "rejected": self.rejected, "scored": self.scored,
                "threshold": self.threshold, "alpha": self.alpha,
                "minimum": MIN_LABELS, "ready": self.ready, "note": self.note}


# ── the nonconformity score ──────────────────────────────────────────────────
#
# Decided by the founder, 2026-10-02:
#
#     (1 - share of sentences with a byte-matched quote AND passed entailment)
#     + 0.5 * number of cascade escalations
#
# Both terms are "the system had to work harder, or had less to stand on". Neither is a
# model's opinion of itself, which is what makes it admissible at all (PLAN_23 §1.5).

ESCALATION_WEIGHT = 0.5


def nonconformity(*, verified: int, total: int, escalations: int) -> tuple:
    """(score, why) for one run, or (None, why) when it cannot be computed.

    `verified` counts sentences that are BOTH byte-matched to a span AND passed
    entailment. Both halves are required because they are different checks:
    `checker/lawyer_summary.py` says so in terms -- "TRACED IS NOT ENTAILMENT. A sentence
    can quote a real span, at real offsets, share its vocabulary, and still assert
    something the span does not say."

    **A run with no sentences scores None, not 1.0.** Zero of zero is not "nothing was
    supported" -- it is "there was nothing to support", and a refusal would otherwise come
    out as maximally nonconforming and drag every threshold computed from it.
    """
    if total <= 0:
        return None, ("no sentences were produced, so there is no share to take. Zero of "
                      "zero is not 'nothing was supported'")
    if verified < 0 or verified > total:
        raise CalibrationError(
            f"verified={verified} of total={total} is impossible; a count outside its own "
            f"denominator means the two were measured over different things")
    if escalations < 0:
        raise CalibrationError(f"escalations cannot be negative, got {escalations}")
    share = verified / total
    score = (1.0 - share) + ESCALATION_WEIGHT * escalations
    return round(score, 4), (
        f"{verified}/{total} sentence(s) byte-matched AND entailed, "
        f"{escalations} escalation(s)")


def bucket_labels(labels) -> dict:
    """{(task, body): [Label]}. The grouping, in one place."""
    out: dict = {}
    for item in labels or ():
        if not isinstance(item, Label):
            raise CalibrationError(
                f"a Label is required, got {type(item).__name__}: a dict would let a "
                f"caller pass a decision with no task and have it silently bucketed")
        out.setdefault(item.key, []).append(item)
    return out


def _quantile(scores, alpha: float) -> float | None:
    """The split-conformal order statistic, or None when the rank exceeds what we have.

    `ceil((n+1)(1-alpha))` can exceed n for small n -- which is the finite-sample way of
    saying "these labels cannot support that level". None, not the maximum: returning the
    largest score would quietly serve a weaker guarantee under the same name.
    """
    ordered = sorted(scores)
    n = len(ordered)
    if n == 0:
        return None
    rank = math.ceil((n + 1) * (1 - alpha))
    if rank > n:
        return None
    return float(ordered[rank - 1])


def calibrate(labels, *, alpha: float = 0.1) -> list:
    """One Readiness per (task, body). Computes a threshold only where the labels allow.

    Scores are the caller's; see the docstring on why this module will not invent one.
    """
    if not 0 < alpha < 1:
        raise CalibrationError(f"alpha must be between 0 and 1, got {alpha!r}")
    out = []
    for (task, body), items in sorted(bucket_labels(labels).items()):
        n = len(items)
        rejected = [i for i in items if i.decision == REJECTED]
        scored = [i.score for i in rejected if isinstance(i.score, (int, float))]
        if n < MIN_LABELS:
            out.append(Readiness(
                task=task, body=body, labels=n, rejected=len(rejected),
                scored=len(scored), alpha=alpha,
                note=(f"insufficient labels (n<{MIN_LABELS}): {n} decision(s) recorded. "
                      f"Nothing is computed and nothing changes.")))
            continue
        if not scored:
            out.append(Readiness(
                task=task, body=body, labels=n, rejected=len(rejected), scored=0,
                alpha=alpha,
                note=(f"{n} labels, which is enough, but NO item carries a score. "
                      f"Nothing in this system records one (C4: no confidence, ever), so "
                      f"a threshold cannot be computed and must not be invented.")))
            continue
        t = _quantile(scored, alpha)
        out.append(Readiness(
            task=task, body=body, labels=n, rejected=len(rejected), scored=len(scored),
            threshold=t, alpha=alpha,
            note=(f"threshold at alpha={alpha} from {len(scored)} scored rejections. "
                  f"UNDER EXCHANGEABILITY at most {alpha:.0%} of future rejected items "
                  f"score at or above it -- and lawyer-reviewed items are not obviously "
                  f"exchangeable, because a reviewer sees what this system chose to send "
                  f"them. This informs who gets a second reviewer; it may never gate an "
                  f"answer (C4, checker/rings.py)."
                  if t is not None else
                  f"{len(scored)} scored rejection(s) cannot support alpha={alpha}: the "
                  f"conformal rank exceeds the sample. No threshold, rather than the "
                  f"largest score wearing one.")))
    return out


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("calibration")

    def many(n, *, task="research_question", body="CA2013", decision=REJECTED, score=0.5):
        return [Label(task, body, decision, score) for _ in range(n)]

    # ── below the floor, NOTHING is computed and NOTHING changes ────────────
    check(MIN_LABELS == 100, f"the floor is {MIN_LABELS} (PLAN_23 CAL-1)")
    r = calibrate(many(99))
    check(len(r) == 1 and r[0].threshold is None,
          "99 labels produce NO threshold")
    check(f"insufficient labels (n<{MIN_LABELS})" in r[0].note,
          f"...and say 'insufficient labels (n<{MIN_LABELS})' in those words "
          f"({r[0].note[:44]!r})")
    check("nothing changes" in r[0].note.lower(),
          "...and that nothing changes")
    check(not r[0].ready, "...and the bucket is not ready")
    check(calibrate([])  == [], "no labels at all is no buckets, not a bucket of zero")

    # ── at and above the floor, with scores ────────────────────────────────
    scored = [Label("research_question", "CA2013", REJECTED, float(i)) for i in range(100)]
    r2 = calibrate(scored, alpha=0.1)
    check(r2[0].ready and r2[0].threshold is not None,
          f"100 scored rejections DO produce a threshold ({r2[0].threshold})")
    check(r2[0].threshold == 90.0,
          f"...the ceil((n+1)(1-alpha))-th smallest: ceil(101*0.9)=91st of 0..99 = 90 "
          f"({r2[0].threshold})")
    check(calibrate(scored, alpha=0.5)[0].threshold == 50.0,
          "...and alpha moves it the way it should")
    check("UNDER EXCHANGEABILITY" in r2[0].note,
          "...and the note states the ASSUMPTION, not just the guarantee")
    check("not obviously exchangeable" in r2[0].note,
          "...and says lawyer-reviewed items may not satisfy it, because a reviewer sees "
          "what this system chose to send them")
    check("may never gate an answer" in r2[0].note,
          "...and that it may never gate an answer (C4, rings)")

    # ── enough labels but NO score: still nothing, and a different reason ───
    r3 = calibrate([Label("research_question", "CA2013", REJECTED, None)
                    for _ in range(120)])
    check(r3[0].threshold is None and r3[0].labels == 120,
          "120 labels with NO score produce no threshold")
    check("NO item carries a score" in r3[0].note and "must not be invented" in r3[0].note,
          f"...with a DIFFERENT reason from too-few-labels: the score is missing, not the "
          f"labels ({r3[0].note[:50]!r})")
    check(r3[0].note != r[0].note,
          "...so the two ways of being unready are distinguishable in the report")

    # ── a rank the sample cannot support ───────────────────────────────────
    few = ([Label("t", "b", REJECTED, 1.0)] * 3) + ([Label("t", "b", APPROVED)] * 100)
    r4 = calibrate(few, alpha=0.01)
    check(r4[0].threshold is None and "cannot support" in r4[0].note,
          f"3 scored rejections cannot support alpha=0.01: the conformal rank exceeds the "
          f"sample, and NO threshold is returned rather than the largest score wearing "
          f"one ({r4[0].note[:40]!r})")

    # ── buckets are per (task, body) ───────────────────────────────────────
    mixed = many(5, task="research_question", body="CA2013") + \
            many(7, task="review_contract", body="CA2013") + \
            many(3, task="research_question", body="SEBI_LODR")
    r5 = calibrate(mixed)
    check([(x.task, x.body, x.labels) for x in r5]
          == [("research_question", "CA2013", 5), ("research_question", "SEBI_LODR", 3),
              ("review_contract", "CA2013", 7)],
          f"labels bucket per (task, body) and the buckets are independent "
          f"({[(x.task, x.body, x.labels) for x in r5]})")
    unlabelled = calibrate([Label("", "", REJECTED, 1.0)])
    check(unlabelled[0].task == "(task not recorded)"
          and unlabelled[0].body == "(body not recorded)",
          "a decision with no task or body is bucketed as NOT RECORDED, never merged into "
          "a real bucket where it would move a real threshold")

    # ── no accuracy claim, anywhere ────────────────────────────────────────
    words = " ".join(x.note for x in calibrate(scored) + r + r3).lower()
    for banned in ("accuracy", "accurate", "% correct", "precision of", "error rate of"):
        check(banned not in words,
              f"no note claims {banned!r}: this module measures where REVIEW EFFORT should "
              f"go, and says nothing about how often the engine is right")
    check(all("threshold" in x.to_dict() and "minimum" in x.to_dict()
              for x in calibrate(scored)),
          "to_dict reports the threshold and the floor it had to clear")

    # ── the nonconformity score the founder specified ──────────────────────
    check(ESCALATION_WEIGHT == 0.5, "the escalation weight is 0.5")
    check(nonconformity(verified=10, total=10, escalations=0)[0] == 0.0,
          "every sentence supported and no escalation scores 0 -- perfectly conforming")
    check(nonconformity(verified=0, total=10, escalations=0)[0] == 1.0,
          "nothing supported scores 1")
    check(nonconformity(verified=5, total=10, escalations=0)[0] == 0.5,
          "half supported scores 0.5")
    check(nonconformity(verified=10, total=10, escalations=2)[0] == 1.0,
          "...and two escalations add 1.0, so escalation alone can match total failure "
          "-- which is the weight the founder chose, not one this file picked")
    check(nonconformity(verified=8, total=10, escalations=1)[0] == 0.7,
          f"(1 - 0.8) + 0.5*1 = 0.7 "
          f"({nonconformity(verified=8, total=10, escalations=1)[0]})")
    check(nonconformity(verified=3, total=4, escalations=0)[1].startswith("3/4"),
          "...and the reason shows the fraction it came from")

    _none, _why = nonconformity(verified=0, total=0, escalations=0)
    check(_none is None,
          "**a run with NO sentences scores None, not 1.0**: zero of zero is 'there was "
          "nothing to support', and a refusal scoring maximally nonconforming would drag "
          "every threshold computed from it")
    check("not 'nothing was supported'" in _why, "...and says so")
    for bad in ((11, 10, 0), (-1, 10, 0)):
        try:
            nonconformity(verified=bad[0], total=bad[1], escalations=bad[2])
            check(False, f"verified={bad[0]} of {bad[1]} raises")
        except CalibrationError:
            check(True, f"verified={bad[0]} of total={bad[1]} RAISES: a count outside its "
                        f"own denominator means the two measured different things")
    try:
        nonconformity(verified=1, total=2, escalations=-1)
        check(False, "negative escalations raise")
    except CalibrationError:
        check(True, "negative escalations raise")

    # ── what a served module may and may not take from this file ───────────
    #
    # The original rule was "nothing served imports this at all", and it broke the day the
    # founder asked for the nonconformity SCORE to be recorded on every run -- which means
    # `gateway/verbs.py` has to import something from here.
    #
    # The rule was too broad, not wrong. What must never reach the answer path is the
    # THRESHOLD: a number computed from past decisions, used to decide a present legal
    # question. RECORDING a measurement is not deciding with it. So the check now names
    # what may cross and asserts the rest does not.
    SCORE_API = {"nonconformity", "ESCALATION_WEIGHT", "CalibrationError"}
    DECIDING_API = {"calibrate", "Readiness", "MIN_LABELS", "Label", "bucket_labels"}
    import ast as _ast
    import pathlib as _pl
    root = _pl.Path(__file__).resolve().parent.parent
    offenders, importers = [], []
    for path in list((root / "gateway").glob("*.py")) + list((root / "agents").glob("*.py")) \
            + list((root / "checker").glob("*.py")):
        if path.name == "calibration.py":
            continue
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom) and "calibration" in (node.module or ""):
                importers.append(path.name)
                for alias in node.names:
                    if alias.name in DECIDING_API:
                        offenders.append(f"{path.name}:{alias.name}")
            elif isinstance(node, _ast.Import) and any(
                    "calibration" in a.name for a in node.names):
                # A whole-module import takes everything, including the threshold API.
                offenders.append(f"{path.name}:<whole module>")
    check(not offenders,
          f"NO served module imports the DECIDING api {sorted(DECIDING_API)} -- a "
          f"threshold reaching the answer path would be a number from past decisions "
          f"deciding a present legal question ({offenders})")
    check(set(importers) <= {"verbs.py"},
          f"...and only gateway/verbs.py imports this file at all, to RECORD the score "
          f"({sorted(set(importers))})")
    check(SCORE_API & DECIDING_API == set(),
          "the two halves of this module's api do not overlap, so 'may import' and 'may "
          "not' is a decidable question rather than a judgement call")

    try:
        calibrate([{"task": "x"}])
        check(False, "a dict label raises")
    except CalibrationError:
        check(True, "a dict instead of a Label RAISES: it would be bucketed with no task "
                    "and silently counted")
    try:
        calibrate(many(100), alpha=1.5)
        check(False, "an impossible alpha raises")
    except CalibrationError:
        check(True, "an alpha outside (0,1) raises")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
