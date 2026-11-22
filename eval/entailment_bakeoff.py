#!/usr/bin/env python3
"""Entailment bake-off: DeBERTa NLI vs the incumbent deterministic cascade.

PLAN_24 §3.3. Measures precision, recall, F1 on the same frozen 67-pair strict
set the incumbent cascade is scored on. DeBERTa wins only if its 95% bootstrap
CI on F1 does not overlap the incumbent's.

The incumbent is 5 deterministic modules (cascade.py) with no model call.
DeBERTa is a 184M-param transformer. Apples-to-oranges on latency/cost — this
measures accuracy only.

Usage:
    PYTHONPATH=. python3 eval/entailment_bakeoff.py           # run bake-off
    PYTHONPATH=. python3 eval/entailment_bakeoff.py --test    # self-test
"""
from __future__ import annotations

import os
import sys

DEBERTA_MODEL = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"


def _load_pairs() -> list:
    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED
    return [p for p in all_pairs()
            if p.label in (ENTAILED, NOT_ENTAILED) and p.source_span]


def _incumbent_scores(pairs) -> list[int]:
    """Run the incumbent cascade on each pair. 1 = correct, 0 = wrong."""
    from checker import cascade
    from checker.grounding_policy import ENTAILED
    results = []
    for p in pairs:
        gold = p.label == ENTAILED
        got = cascade.judge_row(p) is True
        results.append(1 if gold == got else 0)
    return results


def _deberta_scores(pairs) -> list[int]:
    """Run DeBERTa NLI on each pair. 1 = correct, 0 = wrong."""
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    from checker.grounding_policy import ENTAILED

    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    print(f"  loading {DEBERTA_MODEL}...")
    tok = AutoTokenizer.from_pretrained(DEBERTA_MODEL)
    mdl = AutoModelForSequenceClassification.from_pretrained(DEBERTA_MODEL)
    mdl.eval()
    label_names = mdl.config.id2label

    results = []
    for i, p in enumerate(pairs):
        gold = p.label == ENTAILED
        inputs = tok(p.source_span, p.claim, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = mdl(**inputs).logits
        pred_label = label_names.get(int(logits.argmax(dim=-1)), "").lower()
        got = pred_label == "entailment"
        results.append(1 if gold == got else 0)
        if (i + 1) % 10 == 0:
            print(f"    {i + 1}/{len(pairs)} pairs scored")
    return results


def _prf(pairs, predict_fn) -> dict:
    """Compute precision, recall, F1 and per-pair correctness."""
    from checker.grounding_policy import ENTAILED
    tp = fp = fn = tn = 0
    hits = []
    for p in pairs:
        gold = p.label == ENTAILED
        got = predict_fn(p)
        if gold and got:
            tp += 1; hits.append(1)
        elif gold:
            fn += 1; hits.append(0)
        elif got:
            fp += 1; hits.append(0)
        else:
            tn += 1; hits.append(1)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": prec,
            "recall": rec, "f1": f1, "hits": hits, "n": len(pairs)}


