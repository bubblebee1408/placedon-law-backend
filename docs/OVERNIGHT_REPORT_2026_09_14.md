# Overnight report — 14 September 2026

Branch `loop/bookmark-godseye-v0`, pushed after every commit. **16 commits**, gate green at
every one (161 → 162 suites; one new suite added). Nothing on `main`. No cloud resource
created beyond the two you approved. Plan: [PLAN_11](PLAN_11_NEXT_MOVE.md). Working log:
`.claude/plans/loop-overnight-2026-09-14.md`.

Two usage-limit outages interrupted the run (≈14:00–16:20 and ≈17:10–21:20 IST). No work
was lost: partial results were found on disk and resumed, not redone.

---

## 1. Read this first — five things that change decisions

1. **The document checker was serving wrong answers, and four of those holes are now closed.**
   Real models found them, not hand-written tests. See §2.
2. **The strongest models leak nothing on the 18-case benchmark.** gpt-5-mini and
   Llama-3.3-70B on Azure: **0 leaks out of 18** each. The only errors are over-refusals, and
   one of those is our own gate's fault (§3).
3. **The repository's PDF page reader fails on modern PDFs.** `checker/pdf_text.extract_pages`
   agrees with an independent reader on **0 of 14** corpus documents. For example, it returns
   1 page for a 169-page file. Page-anchored citations for bulk review cannot be built on it
   (§4).
4. **Our "clean" test corpus contains OCR'd scans with wrong figures.** One scanner fixture
   carries them. `MANIFEST.md` said no document needed OCR. It is now corrected, and nothing
   was repaired (§4).
5. **Sarvam trains on your content by default** unless you opt out, and it reads at most
   10 pages per call. Both claims were checked word for word against Sarvam's own pages (§5).

---

## 2. Checker fixes — each found by a real model, each replayed before commit

| Commit | Hole | Found by | Now |
|---|---|---|---|
| `433ab7b` | An **empty** text value passed value-support (`""` is in every string). An empty CIN was **served** | llama3, T05 | Refused |
| `0023ce0` | A **company name** was accepted as a CIN | llama3, T04 | CIN must be well-formed. A damaged one is reported, never repaired |
| `522fdcc` | `field_binding` ignored text and date fields, e.g. a company class quoted from the incorporation sentence | llama3, T01 | Text and date fields covered, with the same "silence is not contradiction" rule |
| `f793bcb` | A board minute's **previous-meeting date was served as the document date**, although the orchestrator had been told the real date | the new served-value scoring, T05 | `DOCUMENT_DATE_CONFLICT`. The correction never reveals the date |

**The evidence that none of these over-refuses:** every stored model run was replayed
through the new gates. 0 cases changed for gpt-5-mini and Llama-70B. **Limit:** that is 33
served facts on synthetic documents.

**Instrument work** (`712c3c6`): the probe now scores what was **served** against the
document, not only how it was bound. Two of my own instrument bugs were caught and tested
before any number was kept.

## 3. Benchmark on Azure (`e7c3974`, `32284a0`)

| Model | Correct | Wrong refusal | Correct refusal | **Leaks** |
|---|---|---|---|---|
| gpt-5-mini | 16 | 1 (R03) | 1 | **0 / 18** |
| Llama-3.3-70B | 15 | 2 (R03, H03) | 1 | **0 / 18** |

**R03 was our bug, and it is fixed (15 September, on evidence).** The case says "Four
directors of the Company's **seven**". Integer value-support looked for a digit and found
none, and the old rule read only the *first* number.

1. **Raw proposals first.** The benchmark was changed to store every raw proposal, then re-run.
2. **What the re-run showed.** gpt-5-mini proposed **4** — the *present* count, which is
   wrong — from the full sentence. A words-only fix would have served that 4.
3. **The new rule.** An integer is read in digits or words, and is supported only when the
   span states exactly one number.
4. **Replay.** Llama-70B's R03 becomes **CORRECT** (7 served). gpt-5-mini's stays refused.
   **0 leaks**, and 0 changes on the text-probe runs.
5. **Trade-off.** A correct count sitting in a two-number sentence is now refused.

**The other refusals are now explained, and none is a checker bug:**
- **H03 (Llama):** the model misread Indian digit grouping by 10×, twice. Correctly refused.
- **H05 (gpt-5-mini):** the model *calculated* paid-up capital instead of quoting it.
  Correctly refused; this is the leak the case exists to catch.
- **H03 (gpt-5-mini):** ran out of its reasoning-token budget. Counted as an error, never as
  an empty answer.

The harness labels H03 and H05 as wrong refusals only because it counts any abstention on a
non-`must_refuse` case as one.

**Azure usage:** about 57 model calls in total, against a cap of 300.

## 4. The test corpus and the PDF reader (`9010605`, `583d11e`)

A two-reader census of all 14 corpus PDFs (514 pages), comparing the repo reader with
pdfplumber:

- **The repo's page reader is blind to modern PDFs.** Page objects sit inside compressed
  object streams, which a byte regex cannot see. Examples: 0 pages returned for a 179-page
  file, 37 for a 22-page file. **Whole-document `extract_text` works on all 14**, so the
  acquisition and registration scripts are unaffected. Only the per-page callers
  (`scripts/review.py`, `scripts/parse_board_rules.py`) are exposed.
