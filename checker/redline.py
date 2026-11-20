"""Generate concrete text edits from positional playbook deviations.

Given a PositionResult that landed on FALLBACK or NOT_ACCEPTABLE, and the
extracted clause span + value, produce the smallest text replacement that
brings the clause to the starting position.

The algorithm:
    1. Find the VALUE substring within the SPAN (already verified by review_contract)
    2. Replace ONLY the value with the starting position's value
    3. Return old_text, new_text, and the edit kind

Edit kinds:
    REWRITE   — the value is replaced with the starting position's value
    DELETION  — the entire clause should be removed (must_be_absent_or_approved)
    INSERTION — a clause is missing and the starting position supplies it

This module does NOT touch Word. It produces data; the add-in applies it.

Run: PYTHONPATH=. python3 checker/redline.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.positions import (
    FALLBACK, MANDATORY, NEEDS_LAWYER, NICE_TO_HAVE, NOT_ACCEPTABLE,
    RECOMMENDED, STARTING, Position, PositionResult, PositionRule,
)

__all__ = [
    "Edit", "generate_edit", "generate_edits",
    "REWRITE", "DELETION", "INSERTION", "NO_EDIT",
    "word_jaccard",
]

REWRITE = "REWRITE"
DELETION = "DELETION"
INSERTION = "INSERTION"
NO_EDIT = "NO_EDIT"

# CUAD (arXiv 2103.06268): Jaccard ≥ 0.5 for span matching acceptance
JACCARD_THRESHOLD = 0.5
# DocuToads (arXiv 1608.06459): minimum 5 words to avoid spurious matches on common words
MIN_MATCH_WORDS = 3  # lowered from 5; legal values often 2-3 words ("three years")
# Pattern for structured values that bypass the min-word guard
_STRUCTURED_VALUE = re.compile(
    r"^(?:Rs\.?\s*[\d,]+|INR\s*[\d,]+|\d[\d,.]+\s*(?:crore|lakh|years?|months?|days?|%)|"
    r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4})$",
    re.IGNORECASE,
)


def word_jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity (CUAD metric, arXiv 2103.06268)."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


@dataclass(frozen=True)
class Edit:
    """A concrete text edit the add-in can apply as a tracked change."""
    rule_id: str
    clause: str
    kind: str
    old_text: str
    new_text: str
    comment: str
    priority: str
    status: str
    starting_text: str
    position_detail: str
    # ponytail: Fuzzy Triage (arXiv 2603.07390) confidence from position resolution
    confidence: float = 1.0
    # "exact" | "fuzzy" | "none" — how the value was located in the span
    match_quality: str = "exact"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "clause": self.clause,
            "kind": self.kind,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "comment": self.comment,
            "priority": self.priority,
            "status": self.status,
            "starting_text": self.starting_text,
            "position_detail": self.position_detail,
            "confidence": self.confidence,
            "match_quality": self.match_quality,
        }


def _find_value_in_span(span: str, value: str) -> tuple[int, int, str] | None:
    """Find the value substring within the span, with Jaccard fallback.

    Returns (start, end, quality) where quality is "exact" or "fuzzy".
    Returns None if neither method finds the value.

    - Exact: case-insensitive substring match (current behaviour)
    - Fuzzy: word-level Jaccard ≥ 0.5 on sliding windows (CUAD, arXiv 2103.06268)
    - Guard: values < MIN_MATCH_WORDS must be structured (DocuToads, arXiv 1608.06459)
    """
    norm_value = value.strip()
    if not norm_value:
        return None

    # DocuToads guard: reject very short free-text values to avoid spurious matches
    value_words = norm_value.split()
    if len(value_words) < MIN_MATCH_WORDS and not _STRUCTURED_VALUE.match(norm_value):
        # Still try exact match; just block fuzzy for short unstructured values
        idx = span.lower().find(norm_value.lower())
        if idx != -1:
            return (idx, idx + len(norm_value), "exact")
        return None

    # Try exact match first
    idx = span.lower().find(norm_value.lower())
    if idx != -1:
        return (idx, idx + len(norm_value), "exact")

    # Fuzzy fallback: sliding window of similar word count, best Jaccard
    span_words = span.split()
    window = len(value_words)
    best_j, best_start, best_end = 0.0, 0, 0
    for i in range(max(1, len(span_words) - window + 1)):
        chunk_words = span_words[i:i + window]
        chunk = " ".join(chunk_words)
        j = word_jaccard(norm_value, chunk)
        if j > best_j:
            best_j = j
            # reconstruct character offsets from the original span
            before = " ".join(span_words[:i])
            best_start = len(before) + (1 if before else 0)
            best_end = best_start + len(chunk)

    if best_j >= JACCARD_THRESHOLD:
        return (best_start, best_end, "fuzzy")
    return None


def _starting_value_text(rule: PositionRule) -> str:
    """The text form of the starting position's value, for insertion into a clause."""
    v = rule.starting.value
    if isinstance(v, (list, tuple)):
        return str(v[0])
    return str(v)


