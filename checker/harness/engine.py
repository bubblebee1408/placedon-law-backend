"""Deterministic legal workflow harness: orchestrator, evidence ledger, capability adapters.

Informed by:
  - "Stop Comparing LLM Agents Without Disclosing the Harness" (arXiv:2605.23950)
  - "Harness Engineering for Auditable Enterprise LLM Agents" (arXiv:2607.08028)
  - "CiteGuard-RAG" (arXiv:2609.15830)

The orchestrator is a state machine, not a free-form agent loop. Each stage declares
inputs, outputs, retry policy, and failure behavior. Every source, quote, tier, and
verification result is recorded in an append-only evidence ledger.

Run: PYTHONPATH=. python3 checker/harness/engine.py
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

__all__ = [
    "StageStatus", "CapabilityResult", "EvidenceRecord", "EvidenceLedger",
    "Stage", "Workflow", "WorkflowRun", "Orchestrator",
    "AuthorityTier", "PolicyEngine",
]


# ── Authority tiers ────────────────────────────────────────────────────────

class AuthorityTier(str, Enum):
    PRIMARY = "PRIMARY"
    LICENSED = "LICENSED"
    MACHINE = "MACHINE"


# ── Policy engine ──────────────────────────────────────────────────────────

class PolicyEngine:
    """Declarative policy: LICENSED never VERIFIED, MACHINE never authoritative."""

    RULES = {
        "licensed_never_verified": "A LICENSED source may SUPPORT an answer, never make one VERIFIED.",
        "machine_never_authoritative": "Machine output (translation, extraction, summary) is always MACHINE_TRANSLATED until human-reviewed.",
        "every_claim_needs_source": "Every material claim must resolve to a stored evidence record.",
        "no_unsupported_conclusion": "No legal conclusion without a PRIMARY or LICENSED evidence record.",
    }

    @staticmethod
    def check_tier_promotion(from_tier: AuthorityTier, to_status: str) -> str | None:
        """Return violation message if promotion is illegal, else None."""
        if from_tier == AuthorityTier.LICENSED and to_status == "VERIFIED":
            return PolicyEngine.RULES["licensed_never_verified"]
        if from_tier == AuthorityTier.MACHINE and to_status in ("VERIFIED", "PARTIALLY_VERIFIED"):
            return PolicyEngine.RULES["machine_never_authoritative"]
        return None

    @staticmethod
    def check_evidence_coverage(claims: list[dict], ledger: EvidenceLedger) -> list[str]:
        """Return list of violations for claims without evidence."""
        violations = []
        for c in claims:
            claim_id = c.get("claim_id", "unknown")
            records = ledger.records_for(claim_id)
            if not records:
                violations.append(f"Claim '{claim_id}': {PolicyEngine.RULES['every_claim_needs_source']}")
        return violations


# ── Capability result envelope ─────────────────────────────────────────────

class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    PARTIAL = "PARTIAL"
    WAITING_INPUT = "WAITING_INPUT"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETRYABLE = "RETRYABLE"
    ESCALATED = "ESCALATED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class CapabilityResult:
    """Standard envelope every capability adapter returns."""
    status: StageStatus
    output: Any = None
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    trace_id: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "output": self.output,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "trace_id": self.trace_id,
            "elapsed_ms": self.elapsed_ms,
        }


# ── Evidence ledger ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    matter_id: str
    stage: str
    source_type: str
    source_uri: str
    quote: str
    authority_tier: str
    verification_status: str
    timestamp: float
    actor: str = "system"
    claim_id: str = ""
    playbook_version: str = ""
    model_version: str = ""
    extra: dict = field(default_factory=dict)


class EvidenceLedger:
    """Append-only, immutable evidence store."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def append(self, record: EvidenceRecord) -> None:
        self._records.append(record)

    def records_for(self, claim_id: str) -> list[EvidenceRecord]:
        return [r for r in self._records if r.claim_id == claim_id]

    def records_for_stage(self, stage: str) -> list[EvidenceRecord]:
        return [r for r in self._records if r.stage == stage]

    @property
    def all_records(self) -> list[EvidenceRecord]:
        return list(self._records)

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self._records]


# ── Workflow schema ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Stage:
    name: str
    capability: str
    required: bool = True
    retry_limit: int = 1
    timeout_ms: int = 30000
    needs_human_review: bool = False
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class Workflow:
    id: str
    version: str
    stages: tuple[Stage, ...]

    def stage_by_name(self, name: str) -> Stage | None:
        return next((s for s in self.stages if s.name == name), None)


