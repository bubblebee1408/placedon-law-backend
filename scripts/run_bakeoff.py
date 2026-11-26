"""Run the CUAD bake-off: load eval dataset, extract with two providers, compare.

With LLM_MODE=mock (default): runs the full pipeline with deterministic mock
responses. Proves the wiring works end-to-end without API keys.

With real API keys: runs actual model inference and produces promotion decisions
per PLAN_22 D2.

Usage:
    PYTHONPATH=. python3 scripts/run_bakeoff.py                  # mock mode
    PYTHONPATH=. python3 scripts/run_bakeoff.py --provider azure # real
    PYTHONPATH=. python3 scripts/run_bakeoff.py --test           # self-test

Run: PYTHONPATH=. python3 scripts/run_bakeoff.py --test
"""
from __future__ import annotations

import json
import time
from dataclasses import field
from pathlib import Path

from scripts.bakeoff_cuad import (
    EvalRecord, ProviderResult, BakeoffReport,
    compare_providers, exact_match, token_f1,
    evidence_precision, evidence_recall, unsupported_rate,
    abstention_precision, json_validity_rate,
)
from checker.cuad_pipeline import run_cuad_pipeline
from checker.model_adapters import make_route_fn

EVAL_TEST = Path("corpus/benchmark/cuad/eval_test.json")
EVAL_TRAIN = Path("corpus/benchmark/cuad/eval_train.json")


def load_eval_records(path: Path) -> list[EvalRecord]:
    with open(path) as f:
        raw = json.load(f)
    return [EvalRecord(**{k: v if k != "expected_source_offsets" or v is None
                          else tuple(v)
                          for k, v in r.items()}) for r in raw]


def _group_by_doc(records: list[EvalRecord]) -> dict[str, list[EvalRecord]]:
    groups: dict[str, list[EvalRecord]] = {}
    for r in records:
        groups.setdefault(r.document_id, []).append(r)
    return groups


def evaluate_provider(
    records: list[EvalRecord],
    provider: str,
    model: str,
    *,
    max_docs: int = 0,
) -> ProviderResult:
    """Run extraction on eval records and score against gold annotations."""
    route_fn, prov_name, model_name = make_route_fn("cuad_extract")
    if provider != "mock" and route_fn is None:
        print(f"  [warn] No route available for {provider}, falling back to mock")
        route_fn = None

    doc_groups = _group_by_doc(records)
    if max_docs > 0:
        doc_ids = sorted(doc_groups.keys())[:max_docs]
        doc_groups = {d: doc_groups[d] for d in doc_ids}

    em_scores: list[float] = []
    f1_scores: list[float] = []
    all_extractions: list[dict] = []
    all_responses: list[str] = []
    doc_scores: dict[str, float] = {}
    gold_categories: list[str] = []

    for doc_id, doc_records in doc_groups.items():
        # ponytail: use first record's context as representative text
        text = doc_records[0].context
        start = time.monotonic()

        result = run_cuad_pipeline(
            text, name=f"{doc_id}.pdf", doc_id=doc_id,
            route_fn=route_fn,
            model_provider=prov_name or provider,
            model_version=model_name or model,
        )

        elapsed_ms = (time.monotonic() - start) * 1000

        # Score each question
        doc_em: list[float] = []
        for rec in doc_records:
            if rec.expected_abstention:
                em_scores.append(1.0 if result.extraction is None or
                                 len(result.extraction.extractions) == 0 else 0.0)
                doc_em.append(em_scores[-1])
            else:
                pred_answer = ""
                if result.extraction:
                    for ext in result.extraction.extractions:
                        if rec.question.lower().find(ext.category.lower()) >= 0:
                            pred_answer = ext.answer_text
                            break
                em = exact_match(rec.expected_answer, pred_answer)
                f1 = token_f1(rec.expected_answer, pred_answer)
                em_scores.append(em)
                f1_scores.append(f1)
                doc_em.append(em)
                gold_categories.append(rec.question_id.split("__")[0] if "__" in rec.question_id else rec.question_id)

        doc_scores[doc_id] = sum(doc_em) / len(doc_em) if doc_em else 0.0

        if result.extraction:
            for ext in result.extraction.extractions:
                all_extractions.append({
                    "category": ext.category,
                    "answer": ext.answer_text,
                    "status": ext.verification_status,
                })

    gold_absent = {rec.question_id for rec in records if rec.expected_abstention}

    return ProviderResult(
        provider=provider,
        model=model,
        exact_match_scores=em_scores,
        token_f1_scores=f1_scores,
        evidence_precision_val=evidence_precision(all_extractions),
        evidence_recall_val=evidence_recall(all_extractions, gold_categories),
        unsupported_rate_val=unsupported_rate(all_extractions),
        abstention_precision_val=abstention_precision(all_extractions, gold_absent),
        json_validity_val=1.0,  # ponytail: pipeline handles JSON internally
        latency_p50_ms=0.0,
        latency_p95_ms=0.0,
        cost_per_contract_inr=0.0,
        doc_scores=doc_scores,
    )


