# R4 — Hyperscaler Document AI / OCR for Indian corporate and legal documents

Research date: **2026-09-14**. Track R, task R4.
Providers: **Azure AI Document Intelligence**, **Google Cloud Document AI**, **AWS Textract**,
**Oracle OCI Document Understanding**. Sarvam is covered in
[`SARVAM_DOCUMENT_AI.md`](SARVAM_DOCUMENT_AI.md) and is only cross-referenced here (as `R3:<row>`).

Markers: **SOURCED** = stated on the URL given, opened on 2026-09-14. **INFERRED** = my reasoning
from sourced facts, stated as such. **UNVERIFIED** = asked and not answered by any page I could
open. No login walls were crossed. Two oracle.com marketing pages returned HTTP 403 to the fetcher
and were not retried by any other means. Their content is not used.

**Method note.** A summarising fetch of Google's language page reported handwriting "No" for every
Indic language. The raw HTML (`aria-label="Supported"` / `"Not Supported"`) says otherwise, so
every Google language/region row below comes from parsing the raw page, not from the summary.

---

## Question

For Indian corporate and legal paper, what does each of the four hyperscaler document-AI services
document **today** on each of these?

- Indic scripts (Devanagari at minimum)
- tables and key-value pairs
- handwriting
- stamps and seals
- per-call page and size limits
- async/batch APIs
- India-region availability
- price per 1,000 pages
- retention and zero-retention
- containers / on-prem

Is there any independent benchmark on real scanned Indian documents?

Also re-verify two claims in `docs/PLAN_03_DATA_SOURCES.md` §OCR: "Textract does not support
Devanagari" and the "76-point real-scan spread".

## Short answer

1. **Textract still has no Devanagari. CONFIRMED.** It documents English, French, German, Italian,
   Portuguese and Spanish only. Handwriting is English only, and its published character set has
   no Indic glyphs. It is also **not in Hyderabad (`ap-south-2`)**. OCI Document Understanding
   lists **no Indic language** in any model version.
2. **Only Azure and Google are live options for Indic text, and they cover different scripts.**
   - **Azure**: printed Hindi, Marathi, Nepali, Sanskrit, many minor Devanagari languages, Tamil,
     Urdu. **No Indic handwriting.**
   - **Google Enterprise OCR**: printed Hindi, Marathi, Nepali, Bengali, Gujarati, Kannada,
     Malayalam, Punjabi (Gurmukhi), Tamil, Telugu. **Handwriting for Hindi, Marathi, Nepali,
     Bengali.**
3. **The 76-point spread is real but narrower than PLAN_03 implies. QUALIFIED.** The figures match
   arXiv 2606.29213, but its "real scans" are:
   - 300 **word/short-phrase crops** from a **Sanskrit typeset historical** corpus, not document
     pages;
   - a single-author v1 preprint;
   - a test of **none** of the four providers here.
4. **PLAN_03's Azure on-prem line needs correcting. CHANGED.** Connected v4.0 Read and Layout
   containers exist. **Disconnected** (truly offline) containers need Microsoft approval, are
   limited to "strategic customer or partner" organisations, and take a calendar-year commitment
   charged upfront.
5. **"Azure is the best of the big three for Devanagari" is UNVERIFIED.** No benchmark comparing
   the providers on Indic text was found. On *documented coverage*, Google is broader for major
   scripts and handwriting, and Azure is broader for minor Devanagari languages, Sanskrit and Urdu.
6. **Stamps and seals:** no provider documents stamp or seal detection. Textract documents
   *signature* detection. Azure Layout documents *figures*.
7. **In-India processing:**
   - Google Enterprise OCR in Mumbai is **Preview-only**, and Layout Parser is not offered there.
   - Azure has retail prices only in **Central India** (none in South or West India).
   - Textract is in Mumbai only.
8. **Retention.** Google's online OCR comes closest to zero retention (processed in memory, not
   persisted). Azure keeps inputs and results for 24 h unless deleted by API call. Textract **may
   store and use inputs, including in another region, unless the account is opted out**.

---

## Sources checked

**AWS Textract**
- https://docs.aws.amazon.com/textract/latest/dg/limits-document.html (languages, characters, handwriting, file/page limits)
- https://docs.aws.amazon.com/general/latest/gr/textract.html (endpoints by region, TPS quotas)
- https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonTextract/current/region_index.json and `.../ap-south-1/index.json` (AWS public Price List API; publicationDate 2026-09-11)
- https://aws.amazon.com/textract/pricing/ (US West (Oregon) examples)
- https://aws.amazon.com/textract/faqs/ (data use, features, languages)
- https://docs.aws.amazon.com/textract/latest/dg/API_GetDocumentAnalysis.html (async JobId validity)
- https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_ai-opt-out.html
- Attempted: https://docs.aws.amazon.com/textract/latest/dg/how-it-works-signatures.html (the fetch returned no body, so nothing is cited from it)

**Azure AI Document Intelligence** (Microsoft Learn; ms.date noted)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 (ms.date 2026-04-18, updated 2026-07-10)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0 (ms.date 2026-05-01)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0 (ms.date 2026-09-08)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/batch-analysis?view=doc-intel-4.0.0 (ms.date 2026-05-18)
- https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/containers/install-run?view=doc-intel-4.0.0 (ms.date 2026-08-15)
- https://learn.microsoft.com/en-us/azure/ai-services/containers/disconnected-containers (ms.date 2025-10-02, updated 2026-06-11)
- https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security (ms.date 2026-07-22)
- https://prices.azure.com/api/retail/prices with `$filter=armRegionName eq '<region>' and contains(productName,'Document Intelligence')` for `centralindia`, `southindia`, `westindia` (Microsoft public retail-price API)

