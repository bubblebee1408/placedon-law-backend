# Research gaps before PLAN_12 — a completeness critique of Track R

Written 2026-09-14. Role: completeness critic for `docs/PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md`
(not yet written). This file lists what is missing, or too weak to design on, across the five Track R
outputs and the two plans PLAN_12 must obey. It closes no gap itself.

**Markers used in this file**
- **SOURCED-LOCAL**: I opened the repository file at the path given on 2026-09-14, and the claim is
  in it (or, for a negative, a grep of the named paths returned nothing).
- **CARRIED**: SOURCED in the named Track R file, with that file's URL. **I did not re-open the web
  page.** Where the 2026-09-14 adversarial source check re-opened it, the row says "source-checked".
- **INFERRED**: my reasoning, stated as such.
- **UNVERIFIED**: not established from any page or file opened. This includes every *candidate*
  evidence source named under "where evidence could come from". Those pages were **not opened**, and
  naming one is not a claim about what it says.

Negative findings follow CLAUDE.md: "not found in the files read" is not "does not exist".

---

## Question

Given the five research files (R1 Harvey, R2 Spellbook, R3 Sarvam, R4 hyperscaler document AI,
R5 large-document profile), their source checks, `PLAN_01` and `PLAN_07`, what evidence is **missing
or too weak** to design these parts of PLAN_12 on?

- bulk intake and review of schemes of arrangement and Ind AS financials
- the OCR tier with a confidence gate
- page-anchored spans and cell-level abstention
- the provider abstraction
- the multi-cloud mapping for AWS, Azure, GCP and OCI in India regions
- tenancy and retention

For each gap: why it matters for the architecture, and where evidence could come from.

## Sources checked

**Research files (read in full):**
- `docs/research/HARVEY_DOCUMENT_INTAKE.md` (R1)
- `docs/research/SPELLBOOK_DOCUMENT_INTAKE.md` (R2)
- `docs/research/SARVAM_DOCUMENT_AI.md` (R3)
- `docs/research/DOCUMENT_AI_PROVIDERS_INDIA.md` (R4)
- `docs/research/LARGE_DOCUMENT_PROFILE.md` (R5)

**Plans (read in full):** `docs/PLAN_01_ARCHITECTURE.md`, `docs/PLAN_07_TENANCY_AND_PRICING.md`.

**Read for context:**
- `CLAUDE.md`, in full.
- `docs/PLAN_11_NEXT_MOVE.md` §0–4, which set PLAN_12's required contents.
- `docs/PROVIDER_DECISION.md` §5–7.
- `docs/VENDOR_QUESTIONS.md` §"Jurisdiction and data".
- `docs/METRIC_POLICY.md`, first 30 lines.

**Code inspected (headers and targeted greps only):**
- `checker/anthropic_model.py`, `checker/gemini_model.py`, `checker/document_extract.py`
- `checker/pdf_text.py`, `checker/pdf_signature.py`
- `checker/review_table.py`, `checker/review_record.py`
- `checker/scope.py`
- the directory listing of `corpus/rules/`

**Source-check results supplied with the task (R1–R5):**
- 30 claims were re-checked, 6 per file.
- 1 was downgraded (R2 E5).
- The notes also record three residual defects: R1's "(US implicit)" wording, redirected URLs in R4,
  and an omitted residency condition in R3 H1.

**Greps run over `docs/` and `checker/`, reported only as results of these greps:**

| Term | Result |
|---|---|
| `XBRL`, `CERT-In`, `DPDP Rules`, `Bedrock`, `cross-region`/`Cross-Region`, `PageLabels`, `ClamAV`, `Defender`, `count_tokens` | 0 files |
| `Azure for Students` | `PLAN_11` only |
| `malware`, `clamav`, `virus` over `checker/`, `scripts/`, `docs/*.md` | `PLAN_11` line 82 only |
| `page` in `checker/document_extract.py` | 0 hits |
| `Indian Accounting Standards`, `Ind AS`, `Schedule III`, `CAA Rules`, `Compromises, Arrangements` in `checker/scope.py` | 0 hits |

**Not done:**
- No external web page was opened. This is a critique of the evidence already gathered, and the
  task asks where evidence *could* come from, not for it to be collected.
- No research file was edited, and nothing was committed.

---

## Evidence found

These rows establish that each gap in the Result exists. They are not new facts about vendors.

