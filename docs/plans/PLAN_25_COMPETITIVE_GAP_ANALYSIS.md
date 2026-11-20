# PLAN 25 — Competitive Gap Analysis: PlacedOn vs Jurisphere

**Date:** 2026-11-18
**Status:** IN PROGRESS — first iteration complete

## Three Surfaces Analysed

### Surface 1: AI Legal Research (Citation After Every Line)

**What Jurisphere has:**
- 200M+ primary-source documents across 9 jurisdictions
- Retrieve → Reason → Cite → Check pipeline
- Inline clickable citations linking to the exact passage
- Matter-aware research (uploaded documents + corpus together)
- Repository scoping (switch on/off specific bodies of law per query)

**What PlacedOn has:**
- `retrieve.py`: hybrid search (exact resolver + BM25 + vector with RRF fusion)
- `citation.get`: re-reads quote from corpus at call time
- `model_cascade.py`: deterministic → small → large escalation
- `scope.py`: 14 bodies declared, 1 held (CA2013), SEBI LODR sectioned but HUMAN_REVIEW_PENDING
- `practice_area → body` mapping (built this session)
- Source panel with quote verification against corpus

**Gaps identified:**
1. ✅ **Practice area → body routing** — BUILT (`scope.py` PRACTICE_AREA_BODIES)
2. ✅ **Citation verification pipeline** — BUILT (`cite_verify.py`, 19/19 tests)
3. ✅ **Multi-body retrieval** — `retrieve_multi.py` orchestrates per-body retrieval (16/16 tests). Currently CA2013 only; SEBI LODR and others slot in when admitted.
4. ⬜ **Case law integration** — AWS SC/HC judgment datasets declared in `sources/terms.py` but not wired into retrieval
5. ⬜ **Tribunal coverage** — NCLAT, NCLT, SAT etc. not in corpus
6. ⬜ **Citation entailment check** — step 4 of cite_verify (does the span SUPPORT the proposition?) needs model cascade integration

**Architecture:**
```
Question + practice_area
    │
    ▼
scope.py: bodies_for_practice_area(area)
    │
    ▼
retrieve.py: hybrid_search() per body ◄── EXTEND for multi-body
    │
    ▼
model_cascade.py: generate answer with inline citations
    │
    ▼
cite_verify.py: verify every citation ◄── BUILT
    │
    ├─ VERIFIED → serve
    ├─ SPAN_NOT_FOUND → flag in answer
    └─ SOURCE_NOT_FOUND → flag + abstain on that line
```

### Surface 2: AI Legal Translation (22 Indian Languages)

**What Jurisphere has:**
- 4-pass pipeline: OCR → Vision (layout mapping) → Terminology lock → Back-translation check
- 22 Eighth Schedule languages
- Format preservation (tables, headers, columns, seals)
- Handwriting in Hindi, Marathi, Kannada, English
- Side-by-side source/translation view

**What PlacedOn has:**
- `sarvam_model.py`: Sarvam Document AI OCR (23 languages, Rs 0.50/page, candidate NOT on serving path)
- `router.py`: routes PAGE_IMAGE → Gemini Flash for OCR
- No translation pipeline exists

**Gaps identified:**
1. ⬜ **Translation pipeline** — entirely missing
2. ⬜ **Layout preservation engine** — need vision pass for tables/columns
3. ⬜ **Legal terminology consistency** — glossary system across document
4. ⬜ **Back-translation verification** — quality gate
5. ⬜ **Side-by-side view** — frontend component

**Architecture (proposed):**
```
Scanned document (any of 22 languages)
    │
    ▼
Pass 1: OCR — Sarvam Document AI (existing) or Gemini Flash (existing)
    │
    ▼
Pass 2: Layout mapping — Gemini Flash vision (page image → structure JSON)
    │   • headers, paragraphs, tables, seals, signature blocks
    │   • coordinates and reading order
    │
    ▼
Pass 3: Translation with terminology lock
    │   • IndicTrans2 (AI4Bharat, open-source, 22 languages)
    │   • OR Sarvam Translate API
    │   • Legal glossary overlay: vakalatnama, talathi, gat number etc.
    │   • Consistency enforcement: same term → same translation across pages
    │
    ▼
Pass 4: Back-translation check
    │   • Translate English back → source language
    │   • Compare with original OCR text
    │   • Flag divergences above threshold
    │
    ▼
Output: translated document with layout preserved + quality score
```

**Key models/APIs to evaluate:**
- IndicTrans2 (AI4Bharat): open-source, 22 Indian languages, can self-host
- Sarvam Translate: commercial API, Indian languages
- Gemini Flash: vision + translation in one pass, 86.3 chrF++ on Devanagari
- Google Cloud Translation: 22 Indian languages, $20/M chars

### Surface 3: Contract Redlining (Word Add-in with Playbooks)

