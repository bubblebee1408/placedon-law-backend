# R1 — Harvey: how a document enters, is analysed, and is checked

Written 2026-09-14 for PLAN_11 Track R (task R1). Feeds `PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md`.
All pages fetched 2026-09-14 unless stated. Markers: **SOURCED** (URL opened this session) ·
**INFERRED** (my reasoning, labelled) · **UNVERIFIED** (seen only in a search snippet, a login-walled
page, or a third party; not usable as fact).

Reading discipline is the one in `COMPETITOR_FEATURE_MATRIX.md`: a vendor page is marketing;
engineering blogs are the vendor describing itself; neither says how well anything works; and
**absence from a page is not absence from a product.**

---

## Question

1. **Entry.** How does a document get into Harvey — upload paths, Vault, file types, size / page /
   count limits, integrations (iManage, SharePoint, NetDocuments, Word, Outlook)?
2. **Analysis.** How is it analysed — Vault review tables and bulk extraction, workflows/agents,
   long-document handling?
3. **Checking.** How are outputs checked — citations to pages/spans, verification features, human
   review, hallucination controls?
4. **Custody.** Retention, zero data retention (ZDR), data residency.
5. How do the findings bear on `LEGAL_AI_ARCHITECTURE_ANALYSIS.md`, `COMPETITOR_FEATURE_MATRIX.md`,
   and the PLAN_12 intake design?

## Sources checked

| Source | Type | Accessed? |
|---|---|---|
| https://www.harvey.ai/platform/vault | vendor product page, undated | yes |
| https://www.harvey.ai/products | vendor product page, undated | yes |
| https://www.harvey.ai/platform/workflow-agents | vendor product page, undated | yes |
| https://www.harvey.ai/platform/assistant | vendor product page | fetched; content returned was the Agents page (redirect or merged page) — used only for what it said |
| https://www.harvey.ai/security | vendor security page, undated | yes |
| https://www.harvey.ai/legal/subprocessor-update-faqs | vendor legal page, "Last updated: May 13, 2025" | yes |
| https://developers.harvey.ai/guides/vault | public API docs | yes |
| https://developers.harvey.ai/guides/assistant | public API docs | yes |
| https://developers.harvey.ai/llms.txt | public API docs index | yes |
| https://developers.harvey.ai/api-reference/vault/upload-files-to-project.md | public API reference | yes |
| https://developers.harvey.ai/api-reference/vault/get-review-table-row-details.md | public API reference | yes |
| https://developers.harvey.ai/api-reference/vault/get-review-table-metadata.md | public API reference | yes |
| https://developers.harvey.ai/api-reference/completion/completion.md | public API reference | yes |
| https://www.harvey.ai/blog/introducing-the-next-version-of-vault | vendor blog, 21 Nov 2024 | yes |
| https://www.harvey.ai/blog/scaling-harveys-document-systems-vault-file-upload-and-management | engineering blog, 9 Oct 2025 | yes |
| https://www.harvey.ai/blog/building-new-file-ingestion-system-to-scale-firm-knowledge | engineering blog, 11 Feb 2026 | yes |
| https://www.harvey.ai/blog/scaling-document-processing-across-harvey | engineering blog, 27 Jul 2026 | yes |
| https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute | research blog, 14 Aug 2026 | yes |
| https://www.harvey.ai/blog/agentic-vault-search-and-organization | vendor blog, 8 Sep 2026 | yes |
| https://www.harvey.ai/blog/introducing-agent-builder | vendor blog, 9 Mar 2026 | yes |
| https://www.harvey.ai/blog/building-harveys-imanage-integration | engineering blog, 29 Oct 2025 | yes |
| https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications | vendor blog, 22 Oct 2025 | yes |
| https://www.harvey.ai/blog/why-we-built-our-own-cloud-agent-infrastructure | engineering blog, 1 Jun 2026 | yes |
| https://www.harvey.ai/blog/biglaw-bench-hallucinations | research blog, 7 Oct 2024 | yes |
| https://www.harvey.ai/blog/biglaw-bench-sources | research blog, 23 Sep 2024 | yes |
| https://www.harvey.ai/blog/biglaw-bench-retrieval | research blog, 13 Nov 2024 | yes |
| https://www.harvey.ai/blog/using-agents-to-scale-harveys-knowledge-sources | engineering blog, 2 Feb 2026 | yes |
| https://www.harvey.ai/blog/knowledge-workflows-enhancements | vendor blog, 18 Dec 2025 | yes |
| https://www.harvey.ai/blog/the-brief-march-2026 · -june-2026 · -july-2026 · -august-2026 | monthly release summaries, 10 Mar / 11 Jun / 17 Jul / 13 Aug 2026 | yes |
| https://www.harvey.ai/blog/harvey-partners-with-scc-online | vendor blog, 15 Jan 2026 | yes |
| https://www.harvey.ai/blog/harvey-to-expand-team-with-new-bengaluru-office | vendor blog, 10 Jul 2025 | yes |
| `help.harvey.ai` and `eu.help.harvey.ai` articles and release notes (Vault article, "Support for New File Types", "Australia Data Processing", Quick Start Part 3, etc.) | vendor help centre | **NOT accessed — every URL tried 307-redirects to an Auth0 login.** Not followed, per the no-login-wall rule. Anything these pages say appears below only as UNVERIFIED |
| Third-party reviews and pricing blogs surfaced by search (eesel.ai, vaquill.ai, aivortex.io, legalaiinsight.com, releasebot.io, claudeforlawyers.com, `help-harvey.vercel.app`) | not vendor, not reputable press | **Not used as evidence.** The vercel.app "help" host is not a Harvey domain and was deliberately ignored |