| id | claim | marker | URL / path |
|---|---|---|---|
| E01 | PLAN_07 §1 makes it a rule that "a client document must never be written to durable application storage". Working state "lives in memory for the request and dies with it". Only check results without client content, hash-stamped, may persist | SOURCED-LOCAL | `docs/PLAN_07_TENANCY_AND_PRICING.md` |
| E02 | PLAN_11 requires PLAN_12 to cover five things: intake "upload → hash → type sniff → malware scan → per-page split. Idempotent per page"; tenancy and retention "from PLAN_07"; a four-cloud India mapping in which the "Azure for Students regional policy" is recorded as an account constraint; failure modes; and "cost per 100-page document … with their sources" | SOURCED-LOCAL | `docs/PLAN_11_NEXT_MOVE.md` |
| E03 | Harvey review-table cells carry durable human-review state: `is_edited`, `is_verified` with user and timestamp, `is_flagged` with user and timestamp | CARRIED (R1 C2; source-checked) | https://developers.harvey.ai/api-reference/vault/get-review-table-row-details.md |
| E04 | Harvey says customers set retention (R1 D2), and separately that ZDR means data "is not written into durable application storage by default" (R1 D6). R1 found no published explanation of how Vault storage and the ZDR runtime coexist | CARRIED (R1 D1, D2, D6) / INFERRED (no reconciliation found in R1) | https://www.harvey.ai/security · https://www.harvey.ai/blog/why-we-built-our-own-cloud-agent-infrastructure |
| E05 | Two batch OCR paths need the input in customer object storage: Azure DI batch reads from and writes to the customer's Blob Storage (R4 D5), and OCI async reads from Object Storage (R4 D7) | CARRIED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/batch-analysis?view=doc-intel-4.0.0 · https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/limits.htm |
| E06 | The A1 scheme bundle is 512 pages. 106 are textless, and at least 17 have a corrupted text layer. The garble heuristic missed two of the defects (C-1, C-3), and no OCR-vs-render comparison was run | CARRIED (R5 E-A, E-C; boundaries source-checked) | https://embassyindia.com/wp-content/uploads/2025/12/NCLT_Meeting_Notice_Explanatory_Stmt_Annexures_Equity_shareholders-1.pdf |
| E07 | The production extractor sends the document as `source: {type: "text", media_type: "text/plain"}` with citations enabled. EXTRACT is `claude-opus-5`. Nothing sends a PDF or a page image | SOURCED-LOCAL | `checker/anthropic_model.py` |
| E08 | The Gemini adapter sends text parts through `wrap_untrusted`, model `gemini-3.6-flash`, routed to AI Studio or to Vertex. A test builds an `asia-south1` URL, and a publisher path uses `locations/global`. Its docstring calls arXiv 2606.29213 "the only rigorous independent benchmark of REAL Devanagari scans". R4 I4–I6 qualifies that paper: Sanskrit typeset phrase crops, a single-author v1 preprint, no cloud document-AI service tested | SOURCED-LOCAL / CARRIED (R4 I4–I6) | `checker/gemini_model.py` · https://arxiv.org/html/2606.29213 |
| E09 | None of the five research files documents, for the *extraction* models (Anthropic, Gemini, Azure-hosted LLMs): India-region availability, whether requests can be routed out of region, retention or ZDR terms, or PDF/image input limits | SOURCED-LOCAL (negative, over the five files) | `docs/research/*.md` |
| E10 | PLAN_07 §5 leaves open "Anthropic's and Google's formal ZDR mechanics" | SOURCED-LOCAL | `docs/PLAN_07_TENANCY_AND_PRICING.md` |
| E11 | `scope.py` has no body or text matching Ind AS, Schedule III or the CAA Rules. `corpus/rules/` holds seven files: board powers 2014, G.S.R. 700(E) 2022, G.S.R. 880(E) 2025, KMP rules 2014, PAS rules 2014, an s.188 rule-15 review, and SEBI LODR 2015. None is the Companies (Compromises, Arrangements and Amalgamations) Rules 2016 or an Ind AS rules instrument | SOURCED-LOCAL | `checker/scope.py` · `corpus/rules/` |
| E12 | In A1, financial statements and results are 52.5% of pages and the scheme text is 11.7%. The bundle's notice is issued under ss.230–232 "read with the CAA Rules 2016" | CARRIED (R5 E-B) | A1 URL above |
| E13 | The OCR bake-off is recommended in two places (R3 action 3, R4 action 2), but no results file exists: `docs/research/` holds only the five Track R files | SOURCED-LOCAL | `docs/research/` |
| E14 | Confidence signals are unevenly documented. Sarvam's managed Digitise documents no per-block confidence (R3 E10); self-hosted returns `ocr_confidence` and `layout_confidence` (R3 F3, source-checked). R4 did not check Azure or Google word-level confidence (R4 PLAN_12 item 7) | CARRIED | https://docs.sarvam.ai/api/self-hosted/sagemaker/api-vision.md |
| E15 | PLAN_01 says role 13's confidence gate "has no threshold yet" and "cannot be set without the document corpus" | SOURCED-LOCAL | `docs/PLAN_01_ARCHITECTURE.md` |
| E16 | METRIC_POLICY's release gate is an abstention cap of ≤ 0.25, a false-accept ceiling of ≤ 10, and an F1 floor of ≥ 0.40, defined on the n=71 strict entailment set. The lines read define no F8 cell-level metric | SOURCED-LOCAL (lines 1–30 only) | `docs/METRIC_POLICY.md` |
| E17 | R5 measured table *presence* only (`find_tables`, a lower bound). No table-structure accuracy was measured for any provider on Ind AS pages. The pages use Indian digit grouping (e.g. "8,06,470.99") | CARRIED (R5 E-E, C-1) | https://www.tataconsumer.com/sites/g/files/gfwrlq316/files/2025-06/Tata_Consumer_IAR_2024_25.pdf |
| E18 | No file in `docs/` or `checker/` mentions XBRL | SOURCED-LOCAL (grep) | `docs/`, `checker/` |
| E19 | R5 measured one full scheme bundle, dated 2022, and did not measure documents per matter. R1 sized PLAN_12 at "tens of documents per matter (pending R5)". Private diligence documents are OPEN (R5 F-3) | CARRIED / SOURCED-LOCAL | `docs/research/LARGE_DOCUMENT_PROFILE.md` · `docs/research/HARVEY_DOCUMENT_INTAKE.md` |
| E20 | R5's method measures text layer, garble, images and tables, but not script or language per page. R3 and R4 justify a script router from vendor language tables alone | SOURCED-LOCAL | R3, R4, R5 files |
| E21 | No provider documents stamp or seal handling (R4 C8, R3 D3). `pdf_signature.py` already verifies CCA-India PKCS#7 signatures and defends against incremental-update attacks, but the share of pages in the R5 sample carrying such signatures was not measured | CARRIED / SOURCED-LOCAL | `checker/pdf_signature.py` |
| E22 | B1 has 130 two-up spreads, so PDF index ≠ printed page. B1 and C1 have no usable outline. Page-label extraction was not researched | CARRIED (R5 E-2, E-9, F-1) | B1 URL above |
| E23 | `document_extract.locate()` returns character offsets into a single document string. The file has no `page` token, so page anchoring (PLAN_11 D2) does not exist yet | SOURCED-LOCAL | `checker/document_extract.py` |
| E24 | Several India-region rows are inference only: Azure DI in South India (from pricing, R4 E4); OCI India hosting (availability page returned 403, R4 E9); Sarvam SageMaker regions (R3 F6); Google Mumbai OCR (Preview terms not checked, R4 unresolved 3). The research files source no row for object storage, KMS, queues or malware scanning in any India region | CARRIED / SOURCED-LOCAL (negative) | R3, R4 files |
| E25 | PLAN_07 §3 says DPDP processor obligations are "UNVERIFIED" because "the primary Gazette PDFs were unreachable". Its "reported minimum ₹50 crore" and its SpotDraft India-residency row carry no URL | SOURCED-LOCAL | `docs/PLAN_07_TENANCY_AND_PRICING.md` |
| E26 | Sarvam's training default is contradicted across four of its own documents (R3 H7–H11; H7 source-checked). The source check found that the Trust Center residency FAQ answer opens "In India, for Indian customers", a condition R3 H1 omits | CARRIED (R3 + source-check note) | https://www.sarvam.ai/privacy-policy · https://www.sarvam.ai/trust-center |
| E27 | Spellbook's LLM no-retention term is qualified by "unless otherwise agreed or directed by Customer", so provider-side ZDR is a per-contract variable, not a fixed property | CARRIED (R2 E5 as downgraded) | https://spellbook.com/legal/terms-of-service |
| E28 | Retention defaults differ by provider: Azure DI 24 h, deletable (R4 G3); Google batch has a one-day failsafe TTL and may persist up to a day if a batch job ends abnormally (source-check note on R4 G5); Textract may store and use inputs unless the org opts out (R4 G1) | CARRIED (all source-checked) | https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security · https://docs.cloud.google.com/document-ai/docs/data-usage · https://aws.amazon.com/textract/faqs/ |
| E29 | The malware scan appears only as a word in PLAN_11 line 82. No research file covers scanning options, hostile-PDF handling or parser attack surface | SOURCED-LOCAL (grep) | `docs/PLAN_11_NEXT_MOVE.md` |
| E30 | `review_table.py` is "The human-review table for the eleven fixture proposals" and `review_record.py` is an append-only log of reviewer decisions on fixtures. Neither is an F8 cell-state table | SOURCED-LOCAL (module headers) | `checker/review_table.py` · `checker/review_record.py` |
| E31 | The research files give OCR per-page prices (R3 G1, R3 J5, R4 F1–F8). No file gives LLM token cost or India-region rate limits for extracting a 500-page bundle | SOURCED-LOCAL (negative) | R3, R4 files |
| E32 | VLM OCR can invent text: VLMs "tend to hallucinate plausible-sounding text" (R4 I8), and Digitise writes AI image descriptions (R3 D7). CLAUDE.md records image-borne injection as "deliberately not open yet" | CARRIED / SOURCED-LOCAL | https://arxiv.org/html/2512.18004v1 · `CLAUDE.md` |
| E33 | Harvey's upload API and Sarvam's self-hosted API reject password-protected or encrypted PDFs and mark unsupported files (R1 A19, R3 E3, R4 D1). Whether and how to accept an encrypted PDF is undecided | CARRIED / INFERRED | R1, R3, R4 files |
| E34 | The source checks covered 30 claims. Load-bearing rows that were **not** re-checked include R3 E11 (10 req/min on every plan), R3 H4 (retention ladder), R4 D6 (Google limits), R4 E3/E4 (Azure regions inferred from pricing), R4 D4 (Azure page limits) and R1 A11 (help-centre limits) | CARRIED (source-check notes) | — |
| E35 | PLAN_01's premise quotes a Harvey prompt and "5,000 mini-agents". R1 found no Harvey page containing either (C11, C12) | CARRIED | `docs/research/HARVEY_DOCUMENT_INTAKE.md` |
| E36 | Whether .xlsx/.docx is in scope for intake is undecided (R2 PLAN_12 item 10). Azure DI Read and Layout accept DOCX/PPTX/XLS (R4 D4) | CARRIED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0 |