**Google Cloud Document AI** (all "Last updated 2026-09-03 UTC" unless noted)
- https://docs.cloud.google.com/document-ai/docs/languages (raw HTML parsed)
- https://docs.cloud.google.com/document-ai/limits
- https://docs.cloud.google.com/document-ai/docs/regions (raw HTML parsed)
- https://docs.cloud.google.com/document-ai/docs/data-usage
- https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr
- https://cloud.google.com/document-ai/pricing (raw HTML parsed)
- https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/vertex-ai-ocr-supported-langs (GDC air-gapped OCR; a different product)

**Oracle OCI Document Understanding**
- https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/overview.htm
- https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/getting_started.htm (supported languages, regions)
- https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/limits.htm
- https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/pretrained_doc_ocr.htm
- https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/pretrained-doc-using.htm
- https://docs.oracle.com/en-us/iaas/releasenotes/document-understanding/version-2.htm
- https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD (Oracle public price-list API)
- Blocked (HTTP 403, not used): https://www.oracle.com/artificial-intelligence/document-understanding/ · …/features/ · https://www.oracle.com/artificial-intelligence/pricing/ · https://www.oracle.com/cloud/distributed-cloud/service-availability/

**Benchmarks / papers**
- https://arxiv.org/abs/2606.29213 and https://arxiv.org/html/2606.29213 (Devanagari OCR stress test)
- https://arxiv.org/abs/2512.18004 and https://arxiv.org/html/2512.18004v1 (handwritten Marathi legal documents)
- https://arxiv.org/abs/2604.12978 (GlotOCR Bench)

**Held evidence read first:** `docs/PLAN_03_DATA_SOURCES.md` §"OCR — the gate on bulk document
review" (carries no URLs) and `docs/research/SARVAM_DOCUMENT_AI.md` (its §J comparator rows were
re-opened, not copied).

**Searches with no qualifying result.** These are negative results, stated as searched, not as
"does not exist":
- *Independent benchmark of Azure DI / Google Document AI / Textract / OCI on real scanned Indic
  documents.* One web search (query: evaluation Azure Document Intelligence Google Document AI
  Textract Hindi scanned documents OCR comparison arXiv 2025 2026 Indian). It returned only vendor
  or SEO comparison blogs, not opened and not permitted-quality evidence, and no arXiv paper on
  this. A "DeltOCR Bench" appeared only in a search snippet and was not opened. Nothing is cited
  from it.
- *`stamp` / `seal`* in the Azure Layout page (text grep of the full page): 0 hits. `signature`:
  0 hits.
- *Stamp/seal/signature* on Google's Enterprise OCR page: none for the OCR processor.
- *Stamp/seal* in Textract's limits page and FAQ: not mentioned.
- *Indic language* in OCI's supported-languages table: none.
- *On-prem/container* for Textract (FAQ) and for Google Document AI and OCI Document
  Understanding (pages above): none found. Not searched exhaustively beyond those pages.
- *OCI data retention / training use* in docs.oracle.com Document Understanding pages: no
  statement found. The only such claim surfaced in a search snippet attributed to a 403-blocked
  oracle.com page.

---

## Evidence found

### A. Indic script support (printed)

| id | claim | marker | URL |
|---|---|---|---|
| A1 | Textract: "supports English, French, German, Italian, Portuguese, and Spanish text detection" | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/limits-document.html |
| A2 | Textract "Characters" list: a–z, A–Z, 0–9, Latin diacritics, punctuation and symbols including ₹. No Devanagari or other Indic glyphs listed | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/limits-document.html |
| A3 | Textract FAQ repeats the six languages. Invoices/receipts, identity documents and Queries are "in English" | SOURCED | https://aws.amazon.com/textract/faqs/ |
| A4 | **PLAN_03 "Textract does not support Devanagari at all": CONFIRMED** on current pages (A1–A3) | INFERRED from A1–A3 | — |
| A5 | Azure DI v4.0 Read and Layout, **printed**, includes: Hindi `hi`, Marathi `mr`, Nepali `ne`, Sanskrit (Devanagari) `sa`, Bodo (Devanagari), Dogri (Devanagari), Santali (Devanagari), Tamil `ta`, Urdu `ur`, Punjabi **(Arabic)** `pa`, and many minor Devanagari languages (Awadhi-Hindi, Bhojpuri-Hindi, Chhattisgarhi, Haryanvi, Kangri, Kurukh, Sadri, etc.) | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 |
| A6 | Azure: Bengali, Gujarati, Kannada, Malayalam, Telugu, Odia, Assamese, Sindhi appear **only in the language-detection list**, which "can include languages not currently supported for text extraction" | SOURCED | same |
| A7 | Azure: "Document Intelligence's deep learning based universal models extract all multi-lingual text … including text lines with mixed languages, and don't require specifying a language code"; forcing a code "may return incomplete and incorrect text" | SOURCED | same |
| A8 | Google **Enterprise Document OCR** language table: Bengali (Beng), Gujarati (Gujr), Hindi (Deva), Kannada (Knda), Malayalam (Mlym), Marathi (Deva), Nepali (Deva), Punjabi (Guru), Tamil (Taml), Telugu (Telu). Odia, Assamese, Urdu, Sanskrit **not** in the OCR table | SOURCED (raw HTML) | https://docs.cloud.google.com/document-ai/docs/languages |
| A9 | Google **Layout Parser**: the same 10 scripts as A8. **Form Parser**: Hindi, Marathi, Nepali only. **Custom Extractor** table: Hindi, Marathi, Nepali, Sanskrit, Urdu | SOURCED (raw HTML) | same |
| A10 | OCI supported languages. Version 1: OCR, tables, classification and KV all **EN**. Version 2: OCR and invoice/receipt KV in AR, ZH, FR, DE, HE, JA, PT, RU, ES, NL, UK. No Indic language in either | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/getting_started.htm |
| A11 | OCI's OCR model page says "OCR is limited to English", which is inconsistent with the v2 table (A10) | SOURCED (the inconsistency) | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/pretrained_doc_ocr.htm |
| A12 | OCI Custom Key-Value extraction "Supports 200+ more languages by design", evaluated only for EN/ES/PG (Classic) and EN/ES/FR/GR/DU (Generative). No Indic evaluation stated | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/getting_started.htm |
| A13 | Therefore **only Azure and Google document Indic extraction**, with complementary gaps. Pages in Bengali, Gujarati, Kannada, Malayalam, Telugu or Gurmukhi have no Azure path. Pages in Sanskrit, Urdu and minor Devanagari languages have no Google OCR path. Odia and Assamese have neither (Sarvam covers both: R3:C1) | INFERRED from A5–A10 | — |

