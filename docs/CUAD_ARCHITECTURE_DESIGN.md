# CUAD Architecture Design

## System Context

```
                    vault_ingest.py
                         │
                         ▼
                  ┌──────────────┐
                  │  pipeline.py │  (existing)
                  │  Stages 1-5  │
                  └──────┬───────┘
                         │
              Stage 1: classify (rule-based)
              Stage 2: tag_clauses (rule-based)
              Stage 3: extract ◄── cuad_extractor.py (NEW)
              Stage 4: summarize (TextRank)
              Stage 5: dedup_check (MinHash)
                         │
                         ▼
                  DocumentState
                  (immutable, frozen dataclass)
```

## Component Design

### 1. `checker/sanitize.py` (NEW)

Implements SANITIZATION_SPEC.md stages A–F. Stateless functions.

```python
# Public API
def validate_file(data: bytes, name: str, mime: str) -> FileValidation
def normalize_text(text: str) -> NormalizedText
def detect_structure(text: str, page_boundaries: tuple[int, ...] | None) -> DocumentStructure
def detect_sensitive(text: str) -> SensitiveDataMap
def scan_injection_markers(text: str) -> list[str]
```

**Dependencies:** None beyond stdlib. No model calls.

### 2. `checker/cuad_categories.py` (NEW)

The frozen 41-category registry. Data only, no logic.

```python
@dataclass(frozen=True)
class Category:
    name: str
    question: str
    answer_type: str  # "entity", "date", "boolean", "span"
    description: str

CATEGORIES: dict[str, Category] = { ... }  # 41 entries
```

**Dependencies:** None.

### 3. `checker/cuad_extractor.py` (NEW)

The extraction stage. Implements algorithms 1–7 from CUAD_ALGORITHM_SPEC.md.

```python
@dataclass(frozen=True)
class Extraction:
    category: str
    quoted_text: str
    start: int
    end: int
    status: str              # "VERIFIED" | "FUZZY_MATCH"
    page: int | None
    normalized_value: str
    model_version: str

def extract(state: DocumentState, *, route_fn) -> DocumentState:
    """CUAD extractive QA. route_fn calls router.route() for model access."""

# Internal functions (all pure, all tested)
def _windows(text: str) -> list[Window]
def _select_categories(tags: tuple[Tag, ...], doc_class: str) -> list[str]
def _build_prompt(window: Window, categories: list[str]) -> str
def _parse_response(response: str) -> list[RawExtraction]
def _verify_extractions(raw: list[RawExtraction], text: str) -> list[VerifiedExtraction]
def _deduplicate(extractions: list[VerifiedExtraction]) -> list[VerifiedExtraction]
def _normalize_values(extractions: list[VerifiedExtraction], text: str) -> list[Extraction]
```

**Dependencies:** `checker.cuad_categories`, `checker.clause_tags` (for TAGS and
MIN_QUOTE), `checker.pipeline` (for DocumentState).

### 4. `checker/sanitize.py` → `checker/cuad_extractor.py` boundary

The sanitizer runs BEFORE the pipeline. The extractor receives already-sanitized
text via `DocumentState.text`. The extractor does NOT call the sanitizer — that
separation is enforced by the caller (`vault_ingest.py` or `pipeline.py`).

```
vault_ingest.py:
    1. sanitize.validate_file(data, name, mime)  → reject or proceed
    2. extract_text(data)                         → raw text
    3. sanitize.normalize_text(raw)               → NormalizedText
    4. sanitize.detect_sensitive(normalized)       → SensitiveDataMap
    5. pipeline.process(normalized, ...)           → DocumentState (stages 1,2,4,5)
    6. cuad_extractor.extract(state, route_fn=...) → DocumentState with extractions
```

## Router Integration

The extractor calls the model through a `route_fn` parameter, never directly.

```python
def _default_route_fn(prompt: str) -> str:
    """Route through the existing router for EXTRACTION/HIGH."""
    from checker import router
    task = router.Task(
        name="cuad_extract",
        modality=router.TEXT,
        consequence=router.HIGH,
        purpose=router.EXTRACTION,
    )
    route = router.route(task)
    # Dispatch to the provider returned by route
    if route.provider == router.MISTRAL:
        from checker import mistral_model
        return mistral_model.generate(prompt, deployment=route.model,
                                      max_tokens=mistral_model.LARGE_BUDGET)
    elif route.provider == router.AZURE:
        from checker import azure_model
        return azure_model.generate(prompt, deployment=route.model)
    # ... other providers per existing router table
    raise router.NoRoute(f"unhandled provider {route.provider}")
```

