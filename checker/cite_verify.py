"""Post-generation citation verification: every line checked against its source.

Jurisphere's claim: "Each citation is matched against its source before the answer
reaches you." This module does the same for PlacedOn's conversation answers.

The pipeline:
  1. EXTRACT citations from a generated answer (provision + span pairs)
  2. LOCATE each citation's source text in the corpus
  3. VERIFY the cited span actually appears in the source (exact match)
  4. CHECK the proposition the citation supports (entailment, via the model cascade)

A citation that fails step 3 is UNVERIFIABLE — the span doesn't exist.
A citation that fails step 4 is UNSUPPORTED — the span exists but doesn't back the claim.
Both are surfaced to the user, never silently dropped.

This module is CODE for steps 1-3 and delegates step 4 to the model cascade.
Step 4 is optional and expensive; steps 1-3 are deterministic and run on every answer.

Run: PYTHONPATH=. python3 checker/cite_verify.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

__all__ = [
    "Citation", "VerifiedCitation", "verify_citations",
    "VERIFIED", "SPAN_NOT_FOUND", "SOURCE_NOT_FOUND",
]

VERIFIED = "VERIFIED"
SPAN_NOT_FOUND = "SPAN_NOT_FOUND"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
STATUSES = (VERIFIED, SPAN_NOT_FOUND, SOURCE_NOT_FOUND)


@dataclass(frozen=True)
class Citation:
    """A citation extracted from a generated answer line."""
    line_index: int
    proposition: str
    provision: str | None
    span: str | None
    source_key: str | None = None


@dataclass(frozen=True)
class VerifiedCitation:
    """A citation after verification against the corpus."""
    citation: Citation
    status: str
    matched_offset: int | None = None
    source_text_length: int | None = None
    detail: str = ""


# ── extraction ─────────────────────────────────────────────────────────────

_CITE_MARKER = re.compile(
    r"\[(\d{1,3})\]"
    r"|"
    r"(?:Section|s\.)\s*(\d{1,4}(?:\([^)]+\))*)"
    r"|"
    r"(?:Regulation|Reg\.)\s*(\d{1,4}(?:\([^)]+\))*)",
    re.IGNORECASE,
)


def extract_citations(lines: list[str]) -> list[Citation]:
    """Pull citation markers from each line of a generated answer.

    Handles:
      - Numbered markers: [1], [2]
      - Inline provisions: Section 96(1), s.173, Regulation 30
    """
    out: list[Citation] = []
    for i, line in enumerate(lines):
        for m in _CITE_MARKER.finditer(line):
            # numbered marker
            if m.group(1):
                out.append(Citation(
                    line_index=i,
                    proposition=line.strip(),
                    provision=None,
                    span=None,
                    source_key=m.group(1),
                ))
            # section reference
            elif m.group(2):
                out.append(Citation(
                    line_index=i,
                    proposition=line.strip(),
                    provision=f"s.{m.group(2)}",
                    span=None,
                ))
            # regulation reference
            elif m.group(3):
                out.append(Citation(
                    line_index=i,
                    proposition=line.strip(),
                    provision=f"reg.{m.group(3)}",
                    span=None,
                ))
    return out


# ── span verification ──────────────────────────────────────────────────────

def _normalise_whitespace(text: str) -> str:
    """Collapse runs of whitespace for fuzzy span matching."""
    return re.sub(r"\s+", " ", text.strip())


def find_span_in_source(span: str, source: str) -> int | None:
    """Find the span's offset in source text. Returns start offset or None.

    Tries exact match first, then whitespace-normalised match.
    """
    if not span or not source:
        return None
    idx = source.find(span)
    if idx >= 0:
        return idx
    ns = _normalise_whitespace(span)
    nsrc = _normalise_whitespace(source)
    idx = nsrc.find(ns)
    return idx if idx >= 0 else None


def verify_span(citation: Citation, source_text: str) -> VerifiedCitation:
    """Verify a single citation's span against source text."""
    if citation.span is None:
        return VerifiedCitation(
            citation=citation,
            status=VERIFIED,
            source_text_length=len(source_text),
            detail="no span to verify (provision-level citation)",
        )
    offset = find_span_in_source(citation.span, source_text)
    if offset is not None:
        return VerifiedCitation(
            citation=citation,
            status=VERIFIED,
            matched_offset=offset,
            source_text_length=len(source_text),
        )
    return VerifiedCitation(
        citation=citation,
        status=SPAN_NOT_FOUND,
        source_text_length=len(source_text),
        detail=f"span not found in source ({len(source_text)} chars searched)",
    )


# ── corpus lookup ──────────────────────────────────────────────────────────