---

## Evidence quality

- **The Track R files are strong on what they set out to cover.** That means competitor intake
  surfaces, OCR-vendor capability tables, OCR prices and one real bundle profile. Source checks found
  0 refutations and 1 downgrade in 30 claims. Coverage is thin, though: 6 per file, and several
  load-bearing rows remain unchecked (E34).
- **The files cover only the OCR half of the provider question.** The extraction models PLAN_12
  must wire (E07, E08) have no research row on region, retention, ZDR or input limits (E09). R3 and R4
  studied the rung that feeds text in. Nobody studied the rung that reads it.
- **Every measurement of documents is n=1 per type**, and the only scheme bundle is from 2022 (E19).
  No accuracy measurement of any provider on Indian corporate paper exists (E13).
- **Legal and regulatory inputs to tenancy and retention are the weakest.** PLAN_07's DPDP section
  is self-declared UNVERIFIED (E25). No research covers other Indian operator obligations (E18 grep
  results).
- **Quality of this critique.** Every gap below is either SOURCED-LOCAL (a file or grep shows the
  gap) or INFERRED (my reasoning about architectural consequence). Candidate sources are named but
  unopened, so each is UNVERIFIED.

---

## Result

Twenty-four gaps, in three tiers.

- **Tier 1** gaps block a responsible design. PLAN_12 would otherwise have to guess at the
  architecture's shape.
