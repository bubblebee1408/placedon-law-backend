"""Harness runner: execute workflows against golden cases, assert invariants, emit JSON report.

Usage:
  PYTHONPATH=. python3 -m checker.harness.runner                    # run all golden cases
  PYTHONPATH=. python3 -m checker.harness.runner --case svc_payment_terms_starting
  PYTHONPATH=. python3 -m checker.harness.runner --json             # machine-readable output
  PYTHONPATH=. python3 checker/harness/runner.py                    # also works

Run: PYTHONPATH=. python3 checker/harness/runner.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from checker.harness.engine import (
    Orchestrator, CONTRACT_REVIEW_V1, StageStatus,
    PolicyEngine, AuthorityTier, EvidenceRecord,
)
from checker.harness.adapters import ADAPTERS, TEST_ADAPTERS
from checker.harness.golden_cases import GOLDEN_CASES


# ── Safety invariants ──────────────────────────────────────────────────────

def check_invariants(run, case: dict) -> list[str]:
    """Check universal safety invariants on a completed run. Returns violations."""
    violations: list[str] = []

    # I1: every evidence record has a non-empty stage
    for rec in run.ledger.all_records:
        if not rec.stage:
            violations.append(f"Evidence record {rec.record_id} has empty stage")

    # I2: no LICENSED source is marked VERIFIED
    for rec in run.ledger.all_records:
        if rec.authority_tier == AuthorityTier.LICENSED.value:
            if rec.verification_status == "VERIFIED":
                violations.append(
                    f"LICENSED source {rec.source_uri} marked VERIFIED — "
                    f"{PolicyEngine.RULES['licensed_never_verified']}")

    # I3: no MACHINE output marked VERIFIED
    for rec in run.ledger.all_records:
        if rec.authority_tier == AuthorityTier.MACHINE.value:
            if rec.verification_status in ("VERIFIED", "PARTIALLY_VERIFIED"):
                violations.append(
                    f"MACHINE output {rec.record_id} marked {rec.verification_status}")

    # I4: workflow that reaches synthesis must have evidence
    if "synthesize_findings" in run.stage_results:
        sr = run.stage_results["synthesize_findings"]
        if sr.status == StageStatus.SUCCEEDED and len(run.ledger.all_records) == 0:
            violations.append("Synthesis succeeded but evidence ledger is empty")

    # I5: expected workflow status
    expected_ws = case.get("expected_workflow_status")
    if expected_ws and run.status.value != expected_ws:
        violations.append(
            f"Expected workflow status {expected_ws}, got {run.status.value}")

    return violations


def check_playbook_assertions(run, case: dict) -> list[str]:
    """Check case-specific playbook assertions."""
    violations: list[str] = []
    expected_rule = case.get("expected_rule")
    expected_status = case.get("expected_status")

    if not expected_rule or not expected_status:
        return violations

    pb_stage = run.stage_results.get("evaluate_playbook")
    if not pb_stage or not pb_stage.result or not pb_stage.result.output:
        violations.append(f"No playbook output to check rule {expected_rule}")
        return violations

    findings = pb_stage.result.output.get("findings", [])
    matched = [f for f in findings if f["rule_id"] == expected_rule]
    if not matched:
        violations.append(f"Rule {expected_rule} not found in playbook findings")
    elif matched[0]["status"] != expected_status:
        violations.append(
            f"Rule {expected_rule}: expected {expected_status}, got {matched[0]['status']}")

    return violations


# ── Runner ─────────────────────────────────────────────────────────────────

def run_golden_suite(case_filter: str | None = None, *, live: bool = False) -> dict:
    """Run all (or filtered) golden cases and return evaluation report."""
    adapters = ADAPTERS if live else TEST_ADAPTERS
    orch = Orchestrator(adapters)
    cases = GOLDEN_CASES
    if case_filter:
        cases = [c for c in cases if c["case_id"] == case_filter]
        if not cases:
            return {"error": f"No case found: {case_filter}"}

    results = []
    total_pass = 0
    total_fail = 0
    started = time.time()

    for case in cases:
        # For adversarial case: inject a LICENSED-as-VERIFIED record after run
        is_adversarial = case.get("inject_licensed_as_verified", False)

        run = orch.run(CONTRACT_REVIEW_V1, case)

        if is_adversarial:
            # Inject the bad record to test invariant detection
            run.ledger.append(EvidenceRecord(
                record_id="ev_adversarial",
                matter_id=case["matter_id"],
                stage="retrieve_context",
                source_type="judgment",
                source_uri="s3://indian-supreme-court-judgments/adversarial",
                quote="Adversarial injected citation",
                authority_tier=AuthorityTier.LICENSED.value,
                verification_status="VERIFIED",
                timestamp=time.time(),
            ))

        invariant_violations = check_invariants(run, case)
        playbook_violations = check_playbook_assertions(run, case)

        if is_adversarial:
            # The adversarial case SHOULD produce an invariant violation
            licensed_verified_found = any("LICENSED" in v and "VERIFIED" in v
                                          for v in invariant_violations)
            if licensed_verified_found:
                # Remove it from violations — the invariant checker correctly caught it
                invariant_violations = [v for v in invariant_violations
                                        if not ("LICENSED" in v and "VERIFIED" in v)]
                adversarial_detected = True
            else:
                adversarial_detected = False
                invariant_violations.append(
                    "ADVERSARIAL: LICENSED→VERIFIED injection was NOT detected")

        all_violations = invariant_violations + playbook_violations
        passed = len(all_violations) == 0
        if is_adversarial:
            passed = passed and adversarial_detected

        if passed:
            total_pass += 1
        else:
            total_fail += 1

        results.append({
            "case_id": case["case_id"],
            "matter_id": case["matter_id"],
            "passed": passed,
            "workflow_status": run.status.value,
            "expected_workflow_status": case.get("expected_workflow_status"),
            "invariant_violations": invariant_violations,
            "playbook_violations": playbook_violations,
            "adversarial_detected": adversarial_detected if is_adversarial else None,
            "evidence_count": len(run.ledger.all_records),
            "stages_completed": len([
                s for s in run.stage_results.values()
                if s.status in (StageStatus.SUCCEEDED, StageStatus.PARTIAL,
                                StageStatus.NEEDS_HUMAN_REVIEW, StageStatus.SKIPPED)
            ]),
            "elapsed_ms": (run.finished_at - run.started_at) * 1000 if run.finished_at else 0,
        })

    finished = time.time()
    report = {
        "suite": "golden_contract_review",
        "workflow": "contract_review_v1",
        "total": len(results),
        "passed": total_pass,
        "failed": total_fail,
        "status": "GREEN" if total_fail == 0 else "RED",
        "elapsed_ms": (finished - started) * 1000,
        "cases": results,
    }
    return report


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    case_filter = None
    json_mode = "--json" in sys.argv
    live_mode = "--live" in sys.argv

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--case" and i < len(sys.argv) - 1:
            case_filter = sys.argv[i + 1]

    report = run_golden_suite(case_filter, live=live_mode)

    if json_mode:
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"  HARNESS: {report['suite']}")
        print(f"  Workflow: {report['workflow']}")
        print(f"{'='*60}")

        for c in report.get("cases", []):
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['case_id']}"
                  f" — workflow={c['workflow_status']}"
                  f" evidence={c['evidence_count']}"
                  f" stages={c['stages_completed']}")
            if c.get("adversarial_detected") is not None:
                print(f"         adversarial_detected={c['adversarial_detected']}")
            for v in c.get("invariant_violations", []):
                print(f"         ! invariant: {v}")
            for v in c.get("playbook_violations", []):
                print(f"         ! playbook: {v}")

        print(f"\n  {report['passed']}/{report['total']} passed — {report['status']}")
        print(f"  elapsed: {report['elapsed_ms']:.0f}ms")
        print(f"{'='*60}\n")
        # gate-compatible count line (must be last, grep picks tail -1)
        print(f"{report['passed']}/{report['total']} passed")

    if report.get("status") == "RED":
        sys.exit(1)


if __name__ == "__main__":
    main()
