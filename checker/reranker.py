"""A learned reranker that can be read — M4, the "perceptron".

The retrieval stack this sits on top of is deliberately transparent: BM25 is
arithmetic, RRF fuses ranks and nothing else, and both can be explained to a
practitioner in a sentence. A reranker is where that usually stops being true:
the standard move is a cross-encoder, and a cross-encoder's answer to "why is
s.235 above s.180?" is 22 million parameters. In a system whose entire thesis is
that a finding must carry its source, date, rule and reasoning, an unexplainable
component in the retrieval path is a contradiction, not an upgrade. So this
reranker is a linear model over seven hand-named features, its weights are
printed on every run, and any single ranking decision decomposes exactly into
per-feature contributions (`explain()`). If it cannot beat fusion under those
constraints, the honest outcome is to keep fusion — not to reach for a model
that wins and cannot be audited.

## The features, and why each is defensible

    rrf_bm25        1/(60+rank) from BM25          lexical evidence, rank-only
    rrf_dense       1/(60+rank) from dense         semantic evidence, rank-only
    bm25_top1       1 if BM25 ranked it first      "this retriever was confident"
    dense_top1      1 if dense ranked it first     ditto
    both_retrieved  1 if in both candidate pools   agreement between two retrievers
                                                   whose error sets are near-disjoint
                                                   (M2) is genuine evidence, not
                                                   double-counting
    heading_overlap |query ∩ title| / |query|      the section's own subject line is
                                                   the strongest structural signal of
                                                   what it governs — the same premise
                                                   as corpus_retrieval's heading boost
    query_has_number 1 if the query literally       "what does section 185 say" should
                     names this section number      not be decided by topic similarity

Ranks enter as 1/(k+rank), never as raw BM25 scores or cosines, for the reason
`fusion` spells out: those two quantities are not comparable and normalising one
into the other invents a scale. A linear model over raw scores would have quietly
learned a normalisation constant fitted to 70 queries.

## The number that gets reported is cross-validated

Training a 7-parameter model on 70 labelled queries and reporting how well it fits
those 70 queries measures nothing except that the fit succeeded. Both numbers are
computed here; only the held-out one is a result, and the training fit is printed
beside it specifically so the gap between them is visible.

Folds are grouped by EXPECTED SECTION, not by query. The eval contains paired
questions about the same section ("how to register a charge with the registrar"
and "duty to register a charge on the company's assets" are both s.77); splitting
those across the train/test boundary would let the model see a near-duplicate of
the query it is being scored on. Grouping by section closes that leak.

With 70 queries and 7 features, overfitting is the expected outcome, not the
surprising one. This module is built to detect that, and reports it if so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from checker import fusion as _fusion

# Candidate pool depth per retriever. A reranker can only reorder what it is
# shown, so this sets a hard ceiling on its recall — a ceiling this module
# measures and prints rather than leaving implicit. 10 each is the conventional
# rerank depth and is fixed before any measurement, not chosen after one.
POOL_DEPTH = 10

# Same smoothing constant as the fusion layer, for the same reason: rank features
# must be on the identical scale the fused baseline uses, or the comparison
# against fusion stops being like-for-like.
RRF_K = _fusion.RRF_K

# Number of cross-validation folds over the ~55 distinct expected sections.
# 7 folds ≈ 8 held-out sections each, leaving enough training queries for a
# 7-parameter model to be estimable at all.
N_FOLDS = 7

FEATURES = ("rrf_bm25", "rrf_dense", "bm25_top1", "dense_top1",
            "both_retrieved", "heading_overlap", "query_has_number")

# Words that carry no topical signal in a legal query. Deliberately short: a long
# hand-built stoplist is itself a fitted parameter.
_STOP = frozenset("""a an the of to in on for by is are be was were do does did
what which who whom how when where why must may can shall should would could
and or not it its this that these those with from at as if any all we our
company companies""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP}


@dataclass(frozen=True)
class Candidate:
    section: str
    title: str
    features: tuple[float, ...]
    label: int


