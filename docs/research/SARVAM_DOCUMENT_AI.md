# R3 — Sarvam AI: what document / vision / OCR capability actually exists

Research date: **2026-09-14**. Track R, task R3 of `docs/PLAN_11_NEXT_MOVE.md`.
Every row below carries a marker. **SOURCED** = stated on the URL given, which was opened
on 2026-09-14. **INFERRED** = my reasoning from sourced facts, stated as such.
**UNVERIFIED** = asked and not answered by any page I could open. No login walls were
crossed; nothing behind `dashboard.sarvam.ai` was read.

---

## Question

The founder wants "an Indian model like Sarvam to analyse photos and dragged-and-dropped
documents". What does Sarvam AI offer **today** for document parsing / OCR / vision —
product and model names, Indian scripts, tables, stamps, handwriting, multi-page PDFs,
input limits, API shape, pricing, data residency, retention, training use, and published
accuracy — and how does it compare (where sourced) with Azure Document Intelligence and
Google Document AI for Indic documents?

## Short answer

1. **Document OCR and field extraction exist and are real.** The model is **Sarvam
   Vision** (3B-parameter state-space VLM, announced 5 Feb 2026). It is exposed as the
   **Document AI API** (`/doc-ai/v1`, launched 18 Aug 2026, "powered by Sarvam Vision 1.5")
   with two endpoints — **Digitise** (full-page OCR + layout + tables) and **Extract**
   (schema-driven fields) — plus a no-code dashboard, **Doc Agents**, and a **self-hosted**
   SageMaker package.
2. **"Analyse photos" in the general sense does not exist as a Sarvam-model API.** The only
   image-input chat model Sarvam serves is **Gemma 4 31B** (Google's open model, beta,
   whitelist-only), which Sarvam's own docs say is "not tuned for Indian languages" and
   "Not for … document OCR". Sarvam-105B (their reasoning LLM) is text-only. Sarvam Vision
   *does* reading and extraction; it does not *analyse* a document in the legal-review sense.
3. **Stamps, seals and signatures: no documented capability.** Zero mentions across every
   Sarvam page read (list in *Sources checked*).
4. **Hard managed-API limits that shape our intake:** 10 pages per job (does not rise with
   plan), 10 requests/minute on every plan, async-only.
5. **Training use of customer data is contradictorily documented** across Sarvam's own
   Privacy Policy, EULA and Trust Center. Until resolved in writing, treat the managed API
   as *possibly training on inputs unless opted out*.
6. **All published accuracy numbers are vendor-run**, on a benchmark (Sarvam Indic OCR
   Bench) that is not among Sarvam's public Hugging Face datasets, and they are for the
   Feb 2026 model, not "Vision 1.5". None are on legal documents.

---

## Sources checked

Sarvam — own documentation (docs.sarvam.ai, no visible page dates; changelog dates used):
- https://docs.sarvam.ai/llms.txt · https://docs.sarvam.ai/llms-full.txt · https://docs.sarvam.ai/api/llms.txt · https://docs.sarvam.ai/api-reference/llms.txt · https://docs.sarvam.ai/docai/llms.txt (indexes, used to enumerate every document/vision page)
- https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md
- https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md
- https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md · https://docs.sarvam.ai/api-reference/doc-ai/job/extract.md · https://docs.sarvam.ai/api-reference/doc-ai/job/results.md · https://docs.sarvam.ai/api-reference/doc-ai/job/upload.md
- https://docs.sarvam.ai/docai/getting-started/overview.md · https://docs.sarvam.ai/docai/how-to/digitise-a-document.md · https://docs.sarvam.ai/docai/extract-as-csv-excel.md · https://docs.sarvam.ai/docai/resources/faq.md
- https://docs.sarvam.ai/api/getting-started/pricing.md · https://docs.sarvam.ai/api/getting-started/ratelimits.md · https://docs.sarvam.ai/api/getting-started/models.md
- https://docs.sarvam.ai/api/getting-started/models/open-source/gemma-4-31b.md · https://docs.sarvam.ai/api/getting-started/models/sarvam-105b.md
- https://docs.sarvam.ai/api/platform/data-retention.md
- https://docs.sarvam.ai/api/self-hosted/introduction.md · https://docs.sarvam.ai/api/self-hosted/hosted-vs-self-hosted.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/deploy-vision.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/api-vision.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/limitations.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/operations.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/get-started.md
- Changelog, every entry 2025-05 → 2026-09-09, e.g. https://docs.sarvam.ai/changelog/2026/2/1.md · https://docs.sarvam.ai/changelog/2026/3/1.md · https://docs.sarvam.ai/changelog/2026/5/1.md · https://docs.sarvam.ai/changelog/2026/8/18.md