Web searches run (WebSearch): Vault file limits and types; Vault review table 100,000 files;
review tables "10,000" columns; data residency EU/Australia/ZDR; Harvey India data residency;
`site:harvey.ai India`; OCR / scanned PDF; citations verification hallucination BigLaw Bench;
"cite check"/"verify citations"; Workflow/Agent Builder; iManage/SharePoint/NetDocuments/Word;
Assistant upload limits; the exact PLAN_01 quote "Answer the user's question using ONLY the text
provided below"; Vault "mini-agents" 5,000; Harvey pricing.

---

## Evidence found

### A. Entry — how a document gets in

| # | Claim | Marker | URL |
|---|---|---|---|
| A1 | Vault page: "100,000 files stored per vault"; "Securely store and organize up to 100,000 documents including files, email correspondence, and queries in vaults" | SOURCED (page undated) | https://www.harvey.ai/platform/vault |
| A2 | Nov 2024: "increased the file limit per project from 1,000 to 10,000 documents" | SOURCED (superseded by A1 on the current page) | https://www.harvey.ai/blog/introducing-the-next-version-of-vault |
| A3 | Oct 2025 engineering blog: workflows of "upwards of 50,000 documents" in single transactions; projects with "more than 100,000 documents"; "upload time for 10,000 files dropped from 20 minutes to just over two minutes" | SOURCED | https://www.harvey.ai/blog/scaling-harveys-document-systems-vault-file-upload-and-management |
| A4 | Mar 2026: "upload size limits now up to 500 MB for most major file types in Vault and Assistant" | SOURCED | https://www.harvey.ai/blog/the-brief-march-2026 |
| A5 | API upload: `POST /api/v1/vault/upload_files/{project_id}`; "Max size of 500 MB for all file types"; "A maximum of 50 files can be uploaded per API request"; `duplicate_mode` enum `skip / replace / keep`; "Beware of HTTPS timeouts if too many large files are sent at a time" | SOURCED | https://developers.harvey.ai/api-reference/vault/upload-files-to-project.md |
| A6 | Vault API rate limit "10 requests per minute"; files carry `processing_status` (uploaded → processing → ready_to_query) | SOURCED | https://developers.harvey.ai/guides/vault |
| A7 | Accepted types (API guide): PDF, .doc/.docx, .xls/.xlsx, .ppt/.pptx, .txt, .md, HTML, CSV, RTF, XML, .eml/.msg, JPEG/PNG/TIFF images, and common code files | SOURCED | https://developers.harvey.ai/guides/vault |
| A8 | June 2026: ".pst file support in Vault and Assistant" | SOURCED | https://www.harvey.ai/blog/the-brief-june-2026 |
| A9 | July 2026: audio uploaded "directly into Assistant or Vault for a speaker-labeled, editable transcript"; "Take and Upload Photos on iOS" to "Analyze handwritten notes, exhibits, or diagrams" | SOURCED | https://www.harvey.ai/blog/the-brief-july-2026 |
| A10 | Agents page: "Give agents documents, images, video, or audio" | SOURCED | https://www.harvey.ai/platform/workflow-agents |
| A11 | Audio up to 4 GB in Vault / 2 hours per file; 50-file limit on direct desktop upload; 10,000 Vault files per Assistant thread (15,000 in a Shared Space); "5–10 files per prompt" recommended | UNVERIFIED — search snippets of login-walled help pages only | (help.harvey.ai, not opened) |
| A12 | Assistant API: prompt max 4,000 characters with a file, 20,000 without; 20 requests/minute | SOURCED | https://developers.harvey.ai/guides/assistant |
| A13 | Vault page: "Sync materials from document management systems like iManage, SharePoint, and Google Drive" | SOURCED | https://www.harvey.ai/platform/vault |
| A14 | Connectors named in Jul 2026: "iManage, SharePoint, Box, Google Drive, NetDocuments, and on-premise setups" | SOURCED | https://www.harvey.ai/blog/scaling-document-processing-across-harvey |
| A15 | DMS ingestion: folder selection → crawl and manifest → diff → apply changes → downstream chunking/embedding/OCR. Two modes: one-time import ("hundreds of thousands of files") and one-way continuous sync. "we use hash-based comparison when available, falling back to timestamp comparison if necessary." "We chose Temporal as our orchestrator" | SOURCED | https://www.harvey.ai/blog/building-new-file-ingestion-system-to-scale-firm-knowledge |
| A16 | iManage: OAuth 2.0; iManage Universal API; imported files "follow the same segregation, retention, and compliance policies"; data model "does not differentiate between file import sources"; cloud and on-prem (Azure Application Proxy) | SOURCED | https://www.harvey.ai/blog/building-harveys-imanage-integration |
| A17 | Microsoft 365: Word add-in "Draft and edit documents, run playbook reviews, and get real-time answers"; Outlook routes "emails and attachments directly to Vault projects"; SharePoint selective folder sync | SOURCED | https://www.harvey.ai/blog/how-harvey-integrates-with-microsoft-365-applications |
| A18 | Processing pipeline, verbatim: "The platform downloads the file, identifies the file type, extracts text and structure, runs OCR for scanned content, and captures metadata such as file type, size, page count, source, and processing status." Then chunk + embed, then index "so Vault, Assistant, and workflows can search, cite, and reason" | SOURCED | https://www.harvey.ai/blog/scaling-document-processing-across-harvey |
| A19 | Failure handling: "if one document is corrupt, password-protected, unsupported, or empty, the workflow marks that file and continues processing the rest"; "Extraction runs through ordered fallback chains. Eligible OCR traffic starts with a primary path, then falls back through Harvey-operated services and deterministic local paths." "An OCR-heavy upload can slow the extraction lane without starving indexing" (separate extraction / chunk-embed / index queues) | SOURCED | https://www.harvey.ai/blog/scaling-document-processing-across-harvey |
| A20 | Scale: latest complete week "24.8 million" documents, "56 TB" of original file data | SOURCED (vendor-reported) | https://www.harvey.ai/blog/scaling-document-processing-across-harvey |
| A21 | Oct 2025: "Complex and OCR-heavy documents will experience elevated error rates" — listed among scale challenges the team "set out to systematically address" | SOURCED (the quote); whether it is still true is UNVERIFIED | https://www.harvey.ai/blog/scaling-harveys-document-systems-vault-file-upload-and-management |
| A22 | No named OCR vendor, no OCR confidence threshold, no per-page abstention, no malware scanning and no upload-time content hashing/dedup (beyond `duplicate_mode` and sync change detection) found on any page listed above | INFERRED from pages read — a statement about those pages, **not** about the product | — |

