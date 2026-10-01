#!/usr/bin/env python3
"""One pass, three candidate rankers, three metrics, and a rule decided before the numbers.

R1 follow-up. `checker/text_search.py` ranks without BM25's document-length normalisation,
and its docstring says why in measured terms:

> With b=0.6 the length prior pushed s.173 below s.146 for "can a director attend by video" --
> the correct answer lost to a section about auditors, purely for being long. Measured, then
> removed.

That is a real finding, not a preference, so re-adding the prior needs more than a hunch. This
runs the comparison once and writes the table down whatever it says.

## The candidates

    a  control          the ranker as it ships
    b  length-normalised   BM25 tf saturation WITH the length prior, b in {0.25, 0.5, 0.75}
    c  title prior       control, plus a multiplicative bonus when the heading matches

(b) changes ONLY the body term weight. Title gain, phrase bonuses and the floors are left
exactly as they are, so the length prior is the single variable and the docstring's finding is
tested rather than argued with.

(c)'s constant is fixed at 0.5 BEFORE running -- the same magnitude as the existing
`TITLE_PHRASE_BONUS` -- and is not swept. A constant chosen after seeing the table is a
constant fitted to 13 rows.

## The rule, written before the numbers

A candidate wins only if ALL THREE hold:

    1. it breaks no dev answer row that passes today
    2. title recall@1 does not drop
    3. dev refusal leaks do not rise

More than one winner: the simplest is taken. No winner: the control stays. There is no second
round of variants -- a bake-off that keeps going until something wins is a search for a number,
not a test.

## What this is measured on, and what that is worth

Thirteen dev answer rows, seventeen dev refusal rows, and 464 section headings. **The held-out
split is neither run nor read.** Thirteen rows cannot support an accuracy claim about anything,
and none is made here: the table says which candidate did not break what, on this set, today.

Run:  PYTHONPATH=. python3 scripts/retrieval_bakeoff.py
      PYTHONPATH=. python3 scripts/retrieval_bakeoff.py --test
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLD = ROOT / "eval" / "goldset" / "questions.jsonl"

# Fixed before the run. See the module docstring.
BM25_K1 = 1.2
TITLE_PRIOR = 0.5


def _gold(kind: str) -> list:
    from eval.goldset.split import ids_for

    dev = set(ids_for("dev"))
    out = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["question_id"] in dev and r["expected"] == kind:
            out.append(r)
    return out


def _wanted(row) -> set:
    return {m.group(1) for ref in row.get("expected_refs") or []
            for m in [re.search(r":S(\d+[A-Z]*)$", ref)] if m}


# ── the candidate scorers ────────────────────────────────────────────────────
# Each has the signature of checker.text_search._score and returns the same dict, so the rest
# of the ranker -- floors, ordering, top_k -- is untouched and only the scoring changes.

def _control(ts):
    return ts._score


def _length_normalised(ts, b: float):
    """BM25 tf saturation with the length prior, on the BODY term only.

    dl is the record's total term count and avgdl the corpus mean, both from the index the
    ranker already builds. Title evidence and phrases are left alone: the docstring's claim is
    about the length prior, so the length prior is the only thing that changes.
    """
    lengths = {id(rec): sum(rec["tf"].values()) or 1 for rec in ts._records()}
    avgdl = sum(lengths.values()) / max(len(lengths), 1)

    def score(rec, terms, phrases, qmass):
        title_hits = [t for t in terms if t in rec["title_stems"]]
        body_hits = [t for t in terms if rec["tf"].get(t)]
        gain = ts.TITLE_GAIN * ts._title_precision(rec, title_hits) if title_hits else 0.0
        dl = lengths.get(id(rec), 1)
        norm = 1.0 - b + b * dl / avgdl

        evidence = 0.0
        for term in terms:
            weight = 0.0
            if term in rec["title_stems"]:
                weight = gain
            tf = rec["tf"].get(term, 0)
            if tf:
                bm = (tf * (BM25_K1 + 1.0)) / (tf + BM25_K1 * norm)
                # Scaled to the control's body range so the floors keep their meaning: the
                # control's body weight tops out just below 1.0.
                weight = max(weight, bm / (BM25_K1 + 1.0))
            evidence += ts._idf(term) * weight

        title_phrase = body_phrase = 0.0
        matched = ""
        for gram, mass in phrases:
            if gram in rec["title_seq"] and mass > title_phrase * qmass:
                title_phrase, matched = mass / qmass, gram
            if gram in rec["body_seq"] and mass > body_phrase * qmass:
                body_phrase = mass / qmass
                matched = matched or gram
        s = (evidence / qmass + gain * ts.TITLE_PHRASE_BONUS * title_phrase
             + ts.BODY_PHRASE_BONUS * body_phrase)
        cover = ts._mass(dict.fromkeys(title_hits + body_hits)) / qmass
        return {"score": s, "cover": cover, "title_hits": title_hits,
                "body_hits": body_hits, "phrase": matched.strip()}

    return score


def _title_prior(ts):
    """Control, multiplied by (1 + TITLE_PRIOR x how much of the heading the query accounts
    for). A section whose whole heading is the question gains most; one that merely contains
    the words gains least."""
    base = ts._score

    def score(rec, terms, phrases, qmass):
        out = base(rec, terms, phrases, qmass)
        if out["title_hits"]:
            out["score"] *= 1.0 + TITLE_PRIOR * ts._title_precision(rec, out["title_hits"])
        return out

    return score


def candidates(ts) -> list:
    return [("a  control", _control(ts)),
            ("b  bm25 b=0.25", _length_normalised(ts, 0.25)),
            ("b  bm25 b=0.50", _length_normalised(ts, 0.50)),
            ("b  bm25 b=0.75", _length_normalised(ts, 0.75)),
            ("c  title prior", _title_prior(ts))]


# ── the metrics ──────────────────────────────────────────────────────────────

def measure(ts, scorer, *, sections=None) -> dict:
    """Three numbers and the set of dev answer rows that passed."""
    real = ts._score
    try:
        ts._score = scorer
        passing, misses = set(), []
        for row in _gold("SHOULD_ANSWER"):
            want = _wanted(row)
            if not want:
                continue
            got = {h["section_number"] for h in ts.search(row["question"], top_k=5)}
            if want & got:
                passing.add(row["question_id"])
            else:
                misses.append(row["question_id"])
        leaks = sum(1 for r in _gold("SHOULD_REFUSE") if ts.search(r["question"], top_k=5))
        recs = sections if sections is not None else ts._records()
        at1 = sum(1 for rec in recs
                  if [h["section_number"] for h in ts.search(rec["title"], top_k=5)][:1]
                  == [rec["section_number"]])
        return {"passing": passing, "misses": misses, "leaks": leaks,
                "at1": at1, "n_sections": len(recs)}
    finally:
        ts._score = real


def verdict(control: dict, cand: dict) -> tuple[bool, str]:
    """The rule, applied. Written before the numbers; see the module docstring."""
    broke = sorted(control["passing"] - cand["passing"])
    if broke:
        return False, f"breaks {broke}"
    if cand["at1"] < control["at1"]:
        return False, f"title recall@1 drops {control['at1']} -> {cand['at1']}"
    if cand["leaks"] > control["leaks"]:
        return False, f"refusal leaks rise {control['leaks']} -> {cand['leaks']}"
    gained = sorted(cand["passing"] - control["passing"])
    return True, ("wins" + (f", and gains {gained}" if gained else ", gaining nothing"))


def run() -> tuple[str, list]:
    import checker.text_search as ts

    secs = ts._records()
    rows = []
    control = measure(ts, _control(ts), sections=secs)
    for name, scorer in candidates(ts):
        m = control if name.startswith("a ") else measure(ts, scorer, sections=secs)
        ok, why = (True, "control") if name.startswith("a ") else verdict(control, m)
        rows.append((name, m, ok, why))

    n_ans = len(control["passing"]) + len(control["misses"])
    out = ["RETRIEVAL BAKE-OFF -- one pass, rule fixed before the numbers.",
           "",
           f"  {'candidate':<16}{'answer@5':>10}{'leaks':>8}{'title@1':>10}  verdict",
           f"  {'-' * 58}"]
    for name, m, ok, why in rows:
        out.append(f"  {name:<16}{len(m['passing'])}/{n_ans:<8}{m['leaks']}/17{'':>3}"
                   f"{m['at1']}/{m['n_sections']:<5}  {'WIN ' if ok else 'lose'} {why}")
    out += ["",
            f"  Measured on {n_ans} dev answer rows, 17 dev refusal rows and "
            f"{control['n_sections']} headings.",
            "  Thirteen rows cannot support an accuracy claim, and none is made.",
            "  The held-out split was neither run nor read."]
    return "\n".join(out), rows


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

    import checker.text_search as ts

    # The rule, on synthetic results -- it must reject for each reason on its own.
    base = {"passing": {"x", "y"}, "misses": [], "leaks": 3, "at1": 452, "n_sections": 464}
    okc, why = verdict(base, dict(base))
    check(okc and "gaining nothing" in why, f"an identical candidate wins and says so ({why})")
    okc, why = verdict(base, dict(base, passing={"x"}))
    check(not okc and "breaks ['y']" in why, f"...breaking a passing row loses ({why})")
    okc, why = verdict(base, dict(base, at1=451))
    check(not okc and "title recall@1 drops" in why, f"...a title-recall drop loses ({why})")
    okc, why = verdict(base, dict(base, leaks=4))
    check(not okc and "leaks rise" in why, f"...more refusal leaks lose ({why})")
    okc, why = verdict(base, dict(base, passing={"x", "y", "z"}))
    check(okc and "gains ['z']" in why, f"...and a strict gain wins, naming it ({why})")

    # Every candidate must be a working scorer over the real index.
    secs = ts._records()[:8]
    for name, scorer in candidates(ts):
        m = measure(ts, scorer, sections=secs)
        check(isinstance(m["at1"], int) and m["n_sections"] == 8,
              f"{name} runs over the real index")
    check(ts._score.__name__ == "_score",
          "...and the module's own scorer is restored afterwards, every time")

    check(TITLE_PRIOR == ts.TITLE_PHRASE_BONUS,
          f"(c)'s constant is the same magnitude as the existing title phrase bonus "
          f"({TITLE_PRIOR}), fixed before the run rather than swept")

    from eval.goldset.split import ids_for
    dev = set(ids_for("dev"))
    check(all(r["question_id"] in dev for r in _gold("SHOULD_ANSWER") + _gold("SHOULD_REFUSE")),
          "every row measured is a DEV row -- the held-out split is never read")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    text, _rows = run()
    print(text)