# ── Built-in workflow: contract_review_v1 ──────────────────────────────────

CONTRACT_REVIEW_V1 = Workflow(
    id="contract_review_v1",
    version="1",
    stages=(
        Stage("classify_matter", "task_router"),
        Stage("retrieve_context", "retrieval", depends_on=("classify_matter",)),
        Stage("verify_citations", "citation_verifier", depends_on=("retrieve_context",)),
        Stage("evaluate_playbook", "playbook_evaluator", depends_on=("classify_matter",)),
        Stage("synthesize_findings", "synthesizer",
              depends_on=("verify_citations", "evaluate_playbook")),
        Stage("translate_if_needed", "translation", required=False,
              depends_on=("synthesize_findings",)),
        Stage("request_human_review", "human_review", needs_human_review=True,
              depends_on=("synthesize_findings",)),
        Stage("export_document", "export", depends_on=("request_human_review",)),
    ),
)


# ── Orchestrator ───────────────────────────────────────────────────────────

@dataclass
class StageResult:
    stage_name: str
    status: StageStatus
    result: CapabilityResult | None = None
    error: str = ""
    retries: int = 0


@dataclass
class WorkflowRun:
    run_id: str
    workflow: Workflow
    matter_id: str
    stage_results: dict[str, StageResult] = field(default_factory=dict)
    ledger: EvidenceLedger = field(default_factory=EvidenceLedger)
    status: StageStatus = StageStatus.PENDING
    started_at: float = 0.0
    finished_at: float = 0.0

    def to_report(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow.id,
            "workflow_version": self.workflow.version,
            "matter_id": self.matter_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": (self.finished_at - self.started_at) * 1000 if self.finished_at else 0,
            "stages": {
                name: {
                    "status": sr.status.value,
                    "error": sr.error,
                    "retries": sr.retries,
                    "result": sr.result.to_dict() if sr.result else None,
                }
                for name, sr in self.stage_results.items()
            },
            "evidence_count": len(self.ledger.all_records),
            "evidence": self.ledger.to_list(),
        }


CapabilityAdapter = Callable[[dict, EvidenceLedger], CapabilityResult]


class Orchestrator:
    """Runs a workflow as a deterministic state machine."""

    def __init__(self, adapters: dict[str, CapabilityAdapter] | None = None) -> None:
        self._adapters: dict[str, CapabilityAdapter] = adapters or {}

    def register(self, capability: str, adapter: CapabilityAdapter) -> None:
        self._adapters[capability] = adapter

    def run(self, workflow: Workflow, matter: dict) -> WorkflowRun:
        run = WorkflowRun(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            workflow=workflow,
            matter_id=matter.get("matter_id", "unknown"),
        )
        run.status = StageStatus.RUNNING
        run.started_at = time.time()

        for stage in workflow.stages:
            # check dependencies
            deps_ok = all(
                run.stage_results.get(d, StageResult(d, StageStatus.FAILED)).status
                in (StageStatus.SUCCEEDED, StageStatus.PARTIAL, StageStatus.SKIPPED)
                for d in stage.depends_on
            )
            if not deps_ok:
                if stage.required:
                    run.stage_results[stage.name] = StageResult(
                        stage.name, StageStatus.FAILED,
                        error="dependency not met",
                    )
                    run.status = StageStatus.FAILED
                    run.finished_at = time.time()
                    return run
                else:
                    run.stage_results[stage.name] = StageResult(
                        stage.name, StageStatus.SKIPPED,
                    )
                    continue

            adapter = self._adapters.get(stage.capability)
            if adapter is None:
                if stage.required:
                    run.stage_results[stage.name] = StageResult(
                        stage.name, StageStatus.FAILED,
                        error=f"no adapter for '{stage.capability}'",
                    )
                    run.status = StageStatus.FAILED
                    run.finished_at = time.time()
                    return run
                else:
                    run.stage_results[stage.name] = StageResult(
                        stage.name, StageStatus.SKIPPED,
                    )
                    continue

            ctx = {**matter, "stage": stage.name, "run_id": run.run_id,
                   "prior_results": {k: v.result for k, v in run.stage_results.items() if v.result}}
            sr = StageResult(stage.name, StageStatus.RUNNING)

            for attempt in range(stage.retry_limit):
                try:
                    result = adapter(ctx, run.ledger)
                    sr.result = result
                    sr.retries = attempt
                    if result.status in (StageStatus.SUCCEEDED, StageStatus.PARTIAL):
                        sr.status = result.status
                        break
                    elif result.status == StageStatus.NEEDS_HUMAN_REVIEW:
                        sr.status = StageStatus.NEEDS_HUMAN_REVIEW
                        break
                    elif result.status == StageStatus.DEGRADED:
                        sr.status = StageStatus.DEGRADED
                        break
                    else:
                        sr.status = StageStatus.FAILED
                        sr.error = str(result.warnings) if result.warnings else "adapter returned non-success"
                except Exception as e:
                    sr.status = StageStatus.FAILED
                    sr.error = str(e)
                    sr.retries = attempt

            run.stage_results[stage.name] = sr

            if sr.status == StageStatus.FAILED and stage.required:
                run.status = StageStatus.FAILED
                run.finished_at = time.time()
                return run

            if sr.status == StageStatus.NEEDS_HUMAN_REVIEW:
                run.status = StageStatus.NEEDS_HUMAN_REVIEW
                run.finished_at = time.time()
                return run

        run.status = StageStatus.SUCCEEDED
        run.finished_at = time.time()
        return run


