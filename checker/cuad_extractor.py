"""CUAD-style extractive QA — question-driven clause extraction with deterministic verification.

Stages 3-5 of the CUAD implementation:
  3. Windowing, prompt construction, response parsing
  4. Deterministic evidence verification (model proposes, code verifies)
  5. Abstention and confidence

The model MAY PROPOSE a quotation. Deterministic code MUST LOCATE it in the source.
An extraction without supporting evidence is never marked VERIFIED.

Run: PYTHONPATH=. python3 checker/cuad_extractor.py --test
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from checker.clause_tags import MIN_QUOTE
from checker.cuad_categories import ALL_CATEGORIES, Category, select_categories, SCHEMA_VERSION

__all__ = ["Extraction", "ExtractionResult", "extract", "extract_from_state"]

# ── constants ──────────────────────────────────────────────────────────────────
WINDOW_SIZE = 6000       # characters per window
STRIDE = 2000            # overlap stride
FUZZY_THRESHOLD = 0.5    # Jaccard word-level threshold for fuzzy match
MIN_SPAN_LENGTH = MIN_QUOTE  # reuse clause_tags minimum
DEDUP_JACCARD = 0.8      # threshold for cross-window dedup
PROMPT_VERSION = "1.0"


# ── data types ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Window:
    start: int
    end: int
    text: str
    index: int


@dataclass(frozen=True)
class RawExtraction:
    category: str
    answer: str
    evidence: str
    absent: bool


@dataclass(frozen=True)
class Extraction:
    category: str
    answer_text: str
    evidence_text: str
    normalized_value: str
    start_offset: int
    end_offset: int
    page_number: int | None
    verification_status: str  # VERIFIED, FUZZY_MATCH, PARTIALLY_VERIFIED, UNVERIFIED, NOT_FOUND
    review_status: str        # PENDING, APPROVED
    model_provider: str
    model_version: str
    prompt_version: str
    schema_version: str


@dataclass(frozen=True)
class ExtractionResult:
    extractions: tuple[Extraction, ...]
    model_provider: str
    model_version: str
    categories_asked: tuple[str, ...]
    categories_found: tuple[str, ...]
    categories_absent: tuple[str, ...]
    errors: tuple[str, ...]


# ── 1. Windowing ───────────────────────────────────────────────────────────────

def _windows(text: str, *, window_size: int = WINDOW_SIZE,
             stride: int = STRIDE) -> list[Window]:
    if not text:
        return []
    if len(text) <= window_size:
        return [Window(0, len(text), text, 0)]

    windows: list[Window] = []
    pos = 0
    idx = 0
    while pos < len(text):
        end = min(pos + window_size, len(text))
        windows.append(Window(pos, end, text[pos:end], idx))
        idx += 1
        pos += stride
        if end == len(text):
            break
    return windows


# ── 2. Prompt construction ─────────────────────────────────────────────────────

def _build_prompt(window: Window, categories: list[str]) -> str:
    questions = []
    for i, cat_name in enumerate(categories, 1):
        cat = ALL_CATEGORIES[cat_name]
        questions.append(f"{i}. [{cat_name}] {cat.question}")

    return f"""You are a legal contract analyst. Extract answers from the contract text below.

For each question, respond with a JSON array. Each element must have:
- "category": the category name in brackets
- "answer": the extracted answer, or "NOT_FOUND" if absent
- "evidence": the exact verbatim quote from the text supporting your answer, or "" if NOT_FOUND

Rules:
- Quote EXACTLY from the text. Do not paraphrase.
- If information is not present, answer "NOT_FOUND" with empty evidence.
- If multiple answers exist, return multiple objects for that category.
- Do not fabricate information. Only extract what is explicitly stated.

CONTRACT TEXT (characters {window.start}-{window.end}):
---
{window.text}
---

QUESTIONS:
{chr(10).join(questions)}