- **Tier 2** gaps can be designed around. PLAN_12 must mark them OPEN and make them configuration
  axes or gated adapters.
- **Tier 3** gaps are hygiene: fix before PLAN_12 is cited externally.

### Tier 1 — blocking

| # | Gap | Why it matters for the architecture | Where evidence could come from (all UNVERIFIED, not opened) | Rows |
|---|---|---|---|---|
| G01 | **PLAN_07's "never durable" rule contradicts bulk review, and nothing reconciles them.** Bulk review needs many things that persist: async queues for 500-page bundles, per-page idempotency keyed by hash, batch OCR APIs that read from customer object storage, multi-day human review with durable cell state, and re-audit when a document changes | This is the single largest design fork. Either PLAN_07 §1 is amended (documents persist under tenant-set retention, encrypted, with ZDR on provider calls only), or F8 becomes a single-session, synchronous feature with no batch OCR and no stored review. INFERRED: most of PLAN_12 (queues, caching, review state, re-audit) changes shape depending on the answer. Quoted spans in the audit record are client content too (R1 item 8) | This is a decision, not a web search. Inputs: (a) buyer interviews and the PLAN_05 20-document operator on what retention buyers accept or require; (b) re-reading Harvey's security page and its agent-infrastructure post for how Vault storage coexists with ZDR; (c) provider docs on customer-managed keys and crypto-shredding for the chosen object store | E01–E05 |
| G02 | **No provider research for the extraction models.** Anthropic (`claude-opus-5`), Gemini (`gemini-3.6-flash`) and any Azure-hosted LLM lack evidence on: availability in India regions; whether cross-region inference sends a request out of India; retention, abuse-monitoring logging and ZDR eligibility; free-tier data use; and PDF/image input limits (pages, tokens) | The provider abstraction, the residency row for every cloud, and the chunking unit all depend on this. INFERRED: if the residency-first design uses a model whose India endpoint routes cross-region, its residency claim is false. If PDF input caps pages per request, "whole-section context" (PROVIDER_DECISION §2) sets the section size limit. Model identifiers rot in months (PROVIDER_DECISION §7) | Anthropic API docs (PDF support, Citations, data retention/ZDR) at docs.claude.com; the AWS Bedrock user guide (model support by Region; cross-Region inference); Google Cloud Vertex AI generative-AI locations and data-residency pages; Gemini API terms (AI Studio free-tier data use); Microsoft Learn data privacy for Azure OpenAI/Foundry and model region availability. Verify every model ID against the provider's model list the day PLAN_12 is written | E07–E10 |
| G03 | **The law that Ind AS and scheme cells would be checked against is not held.** `scope.py` has no body for accounting standards, Schedule III or the CAA Rules 2016. `corpus/rules/` holds none of them | R5 shows financial statements are 52.5% of a scheme bundle and the scheme is 11.7%. INFERRED: without a held instrument, F8 can *extract and page-cite* financial cells but cannot *verify* them. Every "missing required information" check on a notice or explanatory statement would be a refusal. PLAN_12's segment → scope routing must name which body each segment maps to. Declaring one is a `scope.py` change with its own acquisition route, and this plan cannot assume it | Acquisition through the existing two-human route: the CAA Rules 2016 and the Companies (Indian Accounting Standards) Rules as published on India Code (`indiacode.gov.in`) or the eGazette; Schedule III from the held Companies Act corpus (check whether the schedule text is actually ingested). A `scope.py` decision on whether accounting standards are a separate body | E11, E12 |
| G04 | **No accuracy or confidence evidence on our paper, so the OCR gate has nothing to be built from.** The bake-off has not run. No vendor's word-level confidence was checked for Azure or Google. Sarvam managed has none documented. No research on calibrating OCR confidence | PLAN_11 says "no threshold until measured", but PLAN_12 still has to choose the *signal type*: vendor confidence, cross-vendor agreement, text-layer-vs-OCR agreement, or a trained estimator. INFERRED: the gate's inputs, how many vendors are called per page (cost), and the abstention path depend on which signal exists. Choosing an agreement signal also forces two providers per page by design | (a) Run the R3/R4 bake-off on public pages already identified: A1 pp.98–146, 207–210, 221–222, 273–294, 433–444, 494–512 (scanned, ≈85–256 dpi). Score per-page CER plus invented text. (b) Azure DI analyze-result schema on Microsoft Learn (word `confidence`); the Google Document AI `Document` object reference (layout confidence); Textract `Block.Confidence` (R4 C1). (c) arXiv literature on OCR confidence calibration and selective prediction / risk-coverage curves | E13–E15 |
| G05 | **No way yet to detect a corrupted text layer.** The heuristic under-flagged: C-1, a Caesar-shifted units line, and C-3, broken ToUnicode. Text-vs-render agreement was never measured | PLAN_11's "text-layer pages skip OCR" rule is unsafe as written. INFERRED: the per-page router needs a third branch, "text present but untrusted". Its detector decides how many pages go to OCR, which drives cost and latency. A missed units line silently scales every figure by 1,000 | Run OCR over A1 pp.445, 460–473, 493, 505 and compare with the native layer (public document, already sourced). Test `checker/pdf_text.py`'s ToUnicode handling against the same pages. PDF text-extraction reliability literature (arXiv) | E06 |
| G06 | **Cell-level accuracy on Ind AS tables is unmeasured, and there is no ground truth to measure it against.** Unknowns include structure fidelity, Indian digit grouping, bracket negatives, units headers, multi-page tables, two-up spreads, and every provider's table output | Cell-level abstention needs a per-cell correctness signal and a labelled set to set any threshold. INFERRED: without one, "cell abstains" can only mean "gate failed", never "likely wrong", and METRIC_POLICY's gate cannot be applied to F8 | (a) A small hand-labelled set from B1's standalone FS (PDF pp.291–360; public). (b) **XBRL** (G07) as a machine-readable cross-check. (c) Published table-structure benchmarks and metrics (e.g. FinTabNet/PubTabNet papers on arXiv) for *method* only, not as evidence about Indian paper | E16, E17 |
| G07 | **XBRL is unresearched as an independent check.** No file mentions it | INFERRED opportunity, not a finding: if listed companies' financial results filed with the exchanges are available as XBRL, extracted FS cells could be matched deterministically against the company's own tagged figures. That fits "models propose; gates decide" and would give G06 its ground truth. It could change whether the FS path needs OCR at all for listed issuers | NSE and BSE public corporate-filing pages for financial-results XBRL, and their robots.txt (fail closed, as R5 did); SEBI circulars on XBRL filing. MCA filings are behind the MCA WAF and V3 login, so they are excluded by CLAUDE.md | E18 |
| G08 | **Document size and mix are unsized beyond n=1.** There is one scheme bundle (2022), no 2025–26 bundles, no user-uploaded scans, no documents-per-matter count, and no profile of private diligence documents | Batch size, queue design, per-tenant quotas, storage sizing and cost ranges all rest on this. R1 item 7's "tens of documents per matter" was left pending R5, and R5 did not measure it. INFERRED: the scale-first design cannot be judged without it | R5's actions 2–4 (3–5 recent bundles from issuer sites or `nsearchives`; robots via `checker/robots.py`). The PLAN_05 20-document test for buyer uploads. Buyer interviews for matter sizes | E19 |

