"""The shipped retrieval ranker: BM25 over structural chunks. Zero dependencies.

Decision A (docs/NEXT_MOVE_PLAN / MODEL_DEVELOPMENT_PLAN §3.4): retrieval ships on
BM25 (precision@1 = 0.62 on the eval, vs 0.15 naive), and the embedding dependency
is revisited only if real usage shows 0.62 is not enough. This module is that
shipped ranker — until now BM25 lived inside `retrieval_eval`; here it has a real,
importable home so production code retrieves through it rather than through a test.

It ranks a fixed set of structural chunks for a natural-language query and returns
them best-first, each with its BM25 score. It does NOT apply admission control —
that is `structural_retrieve`'s job; compose the two when a query must respect what
a reviewer has admitted. Kept separate so the ranker is a pure, testable function.
"""
from __future__ import annotations

from checker.lexical_rank import BM25
from checker.structural_chunk import Chunk
from checker.structural_index import chunks_for_section


def rank(query: str, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    """(chunk, score) best-first, dropping chunks that score zero.

    A zero score means no query term matched, so returning it would be a false
    hit — the same discipline as `BM25.top`. Order is BM25-descending; ties keep
    the chunks' document order (BM25.rank is stable).
    """
    if not chunks:
        return []
    bm = BM25([(c.path, c.text) for c in chunks])
    by_path = {c.path: c for c in chunks}
    return [(by_path[path], score) for path, score in bm.rank(query) if score > 0.0]


def best(query: str, chunks: list[Chunk]) -> Chunk | None:
    """The single best-scoring chunk, or None if nothing scores above zero."""
    ranked = rank(query, chunks)
    return ranked[0][0] if ranked else None


def search_section(query: str, section: str) -> list[tuple[Chunk, float]]:
    """Rank a whole section's structural chunks for a query (via the corpus)."""
    return rank(query, chunks_for_section(section))


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

    print("chunk_retrieval")

    # ── ranks a section's chunks for a query ────────────────────────────────
    ranked = search_section("turnover limit for the preceding financial year", "2")
    check(bool(ranked), "a query returns ranked chunks")
    check(ranked[0][0].path == "2(85)(ii)",
          f"the turnover question tops the turnover limb ({ranked[0][0].path})")
    check(all(ranked[i][1] >= ranked[i + 1][1] for i in range(len(ranked) - 1)),
          "results are ordered by descending score")
    check(all(score > 0 for _, score in ranked), "zero-scoring chunks are dropped")

    # ── best() matches the top of rank() ────────────────────────────────────
    b = best("turnover limit for the preceding financial year", chunks_for_section("2"))
    check(b is not None and b.path == "2(85)(ii)", "best() returns the top-ranked chunk")

    # ── this is the same ranker the eval measures at 0.62 ───────────────────
    from checker.retrieval_eval import run, bm25_select, select_chunk
    bm = run(selector=bm25_select)
    naive = run(selector=select_chunk)
    check(bm.precision_at_1 > naive.precision_at_1,
          f"the shipped ranker beats naive on the eval ({bm.precision_at_1:.2f} > "
          f"{naive.precision_at_1:.2f})")
    # best() and the eval's bm25_select must agree on a shared case.
    s2 = chunks_for_section("2")
    check(best("the turnover limit for a small company in the preceding financial year", s2).path
          == bm25_select("the turnover limit for a small company in the preceding financial year", s2).path,
          "the shipped best() and the eval's bm25_select agree")

    # ── degenerate inputs ───────────────────────────────────────────────────
    check(rank("anything", []) == [], "no chunks -> no results")
    check(best("photosynthesis chlorophyll xylophone", chunks_for_section("2")) is None,
          "a query sharing no term with the section returns None")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
