"""End-to-end verification audit for one document.

Orchestrates existing modules — no new algorithms:
  doc_classifier  → what kind of document is this?
  evidence_extractor → extract dates, counts, facts
  ss/defects      → secretarial standards checks (deterministic)
  obligations     → obligation register evaluation
  fusion          → statutory text retrieval for each obligation

Returns an AuditReport: a frozen record of everything found, with provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from checker import doc_classifier
from checker import evidence_extractor as ee
from checker import obligations as ob
from checker.company_profile import CompanyProfile
from checker.ss import defects as ss

AuditVerdict = Literal[
    "VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED",
    "INAPPLICABLE", "POTENTIAL_ISSUE", "STALENESS_WARNING",
]


@dataclass(frozen=True)
class ObligationResult:
    obligation_id: str
    duty: str
    provision: str
    state: str
    basis: str
    missing_facts: tuple[str, ...]
    needs_attention: bool


@dataclass(frozen=True)
class AuditReport:
    """The full audit output for one document."""
    # ── classification ──
    doc_class: str
    doc_class_reason: str
    ss_doc_type: str  # ss/defects.DocType

    # ── evidence extracted ──
    extraction: ee.ExtractionResult

    # ── secretarial standards ──
    ss_findings: tuple[ss.Finding, ...]
    ss_penalty_exposure: int

    # ── obligations ──
    obligation_rows: tuple[ObligationResult, ...]
    obligations_satisfied: int
    obligations_not_satisfied: int
    obligations_undetermined: int
    obligations_not_applicable: int

    # ── verdict ──
    verdict: AuditVerdict
    verdict_basis: str

    # ── metadata ──
    as_of: date
    document_text_length: int


# Which obligation IDs are relevant to board minutes. The register has 21;
# only some can be evaluated from a board minutes document.
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_ENTERED_ON = re.compile(
    r"entered\s+on\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\w+),?\s+(\d{4})", re.I)
_HELD_ON = re.compile(
    r"held\s+on\s+(?:\w+day,?\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?:day\s+of\s+)?(\w+),?\s+(\d{4})", re.I)


def _parse_date_groups(m: re.Match) -> date | None:
    day, mon_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
    return date(year, _MONTHS[mon_str], day) if mon_str in _MONTHS else None


def _parse_entry_date(text: str) -> date | None:
    m = _ENTERED_ON.search(text)
    return _parse_date_groups(m) if m else None


def _parse_meeting_date(text: str) -> date | None:
    m = _HELD_ON.search(text)
    return _parse_date_groups(m) if m else None


_BOARD_MINUTES_OBLIGATIONS = frozenset({
    "CA13-S173-BOARD",          # board meeting count + spacing
    "CA13-S149-BOARD-SIZE",     # minimum directors
    "CA13-S149-3-RESIDENT",     # resident director
    "CA13-S177-AUDIT-CTTE",     # audit committee (presence noted in minutes)
    "CA13-S184-DIRECTOR-INTEREST",  # s.184 disclosure (mentioned in minutes)
    "CA13-S96-AGM",             # AGM (if referenced)
})


def audit(text: str,
          profile: CompanyProfile,
          as_of: date | None = None,
          page_boundaries: tuple[int, ...] | None = None,
          ) -> AuditReport:
    """Run the full verification audit pipeline on document text.

    `profile` is the company this document belongs to.
    `as_of` is the evaluation date (defaults to today).
    """
    as_of = as_of or date.today()

    # 1. Classify
    doc_class, class_reason = doc_classifier.classify(text)
    ss_doc_type = ss.classify(text)

    # 2. Extract evidence
    extraction = ee.extract(text, as_of=as_of)

    # 3. SS defect scan (only for minutes)
    ss_findings: list[ss.Finding] = []
    ss_exposure = 0
    if ss_doc_type == "minutes":
        meeting_kind: ss.MeetingKind = "board"
        if "annual general meeting" in text.lower() or "AGM" in text:
            meeting_kind = "general"
        mtg_date = _parse_meeting_date(text) or (
            extraction.board_meeting_dates_found[0]
            if extraction.board_meeting_dates_found else None)
        minutes = ss.Minutes(
            text=text,
            kind=meeting_kind,
            meeting_date=mtg_date,
            entry_date=_parse_entry_date(text),
            doc_type=ss_doc_type,
            _page_boundaries=page_boundaries,
        )
        ss_findings = ss.scan(minutes)
        ss_exposure = ss.exposure(ss_findings, officers=1)

    # 4. Obligation register
    rows = ob.build(profile, evidence=extraction.evidence)
    ob_results: list[ObligationResult] = []
    for row in rows:
        # For board minutes, only report obligations relevant to this doc type
        if row.obligation_id not in _BOARD_MINUTES_OBLIGATIONS:
            continue
        ob_results.append(ObligationResult(
            obligation_id=row.obligation_id,
            duty=row.duty,
            provision=row.provision,
            state=row.state,
            basis=row.basis,
            missing_facts=row.missing_facts,
            needs_attention=row.needs_attention,
        ))

    sat = sum(1 for r in ob_results if r.state == ob.APPLIES_SATISFIED)
    not_sat = sum(1 for r in ob_results if r.state == ob.APPLIES_NOT_SATISFIED)
    undet = sum(1 for r in ob_results
                if r.state in (ob.APPLIES_UNDETERMINED, ob.CANNOT_DETERMINE, ob.IN_PROGRESS))
    na = sum(1 for r in ob_results if r.state == ob.DOES_NOT_APPLY)

    # 5. Verdict
    verdict, verdict_basis = _decide_verdict(
        doc_class=doc_class,
        ss_findings=ss_findings,
        ob_results=ob_results,
        sat=sat, not_sat=not_sat, undet=undet,
    )

    return AuditReport(
        doc_class=doc_class,
        doc_class_reason=class_reason,
        ss_doc_type=ss_doc_type,
        extraction=extraction,
        ss_findings=tuple(ss_findings),
        ss_penalty_exposure=ss_exposure,
        obligation_rows=tuple(ob_results),
        obligations_satisfied=sat,
        obligations_not_satisfied=not_sat,
        obligations_undetermined=undet,
        obligations_not_applicable=na,
        verdict=verdict,
        verdict_basis=verdict_basis,
        as_of=as_of,
        document_text_length=len(text),
    )


def _decide_verdict(
    doc_class: str,
    ss_findings: list[ss.Finding],
    ob_results: list[ObligationResult],
    sat: int,
    not_sat: int,
    undet: int,
) -> tuple[AuditVerdict, str]:
    """Derive the overall verdict from the components."""
    if doc_class == "unknown":
        return "UNVERIFIED", "document type could not be classified"

    defects = [f for f in ss_findings if f.status == "DEFECT"]
    if not_sat > 0:
        return ("POTENTIAL_ISSUE",
                f"{not_sat} obligation(s) not satisfied"
                + (f", {len(defects)} SS defect(s)" if defects else ""))

    if defects:
        return "POTENTIAL_ISSUE", f"{len(defects)} secretarial standards defect(s)"

    if sat > 0 and undet == 0:
        return "VERIFIED", f"all {sat} applicable obligation(s) satisfied, no SS defects"

    if sat > 0 and undet > 0:
        return ("PARTIALLY_VERIFIED",
                f"{sat} satisfied, {undet} undetermined — insufficient evidence for full verification")

    if undet > 0 and sat == 0:
        return "UNVERIFIED", f"{undet} obligation(s) undetermined, none satisfied"

    return "UNVERIFIED", "no obligations could be evaluated"


# ── self-test ───────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    # Minimal board minutes text
    text = (
        "Minutes of the meeting of the Board of Directors held on 15th January, 2024.\n"
        "PRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\n4. Mr. D\n\n"
        "IN ATTENDANCE\nX Secretary\n"
        "The quorum was present.\n"
        "Minutes of the previous Board meeting held on 10th October, 2023 were noted.\n"
        "Section 173 of the Companies Act, 2013.\n"
    )
    profile = CompanyProfile(
        company_class="private",
        incorporation_date=date(2020, 1, 1),
        as_of=date(2024, 2, 1),
    )
    r = audit(text, profile, as_of=date(2024, 2, 1))

    check(r.doc_class == "board_minutes", f"doc_class={r.doc_class}")
    check(len(r.doc_class_reason) > 0, "classification has a reason")
    check(r.ss_doc_type == "minutes", f"ss_doc_type={r.ss_doc_type}")
    check(r.extraction.evidence.board_meetings is not None, "board meetings extracted")
    check(len(r.obligation_rows) > 0, f"obligation rows: {len(r.obligation_rows)}")
    check(r.verdict in ("VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "POTENTIAL_ISSUE"),
          f"verdict={r.verdict}")
    check(len(r.verdict_basis) > 0, "verdict has basis")
    check(r.as_of == date(2024, 2, 1), "as_of preserved")
    check(r.document_text_length > 0, "text length recorded")

    # Unknown document
    r2 = audit("Random text with no legal content.", profile, as_of=date(2024, 1, 1))
    check(r2.verdict == "UNVERIFIED", f"unknown doc verdict={r2.verdict}")

    # entry_date parsing
    check(_parse_entry_date("Entered on 10th February, 2025") == date(2025, 2, 10),
          "parse entry date")
    check(_parse_entry_date("No entry date here") is None, "no entry date returns None")

    # T1.4b: late entry date
    late_text = (
        "Minutes of the 5th Board Meeting held on 15th January, 2025.\n"
        "PRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\n"
        "The quorum was present.\n"
        "The Meeting commenced at 3:00 P.M.\n"
        "The Meeting concluded at 4:00 P.M.\n"
        "Signed at Delhi\n"
        "Entered on 28th March, 2025\n"
    )
    r3 = audit(late_text, profile, as_of=date(2025, 4, 1))
    t14b = [f for f in r3.ss_findings if f.check_id == "T1.4b"]
    check(len(t14b) == 1 and t14b[0].status == "DEFECT",
          f"T1.4b fires on 72-day lag: {t14b[0].status if t14b else 'missing'}")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
