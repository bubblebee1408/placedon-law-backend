#!/usr/bin/env python3
"""Reranker bake-off: BGE cross-encoder score as an 8th feature.

PLAN_24 §3.2. Measures whether adding a cross-encoder score to the existing
7-feature linear reranker improves held-out p@1. The 8th feature wins only if
its 95% bootstrap CI on p@1 does not overlap the 7-feature baseline's.

Usage:
    PYTHONPATH=. python3 eval/reranker_bakeoff.py           # run bake-off
    PYTHONPATH=. python3 eval/reranker_bakeoff.py --test    # self-test
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# ponytail: reuses the entire reranker module's training/cv/scoring infra
from checker import reranker as _rr
from checker import fusion as _fusion


CROSS_ENCODER_MODEL = "BAAI/bge-reranker-base"

FEATURES_8 = _rr.FEATURES + ("cross_encoder",)


def _load_cross_encoder():
    from sentence_transformers import CrossEncoder
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    return CrossEncoder(CROSS_ENCODER_MODEL)


def _section_text(section_number: str) -> str:
    """Get the full section text for cross-encoder scoring."""
    from checker import section_index as _si
    from checker.corpus_retrieval import _clean, clean_html
    d = _si.section_by_number(section_number)
    if not d:
        return ""
    title = _clean(d.get("title", ""))
    body = clean_html(d.get("content", ""))[:1200]
    return f"Section {section_number}. {title}. {body}"


def dataset_8(ce_model) -> list[tuple[str, str, list[_rr.Candidate]]]:
    """The 70-case dataset with 8 features (original 7 + cross-encoder score)."""
    rows_7 = _rr.dataset()
    rows_8 = []
    total_scored = 0
    for question, gold, cands_7 in rows_7:
        cands_8 = []
        pairs = [(question, _section_text(c.section)) for c in cands_7]
        if pairs:
            scores = ce_model.predict(pairs)
            total_scored += len(pairs)
        else:
            scores = []
        for c, ce_score in zip(cands_7, scores):
            cands_8.append(_rr.Candidate(
                section=c.section,
                title=c.title,
                features=c.features + (float(ce_score),),
                label=c.label,
            ))
        rows_8.append((question, gold, cands_8))
    print(f"  cross-encoder scored {total_scored} (query, section) pairs")
    return rows_8


def _cv_with_features(rows, n_features: int, label: str) -> dict:
    """Cross-validate using only the first n_features of each candidate."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression

    folds = _rr._folds(rows, _rr.N_FOLDS, "section")
    oof_hits = []
    for f, test_idx in enumerate(folds):
        if not test_idx:
            continue
        train_idx = [i for i in range(len(rows)) if i not in set(test_idx)]
        # Train
        train_rows = [rows[i] for i in train_idx]
        X = np.array([c.features[:n_features] for _, _, cs in train_rows for c in cs], dtype=float)
        y = np.array([c.label for _, _, cs in train_rows for c in cs], dtype=int)
        model = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=0)
        model.fit(X, y)
        # Test
        for i in test_idx:
            q, gold, cands = rows[i]
            if not cands:
                oof_hits.append(0)
                continue
            s = model.decision_function(np.array([c.features[:n_features] for c in cands], dtype=float))
            order = sorted(zip(cands, s), key=lambda p: (-p[1], p[0].section))
            oof_hits.append(1 if order[0][0].section == gold else 0)
    return {"hits": oof_hits, "p_at_1": sum(oof_hits) / len(oof_hits), "n": len(oof_hits), "label": label}


