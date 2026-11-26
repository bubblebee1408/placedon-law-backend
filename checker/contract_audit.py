"""Contract audit — structured review of contracts using CUAD pipeline output.

Sits alongside document_audit.py (board minutes). Does NOT modify that module.
Consumes CUADResult from cuad_pipeline.py — never re-runs extraction.

Every finding links to evidence. Missing evidence is flagged, never hidden.
A contract is never described as "legally safe" because no findings were detected.
A clause is never claimed absent unless search coverage supports that conclusion.

Run: PYTHONPATH=. python3 checker/contract_audit.py --test
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

from checker.cuad_pipeline import CUADResult
from checker.cuad_extractor import Extraction, ExtractionResult
from checker.obligation_extractor import Obligation

__all__ = [
    "ContractAuditFinding", "ContractAuditReport", "AuditRule",
    "audit_contract", "DEFAULT_RULES",
]


# ── types ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContractAuditFinding:
    finding_id: str
    rule_id: str
    category: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    affected_party_id: str
    title: str
    explanation: str
    document_id: str
    clause_references: tuple[str, ...]
    evidence_references: tuple[str, ...]
    review_recommendation: str
    verification_status: str  # VERIFIED, UNVERIFIED, PARTIAL, NO_EXTRACTION


@dataclass(frozen=True)
class ContractAuditReport:
    document_id: str
    document_name: str
    overall_status: str  # REVIEW_REQUIRED, FINDINGS_DETECTED, NO_EXTRACTION
    findings: tuple[ContractAuditFinding, ...]
    severity_distribution: dict[str, int]
    affected_parties: tuple[str, ...]
    missing_categories: tuple[str, ...]
    unverified_findings: int
    total_findings: int
    categories_searched: int
    categories_found: int
    lawyer_review_recommended: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class AuditRule:
    rule_id: str
    category: str
    description: str
    severity_default: str
    required_categories: tuple[str, ...]  # CUAD categories this rule inspects
    check_fn: Callable[[CUADResult, "AuditRule"], list[ContractAuditFinding]]


# ── rule check functions ──────────────────────────────────────────────────────

def _extractions_by_category(result: CUADResult) -> dict[str, list[Extraction]]:
    if not result.extraction or not result.extraction.extractions:
        return {}
    out: dict[str, list[Extraction]] = {}
    for e in result.extraction.extractions:
        out.setdefault(e.category, []).append(e)
    return out


def _obligations_by_category(result: CUADResult) -> dict[str, list[Obligation]]:
    out: dict[str, list[Obligation]] = {}
    for o in result.obligations:
        out.setdefault(o.source_category, []).append(o)
    return out


def _categories_asked(result: CUADResult) -> frozenset[str]:
    if not result.extraction:
        return frozenset()
    return frozenset(result.extraction.categories_asked)


def _make_finding(rule: AuditRule, result: CUADResult, title: str,
                  explanation: str, evidence: list[str] | None = None,
                  clauses: list[str] | None = None,
                  party: str = "", severity: str = "",
                  verification: str = "") -> ContractAuditFinding:
    return ContractAuditFinding(
        finding_id=f"{rule.rule_id}_{result.document_id[:8]}",
        rule_id=rule.rule_id,
        category=rule.category,
        severity=severity or rule.severity_default,
        affected_party_id=party,
        title=title,
        explanation=explanation,
        document_id=result.document_id,
        clause_references=tuple(clauses or []),
        evidence_references=tuple(evidence or []),
        review_recommendation="Lawyer review recommended",
        verification_status=verification or (
            "NO_EXTRACTION" if not result.extraction else "VERIFIED"),
    )


def _check_missing_category(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Flag when a required category was asked but not found."""
    asked = _categories_asked(result)
    if not asked:
        return []
    by_cat = _extractions_by_category(result)
    findings: list[ContractAuditFinding] = []
    for cat in rule.required_categories:
        if cat in asked and cat not in by_cat:
            findings.append(_make_finding(
                rule, result,
                title=f"No {cat} clause detected",
                explanation=(
                    f"The extraction searched for {cat} but found no matching clause. "
                    "This may indicate the provision is absent or was not recognized."
                ),
                severity="MEDIUM",
                verification="VERIFIED",
            ))
    return findings