def features_for(query: str, pool_depth: int = POOL_DEPTH) -> list[Candidate]:
    """Every candidate for one query, with its feature vector. Label is 0 here;
    `dataset()` fills it in from the eval's gold section.

    Raises FusionUnavailable if dense retrieval is missing — a reranker trained on
    features half of which are silently zero would be a different model wearing
    this one's name.
    """
    b_ranks, d_ranks, titles = _fusion.rank_maps(query)
    b_pool = {n for n, r in b_ranks.items() if r <= pool_depth}
    d_pool = {n for n, r in d_ranks.items() if r <= pool_depth}
    q_toks = _tokens(query)
    q_raw = set(_TOKEN.findall(query.lower()))

    out: list[Candidate] = []
    for sec in sorted(b_pool | d_pool, key=lambda s: (len(s), s)):
        br, dr = b_ranks.get(sec), d_ranks.get(sec)
        title = titles.get(sec, "")
        t_toks = _tokens(title)
        overlap = len(q_toks & t_toks) / len(q_toks) if q_toks else 0.0
        feats = (
            1.0 / (RRF_K + br) if br else 0.0,
            1.0 / (RRF_K + dr) if dr else 0.0,
            1.0 if br == 1 else 0.0,
            1.0 if dr == 1 else 0.0,
            1.0 if (sec in b_pool and sec in d_pool) else 0.0,
            overlap,
            1.0 if sec.lower() in q_raw else 0.0,
        )
        out.append(Candidate(sec, title, feats, 0))
    return out


@lru_cache(maxsize=1)
def dataset() -> list[tuple[str, str, list[Candidate]]]:
    """(question, gold_section, candidates) for the frozen 70 cases.

    Cached because building it costs 70 dense encodings and the cross-validation
    loop walks it N_FOLDS times.
    """
    from checker.cross_section_eval import CASES

    rows = []
    for c in CASES:
        cands = [Candidate(x.section, x.title, x.features,
                           1 if x.section == c.section else 0)
                 for x in features_for(c.question)]
        rows.append((c.question, c.section, cands))
    return rows


def pool_ceiling(rows=None) -> tuple[int, int]:
    """(queries whose gold section is in the pool, total). The reranker cannot
    exceed this — it reorders, it does not retrieve."""
    rows = rows if rows is not None else dataset()
    hit = sum(1 for _, gold, cands in rows if any(c.section == gold for c in cands))
    return hit, len(rows)


