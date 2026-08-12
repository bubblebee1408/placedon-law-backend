"""
Measure retrieval. Settle the embeddings question with a number instead of an argument.

## Why this exists before `src/rag/embeddings.py` does

Every planning document proposes replacing keyword-and-scan retrieval with
`all-MiniLM-L6-v2` + ChromaDB. `checker/retrieval.py` argues against it from corpus size. Both are
arguments. Neither is a measurement, and on a compliance product the architecture of the retrieval
layer decides which section of the Act a user is shown — so it should be decided by evidence.

This harness produces the evidence. Add a challenger and it is measured against the same set.

## The ground truth is not the keyword map

Testing `retrieval.py` against `KEYWORD_MAP` would be circular: the map is the thing under test.
So ground truth here is derived **independently**, by locating the operative phrase in the
byte-verified statutory text. For "when must the inquiry be completed", the governing section is
whichever section actually contains *"ninety days"* — established by search over the corpus, not
by anyone's opinion about routing.

That makes each row falsifiable: if the expected section does not contain the phrase, the row is
wrong and the harness says so rather than scoring against it.

## What is reported

    recall@k   did the governing section appear in the top k?
    exact@1    was it ranked first?
    misses     which questions failed, so the failure is a work item and not a percentage

`recall@3` is the number that matters: three sections is what a generation layer would be handed.

    python3 scripts/bench_retrieval.py
    python3 scripts/bench_retrieval.py --verbose
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"


@dataclass(frozen=True)
class Case:
    """A question, and the phrase that identifies its governing section in the statute."""

    question: str
    phrase: str                 # must appear verbatim in the governing section
    note: str = ""


# Questions a real user asks, each pinned to a phrase that occurs in exactly one section. The
# phrase is the ground truth; the section number is derived, never asserted.
CASES = [
    Case("Do I need to constitute an Internal Committee?",
         "constitute a Committee to be known as the"),
    Case("Who can be the Presiding Officer of the committee?",
         "woman employed at a senior level"),
    Case("Does the committee need an external member?",
         "from amongst non-governmental organisations"),
    Case("How long do members of the committee serve?",
         "not exceeding three years"),   # s.4 and s.7 both say it; either is correct
    Case("What happens if my workplace has fewer than ten workers?",
         "less than ten workers"),
    Case("Who constitutes the Local Committee?",
         "Local Committee"),
    Case("How long does an aggrieved woman have to file a complaint?",
         "within a period of three months from the date of incident"),
    Case("Can the parties settle the matter instead of an inquiry?",
         "settle the matter between her and the respondent through conciliation"),
    Case("How long may an inquiry take?",
         "completed within a period of ninety days"),
    Case("Can the woman be transferred while the inquiry is going on?",
         "transfer the aggrieved woman or the respondent"),
    Case("What if the complaint turns out to be false?",
         "malicious intent"),
    Case("Can the details of the complaint be published?",
         "shall not be published, communicated or made known to the public"),
    Case("What must an employer display at the workplace?",
         "display at any conspicuous place in the workplace"),
    Case("Do I have to run awareness training?",
         "organise workshops and awareness programmes"),
    Case("What is the penalty for not complying?",
         "fine which may extend to fifty thousand rupees"),
    Case("Does the committee have to file an annual report?",
         "prepare, in such form and at such time as may be prescribed"),
    Case("Does 'workplace' include a client site or a taxi?",
         "any place visited by the employee arising out of or during the course of employment"),
    Case("Are contract workers covered as employees?",
         "whether for remuneration or not"),
    Case("Can the decision be appealed?",
         "prefer an appeal"),
    Case("What powers does the committee have during an inquiry?",
         "same powers as are vested in a civil court"),
]


def load() -> list[dict]:
    return json.loads(CORPUS.read_text())["provisions"]


def ground_truth(provisions: list[dict]) -> tuple[dict[str, list[int]], list[str]]:
    """
    Resolve each case's phrase to the section(s) containing it.

    Returns (phrase -> sections, problems). A phrase found in zero sections is a broken case and
    is reported, not silently skipped — a benchmark that quietly drops its hard rows measures
    only its easy ones.
    """
    flat = {p["section_number"]: " ".join(p["text_statutory"].split()) for p in provisions}
    truth: dict[str, list[int]] = {}
    problems: list[str] = []
    for c in CASES:
        hits = sorted(n for n, t in flat.items() if c.phrase.lower() in t.lower())
        if not hits:
            problems.append(f"phrase not found in any section: {c.phrase!r} ({c.question!r})")
        truth[c.phrase] = hits
    return truth, problems


# ── the incumbent ────────────────────────────────────────────────────────────────────────────
def rank_current(question: str) -> list[int]:
    from checker import retrieval                              # noqa: PLC0415

    # retrieve() returns (provisions, stage) — a TUPLE. The first version of this function
    # iterated the tuple itself, so every question scored 0.0 and the harness was about to
    # report "embeddings win by +0.737" against a baseline that had never run. A benchmark whose
    # incumbent scores zero on a corpus it was written for is broken, not informative.
    provisions, _stage = retrieval.retrieve(question)
    if not isinstance(provisions, list):
        raise SystemExit(f"REFUSED: retrieve() returned {type(provisions)}; update rank_current().")
    return [p["section_number"] for p in provisions]


# ── the challenger, only if it is installed ──────────────────────────────────────────────────
def rank_embeddings(question: str, _cache: dict = {}) -> list[int] | None:
    """all-MiniLM-L6-v2 cosine over whole sections. Returns None if not installed."""
    try:
        from sentence_transformers import SentenceTransformer   # noqa: PLC0415
    except ImportError:
        return None
    import numpy as np                                         # noqa: PLC0415

    if "m" not in _cache:
        _cache["m"] = SentenceTransformer("all-MiniLM-L6-v2")
        provs = load()
        _cache["ids"] = [p["section_number"] for p in provs]
        texts = [" ".join(p["text_statutory"].split()) for p in provs]
        _cache["mat"] = _cache["m"].encode(texts, normalize_embeddings=True)
    q = _cache["m"].encode([question], normalize_embeddings=True)[0]
    scores = _cache["mat"] @ q
    order = list(reversed(scores.argsort()))
    return [_cache["ids"][i] for i in order]


def score(ranker, truth: dict[str, list[int]], ks=(1, 3, 5)) -> dict:
    hits = {k: 0 for k in ks}
    misses: list[tuple[str, list[int], list[int]]] = []
    n = 0
    for c in CASES:
        want = truth[c.phrase]
        if not want:
            continue                       # broken case, already reported
        n += 1
        got = ranker(c.question)
        for k in ks:
            if set(got[:k]) & set(want):
                hits[k] += 1
        if not (set(got[:3]) & set(want)):
            misses.append((c.question, want, got[:3]))
    return {"n": n, **{f"recall@{k}": round(hits[k] / n, 3) if n else 0.0 for k in ks},
            "misses": misses}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    provisions = load()
    truth, problems = ground_truth(provisions)
    if problems:
        print("  BROKEN CASES — fix these before trusting any number below:")
        for p in problems:
            print(f"    {p}")
        print()

    usable = sum(1 for c in CASES if truth[c.phrase])
    print(f"  {usable}/{len(CASES)} cases have ground truth located in the statute\n")

    cur = score(rank_current, truth)
    print(f"  {'incumbent (keyword + scan)':<34}"
          f"r@1={cur['recall@1']}  r@3={cur['recall@3']}  r@5={cur['recall@5']}  n={cur['n']}")

    emb = rank_embeddings("probe")
    if emb is None:
        print(f"  {'challenger (all-MiniLM-L6-v2)':<34}not installed — nothing to compare")
    else:
        e = score(rank_embeddings, truth)
        print(f"  {'challenger (all-MiniLM-L6-v2)':<34}"
              f"r@1={e['recall@1']}  r@3={e['recall@3']}  r@5={e['recall@5']}  n={e['n']}")
        d = round(e["recall@3"] - cur["recall@3"], 3)
        print(f"\n  recall@3 delta: {d:+}")
        print("  -> embeddings win. Build src/rag/embeddings.py." if d > 0 else
              "  -> no improvement. Adding 2GB of dependencies buys nothing measurable.")

    if cur["misses"]:
        print(f"\n  incumbent misses ({len(cur['misses'])}) — each one is a work item:")
        for q, want, got in cur["misses"]:
            print(f"    {q}\n      want any of s.{want}, got s.{got}")
    else:
        print("\n  incumbent misses nothing at k=3. There is no headroom for a challenger to"
              "\n  win on this set — a perfect score cannot be improved, only matched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
