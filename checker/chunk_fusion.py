"""Dense + RRF fusion over STRUCTURAL CHUNKS — does the cross-section win transfer?

Two retrieval surfaces exist in this project and only one has been improved.

  Surface 1 — CROSS-SECTION: "given a plain question, which SECTION governs it?"
    Measured in `cross_section_eval` over 70 frozen cases. BM25 0.71, dense 0.73,
    RRF fusion 0.80 / recall@5 0.97. Fusion was ADOPTED there.

  Surface 2 — WITHIN-SECTION: "given a claim and a known section, which structural
    CHUNK (sub-section / proviso / clause) is the witness span?" Measured in
    `retrieval_eval`. The shipped ranker is `chunk_retrieval` (BM25 over chunks) at
    p@1 0.62. This surface has never been tested with embeddings or fusion.

This module is the experiment for surface 2, and nothing more. It exists to be
MEASURED against the shipped 0.62, not to be adopted on arrival.

## Why the cross-section result does not transfer for free

Fusion won on surface 1 for one specific, measured reason: BM25's and dense's error
sets there were almost disjoint (11 cases only dense got, 8 only BM25 got). Two
retrievers that fail on different queries are the precondition for rank fusion; two
that fail on the SAME queries fuse into the same failures.

There is a concrete reason to doubt the precondition holds here. Across 527 sections
the candidates are long and topically distinct, so lexical overlap and semantic
similarity genuinely disagree. Within one section the candidates are short, share the
section's vocabulary, and often differ by a single word — s.2(85)(i) vs s.2(85)(ii)
differ in "paid-up share capital" vs "turnover". When the discriminating evidence is
one term, BM25 and a 384-dim sentence embedding tend to be right together and wrong
together. So the honest prior is that fusion may buy nothing here, and a null result
is the finding, not a failure.

## Refusal, not silent degradation

`dense_rank` and `fused_rank` raise if the model is unavailable. A silent BM25
fallback would report BM25's numbers under a dense or fused label and invalidate the
entire comparison this module exists to make — the same failure `dense_index` and
`fusion` each refuse at their own layer.

## Not tuned

k = 60 is the published RRF default, run once. The embedding text is the chunk's own
text (see `_embed_text`), chosen before the first measurement and not revisited — the
eval here is 13 cases, so trying a second text formulation and keeping the better one
would fit the eval outright.
"""
from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

from checker import dense_index as _dense
from checker.chunk_retrieval import rank as _bm25_rank
from checker.dense_index import MODEL_NAME, DenseUnavailable
from checker.structural_chunk import Chunk
from checker.structural_index import chunks_for_section
from checker.section_index import section_by_number

_CACHE = Path(__file__).resolve().parent.parent / "corpus" / ".chunk_dense_cache.pkl"

# Same bound as `dense_index._BODY_CHARS`, and for the same reason: a 384-dim vector
# blurs when it has to carry pages of text. In practice the cap almost never binds on
# a structural chunk — that is the point of chunking on the statute's own structure.
_CHUNK_CHARS = 1200

# The RRF smoothing constant, identical to `fusion.RRF_K` and for the identical
# reason: 60 is Cormack, Clarke & Buettcher (SIGIR 2009) and is pinned at the
# published default so the 13-case eval cannot become a training set. With k = 60
# rank 1 and rank 2 differ by ~1.6%, so agreement across retrievers outweighs
# confidence within one.
RRF_K = 60

FUSED = "FUSED_BM25_DENSE_CHUNK"


class ChunkFusionUnavailable(RuntimeError):
    """Raised when dense chunk retrieval is missing and the caller did not explicitly
    ask for degraded single-retriever mode. Returning BM25's chunk ranking under a
    fused label would be a fabricated measurement."""


def _embed_text(c: Chunk) -> str:
    """What actually gets embedded for a chunk.

    The chunk's own text, capped. Deliberately NOT decorated with its structural path
    ("2(85)(i)") or a synthesised heading: those are identifiers, not meaning, and the
    query never contains them. Chosen once on that reasoning, before any number was
    measured, and not revisited afterwards — with 13 scored cases, picking between two
    formulations by their eval scores would be fitting the eval.
    """
    return c.text[:_CHUNK_CHARS]