### B. Handwriting

| id | claim | marker | URL |
|---|---|---|---|
| B1 | Textract: "Handwritten character recognition is only supported in English" | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/limits-document.html |
| B2 | Azure DI v4.0 Read and Layout **handwritten**: English, Chinese Simplified, French, German, Italian, Japanese, Korean, Portuguese, Spanish, Russian, Thai, Arabic. **No Indic language** | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 |
| B3 | Google Enterprise OCR "Handwriting supported": **Supported** for Bengali, Hindi, Marathi, Nepali. **Not Supported** for Gujarati, Kannada, Malayalam, Punjabi, Tamil, Telugu. Layout Parser identical. Form Parser Supported for Hindi, Marathi, Nepali | SOURCED (raw HTML `aria-label`) | https://docs.cloud.google.com/document-ai/docs/languages |
| B4 | Google OCR supports "Language and handwriting hints"; the font-style add-on reports word-level handwriting | SOURCED | https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr |
| B5 | OCI limits page: "Both handwritten and printed characters supported". Language scope not stated; given A10, English at most | SOURCED (statement) / INFERRED (scope) | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/limits.htm |
| B6 | No handwriting *accuracy* figure for any Indic language was found from any of the four | UNVERIFIED | — |

### C. Tables, key-value, stamps/seals/signatures

| id | claim | marker | URL |
|---|---|---|---|
| C1 | Textract AnalyzeDocument returns KEY_VALUE_SET blocks (forms), TABLE/CELL blocks, selection elements, Query / Query-Result blocks with confidence | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/API_GetDocumentAnalysis.html |
| C2 | Textract features include signatures and layout; Signatures and Layout are separately priced (see F1) | SOURCED | https://aws.amazon.com/textract/faqs/ · https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonTextract/current/ap-south-1/index.json |
| C3 | Azure Layout extracts "text, tables, selection marks, and document structure"; geometric roles include "figures". Markdown output renders tables as HTML (merged cells, multirow headers). Key-value pairs via `prebuilt-layout` with `features=keyValuePairs` | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0 · https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/language-support/ocr?view=doc-intel-4.0.0 |
| C4 | Azure Layout page: 0 occurrences of "stamp", "seal" or "signature" | SOURCED (grep of fetched page) | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0 |
| C5 | Google Enterprise OCR does **not** extract tables or key-values; those are Form Parser (KV, tables), Layout Parser (structure, tables, chunking) and Custom Extractor. OCR add-ons: Math OCR, checkbox detection, font style | SOURCED | https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr |
| C6 | The same Google page mentions "Derived field and signature detection" under Custom Extractor. Whether that covers stamps or seals is not stated | SOURCED (phrase, as reported by the page fetch) / UNVERIFIED (stamps) | https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr |
| C7 | OCI: KV extraction is for a "predefined list" of document types (receipts, invoices, passports, driver IDs); table extraction "maintaining the row and column relationships"; document classification; searchable-PDF output | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/overview.htm |
| C8 | **Stamps and seals: no provider documents detection or extraction.** Textract documents *signatures*; Azure *figures* might enclose a stamp region, but that is untested | SOURCED (C2, C4–C6) / INFERRED (figure-as-stamp) / UNVERIFIED (behaviour on stamp paper) | — |

### D. Limits per call; async and batch