**Key design decisions:**
- `route_fn` is injected so tests can mock it without touching the router
- The extractor never imports a model adapter directly
- If no route is available (NoRoute), the extraction stage is skipped, not failed
- `requires_review` from the route is propagated to the extraction output

## Failure Handling

| Failure | Behavior |
|---------|----------|
| No model route available | Skip extraction, return state unchanged |
| Model returns malformed JSON | Zero extractions for that window, error logged |
| Model timeout | Zero extractions for that window, error logged, retry once |
| All extractions UNVERIFIED | Zero verified extractions, logged as model quality issue |
| Sanitization rejects file | File not processed at all |

**Retry policy:** One retry per window on timeout or HTTP 5xx. No retry on
content filter (ModelRefused) or rate limit (back off and skip).

## Data Flow

```
Input:
    DocumentState(
        doc_id="contract_001",
        text="MUTUAL NDA... [40,000 chars]",
        doc_class="nda",
        tags=(Tag("Confidentiality", ...), Tag("Governing Law", ...), ...),
        extractions=(),         # empty before this stage
        extraction_route="",    # empty before this stage
    )

Processing:
    windows = _windows(text)                           # ~19 windows
    categories = _select_categories(tags, doc_class)   # ~35 categories
    for window in windows:
        prompt = _build_prompt(window, categories)
        response = route_fn(prompt)                    # model call
        raw = _parse_response(response)                # structured
        verified = _verify_extractions(raw, text)      # PLAN_23 gate
    all_extractions = _deduplicate(flatten(verified))
    final = _normalize_values(all_extractions, text)

Output:
    DocumentState(
        ...,
        extractions=(
            {"category": "Governing Law", "value": "laws of India",
             "quote": "This Agreement shall be governed by the laws of India.",
             "start": 12450, "end": 12503, "status": "VERIFIED",
             "page": 8, "model": "mistral-large-4"},
            {"category": "Cap on Liability", "value": "INR 10,00,000",
             "quote": "In no event shall liability exceed INR 10,00,000.",
             "start": 8720, "end": 8770, "status": "VERIFIED",
             "page": 5, "model": "mistral-large-4"},
            ...
        ),
        extraction_route="mistral/mistral-large-4",
    )
```

## Tenant and Matter Permissions

The extractor has no concept of tenants or matters — it operates on text. Access
control is enforced at the vault layer:

1. `vault_ingest.py` checks matter permissions before calling the pipeline
2. `gateway/jobs.py` enforces tenant isolation at the job level
3. The extractor receives a `doc_id` that the vault maps to a tenant/matter
4. Model calls go through the router, which does not carry tenant context (the
   model sees text, not metadata)
5. Results are stored via the vault's existing persistence layer, which enforces
   row-level security

**Invariant:** The extractor never reads from or writes to the database. It
receives text and returns structured data. Persistence is the caller's job.

## Persistence

Extractions are stored as `vault_extractions` rows (new table, migration TBD):

```sql
CREATE TABLE vault_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES vault_documents(id),
    category TEXT NOT NULL,
    quoted_text TEXT NOT NULL CHECK (length(quoted_text) >= 8),
    start_offset INT NOT NULL CHECK (start_offset >= 0),
    end_offset INT NOT NULL CHECK (end_offset > start_offset),
    page_number INT,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED', 'FUZZY_MATCH')),
    normalized_value TEXT,
    model_version TEXT NOT NULL,
    processing_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Invariant:** The CHECK constraints mirror the sanitization spec — a row that
would fail sanitization cannot be stored.

## Evidence Traceability

Every extraction carries:
- `document_id` → which document
- `start_offset`, `end_offset` → where in the document
- `page_number` → which page (if available)
- `quoted_text` → what the model found (verbatim from document)
- `model_version` → which model produced it
- `processing_version` → which code version processed it

A reader can verify any extraction by: `document.text[start:end] == quoted_text`.
