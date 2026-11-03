"""Does Ask's search land on the right section? A fixed question set, before and after.

Measures what `/v1/ask` actually reads: `retrieve.retrieve()` -> the usable provisions of its
evidence pack, in order. (`hybrid_search` adds dense retrieval only when a Voyage key and index
exist; the gate has neither, so this is the lexical ranking in `checker/text_search.py`.)

"Before" is the same code with `text_search.RANKING_HINTS = False` -- no title-match bonus, no
draft topic hints -- so both numbers come from one run and cannot drift apart.

Every expected section was checked against `corpus/companies_act/_index.json` titles and the
section text on 2026-11-01. The labels are ENGINEERING labels, not a lawyer's: each names the
section whose heading is the question's subject. They are not an accuracy claim, and the set
was written and the ranking tuned against it in the same change -- read the after-number as
"these questions now work", not as a held-out score. The independent checks are
`scripts/retrieval_recall.py` and `scripts/retrieval_dev_metrics.py` (gold-set dev rows and
every section heading), which this change did not tune on.

Run: PYTHONPATH=. python3 checker/section_eval.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import text_search
from checker.retrieve import retrieve

# (question, expected section). "" = off-topic: the right answer is no section at all.
CASES: tuple[tuple[str, str], ...] = (
    # the four measured failures and their neighbours
    ("What is the quorum for a board meeting?", "174"),
    ("How many directors are needed for quorum at a board meeting?", "174"),
    ("What is the quorum for an AGM?", "103"),
    ("How many members must be present for quorum at a general meeting?", "103"),
    ("What is the notice period for a general meeting?", "101"),
    ("How many days notice is required to call a general meeting?", "101"),
    ("Who can be an independent director?", "149"),
    ("How many independent directors must a listed company have?", "149"),
    # the topics in PR #143's map
    ("Within how many months must the AGM be held?", "96"),
    ("What is the maximum gap between two annual general meetings?", "96"),
    ("How often must the board meet in a year?", "173"),
    ("Can a director attend a board meeting by video conferencing?", "173"),
    ("What is a special resolution?", "114"),
    ("Which resolutions must be filed with the Registrar?", "117"),
    ("How is an additional director appointed?", "161"),
    ("Can a company appoint an alternate director?", "161"),
    ("Which companies must spend on CSR?", "135"),
    ("What approvals are needed for related party transactions?", "188"),
    ("Does an RPT need shareholder approval?", "188"),
    ("How is the first auditor of a company appointed?", "139"),
    ("When must the annual return be filed?", "92"),
    ("What is the deadline to file financial statements with the Registrar?", "137"),
    ("Can a company give a loan to its director?", "185"),
    ("What disqualifies a person from being appointed a director?", "164"),
    ("Who must sign the minutes of a board meeting?", "118"),
    ("Can members inspect the minute books of general meetings?", "119"),
    # Codex review on PR #147: access wording without "inspect"/"copy", and selection
    ("Can members view the minutes of general meetings?", "119"),
    ("How can members obtain minutes of a general meeting?", "119"),
    ("Who selects an independent director?", "150"),
    ("How are independent directors chosen?", "150"),
    ("Who can requisition an EGM?", "100"),
    # other everyday subjects, so a fix for the above cannot quietly break them
    ("Can a member appoint a proxy to attend a general meeting?", "105"),
    ("How can a director resign?", "168"),
    ("How is a director removed before his term ends?", "169"),
    ("What are the duties of directors?", "166"),
    ("What is the maximum number of directorships a person can hold?", "165"),
    ("Which companies must constitute an audit committee?", "177"),
    ("Who can be appointed as managing director?", "196"),
    ("Which companies must appoint KMP?", "203"),
    ("Can the board pass a resolution by circulation?", "175"),
    # the question names the section: the exact route, which ranking must never touch
    ("What does section 174 say?", "174"),
    ("Explain s.188", "188"),
    ("Under section 135, how much must be spent?", "135"),
    ("What does section 96 require?", "96"),
    # off-topic: silence is the right answer
    ("How long should I boil eggs?", ""),
    ("What is the capital of France?", ""),
    ("Best time to visit Goa in December", ""),
    ("How do I renew my passport?", ""),
)

_KEY = re.compile(r":S(\d+[A-Z]*)$")


def sections_for(question: str) -> list[str]:
    """Section numbers Ask would read for this question, best first."""
    pack, _route = retrieve(question)
    return [m.group(1) for p in pack.usable if (m := _KEY.search(p.key))]


def hit(expected: str, got: list[str], k: int) -> bool:
    return not got if not expected else expected in got[:k]


def run(hints: bool) -> list[dict]:
    saved = text_search.RANKING_HINTS
    text_search.RANKING_HINTS = hints
    try:
        rows = []
        for q, exp in CASES:
            got = sections_for(q)
            rows.append({"q": q, "expected": exp, "got": got[:3],
                         "top1": hit(exp, got, 1), "top3": hit(exp, got, 3)})
        return rows
    finally:
        text_search.RANKING_HINTS = saved


def report(before: list[dict], after: list[dict]) -> str:
    n = len(CASES)
    lines = [f"section_eval, {n} questions",
             f"  top-1  before {sum(r['top1'] for r in before)}/{n}"
             f"   after {sum(r['top1'] for r in after)}/{n}",
             f"  top-3  before {sum(r['top3'] for r in before)}/{n}"
             f"   after {sum(r['top3'] for r in after)}/{n}"]
    for b, a in zip(before, after):
        if b["top1"] != a["top1"] or b["top3"] != a["top3"]:
            lines.append(f"  changed: {a['q']!r} s.{a['expected'] or '-'}  "
                         f"{b['got']} -> {a['got']}")
    return "\n".join(lines)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    index = {e["section_number"]: e for e in
             json.loads(text_search.INDEX.read_text())["entries"].values()}
    live = {n for n, e in index.items() if e.get("section_id")}

    # The labels and the hints name real, live sections -- never a number from memory.
    check(all(exp in live for _q, exp in CASES if exp),
          "every expected section in the eval is a live corpus section")
    hints = text_search._hints()["raw"]
    check(hints["status"].startswith("DRAFT") and "Legal Lead" in hints["status"],
          "topic_hints.json is marked DRAFT, pending Legal Lead approval")
    hinted = {s for t in hints["topics"] for s in t["sections"]}
    check(hinted <= live, f"every topic-hint section is a live corpus section ({sorted(hinted)})")
    check(all(re.fullmatch(r"s\.\d+[A-Z]*", w["provision"]) and w["provision"][2:] in live
              for w in hints["words"]),
          "every word hint names a live corpus section as its evidence")
    check(index["174"]["title"] == "Quorum for meetings of Board"
          and index["103"]["title"] == "Quorum for meetings"
          and index["101"]["title"] == "Notice of meeting",
          "the headings the hints rely on are the corpus headings")

    before, after = run(False), run(True)
    print(report(before, after))
    n = len(CASES)
    b1, a1 = sum(r["top1"] for r in before), sum(r["top1"] for r in after)
    b3, a3 = sum(r["top3"] for r in before), sum(r["top3"] for r in after)
    check(a1 >= b1 and a3 >= b3, f"no worse overall: top-1 {b1}->{a1}, top-3 {b3}->{a3} of {n}")
    regressed = [a["q"] for b, a in zip(before, after)
                 if (b["top1"] and not a["top1"]) or (b["top3"] and not a["top3"])]
    check(not regressed, f"no question that worked before fails now {regressed}")
    check(a1 >= 42, f"after top-1 holds at its measured level ({a1}/{n}, floor 42)")

    # The four failures this change exists for, pinned by name.
    by_q = {r["q"]: r for r in after}
    for q in ("What is the quorum for a board meeting?",
              "What is the notice period for a general meeting?",
              "Who can be an independent director?",
              "What is the quorum for an AGM?"):
        r = by_q[q]
        check(r["top1"], f"{q!r} -> s.{r['expected']} first ({r['got']})")

    # Bonuses reorder, they never admit: silence stays silence.
    for q, exp in CASES:
        if not exp:
            check(by_q[q]["got"] == [], f"off-topic {q!r} still retrieves nothing")
    check(text_search.search("chocolate ice cream recipe") == []
          and text_search.search("quorum", top_k=0) == [],
          "a nonsense query and top_k=0 still return nothing with hints on")

    # A named section is answered by the resolver: the exact route ignores ranking.
    for q in ("What does section 174 say?", "Explain s.188"):
        check(len(by_q[q]["got"]) == 1, f"{q!r} returns only the named section")

    # Word hints are SHOWN, like abbreviations -- the reader sees what was added.
    _, used = text_search.expand_query("Which companies must spend on CSR?")
    check(("CSR", "corporate social responsibility") in used,
          f"a word hint is reported as an expansion ({used})")
    saved = text_search.RANKING_HINTS
    text_search.RANKING_HINTS = False
    try:
        _, used_off = text_search.expand_query("Which companies must spend on CSR?")
    finally:
        text_search.RANKING_HINTS = saved
    check(used_off == (), "with hints off, no word hint is added")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