### Tier 2 — design around, mark OPEN

| # | Gap | Why it matters for the architecture | Where evidence could come from (UNVERIFIED, not opened) | Rows |
|---|---|---|---|---|
| G09 | **Script and language mix of real corporate filings is unmeasured.** | R3 and R4 recommend a per-page script router across Azure, Google and Sarvam, justified by language tables alone. INFERRED: if the measured share of non-Latin pages in corporate filings is near zero, the router is speculative for v1 (YAGNI) and residency and cost dominate. If the share is material, the router is core | Run Unicode-script detection per page over A1, B1, C1 and `corpus/testdocs/_raw/` (all public), plus OCR'd scanned pages after G04. The 20-document test | E20 |
| G10 | **Segmenting a bundle into typed documents** (14 types in A1) has no method, no accuracy figure and no labelled data. Role 12 is DESIGNED only | A segment's type decides which checks may fire and which scope body applies (CLAUDE.md: minutes checks must not fire on notices). INFERRED: a mis-segmented CCI order inside a scheme would receive Companies Act findings. The index page is a hint, not a trusted source | A1's own index (pp.1–2) as one labelled example, extended by G08's bundles. arXiv literature on page-stream segmentation | E12 |
| G11 | **Page identity is undefined.** It is unclear what "page" means in a citation (PDF index vs printed label), how two-up spreads are split, how rotation is normalised, and which text char offsets point into: the native layer, OCR output, or normalised text. `document_extract` has no page field | Page-anchored spans (PLAN_11 D2) and "a refusal names the page" depend on a stable page key. INFERRED: offsets computed on normalised or concatenated section text must map back to page and offset, or a refusal can name the wrong page. B1's 130 spreads make "page 45" ambiguous | The PDF specification (ISO 32000) page-label section; measure `/PageLabels` presence on A1, B1, C1; local code `checker/document_extract.py` and `checker/pdf_text.py` | E22, E23 |
| G12 | **The adapters are text-only, so the "VLM fallback" and "Gemini for pages" have no request path or evidence.** Nothing measures VLM invented text, and there is no mitigation research for image-borne injection | Role 13's third rung and the image-borne injection boundary. INFERRED: an abstention-first design must detect invented text (R4 I8, R3 D7) *before* span grounding. `ground()` only proves a quote is in the OCR text, which the VLM itself wrote | Provider docs for image/PDF input (G02 sources); the bake-off (G04) scored for invented text; arXiv literature on hallucination in VLM-based OCR and on visual prompt injection | E07, E08, E32 |
| G13 | **The multi-cloud India mapping has almost no sourced rows outside OCR.** There is nothing on object storage, KMS/HSM, queues and orchestration, confidential compute or malware scanning per region. Azure South India DI, OCI India and Sarvam SageMaker regions are inferred or unverified. Google Mumbai Preview terms are unchecked. The "Azure for Students" constraint is undocumented. No buyer evidence says multi-cloud is required | PLAN_11 requires every mapping row to be SOURCED or INFERRED. INFERRED: as it stands the table would be mostly INFERRED, and a residency-first design cannot claim end-to-end in-India processing if a single dependency (queue, KMS, model) lacks an India row | AWS regional product-services list; Azure products-by-region page; Google Cloud locations pages per product; OCI regions and service-availability docs (the last returned 403 to R4, so try the docs.oracle.com regions page); the Azure for Students offer terms on azure.microsoft.com; buyer interviews on whether cloud choice matters to them | E24 |
| G14 | **Indian operator obligations that bear on retention and residency are unresearched.** Examples: the status and commencement of the DPDP Rules and the processor duties that flow down by contract; CERT-In directions on log retention and incident reporting; MeitY cloud-provider empanelment for public-sector buyers; sector cloud frameworks for SEBI- or RBI-regulated buyers; and whether Companies (Accounts) Rules requirements on keeping books of account in India reach a third-party audit copy | Log retention could *require* keeping some records for a fixed period, which pulls against PLAN_07's minimisation. A regulated buyer class could make India residency a hard requirement rather than a "trust and procurement argument" (PLAN_07 §3). INFERRED from general knowledge, all UNVERIFIED: I believe CERT-In issued directions in 2022 and the DPDP Rules were notified in late 2025, but neither has been opened. Note that `scope.py`'s DPDP2023 body is *product* scope, not our operator compliance | Official Gazette (egazette.gov.in) and meity.gov.in for the DPDP Rules; cert-in.org.in for the directions; sebi.gov.in circulars for cloud frameworks; India Code for the Companies (Accounts) Rules; a law-firm client alert, as PLAN_07 already suggests | E25 |
| G15 | **Deletion semantics per artefact class are unevidenced.** Unknowns: backups and point-in-time restore, provider-side abuse-monitoring logs, whether hashes and quoted spans outlive content, batch-OCR temp storage (Azure 24 h unless deleted, Google up to one day on abnormal termination), and Textract operational storage | PLAN_12 must publish a retention table per class (raw upload, page images, OCR text, extracted facts, spans, findings, attestations, logs, hashes). INFERRED: a "deleted" claim that ignores backups or provider temp storage is a false claim to a buyer | Each chosen store's backup and retention docs; the provider data-privacy pages already cited in R4 G3/G5; Anthropic/Azure OpenAI retention docs (G02); the decision in G01 | E28 |
| G16 | **Contractual provider terms are unresolved, and ZDR is per-account, not per-provider.** Open items: Sarvam training default and the "for Indian customers" residency condition; Azure DI training position; OCI retention; Textract storage after opt-out; the Spellbook-style "unless otherwise agreed" pattern | The provider abstraction must carry *account-level* preconditions (retention setting, training opt-out, region, contract status) that are checked at call time, not documented once. INFERRED from E26–E27: the same provider can be safe on one account and unsafe on another | Signed DPAs and written vendor answers (add to `docs/VENDOR_QUESTIONS.md`); AWS Organizations AI opt-out policy status for the actual org (R4 G2) | E26–E28 |
| G17 | **File safety at intake is unresearched.** Unknowns: malware scanning options, hostile-PDF parser attack surface (`pdf_text.py` and any new PDF library), decompression bombs, encrypted or password PDFs, polyglot files, and type sniffing. A new dependency needs a stated reason (CLAUDE.md) | Intake is the one component that touches raw untrusted bytes before any gate. INFERRED: whether scanning is a cloud-native service or a self-hosted engine changes the multi-cloud mapping and whether files must sit in object storage before scanning (which ties back to G01) | Cloud-native malware-scanning docs for storage on each provider; the ClamAV project documentation; CVE records for any PDF library considered; OWASP guidance on file upload | E29, E33 |
| G18 | **Nothing supports a cost or latency range for a 500-page bundle end to end.** OCR prices exist. LLM extraction token cost, India-region rate limits for extraction models, and Google `asia-south1` quotas do not | PLAN_11 requires "cost per 100-page document … with their sources". INFERRED: at Sarvam's 10 req/min and Textract Mumbai's 5 TPS, backpressure is a design element. Without extraction-model limits the queue cannot be sized | Provider pricing and quota pages (G02 sources); a token-count dry run over A1 and B1 text with the provider's token-counting endpoint, which generates nothing and sends only public text | E31 |
| G19 | **No F8 cell-state module or metric policy exists.** `review_table.py` and `review_record.py` serve benchmark fixtures. METRIC_POLICY's abstention cap (≤ 0.25) is defined for entailment | INFERRED: on A1, 20.7% of pages are textless and more are corrupted. A per-page abstention rule could push cell abstention near or past 0.25 before any model runs. PLAN_12 needs a separate F8 metric (per-bucket false accepts and abstentions by page class), or METRIC_POLICY will reject the correct behaviour. R1's proposed cell states (ABSTAINED, INVALIDATED_BY_CHANGE) have no home module | `docs/METRIC_POLICY.md` in full and `docs/PLAN_06_EVALUATION.md` (local, not read here); HCI literature on automation bias in review interfaces, relevant to R2's "Apply All" point | E16, E30 |

