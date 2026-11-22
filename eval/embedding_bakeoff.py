#!/usr/bin/env python3
"""Embedding bake-off: candidate models vs the incumbent (MiniLM + BM25 fusion).

PLAN_24 §3.1. Each candidate is measured on the SAME frozen 70-case cross-section eval.
The candidate wins only if its 95% bootstrap CI on p@1 does not overlap the incumbent's.
This script REPORTS; it does not ADOPT.

Usage:
    PYTHONPATH=. python3 eval/embedding_bakeoff.py                      # all candidates
    PYTHONPATH=. python3 eval/embedding_bakeoff.py law-ai/InLegalBERT   # one candidate
    PYTHONPATH=. python3 eval/embedding_bakeoff.py --test               # self-test
"""
from __future__ import annotations

import os
import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"

CANDIDATES: tuple[str, ...] = (
    "law-ai/InLegalBERT",
    "BAAI/bge-m3",
)

INCUMBENT = "sentence-transformers/all-MiniLM-L6-v2"

_BODY_CHARS = 1200


@dataclass(frozen=True)
class BakeoffResult:
    model: str
    dense_p1: float
    dense_r5: float
    fusion_p1: float
    fusion_r5: float
    incumbent_fusion_p1: float
    incumbent_fusion_r5: float
    ci_candidate: dict
    ci_incumbent: dict
    ci_overlap: bool
    wins: bool
    n: int
    dense_misses: list = field(default_factory=list)
    fusion_misses: list = field(default_factory=list)


def _build_index(model_name: str) -> tuple[list[str], dict[str, str], "numpy.ndarray"]:
    """Build a dense index for the given model over the corpus. Returns (numbers, titles, matrix)."""
    import numpy as np
    from checker import section_index as _si
    from checker.corpus_retrieval import _clean, clean_html

    cache_path = CORPUS_DIR / f".dense_cache_{_safe_name(model_name)}.pkl"

    corpus = []
    for number, rec in _si._index().items():
        d = _si.section_by_number(str(number))
        if not d:
            continue
        title = _clean(rec.get("title", ""))
        body = clean_html(d.get("content", ""))[:_BODY_CHARS]
        corpus.append((str(number), title, f"Section {number}. {title}. {body}"))

    numbers = [c[0] for c in corpus]
    titles = {c[0]: c[1] for c in corpus}
    key = (model_name, len(corpus), _BODY_CHARS)

    if cache_path.exists():
        try:
            with cache_path.open("rb") as fh:
                blob = pickle.load(fh)
            if blob.get("key") == key and blob.get("numbers") == numbers:
                print(f"  [cache] {model_name}: loaded from {cache_path.name}")
                return numbers, titles, blob["matrix"]
        except Exception:
            pass

    print(f"  [embed] {model_name}: encoding {len(corpus)} sections...")
    model = _load_model(model_name)
    mat = model.encode([c[2] for c in corpus], batch_size=16,
                       convert_to_numpy=True, normalize_embeddings=True,
                       show_progress_bar=True)

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as fh:
            pickle.dump({"key": key, "numbers": numbers, "matrix": mat}, fh)
    except OSError:
        pass
    return numbers, titles, mat


def _load_model(model_name: str):
    """Load a SentenceTransformer model. Downloads if not cached."""
    from sentence_transformers import SentenceTransformer
    # Allow network for candidate downloads (unlike dense_index which is offline-only)
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    return SentenceTransformer(model_name)


def _safe_name(model_name: str) -> str:
    return model_name.replace("/", "_").replace("-", "_")


def _dense_search(query: str, numbers: list, titles: dict, mat, model,
                  top_k: int = 5) -> list[tuple[str, str, float]]:
    """Dense search using a pre-built index."""
    import numpy as np
    q = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
    sims = mat @ q
    order = np.argsort(-sims)[:top_k]
    return [(numbers[i], titles.get(numbers[i], ""), float(sims[i])) for i in order]


def _rrf(rank_maps: list[dict[str, int]], k: int = 60) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranks in rank_maps:
        for num, rank in ranks.items():
            fused[num] = fused.get(num, 0.0) + 1.0 / (k + rank)
    return fused


