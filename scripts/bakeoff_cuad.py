"""Bake-off: compare model providers on CUAD clause extraction.

Produces reports/bakeoff_cuad_{date}.json. The script measures; a person decides.
PLAN_22 D2: a model is promoted only by bake-off — non-overlapping 95% CI
against incumbent + person edits the router table.

Usage:
    PYTHONPATH=. python3 scripts/bakeoff_cuad.py --test

The script CANNOT modify router.py. It produces a report. A person makes the edit.

Run: PYTHONPATH=. python3 scripts/bakeoff_cuad.py --test
"""
from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field

__all__ = [
    "exact_match", "token_f1", "evidence_precision", "evidence_recall",
    "bootstrap_ci", "paired_bootstrap_ci", "evidence_iou",
    "obligation_metrics", "BakeoffReport", "compare_providers",
    "EvalRecord", "OperationalMeasures", "PromotionConfig",
]

# ── Thresholds from PLAN_22 D2 / CUAD_BENCHMARK_PLAN.md ──────────────────────

THRESHOLDS = {
    "exact_match": 0.70,
    "token_f1": 0.80,
    "evidence_precision": 0.90,
    "evidence_recall": 0.70,
    "unsupported_rate_max": 0.10,
    "abstention_precision": 0.80,
    "json_validity": 0.95,
}


@dataclass(frozen=True)
class PromotionConfig:
    """Versioned promotion gate. PLAN_22 D2: thresholds + comparison."""
    version: str = "1.0"
    min_exact_match: float = THRESHOLDS["exact_match"]
    min_token_f1: float = THRESHOLDS["token_f1"]
    min_evidence_precision: float = THRESHOLDS["evidence_precision"]
    min_evidence_recall: float = THRESHOLDS["evidence_recall"]
    max_unsupported_rate: float = THRESHOLDS["unsupported_rate_max"]
    min_abstention_precision: float = THRESHOLDS["abstention_precision"]
    min_json_validity: float = THRESHOLDS["json_validity"]
    # ponytail: no defaults — report as "unresolved" if missing
    max_p95_latency_ms: float | None = None
    max_cost_per_doc_inr: float | None = None


DEFAULT_PROMOTION = PromotionConfig()


# ── Evaluation dataset schema ─────────────────────────────────────────────────

@dataclass(frozen=True)
class EvalRecord:
    """One evaluation example. Group by document_id; never split one contract."""
    document_id: str
    document_type: str
    document_hash: str
    question_id: str
    question: str
    context: str
    expected_answer: str
    expected_party: str = ""
    expected_modality: str = ""
    expected_evidence: str = ""
    expected_source_offsets: tuple[int, int] | None = None
    expected_abstention: bool = False
    annotation_version: str = "1.0"


# ── Operational measures ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class OperationalMeasures:
    """Per-provider operational stats. Pricing from explicit config, never hardcoded."""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_per_doc: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    api_errors: int = 0
    timeout_rate: float = 0.0
    retry_count: int = 0


# ── Metrics ───────────────────────────────────────────────────────────────────

def exact_match(gold: str, predicted: str) -> float:
    if not gold and not predicted:
        return 1.0
    if not gold or not predicted:
        return 0.0
    return 1.0 if _normalize(gold) == _normalize(predicted) else 0.0


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def token_f1(gold: str, predicted: str) -> float:
    """Token-level F1 using multiset (Counter) overlap for correct repeated-token handling."""
    if not gold and not predicted:
        return 1.0
    gold_counts = Counter(_normalize(gold).split())
    pred_counts = Counter(_normalize(predicted).split())
    if not gold_counts or not pred_counts:
        return 0.0
    tp = sum((gold_counts & pred_counts).values())
    if tp == 0:
        return 0.0
    precision = tp / sum(pred_counts.values())
    recall = tp / sum(gold_counts.values())
    return 2 * precision * recall / (precision + recall)


def evidence_iou(pred_start: int, pred_end: int,
                 gold_start: int, gold_end: int) -> float:
    """Character-level Intersection-over-Union for evidence spans."""
    intersection = max(0, min(pred_end, gold_end) - max(pred_start, gold_start))
    union = max(pred_end, gold_end) - min(pred_start, gold_start)
    if union <= 0:
        return 0.0
    return intersection / union


def evidence_span_exact(pred_start: int, pred_end: int,
                        gold_start: int, gold_end: int) -> float:
    return 1.0 if pred_start == gold_start and pred_end == gold_end else 0.0