### B. Analysis — review tables, workflows, long documents

| # | Claim | Marker | URL |
|---|---|---|---|
| B1 | Review tables: "Extract and compare key data points from thousands of documents at once in a structured, tabular format"; "96% key-term extraction accuracy" (no method stated on page) | SOURCED (the 96% is vendor-reported, method UNVERIFIED) | https://www.harvey.ai/platform/vault |
| B2 | Column types including "dates, currency, or verbatim text"; a "Verbatim" column "extracts a direct quote from the document, preserving its exact wording"; "extract 25+ data points per document"; firm-built custom extraction workflows; per-workflow recall figures (e.g. Merger Agreements 27 fields 99.66%) | SOURCED (recall figures vendor-reported) | https://www.harvey.ai/blog/introducing-the-next-version-of-vault |
| B3 | "A lawyer uploads up to 10,000 files, writes questions about each document"; result is one row per document group, one cell per question | SOURCED | https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute |
| B4 | **Long-document mechanism:** "The production Review Table harness uses semantic search to retrieve snapshots of the relevant document corpus" per cell. An alternative was "trained in a multi-turn agentic harness equipped with read- and grep-style tools" (reported ~50% fewer input tokens at matched quality) | SOURCED | https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute |
| B5 | RL-trained review-table model: answer score 0.903 vs "0.867 for Fable 5 and 0.857 for GPT-5.6-Sol"; "84.1% citation precision and 91.93% citation recall"; the article does not clearly state production deployment | SOURCED (Harvey's internal benchmark; model names as Harvey writes them, not checked against the model vendors' pages) | https://www.harvey.ai/blog/training-frontier-review-table-models-with-applied-compute |
| B6 | Retrieval over "Complex documents (e.g., hundreds of pages and potentially hundreds of thousands of tokens of text)" with cross-references and defined terms; approach = metadata contextualising passages, features like recency, LLM relevance reasoning; "up to 30% more relevant content" than embedding/reranking baselines | SOURCED (vendor benchmark) | https://www.harvey.ai/blog/biglaw-bench-retrieval |
| B7 | Mar 2026: review tables inside custom Workflow agents; "Automatically Convert Folders into Groups in Review Tables" | SOURCED | https://www.harvey.ai/blog/the-brief-march-2026 |
| B8 | Agent Builder (formerly Workflow Builder): "Human-in-the-loop checkpoints as a core feature"; vendor counts 20M+ terms extracted via review tables, 445K+ Deep Analysis reports, 25,000+ custom workflows | SOURCED (counts vendor-reported) | https://www.harvey.ai/blog/introducing-agent-builder |
| B9 | July 2026: attach a file to a review table column to "Evaluate every row against a fixed reference, like a template or regulatory standard" | SOURCED | https://www.harvey.ai/blog/the-brief-july-2026 |
| B10 | Agentic Vault search: "Attach a full Vault to your query … and the agent finds the right document on its own"; uses folder, naming convention and uploader as signals; "every file the agent touches is logged in the workspace's audit trail"; organisation changes are proposed first and "never runs a change without a person confirming it first" | SOURCED | https://www.harvey.ai/blog/agentic-vault-search-and-organization |
| B11 | Assistant/Vault model selector includes an Anthropic "Opus 4.8" (Jun 2026); the public API lists model IDs up to `claude-opus-4-7` and `gpt-5-5` | SOURCED as Harvey's own wording; **not verified** against Anthropic/OpenAI pages, and the API list and blog disagree on what is current | https://www.harvey.ai/blog/the-brief-june-2026 · https://developers.harvey.ai/guides/assistant |
| B12 | Indian content: SCC Online as a selectable knowledge source (announced 15 Jan 2026; "case law, legislation, secondary materials … statute law, rules, notifications"); integration shipped per June 2026 Brief | SOURCED. Point-in-time / version access **not mentioned** on either page | https://www.harvey.ai/blog/harvey-partners-with-scc-online · https://www.harvey.ai/blog/the-brief-june-2026 |