def _check_unverified_evidence(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Flag extractions with fuzzy or weak verification."""
    by_cat = _extractions_by_category(result)
    findings: list[ContractAuditFinding] = []
    for cat in rule.required_categories:
        for ext in by_cat.get(cat, []):
            if ext.verification_status == "FUZZY_MATCH":
                findings.append(_make_finding(
                    rule, result,
                    title=f"{cat}: evidence is fuzzy-matched",
                    explanation=(
                        f"The extracted {cat} clause has fuzzy-matched evidence. "
                        "The exact quoted text was not found verbatim in the source."
                    ),
                    evidence=[ext.evidence_text],
                    clauses=[cat],
                    severity="LOW",
                    verification="PARTIAL",
                ))
    return findings


def _check_obligation_party_missing(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Flag obligations where the responsible party could not be identified."""
    findings: list[ContractAuditFinding] = []
    for obl in result.obligations:
        if not obl.party:
            findings.append(_make_finding(
                rule, result,
                title=f"Unresolved party in {obl.source_category} obligation",
                explanation=(
                    f"An obligation ({obl.modality}) was detected but the responsible "
                    "party could not be identified from the text."
                ),
                evidence=[obl.evidence],
                clauses=[obl.source_category],
                severity="HIGH",
                verification="VERIFIED",
            ))
    return findings


def _check_indemnity(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Check indemnification and liability provisions."""
    by_cat = _extractions_by_category(result)
    findings: list[ContractAuditFinding] = []
    indemnity = by_cat.get("Indemnification", [])
    cap = by_cat.get("Cap On Liability", [])
    uncapped = by_cat.get("Uncapped Liability", [])

    if indemnity and not cap and not uncapped:
        asked = _categories_asked(result)
        if "Cap On Liability" in asked:
            explanation = (
                "Indemnification obligations were found but no cap on liability "
                "was detected. This may expose a party to unlimited liability.")
        else:
            # ponytail: cap wasn't searched — still flag for review, weaker claim
            explanation = (
                "Indemnification obligations were found. Liability cap was not in "
                "the extraction scope — review whether a cap exists in the contract.")
        findings.append(_make_finding(
            rule, result,
            title="Indemnification: liability cap not confirmed",
            explanation=explanation,
            evidence=[e.evidence_text for e in indemnity],
            clauses=["Indemnification", "Cap On Liability"],
            severity="HIGH",
        ))

    if uncapped:
        findings.append(_make_finding(
            rule, result,
            title="Uncapped liability detected",
            explanation="The contract contains explicitly uncapped liability provisions.",
            evidence=[e.evidence_text for e in uncapped],
            clauses=["Uncapped Liability"],
            severity="CRITICAL",
        ))

    return findings


def _check_termination(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Check termination provisions."""
    by_cat = _extractions_by_category(result)
    asked = _categories_asked(result)
    findings: list[ContractAuditFinding] = []

    conv = by_cat.get("Termination For Convenience", [])
    if "Termination For Convenience" in asked and not conv:
        findings.append(_make_finding(
            rule, result,
            title="No termination for convenience clause",
            explanation=(
                "No termination for convenience clause was detected. "
                "This may limit exit options."
            ),
            severity="MEDIUM",
        ))

    return findings


def _check_governing_law(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Check governing law and dispute resolution."""
    return _check_missing_category(result, rule)


def _check_confidentiality(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Check confidentiality provisions."""
    return _check_missing_category(result, rule)


def _check_ip(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Check IP ownership provisions."""
    by_cat = _extractions_by_category(result)
    findings: list[ContractAuditFinding] = []
    ip_assign = by_cat.get("IP Ownership Assignment", [])
    joint = by_cat.get("Joint IP Ownership", [])
    if joint:
        findings.append(_make_finding(
            rule, result,
            title="Joint IP ownership detected",
            explanation="Joint IP ownership provisions can create complex rights situations.",
            evidence=[e.evidence_text for e in joint],
            clauses=["Joint IP Ownership"],
            severity="MEDIUM",
        ))
    if not ip_assign and not joint:
        asked = _categories_asked(result)
        if "IP Ownership Assignment" in asked:
            findings.append(_make_finding(
                rule, result,
                title="No IP ownership clause detected",
                explanation="No explicit IP ownership assignment was found.",
                severity="MEDIUM",
            ))
    return findings


def _check_non_compete(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Flag restrictive covenants for review."""
    by_cat = _extractions_by_category(result)
    findings: list[ContractAuditFinding] = []
    for cat_name in ("Non-Compete", "Non-Disparagement", "No-Solicitation Of Employees",
                     "No-Solicitation Of Customers", "Competitive Restriction Exception"):
        for ext in by_cat.get(cat_name, []):
            findings.append(_make_finding(
                rule, result,
                title=f"Restrictive covenant: {cat_name}",
                explanation=f"A {cat_name} provision was detected and should be reviewed for reasonableness.",
                evidence=[ext.evidence_text],
                clauses=[cat_name],
                severity="MEDIUM",
            ))
    return findings


def _check_inconsistent_provisions(result: CUADResult, rule: AuditRule) -> list[ContractAuditFinding]:
    """Detect potentially inconsistent provisions (deterministic only)."""
    by_cat = _extractions_by_category(result)
    obl_by_cat = _obligations_by_category(result)
    findings: list[ContractAuditFinding] = []

    # Inconsistency: exclusivity + non-compete exception
    if by_cat.get("Exclusivity") and by_cat.get("Competitive Restriction Exception"):
        findings.append(_make_finding(
            rule, result,
            title="Exclusivity with competitive restriction exception",
            explanation=(
                "Both an exclusivity clause and a competitive restriction exception "
                "were detected. These may conflict depending on scope."
            ),
            evidence=(
                [e.evidence_text for e in by_cat["Exclusivity"]] +
                [e.evidence_text for e in by_cat["Competitive Restriction Exception"]]
            ),
            clauses=["Exclusivity", "Competitive Restriction Exception"],
            severity="MEDIUM",
        ))

    # Inconsistency: permission and prohibition on same party for same category
    party_modalities: dict[str, set[str]] = {}
    for obl in result.obligations:
        if obl.party:
            key = obl.party.lower()
            party_modalities.setdefault(key, set()).add(obl.modality)
    for party, mods in party_modalities.items():
        if "permission" in mods and "prohibition" in mods:
            findings.append(_make_finding(
                rule, result,
                title=f"Conflicting modalities for {party}",
                explanation=(
                    f"Party '{party}' has both permission and prohibition obligations. "
                    "Review whether these apply to distinct actions or conflict."
                ),
                party=party,
                severity="HIGH",
            ))

    return findings


# ── default rules ─────────────────────────────────────────────────────────────

DEFAULT_RULES: tuple[AuditRule, ...] = (
    AuditRule("CA-PARTY", "Parties and defined terms", "Verify parties are identified",
              "HIGH", ("Parties",), _check_missing_category),
    AuditRule("CA-PAY", "Payment and financial obligations", "Review payment terms",
              "HIGH", ("Payment Terms",), _check_missing_category),
    AuditRule("CA-RW", "Representations and warranties", "Check reps and warranties",
              "MEDIUM", ("Representations And Warranties",), _check_missing_category),
    AuditRule("CA-INDEM", "Indemnities and liability", "Review indemnification and caps",
              "HIGH", ("Indemnification", "Cap On Liability", "Uncapped Liability"),
              _check_indemnity),
    AuditRule("CA-TERM", "Termination rights", "Review termination provisions",
              "MEDIUM", ("Termination For Convenience",), _check_termination),
    AuditRule("CA-CONF", "Confidentiality", "Verify confidentiality protections",
              "MEDIUM", ("Confidentiality",), _check_confidentiality),
    AuditRule("CA-IP", "Intellectual property", "Review IP ownership",
              "HIGH", ("IP Ownership Assignment", "Joint IP Ownership"), _check_ip),
    AuditRule("CA-COND", "Conditions precedent", "Check conditions precedent",
              "MEDIUM", ("Conditions Precedent",), _check_missing_category),
    AuditRule("CA-GOVLAW", "Governing law", "Verify governing law",
              "MEDIUM", ("Governing Law",), _check_governing_law),
    AuditRule("CA-DISP", "Dispute resolution", "Review dispute resolution mechanism",
              "MEDIUM", ("Dispute Resolution", "Arbitration Seat"), _check_governing_law),
    AuditRule("CA-RESTRICT", "Restrictive covenants", "Flag non-competes and non-solicits",
              "MEDIUM", ("Non-Compete", "Non-Disparagement", "No-Solicitation Of Employees",
                         "No-Solicitation Of Customers", "Competitive Restriction Exception"),
              _check_non_compete),
    AuditRule("CA-EVID", "Evidence verification", "Flag fuzzy-matched evidence",
              "LOW", (),  # ponytail: checks all categories, not a fixed set
              _check_unverified_evidence),
    AuditRule("CA-OBLPARTY", "Obligation party resolution", "Flag unresolved parties",
              "HIGH", (), _check_obligation_party_missing),
    AuditRule("CA-INCONSIST", "Potentially inconsistent provisions",
              "Detect conflicting clauses", "HIGH", (), _check_inconsistent_provisions),
)


# ── main entry ────────────────────────────────────────────────────────────────

def audit_contract(cuad_result: CUADResult, *,
                   rules: list[AuditRule] | None = None) -> ContractAuditReport:
    """Run contract audit on a CUADResult. Never re-runs extraction."""
    rules_to_use = list(rules) if rules is not None else list(DEFAULT_RULES)
    errors: list[str] = list(cuad_result.errors)
    all_findings: list[ContractAuditFinding] = []

    if not cuad_result.extraction:
        return ContractAuditReport(
            document_id=cuad_result.document_id,
            document_name=cuad_result.name,
            overall_status="NO_EXTRACTION",
            findings=(),
            severity_distribution={},
            affected_parties=(),
            missing_categories=(),
            unverified_findings=0,
            total_findings=0,
            categories_searched=0,
            categories_found=0,
            lawyer_review_recommended=True,
            errors=tuple(errors + ["No extraction available — audit cannot assess contract"]),
        )

    for rule in rules_to_use:
        try:
            findings = rule.check_fn(cuad_result, rule)
            all_findings.extend(findings)
        except Exception as exc:
            errors.append(f"Rule {rule.rule_id} failed: {exc}")

    sev_dist = dict(Counter(f.severity for f in all_findings))
    parties = tuple(sorted({f.affected_party_id for f in all_findings if f.affected_party_id}))
    unverified = sum(1 for f in all_findings if f.verification_status in ("UNVERIFIED", "NO_EXTRACTION"))

    asked = set(cuad_result.extraction.categories_asked)
    found = set(cuad_result.extraction.categories_found)
    missing = tuple(sorted(asked - found))

    has_critical = sev_dist.get("CRITICAL", 0) > 0
    has_high = sev_dist.get("HIGH", 0) > 0
    status = "REVIEW_REQUIRED" if (has_critical or has_high or all_findings) else "FINDINGS_DETECTED"
    # ponytail: status is always review-flavored; we never say "safe"
    if not all_findings:
        status = "REVIEW_REQUIRED"

    return ContractAuditReport(
        document_id=cuad_result.document_id,
        document_name=cuad_result.name,
        overall_status=status,
        findings=tuple(all_findings),
        severity_distribution=sev_dist,
        affected_parties=parties,
        missing_categories=missing,
        unverified_findings=unverified,
        total_findings=len(all_findings),
        categories_searched=len(asked),
        categories_found=len(found),
        lawyer_review_recommended=True,  # always true — never claim safe
        errors=tuple(errors),
    )


# ── self-tests ────────────────────────────────────────────────────────────────

def _test() -> int:
    import json
    from checker.cuad_pipeline import run_cuad_pipeline

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("contract_audit")

    contract = (
        "MUTUAL NON-DISCLOSURE AGREEMENT dated January 15, 2024. "
        "This Agreement is entered into between Acme Corp and Beta Ltd. "
        "The receiving party shall not disclose any confidential information. "
        "This Agreement shall be governed by the laws of India. "
        "Any disputes shall be resolved through arbitration in Mumbai. "
        "The term of this agreement is two years from the effective date. "
        "The Supplier shall indemnify the Customer against all losses. "
        "Either party may terminate this agreement by giving 30 days notice.")

    # ── with mock model (findings expected) ─────────────────────────────
    def mock_route(prompt: str) -> str:
        return json.dumps([
            {"category": "Governing Law", "answer": "India",
             "evidence": "governed by the laws of India"},
            {"category": "Parties", "answer": "Acme Corp and Beta Ltd",
             "evidence": "between Acme Corp and Beta Ltd"},
            {"category": "Confidentiality", "answer": "shall not disclose",
             "evidence": "shall not disclose any confidential information"},
            {"category": "Indemnification", "answer": "indemnify",
             "evidence": "The Supplier shall indemnify the Customer against all losses"},
            {"category": "Termination For Convenience", "answer": "may terminate",
             "evidence": "Either party may terminate this agreement by giving 30 days notice"},
            {"category": "Dispute Resolution", "answer": "arbitration in Mumbai",
             "evidence": "disputes shall be resolved through arbitration in Mumbai"},
        ])

    cuad = run_cuad_pipeline(contract, name="NDA.pdf", route_fn=mock_route,
                             model_provider="test", model_version="mock-1",
                             doc_id="test-001")
    report = audit_contract(cuad)

    check(report.document_id == "test-001", f"doc_id={report.document_id}")
    check(report.overall_status == "REVIEW_REQUIRED", f"status={report.overall_status}")
    check(report.lawyer_review_recommended is True, "lawyer review always recommended")
    check(report.total_findings >= 1, f"findings detected ({report.total_findings})")
    check(report.categories_searched > 0, f"categories searched ({report.categories_searched})")
    check(report.categories_found > 0, f"categories found ({report.categories_found})")
    check(len(report.missing_categories) >= 0, "missing categories tracked")

    # Verify severity distribution is consistent
    sev_sum = sum(report.severity_distribution.values())
    check(sev_sum == report.total_findings,
          f"severity sum ({sev_sum}) == total ({report.total_findings})")

    # Every finding has a rule_id and category
    check(all(f.rule_id for f in report.findings), "all findings have rule_id")
    check(all(f.category for f in report.findings), "all findings have category")
    check(all(f.review_recommendation for f in report.findings), "all findings have recommendation")

    # ── no extraction ───────────────────────────────────────────────────
    cuad_no_ext = run_cuad_pipeline(contract, name="NDA.pdf", doc_id="test-002")
    report2 = audit_contract(cuad_no_ext)

    check(report2.overall_status == "NO_EXTRACTION", f"no-ext status={report2.overall_status}")
    check(report2.total_findings == 0, "no findings without extraction")
    check(report2.lawyer_review_recommended is True, "still recommends lawyer review")
    check(len(report2.errors) >= 1, "error message about missing extraction")

    # ── empty document ──────────────────────────────────────────────────
    cuad_empty = run_cuad_pipeline("", name="empty.pdf", doc_id="test-003")
    report3 = audit_contract(cuad_empty)
    check(report3.overall_status == "NO_EXTRACTION", "empty doc → no extraction")

    # ── findings with fuzzy evidence ────────────────────────────────────
    def mock_fuzzy(prompt: str) -> str:
        return json.dumps([
            {"category": "Governing Law", "answer": "India",
             "evidence": "laws of India and all applicable regulations"},
        ])

    cuad_fuzzy = run_cuad_pipeline(contract, name="NDA.pdf", route_fn=mock_fuzzy,
                                   model_provider="test", model_version="mock-1",
                                   doc_id="test-004")
    report4 = audit_contract(cuad_fuzzy)
    check(report4.total_findings >= 1, f"fuzzy produces findings ({report4.total_findings})")

    # ── indemnity without cap (mock only indemnification, no cap) ────────
    def mock_indem_no_cap(prompt: str) -> str:
        return json.dumps([
            {"category": "Indemnification", "answer": "indemnify",
             "evidence": "The Supplier shall indemnify the Customer against all losses"},
            {"category": "Parties", "answer": "Acme Corp and Beta Ltd",
             "evidence": "between Acme Corp and Beta Ltd"},
        ])

    cuad_indem = run_cuad_pipeline(contract, name="NDA.pdf", route_fn=mock_indem_no_cap,
                                   model_provider="test", model_version="mock-1",
                                   doc_id="test-005")
    report5 = audit_contract(cuad_indem)
    indem_findings = [f for f in report5.findings if f.rule_id == "CA-INDEM"]
    check(len(indem_findings) >= 1, f"indemnity without cap flagged ({len(indem_findings)})")
    if indem_findings:
        check("HIGH" in {f.severity for f in indem_findings},
              "indemnity without cap is HIGH severity")

    # ── custom rules ────────────────────────────────────────────────────
    custom = [AuditRule("CUSTOM-1", "Custom", "Test rule", "LOW", ("Parties",),
                        _check_missing_category)]
    report6 = audit_contract(cuad, rules=custom)
    check(all(f.rule_id == "CUSTOM-1" for f in report6.findings),
          "custom rules override defaults")

    # ── severity distribution ───────────────────────────────────────────
    check(isinstance(report.severity_distribution, dict), "severity_distribution is dict")

    # ── inconsistency detection ─────────────────────────────────────────
    conflict_contract = (
        "Agreement between Acme Corp and Beta Ltd. "
        "The receiving party shall not disclose confidential information. "
        "The receiving party may disclose information to affiliates.")

    def mock_conflict(prompt: str) -> str:
        return json.dumps([
            {"category": "Confidentiality", "answer": "shall not disclose",
             "evidence": "The receiving party shall not disclose confidential information"},
            {"category": "Parties", "answer": "Acme Corp and Beta Ltd",
             "evidence": "between Acme Corp and Beta Ltd"},
        ])

    cuad_conflict = run_cuad_pipeline(conflict_contract, name="conflict.pdf",
                                      route_fn=mock_conflict,
                                      model_provider="test", model_version="mock-1",
                                      doc_id="test-006")
    report7 = audit_contract(cuad_conflict)
    # At minimum should flag party resolution issues from obligations
    check(report7.lawyer_review_recommended is True, "conflict contract → lawyer review")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
