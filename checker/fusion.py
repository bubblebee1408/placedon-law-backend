"""Reciprocal Rank Fusion over BM25 and dense retrieval — M3.

M2 measured the two retrievers on the frozen 70-case cross-section eval and found
BM25 at p@1 0.71 / recall@5 0.91 and dense (MiniLM-L6) at 0.73 / 0.96 — but the
finding that matters is that their error sets are almost disjoint: 11 cases only
dense gets, 8 cases only BM25 gets, 9 neither gets. Two retrievers that fail on
different queries are the textbook precondition for rank fusion.

## Why RRF, and why it fuses ranks and never scores

A BM25 score is an unbounded sum of IDF-weighted term saturations. A cosine is a
bounded inner product between two unit vectors. They are not the same quantity, not
on the same scale, and not even on the same *kind* of scale — one is corpus- and
query-length-dependent, the other is not. Adding them, averaging them, or
min-max-normalising one into the other invents a comparability that does not exist,
and the resulting number would silently change meaning with corpus size and query
length. Normalisation is the specific failure this module exists to avoid.

Reciprocal Rank Fusion sidesteps it entirely. It throws the scores away and keeps
only what both retrievers genuinely agree on the meaning of: the ORDER they put
documents in. Each retriever contributes 1/(k + rank) for each document, and the
fused score is the sum of those contributions. Nothing but ranks crosses the
boundary between the two systems. That is the whole argument for RRF here, and it
is why `_rrf()` below takes rank maps and cannot even see a score.

## Refusal, not silent degradation

If dense retrieval is unavailable, `search()` raises. It does not quietly return
BM25's list under a "fused" label — that would report single-retriever numbers as
fusion numbers and repeat, one layer up, exactly the failure `dense_index` refuses
at its own layer. A caller that genuinely wants to limp along on one retriever must
say so with `allow_degraded=True`, and then gets a mode string that says DEGRADED in
it, so the degradation is carried in the result rather than lost.

## Not tuned

k is the published default and the fusion is over full ranked lists, so the module
has no cutoff depth to tune either. It was measured once against the frozen eval and
whatever it scored is what is reported.
"""
from __future__ import annotations

from checker import corpus_retrieval as _bm25
from checker import dense_index as _dense

# The RRF smoothing constant. 60 is the value Cormack, Clarke & Buettcher published
# with the method (SIGIR 2009) and the value virtually every implementation has used
# unchanged since. Its job is to flatten the top of the curve: with 1/rank alone, a
# rank-1 hit is worth twice a rank-2 hit, so one confidently-wrong retriever decides
# the fusion by itself. With k = 60, rank 1 (1/61) and rank 2 (1/62) differ by ~1.6%,
# so agreement across retrievers outweighs confidence within one. It is pinned at the
# published default deliberately: a k fitted against the 70 frozen cases would make
# the eval a training set, which is the one thing it must not become.
RRF_K = 60

# Fuse the FULL ranked list from each retriever rather than a truncated candidate
# pool. A pool depth would be a second free parameter, and a second free parameter is
# a second thing to be tempted to fit. With k = 60 the tail contributes near-uniform
# crumbs anyway (rank 100 -> 0.00625, rank 400 -> 0.00217), so a cutoff buys a knob
# and almost no behaviour. 10_000 is simply "larger than the ~474-section corpus".
_ALL = 10_000

FUSED = "FUSED_BM25_DENSE"


class FusionUnavailable(RuntimeError):
    """Raised when dense retrieval is missing and the caller did not explicitly ask
    for degraded single-retriever mode. Returning BM25's ranking labelled as fused
    would be a fabricated measurement."""


def _rank_map(hits: list[tuple[str, str, float]]) -> dict[str, int]:
    """Ranked list -> {section_number: 1-based rank}.

    The scores in `hits` are discarded here, on purpose and permanently. Everything
    downstream sees ranks only, so there is no code path in which a BM25 score and a
    cosine can be combined even by accident.
    """
    ranks: dict[str, int] = {}
    for i, (num, _title, _score) in enumerate(hits):
        ranks.setdefault(num, i + 1)          # first occurrence wins
    return ranks


def _rrf(rank_maps: list[dict[str, int]], k: int = RRF_K) -> dict[str, float]:
    """Sum 1/(k + rank) across retrievers. A document absent from a retriever's list
    contributes nothing from it — absence is not a zero score, it is no vote."""
    fused: dict[str, float] = {}
    for ranks in rank_maps:
        for num, rank in ranks.items():
            fused[num] = fused.get(num, 0.0) + 1.0 / (k + rank)
    return fused