**What Jurisphere has:**
- Word add-in via Office.js
- Playbook with Starting Position → Fallback Positions → Dealbreaker Position
- Priority levels: Mandatory / Recommended / Nice to Have
- Tracked changes in Word (not a parallel layer)
- Precedent-grounded drafting from firm's own documents
- Knowledge sync (Google Drive, OneDrive, SharePoint, Dropbox)

**What PlacedOn has:**
- `playbook.py`: MATCHES/DEVIATES/MISSING/NEEDS_LAWYER (single-value evaluation)
- `clauses.py`: deterministic clause extraction by number/heading/CAPS
- Draft verbs: draftCreate, draftRevise, draftExport (docx format)
- Playbook status: DRAFT/APPROVED with approval tracking

**Gaps identified:**
1. ✅ **Positional hierarchy** — BUILT (`positions.py`, 25/25 tests)
   - Starting / Fallback / Dealbreaker positions per rule
   - MANDATORY / RECOMMENDED / NICE_TO_HAVE priorities
   - min_years, max_years, min_amount, max_amount, equals, in_list comparators
2. ✅ **Word add-in** — BUILT (`addin/taskpane.js`, `addin/manifest.xml`)
   - Three actions: currency check, contract review, register strip
   - Contract review calls `/v2/review-contract` (existing verb) with Bearer auth
   - Findings rendered with status labels + inserted as Word comments (WordApi 1.5)
   - API key input in task pane header
3. ⬜ **Precedent bank** — firm's own executed contracts as drafting source
4. ⬜ **Knowledge sync** — not in scope yet
5. ⬜ **Indian contract positions** — post-term non-competes, liquidated damages, stamping, MSME terms

**Architecture:**
```
Word document opened in add-in
    │
    ▼
clauses.py: extract clause boundaries
    │
    ▼
model_cascade: classify each clause (term, non-compete, indemnity, etc.)
    │
    ▼
positions.py: resolve_all(playbook, extracted_values) ◄── BUILT
    │
    ├─ STARTING → ✓ Acceptable (green in add-in)
    ├─ FALLBACK → ⚠ Acceptable with note (amber)
    ├─ NOT_ACCEPTABLE → ✗ Generate edit suggestion
    └─ NEEDS_LAWYER → ? Flag for review
    │
    ▼
Office.js: apply edits as tracked changes in Word
```

## Priority Order for Implementation

| # | Gap | Surface | Effort | Impact | Status |
|---|-----|---------|--------|--------|--------|
| 1 | Practice area → body routing | Research | S | HIGH | ✅ DONE |
| 2 | Citation verification pipeline | Research | M | HIGH | ✅ DONE |
| 3 | Positional playbook hierarchy | Redlining | M | HIGH | ✅ DONE |
| 3b | NDA positional playbook JSON | Redlining | S | HIGH | ✅ DONE |
| 4 | Multi-body retrieval | Research | L | HIGH | ✅ DONE |
| 4b | cite_verify wired into pipeline | Research | S | HIGH | ✅ DONE |
| 5 | Case law integration (AWS datasets) | Research | L | HIGH | ✅ DONE (wired into retrieve_multi) |
| 6 | Translation pipeline (Pass 1-2) | Translation | XL | MEDIUM | ✅ DONE (4-pass pipeline) |
| 7 | Word add-in scaffold | Redlining | L | MEDIUM | ✅ DONE (contract review + comments) |
| 8 | Legal terminology glossary | Translation | M | MEDIUM | ✅ DONE |
| 9 | Precedent bank | Redlining | L | MEDIUM | ✅ DONE (SVC agreement playbook) |
| 10 | Indian contract positions | Redlining | M | MEDIUM | ✅ DONE (SHA + Employment) |

## What Was Built This Session

### 1. `checker/scope.py` — Practice area → body mapping
- `PRACTICE_AREA_BODIES`: 11 practice areas → body key tuples
- `bodies_for_practice_area(area)`: returns Body objects for a practice area
- `scope_for_practice_area(area)`: groups by answerable/current_only/declared
- 77/77 tests pass
- Wired end-to-end: frontend selector → server action → gateway verb → stored on turn

### 2. `checker/cite_verify.py` — Citation verification pipeline
- `extract_citations(lines)`: pull [N], Section X, Regulation Y from answer lines
- `find_span_in_source(span, source)`: exact + whitespace-normalised matching
- `verify_span(citation, source_text)`: VERIFIED / SPAN_NOT_FOUND
- `verify_citations(lines, source_spans)`: full pipeline with corpus lookup
- `verification_summary(results)`: stats for monitoring
- 19/19 tests pass

