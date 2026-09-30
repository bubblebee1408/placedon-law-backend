#!/usr/bin/env python3
"""Can retrieval find a section when you describe it? Measured, with no answer key.

R1. H0 left the gold set's remaining failures on both sides of retrieval: answer rows where
"the governing provision never reached the pack", and refusal rows that came back holding
Companies Act provisions. Neither can be worked on without a number, and the gold set is 30
scored rows -- too few to tune against, and half of them held out.

## The trick that removes the answer key

**Every section's own heading is a query whose right answer is that section.** Nobody labels
it; the corpus labels itself. "Meetings of Board" must retrieve s.173, and if it does not, no
practitioner phrasing of a board-meeting question is going to.

That makes a 500-case eval out of a corpus of 500 sections, and it is honest about what it
measures. It is an EASY set: real questions are not headings, and a system that scores 1.00
here can still fail every practitioner phrasing. What it catches is the floor -- a section
that cannot be found by its own title is unreachable by anything.

So this reports two numbers and never merges them:

    title recall@1 / @5   the floor, mechanical, the whole corpus
    dev-row recall@5      the gold set's dev rows against their own `expected_refs`

## The held-out split is not read here

`eval/goldset/split.py` decides which rows are dev. This reads dev only, and never opens a
held-out row -- not to score it, not to print it. H0 spent the one held-out run this change
is allowed, and a retrieval number computed over rows we then tune against is the overfitting
the split exists to prevent.

Run:  PYTHONPATH=. python3 scripts/retrieval_recall.py
      PYTHONPATH=. python3 scripts/retrieval_recall.py --misses
      PYTHONPATH=. python3 scripts/retrieval_recall.py --test
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus" / "companies_act"
GOLD = ROOT / "eval" / "goldset" / "questions.jsonl"

# A heading that is only a number, or an omitted provision, is not a query. Excluded and
# COUNTED, so the denominator is stated rather than quietly shrunk.
_OMITTED = re.compile(r"\bomitted\b", re.I)


def live_sections() -> list[tuple[str, str]]:
    """(section_number, heading) for every live section with a usable heading.

    Read from the RETRIEVER'S OWN index rather than from the corpus files, and that is the
    point rather than a shortcut: the corpus JSON carries `section_id` and `content` and no
    heading at all, so a first version reading `corpus/companies_act/*.json` for a `heading`
    field measured 0 sections and reported a clean 0/0. A recall eval whose denominator can
    silently be zero is worse than none. These are the exact records `search()` ranks, so a
    section missing here is a section the retriever cannot see either.
    """
    from checker.text_search import _records

    out = []
    for rec in _records():
        num = str(rec.get("section_number") or "").strip()
        title = str(rec.get("title") or "").strip()
        if not num or not title:
            continue
        if _OMITTED.search(title) or len(title) < 4:
            continue
        out.append((num, title))
    return out


def title_recall(sections=None, *, top_k: int = 5) -> dict:
    """Each section's heading as its own query. Returns counts and the misses."""
    from checker.text_search import search

    rows = sections if sections is not None else live_sections()
    at1 = at5 = 0
    misses = []
    for num, title in rows:
        hits = search(title, top_k=top_k)
        got = [h["section_number"] for h in hits]
        if got[:1] == [num]:
            at1 += 1
        if num in got:
            at5 += 1
        else:
            misses.append((num, title, got[:3]))
    return {"n": len(rows), "at1": at1, "at5": at5, "misses": misses}


def _dev_ids() -> set:
    from eval.goldset.split import ids_for
    return set(ids_for("dev"))


def dev_recall(*, top_k: int = 5) -> dict:
    """The dev rows that name a governing provision, and whether retrieval reaches it.

    Only rows with `expected_refs`. A refusal row names none, so it is not a recall case --
    counting it would mix two different questions into one number.
    """
    from checker.text_search import search

    dev = _dev_ids()
    hit = 0
    cases, misses = [], []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["question_id"] not in dev or not r.get("expected_refs"):
            continue
        want = {m.group(1) for ref in r["expected_refs"]
                for m in [re.search(r":S(\d+[A-Z]*)$", ref)] if m}
        if not want:
            continue
        cases.append(r["question_id"])
        got = [h["section_number"] for h in search(r["question"], top_k=top_k)]
        if want & set(got):
            hit += 1
        else:
            misses.append((r["question_id"], sorted(want), got[:5]))
    return {"n": len(cases), "hit": hit, "misses": misses}


def report(*, show_misses: bool = False, top_k: int = 5) -> str:
    t = title_recall(top_k=top_k)
    d = dev_recall(top_k=top_k)
    lines = [
        "RETRIEVAL RECALL -- two numbers, never merged.",
        "",
        f"  title-as-query, every live section   n={t['n']}",
        f"    recall@1  {t['at1']}/{t['n']}",
        f"    recall@5  {t['at5']}/{t['n']}",
        "    An EASY set: a heading is not a question. It measures the floor -- a section",
        "    its own title cannot reach is unreachable by any phrasing.",
        "",
        f"  gold-set DEV rows naming a provision  n={d['n']}",
        f"    recall@{top_k}  {d['hit']}/{d['n']}",
        "    The held-out split is not read here.",
    ]
    if show_misses:
        lines += ["", f"  {len(t['misses'])} title miss(es):"]
        lines += [f"    s.{num:<6} {title[:52]:<54} got {got}"
                  for num, title, got in t["misses"][:40]]
        lines += ["", f"  {len(d['misses'])} dev miss(es):"]
        lines += [f"    {qid:<22} wanted {want} got {got}" for qid, want, got in d["misses"]]
    return "\n".join(lines)


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

    secs = live_sections()
    check(len(secs) > 300, f"the index yields a real eval set ({len(secs)} sections)")
    # The denominator must never be able to go quietly to zero -- it did, on the first
    # version, which read a field the corpus does not have and reported a clean 0/0.
    check(secs and all(n and t for n, t in secs),
          "...with a NON-EMPTY denominator: a recall eval that can report 0/0 and look "
          "clean is worse than no eval")
    check(all(n and t for n, t in secs), "...every case has a number and a heading")
    check(not any(_OMITTED.search(t) for _n, t in secs),
          "...and omitted provisions are excluded, not scored as misses")

    # The harness must be able to FAIL. A selector that returns nothing scores 0.
    import checker.text_search as ts
    real = ts.search
    try:
        ts.search = lambda q, top_k=5: []
        blind = title_recall(secs[:20])
        check(blind["at1"] == 0 and blind["at5"] == 0 and len(blind["misses"]) == 20,
              f"a retriever that finds nothing scores 0/20 -- the harness can turn red "
              f"({blind['at1']}, {blind['at5']})")
        ts.search = lambda q, top_k=5: [{"section_number": secs[0][0]}]
        fixed = title_recall(secs[:3])
        check(fixed["at1"] == 1, "...and one that always returns s.%s scores exactly the "
                                 "one case that is right" % secs[0][0])
    finally:
        ts.search = real

    # A small live slice, so the gate exercises the real path without scanning 500 sections.
    live = title_recall(secs[:25])
    check(live["at5"] >= live["at1"], "recall@5 is never below recall@1")
    check(live["at5"] > 0, f"the real retriever finds something ({live['at5']}/25)")

    d = dev_recall()
    check(d["n"] > 0, f"the dev split has rows naming a provision ({d['n']})")
    heldout = _dev_ids()
    check(all(qid in heldout for qid, _w, _g in d["misses"]),
          "every row this reports is a DEV row -- the held-out split is never read")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(report(show_misses="--misses" in sys.argv))
