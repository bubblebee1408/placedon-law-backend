# PLAN_12 — document intake: F8 Bulk Document Review and role 13 (OCR + layout)

Written 2026-09-14. This is the Track A architecture that [PLAN_11](PLAN_11_NEXT_MOVE.md) §2 requires. Three
independent drafts were written (abstention-first, scale-first, residency-first) and scored by three judges. The
abstention-first draft won. This document is that draft, plus the ideas the judges named from the other two, minus
the flaws the judges named in all three.

**Summary.** A ~500-page scheme bundle or an Ind AS annual report enters as bytes. It is hashed, scanned and split
into pages identified by `(file_sha256, pdf_page_index)`. Each page is read and triaged by whether its text can be
trusted. The bundle is segmented into its component documents *before* anyone decides what type they are or which
law applies. Values are extracted per segment, and the gates that already exist decide whether a value is served.
In the table, every cell starts ABSTAINED. A cell is served only when every stage between the bytes and the value
has recorded a positive reason to trust it. A refusal always names its file and, wherever one exists, its PDF page.
Nothing here is buildable as a product until the [PLAN_05](PLAN_05_ROADMAP.md) 20-document test runs and the
blocking research gaps close. §10 lists what can be built now. G01 is the founder's decision between durable state
for bulk review and PLAN_07's rule that client documents are never stored durably. §7 designs both branches and
chooses neither.

| Layer | BUILT today (read 2026-09-14) | DESIGNED here, NOT BUILT | BLOCKED on |
|---|---|---|---|
| Span presence, value-support (empty value and CIN shape refused), field binding (money, text, date) | `reasoning.review`, `document_extract.value_supported_by_span`, `field_binding.check` | Per-page offsets for these gates (§3.11 f) | — |
| Declared-date check; bounded correction | `orchestrator._against_declared_date` (`DOCUMENT_DATE_CONFLICT`); `MAX_CORRECTIONS = 1` | One human-declared date per segment (§3.10) | — |
| Provenance typing; human approval | `provenance_slots.py`; approval raises on `MODEL_SUGGESTION`/`UNKNOWN` | A `DOCUMENT_SPAN` kind (§3.12 j) | — |
| Scope refusal | `scope.py` `BODIES`, `refusal_for` | `SEGMENT_BODY` map (§3.9) | G03 for any verification of FS or CAA-rule checks |
| Session store; release guard | `session.Session`, `session.releasable()` | `[C]` field tagging and the two queue backends (§3.1, §7) | G01 for the durable backend |
| Native text per page | `pdf_text.extract_pages` (ToUnicode maps) — **built, but MEASURED failing on modern PDFs**: agrees with pdfplumber on 0 of 14 corpus files (1 page for a 169-page file, 0 for 179); `scripts/text_layer_census.py`, commit `9010605`. Whole-document `extract_text` works | Two-enumerator page check, triage (§3.3, §3.4) | **D-002** — reader decision (fix the stdlib parser, or adopt a PDF library as a stated new dependency) |
| Signatures; calibration refusal; shadow metric; review items | `pdf_signature`, `calibration_contract.assess`, `shadow.py`, `review_queue` (`page_start`/`page_end`) | Page flags, OCR gate, F8 metric, cell review (§3.5, §3.12, §3.13) | G04, G05, G06, G19 |
| OCR tier, layout, segmentation, cell table, provider registry | — | §3–§5 | G04, G05, G06, G08, G10, G12, G16, G17 |
| Any tenant document in the pipeline | — | — | G01, G17 (intake); G02 (extraction); G04, G16 (OCR) |
| F8 shown to a lawyer | — | — | 20-document test; PLAN_05 Phase 0 falsifier |

**Markers** (as in [PLAN_00](PLAN_00_INDEX.md)): **BUILT** means the code exists and was read on 2026-09-14.
**MEASURED** means measured in a named research file. **SOURCED** means carried from a research row whose ID is
given. **INFERRED** is our reasoning or arithmetic. **UNVERIFIED** means not established. **BLOCKED** means it cannot
be built or claimed until a named gate closes.

**Row IDs.** "R4 G3" is row G3 of the file listed below. "R1 item 4" is item 4 of that file's "What this means for
PLAN_12" list. "G01"–"G24" are gaps in the gaps file.
- R1 [`HARVEY_DOCUMENT_INTAKE.md`](research/HARVEY_DOCUMENT_INTAKE.md)
- R2 [`SPELLBOOK_DOCUMENT_INTAKE.md`](research/SPELLBOOK_DOCUMENT_INTAKE.md)
- R3 [`SARVAM_DOCUMENT_AI.md`](research/SARVAM_DOCUMENT_AI.md)
- R4 [`DOCUMENT_AI_PROVIDERS_INDIA.md`](research/DOCUMENT_AI_PROVIDERS_INDIA.md)
- R5 [`LARGE_DOCUMENT_PROFILE.md`](research/LARGE_DOCUMENT_PROFILE.md)
- G [`RESEARCH_GAPS_2026_09_14.md`](research/RESEARCH_GAPS_2026_09_14.md)

---

## 1. Thesis

1. **A cell starts abstained.** It is served only when every stage has recorded a positive reason to trust it. A
   wrong cell carries our authority. An abstained cell that names a page sends the lawyer to that page. The failure
   this design refuses to reproduce is **silence that reads as absence**. R2 B7: Spellbook accepts a scanned PDF
   and then cannot reference its content. R2 B13: no page describes a warning.
2. **Refusals flow down and are never averaged up.**
   - A page refusal abstains every cell whose evidence touches that page.
   - A segment refusal abstains every cell in that segment.
   - Nothing is scored "mostly readable" at file level.
3. **An absence claim needs full coverage and measured recall.** Silence from an extractor is not evidence of
   absence. A cell may be `NOT_FOUND` only when (a) every page *and every region* of its segment was read and
   trusted, (b) extractor recall for that column family has been measured on a labelled set (`RECALL_THRESHOLD =
   None` today, so `NOT_FOUND` is **unreachable**, the same way `THRESHOLD = None` keeps the OCR gate closed), and
   (c) at least two independent extractors both made no proposal. Until then the cell is
   `ABSTAINED(ABSENCE_UNVERIFIABLE, pages_read)`, or `ABSTAINED(COVERAGE_INCOMPLETE, unread pages)` when (a) fails.
   `NOT_FOUND` never feeds a "missing required information" result in gate k (§3.11).
4. **Models propose at four points and decide none.**
   - The four points: OCR readings from a generative reader, segment boundaries, segment types, field values.
   - Deterministic gates decide at each point.
   - Applicability stays in `obligations.py` and `scope.py` (PLAN_01: zero model decisions).
5. **A text layer is not trusted until it is measured.** R5 E-C found corrupted text layers on pages that look
   born-digital, and the heuristic missed two of them (R5 C-4). `NATIVE_TRUSTED` cannot be reached until
   native-vs-OCR agreement has been measured (G05).
6. **No number is invented.** Every gate that needs a threshold ships with `THRESHOLD = None`, a defined signal and a
   named measurement. A gate with no threshold fails closed.
7. **Residency and retention belong to an account, a region and a contract, not to a provider** (R3 H7–H11; R4
   G1–G7; G16). They are checked at call time, twice: every eligibility field must be SOURCED or contract-backed
   (marker check), **and** every value must satisfy the tenant policy (value check, §5.2). A SOURCED value that is
   itself disqualifying ("outside India", "trains unless opted out") refuses. Any UNVERIFIED eligibility field
   disables an adapter for tenant documents, and the rule applies to every component that receives file bytes, page
   images, text or hashes, the malware scanner included, without exception.
8. **Throughput never weakens a gate, and never widens exposure.** Local deterministic work may run before its
   inputs are final; a cell is never released before they are, and no provider receives content before its segment
   is final (§3.1).

**Cost of the lens.** One local, non-networked OCR reading per text-layer page for the native-layer check; two OCR
readings only on `NO_TEXT` and `NATIVE_UNTRUSTED` pages; and a second extraction witness on money, date and
identifier columns (priced in §9). Today every tenant page also abstains, because no OCR or
extraction adapter is tenant-eligible (§5.3). That is the state of the evidence, not a defect of the design.

---

## 2. Size envelope

| Input | Value | Marker |
|---|---|---|
| Largest files measured | A1: 512 pages, 19.0 MB. B1: 466 pages, 39.4 MB | MEASURED (R5 E-A) |
| Design envelope per file | ≥600 pages and ≥40 MB. The caps are config values that must not be set below this | INFERRED (R5 "What this means", size envelope, itself marked INFERRED; derived from MEASURED A1 512 pp and B1 39.4 MB) |
| Image-only pages | 106 of 512 (20.7%) in A1: pp.98–146, 207–210, 221–222, 273–294, 433–444, 494–503, 506–512 | MEASURED (R5 E-A, E-B, C-5) |
| Text layer present but corrupted | ≥17 pages in A1 (pp.445, 460–473, 493, 505), a lower bound | MEASURED (R5 C-1–C-4) |
| Components per bundle | 14 in A1; FS and results are 52.5% of pages | MEASURED (R5 E-B) |
| Scan resolution | Most A1 scanned blocks ≈85–95 dpi | MEASURED px, INFERRED dpi (R5 C-5) |
| Two-up spreads | 130 of 466 B1 pages | MEASURED (R5 E-2) |
| Documents per matter; private documents; recent bundles | — | UNVERIFIED (G08; R5 F-3). Every figure above is n=1 per type |

---

## 3. Pipeline

```
S0 intake → S1 hash/sniff/safety → S2 pages → S3 text-layer triage → S4 OCR tier → S5 layout/tables
  → S6 segmentation → S7 type → S8 scope → S9 extraction → S10 gates → S11 cells → S12 human review
```

### 3.1 Execution model

Grafted from the scale-first draft. Every mechanism below is INFERRED design, and none is BUILT.

**Content-addressed stage keys.**
```
page_key      = (file_sha256, pdf_page_index)                         # identity; citations use this
page_work_key = sha256(stage ‖ stage_version ‖ page_content_sha256 ‖ provider ‖ model_version ‖ region ‖ config)
segment_key   = sha256(file_sha256 ‖ first_page ‖ last_page ‖ Σ page final-state hashes ‖ segmenter_version)
cell_key      = sha256(segment_key ‖ column ‖ extractor ‖ model_id ‖ prompt_hash ‖ gate_chain_version ‖ declared_date_ref)
value_key     = sha256(cell_key ‖ value_citation.file_sha256 ‖ pdf_page_index ‖ char_start ‖ char_end ‖ text_of_record_id ‖ proposal_sha256)
```
- **Deterministic stages** (hashing, enumeration, pre-filter, local OCR with a pinned engine, deterministic candidates):
  re-running under the same key does nothing. When an upstream result changes, its key changes, so every result
  built on the old key becomes unreachable.
- **Model stages are not idempotent under a fixed key.** An LLM extraction with the same model and prompt can return
  a different value. A model stage therefore records every run under `(cell_key, run_id)` with its
  `proposal_sha256`, and a second run that differs is recorded as run nondeterminism, never silently replaced. The
  key never freezes the first answer.
- **Attestations bind to `value_key`, not `cell_key`** (§3.13). A prior attestation whose `value_key` differs from the
  current cell's is never displayed as applying to it.
- `page_content_sha256` deduplicates work only. It never appears in a citation, and it is never shared across
  tenants (§7).

**Speculation without release, and without exposure.**
- Local deterministic stages (candidate boundaries, heading match, deterministic proposers) may run while some pages
  are still pending.
- **No provider call is made on content before it is needed.** An extraction or classification call to any provider
  requires a segment whose boundaries are `ESTABLISHED`, whose `permitted ≠ NONE`, and all of whose pages have final
  routes with no `INJECTION_SUSPECT` hold unresolved. Speculation exists for latency, and it never sends a range to a
  provider that may resolve to `UNKNOWN` or `NONE`.
- A segment stays `PROVISIONAL` while any of its pages, or a boundary neighbour, is pending. Example: A1's scheme
  text is native, but p.98 is scanned (R5 E-B).
- A cell stays `HELD` until its `segment_key` is final and its segment's date has been declared (§3.10).
- Local speculation is switched off when the matter budget is tight.

**Lanes and backpressure.**
- One queue lane per stage, so an OCR-heavy bundle does not starve text-layer documents (R1 A19).
- One token bucket per `(provider, account, region)`, filled from the registry row (§5), with a per-tenant quota
  inside it, so one tenant's 512-page bundle cannot exhaust a shared provider limit (Sarvam 10 req/min, R3 E11) for
  every tenant.
- Provider-side retention and training settings belong to the account (Sarvam: per workspace, changes not
  retroactive, R3 H4). On a shared account the setting in force must be the **strictest** any tenant on it requires;
  where tenants require different settings, accounts are keyed per tenant. Which of the two is used is a cost
  decision, OPEN.
- A partial provider result maps to per-page results: Textract `PARTIAL_SUCCESS` (R4 D2), Azure batch per-document
  `failed` (R4 D5), Sarvam `partially_completed` (R3 E6).
- A failed page is retried once, on its own, and then abstains. One retry mirrors `MAX_CORRECTIONS = 1`.

**Budget pre-flight.**
- Before any call, the matter's estimated cost is checked against its budget. If it exceeds the budget, the matter is
  refused with a named reason. **An unknown price is a refusal, never zero.** BUILT fact: `router.estimate_inr`
  returns 0.0 for Gemini ("free tier; paid rates UNVERIFIED"), so that path cannot be used by pre-flight as written.
- A HIGH-consequence task never degrades to a cheaper model (`router.py`, BUILT).

**One interface, two backends.** `work_queue` has a `SessionBackend` (in memory, `session.py`) and a
`DurableBackend` (BLOCKED on G01). An adapter flag `requires_customer_object_storage` makes a provider path usable
only with the durable backend.