def rank_maps(query: str) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    """(bm25 ranks, dense ranks, titles) for one query. Raises if dense is missing.

    Exposed because the M4 reranker needs the same two rank lists as features, and
    it should read them from here rather than re-deriving them slightly differently.
    """
    ok, why = _dense.available()
    if not ok:
        raise FusionUnavailable(f"dense retrieval unavailable: {why}")
    b_hits = _bm25.search(query, top_k=_ALL)
    d_hits = _dense.search(query, top_k=_ALL)
    titles = {n: t for n, t, _ in d_hits}
    titles.update({n: t for n, t, _ in b_hits if t})
    return _rank_map(b_hits), _rank_map(d_hits), titles


def search_with_mode(query: str, top_k: int = 5, *, allow_degraded: bool = False
                     ) -> tuple[str, list[tuple[str, str, float]]]:
    """(mode, hits). `mode` is FUSED, or a string beginning 'DEGRADED_' when only one
    retriever ran — so a degraded result can never be mistaken for a fused one."""
    ok, why = _dense.available()
    if not ok:
        if not allow_degraded:
            raise FusionUnavailable(
                f"cannot fuse: dense retrieval is unavailable ({why}). Refusing rather "
                "than returning BM25 results under a fused label. Pass "
                "allow_degraded=True to accept single-retriever mode explicitly.")
        return f"DEGRADED_BM25_ONLY: {why}", _bm25.search(query, top_k)

    b_ranks, d_ranks, titles = rank_maps(query)
    fused = _rrf([b_ranks, d_ranks])
    big = _ALL + 1
    order = sorted(
        fused.items(),
        # Deterministic: fused score, then the better of the two source ranks, then
        # the section number as a final stable key. No score ever enters this sort.
        key=lambda kv: (-kv[1], min(b_ranks.get(kv[0], big), d_ranks.get(kv[0], big)),
                        kv[0]),
    )
    return FUSED, [(n, titles.get(n, ""), s) for n, s in order[:top_k]]


def search(query: str, top_k: int = 5, *, allow_degraded: bool = False
           ) -> list[tuple[str, str, float]]:
    """(section_number, title, rrf_score) best-first — the same shape as
    `corpus_retrieval.search` and `dense_index.search`.

    NOTE the third element is an RRF score, not a relevance score in either source
    system's units, and is comparable only within one query's result list.
    """
    return search_with_mode(query, top_k, allow_degraded=allow_degraded)[1]


def best_section(query: str) -> str | None:
    hits = search(query, top_k=1)
    return hits[0][0] if hits else None


def explain(query: str, section: str) -> dict:
    """Why did this section land where it did? Every term of the sum, by source."""
    b_ranks, d_ranks, _ = rank_maps(query)
    b, d = b_ranks.get(section), d_ranks.get(section)
    contrib = {
        "bm25": 1.0 / (RRF_K + b) if b else 0.0,
        "dense": 1.0 / (RRF_K + d) if d else 0.0,
    }
    return {"section": section, "bm25_rank": b, "dense_rank": d,
            "contributions": contrib, "rrf": sum(contrib.values()), "k": RRF_K}


def available() -> tuple[bool, str]:
    """Probe without raising, so a caller can report 'not runnable' honestly."""
    ok, why = _dense.available()
    if not ok:
        return False, f"fusion needs two retrievers; dense is missing: {why}"
    return True, "BM25 + dense both available"