Respond with ONLY a JSON array. No markdown, no explanation."""


# ── 3. Response parsing ────────────────────────────────────────────────────────

def _parse_response(response: str, valid_categories: frozenset[str]) -> list[RawExtraction]:
    if not response or not response.strip():
        return []

    text = response.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the response.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    if not isinstance(data, list):
        return []

    _MAX_ITEMS = 200  # ponytail: defensive cap; real responses are <50
    extractions: list[RawExtraction] = []
    for item in data[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        cat = item.get("category", "")
        answer = str(item.get("answer", ""))
        evidence = str(item.get("evidence", ""))

        if cat not in valid_categories:
            continue

        absent = answer.upper() == "NOT_FOUND" or not answer.strip()
        extractions.append(RawExtraction(cat, answer, evidence, absent))

    return extractions


# ── 4. Deterministic evidence verification ─────────────────────────────────────

def _word_jaccard(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _find_span(evidence: str, source: str) -> tuple[int, int, str]:
    """Locate evidence in source text. Returns (start, end, status)."""
    if not evidence or len(evidence) < MIN_SPAN_LENGTH:
        return -1, -1, "UNVERIFIED"

    # Exact match.
    idx = source.find(evidence)
    if idx >= 0:
        return idx, idx + len(evidence), "VERIFIED"

    # Whitespace-normalized match.
    norm_evidence = " ".join(evidence.split())
    norm_source = " ".join(source.split())
    idx = norm_source.find(norm_evidence)
    if idx >= 0:
        # Find approximate position in original.
        orig_idx = source.find(norm_evidence[:40])
        if orig_idx >= 0:
            return orig_idx, orig_idx + len(evidence), "VERIFIED"
        return 0, len(evidence), "VERIFIED"

    # Fuzzy match: sliding window over sentences.
    sentences = re.split(r"[.!?\n]+", source)
    best_score = 0.0
    best_start = -1
    best_end = -1
    pos = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            pos = source.find(sent, pos) + len(sent) if sent else pos
            continue
        score = _word_jaccard(evidence, sent)
        if score > best_score:
            best_score = score
            sent_start = source.find(sent, pos)
            if sent_start >= 0:
                best_start = sent_start
                best_end = sent_start + len(sent)
        pos = source.find(sent, pos)
        if pos >= 0:
            pos += len(sent)

    if best_score >= FUZZY_THRESHOLD and best_start >= 0:
        return best_start, best_end, "FUZZY_MATCH"

    return -1, -1, "UNVERIFIED"


def _verify_extractions(raw_list: list[RawExtraction], source: str,
                        *, window_offset: int = 0) -> list[Extraction]:
    verified: list[Extraction] = []
    for raw in raw_list:
        if raw.absent:
            continue

        start, end, status = _find_span(raw.evidence, source)

        if status == "UNVERIFIED":
            # Don't include unverified extractions in output.
            continue

        # Adjust offsets to document-level.
        doc_start = start + window_offset if start >= 0 else -1
        doc_end = end + window_offset if end >= 0 else -1

        # Use the actual source text for verified extractions.
        actual_evidence = source[start:end] if start >= 0 and end >= 0 else raw.evidence

        verified.append(Extraction(
            category=raw.category,
            answer_text=raw.answer,
            evidence_text=actual_evidence,
            normalized_value=raw.answer,
            start_offset=doc_start,
            end_offset=doc_end,
            page_number=None,
            verification_status=status,
            review_status="PENDING",
            model_provider="",
            model_version="",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        ))

    return verified


# ── 5. Cross-window deduplication ──────────────────────────────────────────────

def _deduplicate(extractions: list[Extraction]) -> list[Extraction]:
    if not extractions:
        return []

    by_category: dict[str, list[Extraction]] = {}
    for ext in extractions:
        by_category.setdefault(ext.category, []).append(ext)

    deduped: list[Extraction] = []
    for cat, exts in by_category.items():
        kept: list[Extraction] = []
        for ext in exts:
            is_dup = False
            for existing in kept:
                sim = _word_jaccard(ext.evidence_text, existing.evidence_text)
                if sim >= DEDUP_JACCARD:
                    # Keep the one with better verification.
                    if ext.verification_status == "VERIFIED" and existing.verification_status != "VERIFIED":
                        kept.remove(existing)
                        kept.append(ext)
                    is_dup = True
                    break
            if not is_dup:
                kept.append(ext)
        deduped.extend(kept)

    deduped.sort(key=lambda e: (e.category, e.start_offset))
    return deduped


# ── 6. Page number resolution ──────────────────────────────────────────────────

def _resolve_pages(extractions: list[Extraction],
                   page_boundaries: tuple[int, ...] | None) -> list[Extraction]:
    if not page_boundaries or not extractions:
        return extractions

    result: list[Extraction] = []
    for ext in extractions:
        page = None
        if ext.start_offset >= 0:
            for i, boundary in enumerate(page_boundaries):
                next_b = page_boundaries[i + 1] if i + 1 < len(page_boundaries) else float("inf")
                if boundary <= ext.start_offset < next_b:
                    page = i + 1
                    break
        result.append(Extraction(
            category=ext.category,
            answer_text=ext.answer_text,
            evidence_text=ext.evidence_text,
            normalized_value=ext.normalized_value,
            start_offset=ext.start_offset,
            end_offset=ext.end_offset,
            page_number=page,
            verification_status=ext.verification_status,
            review_status=ext.review_status,
            model_provider=ext.model_provider,
            model_version=ext.model_version,
            prompt_version=ext.prompt_version,
            schema_version=ext.schema_version,
        ))
    return result


# ── 7. Abstention tracking ────────────────────────────────────────────────────

def _compute_abstentions(all_raw: list[RawExtraction],
                         categories_asked: list[str]) -> tuple[list[str], list[str]]:
    found: set[str] = set()
    absent: set[str] = set()
    for raw in all_raw:
        if raw.absent:
            absent.add(raw.category)
        else:
            found.add(raw.category)

    # A category is truly absent only if ALL windows reported NOT_FOUND.
    confirmed_absent = sorted(absent - found)
    confirmed_found = sorted(found)
    return confirmed_found, confirmed_absent


# ── Public API ─────────────────────────────────────────────────────────────────

RouteFunction = Callable[[str], str]


def extract(text: str, *,
            tag_names: frozenset[str] = frozenset(),
            doc_class: str = "",
            route_fn: RouteFunction | None = None,
            page_boundaries: tuple[int, ...] | None = None,
            model_provider: str = "",
            model_version: str = "") -> ExtractionResult:
    """CUAD extractive QA on a document.

    route_fn: callable that sends a prompt and returns the model response.
              If None, returns empty result (model unavailable).
    """
    if not text or route_fn is None:
        cats = select_categories(tag_names, doc_class)
        return ExtractionResult(
            extractions=(),
            model_provider=model_provider,
            model_version=model_version,
            categories_asked=tuple(cats),
            categories_found=(),
            categories_absent=tuple(cats) if text else (),
            errors=() if text else ("empty document",),
        )

    categories = select_categories(tag_names, doc_class)
    valid_cats = frozenset(categories)
    windows = _windows(text)

    all_verified: list[Extraction] = []
    all_raw: list[RawExtraction] = []
    errors: list[str] = []

    for window in windows:
        prompt = _build_prompt(window, categories)
        try:
            response = route_fn(prompt)
        except Exception as e:
            errors.append(f"window {window.index}: {e}")
            continue

        raw = _parse_response(response, valid_cats)
        all_raw.extend(raw)

        verified = _verify_extractions(raw, window.text, window_offset=window.start)
        all_verified.extend(verified)

    deduped = _deduplicate(all_verified)
    with_pages = _resolve_pages(deduped, page_boundaries)

    # Stamp model info.
    final: list[Extraction] = []
    for ext in with_pages:
        final.append(Extraction(
            category=ext.category,
            answer_text=ext.answer_text,
            evidence_text=ext.evidence_text,
            normalized_value=ext.normalized_value,
            start_offset=ext.start_offset,
            end_offset=ext.end_offset,
            page_number=ext.page_number,
            verification_status=ext.verification_status,
            review_status=ext.review_status,
            model_provider=model_provider,
            model_version=model_version,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        ))

    found_cats, absent_cats = _compute_abstentions(all_raw, categories)

    return ExtractionResult(
        extractions=tuple(final),
        model_provider=model_provider,
        model_version=model_version,
        categories_asked=tuple(categories),
        categories_found=tuple(found_cats),
        categories_absent=tuple(absent_cats),
        errors=tuple(errors),
    )


def extract_from_state(state: Any, *, route_fn: RouteFunction | None = None,
                       model_provider: str = "", model_version: str = "",
                       page_boundaries: tuple[int, ...] | None = None) -> Any:
    """Extract from a pipeline DocumentState. Returns updated state."""
    from checker.pipeline import DocumentState, _with

    tag_names = frozenset(t.tag for t in state.tags)
    result = extract(
        state.text,
        tag_names=tag_names,
        doc_class=state.doc_class,
        route_fn=route_fn,
        page_boundaries=page_boundaries,
        model_provider=model_provider,
        model_version=model_version,
    )

    extraction_dicts = tuple(
        {
            "category": e.category,
            "answer": e.answer_text,
            "evidence": e.evidence_text,
            "normalized_value": e.normalized_value,
            "start": e.start_offset,
            "end": e.end_offset,
            "page": e.page_number,
            "status": e.verification_status,
            "review": e.review_status,
            "model": f"{e.model_provider}/{e.model_version}",
        }
        for e in result.extractions
    )

    route_str = f"{model_provider}/{model_version}" if model_provider else ""
    return _with(
        state,
        extractions=extraction_dicts,
        extraction_route=route_str,
        stages_completed=state.stages_completed + ("extract",),
    )


# ── self-tests ─────────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("cuad_extractor")

    # ── windowing ────────────────────────────────────────────────────────
    check(_windows("") == [], "empty text → no windows")
    short = "x" * 100
    w = _windows(short)
    check(len(w) == 1 and w[0].start == 0 and w[0].end == 100,
          f"short text → 1 window ({len(w)})")

    long = "x" * 10000
    w = _windows(long)
    expected = (10000 - WINDOW_SIZE) // STRIDE + 1 + (1 if (10000 - WINDOW_SIZE) % STRIDE else 0)
    check(len(w) >= 3, f"10K text → {len(w)} windows")
    check(w[0].start == 0, "first window starts at 0")
    check(w[-1].end == 10000, "last window ends at document end")
    # Overlap check.
    if len(w) >= 2:
        overlap = w[0].end - w[1].start
        check(overlap == WINDOW_SIZE - STRIDE,
              f"overlap = {overlap} (expected {WINDOW_SIZE - STRIDE})")

    # ── prompt construction ──────────────────────────────────────────────
    win = Window(0, 100, "Test contract text.", 0)
    prompt = _build_prompt(win, ["Governing Law", "Parties"])
    check("Governing Law" in prompt and "Parties" in prompt,
          "prompt contains category names")
    check("CONTRACT TEXT" in prompt, "prompt has contract text section")
    check("JSON array" in prompt, "prompt asks for JSON")
    check("NOT_FOUND" in prompt, "prompt mentions NOT_FOUND")

    # ── response parsing ─────────────────────────────────────────────────
    valid = frozenset(["Governing Law", "Parties"])

    good_response = json.dumps([
        {"category": "Governing Law", "answer": "India", "evidence": "governed by the laws of India"},
        {"category": "Parties", "answer": "Acme Corp", "evidence": "between Acme Corp and Beta"},
    ])
    parsed = _parse_response(good_response, valid)
    check(len(parsed) == 2, f"good JSON → {len(parsed)} extractions")
    check(not parsed[0].absent, "non-NOT_FOUND is not absent")

    not_found = json.dumps([
        {"category": "Governing Law", "answer": "NOT_FOUND", "evidence": ""},
    ])
    parsed = _parse_response(not_found, valid)
    check(len(parsed) == 1 and parsed[0].absent, "NOT_FOUND is absent")

    check(_parse_response("", valid) == [], "empty response → empty")
    check(_parse_response("not json at all", valid) == [], "garbage → empty")
    check(_parse_response("```json\n[]\n```", valid) == [], "empty array → empty")

    # Markdown-wrapped response.
    md = '```json\n' + good_response + '\n```'
    parsed = _parse_response(md, valid)
    check(len(parsed) == 2, f"markdown-wrapped JSON → {len(parsed)}")

    # Unknown category filtered.
    unknown = json.dumps([{"category": "FakeCategory", "answer": "x", "evidence": "y"}])
    check(_parse_response(unknown, valid) == [], "unknown category filtered")

    # ── evidence verification ────────────────────────────────────────────
    source = "This Agreement shall be governed by the laws of India. Disputes shall be resolved through arbitration in Mumbai."

    # Exact match.
    start, end, status = _find_span("governed by the laws of India", source)
    check(status == "VERIFIED" and start >= 0, f"exact match → VERIFIED at {start}")
    check(source[start:end] == "governed by the laws of India", "span points at evidence")

    # Too short.
    _, _, status = _find_span("law", source)
    check(status == "UNVERIFIED", f"short evidence → {status}")

    # Empty.
    _, _, status = _find_span("", source)
    check(status == "UNVERIFIED", "empty evidence → UNVERIFIED")

    # Fuzzy match — evidence must overlap a sentence enough to pass Jaccard threshold.
    _, _, status = _find_span(
        "Agreement shall be governed by the laws of India", source)
    check(status in ("VERIFIED", "FUZZY_MATCH"),
          f"high-overlap evidence → {status}")

    # Non-existent.
    _, _, status = _find_span("completely unrelated text about nothing here", source)
    check(status == "UNVERIFIED", f"no match → {status}")

    # ── verify_extractions ───────────────────────────────────────────────
    raw = [
        RawExtraction("Governing Law", "India", "governed by the laws of India", False),
        RawExtraction("Parties", "unknown", "this text does not exist anywhere at all in the source document", False),
        RawExtraction("Agreement Date", "NOT_FOUND", "", True),
    ]
    verified = _verify_extractions(raw, source)
    check(len(verified) == 1, f"1 of 3 raw → {len(verified)} verified")
    check(verified[0].category == "Governing Law", "verified is Governing Law")
    check(verified[0].verification_status == "VERIFIED", "status is VERIFIED")
    check(verified[0].evidence_text in source, "evidence is from source")

    # ── deduplication ────────────────────────────────────────────────────
    ext1 = Extraction("Governing Law", "India", "governed by the laws of India", "India",
                      30, 60, None, "VERIFIED", "PENDING", "", "", PROMPT_VERSION, SCHEMA_VERSION)
    ext2 = Extraction("Governing Law", "India", "governed by the laws of India", "India",
                      2030, 2060, None, "FUZZY_MATCH", "PENDING", "", "", PROMPT_VERSION, SCHEMA_VERSION)
    ext3 = Extraction("Parties", "Acme", "between Acme Corp and Beta", "Acme",
                      5, 30, None, "VERIFIED", "PENDING", "", "", PROMPT_VERSION, SCHEMA_VERSION)
    deduped = _deduplicate([ext1, ext2, ext3])
    check(len(deduped) == 2, f"3 → {len(deduped)} after dedup")
    gl = [e for e in deduped if e.category == "Governing Law"]
    check(len(gl) == 1 and gl[0].verification_status == "VERIFIED",
          "dedup keeps VERIFIED over FUZZY_MATCH")

    # Distinct evidence is kept.
    ext4 = Extraction("Governing Law", "Singapore", "governed by Singapore law", "Singapore",
                      500, 525, None, "VERIFIED", "PENDING", "", "", PROMPT_VERSION, SCHEMA_VERSION)
    deduped2 = _deduplicate([ext1, ext4])
    check(len(deduped2) == 2, "distinct evidence → both kept")

    # ── page resolution ──────────────────────────────────────────────────
    with_pages = _resolve_pages([ext1, ext3], (0, 20, 50))
    check(with_pages[1].page_number == 1, f"offset 5 → page 1 ({with_pages[1].page_number})")
    check(with_pages[0].page_number == 2, f"offset 30 → page 2 ({with_pages[0].page_number})")

    # ── abstention ───────────────────────────────────────────────────────
    all_raw = [
        RawExtraction("Governing Law", "India", "...", False),
        RawExtraction("Parties", "NOT_FOUND", "", True),
        RawExtraction("Parties", "NOT_FOUND", "", True),  # from another window
        RawExtraction("Agreement Date", "2024", "...", False),
        RawExtraction("Agreement Date", "NOT_FOUND", "", True),  # partial NOT_FOUND
    ]
    found, absent = _compute_abstentions(all_raw, ["Governing Law", "Parties", "Agreement Date", "Effective Date"])
    check("Governing Law" in found, "found: Governing Law")
    check("Agreement Date" in found, "found: Agreement Date (some windows had it)")
    check("Parties" in absent, "absent: Parties (all windows NOT_FOUND)")
    check("Effective Date" not in found and "Effective Date" not in absent,
          "never-asked category not in either list")

    # ── extract with no route_fn ─────────────────────────────────────────
    result = extract("some text", route_fn=None)
    check(len(result.extractions) == 0, "no route → no extractions")
    check(len(result.errors) == 0, "no route → no errors")

    # ── extract with mock route_fn ───────────────────────────────────────
    contract = (
        "MUTUAL NON-DISCLOSURE AGREEMENT dated January 15, 2024. "
        "This Agreement is entered into between Acme Corp and Beta Ltd. "
        "The receiving party shall not disclose any confidential information. "
        "This Agreement shall be governed by the laws of India. "
        "Any disputes shall be resolved through arbitration in Mumbai. "
        "The term of this agreement is two years from the effective date.")

    def mock_route(prompt: str) -> str:
        return json.dumps([
            {"category": "Governing Law", "answer": "India",
             "evidence": "governed by the laws of India"},
            {"category": "Parties", "answer": "Acme Corp and Beta Ltd",
             "evidence": "between Acme Corp and Beta Ltd"},
            {"category": "Agreement Date", "answer": "January 15, 2024",
             "evidence": "dated January 15, 2024"},
            {"category": "Confidentiality", "answer": "shall not disclose",
             "evidence": "shall not disclose any confidential information"},
            {"category": "Dispute Resolution", "answer": "arbitration in Mumbai",
             "evidence": "resolved through arbitration in Mumbai"},
        ])

    result = extract(
        contract,
        tag_names=frozenset({"Governing Law", "Confidentiality", "Dispute Resolution"}),
        doc_class="nda",
        route_fn=mock_route,
        model_provider="test",
        model_version="mock-1",
    )
    check(len(result.extractions) > 0, f"mock extraction → {len(result.extractions)} results")
    check(all(e.model_provider == "test" for e in result.extractions), "model provider stamped")
    check(all(e.verification_status in ("VERIFIED", "FUZZY_MATCH") for e in result.extractions),
          "all extractions are verified or fuzzy")
    check("Governing Law" in result.categories_found, "Governing Law found")
    check(len(result.errors) == 0, f"no errors ({result.errors})")

    # ── extract_from_state ───────────────────────────────────────────────
    from checker.pipeline import process
    state = process(contract, doc_id="test_001", name="NDA.pdf")
    updated = extract_from_state(
        state, route_fn=mock_route,
        model_provider="test", model_version="mock-1")
    check("extract" in updated.stages_completed, "extract stage completed")
    check(len(updated.extractions) > 0, f"state has {len(updated.extractions)} extractions")
    check(updated.extraction_route == "test/mock-1", f"route stamped ({updated.extraction_route})")

    # ── route_fn error handling ──────────────────────────────────────────
    def failing_route(prompt: str) -> str:
        raise ConnectionError("model unavailable")

    result = extract(contract, route_fn=failing_route, doc_class="nda",
                     tag_names=frozenset({"Governing Law"}))
    check(len(result.errors) >= 1, f"route error captured ({len(result.errors)} errors)")
    check(len(result.extractions) == 0, "failed route → no extractions")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