def run_bakeoff() -> dict:
    from checker.retrieval_metrics import bootstrap_ci

    print(f"\n{'='*70}")
    print(f"RERANKER BAKE-OFF: 7 features vs 8 features (+{CROSS_ENCODER_MODEL})")
    print(f"{'='*70}")

    ce_model = _load_cross_encoder()
    rows_8 = dataset_8(ce_model)

    # Cross-validate with 7 features (baseline)
    print("\n7-feature baseline (cross-validated):")
    cv7 = _cv_with_features(rows_8, 7, "7-feature")
    print(f"  p@1 = {cv7['p_at_1']:.3f} (n={cv7['n']})")

    # Cross-validate with 8 features
    print("\n8-feature candidate (cross-validated):")
    cv8 = _cv_with_features(rows_8, 8, "8-feature")
    print(f"  p@1 = {cv8['p_at_1']:.3f} (n={cv8['n']})")

    # Bootstrap CIs
    ci7 = bootstrap_ci(cv7["hits"])
    ci8 = bootstrap_ci(cv8["hits"])

    overlap = True
    if ci7["lo"] is not None and ci8["lo"] is not None:
        overlap = not (ci8["lo"] > ci7["hi"] or ci7["lo"] > ci8["hi"])
    wins = (not overlap) and (ci8["mean"] or 0) > (ci7["mean"] or 0)

    print(f"\n--- Results ---")
    print(f"  7-feature CI: [{ci7['lo']:.3f}, {ci7['hi']:.3f}] mean={ci7['mean']:.3f} reliable={ci7['reliable']}")
    print(f"  8-feature CI: [{ci8['lo']:.3f}, {ci8['hi']:.3f}] mean={ci8['mean']:.3f} reliable={ci8['reliable']}")
    print(f"  CIs overlap: {overlap}")
    if wins:
        print(f"  >>> 8TH FEATURE WINS <<<")
    else:
        reason = "CIs overlap" if overlap else "8-feature lower"
        print(f"  Verdict: NO WIN ({reason})")

    # Weight dominance analysis (PLAN_24 §3.2 constraint)
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    X = np.array([c.features for _, _, cs in rows_8 for c in cs], dtype=float)
    y = np.array([c.label for _, _, cs in rows_8 for c in cs], dtype=int)
    full_8 = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=0)
    full_8.fit(X, y)
    w = full_8.coef_[0]
    total_abs = sum(abs(x) for x in w)
    ce_abs = abs(w[7])
    ce_share = ce_abs / total_abs if total_abs else 0.0

    print(f"\n--- Weight analysis (full 8-feature fit) ---")
    for name, coef in zip(FEATURES_8, w):
        pct = abs(coef) / total_abs * 100 if total_abs else 0
        print(f"  {name:<17} {coef:+8.3f}  ({pct:4.1f}%)")
    print(f"  {'(intercept)':<17} {float(full_8.intercept_[0]):+8.3f}")
    print(f"\n  Cross-encoder weight share: {ce_share:.1%}")
    if ce_share > 0.7:
        print("  DESIGN CONCERN: cross-encoder dominates (>70%); explainability hollow.")
    elif ce_share > 0.4:
        print("  NOTE: cross-encoder significant but other features remain meaningful.")
    else:
        print("  OK: cross-encoder is one voice among many; explainability preserved.")

    # Also print the RRF fusion baseline for context
    print(f"\n  Baselines:")
    print(f"    RRF fusion p@1 = 0.80 (measured in checker/fusion.py)")
    print(f"    7-feature reranker = {cv7['p_at_1']:.3f}")
    print(f"    8-feature reranker = {cv8['p_at_1']:.3f}")

    return {"cv7": cv7, "cv8": cv8, "ci7": ci7, "ci8": ci8,
            "overlap": overlap, "wins": wins, "ce_weight_share": ce_share}


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    check(len(FEATURES_8) == 8, f"8 features declared ({len(FEATURES_8)})")
    check(FEATURES_8[:7] == _rr.FEATURES, "first 7 features match incumbent")
    check(FEATURES_8[7] == "cross_encoder", "8th feature is cross_encoder")
    check(CROSS_ENCODER_MODEL == "BAAI/bge-reranker-base", "model is bge-reranker-base")

    # Verify the 7-feature dataset still works
    rows = _rr.dataset()
    check(len(rows) == 70, f"70 frozen cases ({len(rows)})")
    check(all(len(c.features) == 7 for _, _, cs in rows for c in cs),
          "all candidates have 7 features")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--test" in sys.argv:
        return _test()
    run_bakeoff()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