### Tier 3 — hygiene before external use

| # | Gap | Why it matters | Where evidence could come from | Rows |
|---|---|---|---|---|
| G20 | **Stamps, seals and signatures.** No vendor handles stamps or seals. `pdf_signature.py` exists, but the prevalence of signed pages in scheme bundles is unmeasured, and no research maps which corporate-law facts depend on a stamp (STAMP is a DECLARED body) | Decides whether stamp-region detection is v1 or later, and whether signature verification is an intake stage | Run `pdf_signature.py` over A1, A2, A3, B1, C1 (public); the public verification page of the e-stamp issuer (terms first); object-detection literature | E21 |
| G21 | **Formats other than PDF** (.xlsx, .docx, images, ZIP, email) are undecided | Changes the sniff and normalise stage and the OCR routing | The 20-document test; buyer interviews | E36 |
| G22 | **Unchecked load-bearing rows and known residual defects.** R3 E11 and H4, R4 D4/D6/E3/E4, and R1 A11 were not re-checked. R1 Result item 5 "(US implicit)" is wrong: Harvey's page lists the US explicitly. R4 cites four URLs that now redirect. R3 H1 omits "In India, for Indian customers" | PLAN_12 will cite these rows as design limits (rate limits, page caps, residency) | A second source-check pass on the listed rows; fix wording in R1, R3 and R4 in separate single-file tasks | E34 |
| G23 | **Inherited unsourced premises.** PLAN_01 quotes a Harvey prompt and "5,000 mini-agents" (R1 C11/C12). PLAN_07 has an unsourced SpotDraft India row and an unsourced ₹50 crore figure. `gemini_model.py`'s docstring overstates arXiv 2606.29213 | PLAN_12 must not restate these as rationale | A `RETRACTIONS.md` entry, as R1 recommends; re-source or remove in PLAN_01 and PLAN_07 | E08, E25, E35 |
| G24 | **Competitor India residency is only "not found"** (R1 D8, R2 E4) | A residency-first design may be sold as a differentiator only after re-checking, so PLAN_12 should record it as positioning, not fact | Harvey and Spellbook security pages re-read at PLAN_12 time; vendor questions 18 | — |