**Refusal envelope, used by every stage. Two parts, persisted separately.**
```
RefusalRecord [R]   (code, scope ∈ FILE|PAGE|REGION|SEGMENT|CELL,
                     locator = (file_key, pdf_page_index?, bbox?, segment_id?, cell_id?), stage, pipeline_version)
RefusalDetail [C]   (refusal_id, detail, offending, quoted_figures[])        # session only
```
- Only FILE scope may omit a page. A refusal below FILE scope without a page fails construction.
- `RefusalRecord` is a **closed schema**: enumerated codes, keys, keyed hashes (§4 invariant 6), integers and bboxes.
  It has no free-text field. Anything a person could read as content (a quoted figure, a span, a served date, a
  reviewer's written reason) lives in `RefusalDetail`, which is `[C]` and never leaves the session in Branch A.
- Where a built constant covers the case, that constant is used and wrapped with a locator: `FACT_NOT_GROUNDED`,
  `FACT_VALUE_UNSUPPORTED`, `FACT_MISBOUND`, `DOCUMENT_DATE_CONFLICT`. No parallel code is created. BUILT fact:
  those refusals carry client text (`reasoning.Refusal.offending`; `_against_declared_date` puts `span[:60]` and the
  served date into the refusal). Their `detail` and `offending` therefore map to `RefusalDetail`, never to
  `RefusalRecord`.

### 3.2 S0 Intake · S1 Hash, sniff, safety

| | |
|---|---|
| Inputs | Bytes, tenant, matter, uploader. The **matter as-of date** is supplied by the user and typed USER_FACT (R1 action 3). **No provenance, `PUBLIC_EVAL` or "public filing" field is accepted from an upload request**; a file entering through tenant S0 is tenant content whatever its bytes (§3.5) |
| Order | Fixed: hash → sniff → parser limits (object count, decompression ratio, nesting, **image pixel count and render memory**) → malware scan → signature parsing (`doc_verification`, `pdf_signature`, ASN.1/PKCS#7) → S2 → S3. A failure at any step stops the later steps for that file |
| Isolation | S1–S3 parsing, signature parsing and rendering run in a **per-file sandboxed subprocess with no network, no credentials and memory and time caps**. A crash or cap abstains that file (or that page, for a render) only, never the matter-run worker. INFERRED control; mechanism OPEN (G17) |
| Outputs | `file_sha256`; type sniffed from magic bytes; parser-limit report (object count, decompression ratio, nesting; named constants, values UNSET); scan verdict; signature dimensions from `doc_verification.verify_document`; unsigned incremental ranges from `pdf_signature._uncovered_ranges`. **The original bytes are never re-saved**, because a re-save breaks a PKCS#7 signature |
| Refuses (file) | `FORMAT_NOT_ACCEPTED`: v1 is PDF only; images, .xlsx, .docx and ZIP are OPEN (G21). `FILE_TOO_LARGE`: cap ≥ the §2 envelope. `ENCRYPTED_PDF`: refused, never cracked (G17). `TYPE_MISMATCH`. `MALWARE_SCAN_UNAVAILABLE`: **fail closed**. `MALWARE_DETECTED`. `PARSER_LIMIT_EXCEEDED`. `SANDBOX_LIMIT_EXCEEDED`. `NO_AS_OF_DATE`. Page: `IMAGE_DIMENSION_EXCEEDED` (page N), checked from the image dictionary before rendering; limit constants UNSET, fail closed |
| Scanner | The scanner is the first component to receive raw client bytes, so it is a §5.2 registry adapter under `tenant_eligible` like any reader. Until G17 is researched: a **local, network-isolated engine with no hash-reputation or cloud lookup**. Any cloud or reputation-based scanning service is BLOCKED. The same rule covers every auxiliary call the plan does not list (renderer telemetry, model downloads for local OCR): none may carry bytes, images, text or hashes |
| Flags | `UNSIGNED_INCREMENTAL_CONTENT`. BUILT detection (`pdf_signature._uncovered_ranges`) is file-level. Per-page attribution: resolve each page through the final xref to every object its rendering depends on (content streams, XObjects, fonts, resources, annotations); flag the page if **any** resolved object's latest definition lies in an unsigned range. A page dictionary inside the signed bytes with a content stream redefined in an appended update (a shadow attack) is therefore flagged. If that resolution is not built or fails, **every** page of a file with any uncovered range is flagged, and cells whose value depends on signature status abstain. A shadowed-content-stream fixture is required |
| Surface | Server upload only. The Word add-in shows findings; it is not the intake for files this size (R2 item 2) |
| New | `checker/intake.py`. A scanner engine is a new dependency with no research behind it (G17) |
| Status | NOT BUILT. Tenant intake BLOCKED on G17 and G01 |

### 3.3 S2 Pages and page identity

| | |
|---|---|
| Outputs per page | `pdf_page_index` (1-based, the unit R5 reports); `page_content_sha256`; MediaBox and rotation; `geometry_class ∈ {PORTRAIT, LANDSCAPE, SPREAD_CANDIDATE, OTHER}`; `printed_label_candidates[]`, each with its source (`/PageLabels` or a printed span with its own citation) |
| Identity rule | `(file_sha256, pdf_page_index)` is the page. A printed label is metadata and never identity (G11). A two-up spread stays one page, and its halves are regions (`bbox`) |
| Two enumerators | Page count and order must agree between `pdf_text.extract_pages` and a second parser. BUILT fact: `pdf_text`'s `_PAGE` regex scans raw bytes, and `_CONTENTS` matches only a single `N 0 R` reference. ~~INFERRED from that: pages inside compressed object streams and `/Contents` arrays may be missed on a 40 MB InDesign file~~ **MEASURED 2026-09-14, and not only on large files:** on the 14 local corpus PDFs (1–179 pp, PDF 1.6/1.7) `extract_pages` agrees with pdfplumber on **0 of 14** — 1 page for a 169-page file, 0 for 179-page and 16-page files, 37 for a 22-page file (incremental-update revisions), and no text from most pages even where counts match (`scripts/text_layer_census.py`, `9010605`). So this check is not a hedge against an edge case: on today's reader it would fire on almost every real filing. Reader choice is D-002 |
| Refuses | `PAGE_TREE_UNREADABLE` (file). `PAGE_COUNT_DISAGREEMENT` (file): nothing downstream runs. `PAGE_RENDER_FAILED` (page N): that page abstains and the rest continue |
| New | `checker/pages.py`, plus a parser/renderer dependency. R5 measured with PyMuPDF 1.28.2; its licence is UNVERIFIED and the choice is OPEN, with a reason required |
| Status | NOT BUILT. Page-label census (G11) not run |

### 3.4 S3 Text-layer triage

| Route | Meaning |
|---|---|
| `NATIVE_TRUSTED` | The native layer agrees with an independent OCR reading of the rendered page. **Unreachable until G05 is measured.** Until then the best a text page can reach is `NATIVE_UNCHECKED`, which cannot serve a cell |
| `NATIVE_UNTRUSTED` | A native layer exists and either disagrees or is flagged. **Its text is kept verbatim as a defect exhibit. It is never the text of record, never extracted from, and never decoded.** R5 C-1's Caesar-shifted units line can be decoded, and decoding it would be repairing a source (CLAUDE.md). The page goes to S4 as if it had no text and carries `TEXT_LAYER_CORRUPT` from then on |
| `NO_TEXT` | No usable text and an image present. Goes to S4 |
| `BLANK_CONFIRMED` | No text, no image, and a near-uniform render. A page that is not provably blank is `NO_TEXT` |

- **The pre-filter can only demote.** R5's stopword ratio and Latin-Extended/Greek glyph counts, plus fonts missing a
  `/ToUnicode` map (parsed by `pdf_text._cmaps`, BUILT), can move a page toward UNTRUSTED. They cannot certify
  TRUSTED, because the heuristic missed pp.445, 493 and 505 (R5 C-4).
- **Trust signal.** Token agreement between the native layer and a non-generative OCR reading, computed separately
  for digit tokens (exact), word tokens and any units/scale line. `THRESHOLD = None`. Until the threshold is
  measured, any disagreement on a digit or on the units line makes the page UNTRUSTED.
- **Scale rule (every numeric column, not only money).** A numeric value (money, share count, ratio, percentage or
  any other scaled number) is served only with a scale binding that has its own citation: a units or scale
  expression on the page ("₹ in thousands", "Nos. in lakh", "%"), or the statement or column header bound by S5.
  - `UNITS_LINE_UNTRUSTED` (page N), `UNITS_UNRESOLVED` (page N) or `SCALE_UNRESOLVED` (page N) abstains every
    numeric cell whose evidence is on that page.
  - Why (INFERRED from R5 C-1): the units line was corrupted while the figures survived, which would silently scale
    every value by 1,000. The same risk applies to a share-count note headed "(Nos. in lakh)".
  - **Units expressions are detected on every reading, not only the text of record**: on the native layer and on
    each OCR reading of the page. If any reading shows a local units or scale expression that the text of record
    lacks or renders differently, the page carries `UNITS_LINE_UNTRUSTED`.
  - **No fallback to the statement header** on a page where any reading shows a local units or scale token, or
    where the native layer carries unmapped or out-of-script glyphs in a position S5 marks as a table caption or
    header (R5 C-2: `ȋ᲏Ȍ` where a units bracket is expected). The fallback is allowed only when no reading of the
    page shows a local expression.
- **Measurement M-T.** Positives: A1 pp.445, 460–473, 493, 505. Candidate negatives: B1 pp.291–360 (R5 E-4).
  **The negatives are UNVERIFIED as clean.** R5 E-10 checked by eye only the pages the heuristic flagged, and C-4
  shows the heuristic misses corrupted pages. Every negative page is labelled by hand, comparing its render with its
  native text, before use; the labelled set records who labelled each page. The M-T harness refuses to hand
  `calibration_contract.assess` any page without a label. Output: an agreement distribution per class, from which a
  threshold is proposed for a human to decide.
- **Every page records** its route, its signal values and the pipeline version that chose the route.

Status: NOT BUILT. Signal validation BLOCKED on G04 and G05.

### 3.5 S4 OCR tier (PLAN_01 role 13)

**Rungs.**

| Rung | What | Rule |
|---|---|---|
| R0 render | Render at the embedded image's native resolution, inside the S1 sandbox, after the pixel-count and render-memory check; normalise rotation; record every transformation as a derivation | Low-dpi inputs are not upsampled to look better; dpi is recorded as a signal |
| R1 local OCR | Deterministic local engine, non-generative by construction (a stated reason is required when it is chosen); choice OPEN (new dependency; Indic quality UNVERIFIED) | Non-generative witness, the S3 agreement reader, and the script hint. **The S3 native-vs-OCR check uses R1 only, with no network call.** External readers receive only `NO_TEXT` and `NATIVE_UNTRUSTED` pages. Keeps a deterministic floor (R1 A19) |
| R2 document AI | Azure DI Read/Layout, Google Enterprise OCR, Sarvam Digitise, Textract (English only) | Witnesses. Sarvam's model-written blocks are quarantined (below) |
| R3 VLM | Gemini or Claude on the page image | **Never the only reading.** No request path exists (G12). BLOCKED |

**Text of record.**
- The primary engine the script router selects produces the page's text of record.
- An agreement map is computed against a second, independent reading. Independent means a different provider, and
  at least one of the two must be non-generative. **Until a vendor states its model architecture in writing, only
  local R1 counts as the non-generative witness.** The registry's `generative` field is INFERRED from product type
  (§5.2) and is treated as UNVERIFIED for this rule, so a pair of two cloud readers never satisfies it.
- A page is `OCR_PASSED` only when agreement coverage meets `THRESHOLD`, which is None today, so today the result is
  `OCR_GATE_UNSET`.
- A page that passes can still contain `DISAGREEMENT_REGION`s. A cell whose span touches one abstains, so a smudge
  costs that cell and not the page.

**OCR confidence gate: signal and measurement, no number.**

| Signal | Role | Measured by |
|---|---|---|
| Cross-reading agreement (tokens; digits exact) | Primary. It exists for every provider pair. Vendor confidence is undocumented for Sarvam managed (R3 E10), unchecked for Azure and Google at word level (R4 item 7), and uncalibrated on our paper everywhere | Bake-off on the A1 image-only pages listed in §2 plus the corrupted pages. Ground truth is hand transcription. Record per page: CER, invented text, stamp handling, **correlated error** (both engines agree on the same wrong token) and **correlated omission** (both engines skip the same region, so nothing disagrees; detected against the hand transcription and against image-ink coverage) |
| Vendor confidence: Textract `Confidence` (R4 C1), Sarvam self-hosted `ocr_confidence` (R3 F3) | Secondary. It may demote a page and never promote one | Same bake-off |
| dpi, skew, image coverage | Priors that route a page to more witnesses | Same bake-off |

- **Output of the measurement:** a risk–coverage curve per signal, **per script and per dpi band**.
  - A cut calibrated on Latin pages does not transfer to Devanagari. A script without its own curve abstains.
  - The tolerable error rate is a founder and legal decision, taken from the curve.
  - `calibration_contract.assess` (BUILT) runs on the labelled n. If it refuses, `THRESHOLD` stays None.
  - The Google `asia-south1` Preview vs `us` difference is recorded. That difference is the accuracy cost of
    residency (R4 action 2).
- **Main residual risk:** correlated error. Two engines misreading the same ≈90 dpi digit the same way is INFERRED as
  a risk and unmeasured. If the bake-off finds it on a page class, that class abstains wholesale until a third
  witness or a human transcription exists.

**Script router, applied before any content-bearing call.** The table shows documented coverage. Tenant
eligibility is a separate filter (§5.3), and today it removes every row.

| Script (printed) | Documented coverage | Witnesses possible once eligible |
|---|---|---|
| Latin | Textract (R4 A1), Sarvam English (R3 C1), local; Azure and Google Latin coverage INFERRED (the R4 rows read list their Indic languages only) | ≥2 |
| Hindi, Marathi, Nepali (Devanagari); Tamil | Azure (A5), Google (A8), Sarvam (C1) | ≥2 |
| Sanskrit, Urdu; Bodo, Dogri, Santali (Devanagari) | Azure (A5), Sarvam (C1) | 2 only with Sarvam |
| A5's minor Devanagari languages (Awadhi-Hindi, Bhojpuri-Hindi, Chhattisgarhi, Haryanvi, Kangri, Kurukh, Sadri) | Azure only (R4 A5); not in R3 C1's 23 languages | 1 → `NO_ELIGIBLE_SECOND_WITNESS` |
| Bengali, Gujarati, Kannada, Malayalam, Telugu, Gurmukhi | Google (A8), Sarvam (C1) | 2 only with Sarvam |
| Odia, Assamese | Sarvam only (R4 A13; R3 C1) | 1 → `NO_ELIGIBLE_SECOND_WITNESS` |
| Indic handwriting | Google for Bengali, Hindi, Marathi, Nepali (R4 B3); Sarvam (no metric); Azure none (B2) | ≤2 |
| Mixed-script page | Sarvam takes one language per job (R3 C2); behaviour on the other script UNVERIFIED (C4) | Two script-appropriate readers or abstain |

- **Script detection.**
  - Native pages: a Unicode script census, with no network call.
  - Scanned pages: the local OCR hint. Azure's language-code-free extraction (R4 A7) may do the first pass only once
    Azure is eligible.
  - Scripts that appear only on Azure's detection list (R4 A6: Bengali, Gujarati, Odia and others) are used for
    routing only. Text Azure returns for them is discarded.
- **If the census finds non-Latin pages near zero (G09),** only the Latin and Devanagari rows are built for v1. Every
  other script abstains with `SCRIPT_NOT_SUPPORTED_V1`, naming the page.

**Model-written text is quarantined.**
- Sarvam Digitise writes image and chart descriptions (R3 D7). Those blocks, and any VLM output that failed
  agreement, go to `model_written`. The span grounder never searches that field.
- Text a provider reads is untrusted document data. Text a provider writes is not document data.

**Imperative sentences are a gate, not only a flag.**
- The detector runs on **every reading and on the native layer**, not only the text of record. A disagreement region
  where one reading has an instruction-shaped sentence and the other has nothing (a reader that obeyed by omitting
  the line) also triggers it.
- A trigger sets `INJECTION_SUSPECT` on the page. Every cell whose evidence, binding citations or context unit
  includes a flagged page is `HELD` for human review, and abstains with `INJECTION_SUSPECT` (page N) if no review
  clears it. A flagged page is not sent to any extraction provider before that review (§3.1).
- The text is **never stripped**, because stripping is repair (CLAUDE.md).
- Extraction witnesses receive the same document text, so an injected instruction is a shared input: **two witnesses
  are not independent against injection**, and their agreement is no evidence against it (§8 row 17). This raises the
  cost of an attack; it does not close image-borne injection.

**Stamps and seals.**
- No provider documents stamp or seal handling (R4 C8; R3 D3). A reader's silence is never recorded as "no stamp".
- OCR tokens inside a detected figure region (Azure Layout figures, R4 C3; INFERRED usable) are marked
  `OVERLAPS_MARK`, and cells touching them abstain.
- STAMP is DECLARED in `scope.py`, so stamp-duty facts are refused at S8 anyway. The detector is OPEN (G20).

**Reconciliation.** A job that returns fewer pages than it was sent raises `PAGE_MISSING_FROM_READING` (page N). A
missing page is never treated as empty.

**Sarvam: both hard constraints.**
1. **Training default.** The Privacy Policy says content trains models "unless you explicitly opt-out" (R3 H7).
   The EULA, Trust Center and ToS disagree (H8–H11).
   - `training_opt_out_verified` and `doc_ai_zero_retention_verified` (R3 H4, H5) are **call-time preconditions**.
   - Each becomes VERIFIED only on a dated written vendor answer or a signed DPA recorded in `VENDOR_QUESTIONS.md`.
     A dashboard toggle observed once does not count.
   - The Trust Center's India residency applies "for Indian customers" (R3 H1; G22), and the ToS reserves the right
     to transfer data abroad (R3 H2). Both are carried as preconditions.
   - Until all of these hold, the adapter refuses any document not tagged `PUBLIC_EVAL`. For public bake-offs,
     opt-out and the shortest retention are set before the first upload (R3 action 3).
   - **`PUBLIC_EVAL` is derived, never declared.** It holds only when the file's `file_sha256` exactly matches a
     `corpus/testdocs/MANIFEST.md` entry that records source URL, robots result (`checker/robots.py`) and hash, for a
     file the operator acquired under `docs/ACQUISITION_POLICY.md`. No user, tenant or operator field sets it. A file
     that entered through tenant S0 intake never carries it, **even when its bytes match a manifest hash**: the copy
     may be annotated, and the fact that a tenant is reviewing that deal is itself confidential. Test: a tenant
     upload with bytes identical to a manifest file is refused by the Sarvam adapter.
2. **10 pages per call.** The PDF cap is 10 pages and does not rise with plan (R3 D9, D10). The limit is 10 req/min
   on every plan (R3 E11).
   - Jobs hold ≤10 pages and one language code each (R3 C2), keyed by `page_content_sha256`.
   - Status polls share the token bucket until it is known whether they count (UNVERIFIED, R3 G4).
   - A `partially_completed` job abstains only its failed pages.
   - Managed Digitise documents no confidence (R3 E10), so it can serve only as an agreement witness.
   - Self-hosted SageMaker takes 500 pages per document (R3 F2), returns `ocr_confidence` (F3) and runs in our VPC
     (F1). Its India region is UNVERIFIED (F6) and so is model parity with managed (F7), so it cannot back a
     residency claim.

**S4 refusals.**
- Page: `OCR_GATE_UNSET`, `OCR_READINGS_DISAGREE`, `SINGLE_WITNESS`, `NO_ELIGIBLE_SECOND_WITNESS`,
  `NO_COMPLIANT_READER(script)`, `SCRIPT_NOT_SUPPORTED_V1`, `OCR_PROVIDER_PAGE_FAILED`,
  `PAGE_MISSING_FROM_READING`, `PROVIDER_PRECONDITION_UNVERIFIED(adapter, field)`.
- Adapter: `READER_RETENTION_DELETE_FAILED`, raised when Azure's `Delete Analyze Result` fails. Up to 24 h of
  retention then exists (R4 G3), so an alarm fires and sending stops.
- **A Delete that is never attempted must also alarm.** Before each Azure submission, a content-free pending-delete
  record `(operation_id, adapter, submitted_at)` is written through the persisted `[R]` path. A sweeper outside the
  session worker deletes, or alarms `READER_RETENTION_DELETE_UNCONFIRMED`, on any record not cleared within a bound
  (constant UNSET), including after a worker crash. Even a successful Delete leaves the input and result in Azure's
  shared, logically isolated temporary storage from submission until the Delete (R4 G3): that is retention followed
  by deletion, however short.
- Region: `OVERLAPS_MARK`, `DISAGREEMENT_REGION`.

Status: NOT BUILT. The threshold is BLOCKED on G04, tenant use on G16 and G02, the VLM rung on G12.

### 3.6 S5 Layout and tables

| | |
|---|---|
| Outputs | Blocks (heading, paragraph, table, figure, running header/footer). Running headers are marked (R5 D-3), so they are never a span candidate for a fact. Tables become cells (row, column, bbox, token ids into the text of record) with a header chain per column, a row label per row, continuation links across pages, and a cited units binding |
| Structure is a proposal | (a) Every cell's tokens must exist in the page's text of record inside the cell bbox. (b) A numeric cell needs a row label and a column header, each a grounded span. (c) Where a table states a total over rows it identifies by its own labels, the arithmetic is checked **at the document's stated precision**. A mismatch abstains the table's numeric cells as `TABLE_ARITHMETIC_INCONSISTENT`, with both figures quoted in the session-only `RefusalDetail` (§3.1), never in the persisted record. It is never corrected and never called a defect, because it could be rounding |
| Numbers | Lakh grouping ("8,06,470.99", R5 C-1) and bracket negatives stay as printed. They are parsed against the verbatim span in value-support. An ambiguous grouping abstains |
| Refuses | `TABLE_STRUCTURE_UNGROUNDED`, `ROW_LABEL_UNRESOLVED`, `COLUMN_HEADER_UNRESOLVED`, `TABLE_BINDING_ABSENT`, `TABLE_ARITHMETIC_INCONSISTENT`, `TABLE_CONTINUATION_UNRESOLVED` (pages N–M), `NUMBER_FORMAT_AMBIGUOUS` |
| Headings | S5 marks heading blocks with their position on the page. S6 boundary evidence and S7 title spans must lie in a heading block within the top region of the page (region bound UNSET), so body text that happens to name a document type never establishes a boundary or a type |
| Providers | Azure Layout (R4 C3). Google Layout Parser has **no `asia-south1` row** (R4 E6), and Form Parser there covers Hindi, Marathi and Nepali only among Indic scripts (A9). Structure costs about $10–70 per 1,000 pages against about $1.50 for Read (R4 F10), so it is not run on every page. **Which pages it runs on is a cost choice and never decides whether gate h applies**: gate h is mandatory for every money and numeric cell (§3.11). S5 runs on every page of an `FS_*`, `UNAUDITED_RESULTS` or `MANAGEMENT_ACCOUNTS` segment, and on any page whose numeric-token density marks it as a candidate (signal from R5 E-6; `THRESHOLD = None`, so today every page of those segment types is sent). A numeric value on a page S5 did not run on abstains as `TABLE_BINDING_ABSENT` (page N). Why: detection undercounts borderless tables (R5 E-7), the usual Ind AS layout (INFERRED) |
| Status | NOT BUILT. Accuracy BLOCKED on G06. XBRL as ground truth is a hypothesis (G07) |

### 3.7 S6 Bundle segmentation, before any type or scope decision

| | |
|---|---|
| Why first | A1 is 14 documents in 512 pages (R5 E-B). Typing the file would put Companies Act checks on the CCI order and the valuation report |
| Deterministic candidates | Running-header change (R5 D-3). Printed page-number reset. Title heading at page top ("Independent Auditor's Report", R5 E-4). Change of text-layer route (A1's scanned block starts at p.98, R5 E-B). Geometry change (R5 E-2). Closing or signature block |
| Index page | An in-file index (A1 pp.1–2) is **an untrusted hint** and data, never an instruction |
| Model | May propose a boundary only by quoting a heading that grounds on the first page of the new segment (`document_extract.locate`) **and lies in an S5 heading block at the top of that page**. Otherwise the proposal is dropped. No model call is made on tenant content until an extraction adapter is eligible (§5.3) |
| Gate | A boundary is `ESTABLISHED` only where a deterministic candidate coincides with a proposal or the index on the same page and the evidence span grounds. Pages between competing boundaries are `UNASSIGNED`. Segments cover every page exactly once, **where `UNASSIGNED` ranges count as coverage** |
| Failed boundary | A boundary candidate that cannot be established (for example `BOUNDARY_EVIDENCE_ON_ABSTAINED_PAGE`) turns the range from that page up to the page before the next `ESTABLISHED` boundary into `UNASSIGNED`, producing no cells (`SEGMENT_BOUNDARY_UNCERTAIN`, pages N–M). **An adjacent segment is never extended over it**, so it never lends its type, scope route or declared date to those pages. A1-shaped test: with p.433 and p.445 abstained, pp.433–491 are `UNASSIGNED` and the FY2020-21 accounts segment ends at p.432; likewise p.207 abstained leaves the CCI order ending at p.206 |
| Entity and basis | A segment that may hold figures or obligations of a company carries `entity` (which company, by CIN or name as printed) and `basis` (`STANDALONE`, `CONSOLIDATED`, `NOT_APPLICABLE`). Both are **declared by a human** with a grounded citation, on the same screen as the segment date (§3.10). A1's B-11 holds three companies' statements under one index entry (R5 E-B): unless boundaries inside it are established, it stays one segment with no single entity, and no cell in it is served |
| Refuses | `SEGMENT_BOUNDARY_UNCERTAIN` (pages N–M). `BOUNDARY_EVIDENCE_ON_ABSTAINED_PAGE` (page N): a boundary cannot rest on an unread page. `INDEX_CONFLICT` (index page vs detected page). `SEGMENT_ENTITY_UNDECLARED`, `SEGMENT_BASIS_UNDECLARED` (segment, pages). No cells are produced in an uncertain range |
| Status | NOT BUILT. One labelled example (A1's index), n=1. Accuracy BLOCKED on G10 and G08 |

### 3.8 S7 Segment type

- **Closed vocabulary**, seeded from R5 E-B, E-D and E-E. It is extended only with a fixture:
  `NCLT_MEETING_NOTICE`, `EXPLANATORY_STATEMENT`, `SCHEME`, `VALUATION_REPORT`, `FAIRNESS_OPINION`,
  `EXCHANGE_OBSERVATION_LETTER`, `CCI_ORDER`, `BOARD_REPORT_S232_2C`, `COMPLAINTS_REPORT`, `AUDITORS_REPORT`,
  `FS_STANDALONE`, `FS_CONSOLIDATED`, `UNAUDITED_RESULTS`, `MANAGEMENT_ACCOUNTS`, `ABRIDGED_PROSPECTUS_INFO`,
  `NCLT_ORDER`, `AGM_NOTICE`, `OFFER_DOCUMENT`, `UNKNOWN`.
- **Deciding the type.**
  - A deterministic heading-match classifier runs first, on S5 heading blocks at the top of the segment's first
    page only.
  - **A type is `ESTABLISHED` only when the deterministic classifier matches exactly one type.** A model (the
    `CLASSIFY` tier) may *confirm* that label with a verbatim title span in the same heading block. A model may never
    *originate* a label: a model label with no deterministic match gives `UNKNOWN`. Why: the type selects the check
    set and the scope route, so a model-originated label would let a model pick which law's checks fire.
  - A failed match, two types matching, or a model disagreeing with the deterministic classifier all give
    `UNKNOWN` and `CLASSIFICATION_UNCERTAIN` (segment, pages).
- **An unknown type is uncertainty, not a defect** (CLAUDE.md). Its cells are `NOT_EVALUATED`.
- **A type selects an extraction schema and a candidate check set.** It never decides that an obligation applies.
- **`TYPE_CHECKS` registry** (`check_id → permitted segment types`), beside `SEGMENT_BODY` and with its own
  completeness test. Invariant: no check runs on a segment whose type is not listed for it. Body-level routing (§3.9
  invariant 1) is not enough, because five types share CA2013 (CLAUDE.md: minutes checks must not fire on notices).
  An AGM-notice contents check (s.101/102) never runs on `EXPLANATORY_STATEMENT` or `NCLT_ORDER`.
- **Declared dates have per-type meaning** (`DATE_SEMANTICS`, §3.10).
- `checker/classify.py` classifies companies under s.2(85). It is not this module.

### 3.9 S8 Scope routing

A new `SEGMENT_BODY` table, in the pattern of `scope.OBLIGATION_BODY`. A completeness test fails if any type lacks
an entry.

| Types | Body (state in `scope.py`) | Consequence today |
|---|---|---|
| `SCHEME`, `NCLT_MEETING_NOTICE`, `EXPLANATORY_STATEMENT`, `BOARD_REPORT_S232_2C` | CA2013 (IN_CORPUS) | `permitted = EXTRACT_AND_CITE` until G03 closes, and **no check runs**. The prescribed contents of these documents sit in the CAA Rules 2016, which are not held (G03), so a check resting on ss.230–232 alone would report "no missing item" on half a requirement. Every check touching ss.230–232 is marked as resting on the Rules and refuses whole with `RULE_NOT_HELD`, never partially |
| `AGM_NOTICE` | CA2013 (IN_CORPUS) | Built AGM checks may run, subject to `TYPE_CHECKS` |
| `OFFER_DOCUMENT`, `COMPLAINTS_REPORT` | SEBI_OTHER (DECLARED) for offer documents (ICDR); SEBI_OTHER or SEBI_LODR for the complaints report. The mapping is INFERRED | `BODY_NOT_HELD` → refusal. An offer document never routes to CA2013 even though Chapter III covers prospectuses, because the document is an ICDR filing (R5 F-1) |
| `CCI_ORDER` | COMP2002 (DECLARED) | `BODY_NOT_HELD` → `refusal_for("COMP2002")` |
| `EXCHANGE_OBSERVATION_LETTER`, `ABRIDGED_PROSPECTUS_INFO` | SEBI_LODR (CURRENT_ONLY) or SEBI_OTHER (DECLARED). The mapping is INFERRED | Dated questions refused |
| `FS_*`, `AUDITORS_REPORT`, `UNAUDITED_RESULTS`, `MANAGEMENT_ACCOUNTS`, `VALUATION_REPORT`, `FAIRNESS_OPINION` | None declared for Ind AS, Schedule III or valuation (G03) | `NO_BODY_DECLARED(type)`: the refusal catches `scope.body`'s `LookupError` and names the type. **Never silence** |
| `NCLT_ORDER` | Subtype by a closed deterministic rule on the grounded case-number prefix: `C.P.(CAA)` or `C.A.(CAA)` → CA2013 scheme order (R5 A2, A3); `C.P.(IB)` → IBC2016 (DECLARED); anything else → `UNKNOWN`. The IB prefix pattern is INFERRED and needs a fixture | Scheme order: `EXTRACT_AND_CITE`, no checks until G03 (as row 1). IBC: `BODY_NOT_HELD` |
| `UNKNOWN` | None | `NONE` |

- Output per segment: `permitted ∈ {EXTRACT_AND_CITE, EXTRACT_AND_VERIFY, NONE}` plus the refusal text.
- Invariant tests:
  1. No CA2013-keyed check is invoked on a segment mapped elsewhere.
  2. `EXTRACT_AND_VERIFY` is never given for a body that is not IN_CORPUS.
  3. `UNKNOWN` gives `NONE`.
  4. No check runs on a segment whose type is not in its `TYPE_CHECKS` entry (§3.8).
  5. Every type in the §3.8 vocabulary has a `SEGMENT_BODY` row (this table now has all 19).
  6. No check touching ss.230–232 runs while G03 is open.
- Adding a body is a `scope.py` decision with its own acquisition route. This plan adds none.

### 3.10 S9 Extraction

| | |
|---|---|
| Context unit | The whole segment, or a deterministic sub-unit (a note number or heading) when it exceeds an input limit. A sub-unit never splits a table. **Never top-k retrieval per cell.** Harvey's review-table harness retrieves snapshots per cell (R1 B4), and PLAN_01's objection applies: nothing downstream detects a bad retrieval. Verbatim quotability needs whole sections (PROVIDER_DECISION §2). Every cell records `pages_read[]` |
| Page anchoring | Pages of text of record are concatenated with a stored offset map, and the separators are ours and excluded from grounding. The Anthropic document block is sent **unwrapped**, so `char_location` offsets hold (CLAUDE.md). A span crossing a page boundary abstains in v1 (`SPAN_CROSSES_PAGE`, pages N and N+1); how often that happens is unmeasured |
| Proposal shape | `{field: {value, span, page}}`. The claimed page is checked, not trusted |
| Segment date | **Pass A:** a date-only proposal per segment, grounded and reviewed, outside the orchestrator. It is a `MODEL_SUGGESTION` shown with its quote and page. **Declaration:** a human declares each segment's date, entity and basis (§3.7), batched on one screen per bundle. The declared date is `USER_FACT` with the page the human looked at. A bundle has several dates, for example a valuation report of 18 Aug 2020 and a meeting of 12 Feb 2022 (R5 E-B). **A declaration is allowed only on a final `segment_key`.** If a boundary later changes, the key changes, the declaration is void, and the segment's cells return to `HELD` with `SEGMENT_DATE_UNDECLARED`; a declaration is never carried to a new segment by page overlap. **Pass B:** every other column runs through `orchestrator.run` with the declared date. BUILT fact: `_against_declared_date` returns the review unchanged when the proposal has no `document_date` fact, so for F8 a Pass B proposal that lacks a `document_date` bound to the declared date refuses as `SEGMENT_DATE_NOT_BOUND` (an F8 wrapper; the built function is not changed). Pass B cells stay `HELD` until declaration and make no provider call before their segment is final (§3.1). With no declaration, temporal checks refuse with `SEGMENT_DATE_UNDECLARED` |
| `DATE_SEMANTICS` | What the declared date means, per type, shown on the declaration screen (INFERRED; each entry needs a fixture): `NCLT_MEETING_NOTICE` → the notice's issue date (not the meeting date, not the convening order's date; A1 carries all three); `EXPLANATORY_STATEMENT` → issue date of the notice it accompanies; `SCHEME` → the date the board approved it, if printed, otherwise undeclarable; `FS_*`, `UNAUDITED_RESULTS`, `MANAGEMENT_ACCOUNTS` → balance-sheet or period-end date; `AUDITORS_REPORT` → report signing date; `VALUATION_REPORT`, `FAIRNESS_OPINION` → report date; `EXCHANGE_OBSERVATION_LETTER`, `CCI_ORDER`, `NCLT_ORDER` → date of issue; `AGM_NOTICE` → notice date. A type with no entry cannot be declared. Gate-k modules take dates as follows: `currency` and `staleness` take the **matter as-of date** from S0; `obligations` takes the declared segment date; a check whose date input is neither refuses with `DATE_ROLE_UNDEFINED` |
| Period binding | For money and numeric cells, the column-header period span (S5) must ground and must equal the declared period under `DATE_SEMANTICS`, or the cell abstains `PERIOD_MISBOUND` (cell, page). This is what catches a prior-year comparative column; gate e alone does not |
| Second extraction witness | For money, date and identifier columns, two proposals from **different providers**, with no model seeing the other's output. **A deterministic proposer counts as a witness only after its precision has been measured on a labelled set** (`THRESHOLD = None` today, so it does not count yet), and two deterministic proposers of the same pattern never count as two witnesses. This is an agreement filter, not debate (PLAN_01). The served value must agree exactly, including span location; otherwise `EXTRACTION_WITNESSES_DISAGREE` (cell, pages). Two isolated calls to the same provider are recorded, but **do not count as a second witness until shadow runs show their disagreement catches errors**, because their errors are likely to be correlated (INFERRED). Until then, a column with only one permitted provider abstains as `EXTRACTION_SINGLE_WITNESS` |
| Adapters | `anthropic_model` (text, `EXTRACT = claude-opus-5`). `gemini_model` (text; Vertex location defaults to `global`; AI Studio free-tier data use UNVERIFIED). `eval/realrun/azure_model` (UAE North, Azure for Students; evaluation only). Ollama (evaluation only). Deterministic proposers (CIN pattern, dates, units lines) have no network call and unmeasured recall and precision. On today's evidence they are the only proposers usable on tenant documents, and they are not yet witnesses, so every money, date and identifier column on a tenant document abstains as `EXTRACTION_SINGLE_WITNESS` |
| Refuses | Cell: `SPAN_CROSSES_PAGE`, `PAGE_CLAIM_MISMATCH`, `SPAN_LOCATION_AMBIGUOUS`, `EXTRACTION_WITNESSES_DISAGREE`, `EXTRACTION_SINGLE_WITNESS`, `SEGMENT_DATE_UNDECLARED`, `SEGMENT_DATE_NOT_BOUND`, `PERIOD_MISBOUND`, `INJECTION_SUSPECT`. Segment: `EXTRACTOR_UNAVAILABLE` (reuses `ModelUnavailable`), `INPUT_LIMIT_UNVERIFIED`, `REFUSED_BEFORE_CALL(BUDGET)` |
| New columns | Each needs a validator in `extraction_schema.py` and binding terms in `field_binding.py`. The PLAN_11 L3 replay rule applies: new refusals on correctly served stored facts must be 0, or the widening is not committed |
| Status | NOT BUILT. Tenant use BLOCKED on G02 |

### 3.11 S10 Gates, per cell, in the order the code runs

`reasoning.review()` runs span present, then value-support, then field binding (`reasoning.py`, read). The
orchestrator then applies `DOCUMENT_DATE_CONFLICT`. This design keeps that order. It adds page, reading and table
gates after the built ones, so no built gate is weakened or duplicated.

| # | Gate | Refusal (locator) | State |
|---|---|---|---|
| a | Schema: could this value exist (`extraction_schema.validate_extraction`) | its verdicts (cell) | BUILT |
| b | Span present in the **page text of record** | `FACT_WITHOUT_SPAN`, `FACT_NOT_GROUNDED` (cell, claimed page) | BUILT (single string) |
| c | Value-support: empty value refused, CIN shape checked | `FACT_VALUE_UNSUPPORTED` (cell, page) | BUILT |
| d | Field binding: span names a different field | `FACT_MISBOUND` (cell, page) | BUILT |
| e | Served document date equals the human-declared segment date. **BUILT behaviour covers only a proposal that carries `document_date`**; it is a no-op for any other cell and never checks the period a figure belongs to. F8 adds: a Pass B proposal without a bound `document_date` refuses (`SEGMENT_DATE_NOT_BOUND`), and money and numeric cells need period binding (§3.10) | `DOCUMENT_DATE_CONFLICT`, `SEGMENT_DATE_NOT_BOUND`, `PERIOD_MISBOUND` (cell, page) | BUILT (one date per run, `document_date` only); the F8 additions NOT BUILT |
| f | Page anchoring: the span resolves to exactly one `(file, page, start, end)`, and that is the claimed page. `locate()` returns the first occurrence, so a repeated running header, or one figure in both the standalone and consolidated statements, must be caught here | `PAGE_CLAIM_MISMATCH`, `SPAN_LOCATION_AMBIGUOUS` (cell, pages) | NOT BUILT (PLAN_11 D2) |
| g | Reading quality, applied to **every citation the cell rests on**: the value span and each of `binding_citations[row, column, units]`. Each page is `NATIVE_TRUSTED` or `OCR_PASSED`; no cited span touches a disagreement region, mark region, running header, figure region or `model_written`; no cited page carries `INJECTION_SUSPECT` or `UNITS_LINE_UNTRUSTED`; a numeric cell has a cited scale binding (§3.4) | `PAGE_NOT_TRUSTED`, `DISAGREEMENT_REGION`, `OVERLAPS_MARK`, `UNITS_LINE_UNTRUSTED`, `UNITS_UNRESOLVED`, `SCALE_UNRESOLVED`, `INJECTION_SUSPECT` (cell, the binding or value page, bbox) | NOT BUILT |
| h | Table binding, **mandatory for every money and numeric cell whether or not its page was marked tabular**: row-label and column-header spans ground and align with the value. A value with no grounded row label and column header abstains | `TABLE_MISBOUND`, `TABLE_BINDING_ABSENT` (cell, page, bbox) | NOT BUILT |
| i | Extraction witnesses agree | `EXTRACTION_WITNESSES_DISAGREE`, `EXTRACTION_SINGLE_WITNESS` | NOT BUILT |
| j | Provenance: new kind `DOCUMENT_SPAN` carrying its reading source. A human edit becomes `USER_FACT` and loses `DOCUMENT_SPAN` | `SlotError` at construction | NOT BUILT (extends `provenance_slots.py`) |
| k | Verification, only when S8 permitted it and `TYPE_CHECKS` lists the segment's type: `obligations`, `currency`, `staleness`. BUILT fact: `obligations` generates rows from a `CompanyProfile`, not from a document. Gate k refuses when the segment's `entity` or `basis` is undeclared. **Extracted cells never fill a `CompanyProfile`**; a profile field is set only by a `USER_FACT` attestation naming the entity. `NOT_FOUND` and `ABSTAINED(ABSENCE_UNVERIFIABLE)` never produce a "missing required information" result | their outputs; otherwise the body refusal, `SEGMENT_ENTITY_UNDECLARED` or `SEGMENT_BASIS_UNDECLARED` (segment, pages) | BUILT for CA2013 obligations; the F8 conditions NOT BUILT |
| l | Human (§3.13) | Approval raises on `MODEL_SUGGESTION`/`UNKNOWN` | BUILT pattern; F8 surface NOT BUILT |

One gap is named rather than claimed closed. Nothing detects a wrong value quoted consistently from a correctly
read page with the field's own term; `field_binding`'s docstring states this limit. Witnesses and table binding
reduce the risk and do not remove it. LEAKED is measured, not assumed to be zero.

### 3.12 S11 Cell table

`cell_id = cell_key` (§3.1). **`ABSTAINED` is the construction default.**

| State | Meaning | Shown as |
|---|---|---|
| `NOT_APPLICABLE_TO_TYPE` | The column has no meaning for this type. **Reachable only when both boundaries of the segment are `ESTABLISHED` and its type is `ESTABLISHED`**; otherwise the cell is `NOT_EVALUATED` | Greyed, with the segment's page range and type citation. The type decision is a refusable review item (`TYPE_BASIS`, pages) in the queue. Not an abstention (INAPPLICABLE, never a defect) |
| `NOT_EVALUATED` | Segment uncertain or not permitted (S6–S8) | The segment refusal and its page range |
| `HELD` | Computed; segment or date not final | Not shown to the lawyer |
| `ABSTAINED(code, pages[], bbox?)` | A gate refused | e.g. "Could not read PDF p.273: scanned at ≈95 dpi; two readings disagree on this figure", with the page opened at the region |
| `ABSTAINED(ABSENCE_UNVERIFIABLE, pages_read[])` | Every page and region was read and trusted, no witness proposed a value, but recall for the column family is unmeasured or fewer than two independent extractors made no proposal | "No value proposed from PDF pp.12–37. Whether it is absent has not been verified; check these pages" |
| `NOT_FOUND(pages_read[])` | §1 item 3 (a)–(c) all hold. **Unreachable today** (`RECALL_THRESHOLD = None`) | "Not found on PDF pp.12–37 (all read; recall measured on n=…)". Otherwise `ABSTAINED(ABSENCE_UNVERIFIABLE)` or `ABSTAINED(COVERAGE_INCOMPLETE, unread pages)` |
| `EXTRACTED_UNVERIFIED` | Gates a–j passed; S8 permits cite only | Value, quote on hover (R2 item 4), page, and the body refusal |
| `PROPOSED` | Gates a–k passed | Value, quote, page, check result; awaiting review |
| `VERIFIED(by, at)`, `EDITED(by, at)`, `FLAGGED(by, at)`, `LOCKED` | Harvey's cell states (R1 C2, item 3) | An edit makes the value `USER_FACT` |
| `INVALIDATED_BY_CHANGE(cause)` | File hash, reading, pipeline version or law changed (R1 item 6) | Branch B only |

**Rules.**
- An abstained cell looks different from an unreviewed one.
- No "Apply All" on verdicts (R2 item 5).
- No served cell exists without page and quote. That is Harvey's floor (R1 item 2); ours adds offset, reading id and
  hash.
- No document-level "reviewed" badge appears while any cell is ABSTAINED.
- **Export schema.** Every exported cell carries `state`, refusal code, `pages[]`, `bbox?`, quote, `file_sha256` and
  the pipeline version. A served value never appears without its page. `ABSTAINED`, `NOT_EVALUATED`,
  `NOT_APPLICABLE_TO_TYPE` and `HELD` are never exported as an empty value: they carry their state and code. Test: the
  export of a table containing an `ABSTAINED` cell contains that code and page and no empty value. The display rules
  above apply to the export, since in Branch A review may happen there (§7.2).

**F8 metric (G19).**
- Separate from METRIC_POLICY. Its ≤0.25 abstention cap was set for entailment and is not imported.
- Reported per page class (native trusted, native untrusted → OCR, no text → OCR, mixed script) and per column
  family, using `shadow.py` outcomes and PLAN_11 L5's `WRONG_SERVED`.
- **LEAKED is the release-blocking number.** LEAKED is any cell in a served state (`EXTRACTED_UNVERIFIED`,
  `NOT_FOUND`, `NOT_APPLICABLE_TO_TYPE`, `PROPOSED`, `VERIFIED`) whose value, absence claim or inapplicability claim
  is wrong against the label. OVER_REFUSED and the abstention rate are always reported beside it and never netted
  off.
- The `NO_COMPLIANT_READER` share is reported to the founder as the measured price of residency on the buyer's
  paper.
- No thresholds until a labelled set exists (G06).

### 3.13 S12 Human review

- **Work items** use the `review_queue` shape: one target, specific questions, and `page_start`/`page_end` pointing at
  the page to check (BUILT fields). Review is **batched by page**, so a reviewer looks at a scanned page image once
  for all of its cells. Segment dates are declared on one screen per bundle.
- **Attestations** are append-only, with supersession explicit and pinned to the table hash (the `review_record`
  pattern) and to the cell's `value_key` (§3.1). An attestation is shown only on a cell whose current `value_key`
  equals the attested one; a re-run that yields a different value shows the cell unattested. A restricting decision
  without a written reason is refused (`review_queue`, BUILT). **The written reason is `[C]`** and is never persisted
  in Branch A. An edit invalidates an earlier verification.
- **Resolving an abstention.** A human may transcribe a value from a named page. It is recorded as `USER_FACT` with
  their identity and the page. The original abstention stays in the record.
- **Event log** (R2 item 8): upload, hash, scan verdict, page routes, refusals, and who viewed and attested which
  cell, without content.
- Status: NOT BUILT. Review that lasts beyond a session requires Branch B (§7).

---

## 4. Data model

Frozen dataclasses, stdlib only. **`[C]` marks client content**; everything else is `[R]`, a key or result with no
client content.
- **The persistence rule is structural.** A persisted record type is a closed schema whose fields hold only enumerated
  codes, keys, keyed hashes, integers, timestamps and bboxes. It has no free-text field. A `[C]` field cannot be
  assigned to a persisted type; construction fails.
- `session.releasable()` is a **second line of defence, not the proof.** BUILT facts: it detects verbatim runs of at
  least `LEAK_WINDOW = 40` characters, so a figure such as "8,06,470.99", a CIN, a date or a short written reason
  passes it; and it returns any record unchecked once the session is closed. F8 therefore refuses persistence from a
  closed session instead of passing the record through (an F8 wrapper; the built function is unchanged).
- Tests: persisting a sub-40-character figure, and a reviewer's written reason, is refused by schema; a
  `TABLE_ARITHMETIC_INCONSISTENT` and a `DOCUMENT_DATE_CONFLICT` refusal persist only their `RefusalRecord`;
  persistence attempted after `close()` raises.

```
File      file_sha256 (session), file_key = HMAC(tenant_secret, file_sha256) (persisted), byte_size, sniffed_type,
          received_at, tenant_id, matter_id, uploader (pseudonymous),
          scan_verdict, parser_limits{}, signature_dims{}, unsigned_ranges[], page_count, enumerator_agreement,
          declared_filename [C]
Page      file_sha256, pdf_page_index, page_content_sha256, mediabox, rotation, geometry_class, dpi?, script_hint?,
          printed_label_candidates[(label [C], source, citation?)], route, route_signals{}, flags{},
          text_of_record_id?, status ∈ {TRUSTED, NATIVE_UNCHECKED, OCR_PASSED, ABSTAINED}, refusals[],
          native_text [C] (exhibit only when NATIVE_UNTRUSTED)
Reading   reading_id = page_work_key, provider, model_version, region, generative, vendor_conf_fields, cost,
          tokens[(text [C], bbox)], model_written[] [C] (never searched)
TextOfRecord  id = sha256(text), page ref, source ∈ {NATIVE, OCR(reading_ids)}, text [C],
          agreement_map[(start, end, AGREED|DISAGREED)]
Region    page ref, bbox, kind ∈ {TABLE, TABLE_CELL, FIGURE, MARK, RUNNING_HEADER, RUNNING_FOOTER, SPREAD_HALF, UNITS_LINE}
Segment   segment_key, first_page, last_page, boundary_state ∈ {ESTABLISHED, UNASSIGNED, PROVISIONAL} per end,
          boundary_evidence[Citation], type, type_state, type_citation, body_key?, permitted, check_set (TYPE_CHECKS),
          declared_date{value [C], semantics (DATE_SEMANTICS), by, at, page, segment_key},
          entity{value [C], by, at, citation}?, basis{STANDALONE|CONSOLIDATED|NOT_APPLICABLE, by, at, citation}?,
          status, refusals[]
Citation  file_sha256, pdf_page_index, text_of_record_id, char_start, char_end, bbox?, reading_source,
          printed_label? (own source), quote [C], flags[]
Cell      cell_key, segment_key, column, value? [C], value_citation?, binding_citations[row, column, units]?,
          pages_read[], witnesses[], gate_trace[(gate, result)], provenance_kind ∈ {DOCUMENT_SPAN, USER_FACT},
          state, refusals[], residency_trail[(adapter, region, consent_ref?)], value_key,
          runs[(run_id, proposal_sha256)], attestations[(who, when, value_key, decision, reason [C])] (append-only)
Refusal   RefusalRecord [R] + RefusalDetail [C] (§3.1)
```

**Invariants (new tests).**
1. A `Citation` cannot be constructed without `file_sha256` and `pdf_page_index`. Offsets index into that page's text
   of record only.
2. A served cell has a citation, a gate trace with every applicable gate passed, and
   `pages_read ⊇ {citation page}`.
3. `NOT_FOUND` is constructible only when (a) `pages_read` covers the segment, every page in it is TRUSTED or
   OCR_PASSED, and **no page has any `DISAGREEMENT_REGION`, `MARK`, `FIGURE` or `model_written` region**; (b)
   image-ink coverage on every OCR page is accounted for by the union of reading tokens (signal: rendered ink area
   outside every token bbox; `THRESHOLD = None`, so unaccounted ink gives `REGION_UNREAD` and fails closed); (c)
   `RECALL_THRESHOLD` for the column family is set from a labelled measurement; and (d) at least two independent
   extractors made no proposal. Today (c) fails, so constructing `NOT_FOUND` raises.
4. Every refusal below FILE scope carries a page.
5. A printed label never appears in an identity field.
6. **No unkeyed hash of client content is persisted.** A span hash is as reversible by dictionary as a hash of the
   short value it contains (a CIN, a figure), and an unkeyed `file_sha256` joined against hashes of public filings
   reveals which deal a tenant's matter concerns (INFERRED; R5 lists A1's URL). Persisted file, page and span
   identifiers are `HMAC(tenant_secret, ·)`, with the secret destroyed when the tenant is crypto-shredded. Where that
   secret is held is KMS-dependent, and KMS India rows are U (G13). Unkeyed hashes exist in session memory only.
7. A `Cell` in a segment with no declared `entity` cannot reach a served state. Test: a B-11-shaped fixture (three
   companies' statements, one index entry) yields no served cell.
8. A page in a range whose boundary failed is `UNASSIGNED`, and no segment's range includes it (A1-shaped test,
   §3.7).
9. No check runs on a segment type absent from its `TYPE_CHECKS` entry.

---

## 5. Provider abstraction

### 5.1 Contracts

```
ReadingProvider.read(pages, *, script, mode) -> list[Reading | PageFailure]   # exactly one per page sent
ExtractProvider.extract(document, *, schema) -> (Proposal, CallMeta)          # the built reasoning.Proposal shape
```
Reading and extracting fail differently, and the research covers only reading (G02, G13).

### 5.2 Registry record, one per (provider, account, region)

This is PLAN_11 D3, NOT BUILT. Every field is a triple `(value, marker, row_id)`. The registry covers **every
component that receives file bytes, page images, text or hashes**: readers, extractors, classifiers and the malware
scanner (§3.2).

`tenant_eligible(adapter, policy)` is a pure function that runs at call time and returns true only when **both**
checks pass:
1. **Marker check.** Every eligibility field is SOURCED or backed by a contract reference.
2. **Value check against the tenant policy.** `region` and `processes_in_region` are inside the policy's allowed
   regions; `cross_region_routing == none`; `training_use == none` or `training_opt_out_verified == true`;
   `retention` is within the policy maximum; `generative` is consistent with the witness role; and the account's
   provider-side settings are at least as strict as the policy (§3.1).

Tests: one per UNVERIFIED field (marker check); a fully SOURCED out-of-India adapter (Google `us`, R4 G5) is refused;
a SOURCED "may store in another region unless opted out" value (Textract, R4 G1) is refused; a SOURCED "trains unless
opted out" value (Sarvam, R3 H7) is refused.

| Field | Values today |
|---|---|
| `region`, `processes_in_region` | Azure DI `centralindia`, processed in resource region (R4 E3, E5) |
| `cross_region_routing` | Textract may store content in another region unless opted out (R4 G1) |
| `retention`, `delete_call_required` | Azure DI 24 h, deletable (R4 G3); Google online in memory, batch TTL ≤1 day (R4 G5); Sarvam per workspace, Doc AI coverage UNVERIFIED (R3 H4, H5) |
| `training_use`, `training_opt_out_verified` | Google none (R4 G5); Textract unless the org opts out (R4 G1, G2); Sarvam contradictory (R3 H7–H11); Azure DI not stated (R4 G4); OCI UNVERIFIED (R4 G6) |
| `zdr_contracted`, `contract_status` | UNVERIFIED for all (G16) |
| `preview_or_ga`, `model_version` | Google `asia-south1` OCR is `v2.1.1 (Preview)` only (R4 E6); the version is recorded per page |
| `max_pages_per_request` | Sarvam 10 (R3 D9); Google 15 online, 30 imageless, 500 batch (R4 D6); Textract sync 1, async 3,000 (R4 D1); OCI 5 sync (R4 D7); Azure 2,000 (R4 D4); Sarvam self-hosted 500 (R3 F2) |
| `rate_limit` | Sarvam 10 req/min (R3 E11); Textract Mumbai 5 TPS (R4 D3); Azure analyze 15 TPS default (R4 D4). R3 E11, R4 D4 and R4 D6 were not re-checked (G22) |
| `scripts_printed`, `scripts_handwritten` | R4 A5, A8, B2, B3; R3 C1 |
| `returns_confidence`, `returns_bbox`, `emits_model_text`, `generative` | R4 C1; R3 E10, F3, D7. `generative` is INFERRED from product type; no R3 or R4 row states any vendor's architecture, so for the non-generative witness rule it is UNVERIFIED for every cloud reader (§3.5) |
| `partial_failure_states` | R4 D2, D5; R3 E6 |
| `requires_customer_object_storage` | Azure DI batch: Blob (R4 D5). OCI async: Object Storage (R4 D7). Google batch: INFERRED, not stated in R4. Textract async input source: UNVERIFIED (R4 D1 is silent) |

Registry rules:
- An adapter with `emits_model_text` must return that text in a separate field, or it fails its contract test.
- No adapter may be both witnesses for one page.
- `router.route()` stays deterministic and refuses rather than substituting. **For any tenant document it filters
  candidates through `tenant_eligible(adapter, policy)` and refuses if none remain.** BUILT fact: `router.py` routes
  `(PAGE_IMAGE, LOW)` to Gemini Flash with the rationale "free tier", and `gemini_model.py` uses AI Studio when no
  project is set, whose data use is UNVERIFIED. No free-tier row is reachable by tenant content.
- Model IDs are checked against the vendor's list on the day they are configured (PROVIDER_DECISION §7).
- `router.py`'s `PAGE_IMAGE → Gemini` rationale rests on a benchmark that R4 I4–I6 qualifies (G23). It is not reused
  as evidence here.

### 5.3 Adapters as the evidence stands

| Adapter | Tenant-eligible? | Blocking field |
|---|---|---|
| `native_pdf_text` | Yes, but its pages cannot serve until `NATIVE_TRUSTED` is measured | G05 |
| Azure DI Read/Layout, Central India | **No** | Training use not stated (R4 G4). Delete-after-fetch must also be enforced and alarmed (R4 G3) |
| Google Enterprise OCR, `asia-south1` | **No** | Preview terms unchecked (R4 E6, unresolved 3). **`processes_in_region` UNVERIFIED**: R4 E6 shows only that the location is listed, and R4 G5 says online requests are processed in memory without naming a region. Added to the G13 and R8 vendor questions |
| Google, `us` | **No** | Value check: `region` outside the tenant policy (every other field SOURCED, R4 G5), so a signed contract alone does not make it eligible |
| Textract, `ap-south-1` | **No** | Org opt-out not verified (R4 G1, G2); operational storage beyond the 7-day `JobId` undocumented (R4 G7); Latin only (R4 A1) |
| OCI Document Understanding | **No** | No Indic language (R4 A10); retention undocumented (R4 G6) |
| Sarvam managed | **No** | R3 H2, H5, H7; H1 condition |
| Sarvam self-hosted | **No** | Region (R3 F6); parity (F7) |
| `anthropic_model`, `gemini_model` | **No** | Region, retention, ZDR, input limits (G02) |
| `azure_model` (UAE North, Azure for Students) | **Never** for tenant documents | Outside India. This is a constraint of this account, not of Azure; the offer's regional policy is undocumented (G13) |
| Deterministic proposers | Yes, as proposers; not yet as witnesses | Recall and precision unmeasured (§3.10) |
| Malware scanner | **No** engine chosen | G17. Only a local, network-isolated engine without hash lookup is admissible (§3.2); any cloud scanner is BLOCKED |

### 5.4 When no eligible reader exists in India

The tenant policy is set once per tenant and may be narrowed per matter. The system never widens it.

| Exit | Mechanism | Cell carries | Status |
|---|---|---|---|
| A. Abstain (default) | `NO_COMPLIANT_READER(script, page)` | Page and script | Buildable |
| B. Self-hosted in India | Sarvam Vision on SageMaker in our VPC (R3 F1; region UNVERIFIED, F6), or an Azure DI connected container on our compute. The container sends billing data to Azure (R4 H1); whether any content leaves is UNVERIFIED. Disconnected containers need strategic-customer approval (R4 H2) | `reading_source = OCR:<selfhosted>:<version>:<our region>` | BLOCKED on F6 or on a container egress check |
| C. Human transcription | Transcription task in the review queue | `USER_FACT`, attributed | Buildable; bound by labour |
| D. Out-of-India with consent | A written per-matter consent naming adapter, region and retention, stored as a reference. Consent waives only the region clause of the value check; it **never** waives training, retention, contract or marker preconditions. It must reference the authorisation of the party whose data it is, not only the tenant's. PLAN_07 §3 names our customer as the Data Fiduciary; whose authorisation is needed when that customer is a law firm acting for a client company is OPEN (G14). Extraction providers are under the same rule; until G02 closes, exit D is unavailable for them | `residency_trail` with `consent_ref`; the export states "processed outside India for pages …" | **BLOCKED** on G16 (`zdr_contracted`, `contract_status` UNVERIFIED for every provider, §1 item 7) and on the §5.2 value check being built. Never automatic |

---

## 6. Multi-cloud India mapping

**G13 applies: outside OCR almost nothing is sourced, and this table says so rather than filling cells.** U =
UNVERIFIED, meaning no research file covers it; it does not mean "unavailable". — = absence SOURCED on the page
named. Inside a cell, a bare row ID belongs to the research file named first in that cell, so "G3" after "R4 E3" is
R4 G3. Gap IDs always have two digits (G02).

| Region | OCR / document AI | Layout | Extraction LLM | Object storage · KMS · queue · malware scan |
|---|---|---|---|---|
| AWS `ap-south-1` Mumbai | Textract endpoint and price list (R4 E1, E2); six European languages only, no Indic (A1); 5 TPS (D3); may store and use inputs cross-region unless org opt-out (G1, G2). Sarvam SageMaker region U (R3 F6) | Textract Tables $15/1k, Layout $4/1k (R4 F1); English-trained | U (G02) | U (G13, G17) |
| AWS `ap-south-2` Hyderabad | — Textract absent from endpoint table and price list (R4 E1, E2) | — (E2) | U | U |
| Azure Central India | DI: 76 price meters (R4 E3); processed in region (E5); Read $1.50/1k (F3); printed Indic per A5; no Indic handwriting (B2); 24 h deletable retention (G3); training not stated (G4). Sarvam managed runs here per its Trust Center, "for Indian customers" (R3 H1; G22), with a ToS transfer reservation (H2) | Layout (R4 C3); Batch Layout and Pre-built $10/1k (F3); online Layout meter U | U (G02). This repository's Azure LLMs are in UAE North on Azure for Students (`azure_model.py`), an account constraint | Blob for DI batch exists as a service (R4 D5); India row U |
| Azure South India | 0 DI price meters (R4 E3); availability U (E4) | U | U | U |
| GCP `asia-south1` Mumbai | Enterprise OCR `v2.1.1 (Preview)` only (R4 E6); online in memory, batch TTL ≤1 day (G5); $1.50/1k after a free tier of 1,000, period U (F6, F7) | **Layout Parser: no row** (E6); Form Parser for Hindi, Marathi, Nepali (A9) | U (G02; the Vertex default location in `gemini_model.py` is `global`) | U |
| GCP `asia-south2` Delhi | — Document AI not listed (R4 E7) | — | U | U |
| OCI Mumbai / Hyderabad | Hosted in OC1 commercial regions (R4 E8); India hosting INFERRED (E9); no Indic (A10); retention U (G6) | English-only (A10) | U | Object Storage for async exists (R4 D7); India row U |

**What the table supports (INFERRED).**
- No cloud row supports an end-to-end in-India claim today, because every non-OCR column is U.
- Azure Central India is the only row with SOURCED in-region processing and SOURCED retention for Latin and printed
  Devanagari OCR. It is still disabled on R4 G4.
- The only documented India-region pair that gives two Devanagari witnesses without Sarvam is Azure Central India plus
  Google `asia-south1`, and one half of that pair is Preview.
- No buyer evidence says multi-cloud is required (G13). A single-cloud deployment is the INFERRED minimum, pending R6
  (G02) and R8 (G13).

---

## 7. G01: both branches (founder decision; neither chosen)

PLAN_07 §1: "a client document must never be written to durable application storage." Bulk review wants queues,
per-page state, batch OCR inputs and review lasting several days (G01). The pipeline, gates, refusal envelope, keys,
data model and provider preconditions are **identical** in both branches. The branch decides only where `[C]` fields
live, for how long, which `work_queue` backend runs, and whether adapters with
`requires_customer_object_storage` are usable.

### 7.1 Artefact classes

| Class | `[C]`? | Branch A (ephemeral) | Branch B (durable, controlled) |
|---|---|---|---|
| Raw bytes, rendered pages, readings, text of record, native exhibits | Yes | Session memory only | Tenant store, per-tenant key, tenant-set retention |
| Routes, signals, gate outcomes, page keys, segment ranges and types, scope routes | No | Persist if `releasable()` passes | Stored |
| Title spans, quotes, cell values, declared dates, entities, refusal details, reviewers' written reasons | Yes | **Cannot persist** | Stored, per-tenant key |
| `RefusalRecord`: code, keyed file id, page index, bbox, stage | No (PLAN_07 §1 permits hashes; only keyed hashes, §4 invariant 6) | **Persist.** The page-naming abstention outlives the session. No free text | Stored |
| Attestations: who, when, `value_key`, decision | Value and reason excluded | Persist without value or reason | Persist with value and reason |
| Azure pending-delete records: operation id, adapter, submitted_at | No | Persist until the Delete is confirmed (§3.5) | Same |
| Page-content and file hash cache | Hash only, but equality reveals possession, **within a tenant as well as across tenants**: an unkeyed `file_sha256` matched against public filings names the deal (INFERRED) | Per session, unkeyed; persisted only as keyed hashes | Per tenant, keyed; **never cross-tenant** |
| Provider-side temporary storage | Yes | Azure from submission until Delete succeeds, and up to 24 h if Delete fails or is never called (R4 G3); Google online none (R4 G5) | Adds batch inputs: Azure Blob (R4 D5), Google batch TTL ≤1 day (R4 G5) |
| Logs, backups | Must hold none | Codes only | Backup deletion semantics OPEN (G15) |

### 7.2 Branch A: ephemeral only (PLAN_07 §1 unchanged)

- **Runs** one long-lived in-memory session worker per matter run, on `SessionBackend`. Nothing is written to disk.
  INFERRED control: swap disabled or encrypted, UNVERIFIED on any host.
- **Allowed OCR paths.** Only online calls: Azure analyze with immediate `Delete Analyze Result` and an alarm;
  Google online at ≤15 pages per call.
- **Forbidden OCR paths.**
  - Azure batch (Blob, R4 D5).
  - OCI async (Object Storage, R4 D7).
  - Google batch (persists up to a day, R4 G5).
  - Textract async: the `JobId` is valid for 7 days (R4 D2) and operational storage is undocumented (R4 G7).
- **Delivers** the full table to the user as an export they hold (§3.12 export schema). The export is **streamed
  from session memory in the authenticated response**, with no temp file, bucket, pre-signed URL or cache; a
  "temporary" object with lifecycle deletion is retention followed by deletion. Test: the export path performs no
  filesystem or object-store write. We keep `RefusalRecord`s, cell keys, state counts and attestations without values
  or reasons.
- **Costs.** A dropped session loses the run, and a re-run pays full OCR and extraction. A 512-page bundle must
  finish inside one session, bounded by quotas (§9.3), with no end-to-end time measured. Review happens in-session
  or on the export, where our attestations cannot bind to values. On re-upload we can name the pages that abstained
  last time, not the values that changed. Azure's residual retention after a failed Delete is "retention followed by
  deletion"; the contract must name it, or Azure is disabled.
- **Forbids** batch OCR; durable queues; background completion; review over several days or by several reviewers;
  `INVALIDATED_BY_CHANGE` on stored verdicts; cross-document deduplication.
- **Keeps** the application-level ZDR claim in Harvey's sense (PLAN_07 §1; R1 D6) **for application storage only**,
  and the core artefact, which is the page-naming refusal. A run that used Azure cannot carry a provider-level
  zero-retention claim: Azure holds input and result from submission until Delete, and up to 24 h if Delete fails or
  is never made (R4 G3). The pending-delete sweeper (§3.5) is what bounds the second case.

### 7.3 Branch B: durable, with named controls (requires a PLAN_07 §1 amendment)

Each control is a precondition. One unmet control blocks tenant uploads.
1. Retention per artefact class (§7.1), tenant-set under a published maximum. Defaults OPEN.
2. A schema or database per tenant (PLAN_07 §2). A per-tenant key. Deletion by crypto-shredding plus object deletion.
   Backups inside the deletion semantics, which are OPEN (G15). KMS India rows U.
3. Queues carry identifiers and hashes only, and workers fetch content from the tenant store. A guard in the style of
   `releasable()` runs on every message schema.
4. Batch OCR inputs go to a tenant-scoped, region-pinned bucket with lifecycle deletion. That is named as retention
   followed by deletion.
5. Provider calls keep every §5.2 precondition, checked at call time.
6. No training or evaluation use of tenant content. `annotation.to_sft()` stays dormant (CLAUDE.md E6).
7. Hash caches per tenant only; no cross-tenant statistics (R2 item 11).
8. Access and processing events go to the event log, without content.
9. Every content-holding dependency is region-pinned. No residency claim is made until every §6 row on the route is
   SOURCED (G13).
10. Operator obligations that may *require* retention (CERT-In, DPDP processor duties) are checked before durations
    are set. They are U (G14).

- **Enables** `DurableBackend`; batch OCR (Azure 10,000 documents per request, R4 D5; Google 500 pages, D6);
  resumption from the first missing key; per-tenant page cache; review over several days; `INVALIDATED_BY_CHANGE`;
  re-audit through `event_log.affected_by`.
- **Costs** an amended PLAN_07 and a weaker confidentiality statement; storage, KMS and deletion engineering with
  unsourced India rows; unresearched regulation; a larger breach surface.
- **Forbids** any "zero retention" claim for F8; cross-tenant deduplication even of public filings; content in queues
  or logs.

A Branch B tenant with every retention set to "session" behaves like Branch A. That makes A a configuration of B
**only once B's controls exist**. Building against the `work_queue` interface with `SessionBackend` first loses
nothing either branch needs.

---

## 8. Failure modes

| # | Failure | Caught at | Refusal | What still escapes |
|---|---|---|---|---|
| 1 | Page tree mis-enumerated (object streams) | S2 two enumerators | `PAGE_COUNT_DISAGREEMENT` | Both enumerators wrong in the same way |
| 2 | Scanned page read as empty → "not in document" | S3 routes; coverage invariant | `ABSTAINED(COVERAGE_INCOMPLETE, pages)` | None while the invariant test holds |
| 2a | Value present on a read, trusted page, but no extractor proposes it → "not in document" | `NOT_FOUND` unreachable without measured recall and two non-proposals (§1 item 3) | `ABSTAINED(ABSENCE_UNVERIFIABLE, pages_read)` | Two extractors with correlated misses, once recall is measured |
| 3 | Corrupted text layer passes the heuristic (R5 C-1, C-3) | `NATIVE_TRUSTED` unreachable; agreement check | `TEXT_LAYER_CORRUPT` | Native and OCR wrong identically (unmeasured) |
| 4 | Units or scale line corrupted; figures ×1,000; share counts ×100,000 | Scale rule on every reading; no header fallback where any reading shows a local expression; gate g on binding citations | `UNITS_LINE_UNTRUSTED`, `UNITS_UNRESOLVED`, `SCALE_UNRESOLVED` | Units change mid-statement with no expression in any reading |
| 5 | Low-dpi misread, or region skipped | S4 agreement; ink-coverage signal | `OCR_READINGS_DISAGREE`, `REGION_UNREAD` | **Correlated error and correlated omission**, the main residuals; unmeasured |
| 6 | VLM invents text (R4 I8) | Never the sole witness | `SINGLE_WITNESS` | A VLM agreeing with a wrong non-generative reading |
| 7 | Provider writes descriptions (R3 D7) | Quarantine | Structural | An adapter emitting unlabelled model text; contract test per adapter |
| 8 | Stamp or seal text mixed into content | `OVERLAPS_MARK` | Region abstention | No detector (G20) |
| 9 | Script with one or no eligible reader | Router; `tenant_eligible` | `NO_ELIGIBLE_SECOND_WITNESS`, `NO_COMPLIANT_READER` | None; the cost is coverage |
| 10 | Partial or silent page drop | Reconciliation | `OCR_PROVIDER_PAGE_FAILED`, `PAGE_MISSING_FROM_READING` | A page returned with another page's content (UNVERIFIED) |
| 11 | Printed page ≠ PDF index; spreads (R5 E-2) | Identity rule | — | A misdetected spread; the index citation is still correct |
| 12 | CCI order or valuation report gets Companies Act checks | S6 before S7; failed boundary → `UNASSIGNED`; deterministic type only; S8 invariant; `TYPE_CHECKS` | `SEGMENT_BOUNDARY_UNCERTAIN`, `CLASSIFICATION_UNCERTAIN`, `BODY_NOT_HELD` | A confident wrong boundary on a grounded heading at the top of a page |
| 12a | Figures attributed to the wrong company or basis in a multi-company segment | Declared `entity` and `basis`; gate k refusal; no `CompanyProfile` fill from cells | `SEGMENT_ENTITY_UNDECLARED`, `SEGMENT_BASIS_UNDECLARED` | A human declaring the wrong entity |
| 13 | Body or rule not held | S8 | `NO_BODY_DECLARED`, `RULE_NOT_HELD` | — |
| 14 | Repeated string (running header; standalone vs consolidated figure) | Gate f; S5 header marking | `SPAN_LOCATION_AMBIGUOUS` | Non-header repeats within one page |
| 15 | Prior-year column served as current year | Gate h mandatory for numeric cells; period binding; gate g on the header citation; gate i | `TABLE_MISBOUND`, `TABLE_BINDING_ABSENT`, `PERIOD_MISBOUND`, `DISAGREEMENT_REGION`, `EXTRACTION_WITNESSES_DISAGREE` | Both witnesses and the table model misread the header chain identically, on an agreed header |
| 16 | Model's date drives `DOCUMENT_DATE_CONFLICT` | Human-declared date | `SEGMENT_DATE_UNDECLARED` | A reviewer rubber-stamps the prefilled proposal (automation bias; unmeasured) |
| 17 | Instruction printed in a scan or native layer | Clause; detector on every reading; `INJECTION_SUSPECT` holds cells for review and blocks provider calls on the page | `INJECTION_SUSPECT` (page N) | An instruction the detector does not recognise. **Extraction witnesses share injected inputs, so they are not independent against injection**; a single-witness text column needs only one steered extractor. Image-borne injection steering a VLM witness (open, CLAUDE.md) |
| 18 | Hostile or encrypted PDF; decompression or pixel bomb | S1 fixed order; sandboxed subprocess; pixel and render-memory limits | `PARSER_LIMIT_EXCEEDED`, `IMAGE_DIMENSION_EXCEEDED`, `SANDBOX_LIMIT_EXCEEDED`, `MALWARE_*`, `ENCRYPTED_PDF` | Vulnerabilities in the chosen parser or sandbox (G17) |
| 18a | Signed file with content redefined in an appended update (shadow attack) | Per-page object resolution through the final xref, or every page flagged | `UNSIGNED_INCREMENTAL_CONTENT` | Resolution bugs; needs a fixture |
| 19 | Adapter state drifts, or a Delete call fails or is never made | Call-time check; pending-delete record and sweeper; alarm | `PROVIDER_PRECONDITION_UNVERIFIED`, `READER_RETENTION_DELETE_FAILED`, `READER_RETENTION_DELETE_UNCONFIRMED` | No vendor API exposes account state; retention until Delete, up to 24 h (R4 G3) |
| 19a | Client file treated as public evaluation | `PUBLIC_EVAL` derived from manifest hash and acquisition route only | Adapter refusal | An operator mis-recording an acquisition |
| 20 | Session lost or rate-limited (Branch A) | Token buckets; session close | Table marked `INCOMPLETE_RUN`, unprocessed pages listed | Re-run cost |
| 21 | Abstention makes the table useless | Per-class metric | Reported, never auto-tuned | A product judgement (§11) |

---

## 9. Cost and latency (ranges; every input is a row or marked)

LLM extraction cost, extraction quotas and end-to-end time are **UNVERIFIED** (G18). Nothing below is a
measurement. Pricing is per document checked, never per cell answered (PLAN_07 §4), so abstention does not reduce
revenue.

### 9.1 Per 100 pages sent to external OCR, this design's configuration

External readers receive only `NO_TEXT` and `NATIVE_UNTRUSTED` pages. The native-layer check on text pages uses local
R1 with no network call (§3.5).

| Item | Unit price (row) | Arithmetic (INFERRED) | Range |
|---|---|---|---|
| Azure DI Read, Central India | $1.50 / 1,000 (R4 F3) | 100 pages | $0.15 |
| Google Enterprise OCR (second witness) | $1.50 / 1,000 after a free tier whose period is U (R4 F6, F7) | 100 pages | $0.00–0.15 |
| Azure Layout, tabular pages | $10 / 1,000 (R4 F3; which meter online Layout bills is U) | 33 pages (B1 FS share, R5 E-4) to 100 | $0.33–1.00 |
| Sarvam Digitise (public evaluation only) | ₹0.50 / page (R3 G1) | 100 pages | ₹50 |
| Local OCR witness | Compute | U | — |
| LLM extraction, two witnesses | U (G18). `anthropic_model.PRICING` exists; its source was not checked | BLOCKED until a token-count dry run over A1/B1 text | — |
| Human review | U | — | — |

OCR plus layout with two witnesses comes to **≈ $0.48–1.30 per 100 pages** at list price. That excludes extraction,
storage and human time.

### 9.2 A1, 512 pages

- External OCR on `NO_TEXT` and `NATIVE_UNTRUSTED` pages only: from the measured lower bound of 123 pages (106
  image-only plus ≥17 corrupted, R5 E-A, C-4) up to all 512 if every native page failed the local check.
  123–512 × $0.0015 × (1–2 paid engines) = **$0.18–1.54**. Local R1 on the remaining text pages: compute, U.
- Layout on 269 FS and results pages (R5 E-B) up to all 512: **$2.69–5.12**.
- OCR plus layout: **≈ $2.87–6.66**.
- Sarvam Digitise, if it were enabled: ₹256.
- Self-hosted Sarvam: $10/hr software fee plus instance (R3 F5); throughput U.

**Reading of these numbers (INFERRED, agreeing with R4 F10).** OCR price does not decide this architecture. Layout on
every page, LLM extraction, eligibility and accuracy on our paper do.

### 9.3 Latency lower bounds from quotas (INFERRED arithmetic; processing and queueing excluded)

Rows below assume all 512 pages are sent, an upper bound; at the 123-page lower bound the submission floors scale
down proportionally.

| Path | Limit (row) | A1, 512 pages |
|---|---|---|
| Sarvam managed | 10 pages/job (R3 D9), 10 req/min (E11) | 52 jobs → ≥5.2 min of submissions; longer if polls count (R3 G4) |
| Textract sync, Mumbai | 1 page/call (R4 D1), 5 TPS (D3) | ≥103 s |
| Azure analyze, single-page submissions | 15 TPS default (R4 D4) | ≥35 s |
| Google online | 15 pages/call (R4 D6); `asia-south1` quota U | 35 calls |
| LLM extraction; human review | U (G02, G18) | — |

---

## 10. What is blocked, and the build sequence

### 10.1 Not buildable until the gate closes

| Item | Gate |
|---|---|
| F8 served to any lawyer; the six-weeks-or-research-project call | 20-document test (PLAN_05 Phase 3); Phase 0 "useful or annoying" falsifier |
| Any tenant document entering S0 | G01, G17 (including a local, network-isolated scanner engine) |
| `NOT_FOUND` on any column family | Recall measured on a labelled set per family (G06); `RECALL_THRESHOLD` set by a human |
| Exit D (out-of-India with consent) | G16; §5.2 value check built; G14 for whose authorisation counts |
| Deterministic proposers counting as witnesses | Precision measured on a labelled set |
| Any served cell in a CAA-governed segment (`SCHEME`, notice, explanatory statement, s.232(2)(c) report, scheme order) beyond extract-and-cite | G03 |
| OCR gate threshold; `NATIVE_TRUSTED`; `OCR_PASSED`; any served OCR-derived cell | G04, G05; founder keys with retention and opt-out set first |
| Table-cell accuracy claims; any F8 threshold | G06; G07 |
| `EXTRACT_AND_VERIFY` on scheme, notice and FS segments | G03 |
| Any tenant document to an extraction provider | G02 (R6) |
| Any tenant document to an OCR provider | G16 plus the §5.3 blocking field per adapter |
| VLM rung | G12 |
| Script-router rows beyond Latin and Devanagari | G09 |
| `DurableBackend`, batch OCR, review over several days; queue, store and quota sizing | G01; G08, G18 |
| Any residency claim | G13 (R8), G14 |
| Stamp detector; non-PDF formats; citing limits externally | G20; G21; G22 |

**The eight Tier 1 (blocking) gaps are G01–G08.** None closes by writing code.

### 10.2 Buildable now

Public documents only, stdlib first, TDD, one logical change per commit, serving routes untouched, no keys.

| Step | Work | Done when |
|---|---|---|
| 0 | Measurements with no serving code: D1 text-layer census; script census (G09); page-label and spread census (G11); `pdf_signature` census (G20). Acquire one A1-class fixture under ACQUISITION_POLICY (R5 action 1) | Per-page tables with hashes, labelled "not the 20-document test" |
| 1 | `Citation`, `Page`, `RefusalRecord`/`RefusalDetail` dataclasses with `[C]` tags and closed persisted schemas; invariants 1, 4, 5, 6; schema refusal of a sub-40-character figure and a written reason; persistence after `close()` raises | Tests RED → GREEN |
| 2 | ~~D2 page anchoring: offset map over `pdf_text.extract_pages`; gate f.~~ **Not buildable now — BLOCKED on D-002.** `extract_pages` agrees with an independent reader on 0 of 14 corpus PDFs (`9010605`), so an offset map over it would anchor spans to wrong pages. After the reader decision: offset map over the chosen reader; gate f; replay every stored realrun proposal and report new refusals on correct facts | Reader decision recorded; then replay report committed; single-page callers unchanged |
| 3 | S2 two-enumerator check. The second dependency is stated first, or deferred with `PAGE_COUNT_UNCHECKED` recorded | Refuses on a synthetic disagreement fixture |
| 4 | S3 pre-filter and route recording, with `NATIVE_TRUSTED` unreachable | A1 pp.445, 493, 505 route away from trusted; no page reaches trusted |
| 5 | D3 registry with §5.2 records and `tenant_eligible` (marker check and value check); `router.route()` filtered through it; `PUBLIC_EVAL` derived from manifest hash only | One test per UNVERIFIED field; SOURCED-but-disqualifying values refused; no adapter accepts a non-`PUBLIC_EVAL` document; a tenant upload matching a manifest hash is refused; no eval adapter is callable on a non-manifest hash |
| 6 | Stage keys and `work_queue` with `SessionBackend`: lanes, token buckets from registry rows, retry-once, partial-failure mapping, `HELD` release rule | Stub providers emitting `partially_completed` and 429s; a changed boundary orphans held cells |
| 7 | S6–S8 deterministic parts: segment and type registries, `SEGMENT_BODY` (all 19 types), `TYPE_CHECKS`, `DATE_SEMANTICS`, failed-boundary `UNASSIGNED` rule, entity and basis declaration records, invariant tests | A CCI-order fixture never reaches a CA2013 check; an AGM check never runs on an explanatory statement; pp.433–491 `UNASSIGNED` on the A1-shaped fixture; a B-11-shaped fixture yields no served cell; A1 segmented against its index, n=1 |
| 8 | Cell state machine with ABSTAINED as default, `NOT_FOUND` unconstructible, `ABSENCE_UNVERIFIABLE`, `value_key` attestations, export schema, and the F8 metric | Metric prints LEAKED (all served states) and OVER_REFUSED per class; export of an abstained cell carries code and page; export path writes nothing to disk |
| 9 | S10 gates g–i as stubs that always abstain until S4 exists (g covering binding citations; h mandatory for numeric cells); `SEGMENT_DATE_NOT_BOUND` wrapper; `ocr_gate` with `THRESHOLD = None`; segment-date declaration record voided on `segment_key` change | Constructing a served state without a full gate trace raises; a changed boundary voids the declaration |

### 10.3 After the gates close, in order

1. **G01** → harden `SessionBackend` for long runs, or build `DurableBackend` with the §7.3 controls.
2. **G04/G05 bake-off** → curves per script and dpi band; thresholds proposed for human sign-off, or kept None by
   `calibration_contract`; enable `NATIVE_TRUSTED` and `OCR_PASSED`; build adapters whose preconditions verify.
3. **20-document test.**
   - **Handling rule.** The buyer's documents are confidential (CLAUDE.md: do not obtain confidential company
     documents). They are measured only by local, non-networked tooling (text-layer, script and page-label census)
     run on the buyer's premises, or we receive only the resulting per-page tables with no content. No provider
     adapter, eval harness (`eval/realrun/azure_model`, Ollama, the Google `us` bake-off path) or step 0–9 tool with
     a network path receives those documents. The registry test "no eval adapter is callable on a non-manifest hash"
     (§10.2 step 5) enforces this in code.
   - Typed English → S4 is used mainly for the layer check, and S5 and S9 proceed.
   - Scanned, stamped or mixed-script → scope the OCR tier as a research project (PLAN_05), with those page classes
     abstaining.
4. **G02** → wire extraction on adapters whose preconditions are clean.
5. **G06/G07** → first F8 shadow run on labelled FS cells. **LEAKED (§3.12: any served state, including
   `EXTRACTED_UNVERIFIED`, `NOT_FOUND` and `NOT_APPLICABLE_TO_TYPE`) must be 0 on the labelled set before a lawyer
   sees any served cell.** Recall per column family is measured in the same run, before `NOT_FOUND` is enabled.
6. **G03** → enable `EXTRACT_AND_VERIFY` per type as each instrument is held.
7. **Review surface**, then a design partner.

---

## 11. Open questions

1. **G01.** Branch A or B? If B, the maximum retention per class. Do refusal records outlive content?
2. **Azure DI (R4 G4).** Is documented in-region processing plus deletable 24 h retention, with training silent,
   enough? Or is a written Microsoft answer required? This design requires the answer, so Azure stays disabled.
3. **Google `asia-south1` Preview.** Is it acceptable as a production witness once its terms are read? It is the only
   in-India path for six scripts (R4 E6, A8).
4. **Correlated error.** Is token-level agreement sufficient on ≈90 dpi scans, or do whole page classes need a third
   witness or human transcription?
5. **OCR every native page?** The native check runs on local R1 only and sends nothing out. Once the census and
   bake-off measure how often born-digital pages are corrupted, is the local check still justified? If local R1 is
   not accurate enough to be the agreement reader, the check would need an external reader and would send every
   client page to a provider; that case is a founder decision.
6. **Exits (§5.4).** Which may a tenant enable? Is exit D offered at all?
7. **Unheld bodies.** Should `EXTRACTED_UNVERIFIED` cells be shown for FS segments, or does showing them imply
   verification (PLAN_05 Phase 0)?
8. **Abstention rate.** What rate on a real bundle makes the table not worth delivering? Only the 20-document test
    and the Phase 0 lawyer conversation answer this, and no design parameter substitutes for them.

---

## What would falsify this design

Each item below, if observed, means a part of this plan is wrong, not merely untuned.

1. **Agreement does not catch what it is meant to catch.** In the bake-off, native-vs-OCR agreement fails to flag A1
   pp.445, 493 or 505, or two engines agree on wrong digits at a rate the risk–coverage curve cannot separate from
   correct pages. Then cross-reading agreement is the wrong primary signal, and §3.4–§3.5 must be redesigned around
   another witness, such as human transcription or XBRL.
2. **A served cell leaks.** A shadow run on a labelled set finds a LEAKED cell that passed every gate a–k from a
   correctly anchored page. The gate chain then has a hole this design did not name, beyond the one §3.11 states.
3. **Coverage collapses on typed paper.** On the buyer's 20 documents, if they are typed English, most cells still
   abstain. The abstentions would then come from the design (two witnesses, native pages unreachable, single
   witnesses refused) rather than from unreadable paper, and the lens costs more than it buys.
4. **Segmentation cannot be established.** On G08's recent bundles, deterministic candidates and index hints rarely
   coincide, so most pages sit in `UNASSIGNED` or uncertain ranges. Then "segment before type" needs a different
   mechanism, or F8 must accept one document per upload.
5. **Refusals are annoying.** The PLAN_05 Phase 0 lawyer calls page-naming abstentions annoying rather than useful.
   Thesis item 1 (§1) then fails on the product question, whatever the engineering says.
6. **Residency is not the constraint.** Buyers accept out-of-India processing under contract, or a regulated buyer
   class requires durable records that neither branch keeps. §5.4 and §7 are then solving the wrong problem.
7. **The page is not the right identity.** Real filings carry page trees on which two independent enumerators often
   disagree, or spreads are so common that `(file_sha256, pdf_page_index)` sends reviewers to the wrong half. §3.3
   then needs a region-level identity.
8. **Declared dates are rubber-stamped.** Review logs show reviewers accepting prefilled segment dates without
   opening the page. `DOCUMENT_DATE_CONFLICT` then checks the pipeline against itself again, and the declaration step
   must change.

---

## Red-team findings and dispositions

Applied 2026-09-14. Two red-team passes reused the IDs RT-01 onward, so they are listed as **Set 1** (gates,
segmentation, cells) and **Set 2** (security, residency, retention). Each finding was checked against this document,
the research files and the built code named in its evidence (`orchestrator._against_declared_date`,
`session.releasable`/`LEAK_WINDOW`, `pdf_signature._uncovered_ranges`, `router.py`, `gemini_model.py`,
`obligations.py`, `scope.py`). No finding was rejected. Where a finding overstated a fact, the fix uses the corrected
fact and the note says so. "Residual OPEN" names what still needs the founder or evidence after the text change.

### Set 1

| ID | Severity | Disposition | Where fixed; note |
|---|---|---|---|
| RT-01 | fatal | FIXED | §1 item 3; §3.11 k; §3.12 `ABSENCE_UNVERIFIABLE`; §4 invariant 3; §8 row 2a; §10.1. `NOT_FOUND` unreachable until recall is measured (`RECALL_THRESHOLD = None`) and needs two non-proposals; never feeds gate k. Residual OPEN: the labelled recall set (G06) |
| RT-02 | fatal | FIXED | §3.7 entity and basis; §3.11 k; §4 Segment, invariant 7; §8 row 12a. Confirmed: `obligations.py` generates rows from a `CompanyProfile`; R5 E-B lists B-11 as one component for three companies |
| RT-03 | major | FIXED | §3.7 failed-boundary rule; §4 invariant 8; §10.2 step 7 A1-shaped test |
| RT-04 | major | FIXED | §3.10 `SEGMENT_DATE_NOT_BOUND`, period binding; §3.11 e row corrected. Confirmed in `orchestrator.py`: no `document_date` fact → review returned unchanged |
| RT-05 | major | FIXED | §3.6 Providers row (S5 run choice no longer decides gate h); §3.11 h mandatory for numeric cells; `TABLE_BINDING_ABSENT`. Density signal carries no threshold |
| RT-06 | major | FIXED | §3.11 g applies to every binding citation |
| RT-07 | major | FIXED | §3.4 scale rule for every numeric column; `SCALE_UNRESOLVED` |
| RT-08 | major | FIXED | §3.4 units expressions detected on every reading; no header fallback where any reading shows a local token |
| RT-09 | major | FIXED | §3.6 Headings row; §3.7 Model row; §3.8 a model may confirm, never originate, a type |
| RT-10 | major | FIXED | §3.9 rows for `AGM_NOTICE`, `OFFER_DOCUMENT`, `COMPLAINTS_REPORT`; deterministic `NCLT_ORDER` case-number rule; invariant 5. The complaints-report body mapping and the IB case-number pattern are marked INFERRED |
| RT-11 | major | FIXED | §3.8 `TYPE_CHECKS` registry; §3.9 invariant 4; §4 invariant 9 |
| RT-12 | major | FIXED | §3.9 row 1: `EXTRACT_AND_CITE`, no check runs until G03; ss.230–232 checks refuse whole; invariant 6; §10.1 |
| RT-13 | major | FIXED | §3.10 `DATE_SEMANTICS` and the date each gate-k module takes; `DATE_ROLE_UNDEFINED`. Entries INFERRED, each needs a fixture |
| RT-14 | major | FIXED | §3.12 `NOT_APPLICABLE_TO_TYPE` only with both boundaries and the type established; `TYPE_BASIS` review item; counted in LEAKED. The finding's "B1 has no index" is not established by R5 (E-9 covers the outline only); the defect holds either way |
| RT-15 | major | FIXED | §4 invariant 3 (regions and ink coverage, threshold None); §3.5 bake-off records correlated omission; §8 row 5 |
| RT-16 | major | FIXED | §3.12 LEAKED defined over every served state; §10.3 step 5 |
| RT-17 | major | FIXED | §3.1 `value_key`, model-stage run records; §3.13; §4 Cell; §7.1 attestations |
| RT-18 | major | FIXED | §3.12 export schema and test; §7.2 |
| RT-19 | major | FIXED | §3.1 `RefusalRecord` [R] / `RefusalDetail` [C]; §4 preamble tests; §7.1. Confirmed: `orchestrator.py` puts `span[:60]` into the refusal; `session.releasable()` passes records when closed |
| RT-20 | major | FIXED | §3.4 M-T negatives marked UNVERIFIED, hand-labelled before use; unlabelled pages never reach `calibration_contract.assess` (a harness rule; the built function is unchanged) |
| RT-21 | major | FIXED | §3.2 Inputs; §3.5 `PUBLIC_EVAL` derived from manifest hash and acquisition route only; §10.2 step 5 test. Merged with Set 2 RT-06 |
| RT-22 | minor | FIXED | §3.10 a deterministic proposer is a witness only after measured precision; never two of the same pattern; §5.3 |
| RT-23 | minor | FIXED | §3.10 declaration only on a final `segment_key`, voided on change; §10.2 step 9 |
| RT-24 | minor | FIXED | §3.5 router row split. Confirmed: R3 C1 lists Bodo, Dogri, Santali but none of R4 A5's minor Devanagari languages |

### Set 2

| ID | Severity | Disposition | Where fixed; note |
|---|---|---|---|
| RT-01 | fatal | FIXED | §1 item 7; §5.2 marker check plus value check with refusal tests; §5.3 Google `us` row |
| RT-02 | fatal | FIXED | §3.1 closed persisted schema; §4 preamble (structural rule; `releasable()` is a second line; persistence after close raises); §3.13 reason is [C]; §7.1. Confirmed: `LEAK_WINDOW = 40`; closed session returns the record |
| RT-03 | major | FIXED | §3.5 pending-delete record and sweeper, `READER_RETENTION_DELETE_UNCONFIRMED`; §7.1; §7.2 ZDR claim limited to application storage; §8 row 19. Correction: with a successful Delete, R4 G3 retention lasts until the Delete, not 24 h; it is still retention followed by deletion |
| RT-04 | major | FIXED | §1 item 7; §3.2 Scanner row; §5.2 scope of the registry; §5.3 scanner row; §10.1. Residual OPEN: engine choice (G17) |
| RT-05 | major | FIXED | §3.2 fixed order, sandbox row, `IMAGE_DIMENSION_EXCEEDED`; §3.5 R0; §8 row 18. Limit constants UNSET; sandbox mechanism OPEN (G17) |
| RT-06 | major | FIXED | Same text as Set 1 RT-21: S0 accepts no provenance field; tenant uploads never carry `PUBLIC_EVAL` even on a hash match |
| RT-07 | major | FIXED | §10.3 step 3 handling rule; §10.2 step 5 registry test. Residual OPEN: whether the buyer accepts running local tooling on their premises |
| RT-08 | major | FIXED | §3.5 injection gate on every reading, cells `HELD`, no provider call on flagged pages; §3.1; §3.11 g; §8 row 17 names shared inputs |
| RT-09 | major | FIXED | §3.2 Flags row: per-page object resolution through the final xref, or every page flagged; shadow fixture; §8 row 18a. Confirmed: `_uncovered_ranges` is file-level |
| RT-10 | major | FIXED | §5.4 exit D BLOCKED on G16 and the value check; consent never waives training, retention or contract; extraction providers covered; §10.1. Correction: PLAN_07 §3 names our customer, not the client company, as Data Fiduciary; whose authorisation counts is recorded as OPEN (G14) |
| RT-11 | major | FIXED | §4 File `file_key`, invariant 6 (keyed HMAC, no unkeyed persisted hash); §7.1 possession within a tenant. Residual OPEN: where the per-tenant secret is held (KMS India rows U, G13) |
| RT-12 | minor | FIXED | §1 Cost of the lens; §3.5 R1 row (native check local only); §9.1 and §9.2 recomputed on 123–512 pages (INFERRED arithmetic on R5 lower bound); §9.3 note; §11 Q5 |
| RT-13 | minor | FIXED | §1 item 8; §3.1 no provider call before a segment is final and permitted; §3.10 Pass B |
| RT-14 | minor | FIXED | §3.1 unknown price refuses; §5.2 `router.route()` filters through `tenant_eligible`. Confirmed: `router.py` `(PAGE_IMAGE, LOW)` "free tier"; `estimate_inr` returns 0.0 for Gemini |
| RT-15 | minor | FIXED | §5.3 Google `asia-south1` row: `processes_in_region` UNVERIFIED, added to G13/R8 questions. Confirmed: R4 E6 is an availability row |
| RT-16 | minor | FIXED | §2 envelope re-marked INFERRED. Confirmed: R5 "What this means" is marked INFERRED |
| RT-17 | minor | FIXED | §7.2 export streamed from session memory, no temp object; no-write test |
| RT-18 | minor | FIXED | §3.1 per-tenant quota; strictest shared setting or per-tenant accounts; §5.2 value check. Residual OPEN: which of the two (a cost decision) |
| RT-19 | minor | FIXED | §3.5 only local R1 counts as non-generative until a vendor states architecture in writing; §5.2 `generative` UNVERIFIED for that rule |