def fit(rows) -> "object":
    """Logistic regression over FEATURES. Deterministic (lbfgs, fixed seed) so the
    same data always yields the same weights — an auditable model that changes
    between runs is not auditable."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    X = np.array([c.features for _, _, cands in rows for c in cands], dtype=float)
    y = np.array([c.label for _, _, cands in rows for c in cands], dtype=int)
    model = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=0)
    model.fit(X, y)
    return model


def rerank(query: str, model, top_k: int = 5) -> list[tuple[str, str, float]]:
    """(section_number, title, score) best-first, using an explicitly-supplied
    model. There is deliberately no module-level `search()` fitted on the eval:
    that would put an eval-fitted model into the production path, which is the
    exact thing the frozen eval exists to prevent."""
    import numpy as np

    cands = features_for(query)
    if not cands:
        return []
    scores = model.decision_function(np.array([c.features for c in cands], dtype=float))
    ranked = sorted(zip(cands, scores), key=lambda p: (-p[1], p[0].section))
    return [(c.section, c.title, float(s)) for c, s in ranked[:top_k]]


def explain(query: str, section: str, model) -> dict:
    """The full decomposition of one score: weight × feature, term by term. This is
    what a cross-encoder cannot produce and why the model is linear."""
    for c in features_for(query):
        if c.section == section:
            w = model.coef_[0]
            terms = {name: float(w[i] * c.features[i]) for i, name in enumerate(FEATURES)}
            return {"section": section, "features": dict(zip(FEATURES, c.features)),
                    "terms": terms, "intercept": float(model.intercept_[0]),
                    "score": float(sum(terms.values()) + model.intercept_[0])}
    return {"section": section, "error": "not in the candidate pool"}


def _folds(rows, n_folds: int = N_FOLDS, group_by: str = "section") -> list[list[int]]:
    """Deterministic fold assignment. Grouping by section keeps paired questions
    about the same section on the same side of the split; grouping by query is
    offered only so the size of that leak can be measured."""
    if group_by == "query":
        return [[i for i in range(len(rows)) if i % n_folds == f] for f in range(n_folds)]
    groups = sorted({gold for _, gold, _ in rows}, key=lambda s: (len(s), s))
    assign = {g: i % n_folds for i, g in enumerate(groups)}
    return [[i for i, (_, gold, _) in enumerate(rows) if assign[gold] == f]
            for f in range(n_folds)]


def _score(model, rows, idx) -> tuple[int, int, list[tuple[str, str, str]]]:
    """(p@1 hits, recall@5 hits, misses) over the given row indices."""
    import numpy as np

    p1 = r5 = 0
    misses = []
    for i in idx:
        q, gold, cands = rows[i]
        if not cands:
            misses.append((q, gold, "None"))
            continue
        s = model.decision_function(np.array([c.features for c in cands], dtype=float))
        order = sorted(zip(cands, s), key=lambda p: (-p[1], p[0].section))
        top5 = [c.section for c, _ in order[:5]]
        if top5[0] == gold:
            p1 += 1
        if gold in top5:
            r5 += 1
        else:
            misses.append((q, gold, top5[0]))
    return p1, r5, misses


def cross_validate(n_folds: int = N_FOLDS, group_by: str = "section",
                   verbose: bool = True) -> dict:
    """Held-out evaluation. Every query is scored by a model that never saw it, nor
    any other query about the same section."""
    rows = dataset()
    folds = _folds(rows, n_folds, group_by)
    fold_p1: list[float] = []
    oof_p1 = oof_r5 = n = 0
    oof_misses: list[tuple[str, str, str]] = []
    for f, test_idx in enumerate(folds):
        if not test_idx:
            continue
        train_idx = [i for i in range(len(rows)) if i not in set(test_idx)]
        model = fit([rows[i] for i in train_idx])
        p1, r5, misses = _score(model, rows, test_idx)
        fold_p1.append(p1 / len(test_idx))
        oof_p1 += p1; oof_r5 += r5; n += len(test_idx)
        oof_misses += misses
        if verbose:
            print(f"  fold {f + 1}: {len(test_idx):2d} held-out queries  "
                  f"p@1 {p1}/{len(test_idx)} = {p1 / len(test_idx):.2f}")
    mean = sum(fold_p1) / len(fold_p1)
    spread = (sum((x - mean) ** 2 for x in fold_p1) / len(fold_p1)) ** 0.5
    return {"n": n, "folds": len(fold_p1), "group_by": group_by,
            "oof_p_at_1": oof_p1 / n, "oof_recall_5": oof_r5 / n,
            "oof_p1_hits": oof_p1, "oof_r5_hits": oof_r5,
            "fold_mean_p_at_1": mean, "fold_std_p_at_1": spread,
            "fold_scores": fold_p1, "misses": oof_misses}


def weights_table(model) -> str:
    w = model.coef_[0]
    lines = ["  feature           weight",
             "  ----------------- --------"]
    for name, coef in zip(FEATURES, w):
        lines.append(f"  {name:<17} {coef:+8.3f}")
    lines.append(f"  {'(intercept)':<17} {float(model.intercept_[0]):+8.3f}")
    return "\n".join(lines)


def measure(verbose: bool = True) -> dict:
    """The full honest report: pool ceiling, cross-validated score, training fit
    beside it, and the inspectable weights."""
    rows = dataset()
    hit, total = pool_ceiling(rows)
    print(f"candidate pool: top-{POOL_DEPTH} BM25 ∪ top-{POOL_DEPTH} dense")
    print(f"  pool ceiling (gold section present at all): {hit}/{total} = {hit / total:.2f}")
    print(f"  no reranker over this pool can exceed that recall.\n")

    print(f"cross-validation — {N_FOLDS} folds grouped by expected section")
    cv = cross_validate(verbose=verbose)
    print(f"\n  HELD-OUT p@1:   {cv['oof_p1_hits']}/{cv['n']} = {cv['oof_p_at_1']:.2f}"
          f"   (fold mean {cv['fold_mean_p_at_1']:.2f} ± {cv['fold_std_p_at_1']:.2f})")
    print(f"  HELD-OUT r@5:   {cv['oof_r5_hits']}/{cv['n']} = {cv['oof_recall_5']:.2f}")

    cv_q = cross_validate(group_by="query", verbose=False)
    print(f"  [query-grouped folds, leaking paired questions: p@1 "
          f"{cv_q['oof_p_at_1']:.2f} — the gap is the size of that leak]")

    full = fit(rows)
    tr_p1, tr_r5, _ = _score(full, rows, range(len(rows)))
    print(f"\n  training fit (NOT a result): p@1 {tr_p1}/{len(rows)} = "
          f"{tr_p1 / len(rows):.2f}, r@5 {tr_r5 / len(rows):.2f}")
    print(f"  overfit gap: {tr_p1 / len(rows) - cv['oof_p_at_1']:+.2f}\n")

    print("baselines on the same frozen 70 cases:")
    print("  BM25    p@1 0.71   r@5 0.91")
    print("  dense   p@1 0.73   r@5 0.96")
    print("  RRF     p@1 0.80   r@5 0.97   (measured in checker/fusion.py)")
    print("\nlearned weights (every one of them, every run):")
    print(weights_table(full))
    return {"cv": cv, "cv_query_grouped": cv_q, "train_p_at_1": tr_p1 / len(rows),
            "pool_ceiling": hit / total, "model": full}


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    print("reranker")

    # --- features are arithmetic and checkable by hand ----------------------------
    check(len(FEATURES) == 7, "seven named features, no hidden eighth")
    check(_tokens("what is the annual general meeting") == {"annual", "general", "meeting"},
          "tokenisation drops function words only")

    ok, why = _fusion.available()
    print(f"  [INFO] retrievers available: {ok} — {why}")
    if not ok:
        check(True, "reranker unavailability is reported, not hidden")
        print(f"\n{passed}/{passed + failed} passed")
        return

    cands = features_for("when must a company hold its annual general meeting")
    check(all(len(c.features) == len(FEATURES) for c in cands),
          "every candidate carries exactly one value per named feature")
    check(0 < len(cands) <= 2 * POOL_DEPTH,
          f"the pool is the union of two top-{POOL_DEPTH} lists ({len(cands)} candidates)")
    by_sec = {c.section: c for c in cands}
    check("96" in by_sec, f"s.96 is a candidate for the AGM question ({sorted(by_sec)[:8]}…)")
    check(all(0.0 <= c.features[5] <= 1.0 for c in cands),
          "heading_overlap is a proportion in [0,1]")
    check(max(c.features[0] for c in cands) == 1.0 / (RRF_K + 1),
          "the BM25 rank-1 candidate scores exactly 1/(k+1) — a rank, not a score")
    check(sum(c.features[2] for c in cands) == 1.0 and sum(c.features[3] for c in cands) == 1.0,
          "exactly one bm25_top1 and one dense_top1 per query")

    lit = {c.section: c.features[6]
           for c in features_for("what does section 185 say about loans")}
    check(lit.get("185") == 1.0, "query_has_number fires on the section the query names")
    check(all(v == 0.0 for s, v in lit.items() if s != "185"),
          "query_has_number fires on nothing else")

    # --- the training/held-out distinction is structural, not a promise ------------
    rows = dataset()
    check(len(rows) == 70, f"the frozen eval is all 70 cases ({len(rows)})")
    check(sum(c.label for _, _, cs in rows for c in cs) <= len(rows),
          "at most one positive label per query")
    folds = _folds(rows)
    flat = [i for f in folds for i in f]
    check(sorted(flat) == list(range(len(rows))),
          "the folds partition the eval: every query held out exactly once")
    check(len(flat) == len(set(flat)), "no query appears in two test folds")
    sec_of = {i: g for i, (_, g, _) in enumerate(rows)}
    leak = [f for f in folds
            if any(sec_of[i] == sec_of[j] for i in f
                   for j in range(len(rows)) if j not in f)]
    check(not leak, "no expected section straddles a fold boundary — paired questions "
                    "cannot leak across the split")

    m = fit(rows)
    check(len(m.coef_[0]) == len(FEATURES),
          "one inspectable weight per feature — the model is readable end to end")
    ex = explain("when must a company hold its annual general meeting", "96", m)
    check(abs(ex["score"] - (sum(ex["terms"].values()) + ex["intercept"])) < 1e-9,
          "explain() reconciles: the score is exactly the sum of its named terms")

    hits = rerank("can a company give a loan to its director", m, top_k=5)
    check(len(hits) == 5, "rerank returns top_k hits")
    check(hits == sorted(hits, key=lambda h: -h[2]), "hits are best-first")

    cv = cross_validate(verbose=False)
    check(cv["n"] == 70, "cross-validation scores all 70 queries out-of-fold")
    check(0.0 <= cv["oof_p_at_1"] <= 1.0, "the held-out p@1 is a proportion")
    tr, _, _ = _score(m, rows, range(len(rows)))
    check(tr / len(rows) >= cv["oof_p_at_1"] - 1e-9,
          f"the training fit ({tr / len(rows):.2f}) is not below the held-out score "
          f"({cv['oof_p_at_1']:.2f}) — reporting the fit would flatter the model")

    hit, total = pool_ceiling(rows)
    check(cv["oof_recall_5"] <= hit / total + 1e-9,
          "held-out recall@5 cannot exceed the candidate pool ceiling")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--measure" in sys.argv:
        measure()
    else:
        _test()