---

## Unresolved issues

1. **G01 is a decision, not a research result.** No amount of reading resolves the PLAN_07-vs-F8
   conflict. It needs the founder, informed by buyers.
2. **G07 (XBRL) is a hypothesis.** I have not opened any exchange XBRL page. It may be unavailable,
   robots-restricted or unsuited to per-cell matching.
3. **G14's regulatory items come from general knowledge**, not pages opened. Each could be
   inapplicable to a processor of our kind.
4. **I read only headers of `review_table.py`, `review_record.py` and `pdf_signature.py`**, and
   only the first 30 lines of `METRIC_POLICY.md`. A fuller read could show more existing machinery
   than G19 and G20 credit.
5. **`docs/PLAN_03_DATA_SOURCES.md`, `PLAN_05`, `PLAN_06`, `NON_GOALS.md` and `FEATURES.md` were not
   read in this task.** Any of them may already constrain or answer part of G08, G19 or G21.
6. **Tier ordering is my judgment (INFERRED).** A judge panel may weigh residency (G02, G13, G14)
   above measurement (G04–G06) if the buyer conversation makes residency the purchase criterion.

## Recommended next action

Cheapest and most decisive first. None of these edits another file as part of this task.

1. **Put G01 to the founder as a binary question before PLAN_12 is drafted.**
   - Option (a): client documents persist under tenant-set retention, with ZDR on provider calls.
   - Option (b): F8 is session-scoped, with no batch OCR and no stored review.
   - Record the answer as a PLAN_07 amendment.