def _rank_map(hits: list[tuple[str, str, float]]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for i, (num, _title, _score) in enumerate(hits):
        ranks.setdefault(num, i + 1)
    return ranks


def _fused_search(query: str, numbers, titles, mat, model,
                  top_k: int = 5) -> list[tuple[str, str, float]]:
    """RRF fusion: BM25 + candidate dense model."""
    from checker import corpus_retrieval as _bm25
    b_hits = _bm25.search(query, top_k=10_000)
    d_hits = _dense_search(query, numbers, titles, mat, model, top_k=10_000)
    b_ranks = _rank_map(b_hits)
    d_ranks = _rank_map(d_hits)
    all_titles = {n: t for n, t, _ in d_hits}
    all_titles.update({n: t for n, t, _ in b_hits if t})
    fused = _rrf([b_ranks, d_ranks])
    big = 10_001
    order = sorted(fused.items(),
                   key=lambda kv: (-kv[1], min(b_ranks.get(kv[0], big),
                                               d_ranks.get(kv[0], big)), kv[0]))
    return [(n, all_titles.get(n, ""), s) for n, s in order[:top_k]]


def run_bakeoff(model_name: str) -> BakeoffResult:
    """Run the full bake-off for one candidate model."""
    from checker.cross_section_eval import CASES
    from checker.retrieval_metrics import bootstrap_ci

    print(f"\n{'='*70}")
    print(f"BAKE-OFF: {model_name}")
    print(f"{'='*70}")

    # Build candidate index
    numbers, titles, mat = _build_index(model_name)
    model = _load_model(model_name)
    n = len(CASES)

    # Dense-only eval (candidate)
    dense_p1 = 0
    dense_r5 = 0
    dense_misses = []
    dense_hits_per_case = []
    for c in CASES:
        top5 = [num for num, _, _ in _dense_search(c.question, numbers, titles, mat, model, 5)]
        got = top5[0] if top5 else None
        hit = 1 if got == c.section else 0
        dense_p1 += hit
        dense_hits_per_case.append(hit)
        if c.section in top5:
            dense_r5 += 1
        else:
            dense_misses.append((c.question, c.section, got or "None"))

    # Fusion eval (BM25 + candidate)
    fusion_p1 = 0
    fusion_r5 = 0
    fusion_misses = []
    fusion_hits_per_case = []
    for c in CASES:
        top5 = [num for num, _, _ in _fused_search(c.question, numbers, titles, mat, model, 5)]
        got = top5[0] if top5 else None
        hit = 1 if got == c.section else 0
        fusion_p1 += hit
        fusion_hits_per_case.append(hit)
        if c.section in top5:
            fusion_r5 += 1
        else:
            fusion_misses.append((c.question, c.section, got or "None"))

    # Incumbent fusion eval (BM25 + MiniLM) — re-run for fair comparison
    from checker import fusion as _incumbent_fusion
    inc_p1 = 0
    inc_r5 = 0
    inc_hits_per_case = []
    for c in CASES:
        top5 = [num for num, _, _ in _incumbent_fusion.search(c.question, 5)]
        got = top5[0] if top5 else None
        hit = 1 if got == c.section else 0
        inc_p1 += hit
        inc_hits_per_case.append(hit)
        if c.section in top5:
            inc_r5 += 1

    # Bootstrap CIs on fusion p@1
    ci_cand = bootstrap_ci(fusion_hits_per_case)
    ci_inc = bootstrap_ci(inc_hits_per_case)

    overlap = True
    if ci_cand["lo"] is not None and ci_inc["hi"] is not None:
        overlap = not (ci_cand["lo"] > ci_inc["hi"] or ci_inc["lo"] > ci_cand["hi"])

    wins = (not overlap) and (ci_cand["mean"] or 0) > (ci_inc["mean"] or 0)

    result = BakeoffResult(
        model=model_name,
        dense_p1=dense_p1 / n,
        dense_r5=dense_r5 / n,
        fusion_p1=fusion_p1 / n,
        fusion_r5=fusion_r5 / n,
        incumbent_fusion_p1=inc_p1 / n,
        incumbent_fusion_r5=inc_r5 / n,
        ci_candidate=ci_cand,
        ci_incumbent=ci_inc,
        ci_overlap=overlap,
        wins=wins,
        n=n,
        dense_misses=dense_misses,
        fusion_misses=fusion_misses,
    )

    _print_result(result)
    return result


def _print_result(r: BakeoffResult) -> None:
    print(f"\n--- {r.model} vs {INCUMBENT} (n={r.n}) ---")
    print(f"  Dense only:  p@1={r.dense_p1:.3f}  recall@5={r.dense_r5:.3f}")
    print(f"  Fusion:      p@1={r.fusion_p1:.3f}  recall@5={r.fusion_r5:.3f}")
    print(f"  Incumbent:   p@1={r.incumbent_fusion_p1:.3f}  recall@5={r.incumbent_fusion_r5:.3f}")
    ci_c = r.ci_candidate
    ci_i = r.ci_incumbent
    print(f"  CI candidate: [{ci_c.get('lo', '?'):.3f}, {ci_c.get('hi', '?'):.3f}]"
          f"  mean={ci_c.get('mean', '?'):.3f}  reliable={ci_c.get('reliable')}")
    print(f"  CI incumbent: [{ci_i.get('lo', '?'):.3f}, {ci_i.get('hi', '?'):.3f}]"
          f"  mean={ci_i.get('mean', '?'):.3f}  reliable={ci_i.get('reliable')}")
    print(f"  CIs overlap: {r.ci_overlap}")
    if r.wins:
        print(f"  >>> CANDIDATE WINS (non-overlapping CI, higher mean) <<<")
    else:
        reason = "CIs overlap" if r.ci_overlap else "candidate lower"
        print(f"  Verdict: NO WIN ({reason})")
    if r.dense_misses:
        print(f"  Dense misses ({len(r.dense_misses)}):")
        for q, exp, got in r.dense_misses[:5]:
            print(f"    exp=s.{exp:5} got=s.{got:6} q={q[:52]}")
        if len(r.dense_misses) > 5:
            print(f"    ...and {len(r.dense_misses) - 5} more")


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    # Structural tests only — no model downloads in the self-test
    check(len(CANDIDATES) >= 2, f"at least 2 candidates declared ({len(CANDIDATES)})")
    check(INCUMBENT == "sentence-transformers/all-MiniLM-L6-v2",
          "incumbent is MiniLM-L6-v2")
    check(_safe_name("law-ai/InLegalBERT") == "law_ai_InLegalBERT",
          "safe name escapes slashes and dashes")

    from checker.cross_section_eval import CASES
    check(len(CASES) >= 70, f"eval has >= 70 cases ({len(CASES)})")

    from checker.retrieval_metrics import bootstrap_ci
    ci = bootstrap_ci([1, 0, 1, 1, 0, 1, 1, 1, 0, 1])
    check(0.0 < ci["mean"] < 1.0, "bootstrap_ci produces a sensible mean")
    check(ci["lo"] <= ci["mean"] <= ci["hi"], "CI bounds contain the mean")

    # RRF reproduces the known formula
    r = _rrf([{"a": 1, "b": 2}, {"b": 1, "c": 3}], k=60)
    check(abs(r["a"] - 1/61) < 1e-9, "RRF: single-source item scores 1/(k+rank)")
    check(abs(r["b"] - (1/62 + 1/61)) < 1e-9, "RRF: dual-source item sums both")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--test" in sys.argv:
        return _test()

    targets = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not targets:
        targets = list(CANDIDATES)

    results = []
    for model_name in targets:
        try:
            r = run_bakeoff(model_name)
            results.append(r)
        except Exception as e:
            print(f"\n  [ERROR] {model_name}: {e}")
            import traceback
            traceback.print_exc()

    if results:
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        for r in results:
            verdict = "WIN" if r.wins else "no win"
            print(f"  {r.model:40s}  fusion p@1={r.fusion_p1:.3f}  "
                  f"inc={r.incumbent_fusion_p1:.3f}  overlap={r.ci_overlap}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