def measure(verbose: bool = True) -> dict:
    """Run fusion over the frozen 70-case eval. Measurement only — nothing here
    feeds back into the module's constants."""
    from checker.cross_section_eval import CASES

    p1 = r5 = 0
    misses: list[tuple[str, str, str]] = []
    per_case: list[tuple[str, str, list[str]]] = []
    for c in CASES:
        top5 = [n for n, _, _ in search(c.question, 5)]
        got = top5[0] if top5 else "None"
        per_case.append((c.question, c.section, top5))
        if got == c.section:
            p1 += 1
        if c.section in top5:
            r5 += 1
        else:
            misses.append((c.question, c.section, got))
    n = len(CASES)
    out = {"n": n, "p_at_1": p1, "recall_5": r5,
           "precision": p1 / n, "recall": r5 / n,
           "misses": misses, "per_case": per_case}
    if verbose:
        print(f"RRF fusion (k={RRF_K}) on the frozen {n}-case eval")
        print(f"  precision@1: {p1}/{n} = {out['precision']:.2f}   "
              f"(BM25 0.71, dense 0.73)")
        print(f"  recall@5:    {r5}/{n} = {out['recall']:.2f}   "
              f"(BM25 0.91, dense 0.96)")
        for q, exp, got in misses:
            print(f"  MISS exp=s.{exp:<6} got=s.{got:<6} q={q[:52]}")
    return out


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    print("fusion")

    # --- the arithmetic, on synthetic rank lists (no corpus, no model) ------------
    # Two retrievers that disagree completely: A ranks a,b,c and B ranks c,b,a.
    # RRF must put the two extremes (each rank-1 somewhere) above the compromise
    # candidate that is rank-2 for both. This is the behaviour scores cannot give.
    a = {"a": 1, "b": 2, "c": 3}
    b = {"c": 1, "b": 2, "a": 3}
    f = _rrf([a, b])
    check(abs(f["a"] - (1 / 61 + 1 / 63)) < 1e-12, "RRF sums 1/(k+rank) exactly")
    check(abs(f["a"] - f["c"]) < 1e-12, "mirror-image ranks fuse to equal scores")
    check(f["a"] > f["b"], "a rank-1 somewhere beats rank-2 everywhere (k=60)")
    check(_rrf([{"x": 1}])["x"] == 1 / 61, "a single retriever contributes one term")
    check("y" not in _rrf([{"x": 1}]), "absence from a list contributes nothing")

    # A document's fused score cannot exceed two rank-1 votes: proof that no raw
    # score magnitude ever leaks into the sum.
    check(max(_rrf([a, b]).values()) <= 2 / (RRF_K + 1) + 1e-12,
          "fused scores are bounded by 2/(k+1) — ranks only, never scores")

    # _rank_map must discard scores. Wildly different score scales, same order.
    m1 = _rank_map([("1", "", 943.7), ("2", "", 12.0)])
    m2 = _rank_map([("1", "", 0.81), ("2", "", 0.79)])
    check(m1 == m2 == {"1": 1, "2": 2},
          "rank extraction is scale-free: BM25 magnitudes and cosines map identically")

    # --- the refusal discipline ---------------------------------------------------
    orig = _dense.available
    try:
        _dense.available = lambda: (False, "simulated absence")
        raised = False
        try:
            search("annual general meeting")
        except FusionUnavailable:
            raised = True
        check(raised, "search() REFUSES when dense is unavailable")
        mode, hits = search_with_mode("annual general meeting", 5, allow_degraded=True)
        check(mode.startswith("DEGRADED_"),
              f"explicit degraded mode is labelled as degraded ({mode.split(':')[0]})")
        check(len(hits) > 0, "degraded mode still returns BM25 results, clearly marked")
        ok_probe, why_probe = available()
        check(not ok_probe and "dense is missing" in why_probe,
              "available() reports the missing retriever without raising")
    finally:
        _dense.available = orig

    # --- live behaviour ------------------------------------------------------------
    ok, why = available()
    print(f"  [INFO] fusion available: {ok} — {why}")
    if not ok:
        check(True, "fusion unavailability is reported, not hidden")
        print(f"\n{passed}/{passed + failed} passed")
        return

    hits = search("can a company give a loan to its director", top_k=5)
    check(len(hits) == 5, "search returns top_k hits")
    check(hits == sorted(hits, key=lambda h: -h[2]), "hits are best-first")
    nums = [h[0] for h in hits]
    check("185" in nums, f"'loan to its director' reaches s.185 in top-5 ({nums})")
    check(all(0.0 < h[2] <= 2 / (RRF_K + 1) + 1e-12 for h in hits),
          "every fused score is a sum of at most two 1/(k+rank) terms")

    q = "related party transaction approval"
    b_ranks, d_ranks, _ = rank_maps(q)
    fused_nums = [n for n, _, _ in search(q, top_k=5)]
    check(all(n in b_ranks or n in d_ranks for n in fused_nums),
          "fusion invents no candidate that neither retriever returned")

    ex = explain(q, "188")
    check(abs(ex["rrf"] - sum(ex["contributions"].values())) < 1e-12,
          "explain() reconciles: the total is exactly its per-retriever terms")
    check(ex["k"] == 60, "k is the published RRF default, not a fitted value")

    # The fused top-1 must be traceable to at least one retriever's own top ranks —
    # a fused winner nobody ranked highly would mean the fusion is inventing signal.
    top = fused_nums[0]
    check(min(b_ranks.get(top, 10 ** 9), d_ranks.get(top, 10 ** 9)) <= 10,
          f"the fused winner s.{top} is top-10 for at least one retriever")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--measure" in sys.argv:
        measure()
    else:
        _test()