2. **Research task R6: extraction-model providers (G02).** One file with the same structure as R3
   and R4, covering Anthropic, Gemini on Vertex and AI Studio, and Azure-hosted models:
   - India regions and cross-region routing
   - retention, ZDR and abuse-monitoring
   - PDF/image input limits
   - rate limits and token prices
   - every model ID checked against the vendor's current list
3. **A scope decision on G03**, with acquisition tickets for the CAA Rules 2016 and the Ind AS rules
   through the existing two-human route. Until then PLAN_12 treats FS and notice cells as
   extract-and-cite only, with verification refused, named.
4. **Measurement task M1 (no external model calls needed for parts a–c), public documents only:**
   - a. Per-page script census over A1, B1, C1 and `corpus/testdocs/_raw/` (G09).
   - b. Page-label and spread census (G11).
   - c. `pdf_signature.py` over the same files (G20).
   - d. The OCR bake-off on A1's scanned and corrupted pages, scored for CER, invented text and
     stamp handling, with each vendor's confidence output recorded (G04, G05, G12). Part (d) needs
     the founder's keys and retention/opt-out preconditions set first (R3 action 3).
5. **Research task R7: XBRL feasibility (G07)**, checking robots first. If positive, label B1's FS
   cells against it for G06.
6. **Research task R8: the India cloud mapping beyond OCR (G13), plus operator obligations (G14) and
   deletion semantics (G15).** Official pages only, with a law-firm alert for DPDP as PLAN_07 already
   suggests.
7. **A second source-check pass** on the rows in G22 before PLAN_12 cites them as limits.

---

## What this means for PLAN_12 (document intake architecture)

All items are INFERRED design consequences of the gaps above.

1. **Do not start with the pipeline. Start with G01.** The retention decision determines whether
   PLAN_12 has queues, stored page images, a review-state store and batch OCR at all. A design that
   assumes persistence while PLAN_07 §1 forbids it would fail its own judge criteria.
2. **Write the provider abstraction so that account-level terms are data, checked at call time**
   (G02, G16). Each adapter entry carries:
   - `region`, `cross_region_routing`, `retention_days`, `training_opt_out_verified`,
     `zdr_contracted`
   - `max_pages_per_request`, `returns_confidence`, `returns_bbox`, `emits_model_text`
   Any unknown field is `UNVERIFIED`, and an UNVERIFIED precondition disables the adapter for tenant
   documents. That keeps the R6 gap from becoming a silent residency or retention defect.
3. **Make the per-page router three-way from day one: text trusted / text untrusted / no text**
   (G05). Mark the "untrusted" detector OPEN with R5's heuristic as a placeholder known to
   under-flag. The router records *why* each page took its path.
4. **Define the page key and span coordinates before any extractor is wired** (G11):
   - `(file_sha256, pdf_page_index)` is identity.
   - `printed_label` is optional metadata.
   - Offsets are into the stored per-page text of record (native or OCR, labelled which), never into
     concatenated or normalised section text.
   - Section-level extraction maps offsets back to page and offset, or abstains.
5. **Separate "extract and cite" from "verify" per segment, driven by `scope.py`** (G03, G10).
   - Segments whose governing body is not held produce page-cited extractions with verification
     refused and the body named.
   - Unknown segment type produces classification uncertainty.
   - This lets F8 ship useful tables on FS pages without implying verification it cannot perform.
6. **Leave the confidence gate's signal type as a named OPEN choice with a measurement plan**
   (G04). Candidates: vendor confidence, cross-vendor agreement, native-vs-OCR agreement. The gate's
   *interface* (page in; `PASS | ABSTAIN(reason)` out; signal values logged) can be fixed now. Its
   threshold and signal cannot.
7. **Quarantine model-written text structurally** (G12): image descriptions, VLM transcriptions of
   pages that fail agreement. It gets a separate field that the span grounder cannot search. Treat
   VLM output as a proposal needing a second reading, not as the text of record.
8. **Give F8 its own metric section** (G19): per page class (text / untrusted / scanned), false
   accepts and abstentions reported separately. State explicitly that METRIC_POLICY's 0.25
   abstention cap was set for entailment and does not transfer.
9. **Present the multi-cloud table honestly** (G13). Rows for every dependency, not just OCR, each
   SOURCED, INFERRED or UNVERIFIED. Until R8 lands, the residency-first design cannot claim
   end-to-end in-India processing, and PLAN_12 should say so in the table.
10. **Size for ranges, not a point, and say n=1** (G08, G18). Design envelope: ≥ 40 MB and ≈ 600
    PDF pages per file (R5). Batch size, matter size and end-to-end cost are OPEN with named
    measurement tasks. Cost per 100 pages may be stated only for the OCR share, where sourced.
11. **Keep out of PLAN_12's rationale** the unsourced premises in G23 and competitor residency
    claims beyond "not found" (G24).
