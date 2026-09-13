"""Measure date-conditioned retrieval against a naive current-corpus baseline.

FiscalQA (arXiv 2608.09393) reports that naive RAG over a current-version corpus
retrieves the date-applicable provision almost never, and cites a real but
inapplicable version with full confidence. This repository is built the other
way. The claim that this matters has been made in its documents for months
without a number attached to it. This produces the number, on our own law.

## Two conditions, one difference

    A  NAIVE_CURRENT     ignores the query date and returns whatever version is
                         in force today. This is not a strawman -- it is what a
                         consolidated Act, a commercial database's "current
                         text", and a vector index over today's corpus all do.
    B  DATE_CONDITIONED  selects the version whose [effective_from, effective_to]
                         contains the query date, and refuses when none does.

The only difference is whether effective-date metadata is consulted. Not the
embedding, not the ranker, not the prompt.

## Deterministic scoring, and why an LLM judge is disqualified

Every gold answer is a nugget: a number with a tolerance, or a regex on an
instrument name. A model asked to grade these would bring the same recency prior
that condition A is being measured for -- shown a 2024 question answered with the
2025 figure, it has a documented tendency to accept the newer number as "the
right answer, just updated". A judge that shares the bias cannot measure it.

## Refusal is scored, not excused

Three question classes have no servable answer here: dates before any held
version, the criminal codes (held as commencement dates only -- the text is not
in the corpus), and the allotment window (registered but unattested). For those
the correct output is a refusal, and a condition that answers anyway scores
WRONG_ANSWER. A benchmark that dropped them would be measuring only the cases
the system is good at.

Run: python3 eval/temporal/harness.py
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
CORPUS = ROOT / "corpus" / "versions.json"
GOLD = ROOT / "gold.csv"

NAIVE_CURRENT = "A_NAIVE_CURRENT"
DATE_CONDITIONED = "B_DATE_CONDITIONED"

# ── outcomes ─────────────────────────────────────────────────────────────────
CORRECT_ANSWER = "CORRECT_ANSWER"
CORRECT_REFUSAL = "CORRECT_REFUSAL"
WRONG_ANSWER = "WRONG_ANSWER"        # answered, and wrong. The costly one.
WRONG_REFUSAL = "WRONG_REFUSAL"      # refused when an answer was available.
OUTCOMES = (CORRECT_ANSWER, CORRECT_REFUSAL, WRONG_ANSWER, WRONG_REFUSAL)

REFUSE = "__REFUSE__"

# Instruments whose TEXT this repo does not hold, or holds unattested. A version
# row existing in the mini-corpus is not the same as the law being servable, and
# collapsing the two is the error the whole repository is built against.
NOT_SERVABLE = {
    "criminal.substantive_code": "the code text is not in the corpus; "
                                 "code_transition returns INSTRUMENT_NOT_HELD",
    "criminal.procedural_code": "the code text is not in the corpus; "
                                "code_transition returns INSTRUMENT_NOT_HELD",
    "allotment.return_window_days": "registered but PENDING_HUMAN_REVIEW; "
                                    "storage is not review",
}


@dataclass(frozen=True)
class Version:
    value: object
    display: str
    effective_from: date
    effective_to: date | None
    instrument: str

    def covers(self, d: date) -> bool:
        if d < self.effective_from:
            return False
        return self.effective_to is None or d <= self.effective_to


@dataclass(frozen=True)
class Instrument:
    key: str
    question_form: str
    unit: str
    provenance: str
    versions: tuple[Version, ...]

    @property
    def servable(self) -> bool:
        return self.key not in NOT_SERVABLE

    def current(self) -> Version | None:
        open_ended = [v for v in self.versions if v.effective_to is None]
        if open_ended:
            return max(open_ended, key=lambda v: v.effective_from)
        return max(self.versions, key=lambda v: v.effective_from, default=None)

    def at(self, d: date) -> Version | None:
        for v in self.versions:
            if v.covers(d):
                return v
        return None


def load_corpus() -> dict[str, Instrument]:
    raw = json.loads(CORPUS.read_text())
    out = {}
    for i in raw["instruments"]:
        vs = tuple(Version(
            v["value"], v["display"], date.fromisoformat(v["effective_from"]),
            date.fromisoformat(v["effective_to"]) if v["effective_to"] else None,
            v["instrument"]) for v in i["versions"])
        out[i["key"]] = Instrument(i["key"], i["question_form"], i["unit"],
                                   i["provenance"], vs)
    return out


# ── the two retrieval conditions ─────────────────────────────────────────────

def retrieve(condition: str, inst: Instrument, query_date: date):
    """Return the Version this condition would serve, or None to refuse."""
    if not inst.servable:
        # Both conditions face the same fact: we do not hold the text. A
        # condition is being measured on its DATE handling, not on whether it
        # will invent law we never acquired.
        return None
    if condition == NAIVE_CURRENT:
        return inst.current()          # the date is not consulted. That is the point.
    if condition == DATE_CONDITIONED:
        return inst.at(query_date)
    raise ValueError(f"unknown condition {condition!r}")


# ── deterministic scoring ────────────────────────────────────────────────────

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def nugget_matches(gold: str, unit: str, served) -> bool:
    """Does the served version satisfy the gold nugget? Regex or number only."""
    if served is None:
        return gold == REFUSE
    if gold == REFUSE:
        return False
    if unit in ("INR", "DAYS"):
        want = _NUM.search(gold)
        if not want:
            return False
        target = float(want.group())
        try:
            got = float(served.value)
        except (TypeError, ValueError):
            return False
        # Tolerance is absolute-zero for money and periods on purpose. A
        # threshold is exact; "approximately four crore" is not a legal position.
        return abs(got - target) < 0.5
    # SELECTION: a regex on the instrument or the value.
    pat = re.compile(gold, re.I)
    return bool(pat.search(str(served.value)) or pat.search(served.instrument))


def score_one(condition: str, inst: Instrument, query_date: date,
              gold: str) -> tuple[str, str]:
    served = retrieve(condition, inst, query_date)
    hit = nugget_matches(gold, inst.unit, served)
    if gold == REFUSE:
        return (CORRECT_REFUSAL if served is None else WRONG_ANSWER,
                "refused" if served is None else f"answered {served.display}")
    if served is None:
        return WRONG_REFUSAL, "refused when an answer was available"
    return (CORRECT_ANSWER if hit else WRONG_ANSWER,
            f"served {served.display} ({served.instrument})")


# ── gold set ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Question:
    qid: str
    instrument_key: str
    query_date: date
    question: str
    gold: str
    note: str = ""

    @property
    def pending_human(self) -> bool:
        return self.gold.strip().upper() == "PENDING_HUMAN"


def load_gold() -> list[Question]:
    out = []
    with GOLD.open() as f:
        for row in csv.DictReader(f):
            out.append(Question(row["qid"], row["instrument_key"],
                                date.fromisoformat(row["query_date"]),
                                row["question"], row["gold"], row.get("note", "")))
    return out


def run() -> dict:
    corpus, gold = load_corpus(), load_gold()
    scored = [q for q in gold if not q.pending_human]
    pending = [q for q in gold if q.pending_human]

    results = {NAIVE_CURRENT: [], DATE_CONDITIONED: []}
    for q in scored:
        inst = corpus[q.instrument_key]
        for cond in (NAIVE_CURRENT, DATE_CONDITIONED):
            outcome, detail = score_one(cond, inst, q.query_date, q.gold)
            results[cond].append((q, outcome, detail))
    return {"corpus": corpus, "scored": scored, "pending": pending,
            "results": results}


def tally(rows) -> dict[str, int]:
    t = {o: 0 for o in OUTCOMES}
    for _, outcome, _ in rows:
        t[outcome] += 1
    return t


def accuracy(rows) -> float:
    if not rows:
        return 0.0
    good = sum(1 for _, o, _ in rows if o in (CORRECT_ANSWER, CORRECT_REFUSAL))
    return good / len(rows)


def answerable_accuracy(rows) -> tuple[float, int]:
    """Accuracy restricted to questions that HAVE a servable answer.

    Reported separately because a benchmark heavy with refusal cases can show a
    high headline score for a system that only ever refuses. This is the number
    that cannot be gamed by abstaining.
    """
    sub = [(q, o, d) for q, o, d in rows if q.gold != REFUSE]
    if not sub:
        return 0.0, 0
    return sum(1 for _, o, _ in sub if o == CORRECT_ANSWER) / len(sub), len(sub)


def historical_accuracy(rows, corpus) -> tuple[float, int]:
    """Accuracy on answerable questions whose date is NOT in the current window.

    This is the sharpest cut and the one closest to the published finding. Naive
    retrieval is not wrong everywhere -- it is right by coincidence whenever the
    question happens to be about today, which is why the headline numbers
    understate the gap. Restricting to historical dates removes the coincidence.
    """
    sub = []
    for q, o, d in rows:
        if q.gold == REFUSE:
            continue
        inst = corpus[q.instrument_key]
        cur = inst.current()
        if cur is not None and not cur.covers(q.query_date):
            sub.append((q, o, d))
    if not sub:
        return 0.0, 0
    return sum(1 for _, o, _ in sub if o == CORRECT_ANSWER) / len(sub), len(sub)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("temporal harness")
    r = run()
    A, B = r["results"][NAIVE_CURRENT], r["results"][DATE_CONDITIONED]

    ta, tb = tally(A), tally(B)
    acc_a, acc_b = accuracy(A), accuracy(B)
    ans_a, n_ans = answerable_accuracy(A)
    ans_b, _ = answerable_accuracy(B)

    print(f"\n  scored questions      {len(r['scored'])}")
    print(f"  pending human         {len(r['pending'])}")
    print(f"  A naive-current       {acc_a:.0%} overall | {ans_a:.0%} on the "
          f"{n_ans} answerable | {ta}")
    hist_a, n_hist = historical_accuracy(A, r["corpus"])
    hist_b, _ = historical_accuracy(B, r["corpus"])
    print(f"  B date-conditioned    {acc_b:.0%} overall | {ans_b:.0%} on the "
          f"{n_ans} answerable | {tb}")
    print(f"  historical only ({n_hist})  A {hist_a:.0%}  vs  B {hist_b:.0%}\n")

    check(len(r["scored"]) >= 20,
          f"at least 20 questions are scored ({len(r['scored'])})")
    check(ans_b == 1.0,
          f"date-conditioned retrieval is exact on every answerable question "
          f"({ans_b:.0%})")
    check(ans_a < 0.6,
          f"naive current-corpus retrieval collapses on them ({ans_a:.0%}) -- if "
          f"this were high the mini-corpus would not actually be versioned")
    check(hist_a == 0.0 and hist_b == 1.0,
          f"on the {n_hist} questions whose date is NOT in the current window -- "
          f"the cut that removes coincidence -- naive scores {hist_a:.0%} and "
          f"date-conditioned scores {hist_b:.0%}")
    check(ta[WRONG_ANSWER] > 0 and tb[WRONG_ANSWER] == 0,
          f"the naive condition produces {ta[WRONG_ANSWER]} confident wrong "
          f"answers; the date-conditioned one produces {tb[WRONG_ANSWER]}")
    check(tb[WRONG_REFUSAL] == 0,
          "...and does not buy that by refusing when an answer existed")

    # The refusal cases must be genuinely testing something.
    refusals = [q for q in r["scored"] if q.gold == REFUSE]
    check(len(refusals) >= 6,
          f"{len(refusals)} questions require a refusal -- unheld law, unattested "
          f"artifacts, and dates before any held version")
    check(all(o == CORRECT_REFUSAL for _, o, _ in B if _.gold == REFUSE
              ) if False else
          all(o == CORRECT_REFUSAL for q, o, _ in B if q.gold == REFUSE),
          "the date-conditioned condition refuses every one of them")

    # A pre-window date is the case a versioned index must NOT answer.
    early = [q for q in r["scored"]
             if q.instrument_key.startswith("small_company")
             and q.query_date < date(2022, 9, 15)]
    check(early, "the set contains dates before any held version")
    for q in early:
        outcome, _ = score_one(DATE_CONDITIONED, r["corpus"][q.instrument_key],
                               q.query_date, q.gold)
        check(outcome == CORRECT_REFUSAL,
              f"{q.qid}: a date before the earliest held version is refused, not "
              f"answered with the oldest one we happen to have")

    # No judge. Asserted structurally, because this is the rule most likely to
    # rot: someone adds a hard question and reaches for a model to grade it.
    #
    # Checked by PARSING IMPORTS, not by searching for the word. The first version
    # searched the source text and failed on its own docstring, which explains why
    # an LLM judge is disqualified -- the same mistake made earlier this week in
    # model_adapter, where counting "<source>" also counted the sentence
    # documenting "<source>". A check that greps for a token counts the
    # documentation of that token.
    import ast
    tree = ast.parse(Path(__file__).read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    banned = roots & {"anthropic", "openai", "google", "genai", "requests",
                      "httpx", "urllib"}
    check(not banned,
          f"the harness imports no model or network library ({banned or 'clean'}) "
          f"-- scoring is regex and numbers, and a judge that shares the recency "
          f"bias cannot measure it")
    check("checker" not in roots,
          "...and it does not import the currency engine either: the benchmark "
          "measures a retrieval strategy, not this repo's implementation of one, "
          "so a bug in the engine cannot flatter its own score")

    check(nugget_matches("40000000", "INR",
                         Version(40000000, "x", date(2022, 9, 15), None, "i")),
          "a numeric nugget matches on exact value")
    check(not nugget_matches("40000000", "INR",
                             Version(100000000, "x", date(2025, 12, 1), None, "i")),
          "...and does not match the newer figure, which is the whole measurement")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
