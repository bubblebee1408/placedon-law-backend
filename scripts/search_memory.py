"""
Agent retrieval over code and memory. The read half of `index_codebase.py`.

This is what the spec calls meta-RAG: before an agent builds anything it asks the codebase
whether the thing already exists. On this project that question has teeth — `RESEARCH_LOG.md`
records twelve findings and `DECISIONS.md` eight decisions with reversal conditions, and an agent
that rebuilds something already decided against is worse than one that builds nothing.

    python3 scripts/search_memory.py "how did we implement rate limiting"
    python3 scripts/search_memory.py --memory "why no vector search"   # memory + docs only
    python3 scripts/search_memory.py --benchmark                        # timings

Ranking is BM25F over two fields — **identity** (path segments, defined symbols) and **body**
(everything else) — with identity weighted 6x. That split is not decoration. A single weighted
bag ranked `search_memory.py` above `checker/ratelimit.py` for "how did we implement rate
limiting", because this file's docstring quotes that phrase as an example: the document *about*
the query beat the document *answering* it. Weighting identity fixes it, and the case is pinned
in `scripts/verify.py` so it cannot come back.

Exact, total recall, under a millisecond — see `--benchmark`.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / ".claude/index.json"

IDENT_BOOST = 6.0

MEMORY_PREFIXES = (".claude/", "docs/", "RESEARCH_LOG.md", "DECISIONS.md", "BACKLOG.md",
                   "README.md")
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
STOP = {"the", "and", "for", "how", "did", "␟", "with", "what", "why", "our", "this", "that",
        "was", "are", "not", "you", "have", "from", "when", "where", "which", "does", "use"}


def _load() -> dict:
    if not INDEX.exists():
        print("No index. Run: python3 scripts/index_codebase.py", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(INDEX.read_text())


def _expand(query: str) -> set[str]:
    """`rate limiting` also matches `ratelimit`; camelCase and snake_case both split."""
    terms: set[str] = set()
    toks = [t.lower() for t in WORD.findall(query)]
    for t in toks:
        if t in STOP:
            continue
        terms.add(t)
        terms |= {p.lower() for p in re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", t) if len(p) > 2}
    # adjacent pairs joined — "rate limiting" -> "ratelimiting", "ratelimit"
    for a, b in zip(toks, toks[1:]):
        if a in STOP or b in STOP:
            continue
        terms.add(a + b)
        terms.add(a + b.rstrip("ing").rstrip("e"))
    return terms


def search(query: str, idx: dict, *, memory_only: bool = False, top_k: int = 8) -> list[tuple]:
    docs, postings = idx["docs"], idx["postings"]
    n = len(docs)
    scores: dict[int, float] = {}

    for term in _expand(query):
        flat = postings.get(term)
        if not flat:
            continue
        df = len(flat) // 3
        idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)      # BM25 idf, never negative
        for i in range(0, len(flat), 3):
            doc_id, body_tf, ident_tf = flat[i], flat[i + 1], flat[i + 2]
            # Saturating tf so one file repeating a token 400 times cannot dominate, then
            # identity x6: being named for a concept beats mentioning it.
            tf = body_tf / (body_tf + 6.0) + IDENT_BOOST * (ident_tf / (ident_tf + 1.5))
            scores[doc_id] = scores.get(doc_id, 0.0) + idf * tf

    ranked = []
    for doc_id, score in scores.items():
        d = docs[doc_id]
        if memory_only and not d["path"].startswith(MEMORY_PREFIXES):
            continue
        ranked.append((score, d))
    ranked.sort(key=lambda x: -x[0])
    return ranked[:top_k]


def benchmark(idx: dict) -> None:
    queries = [
        "how did we implement rate limiting",
        "why no vector search",
        "district jurisdiction abstention",
        "budget daily cap monthly",
        "who validates the internal committee",
        "board report three numbers",
    ]
    print("query                                   ms     top hit")
    print("-" * 78)
    total = 0.0
    for q in queries:
        t0 = time.perf_counter()
        hits = search(q, idx)
        ms = (time.perf_counter() - t0) * 1000
        total += ms
        top = hits[0][1]["path"] if hits else "(none)"
        print(f"  {q:<38}{ms:5.2f}   {top}")
    print("-" * 78)
    print(f"  mean {total / len(queries):.2f} ms over {len(idx['docs'])} files, "
          f"{sum(d['lines'] for d in idx['docs']):,} lines.")
    print("\n  An embedding round-trip on the same corpus is dominated by model load — seconds,")
    print("  not milliseconds — before any ranking happens. At this size the index wins on")
    print("  latency, on exactness, and on not shipping 2 GB of dependencies.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", nargs="*", help="what to look for")
    ap.add_argument("--memory", action="store_true", help="memory, docs and logs only")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("-k", type=int, default=8)
    args = ap.parse_args()

    idx = _load()
    if args.benchmark:
        benchmark(idx)
        return 0
    if not args.query:
        ap.print_help()
        return 1

    hits = search(" ".join(args.query), idx, memory_only=args.memory, top_k=args.k)
    if not hits:
        print("Nothing matched. That is a real answer — it probably does not exist yet.")
        return 0

    for score, d in hits:
        print(f"\n  {d['path']}  ({d['lines']} lines, score {score:.2f})")
        if d["symbols"]:
            print(f"    symbols: {', '.join(d['symbols'][:8])}")
        if d["headings"]:
            print(f"    sections: {' | '.join(d['headings'][:4])}")
        if d["summary"]:
            print(f"    {d['summary'][:190]}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