### C. Checking — citations, verification, hallucination controls

| # | Claim | Marker | URL |
|---|---|---|---|
| C1 | **Review-table cell schema:** each cell has `citations[]` with `citation_page` (integer) and `citation_quote` (string); `summary` and `additional_context` carry `[N]` markers into that array; `summary` is "user-edited value if present, otherwise the AI-generated answer" | SOURCED | https://developers.harvey.ai/api-reference/vault/get-review-table-row-details.md |
| C2 | **Per-cell human review state:** `is_edited`, `is_verified`, `verified_user` (email), `verified_timestamp`, `is_flagged`, `flagged_user`, `flagged_timestamp` | SOURCED | https://developers.harvey.ai/api-reference/vault/get-review-table-row-details.md |
| C3 | Cell Lock protects finalized answers "from editing or re-running by teammates" (Aug 2026); re-run a single cell (Jun 2026); in-line cell correction (Jul 2026) | SOURCED | https://www.harvey.ai/blog/the-brief-august-2026 · https://www.harvey.ai/blog/the-brief-june-2026 · https://www.harvey.ai/blog/the-brief-july-2026 |
| C4 | Completion API: `include_citations` default true; `sources[]` of "cited source snippets" with citation number, document name, page, quoted text | SOURCED | https://developers.harvey.ai/api-reference/completion/completion.md |
| C5 | "Internally at Harvey, we define an effective source as one that links to a specific piece of text _within_ a source document." The public benchmark scores only document-level sources; "On internal evaluations, however, Harvey demands more of its models." | SOURCED (Sep 2024) | https://www.harvey.ai/blog/biglaw-bench-sources |
| C6 | Hallucination = "a factual claim made by an LLM that can be demonstrably disproven by reference to a source of truth." Method: "a system of models" that first "break down an answer into all of its relevant factual claims" then "consider whether each factual claim made in the answer is true based on the information in the source of truth documents." Result: "Harvey's Assistant model hallucinates around 1 in 500 claims (.2%)" on "a subset of BigLaw Bench tasks that require reasoning over multiple, long documents" | SOURCED (Oct 2024; vendor-run, vendor-graded; described as a measurement, not stated to be a production gate) | https://www.harvey.ai/blog/biglaw-bench-hallucinations |
| C7 | Agents page: "Every claim is backed by a citation and every step is logged, making it easy to verify accuracy before partner or client review"; "Preview the plan, adjust the scope, and approve work before Harvey begins" | SOURCED (marketing) | https://www.harvey.ai/platform/workflow-agents |
| C8 | "Hallucinated citations cause an automatic rejection" — inside a multi-step evaluator used when **onboarding new knowledge sources**, not on answers served to users | SOURCED | https://www.harvey.ai/blog/using-agents-to-scale-harveys-knowledge-sources |
| C9 | Ask LexisNexis: "trusted Shepard's® Citations information to validate cited authorities" | SOURCED | https://www.harvey.ai/blog/knowledge-workflows-enhancements |
| C10 | A published deterministic (non-model) check of legal conclusions, statute currency, or commencement for citations — not found on any page above | INFERRED from pages read; not evidence of absence | — |
| C11 | PLAN_01's quoted Harvey safety prompt, *"Answer the user's question using ONLY the text provided below"* | UNVERIFIED — exact-phrase web search returned no Harvey page containing it | — |
| C12 | PLAN_01's Vault "5,000 mini-agents" | UNVERIFIED — search for "mini-agents" 5,000 returned no Harvey page containing it. Nearest sourced statement: review tables make "hundreds of thousands of model calls" (B3/B5 page) | — |