- **17 pages are OCR over a scan:**
  - all 14 pages of `rm_bm_20250128.pdf`, 1 of `rm_bm_20240529`, 2 of `rm_bm_20251103`
  - errors reach the figures: "1.1124.31", "621.8.)", "7.(,4", and the CIN
  - `board_outcomes/routemobile_outcome_board_meeting_2025-01-28.txt` carries them
  - the meeting times the T1.6b/c checks read are clean
  - a word heuristic misses 13 of the 17 pages; a page-covering-image signal sees all 17
- `MANIFEST.md` and R5 now carry dated corrections. **No source was repaired.**

## 5. Research (`c6bb3a6`) — every file adversarially source-checked

| File | Checked | Result |
|---|---|---|
| Harvey document intake | 6 claims | all hold. Vault holds 100,000 files; citations are page and quote per cell; no India region found |
| Spellbook document intake | 6 claims | 1 downgraded: provider zero data retention can be switched off by customer agreement |
| Sarvam document AI | 6 claims | all hold. **10 pages per call max; trains on content unless opted out**; 23 languages; India residency "for Indian customers" |
| Document AI providers (Azure, Google, AWS, OCI) | 6 claims | all hold. **Textract reads no Indian script.** Azure and Google each cover different Indian scripts. No independent benchmark on real Indian corporate paper exists |
| Large-document profile | 6 claims | all hold. A real scheme bundle is **512 pages, 19 MB, about 14 documents in one PDF, 20.7% image-only pages**, and some text layers are corrupted |

The main session re-checked two claims word for word: Sarvam's 10-page limit, and Textract's
language list.

**`RESEARCH_GAPS_2026_09_14.md`** lists 24 gaps, 8 of them blocking.

## 6. PLAN_12 — large-document intake architecture

**Status: complete and committed** — [PLAN_12](PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md).

- **How it was made:** three independent designs (abstention-first, scale-first,
  residency-first), three judges, a synthesis, a two-lens red team, then fixes.
  **Abstention-first won** (judge totals 105.5 against 94.5 and 94.5).
- **Red team:** **43 findings, all FIXED**, including two rated fatal:
  - the provider-eligibility check read the evidence marker, not the value
  - `NOT_FOUND` rested on unmeasured extractor recall; it is now unreachable until recall
    is measured

  7 findings carry a residual OPEN note tied to a named research gap.
- **The shape, in one line:** every cell starts ABSTAINED and is served only when every stage
  from the bytes to the value has recorded a positive reason to trust it. A refusal names its
  page. Every threshold ships as `None` until measured. G01 has both branches designed and
  neither chosen.
- **Checked by the main session before commit:**
  - Sarvam's 10-page limit matches R3 D9 word for word
  - Textract is marked ineligible in Mumbai on R4 G1/G2 (org opt-out unverified), matching
    the row
- **One error corrected.** PLAN_12 listed the per-page reader as BUILT with nothing blocking it,
  and planned page anchors over it as "buildable now". The synthesis ran before D1's census
  existed. D1 measured that reader agreeing with an independent one on 0 of 14 files. The
  status row, the enumerator rationale (INFERRED → MEASURED) and build step 2 now say
  **BLOCKED on D-002**.
- **Length:** about 16,600 words. It is a design reference, not a read-once document; §1
  (thesis) and §10 (what is blocked and the build order) are the parts to read first.

## 7. Tooling (`ea35142`)

- **CLIs installed:** AWS, OCI, Azure (signed in) and Google Cloud. **Kaggle CLI is installed
  but not on PATH:** `~/Library/Python/3.12/bin/kaggle`.
- **`docs/TOOLING.md`** has the exact MCP commands, each read from the vendor's own page. Before
  registering any of them:
  - **AWS:** the managed server's endpoint is **us-east-1**, so it must never carry client data
  - **Azure:** telemetry is on by default, and **no read-only mode** is documented
  - **Kaggle:** its official pages would not render. The endpoint and OAuth come only from a
    third-party bug report
- **Nothing was registered.**

---

## 8. Waiting on you

| # | Decision | Why it is yours |
|---|---|---|
| 1 | **PLAN_12 G01 — durable storage for bulk review?** PLAN_07 says client documents are never durable; a 500-page bundle needs queues and per-page state | Both branches are designed; choosing is a product and liability call |
| 2 | **L7 — map document wording to company class?** ("Private Limited" → `private`; "(OPC) Private Limited" → `opc`) | Mapping is interpretive. Today an unmapped class is refused at the API (`api.py:86`), so nothing is silently wrong |
| 3 | **D2 — which PDF reader for page anchors?** Fix the stdlib parser (large job), or adopt a PDF library (a new runtime dependency, now with a stated reason) | Dependency policy |
| 4 | ~~L8 — integer value-support rule~~ **Done 15-09 on replay evidence** (§3). Remaining choice: keep refusing a correct count in a two-number sentence, or accept it | Recall vs never serving the wrong count |
| 5 | **Register any MCP server?** Credentials, and tool scope for Azure | §7 |
| 6 | **Sarvam** — only with training opted out, and only if 10-page batching is acceptable | Contract terms |
| 7 | **The 20-document test** — still the gate on bulk review (F8) | Needs real buyer documents |

## 9. What this run did not do

- **No real client document** went to any model or cloud. Probes used synthetic documents and
  public filings only.
- **Not changed**, only reported: `router.py`'s rationale for sending scanned pages to Gemini
  cites a benchmark R4 shows is overstated (word crops from a historical Sanskrit collection,
  not document pages).
- **Found and recorded, not fixed:** the 18-case benchmark does not store raw model proposals,
  so its refusals cannot be replayed (H03's cause is unknown for this reason).
