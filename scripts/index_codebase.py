"""
Build the agent search index over code and memory.

The spec asks for `sentence-transformers` + `chromadb` — embed every file, store vectors, query
by cosine similarity. This does the same job with an inverted index over symbols, docstrings and
identifiers, and the reason is measurement rather than preference. Run
`python3 scripts/search_memory.py --benchmark` for the numbers on this repo.

Why exact search wins at this size:

  * **The corpus is 6,000 lines.** An embedding model to rank 40 files costs ~2GB of
    dependencies (torch, transformers, chromadb) and several seconds of cold start, against an
    index that builds in milliseconds and fits in a JSON file you can read.
  * **Code search is lexical.** When an agent asks "how did we implement rate limiting", the
    useful answer is the file containing `ratelimit`. Embeddings blur exactly the token you
    wanted into a neighbourhood of tokens you did not — `all-MiniLM-L6-v2` was trained on prose,
    not on Python identifiers, and it has no idea that `check_hallucination` is one concept.
  * **Recall must be total, not approximate.** These agents make claims about statute. "The
    nearest three chunks" is the wrong contract when the question is *does this codebase already
    handle X* — a false negative there produces a duplicate implementation, silently.

This flips when the corpus reaches the four labour codes (~500 sections of prose, where semantic
similarity genuinely beats keyword overlap). `architect`'s standing position holds until then:
no vector search until exact search stops working, and it has not started to.

    python3 scripts/index_codebase.py            # rebuild
    python3 scripts/index_codebase.py --stats    # what's in it

Writes .claude/index.json. Safe to delete; rebuilt in under a second.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".claude/index.json"

INCLUDE_SUFFIX = {".py", ".ts", ".tsx", ".html", ".md", ".json", ".sh"}
SKIP_DIRS = {".git", "node_modules", ".next", "__pycache__", ".venv", "venv"}
# The index indexed itself on the first run and then ranked for "who validates the internal
# committee", because it contains every symbol in the repo. A search tool returning its own
# index is pure noise, and it grows every rebuild.
SKIP_FILES = {".claude/index.json"}
# Ingested statute is searched through checker/retrieval.py, which knows about sections and
# citations. Duplicating 30 provisions into a generic keyword index would return worse hits for
# legal questions than the purpose-built router already does.
SKIP_PATHS = {"corpus/provisions", "corpus/sample_", "corpus/review_pack"}

SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|const|interface|type)\s+([A-Za-z_]\w*)",
    re.M)
HEADING = re.compile(r"^#{1,3}\s+(.+)$", re.M)
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _split_identifier(tok: str) -> set[str]:
    """`check_hallucination` and `checkHallucination` both yield {check, hallucination}."""
    parts = re.split(r"_|(?<=[a-z0-9])(?=[A-Z])", tok)
    return {p.lower() for p in parts if len(p) > 2}


def _walk() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in INCLUDE_SUFFIX:
            continue
        rel = str(p.relative_to(ROOT))
        if (any(d in p.parts for d in SKIP_DIRS) or rel in SKIP_FILES
                or any(rel.startswith(s) for s in SKIP_PATHS)):
            continue
        out.append(p)
    return sorted(out)


def build() -> dict:
    t0 = time.perf_counter()
    docs: list[dict] = []
    postings: dict[str, list[int]] = {}

    for p in _walk():
        rel = str(p.relative_to(ROOT))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        symbols = SYMBOL.findall(text)
        headings = HEADING.findall(text) if p.suffix == ".md" else []
        # First docstring or block comment — usually the file's own statement of purpose, and on
        # this project that is where the reasoning lives.
        m = re.search(r'"""(.*?)"""', text, re.S) or re.search(r"/\*\*(.*?)\*/", text, re.S)
        summary = " ".join((m.group(1) if m else text[:400]).split())[:400]

        doc_id = len(docs)
        docs.append({
            "path": rel, "lines": text.count("\n") + 1, "symbols": symbols[:60],
            "headings": headings[:30], "summary": summary,
        })

        # Three fields, scored separately (BM25F). Collapsing them into one weighted bag was
        # the first implementation and it got "how did we implement rate limiting" wrong:
        # search_memory.py won, because its docstring quotes that phrase as an example, while
        # checker/ratelimit.py — the actual implementation — came second. A document ABOUT a
        # query outranked the document ANSWERING it. Identity (what a file is named, what it
        # defines) has to dominate prose (what a file happens to mention).
        body: dict[str, int] = {}
        ident: dict[str, int] = {}

        for tok in WORD.findall(text):
            for t in _split_identifier(tok) | {tok.lower()}:
                body[t] = body.get(t, 0) + 1
        for h in headings:
            for t in WORD.findall(h):
                body[t.lower()] = body.get(t.lower(), 0) + 4

        for sym in symbols:
            for t in _split_identifier(sym) | {sym.lower()}:
                ident[t] = ident.get(t, 0) + 1
        for seg in re.split(r"[/_.\-]", rel):
            if len(seg) > 2:
                ident[seg.lower()] = ident.get(seg.lower(), 0) + 3

        for t in set(body) | set(ident):
            postings.setdefault(t, []).extend((doc_id, body.get(t, 0), ident.get(t, 0)))

    idx = {
        "built_at_ms": round((time.perf_counter() - t0) * 1000, 1),
        "docs": docs,
        # flat [doc_id, body_tf, ident_tf, ...] — smaller on disk than nested objects
        "postings": postings,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(idx), encoding="utf-8")
    return idx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    idx = build()
    n_docs, n_terms = len(idx["docs"]), len(idx["postings"])
    size_kb = OUT.stat().st_size / 1024
    total_lines = sum(d["lines"] for d in idx["docs"])
    total_syms = sum(len(d["symbols"]) for d in idx["docs"])

    print(f"indexed {n_docs} files / {total_lines:,} lines / {total_syms} symbols")
    print(f"  {n_terms:,} terms, {size_kb:.0f} KB, built in {idx['built_at_ms']} ms")
    print(f"  → {OUT.relative_to(ROOT)}")
    print("\nFor comparison, the specified stack (sentence-transformers + chromadb) is ~2 GB of")
    print("dependencies and a multi-second cold start to rank the same 40 files. Revisit when")
    print("the corpus reaches the labour codes; see the module docstring.")

    if args.stats:
        print("\nlargest files:")
        for d in sorted(idx["docs"], key=lambda x: -x["lines"])[:10]:
            print(f"  {d['lines']:5}  {d['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