### D. Custody — retention, ZDR, residency

| # | Claim | Marker | URL |
|---|---|---|---|
| D1 | "We don't use inputs, outputs, or uploaded documents to train underlying models"; "Harvey requires Zero Data Retention (ZDR) by model providers" | SOURCED | https://www.harvey.ai/security |
| D2 | "Customers can determine what data to upload to Harvey, how long it is retained, and whether that data can be shared with others." | SOURCED | https://www.harvey.ai/security |
| D3 | "Harvey hosts its cloud environment in Microsoft Azure"; "Customer data for each customer is logically separated"; SAML SSO, audit logs, IP allow-listing; ethical walls synced and enforced; SOC 2 Type II, ISO 27001, ISO 27701, ISO 42001 listed | SOURCED | https://www.harvey.ai/security |
| D4 | "For customers with requirements or preferences for data localization we offer processing in the EU and Switzerland or Australia." | SOURCED | https://www.harvey.ai/security |
| D5 | Subprocessors AWS and GCP added for "Gemini and Claude series"; ZDR = "subprocessors do not store your data; it is only processed ephemerally"; processing "in the United States, European Union, or Australia"; "No human review" | SOURCED (Last updated May 13, 2025) | https://www.harvey.ai/legal/subprocessor-update-faqs |
| D6 | Agent runtime: "Every law firm contract we sign, and every enterprise contract, requires zero data retention (ZDR)." "ZDR means designing the runtime so customer data is not written into durable application storage by default." Sandbox disk "lifecycle-bound … automatically cleaned up"; "Automatic state persistence and zero retention are mutually exclusive"; sovereign self-hosted deployments named as a need | SOURCED (Jun 2026) | https://www.harvey.ai/blog/why-we-built-our-own-cloud-agent-infrastructure |
| D7 | Deleted vaults recoverable by workspace admins within a "30-day window" | SOURCED | https://www.harvey.ai/blog/the-brief-august-2026 |
| D8 | India data processing/residency region | **Not found.** Checked: security page (D4 lists EU, Switzerland, Australia), subprocessor FAQ (US, EU, Australia), SCC Online and Bengaluru-office posts (no hosting statement). Not evidence that none exists or is planned | INFERRED from pages read |
| D9 | Indian customers: PwC, Shardul Amarchand Mangaldas & Co., S&A Law Offices named (Jul 2025) | SOURCED | https://www.harvey.ai/blog/harvey-to-expand-team-with-new-bengaluru-office |
| D10 | Per-seat prices (e.g. ~$1,200/seat/month, 20–25 seat minimums) | UNVERIFIED — third-party blogs only; no Harvey pricing page found | — |

---

## Evidence quality

- **Strongest:** the public API reference (A5, A6, A12, C1, C2, C4). It is a contract developers
  code against, so it is less likely to be puffed than a product page, and it is the only source
  giving *shapes* (page + quote citations, verify/flag state per cell). Caveat: the API may expose a
  subset of the UI, and version drift is visible (B11).
- **Good, first-party, self-describing:** engineering blogs (A3, A15, A18–A21, B4, D6). Specific,
  dated, often naming trade-offs. Still unaudited and written for recruiting and marketing.
- **Weakest usable:** undated product pages (A1, B1, C7) and vendor metrics (96% extraction,
  0.2% hallucination, 84.1% citation precision, 24.8M docs/week). Vendor-run, vendor-graded, no
  independent replication found. Quote them as "Harvey reports", never as accuracy.
- **Not usable:** the help centre (login-walled; not accessed) and third-party review/pricing sites.
  That leaves some precise per-surface limits (A11) and all pricing (D10) unverified.
- **Staleness:** limits moved quickly (1,000 → 10,000 files/project in Nov 2024; 100,000 per vault
  on the current page; 500 MB in Mar 2026). Treat every number as of its page date.