| id | claim | marker | URL |
|---|---|---|---|
| D1 | Textract sync: 10 MB, **1 page** for PDF/TIFF. Async: PDF/TIFF 500 MB and **3,000 pages**; JPEG/PNG 10 MB. JPEG, PNG, PDF, TIFF; no XFA or password-protected PDFs. Minimum text height 15 px (~8 pt at 150 DPI) | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/limits-document.html |
| D2 | Textract async `JobId` "is only valid for 7 days"; results paginated at ≤1,000 blocks; job states include `PARTIAL_SUCCESS` | SOURCED | https://docs.aws.amazon.com/textract/latest/dg/API_GetDocumentAnalysis.html |
| D3 | Textract quotas in **Mumbai**: AnalyzeDocument 5 TPS, DetectDocumentText 5 TPS, StartDocumentAnalysis 5 TPS, 100 simultaneous async jobs (vs 10/25/10/600 in us-east-1) | SOURCED | https://docs.aws.amazon.com/general/latest/gr/textract.html |
| D4 | Azure DI S0: max document **500 MB**, **2,000 pages** per analysis (not adjustable); F0 4 MB / 2 pages. Analyze 15 TPS and Get 50 TPS by default (adjustable). v4.0 accepts PDF, JPEG, PNG, BMP, TIFF, HEIF; DOCX/PPTX/XLS for Read and Layout | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0 |
| D5 | Azure analyze is async by design: inputs and results held until fetched (see G3). **Batch API**: up to **10,000 documents per request**, input and output in the customer's Azure Blob Storage; batch status retained 24 h; results written as `.ocr.json` | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/batch-analysis?view=doc-intel-4.0.0 · https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security |
| D6 | Google: online **15 pages** (30 with `imageless_mode`), 40 MB. Batch **500 pages** (OCR, Layout) or 100 (Form Parser), 1 GB per file, 5,000 files per batch. Custom Extractor 15 online / 200 batch | SOURCED | https://docs.cloud.google.com/document-ai/limits |
| D7 | OCI: sync and async-inline 8 MB and ≤5 pages. Async from Object Storage: 500 MB, **2,000 pages per document**, ≤2,000 documents per job. JPEG, PNG, PDF, TIFF. Minimum text height 15 px | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/limits.htm |
| D8 | OCI sync = `AnalyzeDocument`; async = `CreateProcessorJob` | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/pretrained-doc-using.htm |

### E. India region availability

| id | claim | marker | URL |
|---|---|---|---|
| E1 | Textract has an endpoint in **Asia Pacific (Mumbai) `ap-south-1`**. **`ap-south-2` (Hyderabad) is not in the endpoint table** | SOURCED | https://docs.aws.amazon.com/general/latest/gr/textract.html |
| E2 | The AWS Price List region index for AmazonTextract (publication 2026-09-11) contains `ap-south-1` and no `ap-south-2` | SOURCED | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonTextract/current/region_index.json |
| E3 | Azure retail-price API returns 76 Document Intelligence meters for **`centralindia`**, including disconnected-container tiers; **0** for `southindia` and **0** for `westindia` | SOURCED | https://prices.azure.com/api/retail/prices (filters as in Sources) |
| E4 | Azure DI is therefore offered in Central India; South India availability is not evidenced by pricing. A product-by-region page was not checked | INFERRED from E3 / UNVERIFIED (South India) | — |
| E5 | Azure: "incoming data is processed in the same region where the Document Intelligence resource was created" | SOURCED | https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security |
| E6 | Google: `asia-south1` (Mumbai) is a single-region location with "limited support". **OCR: only `v2.1.1 (Preview)` is marked Supported** (v1.2, v2.0, v2.1 not). Form Parser v1.0/v2.0/v2.1 Supported. Custom Extractor (custom- and template-based) listed. Custom Extractor with GenAI v1.5 marked † Preview. **Layout Parser has no asia-south1 row** | SOURCED (raw HTML) | https://docs.cloud.google.com/document-ai/docs/regions |
| E7 | Google `asia-south2` (Delhi) is not listed for Document AI | SOURCED (absence on page) | https://docs.cloud.google.com/document-ai/docs/regions |
| E8 | OCI: "Except for the subset of regions that you can manage custom generative models in, Document Understanding is hosted in … Commercial Regions (OC1)"; custom generative models only in São Paulo, Osaka, London, Chicago | SOURCED | https://docs.oracle.com/en-us/iaas/Content/document-understanding/using/getting_started.htm |
| E9 | OCI Mumbai (`ap-mumbai-1`) and Hyderabad (`ap-hyderabad-1`) are OC1 commercial regions, so Document Understanding is likely hosted there. OCI's regions page was surfaced by search but not opened; the service-availability page returned 403 | INFERRED / UNVERIFIED | — |

### F. Price per 1,000 pages (USD list, pay-as-you-go)