# ── self-test ──────────────────────────────────────────────────────────────

def _self_test() -> None:
    ok = fail = 0

    def check(name: str, cond: bool) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {name}")
        else:
            fail += 1; print(f"  [FAIL] {name}")

    # --- Workflow schema ---
    check("contract_review has 8 stages", len(CONTRACT_REVIEW_V1.stages) == 8)
    check("first stage is classify", CONTRACT_REVIEW_V1.stages[0].name == "classify_matter")
    check("export depends on human_review",
          "request_human_review" in CONTRACT_REVIEW_V1.stages[-1].depends_on)
    check("translate is optional",
          not CONTRACT_REVIEW_V1.stage_by_name("translate_if_needed").required)

    # --- Evidence ledger ---
    ledger = EvidenceLedger()
    rec = EvidenceRecord(
        record_id="ev1", matter_id="m1", stage="retrieve_context",
        source_type="statute", source_uri="ACT:CA2013:S173",
        quote="Board of Directors shall hold...", authority_tier="PRIMARY",
        verification_status="VERIFIED", timestamp=time.time(),
        claim_id="payment_terms",
    )
    ledger.append(rec)
    check("ledger has 1 record", len(ledger.all_records) == 1)
    check("records_for finds by claim_id", len(ledger.records_for("payment_terms")) == 1)
    check("records_for_stage works", len(ledger.records_for_stage("retrieve_context")) == 1)
    check("ledger is serializable", isinstance(ledger.to_list()[0], dict))

    # --- Policy engine ---
    check("LICENSED→VERIFIED blocked",
          PolicyEngine.check_tier_promotion(AuthorityTier.LICENSED, "VERIFIED") is not None)
    check("PRIMARY→VERIFIED allowed",
          PolicyEngine.check_tier_promotion(AuthorityTier.PRIMARY, "VERIFIED") is None)
    check("MACHINE→VERIFIED blocked",
          PolicyEngine.check_tier_promotion(AuthorityTier.MACHINE, "VERIFIED") is not None)
    check("MACHINE→PARTIALLY_VERIFIED blocked",
          PolicyEngine.check_tier_promotion(AuthorityTier.MACHINE, "PARTIALLY_VERIFIED") is not None)
    check("LICENSED→SUPPORTED allowed",
          PolicyEngine.check_tier_promotion(AuthorityTier.LICENSED, "SUPPORTED") is None)

    claims_with_evidence = [{"claim_id": "payment_terms"}]
    claims_without = [{"claim_id": "phantom_claim"}]
    check("covered claim passes", PolicyEngine.check_evidence_coverage(claims_with_evidence, ledger) == [])
    check("uncovered claim fails", len(PolicyEngine.check_evidence_coverage(claims_without, ledger)) == 1)

    # --- CapabilityResult ---
    cr = CapabilityResult(StageStatus.SUCCEEDED, output={"findings": []}, trace_id="t1")
    d = cr.to_dict()
    check("result serializable", d["status"] == "SUCCEEDED")
    check("trace_id preserved", d["trace_id"] == "t1")

    # --- Orchestrator with mock adapters ---
    def mock_classify(ctx, ledger):
        return CapabilityResult(StageStatus.SUCCEEDED, output={"contract_type": "service_agreement"})

    def mock_retrieve(ctx, ledger):
        ledger.append(EvidenceRecord(
            record_id=f"ev_{uuid.uuid4().hex[:6]}", matter_id=ctx["matter_id"],
            stage="retrieve_context", source_type="statute", source_uri="ACT:CA2013:S173",
            quote="relevant text", authority_tier="PRIMARY",
            verification_status="RETRIEVED", timestamp=time.time(),
        ))
        return CapabilityResult(StageStatus.SUCCEEDED, output={"provisions": ["s.173"]})

    def mock_cite_verify(ctx, ledger):
        return CapabilityResult(StageStatus.SUCCEEDED, output={"valid": True})

    def mock_playbook(ctx, ledger):
        ledger.append(EvidenceRecord(
            record_id=f"ev_{uuid.uuid4().hex[:6]}", matter_id=ctx["matter_id"],
            stage="evaluate_playbook", source_type="playbook",
            source_uri="service_agreement_positions_v1",
            quote="payment_terms_days: 45 → FALLBACK", authority_tier="MACHINE",
            verification_status="EVALUATED", timestamp=time.time(),
            playbook_version="1",
        ))
        return CapabilityResult(StageStatus.SUCCEEDED, output={"findings": [
            {"rule_id": "SVC-POS-01", "status": "FALLBACK"},
        ]})

    def mock_synthesize(ctx, ledger):
        return CapabilityResult(StageStatus.SUCCEEDED, output={"summary": "Review complete"})

    def mock_human_review(ctx, ledger):
        return CapabilityResult(StageStatus.NEEDS_HUMAN_REVIEW, output={"requires_approval": True})

    def mock_export(ctx, ledger):
        return CapabilityResult(StageStatus.SUCCEEDED, output={"format": "json"})

    orch = Orchestrator()
    orch.register("task_router", mock_classify)
    orch.register("retrieval", mock_retrieve)
    orch.register("citation_verifier", mock_cite_verify)
    orch.register("playbook_evaluator", mock_playbook)
    orch.register("synthesizer", mock_synthesize)
    orch.register("human_review", mock_human_review)
    orch.register("export", mock_export)

    run = orch.run(CONTRACT_REVIEW_V1, {"matter_id": "test_001"})
    check("run stops at human_review", run.status == StageStatus.NEEDS_HUMAN_REVIEW)
    check("5 stages completed before human_review", len([
        s for s in run.stage_results.values()
        if s.status in (StageStatus.SUCCEEDED, StageStatus.PARTIAL, StageStatus.NEEDS_HUMAN_REVIEW)
    ]) == 6)  # classify + retrieve + cite + playbook + synthesize + human_review
    check("evidence ledger has records", len(run.ledger.all_records) >= 2)
    check("run has a run_id", run.run_id.startswith("run_"))
    check("report is JSON-serializable", isinstance(json.dumps(run.to_report()), str))

    report = run.to_report()
    check("report has workflow_id", report["workflow_id"] == "contract_review_v1")
    check("report has evidence", report["evidence_count"] >= 2)

    # --- Missing adapter fails required stage ---
    orch2 = Orchestrator()
    orch2.register("task_router", mock_classify)
    # no retrieval adapter
    run2 = orch2.run(CONTRACT_REVIEW_V1, {"matter_id": "test_002"})
    check("missing required adapter → FAILED", run2.status == StageStatus.FAILED)
    check("failure on retrieve_context",
          run2.stage_results["retrieve_context"].error == "no adapter for 'retrieval'")

    # --- Optional stage skipped when deps fail ---
    # translate_if_needed depends on synthesize; if synth fails, translate skips
    def mock_fail_synth(ctx, ledger):
        return CapabilityResult(StageStatus.FAILED, warnings=("bad input",))

    orch3 = Orchestrator()
    orch3.register("task_router", mock_classify)
    orch3.register("retrieval", mock_retrieve)
    orch3.register("citation_verifier", mock_cite_verify)
    orch3.register("playbook_evaluator", mock_playbook)
    orch3.register("synthesizer", mock_fail_synth)
    run3 = orch3.run(CONTRACT_REVIEW_V1, {"matter_id": "test_003"})
    check("synth failure → workflow FAILED", run3.status == StageStatus.FAILED)

    # --- Retry on transient failure ---
    call_count = [0]
    def flaky_classify(ctx, ledger):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("transient")
        return CapabilityResult(StageStatus.SUCCEEDED, output={"type": "nda"})

    retry_workflow = Workflow("retry_test", "1", (
        Stage("classify", "classifier", retry_limit=3),
    ))
    orch4 = Orchestrator({"classifier": flaky_classify})
    run4 = orch4.run(retry_workflow, {"matter_id": "test_004"})
    check("retry succeeds on 2nd attempt", run4.status == StageStatus.SUCCEEDED)
    check("retries recorded", run4.stage_results["classify"].retries == 1)

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