@lru_cache(maxsize=1)
def _disk_cache() -> dict:
    if _CACHE.exists():
        try:
            with _CACHE.open("rb") as fh:
                blob = pickle.load(fh)
            if isinstance(blob, dict):
                return blob
        except Exception:                       # noqa: BLE001 - a bad cache is not fatal
            pass                                # recompute; never trust a stale cache
    return {}


def _flush(cache: dict) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE.open("wb") as fh:
            pickle.dump(cache, fh)
    except OSError:
        pass                                    # a cache we cannot write is not an error


def _corpus_sha(section: str) -> str:
    d = section_by_number(section)
    return (d or {}).get("sha256", "")


def embed_section(section: str):
    """(paths, matrix) of unit-normalised chunk embeddings for a section.

    Cached to disk keyed on model, section, the section's stored corpus sha256 and the
    chunk-text cap — so a corpus edit or a change to `_embed_text`'s bound invalidates
    it rather than silently serving vectors for text that no longer exists.
    """
    chunks = chunks_for_section(section)
    paths = [c.path for c in chunks]
    key = (MODEL_NAME, section, _corpus_sha(section), _CHUNK_CHARS, len(paths))

    cache = _disk_cache()
    hit = cache.get(section)
    if hit and hit.get("key") == key and hit.get("paths") == paths:
        return paths, hit["matrix"]

    if not chunks:
        return paths, None

    model = _dense._model()                     # raises DenseUnavailable; never falls back
    mat = model.encode([_embed_text(c) for c in chunks], batch_size=16,
                       convert_to_numpy=True, normalize_embeddings=True,
                       show_progress_bar=False)
    cache[section] = {"key": key, "paths": paths, "matrix": mat}
    _flush(cache)
    return paths, mat


def dense_rank(query: str, chunks: list[Chunk]) -> list[tuple[Chunk, float]]:
    """(chunk, cosine) best-first over the given chunks. Raises if dense is missing.

    Unlike BM25 this drops nothing: a cosine is defined for every chunk, so every
    candidate is ranked. That asymmetry is deliberate and is what fusion consumes —
    BM25 abstains on a chunk sharing no term with the query, dense never does.
    """
    import numpy as np

    if not chunks:
        return []
    section = chunks[0].section
    paths, mat = embed_section(section)
    if mat is None:
        return []
    by_path = {c.path: c for c in chunks}
    q = _dense._model().encode([query], convert_to_numpy=True,
                               normalize_embeddings=True)[0]
    sims = mat @ q                              # both normalised -> cosine
    scored = [(by_path[p], float(s)) for p, s in zip(paths, sims) if p in by_path]
    return sorted(scored, key=lambda t: (-t[1], t[0].start))


def dense_select(query: str, chunks: list[Chunk]) -> Chunk | None:
    """Selector with `retrieval_eval`'s contract: Chunk or None."""
    ranked = dense_rank(query, chunks)
    return ranked[0][0] if ranked else None


def _rank_map(ranked: list[tuple[Chunk, float]]) -> dict[str, int]:
    """Ranked list -> {chunk path: 1-based rank}. The scores are discarded here, on
    purpose and permanently, so no BM25 magnitude and no cosine can ever be combined
    even by accident downstream."""
    out: dict[str, int] = {}
    for i, (c, _score) in enumerate(ranked):
        out.setdefault(c.path, i + 1)           # first occurrence wins
    return out


def _rrf(rank_maps: list[dict[str, int]], k: int = RRF_K) -> dict[str, float]:
    """Sum 1/(k + rank) across retrievers. A chunk absent from a retriever's list
    contributes nothing from it — absence is not a zero score, it is no vote."""
    fused: dict[str, float] = {}
    for ranks in rank_maps:
        for path, rank in ranks.items():
            fused[path] = fused.get(path, 0.0) + 1.0 / (k + rank)
    return fused


def rank_maps(query: str, chunks: list[Chunk]
              ) -> tuple[dict[str, int], dict[str, int]]:
    """(bm25 ranks, dense ranks) by chunk path. Raises if dense is unavailable."""
    ok, why = _dense.available()
    if not ok:
        raise ChunkFusionUnavailable(f"dense chunk retrieval unavailable: {why}")
    return _rank_map(_bm25_rank(query, chunks)), _rank_map(dense_rank(query, chunks))