| id | claim | marker | URL |
|---|---|---|---|
| F1 | Textract **Mumbai**, 0–1M pages / above 1M:<br>• DetectDocumentText (sync and async) **$1.50 / $0.60**<br>• Tables $15 / $10<br>• Forms $50 / $40<br>• Queries $15 / $10<br>• Layout $4 / $3<br>• Signatures $3.50 / $1.40<br>• Forms+Tables+Queries $70 / $55 | SOURCED | https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonTextract/current/ap-south-1/index.json |
| F2 | The Textract pricing page's Oregon examples show the same DetectDocumentText, Tables, Forms, Queries and Signatures rates | SOURCED | https://aws.amazon.com/textract/pricing/ |
| F3 | Azure **Central India**:<br>• S0 Read **$1.50**, $0.60 above the 1,000-unit (1M-page) tier<br>• S0 Batch Read same<br>• S0 Pre-built Pages $10<br>• S0 Batch Layout Pages $10<br>• S0 Add-on Pages $6<br>• S0 pages for query fields $10<br>• S0 Custom Pages $30 | SOURCED | https://prices.azure.com/api/retail/prices (centralindia) |
| F4 | Azure disconnected-container tiers in Central India are priced per year: Pre-Built Disconnected 100K $8,640/yr; Read Disconnected 2000K $12,960/yr (the smallest Read tier listed); Custom Disconnected 100K $24,480/yr | SOURCED | same |
| F5 | The disconnected tier quantities are **per month, billed annually**: Pre-Built Connected 100K is $720/month and ×12 = $8,640; Read Connected 2000K is $1,080/month and ×12 = $12,960 | INFERRED (arithmetic on F3/F4 rows) | — |
| F6 | Google:<br>• Enterprise Document OCR: 0–1,000 **$0.00 (Free)**, 1,000–5,000,000 **$1.50**, 5M+ **$0.60**<br>• OCR add-ons $6.00<br>• Form Parser $30 (0–1M) / $20<br>• Layout Parser $10.00<br>Other columns are 1-year and 3-year savings-plan prices (e.g. OCR $1.35 / $1.20) | SOURCED (raw HTML) | https://cloud.google.com/document-ai/pricing |
| F7 | Whether Google's "count" is pages and its free tier is monthly is not stated in the text parsed. R3:J11 read the page's worked examples as per 1,000 pages | UNVERIFIED (free-tier period) | https://cloud.google.com/document-ai/pricing |
| F8 | OCI, per **1,000 transactions**, first 5 (thousand) free:<br>• OCR **$1.00**<br>• Document Properties $0.25<br>• Document Extraction $10.00<br>• Custom Document Extraction $30.00<br>• Custom Document Properties $1.50 | SOURCED | https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD |
| F9 | Whether an OCI "transaction" is a page | UNVERIFIED | — |
| F10 | Plain OCR costs about $1–1.50 per 1,000 pages on all four. Structure extraction costs about $10–70 per 1,000. Cost is not the differentiator for Indic text: Textract and OCI cannot read it at any price | INFERRED from F1–F8, A4, A10 | — |

### G. Data retention, training use, zero retention

