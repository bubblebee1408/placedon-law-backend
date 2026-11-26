"""Obligation extraction — LexDeMod-style per-party deontic modality detection.

Adapted from: Sancheti et al. (2022), "Agent-Specific Deontic Modality Detection
in Legal Language", EMNLP 2022. DOI: 10.18653/v1/2022.emnlp-main.795

Full LexDeMod taxonomy (7 labels, multi-label per sentence):
  OBLIGATION, PROHIBITION, PERMISSION, ENTITLEMENT,
  NO_OBLIGATION, NO_ENTITLEMENT, NONE

Legacy API (`extract_obligations`) returns 3-class for backward compat.
New API (`extract_deontic`) returns full 7-class DeonticExtraction.

This is deterministic Python — no model calls. It operates on the evidence text
already extracted and verified by cuad_extractor.

Run: PYTHONPATH=. python3 checker/obligation_extractor.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Obligation", "extract_obligations",
    "DeonticExtraction", "PartyRef", "extract_deontic",
    "MODALITY_LABELS",
]

MODALITY_LABELS = frozenset({
    "OBLIGATION", "PROHIBITION", "PERMISSION", "ENTITLEMENT",
    "NO_OBLIGATION", "NO_ENTITLEMENT", "NONE",
})

SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class Obligation:
    party: str
    action: str
    modality: str  # "obligation", "prohibition", "permission"
    object_: str
    condition: str
    deadline: str
    exception: str
    evidence: str
    source_category: str


@dataclass(frozen=True)
class PartyRef:
    canonical: str
    mention: str
    alias: str
    party_id: str
    resolution_status: str  # "resolved" | "unresolved"


@dataclass(frozen=True)
class DeonticExtraction:
    document_id: str
    clause_id: str | None
    party_id: str | None
    party_name: str | None
    party_resolution_status: str
    modality_labels: tuple[str, ...]
    trigger_text: str
    trigger_start: int | None
    trigger_end: int | None
    action: str | None
    object_: str | None
    condition: str | None
    deadline_text: str | None
    deadline_normalized: str | None
    exception_text: str | None
    negation_scope: str | None
    evidence_text: str
    evidence_start: int
    evidence_end: int
    page_number: int | None
    section_reference: str | None
    verification_status: str
    model_id: str
    prompt_version: str
    schema_version: str


# ── trigger patterns ───────────────────────────────────────────────────────────
# Order matters: negated forms checked before base forms.

# Negated deontic — must be checked BEFORE prohibition and obligation
_NO_OBLIGATION_TRIGGERS = (
    re.compile(r"\bshall not be (?:required|obligated|obliged) to\b", re.I),
    re.compile(r"\bis not (?:required|obligated|obliged) to\b", re.I),
    re.compile(r"\bneed not\b", re.I),
    re.compile(r"\bshall have no obligation to\b", re.I),
)

_NO_ENTITLEMENT_TRIGGERS = (
    re.compile(r"\bis not entitled to\b", re.I),
    re.compile(r"\bshall not be entitled to\b", re.I),
    re.compile(r"\bhas no right to\b", re.I),
    re.compile(r"\bshall have no right to\b", re.I),
)

_ENTITLEMENT_TRIGGERS = (
    re.compile(r"\bis entitled to\b", re.I),
    re.compile(r"\bshall be entitled to\b", re.I),
    re.compile(r"\bhas the right to\b", re.I),
    re.compile(r"\breserves the right\b", re.I),
)

_OBLIGATION_TRIGGERS = (
    re.compile(r"\bshall\b", re.I),
    re.compile(r"\bmust\b", re.I),
    re.compile(r"\bis required to\b", re.I),
    re.compile(r"\bagrees to\b", re.I),
    re.compile(r"\bundertakes to\b", re.I),
    re.compile(r"\bwill\b(?!\s+not\b)", re.I),
)

_PROHIBITION_TRIGGERS = (
    re.compile(r"\bshall not\b", re.I),
    re.compile(r"\bmust not\b", re.I),
    re.compile(r"\bmay not\b", re.I),
    re.compile(r"\bwill not\b", re.I),
    re.compile(r"\bis prohibited from\b", re.I),
    re.compile(r"\bshall in no (event|circumstance)\b", re.I),
)

_PERMISSION_TRIGGERS = (
    re.compile(r"\bmay\b(?!\s+not\b)", re.I),
)

# ── party extraction ───────────────────────────────────────────────────────────

_PARTY_PATTERN = re.compile(
    r"\b((?:the\s+)?(?:buyer|seller|licensor|licensee|supplier|customer|employer|"
    r"employee|landlord|tenant|borrower|lender|company|consultant|contractor|"
    r"service provider|receiving party|disclosing party|indemnifying party|"
    r"indemnified party|party|parties|either party|each party|both parties|"
    r"[A-Z][a-z]+ (?:Corp|Ltd|Inc|LLP|LLC|Limited|Private|Pvt)))\b",
    re.I,
)

_DEADLINE_PATTERN = re.compile(
    r"\b(within|before|no later than|by|after)\s+"
    r"((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|sixty|ninety)"
    r"\s*(?:business\s+|calendar\s+|working\s+)?(?:days?|months?|years?|weeks?)"
    r"(?:\s+(?:of|from|after)\s+[\w\s]+)?)",
    re.I,
)

_CONDITION_PATTERN = re.compile(
    r"\b(?:provided that|subject to|on condition that|if|unless|in the event)\s+(.{10,80})\b",
    re.I,
)

_EXCEPTION_PATTERN = re.compile(
    r"\b(?:except|other than|excluding|save for|notwithstanding)\s+(.{5,80})\b",
    re.I,
)


def _classify_modalities(sentence: str) -> list[str]:
    """Full 7-class LexDeMod multi-label classification. Order: most specific first."""
    labels: list[str] = []

    # Negated deontics — check before base forms
    for pat in _NO_OBLIGATION_TRIGGERS:
        if pat.search(sentence):
            labels.append("NO_OBLIGATION")
            break
    for pat in _NO_ENTITLEMENT_TRIGGERS:
        if pat.search(sentence):
            labels.append("NO_ENTITLEMENT")
            break

    if labels:
        return labels  # negated form found — don't also match base form

    # Base forms — prohibition before obligation ("shall not" before "shall")
    for pat in _ENTITLEMENT_TRIGGERS:
        if pat.search(sentence):
            labels.append("ENTITLEMENT")
            break
    for pat in _PROHIBITION_TRIGGERS:
        if pat.search(sentence):
            labels.append("PROHIBITION")
            break
    for pat in _PERMISSION_TRIGGERS:
        if pat.search(sentence):
            labels.append("PERMISSION")
            break
    for pat in _OBLIGATION_TRIGGERS:
        if not any(l in ("PROHIBITION", "ENTITLEMENT") for l in labels):
            if pat.search(sentence):
                labels.append("OBLIGATION")
                break

    return labels


# ponytail: maps 7-class → legacy 3-class for backward compat
_LEGACY_MAP = {
    "OBLIGATION": "obligation",
    "PROHIBITION": "prohibition",
    "PERMISSION": "permission",
    "ENTITLEMENT": "permission",  # closest legacy equivalent
    "NO_OBLIGATION": "",  # no legacy equivalent — skip
    "NO_ENTITLEMENT": "",
}


def _classify_modality(sentence: str) -> str:
    """Legacy 3-class classification — backward compatible."""
    labels = _classify_modalities(sentence)
    if not labels:
        return ""
    return _LEGACY_MAP.get(labels[0], "")


def _extract_party(sentence: str) -> str:
    m = _PARTY_PATTERN.search(sentence)
    return m.group(1).strip() if m else ""


def _extract_action(sentence: str, modality_trigger_end: int) -> str:
    # The action is typically the verb phrase after the trigger.
    rest = sentence[modality_trigger_end:].strip()
    # Take up to the first period, comma-clause, or 80 chars.
    end = min(len(rest), 80)
    for delim in (".", ";", ", provided", ", subject", ", except", ", unless"):
        idx = rest.find(delim)
        if 0 < idx < end:
            end = idx
    return rest[:end].strip()


def _extract_deadline(sentence: str) -> str:
    m = _DEADLINE_PATTERN.search(sentence)
    return m.group(0).strip() if m else ""


def _extract_object(sentence: str) -> str:
    return ""  # ponytail: placeholder, populated from extraction answer


def _extract_condition(sentence: str) -> str:
    m = _CONDITION_PATTERN.search(sentence)
    return m.group(0).strip() if m else ""


def _extract_exception(sentence: str) -> str:
    m = _EXCEPTION_PATTERN.search(sentence)
    return m.group(0).strip() if m else ""


def _find_trigger_end(sentence: str) -> int:
    """Find the end position of the modality trigger in the sentence."""
    for pat_list in (_PROHIBITION_TRIGGERS, _PERMISSION_TRIGGERS, _OBLIGATION_TRIGGERS):
        for pat in pat_list:
            m = pat.search(sentence)
            if m:
                return m.end()
    return 0


# ── negation scope ────────────────────────────────────────────────────────────

_NEGATION_SCOPE_PATTERN = re.compile(
    r"\b((?:shall |must |is |are |has |have )?"
    r"(?:not |no |never )"
    r"(?:be )?(?:required|obligated|obliged|entitled|permitted|allowed)"
    r"(?:\s+to)?)\b",
    re.I,
)


def _detect_negation_scope(sentence: str) -> str:
    m = _NEGATION_SCOPE_PATTERN.search(sentence)
    return m.group(0).strip() if m else ""


# ── trigger location ─────────────────────────────────────────────────────────

def _find_trigger_match(sentence: str) -> tuple[str, int, int]:
    """Find the first matching trigger and return (text, start, end)."""
    all_trigger_groups = (
        _NO_OBLIGATION_TRIGGERS, _NO_ENTITLEMENT_TRIGGERS,
        _ENTITLEMENT_TRIGGERS, _PROHIBITION_TRIGGERS,
        _PERMISSION_TRIGGERS, _OBLIGATION_TRIGGERS,
    )
    best = None
    for group in all_trigger_groups:
        for pat in group:
            m = pat.search(sentence)
            if m and (best is None or m.start() < best.start()):
                best = m
    if best:
        return best.group(0), best.start(), best.end()
    return "", 0, 0


# ── party resolution ─────────────────────────────────────────────────────────

def _resolve_party(mention: str, known_parties: list[str] | None) -> PartyRef:
    """Resolve a mention to a canonical party from known_parties."""
    if not mention:
        return PartyRef("", "", "", "", "unresolved")
    mention_lower = mention.lower().lstrip("the ").strip()
    if known_parties:
        for i, kp in enumerate(known_parties):
            if mention_lower in kp.lower() or kp.lower() in mention_lower:
                return PartyRef(
                    canonical=kp, mention=mention, alias=mention,
                    party_id=f"party_{i + 1}", resolution_status="resolved",
                )
    return PartyRef(
        canonical=mention, mention=mention, alias=mention,
        party_id="", resolution_status="unresolved",
    )


# ── full LexDeMod extraction ─────────────────────────────────────────────────

def extract_deontic(
    extractions: list[dict],
    *,
    known_parties: list[str] | None = None,
    document_id: str = "",
    model_id: str = "",
    prompt_version: str = "",
) -> list[DeonticExtraction]:
    """Extract full 7-class LexDeMod deontic modalities from CUAD evidence."""
    results: list[DeonticExtraction] = []

    for ext in extractions:
        evidence = ext.get("evidence", "")
        category = ext.get("category", "")
        verification = ext.get("status", "")
        if not evidence:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", evidence)
        offset = 0
        for sent in sentences:
            labels = _classify_modalities(sent)
            if not labels:
                offset += len(sent) + 1
                continue

            party_mention = _extract_party(sent)
            party_ref = _resolve_party(party_mention, known_parties)
            trigger_text, trigger_start, trigger_end = _find_trigger_match(sent)
            action = _extract_action(sent, trigger_end)
            deadline = _extract_deadline(sent)
            condition = _extract_condition(sent)
            exception = _extract_exception(sent)
            negation = _detect_negation_scope(sent)

            results.append(DeonticExtraction(
                document_id=document_id,
                clause_id=category or None,
                party_id=party_ref.party_id or None,
                party_name=party_ref.canonical or None,
                party_resolution_status=party_ref.resolution_status,
                modality_labels=tuple(labels),
                trigger_text=trigger_text,
                trigger_start=trigger_start,
                trigger_end=trigger_end,
                action=action or None,
                object_=ext.get("answer") or None,
                condition=condition or None,
                deadline_text=deadline or None,
                deadline_normalized=None,  # ponytail: needs calendar context for normalization
                exception_text=exception or None,
                negation_scope=negation or None,
                evidence_text=sent.strip(),
                evidence_start=offset,
                evidence_end=offset + len(sent),
                page_number=None,
                section_reference=None,
                verification_status=verification,
                model_id=model_id,
                prompt_version=prompt_version,
                schema_version=SCHEMA_VERSION,
            ))
            offset += len(sent) + 1

    return results


def extract_obligations(extractions: list[dict],
                        *, known_parties: list[str] | None = None) -> list[Obligation]:
    """Extract obligations from verified CUAD extraction dicts."""
    obligations: list[Obligation] = []

    for ext in extractions:
        evidence = ext.get("evidence", "")
        category = ext.get("category", "")
        if not evidence:
            continue

        # Split into sentences.
        sentences = re.split(r"(?<=[.!?])\s+", evidence)
        for sent in sentences:
            modality = _classify_modality(sent)
            if not modality:
                continue

            party = _extract_party(sent)
            trigger_end = _find_trigger_end(sent)
            action = _extract_action(sent, trigger_end)
            deadline = _extract_deadline(sent)
            condition = _extract_condition(sent)
            exception = _extract_exception(sent)

            obligations.append(Obligation(
                party=party,
                action=action,
                modality=modality,
                object_=ext.get("answer", ""),
                condition=condition,
                deadline=deadline,
                exception=exception,
                evidence=sent.strip(),
                source_category=category,
            ))

    return obligations


# ── self-tests ─────────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("obligation_extractor")

    # ── modality classification ──────────────────────────────────────────
    check(_classify_modality("The Buyer shall pay the purchase consideration") == "obligation",
          "shall → obligation")
    check(_classify_modality("The Supplier shall not disclose") == "prohibition",
          "shall not → prohibition")
    check(_classify_modality("Either party may terminate this agreement") == "permission",
          "may → permission")
    check(_classify_modality("The agreement is dated January 2024") == "",
          "no trigger → empty")
    check(_classify_modality("The company must not compete") == "prohibition",
          "must not → prohibition")
    check(_classify_modality("The licensee is entitled to use the software") == "permission",
          "is entitled to → permission")

    # ── party extraction ─────────────────────────────────────────────────
    check(_extract_party("The Buyer shall pay").lower() == "the buyer",
          f"'the Buyer' extracted ({_extract_party('The Buyer shall pay')})")
    check(_extract_party("Acme Corp shall indemnify") == "Acme Corp",
          f"'Acme Corp' extracted ({_extract_party('Acme Corp shall indemnify')})")
    check(_extract_party("the receiving party shall not disclose") == "the receiving party",
          f"receiving party ({_extract_party('the receiving party shall not disclose')})")

    # ── deadline extraction ──────────────────────────────────────────────
    check("ten Business Days" in _extract_deadline("within ten Business Days of closing"),
          f"deadline extracted ({_extract_deadline('within ten Business Days of closing')})")
    check(_extract_deadline("The agreement is effective.") == "",
          "no deadline → empty")

    # ── full extraction from CUAD results ────────────────────────────────
    mock_extractions = [
        {
            "category": "Indemnification",
            "answer": "indemnify",
            "evidence": "The Supplier shall indemnify the Customer against all losses.",
            "status": "VERIFIED",
        },
        {
            "category": "Confidentiality",
            "answer": "not disclose",
            "evidence": "The receiving party shall not disclose any confidential information to third parties.",
            "status": "VERIFIED",
        },
        {
            "category": "Termination For Convenience",
            "answer": "may terminate",
            "evidence": "Either party may terminate this agreement by giving 30 days written notice.",
            "status": "VERIFIED",
        },
        {
            "category": "Payment Terms",
            "answer": "pay",
            "evidence": "Buyer shall pay the purchase consideration within ten Business Days.",
            "status": "VERIFIED",
        },
    ]

    obligations = extract_obligations(mock_extractions)
    check(len(obligations) >= 4, f"extracted {len(obligations)} obligations")

    modalities = {o.modality for o in obligations}
    check("obligation" in modalities, "obligation modality found")
    check("prohibition" in modalities, "prohibition modality found")
    check("permission" in modalities, "permission modality found")

    # Supplier indemnification.
    indemnity = [o for o in obligations if o.source_category == "Indemnification"]
    check(len(indemnity) >= 1, f"indemnification obligation ({len(indemnity)})")
    if indemnity:
        check(indemnity[0].modality == "obligation", "indemnify is obligation")
        check("supplier" in indemnity[0].party.lower() or indemnity[0].party != "",
              f"party identified ({indemnity[0].party})")

    # Confidentiality prohibition.
    conf = [o for o in obligations if o.source_category == "Confidentiality"]
    check(len(conf) >= 1 and conf[0].modality == "prohibition",
          "confidentiality → prohibition")

    # Payment with deadline.
    pay = [o for o in obligations if o.source_category == "Payment Terms"]
    check(len(pay) >= 1 and pay[0].deadline != "",
          f"payment deadline extracted ({pay[0].deadline if pay else 'none'})")

    # Every obligation links to source category.
    check(all(o.source_category for o in obligations), "all linked to source category")
    check(all(o.evidence for o in obligations), "all have evidence")

    # Empty input.
    check(extract_obligations([]) == [], "empty input → empty")
    check(extract_obligations([{"evidence": ""}]) == [], "empty evidence → empty")

    # No trigger sentence.
    check(extract_obligations([{"evidence": "The agreement is dated January 2024.", "category": "Date"}]) == [],
          "no trigger → no obligations")

    # ── LexDeMod 7-class taxonomy ──────────────────────────────────────
    print("\n  lexdemod 7-class taxonomy")

    labels = _classify_modalities("Buyer shall pay the purchase price.")
    check(labels == ["OBLIGATION"], f"shall pay → OBLIGATION ({labels})")

    labels = _classify_modalities("Seller shall not disclose confidential information.")
    check(labels == ["PROHIBITION"], f"shall not disclose → PROHIBITION ({labels})")

    labels = _classify_modalities("Buyer may terminate this agreement.")
    check(labels == ["PERMISSION"], f"may terminate → PERMISSION ({labels})")

    labels = _classify_modalities("Seller is entitled to receive payment.")
    check(labels == ["ENTITLEMENT"], f"is entitled to → ENTITLEMENT ({labels})")

    labels = _classify_modalities("Buyer shall not be required to pay any fee.")
    check(labels == ["NO_OBLIGATION"], f"shall not be required → NO_OBLIGATION ({labels})")

    labels = _classify_modalities("Seller is not entitled to any compensation.")
    check(labels == ["NO_ENTITLEMENT"], f"is not entitled → NO_ENTITLEMENT ({labels})")

    labels = _classify_modalities("The agreement is dated January 2024.")
    check(labels == [], f"no deontic → [] ({labels})")

    labels = _classify_modalities("The Buyer is not obligated to proceed.")
    check(labels == ["NO_OBLIGATION"], f"is not obligated → NO_OBLIGATION ({labels})")

    labels = _classify_modalities("The company shall have no right to appeal.")
    check(labels == ["NO_ENTITLEMENT"], f"shall have no right → NO_ENTITLEMENT ({labels})")

    # ── negation scope ──────────────────────────────────────────────────
    print("\n  negation scope")

    neg = _detect_negation_scope("Buyer shall not be required to pay any fee.")
    check("not be required" in neg, f"negation detected ({neg})")

    neg = _detect_negation_scope("Seller is not entitled to compensation.")
    check("not" in neg and "entitled" in neg, f"not-entitled negation ({neg})")

    neg = _detect_negation_scope("Buyer shall pay the price.")
    check(neg == "", f"no negation in positive sentence ({neg})")

    # ── DeonticExtraction ───────────────────────────────────────────────
    print("\n  extract_deontic")

    deontic_input = [
        {"category": "Payment", "answer": "pay", "status": "VERIFIED",
         "evidence": "Buyer shall pay the purchase price within thirty days."},
        {"category": "Confidentiality", "answer": "not disclose", "status": "VERIFIED",
         "evidence": "Seller shall not disclose confidential information."},
        {"category": "Termination", "answer": "may terminate", "status": "VERIFIED",
         "evidence": "Either party may terminate this agreement."},
        {"category": "Entitlement", "answer": "receive payment", "status": "VERIFIED",
         "evidence": "Seller is entitled to receive payment."},
        {"category": "Limitation", "answer": "no fee", "status": "VERIFIED",
         "evidence": "Buyer shall not be required to pay any additional fee."},
        {"category": "Rights", "answer": "no compensation", "status": "VERIFIED",
         "evidence": "Seller is not entitled to any compensation."},
    ]
    deontic = extract_deontic(
        deontic_input, known_parties=["Buyer Corp", "Seller Inc"],
        document_id="doc-1", model_id="test", prompt_version="1.0",
    )

    check(len(deontic) == 6, f"6 deontic extractions ({len(deontic)})")

    all_labels = {lab for d in deontic for lab in d.modality_labels}
    check("OBLIGATION" in all_labels, "has OBLIGATION")
    check("PROHIBITION" in all_labels, "has PROHIBITION")
    check("PERMISSION" in all_labels, "has PERMISSION")
    check("ENTITLEMENT" in all_labels, "has ENTITLEMENT")
    check("NO_OBLIGATION" in all_labels, "has NO_OBLIGATION")
    check("NO_ENTITLEMENT" in all_labels, "has NO_ENTITLEMENT")

    # Schema fields
    d0 = deontic[0]
    check(d0.document_id == "doc-1", "document_id preserved")
    check(d0.schema_version == "2.0", f"schema_version ({d0.schema_version})")
    check(d0.model_id == "test", "model_id preserved")
    check(d0.trigger_text != "", f"trigger_text present ({d0.trigger_text})")
    check(d0.verification_status == "VERIFIED", "verification_status preserved")

    # Party resolution
    buyer_d = [d for d in deontic if d.party_name and "buyer" in d.party_name.lower()]
    check(len(buyer_d) >= 1, f"buyer party resolved ({len(buyer_d)})")
    if buyer_d:
        check(buyer_d[0].party_resolution_status == "resolved",
              f"buyer resolved ({buyer_d[0].party_resolution_status})")

    # Negation scope on NO_OBLIGATION
    no_obl = [d for d in deontic if "NO_OBLIGATION" in d.modality_labels]
    check(len(no_obl) >= 1 and no_obl[0].negation_scope is not None,
          f"NO_OBLIGATION has negation_scope ({no_obl[0].negation_scope if no_obl else 'none'})")

    # PartyRef
    pr = _resolve_party("the Buyer", ["Buyer Corp", "Seller Inc"])
    check(pr.resolution_status == "resolved", f"party resolved ({pr.resolution_status})")
    check(pr.canonical == "Buyer Corp", f"canonical={pr.canonical}")
    check(pr.party_id == "party_1", f"party_id={pr.party_id}")

    pr2 = _resolve_party("Unknown Entity", ["Buyer Corp"])
    check(pr2.resolution_status == "unresolved", "unknown party → unresolved")

    pr3 = _resolve_party("", None)
    check(pr3.resolution_status == "unresolved", "empty mention → unresolved")

    # Empty/no-trigger
    check(extract_deontic([]) == [], "empty deontic input → empty")
    check(extract_deontic([{"evidence": "Plain text.", "category": "X"}]) == [],
          "no trigger → no deontic")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