def generate_edit(
    result: PositionResult,
    rule: PositionRule,
    span: str | None = None,
    value: str | None = None,
) -> Edit:
    """Turn a positional deviation into a concrete text edit.

    span: the verbatim clause text from the contract (from extraction)
    value: the specific value extracted from the span (e.g. "three years")
    """
    conf = result.confidence

    if result.status == STARTING:
        return Edit(
            rule_id=result.rule_id, clause=result.clause,
            kind=NO_EDIT, old_text="", new_text="",
            comment="Meets starting position.",
            priority=result.priority, status=result.status,
            starting_text=rule.starting.text,
            position_detail=result.detail,
            confidence=conf, match_quality="exact",
        )

    if result.status == NEEDS_LAWYER:
        return Edit(
            rule_id=result.rule_id, clause=result.clause,
            kind=NO_EDIT, old_text="", new_text="",
            comment=f"Needs lawyer review: {result.detail}",
            priority=result.priority, status=result.status,
            starting_text=rule.starting.text,
            position_detail=result.detail,
            confidence=conf, match_quality="none",
        )

    # MISSING clause → suggest insertion
    if span is None or not span.strip():
        return Edit(
            rule_id=result.rule_id, clause=result.clause,
            kind=INSERTION, old_text="",
            new_text=rule.starting.text,
            comment=f"Missing clause. Starting position: {rule.starting.text}",
            priority=result.priority, status=result.status,
            starting_text=rule.starting.text,
            position_detail=result.detail,
            confidence=conf, match_quality="none",
        )

    # FALLBACK or NOT_ACCEPTABLE with a span — rewrite the value
    if value and span:
        loc = _find_value_in_span(span, value)
        if loc is not None:
            start, end, quality = loc
            start_val = _starting_value_text(rule)
            new_span = span[:start] + start_val + span[end:]
            status_label = "Fallback" if result.status == FALLBACK else "Not acceptable"
            fuzzy_note = " [fuzzy match]" if quality == "fuzzy" else ""
            return Edit(
                rule_id=result.rule_id, clause=result.clause,
                kind=REWRITE, old_text=span, new_text=new_span,
                comment=(
                    f"[{status_label}]{fuzzy_note} {result.detail}\n"
                    f"Starting position: {rule.starting.text}"
                ),
                priority=result.priority, status=result.status,
                starting_text=rule.starting.text,
                position_detail=result.detail,
                confidence=conf, match_quality=quality,
            )

    # Fallback: can't locate value in span, suggest full span replacement
    status_label = "Fallback" if result.status == FALLBACK else "Not acceptable"
    return Edit(
        rule_id=result.rule_id, clause=result.clause,
        kind=REWRITE, old_text=span or "", new_text=rule.starting.text,
        comment=(
            f"[{status_label}] {result.detail}\n"
            f"Starting position: {rule.starting.text}"
        ),
        priority=result.priority, status=result.status,
        starting_text=rule.starting.text,
        position_detail=result.detail,
        confidence=conf, match_quality="none",
    )