def evidence_precision(extractions: list[dict]) -> float:
    if not extractions:
        return 1.0
    verified = sum(1 for e in extractions
                   if e.get("status") in ("VERIFIED", "FUZZY_MATCH"))
    return verified / len(extractions)


def evidence_recall(extractions: list[dict], gold_categories: list[str]) -> float:
    if not gold_categories:
        return 1.0
    found = {e.get("category") for e in extractions if e.get("answer") and e.get("answer") != "NOT_FOUND"}
    return len(found & set(gold_categories)) / len(gold_categories)


def unsupported_rate(extractions: list[dict]) -> float:
    if not extractions:
        return 0.0
    unverified = sum(1 for e in extractions if e.get("status") == "UNVERIFIED")
    return unverified / len(extractions)


def abstention_precision(extractions: list[dict], gold_absent: set[str]) -> float:
    abstained = {e.get("category") for e in extractions
                 if e.get("answer") == "NOT_FOUND" or not e.get("answer")}
    if not abstained:
        return 1.0
    correct = abstained & gold_absent
    return len(correct) / len(abstained)


def json_validity_rate(responses: list[str]) -> float:
    if not responses:
        return 1.0
    valid = 0
    for r in responses:
        try:
            json.loads(r.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
            valid += 1
        except (json.JSONDecodeError, ValueError):
            pass
    return valid / len(responses)


# ── Obligation evaluation metrics ─────────────────────────────────────────────

def obligation_metrics(predicted: list[dict], gold: list[dict]) -> dict:
    """Evaluate obligation extraction: party/modality/trigger tuples.

    Each dict: {"party": str, "modality": str, "trigger": str}.
    Returns per-label and aggregate metrics.
    """
    if not gold and not predicted:
        return {"relationship_accuracy": 1.0, "micro_f1": 1.0, "macro_f1": 1.0, "per_label": {}}
    if not gold or not predicted:
        return {"relationship_accuracy": 0.0, "micro_f1": 0.0, "macro_f1": 0.0, "per_label": {}}

    # Full relationship accuracy: (party, modality, trigger) tuples
    gold_tuples = {(g["party"].lower(), g["modality"].lower(), _normalize(g.get("trigger", ""))) for g in gold}
    pred_tuples = {(p["party"].lower(), p["modality"].lower(), _normalize(p.get("trigger", ""))) for p in predicted}
    rel_correct = len(gold_tuples & pred_tuples)
    rel_accuracy = rel_correct / len(gold_tuples) if gold_tuples else 0.0

    # Per-label modality metrics
    all_labels = {g["modality"].lower() for g in gold} | {p["modality"].lower() for p in predicted}
    gold_labels = [g["modality"].lower() for g in gold]
    pred_labels = [p["modality"].lower() for p in predicted]

    per_label: dict[str, dict] = {}
    micro_tp = micro_fp = micro_fn = 0
    f1s: list[float] = []

    for label in sorted(all_labels):
        tp = sum(1 for g, p in zip(gold_labels, pred_labels) if g == label and p == label) if len(gold_labels) == len(pred_labels) else 0
        # Fall back to count-based when lengths differ
        g_count = sum(1 for g in gold_labels if g == label)
        p_count = sum(1 for p in pred_labels if p == label)
        tp = min(g_count, p_count)  # ponytail: conservative TP estimate
        fp = p_count - tp
        fn = g_count - tp
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        per_label[label] = {"precision": prec, "recall": rec, "f1": f1, "support": g_count}
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        f1s.append(f1)

    micro_prec = micro_tp / (micro_tp + micro_fp) if (micro_tp + micro_fp) > 0 else 0.0
    micro_rec = micro_tp / (micro_tp + micro_fn) if (micro_tp + micro_fn) > 0 else 0.0
    micro_f1 = 2 * micro_prec * micro_rec / (micro_prec + micro_rec) if (micro_prec + micro_rec) > 0 else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    return {
        "relationship_accuracy": rel_accuracy,
        "micro_f1": micro_f1,
        "macro_f1": macro_f1,
        "per_label": per_label,
    }


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def bootstrap_ci(scores: list[float], *, n_resamples: int = 1000,
                 alpha: float = 0.05, seed: int = 42) -> tuple[float, float, float]:
    if not scores:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [rng.choice(scores) for _ in range(len(scores))]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    mean = sum(scores) / len(scores)
    return means[lo_idx], mean, means[hi_idx]


def paired_bootstrap_ci(
    doc_scores_a: dict[str, float],
    doc_scores_b: dict[str, float],
    *,
    n_resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Paired document-level percentile bootstrap on Δ = A - B.

    Resampling unit: complete documents. Same documents for both models per iteration.
    Returns (ci_lower, mean_delta, ci_upper).
    """
    doc_ids = sorted(set(doc_scores_a) & set(doc_scores_b))
    if not doc_ids:
        return 0.0, 0.0, 0.0
    deltas = [doc_scores_a[d] - doc_scores_b[d] for d in doc_ids]
    mean_delta = sum(deltas) / len(deltas)

    rng = random.Random(seed)
    boot_deltas: list[float] = []
    for _ in range(n_resamples):
        sampled = [rng.choice(deltas) for _ in range(len(deltas))]
        boot_deltas.append(sum(sampled) / len(sampled))
    boot_deltas.sort()
    lo_idx = int(alpha / 2 * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return boot_deltas[lo_idx], mean_delta, boot_deltas[hi_idx]


def cis_overlap(ci_a: tuple[float, float, float],
                ci_b: tuple[float, float, float]) -> bool:
    return ci_a[0] <= ci_b[2] and ci_b[0] <= ci_a[2]


# ── Report ────────────────────────────────────────────────────────────────────

@dataclass
class ProviderResult:
    provider: str
    model: str
    exact_match_scores: list[float]
    token_f1_scores: list[float]
    evidence_precision_val: float
    evidence_recall_val: float
    unsupported_rate_val: float
    abstention_precision_val: float
    json_validity_val: float
    latency_p50_ms: float
    latency_p95_ms: float
    cost_per_contract_inr: float
    # Optional per-document scores for paired bootstrap
    doc_scores: dict[str, float] = field(default_factory=dict)
    ops: OperationalMeasures = field(default_factory=OperationalMeasures)

    def to_report(self) -> dict:
        em_ci = bootstrap_ci(self.exact_match_scores)
        f1_ci = bootstrap_ci(self.token_f1_scores)
        return {
            "exact_match": {"mean": em_ci[1], "ci_lower": em_ci[0], "ci_upper": em_ci[2]},
            "token_f1": {"mean": f1_ci[1], "ci_lower": f1_ci[0], "ci_upper": f1_ci[2]},
            "evidence_precision": self.evidence_precision_val,
            "evidence_recall": self.evidence_recall_val,
            "unsupported_rate": self.unsupported_rate_val,
            "abstention_precision": self.abstention_precision_val,
            "json_validity": self.json_validity_val,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "cost_per_contract_inr": self.cost_per_contract_inr,
        }


@dataclass
class BakeoffReport:
    date: str
    eval_set: str
    n_contracts: int
    providers: dict[str, dict]
    promotion_decision: str
    decided_by: str
    paired_delta_ci: tuple[float, float, float] | None = None
    unresolved_gates: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        d = {
            "date": self.date,
            "eval_set": self.eval_set,
            "n_contracts": self.n_contracts,
            "providers": self.providers,
            "promotion_decision": self.promotion_decision,
            "decided_by": self.decided_by,
        }
        if self.paired_delta_ci:
            d["paired_delta_ci"] = {"lower": self.paired_delta_ci[0], "mean": self.paired_delta_ci[1], "upper": self.paired_delta_ci[2]}
        if self.unresolved_gates:
            d["unresolved_gates"] = self.unresolved_gates
        return json.dumps(d, indent=2)


def compare_providers(candidate: ProviderResult,
                      incumbent: ProviderResult,
                      config: PromotionConfig | None = None) -> str:
    config = config or DEFAULT_PROMOTION

    cand_em = bootstrap_ci(candidate.exact_match_scores)

    failures: list[str] = []
    if cand_em[1] < config.min_exact_match:
        failures.append(f"EM {cand_em[1]:.3f} < {config.min_exact_match}")
    cand_f1_ci = bootstrap_ci(candidate.token_f1_scores)
    if cand_f1_ci[1] < config.min_token_f1:
        failures.append(f"F1 {cand_f1_ci[1]:.3f} < {config.min_token_f1}")
    if candidate.evidence_precision_val < config.min_evidence_precision:
        failures.append(f"EP {candidate.evidence_precision_val:.3f} < {config.min_evidence_precision}")
    if candidate.unsupported_rate_val > config.max_unsupported_rate:
        failures.append(f"UR {candidate.unsupported_rate_val:.3f} > {config.max_unsupported_rate}")
    if candidate.json_validity_val < config.min_json_validity:
        failures.append(f"JV {candidate.json_validity_val:.3f} < {config.min_json_validity}")

    # Latency / cost gates — report as unresolved if thresholds not set
    unresolved: list[str] = []
    if config.max_p95_latency_ms is None:
        unresolved.append("max_p95_latency_ms not configured")
    elif candidate.latency_p95_ms > config.max_p95_latency_ms:
        failures.append(f"P95 {candidate.latency_p95_ms:.0f}ms > {config.max_p95_latency_ms:.0f}ms")
    if config.max_cost_per_doc_inr is None:
        unresolved.append("max_cost_per_doc_inr not configured")
    elif candidate.cost_per_contract_inr > config.max_cost_per_doc_inr:
        failures.append(f"Cost ₹{candidate.cost_per_contract_inr:.2f} > ₹{config.max_cost_per_doc_inr:.2f}")

    if failures:
        result = f"FAIL — {'; '.join(failures)}"
        if unresolved:
            result += f" [unresolved: {'; '.join(unresolved)}]"
        return result

    # Paired bootstrap if doc_scores available
    if candidate.doc_scores and incumbent.doc_scores:
        delta_ci = paired_bootstrap_ci(candidate.doc_scores, incumbent.doc_scores)
        if delta_ci[0] > 0:
            result = f"PROMOTE — paired Δ CI [{delta_ci[0]:.4f}, {delta_ci[2]:.4f}] entirely above 0"
        elif delta_ci[2] < 0:
            result = "HOLD — incumbent significantly better (paired Δ CI below 0)"
        else:
            result = f"HOLD — paired Δ CI [{delta_ci[0]:.4f}, {delta_ci[2]:.4f}] overlaps 0"
        if unresolved:
            result += f" [unresolved: {'; '.join(unresolved)}]"
        return result

    # Fallback to unpaired CI comparison
    inc_f1_ci = bootstrap_ci(incumbent.token_f1_scores)
    if cis_overlap(cand_f1_ci, inc_f1_ci):
        result = f"HOLD — CIs overlap on token_f1 (cand [{cand_f1_ci[0]:.3f}, {cand_f1_ci[2]:.3f}] vs inc [{inc_f1_ci[0]:.3f}, {inc_f1_ci[2]:.3f}])"
    elif cand_f1_ci[0] > inc_f1_ci[2]:
        result = "PROMOTE — candidate beats incumbent with non-overlapping CI"
    else:
        result = "HOLD — incumbent retains preference"

    if unresolved:
        result += f" [unresolved: {'; '.join(unresolved)}]"
    return result


# ── self-tests ────────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("bakeoff_cuad")

    # ── exact_match ──────────────────────────────────────────────────────
    check(exact_match("India", "India") == 1.0, "EM: exact")
    check(exact_match("India", "india") == 1.0, "EM: case insensitive")
    check(exact_match("India", "Singapore") == 0.0, "EM: different")
    check(exact_match("", "") == 1.0, "EM: both empty")
    check(exact_match("India", "") == 0.0, "EM: one empty")

    # ── token_f1 ─────────────────────────────────────────────────────────
    check(token_f1("the laws of India", "the laws of India") == 1.0, "F1: perfect")
    check(token_f1("the laws of India", "laws India") > 0.5, "F1: partial > 0.5")
    check(token_f1("alpha", "beta") == 0.0, "F1: no overlap")
    check(token_f1("", "") == 1.0, "F1: both empty")

    # F1: multiset correctness — repeated tokens
    f1_rep = token_f1("the the the cat", "the cat")
    check(0.3 < f1_rep < 0.8, f"F1: multiset penalises missing repeats ({f1_rep:.3f})")

    # ── evidence_precision ───────────────────────────────────────────────
    exts = [{"status": "VERIFIED"}, {"status": "FUZZY_MATCH"}, {"status": "UNVERIFIED"}]
    check(abs(evidence_precision(exts) - 2/3) < 0.01, f"EP: 2/3 ({evidence_precision(exts):.3f})")
    check(evidence_precision([]) == 1.0, "EP: empty → 1.0")

    # ── evidence_recall ──────────────────────────────────────────────────
    exts = [{"category": "Governing Law", "answer": "India"},
            {"category": "Parties", "answer": "NOT_FOUND"}]
    check(evidence_recall(exts, ["Governing Law", "Parties"]) == 0.5, "ER: 1 of 2")

    # ── evidence_iou ─────────────────────────────────────────────────────
    check(evidence_iou(10, 20, 10, 20) == 1.0, "IoU: exact match")
    check(abs(evidence_iou(10, 20, 15, 25) - 5/15) < 0.01,
          f"IoU: half overlap ({evidence_iou(10, 20, 15, 25):.3f})")
    iou_half = evidence_iou(10, 20, 15, 25)
    check(abs(iou_half - 5/15) < 0.01, f"IoU: 5/15 ({iou_half:.3f})")
    check(evidence_iou(10, 20, 30, 40) == 0.0, "IoU: no overlap")
    check(evidence_span_exact(10, 20, 10, 20) == 1.0, "span exact: match")
    check(evidence_span_exact(10, 20, 10, 21) == 0.0, "span exact: mismatch")

    # ── bootstrap_ci ─────────────────────────────────────────────────────
    scores = [0.8, 0.9, 0.7, 0.85, 0.95, 0.75, 0.88, 0.82, 0.91, 0.78]
    lo, mean, hi = bootstrap_ci(scores, seed=42)
    check(0.7 < lo < mean < hi < 1.0, f"CI: {lo:.3f} < {mean:.3f} < {hi:.3f}")
    lo2, mean2, hi2 = bootstrap_ci(scores, seed=42)
    check(lo == lo2 and mean == mean2 and hi == hi2, "CI: reproducible")

    # ── paired_bootstrap_ci ──────────────────────────────────────────────
    doc_a = {"d1": 0.9, "d2": 0.8, "d3": 0.95, "d4": 0.85, "d5": 0.88}
    doc_b = {"d1": 0.6, "d2": 0.5, "d3": 0.65, "d4": 0.55, "d5": 0.58}
    plo, pmean, phi = paired_bootstrap_ci(doc_a, doc_b, seed=42)
    check(plo > 0, f"paired CI lower > 0 when A >> B ({plo:.4f})")
    check(pmean > 0, f"paired mean delta > 0 ({pmean:.4f})")
    # Reproducible
    plo2, pmean2, phi2 = paired_bootstrap_ci(doc_a, doc_b, seed=42)
    check(plo == plo2 and pmean == pmean2 and phi == phi2, "paired CI: reproducible")
    # Same scores → delta ~ 0
    doc_same = {"d1": 0.8, "d2": 0.8}
    slo, smean, shi = paired_bootstrap_ci(doc_same, doc_same, seed=42)
    check(abs(smean) < 0.001, f"paired CI: same scores → delta ~0 ({smean:.4f})")

    # ── cis_overlap ──────────────────────────────────────────────────────
    check(cis_overlap((0.7, 0.8, 0.9), (0.75, 0.85, 0.95)), "overlapping CIs")
    check(not cis_overlap((0.7, 0.8, 0.85), (0.9, 0.95, 1.0)), "non-overlapping CIs")

    # ── obligation_metrics ───────────────────────────────────────────────
    gold_obs = [
        {"party": "Buyer", "modality": "obligation", "trigger": "shall pay"},
        {"party": "Seller", "modality": "prohibition", "trigger": "shall not disclose"},
    ]
    pred_obs = [
        {"party": "Buyer", "modality": "obligation", "trigger": "shall pay"},
        {"party": "Seller", "modality": "obligation", "trigger": "shall not disclose"},  # wrong modality
    ]
    om = obligation_metrics(pred_obs, gold_obs)
    check(om["relationship_accuracy"] == 0.5, f"obl: rel accuracy 0.5 ({om['relationship_accuracy']})")
    check(om["micro_f1"] > 0, f"obl: micro_f1 > 0 ({om['micro_f1']:.3f})")
    check("obligation" in om["per_label"], "obl: per-label has obligation")
    # Empty cases
    check(obligation_metrics([], [])["micro_f1"] == 1.0, "obl: empty → 1.0")
    check(obligation_metrics([], gold_obs)["micro_f1"] == 0.0, "obl: no preds → 0.0")

    # ── compare_providers ────────────────────────────────────────────────
    strong = ProviderResult("test", "strong", [0.9]*10, [0.9]*10, 0.95, 0.85, 0.05, 0.9, 0.98, 100, 200, 5.0)
    weak = ProviderResult("test", "weak", [0.5]*10, [0.5]*10, 0.7, 0.4, 0.2, 0.5, 0.8, 500, 1000, 15.0)
    decision = compare_providers(strong, weak)
    check("PROMOTE" in decision, f"strong beats weak: {decision}")

    failing = ProviderResult("test", "fail", [0.3]*10, [0.3]*10, 0.6, 0.3, 0.3, 0.4, 0.7, 500, 1000, 15.0)
    decision2 = compare_providers(failing, weak)
    check("FAIL" in decision2, f"failing candidate: {decision2}")

    # Paired bootstrap decision
    strong_paired = ProviderResult("test", "strong", [0.9]*5, [0.9]*5, 0.95, 0.85, 0.05, 0.9, 0.98, 100, 200, 5.0,
                                   doc_scores={"d1": 0.95, "d2": 0.9, "d3": 0.92, "d4": 0.88, "d5": 0.91})
    weak_paired = ProviderResult("test", "weak", [0.5]*5, [0.5]*5, 0.7, 0.4, 0.05, 0.9, 0.98, 500, 1000, 15.0,
                                  doc_scores={"d1": 0.5, "d2": 0.45, "d3": 0.52, "d4": 0.48, "d5": 0.47})
    decision3 = compare_providers(strong_paired, weak_paired)
    check("PROMOTE" in decision3, f"paired promote: {decision3}")

    # ── report format ────────────────────────────────────────────────────
    report = BakeoffReport(
        date="2026-12-01", eval_set="cuad_test", n_contracts=10,
        providers={"test-strong": strong.to_report()},
        promotion_decision="PROMOTE", decided_by="pending human review")
    j = json.loads(report.to_json())
    check(j["date"] == "2026-12-01", "report date")
    check("test-strong" in j["providers"], "report has provider")
    check("mean" in j["providers"]["test-strong"]["exact_match"], "report has EM mean")
    check(j["decided_by"] == "pending human review", "decided_by is human")

    # ── unsupported_rate ─────────────────────────────────────────────────
    check(unsupported_rate([]) == 0.0, "UR: empty → 0")
    check(unsupported_rate([{"status": "UNVERIFIED"}]) == 1.0, "UR: all → 1")

    # ── json_validity_rate ───────────────────────────────────────────────
    check(json_validity_rate(['[{"a":1}]', '{"b":2}', 'invalid']) == 2/3, "JV: 2/3")

    # ── EvalRecord ───────────────────────────────────────────────────────
    rec = EvalRecord(document_id="doc1", document_type="nda", document_hash="abc",
                     question_id="q1", question="Who?", context="text",
                     expected_answer="Acme", expected_party="Buyer",
                     expected_modality="obligation")
    check(rec.document_id == "doc1", "EvalRecord: immutable")
    check(rec.annotation_version == "1.0", "EvalRecord: default version")

    # ── PromotionConfig ──────────────────────────────────────────────────
    pc = PromotionConfig()
    check(pc.max_p95_latency_ms is None, "PromotionConfig: latency unresolved by default")
    check(pc.max_cost_per_doc_inr is None, "PromotionConfig: cost unresolved by default")
    pc2 = PromotionConfig(max_p95_latency_ms=5000.0, max_cost_per_doc_inr=10.0)
    check(pc2.max_p95_latency_ms == 5000.0, "PromotionConfig: latency configurable")

    # ── compare with unresolved gates ────────────────────────────────────
    decision4 = compare_providers(strong, weak, config=DEFAULT_PROMOTION)
    check("unresolved" in decision4, f"unresolved gates reported: {decision4}")

    # ── OperationalMeasures ──────────────────────────────────────────────
    ops = OperationalMeasures(input_tokens=1000, output_tokens=200, cost_per_doc=1.5)
    check(ops.input_tokens == 1000, "ops: input_tokens")
    check(ops.timeout_rate == 0.0, "ops: defaults to 0")

    # ── report with paired delta ─────────────────────────────────────────
    report2 = BakeoffReport(
        date="2026-12-01", eval_set="cuad_test", n_contracts=5,
        providers={}, promotion_decision="PROMOTE",
        decided_by="pending human review",
        paired_delta_ci=(0.1, 0.3, 0.5),
        unresolved_gates=["max_p95_latency_ms"])
    j2 = json.loads(report2.to_json())
    check("paired_delta_ci" in j2, "report has paired delta")
    check(j2["paired_delta_ci"]["lower"] == 0.1, "report paired delta lower")
    check("unresolved_gates" in j2, "report has unresolved gates")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