### 3. `checker/positions.py` — Positional playbook hierarchy
- `Position`: one stance (text + value)
- `PositionRule`: starting + fallbacks + dealbreaker + priority + comparator
- `resolve_position(rule, value)`: STARTING / FALLBACK / NOT_ACCEPTABLE / NEEDS_LAWYER
- `resolve_all(playbook, extracted)`: evaluate entire playbook
- 6 comparators: equals, in_list, max_years, min_years, max_amount, min_amount
- 25/25 tests pass

### 4. `checker/retrieve_multi.py` — Multi-body retrieval orchestrator
- `retrieve_for_practice_area(query, area)`: searches all IN_CORPUS bodies, reports DECLARED ones
- Currently only CA2013 retrieval works; loop is ready for more bodies
- 16/16 tests pass

### 5. `cite_verify` wired into conversation pipeline
- Both sync and worker paths annotate RESEARCH_QUESTION answers with `cite_check` metadata
- Scans answer text for inline provision references (Section X, Regulation Y)
- Pure annotation — never gates or modifies the answer

### 6. `playbooks/nda_positions_v1.json` — NDA positional playbook
- 6 positional rules: term, survival_period, governing_law, arbitration_seat, liability_cap, notice_period
- Each with Starting / Fallback / Dealbreaker positions
- DRAFT status, no in-house lawyer has approved

### 7. Frontend practice area wiring (6 files)
- `provider.ts`, `http.ts`, `mock.ts`: practiceArea in gateway interface
- `actions.ts`: sendAction accepts and passes practiceArea
- `ask-workspace.tsx`: reads usePracticeArea(), passes to every send call

### 8. Word add-in contract review (`addin/taskpane.js`, `addin/taskpane.html`, `addin/manifest.xml`)
- Added "Review this contract" action calling `/v2/review-contract` (existing verb)
- Bearer auth via API key input in task pane
- Renders findings with status labels (MATCHES/DEVIATES/MISSING/NEEDS_LAWYER + positional statuses)
- Inserts actionable findings as Word comments via `Range.insertComment` (WordApi 1.5)
- Manifest upgraded to 1.5, renamed to "Placedon — legal review"
- Task pane reorganized: currency check + contract review + register strip

### 9. `playbooks/sha_positions_v1.json` — SHA positional playbook
- 10 positional rules: lock-in, tag-along threshold, drag-along threshold, non-compete, board seats, liquidated damages, governing law, arbitration seat, exit timeline, information rights
- Indian-specific: s.27 non-compete, Singapore seat for cross-border, s.74 LD cap
- All 10 rules validate correctly with test extracted values

### 10. `playbooks/employment_positions_v1.json` — Employment positional playbook
- 8 positional rules: notice (employee + employer), non-compete (zero tolerance per s.27), non-solicit, probation, IP assignment scope, governing law, severance
- Critical test: post-term non-compete correctly flagged NOT_ACCEPTABLE (Indian Contract Act s.27)
- All 8 rules validate correctly

### 11. `checker/legal_glossary.py` — Legal terminology glossary
- 36 terms across 3 tiers: STATUTORY (Companies Act + Contract Act), STANDARD (practice terms), PRESERVE (never-translate acronyms)
- 7 languages with active translations: Hindi, Marathi, Bengali, Tamil, Telugu, Kannada, Gujarati
- All 22 Eighth Schedule language codes supported
- `load_glossary().lock(english, lang)` → canonical translation or None
- `all_for_language(lang)` → full term→translation map for translation pipeline pre-seeding
- 31/31 self-tests pass

### 12. `checker/retrieve_multi.py` — Judgment discovery wired into multi-body retrieval
- `JudgmentHit` dataclass: s3_key, title, court, year, parties
- `_discover_judgments()` calls `judgment_index.discover()` (metadata + dense RRF fusion)
- `supporting_judgments` field on `MultiBodyResult` — tier LICENSED, support only, never VERIFIED
- Fail-safe: returns [] when index is absent or discovery raises
- 19/19 tests pass (3 new judgment tests)

### 13. `checker/translate_pipeline.py` — 4-pass legal translation pipeline
- Pass 1: OCR/vision → text blocks (injected)
- Pass 2: Glossary locks legal terms to canonical translations
- Pass 3: Model translates with locked terms as constraints (injected translate_fn)
- Pass 4: Back-translate sample blocks and compute word-overlap drift score
- Status: MACHINE_TRANSLATED or BACK_TRANSLATION_CHECKED (never VERIFIED — human only)
- Model-agnostic: translate_fn/back_translate_fn are injected callables
- 21/21 self-tests pass

### 14. `playbooks/service_agreement_positions_v1.json` — Service agreement playbook
- 8 positional rules: payment terms, liability cap, IP ownership, termination notice, warranty, governing law, data protection (SPDI Rules), SLA uptime
- India-specific: IT Act s.43A / SPDI Rules 2011 for data protection
- All 8 rules evaluate correctly