| id | claim | marker | URL |
|---|---|---|---|
| G1 | Textract "may store and use document and image inputs … to improve and develop the quality of Amazon Textract and other Amazon machine-learning/artificial-intelligence technologies". Unless opted out, "some portion of content … may be stored in another AWS region" | SOURCED | https://aws.amazon.com/textract/faqs/ |
| G2 | Opt-out is by AWS Organizations AI services opt-out policy. Opting out deletes historical content stored for service improvement, but "any content that is used to provide the service to you is not deleted" | SOURCED | https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_ai-opt-out.html |
| G3 | Azure DI "stores submitted input data and analyze results for 24 hours after an analysis operation completes" and then deletes them automatically. `Delete Analyze Result` deletes earlier. Temporary storage is in the same region, shared across customers, logically isolated | SOURCED | https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/document-intelligence/data-privacy-security |
| G4 | That Azure page does not state whether inputs are used for training (re-checked; matches R3:J6) | SOURCED (absence on page) / UNVERIFIED (Microsoft's position) | same |
| G5 | Google: "Google does not use any of your content (such as documents and predictions) for any purpose except to provide you with the Document AI service". Online requests are "processed in memory … not persisted to disk". Batch documents are "typically deleted immediately after the processing, with a failsafe Time to live (TTL) of one day" | SOURCED | https://docs.cloud.google.com/document-ai/docs/data-usage |
| G6 | OCI Document Understanding: no retention or training statement found on the docs.oracle.com pages read | UNVERIFIED | — |
| G7 | Zero retention in effect:<br>• **Google online**: documented, no persistence.<br>• **Azure**: achievable by calling Delete immediately after reading results. Not zero by default: up to 24 h if the call fails.<br>• **Textract**: opt-out stops improvement use, but the service's own operational storage is undocumented beyond the 7-day `JobId` | INFERRED from G1–G5, D2 | — |

### H. Containers / on-prem

| id | claim | marker | URL |
|---|---|---|---|
| H1 | Azure: "`v4.0 2024-11-30 (GA)` for Read and Layout" containers (images `form-recognizer/read-4.0`, `layout-4.0`). Docker "must be configured to allow the containers to connect with and send billing data to Azure". "Container pricing is the same as cloud service pricing" | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/containers/install-run?view=doc-intel-4.0.0 · https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?view=doc-intel-4.0.0 |
| H2 | Azure **disconnected** containers need a request form, with a decision "within 10 business days". "Your organization should be identified as strategic customer or partner with Microsoft". Use case must be zero-connectivity, occasional connectivity, or "strict regulation of not sending any kind of data back to cloud". Commitment is "a calendar year … charged the full price immediately" | SOURCED | https://learn.microsoft.com/en-us/azure/ai-services/containers/disconnected-containers |
| H3 | **PLAN_03 "genuine on-prem path, gated at 100k pages/month on a 1-year commitment": PARTIALLY CORRECT, MATERIALLY INCOMPLETE.**<br>• The 100K-per-month (billed annually) tier exists for Pre-Built (F4/F5), but Read's smallest disconnected tier is 2M/month.<br>• The binding gate is **eligibility** (strategic customer or partner, Microsoft approval), not volume.<br>• Connected containers run locally without that gate but phone home for billing (H1) | INFERRED from H1, H2, F4, F5 | — |
| H4 | Google Document AI: no container or on-prem option found on the pages read. Separately, **Google Distributed Cloud air-gapped** offers an OCR feature (Vertex AI OCR, a different product) listing Hindi, Marathi, Malayalam, Nepali as supported | SOURCED (GDC list) / UNVERIFIED (Document AI on-prem) | https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/application/ao-user/vertex-ai-ocr-supported-langs |
| H5 | Textract: no on-prem or container option mentioned in the FAQ | SOURCED (absence on FAQ) / UNVERIFIED (none exists) | https://aws.amazon.com/textract/faqs/ |
| H6 | OCI Document Understanding: no on-prem option found on the pages read | UNVERIFIED | — |

### I. Independent benchmarks on real scanned Indic / Indian documents

| id | claim | marker | URL |
|---|---|---|---|
| I1 | arXiv **2606.29213**, "Can OCR-VLMs Read Devanagari? A Stress-Test Benchmark and Post-Correction Study", Aditya Pratap Singh, v1, submitted 28 Jun 2026. Ten systems (EasyOCR; Qwen2.5-VL-3B, Qwen3-VL-8B, olmOCR-7B; DeepSeek-OCR, Unlimited-OCR; Gemini 2.5 Flash, Claude Opus 4.7, GPT-5.5, Mistral OCR) across four synthetic degradations and 300 real printed scans | SOURCED | https://arxiv.org/abs/2606.29213 |
| I2 | Abstract: on real scans "nine of the ten systems collapse (EasyOCR falls from chrF++ 93.6 to 58.3) and the field spreads across a 76-point range"; "Gemini and Claude lead at 86.3 and 82.2"; olmOCR-7B "falls to 40.5"; GPT-5.5 58.5; Qwen3-VL-8B 75.2 | SOURCED | https://arxiv.org/abs/2606.29213 |
| I3 | **PLAN_03 figures: CONFIRMED** (86.3 / 82.2 / 58.3 from 93.6 / 40.5 / 76-point) | INFERRED from I2 | — |
| I4 | **But the real set is not Indian documents.** The 300 scans come from "the Sanskrit-OCR-Typed corpus (historical typeset scans)" and are "word and short-phrase level, which disadvantages page-oriented models". The authors call it "Sanskrit typeset rather than sentence-level Hindi". chrF++ is corpus-level | SOURCED (as reported from the HTML full text) | https://arxiv.org/html/2606.29213 |
| I5 | The paper evaluates **none** of Azure DI, Google Document AI/Cloud Vision, Textract, OCI | SOURCED (system list in abstract, I1) | https://arxiv.org/abs/2606.29213 |
| I6 | PLAN_03's framing "the only rigorous independent benchmark on real Devanagari scans" overstates it. It is a single-author v1 preprint with no peer-review venue shown, on phrase crops of Sanskrit type. "Only" is not verifiable from one search | INFERRED from I1, I4; UNVERIFIED ("only") | — |
| I7 | arXiv **2512.18004**, "Seeing Justice Clearly: Handwritten Legal Document Translation with OCR and Vision-Language Models", Nigam, Shukla, Shallum, Bhattacharya; submitted 19 Dec 2025; AILaw @ AAAI 2026. Records "such as FIRs, charge sheets, and witness statements" | SOURCED | https://arxiv.org/abs/2512.18004 |
| I8 | Dataset: "approximately 60 scanned PDF documents" in Marathi from authentic legal sources, with "official stamps, seals, signatures, and structured tables". OCR tools: Tesseract, EasyOCR, PaddleOCR (EasyOCR best "but still struggled"). VLMs: Chitrarth, Maya-8B, Ovis2-34B. Human evaluators: "these models currently lack the precision required for legal-grade document translation"; VLMs "tend to hallucinate plausible-sounding text" | SOURCED | https://arxiv.org/html/2512.18004v1 |
| I9 | **PLAN_03 Marathi-study claim: CONFIRMED with scope correction.**<br>• The conclusion is about **translation**, not OCR alone.<br>• The documents are criminal-court records, not corporate documents.<br>• No commercial cloud OCR was tested.<br>• No numeric CER/WER appeared in the main text as read | INFERRED from I7, I8 | — |
| I10 | arXiv **2604.12978** (GlotOCR Bench) uses images "rendered using fonts from the Google Fonts repository"; synthetic, not real scans. Named cloud Document AI services were not identified in the abstract | SOURCED | https://arxiv.org/abs/2604.12978 |
| I11 | PLAN_03 "No published OCR benchmark exists for genuinely scanned Indian legal paper" is **nearly right**. I8 is a study on scanned Indian legal paper, but whether its dataset is released was not checked, and it reports no OCR numbers in the text read | INFERRED / UNVERIFIED (dataset release) | — |
| I12 | No independent benchmark comparing Azure DI, Google Document AI, Textract and OCI on real scanned Indic or Indian corporate documents was found (see negative searches). The only cross-vendor Indic numbers found are Sarvam's own vendor-run table, which includes Google **Cloud Vision** (R3:I2, R3:J12) | UNVERIFIED (absence) | — |
| I13 | **PLAN_03 "Azure DI is the best of the big three for Devanagari": UNVERIFIED.** No comparative accuracy evidence found. On documented coverage, Google is broader for major scripts and Indic handwriting (A8, B3); Azure is broader for Sanskrit, Urdu and minor Devanagari languages (A5) | INFERRED from A5, A8, B2, B3, I12 | — |

---

## Evidence quality

- **Language, handwriting, limits, retention (Azure, Google, Textract): high.** These are dated
  primary docs; Google tables were parsed from raw HTML. One tool-summary error on Google
  handwriting was caught and corrected (see Method note), so any earlier Google handwriting row
  not taken from raw HTML should be distrusted.
- **Prices: high for list rates.** Rates come from the public price APIs of AWS, Microsoft and
  Oracle, and Google's page HTML. Unit semantics are UNVERIFIED for Google's free tier and OCI's
  "transaction", and the disconnected-tier period is an INFERRED reading.
- **Region availability: medium.** AWS is high (endpoint table plus price list). Azure is inferred
  from price rows, not a product-by-region page. Google is high (raw table). OCI is inferred; the
  availability page was blocked.
- **OCI overall: medium-low.** Its own pages contradict each other on OCR language (A10 vs A11).
  No retention statement was found, and marketing pages were blocked.
- **Benchmarks: low for our purpose.** Neither paper tests any of the four providers, uses Indian
  *corporate* paper, or measures stamp-paper pages. The Devanagari study is word-level Sanskrit
  type. The Marathi study is handwritten criminal records measured as translation. Nothing here
  tells us Azure vs Google accuracy on a board resolution or a share-transfer deed.

## Result

| Dimension | Azure DI (v4.0) | Google Document AI | AWS Textract | OCI Doc Understanding |
|---|---|---|---|---|
| Devanagari printed | **Yes**: Hindi, Marathi, Nepali, Sanskrit, many minor | **Yes**: Hindi, Marathi, Nepali | **No** | **No** |
| Other Indic printed | Tamil, Urdu, Punjabi (Arabic) | Bengali, Gujarati, Kannada, Malayalam, Punjabi (Gurmukhi), Tamil, Telugu | No | No |
| Indic handwriting | **None** | Hindi, Marathi, Nepali, Bengali | No (English only) | No |
| Tables / key-value | Layout + `keyValuePairs` | Form Parser (Hindi/Marathi/Nepali), Layout Parser (10 scripts) | Yes (English-trained; Indic unreadable) | Yes, English-only models |
| Stamps / seals | Not documented | Not documented | Not documented (signatures yes) | Not documented |
| Pages per call | 2,000 / 500 MB | 15 online (30 imageless) / 500 batch | 1 sync / 3,000 async | 5 sync / 2,000 async |
| Batch | 10,000 docs per request via Blob | 5,000 files per batch | Async jobs, 100 concurrent in Mumbai | ≤2,000 docs per job |
| India region | Central India | asia-south1: **OCR Preview-only**, no Layout Parser; not asia-south2 | ap-south-1 only; **not ap-south-2** | OC1 commercial (India inferred) |
| OCR $/1,000 pages | $1.50 → $0.60 | $1.50 → $0.60 (first 1,000 free) | $1.50 → $0.60 | $1.00 per 1,000 transactions |
| Retention | 24 h, deletable | Online: in-memory; batch ≤1 day | May store and train unless org opt-out; may leave region | Not documented |
| On-prem | Connected Read/Layout v4.0; disconnected by approval, strategic customers only | Not found (GDC air-gapped OCR is a different product) | Not found | Not found |

PLAN_03 re-verification:

| PLAN_03 claim | Status on 2026-09-14 |
|---|---|
| Textract does not support Devanagari; Mumbai doesn't help | **CONFIRMED** (A1–A4). Add: not in Hyderabad (E1, E2) |
| 76-point spread: Gemini 2.5 Flash 86.3, Claude Opus 4.7 82.2, EasyOCR 58.3 (from 93.6), olmOCR 40.5 | **CONFIRMED numbers, QUALIFIED meaning**: Sanskrit typeset phrase crops, single-author preprint, no cloud Document AI tested (I1–I6) |
| ~60 real scanned Marathi legal docs; lack precision for legal-grade work | **CONFIRMED, scope-corrected**: translation not OCR; criminal records; open-source OCR only (I7–I9) |
| Azure is best of the big three for Devanagari | **UNVERIFIED**; coverage evidence partly cuts the other way (I13) |
| Azure on-prem gated at 100k pages/month, 1-year commitment | **CHANGED / INCOMPLETE**: gate is strategic-customer approval; Read tiers start at 2M/month (H1–H3) |
| No published OCR benchmark for scanned Indian legal paper | **Mostly holds**, with I8 as a near-miss (I11) |

## Unresolved issues

1. Accuracy of Azure DI vs Google Enterprise OCR (vs Sarvam, R3) on real Indian corporate paper:
   English, Hindi, mixed-script, stamp paper. No evidence exists (I12).
2. Stamp and seal behaviour for every provider (C8): dropped, OCR'd as noise, or captured as a
   figure or signature?
3. Google OCR in `asia-south1` is Preview only (E6). Preview terms, SLA and whether Indic
   handwriting works on `v2.1.1` in Mumbai were not checked.
4. Azure DI in South India (E4). Microsoft's position on training use of DI inputs (G4).
5. Textract operational retention beyond the 7-day `JobId`, after opt-out (G2, G7).
6. OCI: the OCR language contradiction (A10/A11), retention and training terms (G6), India
   region hosting (E9), and whether a "transaction" is a page (F9).
7. Google free-tier period and unit (F7).
8. Whether PlacedOn could qualify for Azure disconnected containers (H2). INFERRED unlikely
   ("strategic customer or partner").
9. Whether the 2512.18004 Marathi legal dataset is public (I11).
10. Mixed-script pages. Azure auto-detects without a language code (A7). Google's behaviour on an
    English deed with Hindi stamp text was not checked.

## Recommended next action

1. **Drop Textract and OCI from any Indic path.** Keep Textract only as a possible English-page
   baseline in `ap-south-1` with the org AI opt-out applied first (G1, G2). No further OCI work
   until it documents an Indic language.
2. **Extend R3's bake-off rather than run a second one** (R3 "Recommended next action" item 3):
   - Same public page set: ICSI specimens, scanned annexures from listed-company filings,
     stamp-paper pages, at least one non-Devanagari page.
   - Vendors: Azure DI Read + Layout (Central India), Google Enterprise OCR in `asia-south1`
     (Preview) **and** in `us` (GA), plus Sarvam Digitise.
   - Score per page: CER against hand transcription; stamp/seal region handled / dropped /
     garbled; any invented text.
   - Record the Google Mumbai-vs-US delta, because residency would force the Preview version.
3. **Correct PLAN_03 §OCR.** This file does not edit it. Replace the Azure on-prem sentence (H3),
   qualify the benchmark sentence (I4–I6), and mark the "best of the big three" sentence
   UNVERIFIED (I13). Add URLs from this file.
4. **Vendor questions** to add to `docs/VENDOR_QUESTIONS.md` (not edited by this task):
   - Microsoft: DI training-use position; South India availability; disconnected eligibility for
     a startup.
   - Google: GA timeline for OCR in `asia-south1`; Layout Parser in India.
   - AWS: Textract Indic roadmap; operational retention after opt-out.

---

## What this means for PLAN_12 (document intake architecture)

All rows here are **INFERRED** design consequences of the sourced evidence above.

1. **The OCR tier needs a script router before any vendor call, not after.** Route per page:
   - Latin → any vendor.
   - Devanagari (Hindi/Marathi/Nepali) → Azure or Google.
   - Sanskrit, Urdu, minor Devanagari → Azure.
   - Bengali/Gujarati/Kannada/Malayalam/Telugu/Gurmukhi → Google or Sarvam.
   - Odia/Assamese → Sarvam only.
   - Indic handwriting → Google (Hindi/Marathi/Nepali/Bengali) or Sarvam; never Azure (B2).
   This extends R3's router point with the Google half (A5–A10, B2–B3).
2. **Residency and capability conflict for Google; it must be a config axis, not a default.**
   Mumbai gives Preview-only OCR and no Layout Parser (E6). Structured Indic extraction in India
   means Azure Layout (Central India) or Google Form Parser (Mumbai, Hindi/Marathi/Nepali only).
   The adapter must record the actual processor version and location per page in provenance.
3. **Page splitting is driven by the smallest cap in the route**, not by the document:
   - Google online: 15 pages (30 imageless); batch 500.
   - Textract sync: 1 page.
   - OCI sync: 5 pages.
   - Sarvam: 10 per job (R3:D9).
   - Azure: 2,000 pages per call, but still split per page for idempotency and per-page
     abstention.
   Map partial-failure states (Textract `PARTIAL_SUCCESS`, Azure batch per-document `failed`,
   Sarvam `partially_completed`) to **per-page abstention**, never document success.
4. **Stamps and seals are ours to handle.** No vendor documents them (C8). PLAN_12 needs a
   region detector that flags stamp-dependent facts (stamp duty, execution, notarisation) as
   `UNVERIFIED`. Never trust silence from an OCR response as "no stamp".
5. **Tenant documents go only to adapters whose retention is a checked precondition:**
   - Google online: in-memory (G5).
   - Azure: call `Delete Analyze Result` immediately after fetch, and alarm if delete fails,
     since data lingers up to 24 h (G3).
   - Textract: disabled unless the AWS org AI opt-out policy is verified in effect, because
     inputs may otherwise be stored in another region (G1, G2).
   - OCI: disabled (G6).
   This mirrors R3's rule for Sarvam.
6. **No on-prem assumption.** Azure disconnected is approval-gated to strategic customers (H2).
   Connected containers still send billing data (H1). The realistic self-hosted Indic option
   evidenced so far is Sarvam on SageMaker (R3:F1). Region availability there is still
   UNVERIFIED (R3:F6).
7. **Confidence gate.**
   - Textract blocks carry `Confidence` (C1).
   - Azure selection marks carry `confidence` (C3).
   - Word-level OCR confidence was documented only for OCI in the pages read (A11 page). Its
     availability for Azure and Google was not checked here.
   Whatever the vendor emits is uncalibrated on our paper. Cross-vendor agreement per page, from
   the bake-off, is the defensible gate signal.
8. **Cost does not drive architecture.** Plain OCR costs about $1–1.50 per 1,000 pages
   everywhere (F10). Structure extraction costs $10–70 per 1,000 and should be reserved for pages
   the router marks as tabular or form-like.
9. **Scanned text stays untrusted.** It is untrusted document data under CLAUDE.md's image-borne
   injection note. Nothing in any vendor's output changes that.