def fused_rank_with_mode(query: str, chunks: list[Chunk], *,
                         allow_degraded: bool = False
                         ) -> tuple[str, list[tuple[Chunk, float]]]:
    """(mode, ranked). `mode` is FUSED, or a string beginning 'DEGRADED_' when only
    one retriever ran — so a degraded result can never be read as a fused one."""
    ok, why = _dense.available()
    if not ok:
        if not allow_degraded:
            raise ChunkFusionUnavailable(
                f"cannot fuse chunks: dense retrieval is unavailable ({why}). Refusing "
                "rather than returning BM25 chunk results under a fused label. Pass "
                "allow_degraded=True to accept single-retriever mode explicitly.")
        return f"DEGRADED_BM25_ONLY: {why}", _bm25_rank(query, chunks)

    if not chunks:
        return FUSED, []
    b_ranks, d_ranks = rank_maps(query, chunks)
    fused = _rrf([b_ranks, d_ranks])
    by_path = {c.path: c for c in chunks}
    big = len(chunks) + 1
    order = sorted(
        fused.items(),
        # Deterministic: fused score, then the better of the two source ranks, then
        # document order. No score ever enters this sort.
        key=lambda kv: (-kv[1], min(b_ranks.get(kv[0], big), d_ranks.get(kv[0], big)),
                        by_path[kv[0]].start),
    )
    return FUSED, [(by_path[p], s) for p, s in order]


def fused_rank(query: str, chunks: list[Chunk], *, allow_degraded: bool = False
               ) -> list[tuple[Chunk, float]]:
    """(chunk, rrf_score) best-first — same shape as `chunk_retrieval.rank`.

    NOTE the score is an RRF score, not a relevance score in either source system's
    units, and is comparable only within one query's result list.
    """
    return fused_rank_with_mode(query, chunks, allow_degraded=allow_degraded)[1]


def fusion_select(query: str, chunks: list[Chunk]) -> Chunk | None:
    """Selector with `retrieval_eval`'s contract: Chunk or None."""
    ranked = fused_rank(query, chunks)
    return ranked[0][0] if ranked else None


def explain(query: str, chunks: list[Chunk], path: str) -> dict:
    """Why did this chunk land where it did? Every term of the sum, by source."""
    b_ranks, d_ranks = rank_maps(query, chunks)
    b, d = b_ranks.get(path), d_ranks.get(path)
    contrib = {"bm25": 1.0 / (RRF_K + b) if b else 0.0,
               "dense": 1.0 / (RRF_K + d) if d else 0.0}
    return {"path": path, "bm25_rank": b, "dense_rank": d,
            "contributions": contrib, "rrf": sum(contrib.values()), "k": RRF_K}


def available() -> tuple[bool, str]:
    """Probe without raising, so a caller can report 'not runnable' honestly."""
    ok, why = _dense.available()
    if not ok:
        return False, f"chunk fusion needs two retrievers; dense is missing: {why}"
    return True, "BM25 + dense both available over structural chunks"


# ── measurement ───────────────────────────────────────────────────────────────────
# Everything below reads the frozen eval and reports. Nothing here feeds back into
# the constants above.

_RANKERS = {
    "bm25": lambda q, cs: _bm25_rank(q, cs),
    "dense": dense_rank,
    "fusion": lambda q, cs: fused_rank(q, cs),
}


def _scoreable():
    """The eval's SCORED cases only.

    `retrieval_eval` deliberately excludes NEEDS_LAWYER cases: their correct span is a
    matter of legal judgement this project does not have, and scoring a guessed label
    would manufacture a green number. That exclusion is reproduced here exactly — the
    predicate is copied from `retrieval_eval.run`, not re-invented.
    """
    from checker.retrieval_eval import CASES
    return [c for c in CASES if not (c.needs_lawyer or c.expected_path is None)]