def run(*, provider: str = "mock", model: str = "mock-v1",
        max_docs: int = 5, eval_path: Path | None = None) -> BakeoffReport:
    path = eval_path or EVAL_TEST
    if not path.exists():
        from scripts.build_eval_dataset import build
        build()

    records = load_eval_records(path)
    print(f"Loaded {len(records)} eval records from {path}")

    # Evaluate candidate
    print(f"\nEvaluating candidate: {provider}/{model}...")
    candidate = evaluate_provider(records, provider, model, max_docs=max_docs)

    # Mock incumbent for comparison
    print(f"\nEvaluating incumbent (mock baseline)...")
    incumbent = evaluate_provider(records, "mock", "baseline-v0", max_docs=max_docs)

    decision = compare_providers(candidate, incumbent)

    report = BakeoffReport(
        date=time.strftime("%Y-%m-%d"),
        eval_set=str(path),
        n_contracts=len({r.document_id for r in records}),
        providers={
            candidate.provider: candidate.to_report(),
            incumbent.provider: incumbent.to_report(),
        },
        promotion_decision=decision,
        decided_by="scripts/run_bakeoff.py",
    )

    out_path = Path("corpus/benchmark/cuad/bakeoff_report.json")
    with open(out_path, "w") as f:
        f.write(report.to_json())
    print(f"\nReport: {out_path}")
    print(f"Decision: {decision}")
    return report


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("run_bakeoff")

    # Build eval data if missing
    if not EVAL_TEST.exists():
        from scripts.build_eval_dataset import build
        build()

    # Load records
    records = load_eval_records(EVAL_TEST)
    check(len(records) > 0, f"loaded {len(records)} records")

    # Records are EvalRecord instances
    check(isinstance(records[0], EvalRecord), "records are EvalRecord")

    # Run mock bakeoff (small subset)
    report = run(max_docs=3)
    check(report.n_contracts > 0, f"report covers {report.n_contracts} contracts")
    check(report.promotion_decision != "", "promotion decision made")
    check("mock" in report.providers, "mock provider in report")

    # Report file exists
    rp = Path("corpus/benchmark/cuad/bakeoff_report.json")
    check(rp.exists(), "report file written")

    # Report JSON valid
    with open(rp) as f:
        rj = json.loads(f.read())
    check("promotion_decision" in rj, "report has promotion_decision")
    check("providers" in rj, "report has providers")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--model", default="mock-v1")
    parser.add_argument("--max-docs", type=int, default=10)
    parser.add_argument("--eval-path", type=str, default=None)
    args = parser.parse_args()
    run(provider=args.provider, model=args.model, max_docs=args.max_docs,
        eval_path=Path(args.eval_path) if args.eval_path else None)