def generate_edits(
    results: tuple[PositionResult, ...],
    rules: tuple[PositionRule, ...],
    extracted: dict[str, tuple[str, str]],
) -> tuple[Edit, ...]:
    """Generate edits for all results.

    extracted: {clause_name: (span, value)} from the extraction step.
    """
    rule_map = {r.id: r for r in rules}
    edits = []
    for result in results:
        rule = rule_map.get(result.rule_id)
        if rule is None:
            continue
        span, value = extracted.get(result.clause, (None, None))
        edits.append(generate_edit(result, rule, span, value))
    return tuple(edits)


# ── self-test ──────────────────────────────────────────────────────────────

def _self_test() -> None:
    passed = failed = 0

    def check(name: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    # Setup: NDA survival rule
    survival = PositionRule(
        id="NDA-SURVIVAL", clause="survival_period",
        starting=Position("5 years from termination", "5 years"),
        fallbacks=(Position("3 years if counterparty pushes", "3 years"),),
        dealbreaker=Position("below 1 year", "1 year"),
        priority=MANDATORY, comparator="min_years",
    )

    # STARTING → NO_EDIT
    r = PositionResult("NDA-SURVIVAL", "survival_period", STARTING,
                       position_index=0, detail="meets starting position",
                       priority=MANDATORY)
    e = generate_edit(r, survival, "survive for five years from termination", "five years")
    check("STARTING produces NO_EDIT", e.kind == NO_EDIT)

    # FALLBACK → REWRITE with value replacement
    r = PositionResult("NDA-SURVIVAL", "survival_period", FALLBACK,
                       position_index=1, detail="meets fallback 1: 3 years",
                       priority=MANDATORY)
    e = generate_edit(r, survival,
                      "Obligations survive for three years from termination",
                      "three years")
    check("FALLBACK produces REWRITE", e.kind == REWRITE)
    check("old_text is the original span",
          e.old_text == "Obligations survive for three years from termination")
    check("new_text replaces value with starting",
          "5 years" in e.new_text and "three years" not in e.new_text)
    check("rest of span preserved",
          "Obligations survive for" in e.new_text and "from termination" in e.new_text)

    # NOT_ACCEPTABLE → REWRITE
    r = PositionResult("NDA-SURVIVAL", "survival_period", NOT_ACCEPTABLE,
                       detail="crosses dealbreaker: below 1 year", priority=MANDATORY)
    e = generate_edit(r, survival,
                      "Obligations survive for six months from termination",
                      "six months")
    check("NOT_ACCEPTABLE produces REWRITE", e.kind == REWRITE)
    check("comment mentions not acceptable", "Not acceptable" in e.comment)

    # MISSING clause → INSERTION
    r = PositionResult("NDA-SURVIVAL", "survival_period", NOT_ACCEPTABLE,
                       detail="below all fallback positions", priority=MANDATORY)
    e = generate_edit(r, survival, None, None)
    check("missing span produces INSERTION", e.kind == INSERTION)
    check("insertion text is the starting position", e.new_text == survival.starting.text)

    # NEEDS_LAWYER → NO_EDIT
    r = PositionResult("NDA-SURVIVAL", "survival_period", NEEDS_LAWYER,
                       detail="value could not be compared", priority=MANDATORY)
    e = generate_edit(r, survival, "some clause text", "forever")
    check("NEEDS_LAWYER produces NO_EDIT", e.kind == NO_EDIT)
    check("comment says needs lawyer", "Needs lawyer" in e.comment)

    # in_list comparator: governing law
    gov_law = PositionRule(
        id="GOV-LAW", clause="governing_law",
        starting=Position("Indian law, courts of Mumbai", "India"),
        fallbacks=(), dealbreaker=None,
        priority=MANDATORY, comparator="in_list",
    )
    r = PositionResult("GOV-LAW", "governing_law", NOT_ACCEPTABLE,
                       detail="below all fallback positions", priority=MANDATORY)
    e = generate_edit(r, gov_law,
                      "governed by the laws of Singapore",
                      "Singapore")
    check("in_list rewrite replaces value", "India" in e.new_text)
    check("in_list rewrite keeps frame", "governed by the laws of" in e.new_text)

    # generate_edits batch
    rules = (survival, gov_law)
    results = (
        PositionResult("NDA-SURVIVAL", "survival_period", FALLBACK,
                       position_index=1, detail="fallback 1", priority=MANDATORY),
        PositionResult("GOV-LAW", "governing_law", STARTING,
                       position_index=0, detail="starting", priority=MANDATORY),
    )
    extracted = {
        "survival_period": ("survive for three years", "three years"),
        "governing_law": ("governed by Indian law", "Indian law"),
    }
    edits = generate_edits(results, rules, extracted)
    check("generate_edits returns one per result", len(edits) == 2)
    check("first edit is REWRITE", edits[0].kind == REWRITE)
    check("second edit is NO_EDIT (STARTING)", edits[1].kind == NO_EDIT)

    # to_dict roundtrip
    d = edits[0].to_dict()
    check("to_dict has all keys", set(d) == {
        "rule_id", "clause", "kind", "old_text", "new_text",
        "comment", "priority", "status", "starting_text", "position_detail",
        "confidence", "match_quality",
    })

    # ── word_jaccard (CUAD, arXiv 2103.06268) ──
    check("jaccard identical = 1.0", word_jaccard("three years", "three years") == 1.0)
    check("jaccard disjoint = 0.0", word_jaccard("three years", "five months") == 0.0)
    check("jaccard partial overlap", 0.0 < word_jaccard("three years from date", "three years") < 1.0)
    check("jaccard empty = 0.0", word_jaccard("", "test") == 0.0)

    # ── fuzzy span matching ──
    # Exact match still works
    loc = _find_value_in_span("survive for three years from termination", "three years")
    check("exact match returns quality='exact'", loc is not None and loc[2] == "exact")

    # Fuzzy match: "three yrs" vs span containing "three years"
    loc = _find_value_in_span(
        "obligations survive for three years from the date of termination",
        "three years from termination date")
    check("fuzzy match finds near-match", loc is not None and loc[2] == "fuzzy")

    # Min-word guard: single word without structure → no fuzzy
    loc = _find_value_in_span("governed by the laws of Singapore", "india")
    check("short value no exact match → None", loc is None)

    # Structured short value passes guard: "Rs 50,000"
    loc = _find_value_in_span("liability capped at Rs 50,000 per annum", "Rs 50,000")
    check("structured short value → exact match", loc is not None and loc[2] == "exact")

    # ── confidence propagation ──
    r = PositionResult("NDA-SURVIVAL", "survival_period", FALLBACK,
                       position_index=1, detail="fallback 1", priority=MANDATORY,
                       confidence=0.85)
    e = generate_edit(r, survival,
                      "Obligations survive for three years from termination",
                      "three years")
    check("confidence propagated to edit", e.confidence == 0.85)
    check("match_quality is exact", e.match_quality == "exact")

    # vocabulary: no legal verdict words
    all_edits = [
        generate_edit(
            PositionResult("X", "c", s, detail="d", priority=MANDATORY),
            survival, "survive for three years", "three years")
        for s in (STARTING, FALLBACK, NOT_ACCEPTABLE, NEEDS_LAWYER)
    ]
    banned = ("violation", "breach", "unenforceable", "illegal", "defect")
    hits = [w for e in all_edits for w in banned
            if w in f"{e.comment} {e.kind}".lower()]
    check("no legal verdict words in output", not hits)

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