## Result

1. **Entry.** Harvey takes documents in by browser upload, a public upload API (500 MB/file,
   50 files/request, 10 rpm), Outlook routing, iOS photo capture, and DMS connectors (iManage,
   SharePoint, Google Drive, Box, NetDocuments; one-time import or one-way sync with hash-or-timestamp
   change detection on Temporal). Formats go well beyond PDF/Word: spreadsheets, slides, email
   (.eml/.msg/.pst), images, audio, video on the agents page. Vault holds up to 100,000 files per
   vault on the current product page. All SOURCED.
2. **Processing.** One shared pipeline for every surface: type detection → text + structure
   extraction → OCR for scanned content (ordered fallback chain ending in deterministic local paths)
   → page count and status metadata → chunk → embed → index. Stages run on separate queues; a bad
   file is marked and skipped, not fatal to the batch. SOURCED. Harvey itself called complex and
   OCR-heavy documents a source of "elevated error rates" (Oct 2025).
3. **Analysis.** Bulk work is a review table: documents × questions, up to 10,000 files, typed
   columns (including verbatim quote), per-column reference files, used inside custom agents.
   **For long documents the production review-table harness retrieves semantic-search snapshots
   per cell rather than reading the whole document** (SOURCED, Aug 2026). They are testing an
   agentic read/grep harness as the alternative.
4. **Checking.** Every cell and every Assistant answer carries citations shaped as
   **page number + quoted text**. Each cell has a human review state: edited, verified (who, when),
   flagged (who, when), plus lock and single-cell re-run. Harvey's published hallucination control is
   model-based claim decomposition and entailment against sources, reported as a benchmark
   measurement (0.2% of claims). Its RL review-table model reports 84.1% citation precision on its
   own benchmark. Shepard's validates authorities, but only on the LexisNexis path. SOURCED. I found
   no published deterministic, currency-aware or commencement-aware check (INFERRED from the pages
   read).
5. **Custody.** Harvey says it does no training on customer data, requires ZDR from model
   providers, makes ZDR a runtime design property of its agent infrastructure, runs on Azure with
   logical per-customer separation, and lets customers set retention. Residency options named: EU,
   Switzerland, Australia (US implicit). No India region found. SOURCED except the India negative,
   which is INFERRED.

### Where this confirms, extends, or contradicts the existing docs

**`LEGAL_AI_ARCHITECTURE_ANALYSIS.md` (2026-08-12).** This document is about PoSH / Court Corridor.
It says almost nothing about Harvey's document path, so R1 mostly *extends* it from zero. Its one
Harvey sentence is partly contradicted:

