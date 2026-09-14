# PLAN_11 — the next move: large-document intake, providers, and the fixes the evidence now demands

Written 2026-09-14 by the main session, before an unattended overnight loop.
Runbook the loop executes: [`.claude/plans/loop-overnight-2026-09-14.md`](../.claude/plans/loop-overnight-2026-09-14.md).

Status markers as in [PLAN_00_INDEX](PLAN_00_INDEX.md): BUILT · MEASURED · SOURCED · INFERRED · UNVERIFIED · BLOCKED.

---

## 0. What the founder asked for, and how it maps onto the plan that already exists

| Asked | Where it already lives | What this plan does |
|---|---|---|
| Analyse how Harvey and Spellbook take in, analyse, check and verify documents | `LEGAL_AI_ARCHITECTURE_ANALYSIS`, `COMPETITOR_FEATURE_MATRIX`, `SPELLBOOK`, `SPELLBOOK_INFERRED_ARCHITECTURE` | **Extends them** with the document-intake path specifically. No parallel documents |
| An Indian model (Sarvam AI) for photos and dragged-in documents | `PLAN_03` §OCR, `PLAN_01` role 13 (DESIGNED) | Researches Sarvam's actual document/vision offering and places it in the role-13 OCR tier against Azure DI, Google Document AI, OCI, Textract |
| Massive corporate documents — merger schemes, Ind AS financials | `FEATURES` F8 Bulk Document Review (NOT BUILT, riskiest) | Designs F8 + role 13 end to end, page-anchored |
| Architecture on AWS, Azure, Google Cloud, Oracle Cloud | `PLAN_07` tenancy | A provider-neutral design with a per-cloud mapping, India regions first |
| Develop the planned features, integrate existing models into the backend | `FEATURES`, `PLAN_01` Tier 2 | Builds what is not gated; wires providers for shadow evaluation, never for deciding law |
| CLIs and MCPs for AWS / Azure / Kaggle | — | CLIs installed; MCPs listed for the founder to approve with credentials |

**The gate this plan does not skip.** `PLAN_05` gates F8 on the 20-document test: are the buyer's
documents typed English, or scanned, stamped, mixed-script paper? No autonomous work answers that,
because it needs the buyer's documents. What the loop *can* do is produce the other half of the
evidence from public documents already held (`corpus/testdocs/`) and make the architecture ready,
so the day the test runs the answer is a configuration, not a rewrite.

---

## 1. What changed today (measured, 2026-09-14)

| Model | Where | Text/date facts with spans | Span names another field | Served a wrong value |
|---|---|---|---|---|
| gemma3:1b | laptop | 0 | UNMEASURABLE | — (value confusion 5) |
| llama3 8B | laptop | 36 | **5** | **yes — an empty CIN, T05** |
| Llama-3.3-70B | Azure | 19 | 1 (refused on attempt 1) | not observed |
| gpt-5-mini | Azure | 19 | 0 | not observed |

Three defects follow, each with a replayable witness in `eval/realrun/last_text_probe*.json`:

1. **Empty text value always passes value-support.** `document_extract.py:227` tests
   `str(value).lower() in span`; the empty string is in every string. Served: `cin = ''`.
2. **No format check on CIN.** `cin = 'ACME HOLDINGS PUBLIC LIMITED'` serves when proposed alone.
3. **`field_binding` covers money fields only.** `company_class = 'under the Companies Act, 2013'`
   on a span naming incorporation serves when proposed alone. Widening was declined on
   13-09 for lack of evidence; the evidence now exists, but only strongly on a small model —
   so widening must prove it refuses **none** of the facts gpt-5-mini and 70B served correctly.

"Not observed" above is not "correct": the probe does not yet compare a served value to the
document's ground truth. That is task L5.

---

## 2. Tracks

### Track L — correctness, with evidence (build; TDD; one commit each)
| ID | Task | Done when |
|---|---|---|
| L1 | Refuse an empty or whitespace text value | Unit test RED→GREEN; replaying the stored T05 proposal now abstains; every fact gpt-5-mini/70B served still serves |
| L2 | A `cin` value must be CIN-shaped (reuse the CIN pattern already in `party_resolution.py`; report, never repair) | Same replay discipline |
| L5 | Probe scores served values against each case's ground truth → `WRONG_SERVED` | Stub test sees a wrong served value; re-scored from stored raw proposals, no new calls |
| L3 | Widen `field_binding` to text/date fields | Replay over all four stored runs: new refusals on correct facts = **0**, or the widening is not committed and the reason is recorded |
| L4 | The 18-case realrun benchmark on Azure (`run.py --azure <deployment>`) | Leak rate for gpt-5-mini and 70B, reporting floor respected |