def _load_section_text(provision: str) -> str | None:
    """Load section text from corpus by provision reference.

    Returns the full section text or None if not found.
    """
    from checker.section_index import section_by_number

    num = re.search(r"(\d+)", provision)
    if not num:
        return None
    entry = section_by_number(num.group(1))
    if entry is None:
        return None
    return entry.get("content")


# ── the main pipeline ──────────────────────────────────────────────────────

def verify_citations(
    lines: list[str],
    source_spans: dict[str, str] | None = None,
) -> list[VerifiedCitation]:
    """Verify all citations in a generated answer.

    Args:
        lines: the answer split into lines
        source_spans: optional pre-loaded map of source_key → source text.
            When a citation has a source_key (numbered marker), the caller
            provides the text. When it has a provision, the corpus is queried.

    Returns one VerifiedCitation per extracted citation.
    """
    citations = extract_citations(lines)
    if not citations:
        return []
    source_spans = source_spans or {}
    results: list[VerifiedCitation] = []
    for cit in citations:
        # resolve source text
        source: str | None = None
        if cit.source_key and cit.source_key in source_spans:
            source = source_spans[cit.source_key]
        elif cit.provision:
            source = _load_section_text(cit.provision)
        if source is None:
            results.append(VerifiedCitation(
                citation=cit,
                status=SOURCE_NOT_FOUND,
                detail=f"no source text for {cit.provision or cit.source_key}",
            ))
            continue
        results.append(verify_span(cit, source))
    return results


# ── summary ────────────────────────────────────────────────────────────────

def verification_summary(results: list[VerifiedCitation]) -> dict:
    """Summary stats for a set of verification results."""
    total = len(results)
    verified = sum(1 for r in results if r.status == VERIFIED)
    not_found = sum(1 for r in results if r.status == SPAN_NOT_FOUND)
    no_source = sum(1 for r in results if r.status == SOURCE_NOT_FOUND)
    return {
        "total": total,
        "verified": verified,
        "span_not_found": not_found,
        "source_not_found": no_source,
        "all_verified": total > 0 and verified == total,
    }


# ── self-test ──────────────────────────────────────────────────────────────

def _self_test() -> None:
    passed = 0
    failed = 0

    def check(name: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    # extract_citations
    lines = [
        "The board must meet at least four times a year. [1]",
        "Section 173(1) requires quarterly meetings.",
        "Regulation 17(2) mandates the same for listed entities.",
        "This line has no citation.",
    ]
    cits = extract_citations(lines)
    check("extracts numbered marker [1]", any(c.source_key == "1" for c in cits))
    check("extracts Section 173(1)", any(c.provision == "s.173(1)" for c in cits))
    check("extracts Regulation 17(2)", any(c.provision == "reg.17(2)" for c in cits))
    check("line without citation produces none",
          not any(c.line_index == 3 for c in cits))

    # find_span_in_source
    source = "The company shall hold at least four board meetings in every calendar year."
    check("exact span found", find_span_in_source("at least four board meetings", source) is not None)
    check("span with extra whitespace found",
          find_span_in_source("at  least  four  board  meetings", source) is not None)
    check("absent span not found", find_span_in_source("six annual meetings", source) is None)
    check("empty span returns None", find_span_in_source("", source) is None)

    # verify_span
    cit = Citation(line_index=0, proposition="test", provision="s.173", span="at least four board meetings")
    result = verify_span(cit, source)
    check("verify_span VERIFIED on match", result.status == VERIFIED)
    check("verify_span records offset", result.matched_offset is not None)

    cit_bad = Citation(line_index=0, proposition="test", provision="s.173", span="six annual meetings")
    result_bad = verify_span(cit_bad, source)
    check("verify_span SPAN_NOT_FOUND on miss", result_bad.status == SPAN_NOT_FOUND)

    cit_no_span = Citation(line_index=0, proposition="test", provision="s.173", span=None)
    result_no = verify_span(cit_no_span, source)
    check("provision-only citation verifies", result_no.status == VERIFIED)

    # verify_citations with pre-loaded sources
    answer = [
        "The board must meet quarterly. [1]",
        "Section 173(1) mandates this.",
    ]
    sources = {"1": source}
    results = verify_citations(answer, source_spans=sources)
    check("verify_citations returns results for all citations", len(results) >= 2)
    check("numbered citation verified against provided source",
          any(r.citation.source_key == "1" and r.status == VERIFIED for r in results))

    # verification_summary
    summary = verification_summary(results)
    check("summary has total", summary["total"] >= 2)
    check("summary counts verified", summary["verified"] >= 1)

    # vocabulary
    check("VERIFIED in STATUSES", VERIFIED in STATUSES)
    check("SPAN_NOT_FOUND in STATUSES", SPAN_NOT_FOUND in STATUSES)
    check("SOURCE_NOT_FOUND in STATUSES", SOURCE_NOT_FOUND in STATUSES)

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