Sarvam — company site and legal:
- https://www.sarvam.ai/blogs/sarvam-vision (dated 5 Feb 2026)
- https://www.sarvam.ai/api-pricing
- https://www.sarvam.ai/privacy-policy ("Updated on: July 29, 2026")
- https://www.sarvam.ai/terms-of-service ("Effective from July 29, 2026")
- https://www.sarvam.ai/eula ("Last Modified: 22nd May, 2026")
- https://www.sarvam.ai/trust-center (no visible date; FAQ answers read from the page's own embedded FAQ data)
- https://aws.amazon.com/marketplace/pp/prodview-exwi6jgzqsqc2 (Sarvam Vision listing)
- https://huggingface.co/api/datasets?author=sarvamai and https://huggingface.co/api/models?author=sarvamai (public list endpoints, to test whether the benchmark/model is published)

Comparators:
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 (ms.date 2026-04-18, updated 2026-07-10)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0 (ms.date 2026-08-15)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0 (ms.date 2026-05-01)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0 (ms.date 2026-09-08)
- https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security (ms.date 2026-07-22; the older `/legal/cognitive-services/…` URL redirects here)
- https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'centralindia' and contains(productName,'Document Intelligence') (Microsoft's public retail-price API; the marketing pricing page renders "$-" without sign-in)
- https://docs.cloud.google.com/document-ai/docs/languages (last updated 2026-09-03)
- https://docs.cloud.google.com/document-ai/limits (last updated 2026-09-03)
- https://docs.cloud.google.com/document-ai/docs/regions (last updated 2026-09-03)
- https://docs.cloud.google.com/document-ai/docs/data-usage (last updated 2026-09-03)
- https://cloud.google.com/products/document-ai/pricing

Held evidence read first: `docs/PLAN_03_DATA_SOURCES.md` §"OCR — the gate on bulk document review".
**That section carries no URLs** for any of its figures (the 76-point Devanagari spread,
the Marathi legal-scan study, Textract/Azure claims). This file neither confirms nor
refutes them; it cites none of them as sourced.

Searches that returned nothing (negative results, stated as searched — not as "does not exist"):
- `stamp|seal` (word match) across every Sarvam page listed above, the Azure Read/Layout
  pages and the Google pages: **0 hits**. `signature` on Sarvam pages: 0 hits (other than
  AWS S3 URL parameters).
- A Sarvam-model endpoint for general image understanding / visual Q&A: searched the full
  docs index, API-reference index and models page. None found beyond Document AI and the
  third-party Gemma 4 31B.
- "Sarvam Indic OCR Bench" as a public dataset: not among the 16 datasets listed at the
  `sarvamai` Hugging Face author endpoint on 2026-09-14; web search found no other host.
- Sarvam Vision weights: not among the 14 `sarvamai` Hugging Face models.
- A benchmark published for "Sarvam Vision 1.5" specifically: web search and the docs
  returned only the Feb 2026 Sarvam Vision blog.
- Per-block OCR confidence in the **managed** Digitise output: not documented on the
  overview, digitise, results or download pages.

---

## Evidence found

### A. What the offering is called and when it appeared

| # | Claim | Marker | URL |
|---|---|---|---|
| A1 | Sarvam Vision announced 5 Feb 2026 as "a 3B-parameter state-space vision-language model", capable of captioning, scene text, charts, complex tables | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| A2 | Architecture described as the VLM plus two harness modules: "semantic layout parser" and "reading order network"; continual pretraining, SFT, RL with verifiable rewards | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| A3 | Model ID `sarvam-vision`; "Known limitations: 10-page cap per job" | SOURCED | https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md |
| A4 | 18 Aug 2026: "Replaced the Document Digitization API with Document AI (`/doc-ai/v1`), powered by an upgraded Sarvam Vision 1.5 trained for both OCR and key-value extraction"; old API "is now legacy" | SOURCED | https://docs.sarvam.ai/changelog/2026/8/18.md |
| A5 | Naming history: Document Digitization added to SDKs (Feb 2026); 10-page limit + ₹1.5/page (Mar 2026); "Document Intelligence has been renamed to Document Digitization" and repriced to ₹0.5/page (May 2026) | SOURCED | https://docs.sarvam.ai/changelog/2026/2/1.md · https://docs.sarvam.ai/changelog/2026/3/1.md · https://docs.sarvam.ai/changelog/2026/5/1.md |
| A6 | Doc Agents (renamed from "Sarvam Pages") is the no-code dashboard for Extract / Digitise / Translate | SOURCED | https://docs.sarvam.ai/changelog/2026/8/18.md · https://docs.sarvam.ai/docai/getting-started/overview.md |
| A7 | The model page says "Sarvam Vision" / `sarvam-vision`; the API overview says "Sarvam Vision 1.5". Which version the `model` form field selects, and its accepted values, are not listed in the API reference | SOURCED (the inconsistency) / UNVERIFIED (resolution) | https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md · https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md |

### B. Does "analyse photos" exist?

| # | Claim | Marker | URL |
|---|---|---|---|
| B1 | Gemma 4 31B is "the only chat model here that accepts images"; beta, access per API key by whitelisting; "Not tuned for Indian languages"; "Not for: Indian language workloads or document OCR"; base64 images only; 10 MB request cap | SOURCED | https://docs.sarvam.ai/api/getting-started/models/open-source/gemma-4-31b.md |
| B2 | Sarvam-105B supports "10 most-spoken Indian languages + English"; its model page describes text/code-mixed input and a 128K context — no image input | SOURCED | https://docs.sarvam.ai/api/getting-started/models/sarvam-105b.md · https://docs.sarvam.ai/api/getting-started/models.md |
| B3 | The Sarvam Vision blog shows captioning and "in-the-wild" OCR, and says current efforts are "focused on pushing the frontiers of document intelligence" | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| B4 | A "Vision Real-time" rate limit (30 req/min) is listed, but no endpoint documentation for it was found in the docs or API-reference indexes | SOURCED (limit row) / UNVERIFIED (what it serves) | https://docs.sarvam.ai/api/getting-started/ratelimits.md |
| B5 | Therefore: a Sarvam-owned model that takes a photo and *reasons* about it (as opposed to reading text off it) is not offered through the public API today | INFERRED from B1–B4 | — |
| B6 | Drag-and-drop upload exists in Sarvam's own dashboard ("Drag and drop or click to upload PDF, JPEG, or PNG") — it is Sarvam's UI, not an embeddable component; our product would call the API | SOURCED (dashboard) / INFERRED (implication) | https://docs.sarvam.ai/docai/how-to/digitise-a-document.md |

### C. Languages and scripts

| # | Claim | Marker | URL |
|---|---|---|---|
| C1 | 23 languages: all 22 scheduled Indian languages + English — Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese, Bodo, Dogri, Kashmiri, Konkani, Maithili, Manipuri, Nepali, Sanskrit, Santali, Sindhi, Urdu, English | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md |
| C2 | "Always specify the correct language code for optimal accuracy"; `language` is a single BCP-47 code per job | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md · https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md |
| C3 | Language codes differ between managed and self-hosted: managed `od-IN`, `brx-IN`; self-hosted `or-IN`, `bodo-IN`; self-hosted default is `hi-IN`, anything else → `400 UNSUPPORTED_LANGUAGE` | SOURCED | https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/api-vision.md |
| C4 | How a mixed-script page (e.g. English deed with Hindi stamp text) should be declared, and what happens to the non-declared script | UNVERIFIED | — |

### D. Tables, stamps, handwriting, multi-page, layout

| # | Claim | Marker | URL |
|---|---|---|---|
| D1 | Tables: "Handles merged cells and multi-level headers", "invisible borders"; output as HTML/Markdown tables (vendor claim, no table metric beyond D-benchmarks below) | SOURCED | https://docs.sarvam.ai/api/getting-started/models/sarvam-vision.md |
| D2 | Digitise section types: headline, sub-headline, section-title, header, paragraph, footer, footnote, page-number, table, image, image-caption, photograph, chart/diagram, advertisement, folio — **no stamp, seal, signature or checkbox type** | SOURCED | https://docs.sarvam.ai/docai/how-to/digitise-a-document.md |
| D3 | Stamps/seals/signatures: no documented detection or extraction capability (see negative search) | UNVERIFIED (absence of documentation, not proof of absence) | — |
| D4 | Handwriting: dashboard "Document format" choice of Printed / Handwritten / Mixed; a "Digitise Handwritten Document" template ships | SOURCED | https://docs.sarvam.ai/docai/how-to/digitise-a-document.md |
| D5 | API has a `content_type` enum "Nature of the document content" whose values are not listed in the reference; that it maps to Printed/Handwritten/Mixed | SOURCED (field) / INFERRED (mapping) | https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md |
| D6 | No handwriting accuracy figure for any Indian language was found | UNVERIFIED | — |
| D7 | Digitise output includes "AI-generated image descriptions" for image sections; the blog's examples show an "Enhanced Version" and chart descriptions written by the model | SOURCED | https://docs.sarvam.ai/docai/getting-started/overview.md · https://www.sarvam.ai/blogs/sarvam-vision |
| D8 | Blog "Edge Cases": incorrect Bengali transliteration while describing an image; "Instruction following for such long-tail requests can be low quality" (Santhali) | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| D9 | Multi-page: PDF max 10 pages; ZIP max 10 flat JPG/PNG images, ordered by filename; >10 → `400 invalid_request_error`; "Split larger documents into batches of 10 pages or fewer" | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md |
| D10 | "The 10-page cap applies uniformly across plans; upgrading does not raise it" (dashboard FAQ) | SOURCED | https://docs.sarvam.ai/docai/resources/faq.md |
| D11 | FAQ advice: "Blurry or skewed scans hurt accuracy more than any prompt change. Re-scan at 300 DPI" | SOURCED | https://docs.sarvam.ai/docai/resources/faq.md |

### E. Input limits and API shape

| # | Claim | Marker | URL |
|---|---|---|---|
| E1 | Managed API formats: PDF, PNG, JPG/JPEG, ZIP; max file 200 MB | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md |
| E2 | Dashboard: PDF, JPEG, PNG; 50 MB per file; 10 pages per project | SOURCED | https://docs.sarvam.ai/docai/resources/faq.md |
| E3 | Self-hosted rejects TIFF, WebP, BMP, GIF with `415 UNSUPPORTED_MEDIA_TYPE`; password-protected PDF → `400 INVALID_INPUT` | SOURCED | https://docs.sarvam.ai/api/self-hosted/sagemaker/api-vision.md |
| E4 | Whether the managed API also rejects TIFF (not in its format list) | INFERRED likely; UNVERIFIED | — |
| E5 | Endpoints: `POST /doc-ai/v1/job/digitise`, `POST /doc-ai/v1/job/extract`, `GET /doc-ai/v1/job/{id}/status`, `GET …/results`, `GET …/download-url`, `POST /doc-ai/v1/job/upload`; auth header `api-subscription-key`; multipart form; `file` or `upload_ids`; async only | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md · https://docs.sarvam.ai/api-reference/doc-ai/job/digitise.md |
| E6 | Job states: `pending`, `running`, `completed`, `partially_completed` ("Some pages succeeded, some failed"), `failed`, `rejected`; usage reports `pages_succeeded` / `pages_failed` | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md |
| E7 | Digitise output: `html` (default) / `md` / `json`; JSON has "blocks containing text, tag, and bounding box"; download is a ZIP with the primary file, `metadata/page_NNN.json` per page, `manifest.json`; results endpoint returns per-page `content` | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md · https://docs.sarvam.ai/api-reference/doc-ai/job/results.md |
| E8 | Extract: exactly one of inline JSON `schema` (root object, every field needs `type` + `description`, depth ≤ 4) or saved `config_id`; results include `annotations` "where every leaf has `confidence` and `sources`"; optional `classification` flag | SOURCED | https://docs.sarvam.ai/api-reference/doc-ai/job/extract.md · https://docs.sarvam.ai/api-reference/doc-ai/job/results.md |
| E9 | The shape of Extract `sources` (page? bbox? text span?) | UNVERIFIED | — |
| E10 | Managed Digitise per-block OCR confidence | UNVERIFIED (not documented) | — |
| E11 | Rate limit: Document Intelligence **10 req/min on Starter, Pro and Business alike**; "Upgrading your plan does not increase Vision limits" | SOURCED | https://docs.sarvam.ai/api/getting-started/ratelimits.md |
| E12 | Official Python and JavaScript SDKs (`sarvamai`); JS SDK uses wire names, `schema` must be a JSON string | SOURCED | https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview.md |

### F. Self-hosted (AWS SageMaker)

| # | Claim | Marker | URL |
|---|---|---|---|
| F1 | Since Aug 2026, Sarvam Vision can be deployed from AWS Marketplace as a SageMaker endpoint "in your own VPC … your audio and documents never leave your infrastructure"; network isolation, no outbound internet | SOURCED | https://docs.sarvam.ai/api/self-hosted/introduction.md · https://docs.sarvam.ai/changelog/2026/8/18.md |
| F2 | Self-hosted limits: 500 pages per document hard cap; async 50 MB per file; sync ~6 MB and ≤5 pages recommended (60 s AWS timeout); ~6 GB model on `ml.g6e.xlarge` (L40S) | SOURCED | https://docs.sarvam.ai/api/self-hosted/sagemaker/limitations.md · https://docs.sarvam.ai/api/self-hosted/sagemaker/deploy-vision.md |
| F3 | Self-hosted `output_format=json` returns per block `bbox`, `reading_order`, `type`, `text`, **`layout_confidence` and `ocr_confidence`** | SOURCED | https://docs.sarvam.ai/api/self-hosted/sagemaker/api-vision.md |
| F4 | Model package ARNs are region-specific; the doc names no region list | SOURCED | https://docs.sarvam.ai/api/self-hosted/sagemaker/limitations.md |
| F5 | AWS Marketplace listing: version "akshar-v1-aug-13 - latest"; software fee $10.00/hr on `ml.g6e.xlarge` / `ml.g6e.4xlarge` real-time, $5.00/hr on `ml.g6.*` batch, plus AWS infrastructure | SOURCED | https://aws.amazon.com/marketplace/pp/prodview-exwi6jgzqsqc2 · https://docs.sarvam.ai/api/self-hosted/sagemaker/operations.md |
| F6 | Whether the package is offered in `ap-south-1` (Mumbai) / `ap-south-2` (Hyderabad) | UNVERIFIED (regions not rendered on the listing as fetched) | — |
| F7 | Whether the self-hosted package is the same model as managed "Vision 1.5" (docs say "same models as the Managed API"; package label says v1 Aug-13) | UNVERIFIED | https://docs.sarvam.ai/changelog/2026/8/18.md |
| F8 | Async endpoints can scale to zero | SOURCED | https://docs.sarvam.ai/api/self-hosted/sagemaker/operations.md |

### G. Pricing

| # | Claim | Marker | URL |
|---|---|---|---|
| G1 | Document AI: **Digitisation API ₹0.50 per page; Extraction API ₹1.00 per page** | SOURCED | https://www.sarvam.ai/api-pricing |
| G2 | The docs pricing page still lists only "Document Digitization API ₹0.5/page, Max 10 pages per job" (docs lag the site) | SOURCED | https://docs.sarvam.ai/api/getting-started/pricing.md |
| G3 | New accounts get ₹100 free credits (was ₹1,000) | SOURCED | https://docs.sarvam.ai/changelog/2026/5/1.md · https://docs.sarvam.ai/api/getting-started/pricing.md |
| G4 | Digitise of a 100-page document ≈ ₹50 (10 jobs); Extract ≈ ₹100; at 10 req/min, submission of those 10 jobs fits in ~1 minute, but a 1,000-page batch needs ≥100 job submissions ≈ 10 minutes before any polling load | INFERRED (arithmetic on G1, D9, E11; ignores whether status polls count against the 10 req/min limit, which is UNVERIFIED) | — |

### H. Data residency, retention, training

| # | Claim | Marker | URL |
|---|---|---|---|
| H1 | Trust Center: "Complete data residency in India"; FAQ: "Our managed production environment runs on Microsoft Azure's Central India region, and our LLM inference runs on sovereign GPU infrastructure operated by Yotta and NxtGen" | SOURCED | https://www.sarvam.ai/trust-center |
| H2 | Terms of Service §8.2: "We process and store information in India **and may transfer it to other countries** where we and our service providers operate" | SOURCED | https://www.sarvam.ai/terms-of-service |
| H3 | H1 and H2 are in tension; which governs a Document AI API call without an enterprise contract is not stated | INFERRED (tension) / UNVERIFIED (resolution) | — |
| H4 | Retention is per workspace (Owner-only) with a ladder: No retention (0 days), 1, 15, 30, 45, 60, 90, 180, 365, 730 days; product overrides exist only for "Voice Agents" and "Sarvam API"; "Voice Agents does not currently support 0-day"; changes are not retroactive | SOURCED | https://docs.sarvam.ai/api/platform/data-retention.md |
| H5 | Whether Document AI jobs fall under the "Sarvam API" override, and whether 0-day retention is accepted for them | UNVERIFIED | — |
| H6 | Privacy Policy retention table: "Your Content (Inputs/Outputs) — User-configurable (default: 30 days after last access)"; usage logs 1 year | SOURCED | https://www.sarvam.ai/privacy-policy |
| H7 | Privacy Policy, under the heading **"Default Policy: Opt-In"**: "We use Your content (including inputs, uploads, prompts, or generated outputs) to train, fine-tune, and/or improve our AI models **unless you explicitly opt-out**" | SOURCED | https://www.sarvam.ai/privacy-policy |
| H8 | EULA: "Sarvam will not use Your Content to train our AI models **unless you provide explicit opt-in consent**" (scope: downloaded/installed "Software") | SOURCED | https://www.sarvam.ai/eula |
| H9 | Trust Center: "Customer data is never used to train models **for other customers**"; "We do not use your data, PII or otherwise, to improve models for anyone else" | SOURCED | https://www.sarvam.ai/trust-center |
| H10 | Terms §17.5: training on Inputs/Outputs "in accordance with the Privacy Policy … and (where required) subject to your consent" | SOURCED | https://www.sarvam.ai/terms-of-service |
| H11 | H7–H10 do not agree on the default for a self-serve API account; H9 permits training a shared model on data that is then used "for" the same customer only in a narrow reading | INFERRED | — |
| H12 | Trust Center lists ISO 27001:2022 and SOC 2 Type II "Certified", DPDP "In progress", ISO 42001 "In progress"; reports under mutual NDA | SOURCED | https://www.sarvam.ai/trust-center |
| H13 | Trust Center lists "Inference-time guardrails against prompt injection" as a control — not documented for Document AI specifically | SOURCED (claim) / UNVERIFIED (applies to Doc AI) | https://www.sarvam.ai/trust-center |

### I. Published accuracy (all vendor-run)

| # | Claim | Marker | URL |
|---|---|---|---|
| I1 | **Sarvam Indic OCR Bench**: 20,267 samples, 22 scheduled languages, documents "ranging from 1800-present", block-level; metric "word accuracy … 100 x (1 - WER)" | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| I2 | Word accuracy, Sarvam Vision vs Gemini 3 Pro vs Google Cloud Vision (GCV): Hindi 95.91 / 95.12 / 90.94; Marathi 93.13 / 90.39 / 87.86; Bengali 92.61 / 90.79 / 88.23; Tamil 93.42 / 92.73 / 89.69; Telugu 87.70 / 85.32 / 82.58; Gujarati 90.74 / 88.40 / 81.63; Kannada 89.89 / 87.36 / 85.54; Malayalam 91.60 / 87.10 / 88.30; Odia 81.95 / 75.39 / **82.20**; Urdu 87.01 / 85.76 / 81.17; Sanskrit 81.65 / 76.62 / 64.90; Maithili 81.95 / 50.96 / 49.04; **Kashmiri 55.93** / 44.46 / 33.41 | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| I3 | Same table reports Opus 4.5 and GPT 5.2 far lower on several scripts (e.g. Sanskrit 4.25 and −21.22) | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision |
| I4 | **olmOCR-Bench (English subset)**, Sarvam Vision per category: ArXiv Math 86.5, Base 99.6, Headers/Footers 96.3, Tiny text 91.0, Multi-column 82.2, **Old scans 49.8**, Old math 81.0, Tables 88.3; the harness and filtered dataset are public | SOURCED | https://www.sarvam.ai/blogs/sarvam-vision · https://github.com/sarvamai/olmOCR-bench-sarvam-api · https://huggingface.co/datasets/sarvamai/olmOCR-Bench-English |
| I5 | Blog's subset wording — "we filtered out 1,258 samples out of 1,403 total" — is ambiguous about whether 1,258 were kept or removed | SOURCED (wording) / UNVERIFIED (meaning) | https://www.sarvam.ai/blogs/sarvam-vision |
| I6 | OmniDocBench v1.5 English-only split (628 samples) is reported in a chart; no figure is in the page text I could extract | SOURCED (that it was run) / UNVERIFIED (score) | https://www.sarvam.ai/blogs/sarvam-vision |
| I7 | AWS listing: "best-in-class scores on global benchmarks (olmOCR-Bench, OmniDocBench V1.5) for English" and "leading accuracy on the Sarvam Indic OCR Bench" | SOURCED (as vendor claim) | https://aws.amazon.com/marketplace/pp/prodview-exwi6jgzqsqc2 |
| I8 | Sarvam Indic OCR Bench is not among the `sarvamai` public HF datasets (16 listed on 2026-09-14) → not independently reproducible from public material found | SOURCED (list) / INFERRED (reproducibility) | https://huggingface.co/api/datasets?author=sarvamai |
| I9 | No benchmark figures found for "Vision 1.5"; all figures above predate it | UNVERIFIED | — |
| I10 | None of the benchmarks is on Indian corporate or legal paper, stamp paper, or sealed/stamped pages; the Indic bench's domain mix is described only generally | INFERRED from I1 description | https://www.sarvam.ai/blogs/sarvam-vision |

### J. Comparators, where sourced

| # | Claim | Marker | URL |
|---|---|---|---|
| J1 | **Azure DI v4.0 Read/Layout, printed extraction** includes Hindi, Marathi, Nepali, Sanskrit, Tamil, Urdu, Bodo, Dogri, Santali, Punjabi **(Arabic script)** | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 |
| J2 | Bengali, Telugu, Kannada, Malayalam, Gujarati, Odia, Assamese, Sindhi appear on that page **only in the language-detection list**, which the page says "can include languages not currently supported for text extraction"; Punjabi in Gurmukhi is not in the extraction list | SOURCED | same |
| J3 | Azure DI v4.0 handwritten extraction: English, Chinese Simplified, French, German, Italian, Japanese, Korean, Portuguese, Spanish, Russian, Thai, Arabic — **no Indian language** | SOURCED | same |
| J4 | Azure DI: up to 2,000 pages per PDF/TIFF, 500 MB (S0); inputs and results stored 24 hours then deleted (earlier via Delete Analyze Result); processed and stored "in the same region where the Document Intelligence resource was created" | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/read?view=doc-intel-4.0.0 · https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security |
| J5 | Azure DI is sold in `centralindia`: S0 Read $1.50 per 1K pages (0–1M), $0.60 above; S0 Batch Layout $10 per 1K; disconnected (on-prem container) Read tiers from 2M pages/year | SOURCED | https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'centralindia' and contains(productName,'Document Intelligence') |
| J6 | The Azure privacy page I opened does not itself state whether inputs train Microsoft models | SOURCED (absence on that page) / UNVERIFIED (Microsoft's position) | https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security |
| J7 | **Google Enterprise Document OCR** lists Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Nepali, Punjabi (Gurmukhi), Tamil, Telugu; handwriting marked Supported for Hindi, Marathi, Nepali, Bengali and **Not Supported** for Gujarati, Kannada, Malayalam, Punjabi, Tamil, Telugu. Odia, Assamese, Urdu and Sanskrit are not in the Enterprise OCR table (Urdu and Sanskrit are in the Custom Extractor table) | SOURCED | https://docs.cloud.google.com/document-ai/docs/languages |
| J8 | Google: Enterprise OCR and Layout Parser 15 pages online / 500 pages batch; 40 MB online, 1 GB batch | SOURCED | https://docs.cloud.google.com/document-ai/limits |
| J9 | Google in `asia-south1` (Mumbai): OCR only for processor version **v2.1.1 (Preview)**; GA OCR versions are `us`/`eu` only; **Layout Parser has no asia-south1 location** | SOURCED | https://docs.cloud.google.com/document-ai/docs/regions |
| J10 | Google: "we never use customer data to train our Document AI models"; batch documents deleted after processing with a 1-day failsafe TTL; online requests processed in memory, not persisted | SOURCED | https://docs.cloud.google.com/document-ai/docs/data-usage |
| J11 | Google Enterprise Document OCR: $1.50 (1,000–5,000,000 tier), $0.60 above; Layout Parser $10.00; unit per 1,000 pages per the page's worked examples | SOURCED | https://cloud.google.com/products/document-ai/pricing |
| J12 | On Sarvam's own Indic bench, Google Cloud Vision (a different Google product from Document AI) scores below Sarvam Vision on 21 of 22 languages; no independent Azure-DI-vs-Sarvam comparison was found | SOURCED (vendor table) / UNVERIFIED (independent comparison) | https://www.sarvam.ai/blogs/sarvam-vision |

---

## Evidence quality

- **Capability, limits, API shape, pricing: high.** Primary vendor documentation, consistent
  across model page, guide, API reference, changelog and self-hosted docs. One naming
  inconsistency (Vision vs Vision 1.5) and one docs-vs-site pricing lag, both recorded.
- **Residency and training terms: low-to-medium.** Four first-party legal/marketing
  documents disagree on the default. Only a signed DPA or written answer settles it.
- **Accuracy: low for our purpose.** Vendor-run, self-built Indic benchmark not publicly
  available, older model version, no legal documents, no stamps, no handwriting metric for
  Indic scripts. The olmOCR-Bench English numbers are reproducible in principle (harness
  and data public) but English is not where Sarvam would be chosen. Treat every number as
  a claim to test, not a result.
- **Comparator rows: high** for language tables, limits, regions and data-usage (dated
  official docs). Azure prices come from Microsoft's retail-price API, not a rendered page.
- **Gap in held evidence:** `PLAN_03` §OCR has no URLs; it cannot be used as a sourced
  baseline against which to set Sarvam's numbers.

## Result

| Founder's assumption | What exists today | Verdict |
|---|---|---|
| An Indian model reads scanned / photographed documents | Sarvam Vision via Document AI (Digitise, Extract), managed or self-hosted | **EXISTS** |
| It covers Indian scripts | 23 languages, incl. the eight scripts Azure DI cannot extract | **EXISTS** (accuracy vendor-claimed only) |
| It handles long drag-and-dropped PDFs | 10 pages per job, managed; 500 per document self-hosted | **PARTIAL** — we must split |
| It handles tables | Documented, HTML/Markdown/JSON | **EXISTS** (vendor claim) |
| It handles handwriting | Documented mode; no Indic handwriting metric | **PARTIAL / UNMEASURED** |
| It handles stamps, seals, signatures | Nothing documented | **NOT FOUND** — searched as listed |
| It "analyses photos" (reasons about images) | No Sarvam-model endpoint; only Gemma 4 31B, beta, non-Indic | **NOT FOUND** as a Sarvam model |
| It analyses the document (legal review) | Not what the product does; reading only. Reasoning would be Sarvam-105B over extracted text (11 languages) | **DOES NOT MATCH** the assumption |
| Data stays in India | Managed on Azure Central India per Trust Center; ToS reserves cross-border transfer; self-hosted keeps it in our VPC | **PARTIAL** until contract |
| Not used for training | Documents disagree | **UNRESOLVED** |

Net: Sarvam is a credible **candidate for the document-AI rung of role 13** — the only
one of the three that documents extraction for Bengali, Telugu, Kannada, Malayalam,
Gujarati, Odia and Assamese — and not a candidate for "the model that analyses the
document". It is not proven better than anything on our kind of paper.

## Unresolved issues

1. Training default for a self-serve API workspace (H7 vs H8 vs H9 vs H10).
2. Whether Document AI honours 0-day retention, and under which override (H5).
3. ToS cross-border clause vs Trust Center residency claim (H3), and where Doc AI
   download ZIPs and `upload` pre-signed URLs are physically hosted.
4. Managed Digitise per-block confidence (E10); shape of Extract `sources` (E9).
5. `content_type` and `model` enum values (A7, D5).
6. Stamps, seals, signatures, checkboxes (D2, D3).
7. Mixed-script pages and the single-`language` parameter (C4).
8. Self-hosted: AWS regions incl. `ap-south-1`/`ap-south-2` (F6); version parity with
   managed Vision 1.5 (F7).
9. Accuracy of Vision 1.5 at all; any independent benchmark; availability of Sarvam Indic
   OCR Bench (I6, I8, I9).
10. What the "Vision Real-time" 30 req/min limit serves (B4).
11. Whether status polls count against the 10 req/min Document Intelligence limit (G4).

## Recommended next action

1. **Do not wire Sarvam into anything that sees a client document yet.** The training
   default is unresolved; CLAUDE.md forbids obtaining confidential documents and
   `PLAN_07` assumes zero retention where offered.
2. **Send the eleven unresolved issues to Sarvam in one email** (support@sarvam.ai per the
   docs FAQ), asking specifically for the DPA the Trust Center lists and a written
   answer on training default and Doc AI 0-day retention. Suggest adding them to
   `docs/VENDOR_QUESTIONS.md` (not edited by this task).
3. **Run a bounded bake-off inside R4, public documents only**: take the ₹100 free-credit
   key, set the workspace to shortest retention and opt out of training *before* the
   first upload, and send the same page set — public ICSI specimens and scanned annexures
   from listed-company filings (R5), including stamp-paper pages and at least one
   non-Devanagari page — to Sarvam Digitise, Azure DI Read/Layout (Central India) and
   Google Enterprise OCR. Score character error rate per page against hand transcription
   and record, per page, whether each vendor's output invented text (image descriptions)
   or silently dropped a stamp. This is the measurement `PLAN_01` says role 13's
   threshold is waiting for.
4. Only if (2) comes back clean and (3) shows a per-page win on a script we actually
   receive, request the production key PLAN_11 gates on R3.

---

## What this means for PLAN_12 (document intake architecture)

All rows here are **INFERRED** design consequences of the sourced evidence above.

1. **Sarvam is an adapter in the OCR tier, not a new tier.** Role 13 stays
   "cheap OCR → document-AI → VLM fallback". Sarvam Digitise sits in the document-AI rung
   alongside Azure DI and Google OCR. A script router is justified by J1–J3/J7: pages whose
   detected script is Bengali, Telugu, Kannada, Malayalam, Gujarati, Odia, Assamese or
   Gurmukhi have **no Azure DI extraction path at all**, and several have no Google
   handwriting path. For English and Devanagari pages there is no sourced reason to prefer
   Sarvam.
2. **Per-page split is mandatory, and the 10-page job is its natural batch.** PLAN_11's
   intake (hash → sniff → scan → per-page split, idempotent per page) already fits: submit
   pages in ≤10-page jobs keyed by page hash. `partially_completed` (E6) must map to
   **per-page abstention for the failed pages**, never to a document-level success.
3. **Throughput is capped by the account, not the plan.** 10 req/min on every tier (E11)
   means a queue with backpressure is required for large documents (R5); the managed API
   cannot be the only path for bulk. Self-hosted async (500 pages, scale-to-zero, F2/F8)
   is the bulk and residency-first path, pending F6.
4. **The confidence gate cannot be computed from managed Digitise output as documented.**
   No per-block OCR confidence is documented (E10). Self-hosted returns `ocr_confidence`
   and `layout_confidence` (F3). Either the gate uses self-hosted output, or it computes its
   own signal (e.g. cross-vendor agreement on the page). Vendor confidence, where present,
   is uncalibrated on our paper and must not be the threshold by itself.
5. **Page-anchored spans are feasible.** Digitise JSON gives page, block, bbox, reading
   order (E7, F3). The adapter must map each fact's offset into *our* stored page text and
   keep the bbox, so a refusal can name the page and region. Merged Markdown output must not
   be the stored text of record.
6. **Model-generated text must be separated from document text.** Digitise emits
   AI-written image and chart descriptions (D7). The adapter must drop or quarantine text
   from `image`, `photograph`, `chart/diagram` blocks and label it as model output — never
   let it enter the extraction or quotation path. This is the same boundary as CLAUDE.md's
   "never repair a source" and the image-borne-injection limitation: text Sarvam *reads*
   off a page is untrusted document data; text Sarvam *writes about* a page is not document
   data at all.
7. **Extract is a proposer, not a decider.** Its schema-driven fields with `confidence` and
   `sources` (E8) are proposals under "models propose; gates decide" and pass through span
   verification exactly like the Anthropic/Gemini extractor. It never decides applicability.
8. **Stamps, seals and signatures need our own handling.** Nothing documented at Sarvam
   (D3), and nothing found on the Azure/Google pages read. PLAN_12 should specify region
   detection → abstain/flag (`UNVERIFIED` for stamp-dependent facts such as stamp duty
   paid or execution), not a vendor call that silently omits the region.
9. **Intake must normalise formats and declare a language.** TIFF is rejected self-hosted
   (E3) and absent from the managed list (E4); convert to PNG/PDF at intake. The single
   `language` per job (C2) means a per-page script/language-ID step precedes the Sarvam call;
   mixed-script pages are an open risk (C4) and should route to two vendors, not one.
10. **Residency table rows for Sarvam.** Managed: Azure Central India per Trust Center
    (H1), with ToS cross-border reservation (H2) → row marked PARTIAL until DPA. Self-hosted:
    our AWS account; `ap-south-1`/`ap-south-2` availability UNVERIFIED (F6). Google OCR in
    Mumbai is Preview-only and Layout Parser is not offered there (J9) — record that as a
    constraint of Google, not of our account.
11. **Tenancy and retention.** Until H5/H7 resolve, the Sarvam adapter is disabled for any
    tenant document and enabled only for public-document evaluation; the adapter config must
    carry the workspace retention setting and training opt-out status as checked
    preconditions, not as documentation.
12. **Cost per 100-page document (ranges, sourced inputs):** Sarvam Digitise ≈ ₹50, Extract
    ≈ ₹100 (G1); Azure Read ≈ $0.15 and Layout ≈ $1.00 at list (J5); Google Enterprise OCR
    ≈ $0.15, Layout Parser ≈ $1.00 (J11). Self-hosted Sarvam: $10/hr software fee plus
    instance, amortised by volume (F5). Price is not the deciding variable at these levels;
    per-page accuracy on our paper and the training/residency terms are.