### Track R — research (agents, web, public sources only)
| ID | Question | Output |
|---|---|---|
| R1 | Harvey: how a document enters (upload, Vault, limits, formats), how it is analysed (review tables, workflows), how outputs are checked (citations, verification) | Extends `LEGAL_AI_ARCHITECTURE_ANALYSIS` |
| R2 | Spellbook: the same questions, in Word | Extends `SPELLBOOK_INFERRED_ARCHITECTURE` |
| R3 | Sarvam AI: what document / vision / OCR capability actually exists, languages, API, data residency, retention and training terms | `docs/research/SARVAM_DOCUMENT_AI.md` |
| R4 | Document AI for Indian legal scans across Azure DI, Google Document AI, AWS Textract, OCI Document Understanding, Sarvam: scripts, tables, stamps, handwriting, India regions, page limits, price, retention | Extends `PLAN_03` §OCR |
| R5 | What large Indian corporate documents actually look like: schemes of arrangement (ss.230–232), Ind AS financial statements, from public listed-company filings — page counts, tables, scanned annexures | `docs/research/LARGE_DOCUMENT_PROFILE.md` |

Every claim carries a URL or a marker. Competitor claims without a source are INFERRED.
Each research output gets an adversarial source check before it is committed.

### Track A — architecture (judge panel, after R lands)
`docs/PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md`: F8 and role 13, end to end. Three independent
designs — abstention-first, scale-first, residency-first — scored by independent judges against
CLAUDE.md's rules, `NON_GOALS`, the `PLAN_01` gate chain and `PLAN_07` tenancy; synthesised; then
red-teamed. It must specify at least:

- **Intake:** upload → hash → type sniff → malware scan → per-page split. Idempotent per page.
- **Text path:** text-layer pages skip OCR; scanned pages go to the OCR tier; mixed documents are
  split, not averaged.
- **OCR tier (role 13):** cheap OCR → document-AI → VLM fallback, a **confidence gate with no
  threshold until measured** (`PLAN_01` open question), and a page that fails the gate abstains.
- **Page-anchored spans:** every fact cites page + offset, so a refusal can say *which page*.
- **Large documents:** page map → section/table detection → per-section extraction → the existing
  gates → cell-level abstention in the F8 table. Whole-section context is kept where verbatim
  quotability depends on it (`PROVIDER_DECISION` §2).
- **Providers:** one extract contract, many adapters (Anthropic, Gemini AI Studio/Vertex, Azure,
  Ollama, Sarvam if R3 supports it). Models propose; gates decide; no model decides applicability.
- **Clouds:** a mapping table — AWS `ap-south-1`/`ap-south-2`, Azure Central/South India, Google
  `asia-south1`/`asia-south2`, OCI Mumbai/Hyderabad — each row SOURCED or INFERRED, with the
  Azure for Students regional policy recorded as a constraint of *this* account, not of Azure.
- **Tenancy and retention:** from `PLAN_07`; zero retention on provider calls where offered.
- **Failure modes and cost per 100-page document**, stated as ranges with their sources.

### Track D — build what is not gated (TDD)
| ID | Task |
|---|---|
| D1 | Text-layer census of `corpus/testdocs/`: per page, text layer / needs OCR / mixed. MEASURED on public documents — explicitly **not** the buyer's 20-document test |
| D2 | Page-anchored grounding: `document_extract` spans carry a page number for multi-page PDFs |
| D3 | Provider registry: one module listing the extract adapters and their capabilities; serving routes untouched |

### Track E — tooling
| ID | Task |
|---|---|
| E1 | Install AWS CLI, OCI CLI, Kaggle CLI; record versions. **No credentials are configured** |
| E2 | `docs/TOOLING.md`: CLIs present, and the MCP servers worth adding for AWS, Azure and Kaggle, with the exact command — registered only after the founder supplies credentials |

---

## 3. What the loop may not do

- Commit with the gate red, or bundle two logical changes in one commit.
- Push anywhere but `loop/bookmark-godseye-v0`. Never `main`.
- Create, resize or delete cloud resources. It uses only the two Azure deployments that exist.
- Exceed **300 Azure model calls** overnight (≈ a few US dollars at list price — INFERRED; the
  count is recorded in the runbook log, which is the real control).
- Send anything but synthetic probe documents or public filings to any external model.
- Scrape, bypass robots or the MCA WAF, or fetch confidential documents (CLAUDE.md).
- Register MCP servers or enter credentials.
- State a competitor or provider fact without a URL.

## 4. Blocked on the founder
| Item | Why |
|---|---|
| The 20-document test | Needs buyer documents |
| AWS / OCI / Kaggle credentials | Not supplied |
| Sarvam API key | Only after R3 says it is worth one |
| Commit or revert L3 if its replay shows new refusals | A product judgement, not an engineering one |