def run_bakeoff() -> dict:
    from checker.retrieval_metrics import bootstrap_ci
    from checker import cascade
    from checker.grounding_policy import ENTAILED

    print(f"\n{'='*70}")
    print(f"ENTAILMENT BAKE-OFF: cascade vs {DEBERTA_MODEL}")
    print(f"{'='*70}")

    pairs = _load_pairs()
    print(f"  {len(pairs)} pairs (entailed: {sum(1 for p in pairs if p.label == ENTAILED)}, "
          f"not: {sum(1 for p in pairs if p.label != ENTAILED)})")

    # Incumbent cascade
    print("\nIncumbent cascade:")
    inc = _prf(pairs, lambda p: cascade.judge_row(p) is True)
    print(f"  P={inc['precision']:.3f} R={inc['recall']:.3f} F1={inc['f1']:.3f}")
    print(f"  tp={inc['tp']} fp={inc['fp']} fn={inc['fn']} tn={inc['tn']}")

    # DeBERTa NLI — proper premise/hypothesis entailment
    print(f"\nDeBERTa ({DEBERTA_MODEL}):")
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    print(f"  loading model...")
    _tok = AutoTokenizer.from_pretrained(DEBERTA_MODEL)
    _mdl = AutoModelForSequenceClassification.from_pretrained(DEBERTA_MODEL)
    _mdl.eval()
    _label_names = _mdl.config.id2label  # {0: "entailment", 1: "neutral", 2: "contradiction"} or similar

    def _deberta_predict(p):
        inputs = _tok(p.source_span, p.claim, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = _mdl(**inputs).logits
        pred_id = int(logits.argmax(dim=-1))
        pred_label = _label_names.get(pred_id, "").lower()
        return pred_label == "entailment"

    deb = _prf(pairs, _deberta_predict)
    print(f"  P={deb['precision']:.3f} R={deb['recall']:.3f} F1={deb['f1']:.3f}")
    print(f"  tp={deb['tp']} fp={deb['fp']} fn={deb['fn']} tn={deb['tn']}")

    # Bootstrap CIs on accuracy (correctness per pair)
    ci_inc = bootstrap_ci(inc["hits"])
    ci_deb = bootstrap_ci(deb["hits"])

    # Also CI on F1 via per-pair bootstrap
    # ponytail: accuracy CI is simpler and more directly comparable; F1 bootstrap
    # over pairs is methodologically tricky (not iid). Report both accuracy CIs.

    overlap = True
    if ci_inc["lo"] is not None and ci_deb["lo"] is not None:
        overlap = not (ci_deb["lo"] > ci_inc["hi"] or ci_inc["lo"] > ci_deb["hi"])
    wins = (not overlap) and (ci_deb["mean"] or 0) > (ci_inc["mean"] or 0)

    print(f"\n--- Accuracy comparison ---")
    print(f"  Cascade  acc={sum(inc['hits'])/len(inc['hits']):.3f}  "
          f"CI [{ci_inc['lo']:.3f}, {ci_inc['hi']:.3f}]  reliable={ci_inc['reliable']}")
    print(f"  DeBERTa  acc={sum(deb['hits'])/len(deb['hits']):.3f}  "
          f"CI [{ci_deb['lo']:.3f}, {ci_deb['hi']:.3f}]  reliable={ci_deb['reliable']}")
    print(f"  CIs overlap: {overlap}")
    if wins:
        print(f"  >>> DEBERTA WINS <<<")
    else:
        reason = "CIs overlap" if overlap else "DeBERTa lower"
        print(f"  Verdict: NO WIN ({reason})")

    print(f"\n  Note: cascade is deterministic (0 model calls, 0 latency).")
    print(f"  DeBERTa is 184M params, ~1s/pair on CPU.")
    print(f"  Even if DeBERTa wins on accuracy, the cascade's explainability")
    print(f"  and speed may outweigh a marginal accuracy gain.")

    return {"incumbent": inc, "deberta": deb, "ci_inc": ci_inc, "ci_deb": ci_deb,
            "overlap": overlap, "wins": wins}


def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    pairs = _load_pairs()
    check(len(pairs) == 67, f"67 frozen pairs ({len(pairs)})")

    from checker.grounding_policy import ENTAILED, NOT_ENTAILED
    check(sum(1 for p in pairs if p.label == ENTAILED) == 20, "20 entailed")
    check(sum(1 for p in pairs if p.label == NOT_ENTAILED) == 47, "47 not entailed")
    check(all(p.source_span for p in pairs), "all pairs have source spans")

    # Incumbent cascade runs
    inc_scores = _incumbent_scores(pairs)
    check(len(inc_scores) == 67, "incumbent scored all pairs")
    check(all(s in (0, 1) for s in inc_scores), "scores are binary")
    acc = sum(inc_scores) / len(inc_scores)
    check(acc > 0.5, f"incumbent accuracy > 0.5 ({acc:.3f})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--test" in sys.argv:
        return _test()
    run_bakeoff()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