| That doc says | Finding | Verdict |
|---|---|---|
| Harvey serves lawyers "on desktop" and "cannot reach a litigator on a phone" | Harvey Mobile is listed on the products page (per the matrix); iOS photo upload and Vault sharing on iOS shipped Jul 2026 (A9) | **Contradicts** the desktop-only framing. Whether it reaches a Nagpur litigator is a market question these pages cannot settle |
| "in English" | Spanish interface end to end, Aug 2026 (https://www.harvey.ai/blog/the-brief-august-2026) | **Contradicts** English-only as of Aug 2026. No Indian-language UI found |
| Implicitly not serving India | SCC Online Indian case law and legislation as a knowledge source (B12); Bengaluru office; SAM, PwC, S&A named (D9) | **Contradicts** any reading that Harvey is absent from India. Not contradicted: I found no India residency (D8) and no point-in-time statute access (B12) |
| "$50,000/year" | No vendor pricing found; third-party figures differ (D10) | **Unsourced there, still UNVERIFIED.** Do not repeat |
| (PLAN_01, cited by that doc's lineage) Harvey's safety mechanism "is a prompt"; "Harvey verifies that a citation exists" | Harvey publishes claim-level checking against source documents (C6), sentence-level citation scoring (B5, C5), and per-cell human verification (C2). The quoted prompt was not found (C11) | **Contradicts** the "only a prompt / only existence" framing as a description of what Harvey *publishes*. Still **consistent** with the narrower point that none of it is deterministic or currency-aware (C10) |

**`COMPETITOR_FEATURE_MATRIX.md` (2026-09-01).**

| Matrix says | Finding | Verdict |
|---|---|---|
| Vault: "Securely store, organize, and bulk-analyze legal documents"; products page lists Contract Intelligence, Command Center, Memory, Spaces | Re-fetched 2026-09-14: same wording, same surfaces | **Confirms** |
| "it asserted a Vault ceiling of 100,000 documents. Harvey's own page says 'thousands'. The specific figure was not sourced from the vendor and should not be repeated." | Harvey's own **Vault** page says "100,000 files stored per vault" (A1); the Oct 2025 engineering blog says projects of "more than 100,000 documents" (A3). The *products* page does say "thousands" | **Contradicts.** The correction was right about the products page and wrong about the vendor. `COMPETITOR_PATTERN_ANALYSIS.md` H3 ("LIKELY FABRICATED") is contradicted on the number too. Its "parallel agents" mechanism is still unsourced (C12), but review tables do run "hundreds of thousands of model calls". Recommend a `RETRACTIONS.md` entry (not made here — single-file task) |
| Tabular/grid review: Harvey = "Contract Intelligence" | The documented grid surface is **Vault Review Tables** (B1–B3, C1–C3) | **Extends / corrects the cell** |
| Word / Outlook / mobile: Harvey "yes" | Word add-in with playbook review, Outlook to Vault routing, iOS (A9, A17) | **Confirms and extends** |
| Placedon `review_table.py` is PARTIAL: "axes are documents × rules, not documents × questions" | Harvey's axis is documents × questions, but column reference files (B9) let a column test each row against "a template or regulatory standard". That moves toward documents × rules, and the rule is model-applied | **Extends.** The distinction still holds for *deterministic* rules, but is narrower than the matrix implies |
| Deterministic verification / point-in-time reconstruction / commencement provenance: "not listed" | Still not found on any page read (C10, B12), including the SCC Online announcement | **Confirms**, under the same rule: not listed ≠ absent |
| Nothing on custody | ZDR, retention control, Azure, EU/CH/AU residency, no India region found (D1–D8) | **Extends** |

---

## What this means for PLAN_12 (document intake architecture)

All items below are INFERRED design consequences unless they restate a sourced row.

1. **The pipeline shape PLAN_11 specifies is industry-normal, and that is reassuring rather than
   differentiating.** Harvey's published pipeline (A18, A19) is type detection → extraction → OCR →
   metadata incl. page count → chunk/embed → index. It runs on separate stage queues, marks and
   skips bad files, and falls back through OCR paths to a deterministic local path. PLAN_11's
   upload → hash → sniff → malware scan → per-page split matches it. Adopt from Harvey: **per-stage
   queues** (one OCR-heavy 400-page scheme must not starve text-layer documents) and **file-level
   "mark and continue"** with an explicit reason code (corrupt / password-protected / unsupported /
   empty). Keep what Harvey does not publish (A22): per-page idempotency, upload hashing, malware
   scan.

2. **Citation contract: Harvey's public floor is page + quote. Make ours page + quote + offset +
   hash, and refuse when the quote does not resolve.** C1/C4 show the user-visible unit is
   `citation_page` + `citation_quote`. D2 (page-anchored spans) should at minimum emit the same
   pair, because users will expect it. Our added value is that an unresolvable quote is a
   **refusal**, not a lower score. Harvey's own benchmark shows 84.1% citation precision for its
   best review-table model (B5): about 1 in 6 citations do not match reference evidence on that
   benchmark. That is the gap a hard span gate closes.

3. **Adopt the per-cell review state almost verbatim.** C2/C3 (edited, verified-by/at,
   flagged-by/at, lock, single-cell re-run) is what a reviewing lawyer expects in a grid. For F8,
   bind it to `review_record.py`: a verification is an immutable attestation event, and an edit
   after verification invalidates it. Add a state Harvey does not publish: **ABSTAINED(reason, page)**.
   A cell the gates refused must look different from a cell nobody has reviewed.

4. **Long documents: do not copy the per-cell semantic-snapshot retrieval.** B4 says Harvey's
   production review table answers each cell from retrieved snapshots. That is the design
   `PLAN_01` argues against: nothing downstream detects a bad retrieval. It also clashes with
   `PROVIDER_DECISION` §2, which keeps whole-section context for verbatim quotability. For a merger
   scheme or Ind AS statements, PLAN_12 should build a **page map → section/table map first**. It
   should extract per section with the section in full, and record *which pages were read* for
   every cell. Then "not found" is a statement about named pages, not about a top-k. Harvey's
   agentic read/grep harness experiment (B4) is the closer analogue and worth watching.

5. **OCR: Harvey publishes no confidence gate and no per-page abstention, and admits OCR-heavy
   error rates (A21, A22).** This supports keeping PLAN_11's "confidence gate with no threshold
   until measured, failing page abstains" as a real differentiator for scanned Indian filings. It
   is only a differentiator if the refusal names the page (item 2). The ordered fallback chain
   ending in a deterministic local path (A19) is worth copying as the tier structure for role 13.

6. **Sync means re-audit.** Harvey's one-way DMS sync with hash-then-timestamp change detection
   (A15) is a cheap pattern. For us, a changed hash should do more than re-index: it should
   **invalidate prior verdicts and attestations** on that document and queue re-verification. That
   ties intake to `staleness.py` and the event log, which a retrieval product has no reason to do.

7. **Limits to design against (reference points, not targets).** 500 MB/file, 50 files/API
   request, 10 rpm on Vault API, 10,000 files per review table, 100,000 files per vault
   (A1, A4, A5, A6, B3). Our buyer is an Indian CS/company-secretarial practice, far smaller.
   PLAN_12 should size for **hundreds of pages per document and tens of documents per matter**
   (pending R5) and must not import Harvey's scale targets as requirements.

8. **Custody: ZDR and an immutable audit record pull in opposite directions. Separate them
   explicitly.** Harvey's line (D6) is that persistence and zero retention are mutually exclusive.
   PLAN_12 should keep *document content* under customer-set retention with ZDR on provider calls
   (D1, D2). It should keep the *audit record* (hashes, page numbers, quoted spans, verdicts,
   attestations) as the durable artefact. The spans are quotations of client documents, so the
   record's retention and deletion rules must be decided, not assumed. Open question for PLAN_07.

9. **Residency is an open flank, not a proven one.** No India processing region was found for
   Harvey (D8), though it serves Indian firms (D9) and holds SCC Online content (B12). A
   residency-first design (Azure Central/South India, AWS ap-south-1, etc.) is a credible selling
   point for Indian buyers. It becomes a claim only after Harvey's current residency list is
   re-checked; do not state "Harvey cannot host in India".

10. **Where Harvey is already closer than our docs assume:** column reference files (B9) and
    SCC Online legislation (B12) mean Harvey can already put "check this document against this
    regulatory text" in front of an Indian lawyer. The wedge that remains is **currency**: which
    version of the provision applied on the document's date, and a refusal when the instrument is
    not held. Nothing read here shows Harvey doing that. PLAN_12 should make the as-of date a
    first-class intake field, extracted and page-cited like any other fact, because every
    downstream verdict depends on it.

## Unresolved issues

- **Help-centre limits are unverified** (A11): per-thread file caps, the direct-upload cap in the
  UI, audio caps, any page-count or OCR limits. They sit behind a login; not accessed.
- **Is the 100,000-file figure per vault, per project, or storage-bounded?** A1 says "per vault";
  a search snippet mentioned a 100 GB storage limit that I could not open (UNVERIFIED).
- **Is the RL review-table model (B5) in production?** The article does not say clearly.
- **Is claim-decomposition checking (C6) a production gate or only an evaluation?** The 2024 post
  describes measurement. No page read says answers are blocked on it.
- **OCR vendor and quality**, and whether Oct 2025's "elevated error rates" still hold. Not stated.
- **Model names drift.** The API lists IDs up to `claude-opus-4-7`/`gpt-5-5`; blogs name Opus 4.8,
  Fable 5, GPT-5.6-Sol, Claude Sonnet 5. None checked against the model vendors' pages. This also
  bears on `TECHNICAL_PLAN_EVIDENCED_2026_09.md`, which lists "Claude Opus 5, Claude Sonnet 5,
  GPT-5.6, and Fable 5.1" as Harvey selectables. Not re-verified here.
- **India residency** (D8) and **pricing** (D10) remain open.
- **Horizon Scanning** (named in `TECHNICAL_PLAN_EVIDENCED_2026_09.md`) was not checked in this
  task. The matrix's "Regulatory change monitoring: Harvey not listed" is neither confirmed nor
  contradicted here.
- The PLAN_01 quoted prompt (C11) and "5,000 mini-agents" (C12) have no source found.

## Recommended next action

1. **Record the Vault-ceiling correction.** Add a `RETRACTIONS.md` entry saying
   `COMPETITOR_FEATURE_MATRIX.md`'s "thousands, not 100,000" note and
   `COMPETITOR_PATTERN_ANALYSIS.md` H3 are contradicted by https://www.harvey.ai/platform/vault.
   Also flag PLAN_01's unsourced prompt quote and "5,000 mini-agents" for sourcing or removal.
   (Separate change; not made here.)
2. **Give PLAN_12 a cell-level contract table** built from items 2, 3 and 6 above:
   `page`, `quote`, `char_offset`, `span_hash`, `pages_read[]`, `state ∈ {PROPOSED, ABSTAINED,
   EDITED, VERIFIED, FLAGGED, LOCKED, INVALIDATED_BY_CHANGE}`, `attested_by/at`.
3. **Put an explicit "as-of date" extraction step** into the PLAN_12 intake chain (item 10).
4. **If a Harvey trial or demo is ever available**, ask the `VENDOR_QUESTIONS.md` set plus: page
   caps per document; OCR confidence exposure; whether the claim-check gates answers; India
   processing region; whether SCC Online legislation is versioned by date.
5. Re-run this check before any external use. Every limit here moved within the last 18 months.