def measure(k: int = 5, verbose: bool = True) -> dict:
    """p@1 and recall@k for BM25, dense and fusion on the eval's scoreable cases."""
    from checker.retrieval_eval import CASES, run

    cases = _scoreable()
    excluded = len(CASES) - len(cases)
    n = len(cases)

    selectors = {"bm25": None, "dense": dense_select, "fusion": fusion_select}
    from checker.retrieval_eval import bm25_select
    selectors["bm25"] = bm25_select

    out: dict = {"n": n, "excluded_needs_lawyer": excluded, "k": k,
                 "rrf_k": RRF_K, "approaches": {}, "per_case": {}}

    for name, sel in selectors.items():
        # p@1 comes from the eval harness itself, so all three numbers are scored by
        # the same code path the shipped 0.62 was scored by.
        res = run(cases=CASES, selector=sel)
        recall = 0
        got_at_1: dict[str, str | None] = {}
        for c in cases:
            topk = [ch.path for ch, _ in _RANKERS[name](c.question,
                                                        chunks_for_section(c.section))[:k]]
            got_at_1[c.question] = topk[0] if topk else None
            if c.expected_path in topk:
                recall += 1
        out["approaches"][name] = {
            "p_at_1": res.correct, "precision": res.precision_at_1,
            "recall_hits": recall, "recall": recall / n if n else 0.0,
            "misses": list(res.misses),
        }
        out["per_case"][name] = got_at_1

    correct = {name: {c.question for c in cases
                      if out["per_case"][name][c.question] == c.expected_path}
               for name in selectors}
    out["only_bm25"] = sorted(correct["bm25"] - correct["dense"])
    out["only_dense"] = sorted(correct["dense"] - correct["bm25"])
    out["both"] = sorted(correct["bm25"] & correct["dense"])
    out["neither"] = sorted({c.question for c in cases}
                            - correct["bm25"] - correct["dense"])
    out["fusion_gained"] = sorted(correct["fusion"] - correct["bm25"])
    out["fusion_lost"] = sorted(correct["bm25"] - correct["fusion"])

    if verbose:
        print(f"within-section chunk retrieval — {n} scoreable cases "
              f"({excluded} NEEDS_LAWYER excluded), RRF k={RRF_K}")
        if n < 15:
            print(f"  *** SMALL SAMPLE: {n} cases. One case moves p@1 by "
                  f"{1 / n:.2f}. Every number below is PROVISIONAL. ***")
        for name in ("bm25", "dense", "fusion"):
            a = out["approaches"][name]
            print(f"  {name:<7} p@1 {a['p_at_1']}/{n} = {a['precision']:.2f}   "
                  f"recall@{k} {a['recall_hits']}/{n} = {a['recall']:.2f}")
        print(f"  error sets: both={len(out['both'])} only_bm25={len(out['only_bm25'])} "
              f"only_dense={len(out['only_dense'])} neither={len(out['neither'])}")
        for label in ("only_bm25", "only_dense", "neither", "fusion_gained",
                      "fusion_lost"):
            for q in out[label]:
                print(f"    {label:<14} {q[:64]}")
    return out


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    print("chunk_fusion")

    # --- the arithmetic, on synthetic rank lists (no corpus, no model) ------------
    a = {"2(85)(i)": 1, "2(85)(ii)": 2, "2(85)": 3}
    b = {"2(85)": 1, "2(85)(ii)": 2, "2(85)(i)": 3}
    f = _rrf([a, b])
    check(abs(f["2(85)(i)"] - (1 / 61 + 1 / 63)) < 1e-12, "RRF sums 1/(k+rank) exactly")
    check(abs(f["2(85)(i)"] - f["2(85)"]) < 1e-12,
          "mirror-image ranks fuse to equal scores")
    check(f["2(85)(i)"] > f["2(85)(ii)"],
          "a rank-1 somewhere beats rank-2 everywhere (k=60)")
    check(_rrf([{"x": 1}])["x"] == 1 / 61, "a single retriever contributes one term")
    check("y" not in _rrf([{"x": 1}]), "absence from a list contributes nothing")
    check(max(_rrf([a, b]).values()) <= 2 / (RRF_K + 1) + 1e-12,
          "fused scores are bounded by 2/(k+1) — ranks only, never scores")
    check(RRF_K == 60, "k is the published RRF default, not a fitted value")

    # _rank_map must discard scores: wildly different scales, identical order.
    cs2 = chunks_for_section("2")
    c1, c2 = cs2[1], cs2[2]
    m1 = _rank_map([(c1, 943.7), (c2, 12.0)])
    m2 = _rank_map([(c1, 0.81), (c2, 0.79)])
    check(m1 == m2 == {c1.path: 1, c2.path: 2},
          "rank extraction is scale-free: BM25 magnitudes and cosines map identically")

    # --- the refusal discipline ---------------------------------------------------
    orig = _dense.available
    try:
        _dense.available = lambda: (False, "simulated absence")
        for fn, name in ((lambda: fused_rank("agm", cs2), "fused_rank"),
                         (lambda: rank_maps("agm", cs2), "rank_maps")):
            raised = False
            try:
                fn()
            except ChunkFusionUnavailable:
                raised = True
            check(raised, f"{name}() REFUSES when dense is unavailable")
        mode, hits = fused_rank_with_mode("annual general meeting", cs2,
                                          allow_degraded=True)
        check(mode.startswith("DEGRADED_"),
              f"explicit degraded mode is labelled as degraded ({mode.split(':')[0]})")
        check(len(hits) > 0, "degraded mode still returns BM25 results, clearly marked")
        ok_probe, why_probe = available()
        check(not ok_probe and "dense is missing" in why_probe,
              "available() reports the missing retriever without raising")
    finally:
        _dense.available = orig

    # --- the NEEDS_LAWYER exclusion is honoured -----------------------------------
    from checker.retrieval_eval import CASES
    cases = _scoreable()
    check(all(not c.needs_lawyer and c.expected_path is not None for c in cases),
          "no lawyer-gated case is scored here")
    check(len(cases) < len(CASES),
          f"lawyer-gated cases are excluded ({len(CASES) - len(cases)} of {len(CASES)})")

    # --- live behaviour ------------------------------------------------------------
    ok, why = available()
    print(f"  [INFO] chunk fusion available: {ok} — {why}")
    if not ok:
        check(True, "chunk fusion unavailability is reported, not hidden")
        print(f"\n{passed}/{passed + failed} passed")
        return

    q = "the turnover limit for a small company in the preceding financial year"
    d = dense_rank(q, cs2)
    check(len(d) == len(cs2), "dense ranks every chunk — it never abstains")
    check(d == sorted(d, key=lambda t: (-t[1], t[0].start)), "dense hits are best-first")
    check(all(-1.01 <= s <= 1.01 for _, s in d), "every dense score is a cosine in range")

    fr = fused_rank(q, cs2)
    check(fr == sorted(fr, key=lambda t: -t[1]) or
          all(fr[i][1] >= fr[i + 1][1] for i in range(len(fr) - 1)),
          "fused hits are best-first")
    check(all(0.0 < s <= 2 / (RRF_K + 1) + 1e-12 for _, s in fr),
          "every fused score is a sum of at most two 1/(k+rank) terms")
    b_ranks, d_ranks = rank_maps(q, cs2)
    check(all(c.path in b_ranks or c.path in d_ranks for c, _ in fr),
          "fusion invents no candidate that neither retriever returned")

    ex = explain(q, cs2, "2(85)(ii)")
    check(abs(ex["rrf"] - sum(ex["contributions"].values())) < 1e-12,
          "explain() reconciles: the total is exactly its per-retriever terms")

    # the fused top-1 must be traceable to a retriever's own top ranks
    top = fr[0][0].path
    check(min(b_ranks.get(top, 10 ** 9), d_ranks.get(top, 10 ** 9)) <= 10,
          f"the fused winner {top} is top-10 for at least one retriever")

    check(dense_select("photosynthesis chlorophyll xylophone", []) is None,
          "no chunks -> no dense selection")
    check(fused_rank("anything", []) == [], "no chunks -> no fused results")

    # the embedding cache is real, and keyed so a corpus edit invalidates it
    paths, mat = embed_section("96")
    check(mat is not None and len(paths) == mat.shape[0],
          "every chunk of s.96 has exactly one embedding row")
    check(_CACHE.exists(), "the chunk embedding matrix is persisted to disk")

    # selectors satisfy retrieval_eval's contract
    for sel, name in ((dense_select, "dense_select"), (fusion_select, "fusion_select")):
        picked = sel("by when must the first annual general meeting be held",
                     chunks_for_section("96"))
        check(picked is None or isinstance(picked, Chunk),
              f"{name} returns a Chunk or None, as the eval requires")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--measure" in sys.argv:
        measure()
    else:
        _test()
