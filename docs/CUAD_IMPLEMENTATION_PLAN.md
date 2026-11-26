# CUAD Implementation Plan

## Execution Sequence

Each stage is independently verifiable. No stage depends on a live model.

---

## Stage 1: Sanitization and Source Provenance — COMPLETE

**File:** `checker/sanitize.py` (32 tests)
**Dependencies:** stdlib only

Mandatory boundary before model processing. Six controls:
- A. File validation (size ≤ 50MB, MIME whitelist, file signatures)
- B. Text normalization (BOM, Unicode NFC, control chars, whitespace)
- C. Structure preservation (pages, paragraphs, spans with offsets)
- D. Sensitive data detection (PAN, Aadhaar, email, phone — record, never strip)
- E. Prompt-injection marker scanning (6 patterns)
- F. Transformation traceability (every transform logged)

---

## Stage 2: CUAD Question Templates — COMPLETE

**File:** `checker/cuad_categories.py` (79 tests)
**Dependencies:** stdlib only

- 41 CUAD categories (indices 1–41, matching the paper appendix exactly)
- 10 India-specific extensions (Stamp Duty, Arbitration Seat, Companies Act Reference,
  SEBI Compliance, Indemnification, Confidentiality, Representations And Warranties,
  Conditions Precedent, Payment Terms, Dispute Resolution)
- 51 total categories, 5 answer types (entity, date, boolean, span, currency)
- `_TAG_TO_CATEGORIES` maps all 13 regex tagger tags to CUAD category names
- `_ALWAYS_ASK`: 8 categories always extracted regardless of tag detection
- `select_categories()`: picks categories based on detected tags + doc_class

---

## Stage 3–5: Extraction, Verification, Abstention — COMPLETE

**File:** `checker/cuad_extractor.py` (49 tests)
**Dependencies:** `checker.cuad_categories`, `checker.clause_tags`, `checker.pipeline`

- **Windowing:** 6000-char windows, 2000-char stride, character-level
- **Prompt construction:** per-window, includes selected category questions
- **Response parsing:** JSON extraction with markdown fence stripping, unknown category filtering
- **Span verification:** exact match → VERIFIED, Jaccard fuzzy → FUZZY_MATCH, below threshold → dropped
- **Cross-window deduplication:** Jaccard 0.8 threshold, keeps better verification status
- **Page resolution:** maps offsets to page numbers from explicit boundaries
- **Abstention:** category absent only if ALL windows report NOT_FOUND
- **Model injection:** `route_fn` callable, never imports model adapters directly
- **NoRoute handling:** extraction skipped (not failed) when no model available

---

## Stage 6: Obligation Extraction (LexDeMod) — COMPLETE

**File:** `checker/obligation_extractor.py` (25 tests)
**Dependencies:** stdlib only (operates on extraction evidence text)

Deterministic Python — no model calls. Operates on evidence already extracted
and verified by cuad_extractor.

- Deontic modality classification: obligation / prohibition / permission
- Party extraction via regex (22 role patterns + PascalCase Corp/Ltd/Inc)
- Action extraction from post-trigger verb phrase
- Deadline detection (numeric and word-form, business/calendar/working days)
- Condition and exception extraction
- Each obligation links to source category and evidence sentence

---

## Stage 7: Bake-off Framework — COMPLETE

**File:** `scripts/bakeoff_cuad.py` (25 tests)
**Dependencies:** stdlib only

PLAN_22 D2 enforcement: the script measures, a person decides. It CANNOT
modify `checker/router.py`.

- Metrics: Exact Match, Token F1, Evidence Precision, Evidence Recall,
  Unsupported Rate, Abstention Precision, JSON Validity Rate
- Bootstrap CI: 1000 resamples, seeded for reproducibility
- Comparison: PROMOTE (non-overlapping CI, all thresholds met),
  HOLD (CIs overlap or incumbent retains), FAIL (below thresholds)
- Report: JSON with per-provider results, CI bounds, latency, cost
- `decided_by` field always set to "pending human review"

Existing `scripts/bakeoff_models.py` covers the general model bake-off;
`bakeoff_cuad.py` adds CUAD-specific metrics (evidence precision, span
verification rates, abstention accuracy).

---

## Stage 8: Pipeline Integration — COMPLETE

**File:** `checker/cuad_pipeline.py` (16 tests)
**Dependencies:** `checker.sanitize`, `checker.pipeline`, `checker.cuad_extractor`,
`checker.obligation_extractor`

Full pipeline: sanitize → classify → tag → extract → obligations.

- Sanitization boundary enforced before any model processing
- Injection markers detected and logged as errors
- Sensitive data counted but not stripped
- Classification and tagging via existing deterministic pipeline
- CUAD extraction via injected `route_fn` (skipped if None)
- Obligation extraction from verified evidence (deterministic)
- Returns `CUADResult` with all outputs, errors, and provenance

**Integration with vault_ingest.py:** `cuad_pipeline.py` exists alongside
`vault_ingest.py` without modifying it. The call site is a one-line addition
when the team decides where extraction triggers (post-ingest, on-demand, or
background job).

---

## Files Created

| File | Stage | Tests | Description |
|------|-------|-------|-------------|
| `checker/sanitize.py` | 1 | 32 | Sanitization boundary |
| `checker/cuad_categories.py` | 2 | 79 | 51-category registry (41 CUAD + 10 India) |
| `checker/cuad_extractor.py` | 3–5 | 49 | Extraction, verification, abstention |
| `checker/obligation_extractor.py` | 6 | 25 | LexDeMod obligation extraction |
| `scripts/bakeoff_cuad.py` | 7 | 25 | CUAD bake-off framework |
| `checker/cuad_pipeline.py` | 8 | 16 | Full pipeline integration |
| **Total** | | **226** | |

## Deferred or Cancelled Items

- **LangChain wrappers** — cancelled; LangChain is forbidden by the directive.
- **Research memo template** — deferred; extraction output is the deliverable for now.
- **Client email template** — deferred; same as above.

## Implementation Order (actual)

```
Stage 1 ──► Stage 2 ──► Stage 3–5 ──► Stage 6 ──► Stage 7
  │                                                   │
  └──────────────────────────────────► Stage 8 ◄──────┘
```

Stages 1–2 were built first (data-only, no model calls). Stages 3–5 were
combined into one file (`cuad_extractor.py`). Stage 6 (obligations) is
deterministic post-processing. Stage 7 (bake-off) is independent. Stage 8
(pipeline integration) ties everything together.
