# R2 — Spellbook: how documents enter, how they are analysed, how outputs are checked

Track R, task R2 of `docs/PLAN_11_NEXT_MOVE.md`. Extends `docs/SPELLBOOK_INFERRED_ARCHITECTURE.md`
and `docs/SPELLBOOK.md`; does not replace them.

**Read on 2026-09-14.** Public pages only. No account, no trial, no login wall, no authenticated
area (`associate.spellbook.legal` returns 200 but is the product itself and was not entered).
`spellbook.com/robots.txt` disallows only `/checkout` and `/goodlawyer`; nothing read here is under
either. Pages were fetched individually, not crawled.

**Marker rules used in this file.**
`SOURCED` = the URL was opened on 2026-09-14 and the claim is on it; quoted text is verbatim.
`INFERRED` = our reasoning, stated as such. `UNVERIFIED` = could not be confirmed from a page we opened.
A vendor statement is SOURCED *as a vendor statement*. It is not evidence that the product behaves
that way.

**Dates.** Help-centre articles (Intercom) show only relative dates ("Updated over 2 weeks ago",
"Updated this week") as read on 2026-09-14, i.e. roughly late August to mid-September 2026
(INFERRED from the relative label). Blog posts show absolute "Last Updated" dates, given per row.

**Tool caveat.** Pages were read through a fetch tool that converts HTML to text and summarises.
Where wording is load-bearing (limits, OCR, citations, retention, audit logs, Market data model)
the exact string was re-requested character-for-character and is quoted below. Other paraphrases are
marked as such. A second human read of the quoted strings is part of the adversarial source check
PLAN_11 requires before commit.

---

## Question

Same questions as R1 (Harvey), for Spellbook:

1. **Intake.** How does a document get in — Word add-in, Google Docs, uploads, bulk / Associate,
   integrations — and with what formats and limits? What happens to a scanned PDF?
2. **Analysis.** How is it analysed — clause review, redlining, benchmarks / market standards,
   playbooks, multi-document review tables?
3. **Checking.** How are outputs checked or verified — citations, granularity, human approval?
4. **Security and retention.** Where is data processed, what is retained, for how long, and is it
   used for training?
5. **Against our prior documents.** Where does the public record confirm, extend or contradict
   `SPELLBOOK.md` and `SPELLBOOK_INFERRED_ARCHITECTURE.md`?

---

## Sources checked

All opened 2026-09-14.

**Vendor marketing and legal pages (spellbook.com)**
- https://www.spellbook.com/ (homepage; nav/footer; no page date)
- https://spellbook.com/features/ask (no page date)
- https://spellbook.com/features/review (no page date)
- https://spellbook.com/associate (no page date)
- https://spellbook.com/acm (no page date)
- https://spellbook.com/security (no page date)
- https://spellbook.com/legal/terms-of-service ("Updated: July 27, 2026")
- https://spellbook.com/legal/privacy-policy ("Updated: June 4, 2026")
- https://spellbook.com/sitemap.xml and https://spellbook.com/robots.txt (to find product pages,
  and to confirm nothing read is disallowed)

**Vendor blog**
- https://spellbook.com/blog/introducing-compare-to-market ("Last Updated on Jan 13, 2026";
  `spellbook.com/market` 301-redirects here)
- https://spellbook.com/blog/benchmarks ("last updated July 9, 2024")
- https://spellbook.com/blog/whats-new-in-spellbook-march-2026 (dated April 14, 2026)
- https://spellbook.com/blog/introducing-spellbooks-ai-document-editor ("Last Updated on Aug 13, 2026")
- https://spellbook.com/blog/gpt-5-live-in-spellbook ("Last updated August 7, 2025")
- https://spellbook.com/blog/humans-hallucinate-too (re-read; no absolute date surfaced by the fetch)

**Vendor help centre (help.spellbook.legal) — the main new source**
- https://help.spellbook.legal/en/ (collection index)
- https://help.spellbook.legal/en/articles/9926203-spellbook-overview
- https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate
- https://help.spellbook.legal/en/articles/15031655-reviewing-pdfs-with-spellbook-and-associate
- https://help.spellbook.legal/en/articles/15031616-data-retention-from-trial-to-paid-subscription
- https://help.spellbook.legal/en/articles/11525950-frequently-asked-questions-faq
- https://help.spellbook.legal/en/articles/10438652-associate-overview
- https://help.spellbook.legal/en/articles/16301239-upload-files-to-associate-library
- https://help.spellbook.legal/en/articles/10438749-ask-questions-across-multiple-documents
- https://help.spellbook.legal/en/articles/10438718-compare-documents-in-associate
- https://help.spellbook.legal/en/articles/16673907-create-and-configure-an-associate-workflow
- https://help.spellbook.legal/en/articles/12002974-review-tables
- https://help.spellbook.legal/en/articles/16042055-tabular-reports
- https://help.spellbook.legal/en/articles/9926323-set-up-and-use-library
- https://help.spellbook.legal/en/articles/14742397-imanage-integration
- https://help.spellbook.legal/en/articles/9079381-install-spellbook-in-microsoft-word
- https://help.spellbook.legal/en/articles/9940733-examine-documents-with-reviews
- https://help.spellbook.legal/en/articles/15656286-how-to-use-comprehensive-review
- https://help.spellbook.legal/en/articles/11321247-custom-review
- https://help.spellbook.legal/en/articles/14658818-how-to-use-proofread
- https://help.spellbook.legal/en/articles/9926250-playbooks-overview
- https://help.spellbook.legal/en/articles/11327030-create-playbooks
- https://help.spellbook.legal/en/articles/13875622-first-party-playbooks-redline-review
- https://help.spellbook.legal/en/articles/9160166-benchmarks
- https://help.spellbook.legal/en/articles/9926382-ask-spellbook-s-built-in-assistant
- https://help.spellbook.legal/en/articles/12881825-upload-and-use-reference-documents-in-ask
- https://help.spellbook.legal/en/articles/12953955-legal-sources
- https://help.spellbook.legal/en/articles/12641177-preference-learning
- https://help.spellbook.legal/en/articles/12650543-access-controls

**Trust centre**
- https://trust.spellbook.com/ and https://trust.spellbook.com/subprocessors
  (`trust.spellbook.legal/subprocessors` 301-redirects there). Both returned 200 but the fetch saw
  only a page title — the content is client-rendered. **Nothing about subprocessors could be read.**

**URL status checks (HTTP HEAD/GET status only, 2026-09-14)**
- `spellbook.legal` → 301 `spellbook.com`. `docs.spellbook.legal` → no response.
- `spellbook.com/product/associate`, `/ask`, `/review`, `/intake`, `/insight` → 404.
- `spellbook.com/associate`, `/acm`, `/security` → 200. `/playbooks` → 301 `/reviews`.

**Searched and not found (a search result, not a finding of absence):** a public API or developer
documentation; a public subprocessor list we could read; any page describing OCR of scanned
documents; any page describing how an Ask answer is checked against its cited text; any Spellbook
legal-source database named for India.

---

## Evidence found

### A. Intake — surfaces

| # | Claim | Marker | URL |
|---|---|---|---|
| A1 | Products listed: Review, Draft, Associate, Compare, Ask, Playbooks, ACM, Intake, Insight | SOURCED (paraphrase of nav) | https://www.spellbook.com/ |
| A2 | Entry surfaces named on the homepage: Word add-in, Google Docs add-in, browser document editor, email / Slack / Salesforce, and cloud storage (Google Drive, Dropbox, OneDrive, SharePoint, iManage) | SOURCED (paraphrase) | https://www.spellbook.com/ |
| A3 | Word add-in installs from the Microsoft Office Add-in Store on Windows and macOS; sign-in by email, Google or Microsoft account; licence key to activate. Word Online and iPad are not mentioned | SOURCED (paraphrase); Word Online/iPad support UNVERIFIED | https://help.spellbook.legal/en/articles/9079381-install-spellbook-in-microsoft-word |
| A4 | Associate is "a web application designed to streamline multi-document workflows", at `associate.spellbook.legal`, with a desktop app; it is distinct from the Word add-in, which handles single-document tasks | SOURCED | https://help.spellbook.legal/en/articles/10438652-associate-overview |
| A5 | Associate recommends starting with "2-5" documents "for best results" | SOURCED | https://help.spellbook.legal/en/articles/10438652-associate-overview |
| A6 | An AI document editor inside Associate: "fix a typo or tighten a clause without downloading the file and opening Word first" — launched August 2026 | SOURCED | https://spellbook.com/blog/introducing-spellbooks-ai-document-editor |
| A7 | Library: upload from device or connect an integration; "Library documents are used to pull relevant clauses and context into your projects, they don't give you access to the full document itself within a project" | SOURCED (second sentence exact) | https://help.spellbook.legal/en/articles/16301239-upload-files-to-associate-library |
| A8 | iManage: fetched on demand, "It does not create a persistent library sync of your iManage repository"; honours iManage access controls including ethical walls; IT admin must enable it in iManage Control Center | SOURCED | https://help.spellbook.legal/en/articles/14742397-imanage-integration |
| A9 | Tabular Reports: documents uploaded or synced from OneDrive, SharePoint, Dropbox, iManage, Google Drive; "a limit of 500 documents per account at no extra cost … a pooled account-wide limit" | SOURCED | https://help.spellbook.legal/en/articles/16042055-tabular-reports |
| A10 | ACM Intake pulls contracts from email, Slack, Salesforce and CLM systems and runs a first-pass review against organisational standards; ACM Insight stores and indexes executed contracts and monitors renewals | SOURCED (paraphrase) | https://spellbook.com/acm |
| A11 | ACM general availability was stated as "Summer 2026" behind a waitlist; whether it is GA on 2026-09-14 | SOURCED (the statement); current status UNVERIFIED | https://spellbook.com/acm |

### B. Intake — formats and limits

| # | Claim | Marker | URL |
|---|---|---|---|
| B1 | Word and Google Docs add-in: "4 MB per document" | SOURCED (exact) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B2 | Ask attachments: "20 files at a time" (100 total per session) | SOURCED (first part exact; "100 per session" paraphrase) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B3 | Ask attachments: "Files are automatically deleted after 3 days" | SOURCED (exact) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B4 | Add-in accepts .doc/.docx, "OCR PDFs", .txt | SOURCED ("OCR PDFs" exact) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B5 | Associate: 20 MB per file; Word, PDF, "Excel (.xlsx) files"; only .docx directly editable; avoid "heavy photos", tables or complex formatting for accuracy | SOURCED (quoted parts exact) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B6 | Large files: split into smaller segments | SOURCED (paraphrase) | https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B7 | **Scanned PDFs are not OCR'd:** PDFs must be "OCR'd (have a searchable text layer)"; "Scanned PDFs without OCR will upload" but Associate cannot reference their content | SOURCED (quoted parts exact) | https://help.spellbook.legal/en/articles/16301239-upload-files-to-associate-library |
| B8 | Ask: "make sure any PDFs you upload are OCR'd (text-recognizable)" | SOURCED (exact) | https://help.spellbook.legal/en/articles/12881825-upload-and-use-reference-documents-in-ask |
| B9 | The Word product "cannot directly analyze or review PDF documents"; convert to .docx first, or use Associate | SOURCED (paraphrase with quoted fragment) | https://help.spellbook.legal/en/articles/15031655-reviewing-pdfs-with-spellbook-and-associate |
| B10 | B4 and B9 conflict on their face (OCR PDFs accepted by the add-in vs add-in cannot review PDFs). Most likely reading: PDFs are accepted as Ask *reference* attachments but cannot be the document under review in Word | INFERRED | (B4, B9 URLs) |
| B11 | Associate Overview lists Word, PDF and .txt as readable; File Size Limits lists Word, PDF and Excel. The two help articles disagree on the format list | SOURCED (both statements); which is current UNVERIFIED | https://help.spellbook.legal/en/articles/10438652-associate-overview ; https://help.spellbook.legal/en/articles/15031689-file-size-limits-in-spellbook-and-associate |
| B12 | Ask marketing page claims "any contract length" and "140+ languages", against a 4 MB add-in limit (B1) | SOURCED (claims); reconciliation UNVERIFIED | https://spellbook.com/features/ask |
| B13 | Whether the UI warns a user at upload time that a scanned PDF has no text layer | UNVERIFIED (no page describes it) | https://help.spellbook.legal/en/articles/16301239-upload-files-to-associate-library |

### C. Analysis — review, redlining, playbooks, benchmarks, market

| # | Claim | Marker | URL |
|---|---|---|---|
| C1 | Review takes a represented party; three levels: "Light Markup: Flag only critical issues", "Standard Markup: Balanced review of important and notable issues", "Heavy Markup: Flag everything, including minor and phrasing issues" | SOURCED (exact) | https://help.spellbook.legal/en/articles/9940733-examine-documents-with-reviews |
| C2 | Each flagged issue shows reasoning ("Down below, you will see reasoning as to why that issue was flagged"); "Click "show" to see where in the document it applies"; "Apply" inserts; "Toggle "Use tracked changes" if you'd like Spellbook to redline revisions for you" | SOURCED (exact) | https://help.spellbook.legal/en/articles/9940733-examine-documents-with-reviews |
| C3 | Comprehensive Review adds jurisdiction and deal context and returns "General Risks" and "Proofread" results | SOURCED (paraphrase) | https://help.spellbook.legal/en/articles/15656286-how-to-use-comprehensive-review |
| C4 | Custom Review: free-text instructions, "It will review only what it tells you to and gets more detailed than a general review" | SOURCED | https://help.spellbook.legal/en/articles/11321247-custom-review |
| C5 | Proofread covers "definitions, section references, template placeholders, grammar"; whether it is rule-based or model-based is not stated | SOURCED (scope); mechanism UNVERIFIED | https://help.spellbook.legal/en/articles/14658818-how-to-use-proofread |
| C6 | Redlines "appear under your name"; "You choose which are approved and applied" | SOURCED | https://spellbook.com/features/review |
| C7 | "Apply All" accepts multiple suggested edits in one click (March 2026 release) | SOURCED (paraphrase) | https://spellbook.com/blog/whats-new-in-spellbook-march-2026 |
| C8 | Playbooks "are intended to run a set of automated checks against the document"; results pass (green check) / fail (red dotted circle), with AI reasoning, and a target icon jumps to the location | SOURCED | https://help.spellbook.legal/en/articles/9926250-playbooks-overview |
| C9 | Playbook creation: clone a starter playbook, generate from model documents (Word/PDF, favoured party, jurisdiction), generate from a plain-language description, or add rules by hand; "Suggest Rules from Current Document"; "Chat with AI" | SOURCED (paraphrase) | https://help.spellbook.legal/en/articles/11327030-create-playbooks |
| C10 | Rule fields: fallback positions, Low/Medium/High risk, preferred language, notes, suggested comments, approval requirements (named reviewers) | SOURCED (paraphrase) | https://help.spellbook.legal/en/articles/11327030-create-playbooks |
| C11 | Playbook version history and "rule conflict detection" before review runs (March 2026) | SOURCED (paraphrase) | https://spellbook.com/blog/whats-new-in-spellbook-march-2026 |
| C12 | First-party playbooks run on tracked changes and return per rule: Accept Redline, Reject Redline, Accept/Reject with Revision, No Relevant Redline; plus internal and counterparty comments | SOURCED | https://help.spellbook.legal/en/articles/13875622-first-party-playbooks-redline-review |
| C13 | Benchmarks: "a proprietary Rules Engine that uses LLMs to generate standards for specific types of contracts"; "over 2,000 standards"; output is a coverage percentage of rules covered | SOURCED | https://help.spellbook.legal/en/articles/9160166-benchmarks |
| C14 | Benchmarks collects "standard ruleset" data from all firms, which "may be used to calculate things like rule 'hit rates'" | SOURCED | https://help.spellbook.legal/en/articles/9160166-benchmarks |
| C15 | Benchmarks blog describes "a powerful matching algorithm" to match a document to a standard, and was "still in beta" (July 2024) | SOURCED (dated 2024; may be stale) | https://spellbook.com/blog/benchmarks |
| C16 | Compare to Market data model: "Give to Get: Combine aggregate statistical insights with the rest of our users in order to get access for free." / "Pay to Get: Withhold your data from the pool, and get access to insights from the full pool, for an extra fee." / "Siloed Data" for private dealflow | SOURCED (exact) | https://spellbook.com/blog/introducing-compare-to-market |
| C17 | Market data "is completely anonymous, and only contains facts like: 'What is the average late payment interest rate in SaaS agreements?'" | SOURCED (exact) | https://spellbook.com/blog/introducing-compare-to-market |
| C18 | The Market pool is built at least partly from deal-point statistics extracted from customers' own agreements (opt-in by default under "Give to Get"). The page does not say whether any non-customer corpus (e.g. public filings) is also in the pool | INFERRED from C16–C17 | https://spellbook.com/blog/introducing-compare-to-market |
| C19 | Market looks like **extract deal points → aggregate statistics**, not nearest-neighbour document retrieval | INFERRED from C17's example | https://spellbook.com/blog/introducing-compare-to-market |
| C20 | Associate workflows: fixed step types — prompt steps, file-upload steps, question steps (single/multi select, free text) — run in sequence, "once one step completes, the next begins automatically" | SOURCED | https://help.spellbook.legal/en/articles/16673907-create-and-configure-an-associate-workflow |
| C21 | Associate: "breaks goals down into tasks and executes them"; use cases dataroom reviews, financing documents, disclosure schedules, employment packages | SOURCED | https://spellbook.com/associate |
| C22 | Review Tables: user enters questions, Associate returns a table with an answer per document; exportable. Limits and cell citations not described | SOURCED (feature); cell citations UNVERIFIED | https://help.spellbook.legal/en/articles/12002974-review-tables |
| C23 | Preference Learning: "an opt-in, per-user feature that stores small fragments of a user's review interactions"; suggestions generated "by comparing previously accepted review text to target paragraphs" | SOURCED | https://help.spellbook.legal/en/articles/12641177-preference-learning |
| C24 | Models named: homepage says "state-of-the-art LLMs like GPT5 and Opus" (undated page); a 2025 post names GPT-5, Claude 4 and GPT-4o. Which model serves which feature today | SOURCED (statements); current routing UNVERIFIED | https://www.spellbook.com/ ; https://spellbook.com/blog/gpt-5-live-in-spellbook |

### D. Checking — citations, verification, human approval

| # | Claim | Marker | URL |
|---|---|---|---|
| D1 | Ask with reference documents: "There will be citations that you can hover over to see the exact quoted paragraph or bullet from your reference document." | SOURCED (exact) | https://help.spellbook.legal/en/articles/12881825-upload-and-use-reference-documents-in-ask |
| D2 | Legal Sources: answers "grounded in trusted, jurisdiction-specific legal sources like CanLII and EDGAR"; "citations you can hover over to see where the information was sourced from"; a list of all sources searched | SOURCED | https://help.spellbook.legal/en/articles/12953955-legal-sources |
| D3 | Legal Sources Asia & Pacific section names only Japanese law sources (laws.e-gov.go.jp, japaneselawtranslation.go.jp). No Indian database was named. The fetch reported AsianLII among "Commonwealth" sources; whether it is used for Indian statutes is not stated | SOURCED (list as read); AsianLII listing and Indian coverage UNVERIFIED | https://help.spellbook.legal/en/articles/12953955-legal-sources |
| D4 | No help article read describes whether Legal Sources checks currency, commencement or amendment date of a source | SOURCED (absence on these pages only — not absence in the product) | https://help.spellbook.legal/en/articles/12953955-legal-sources |
| D5 | Multi-document Ask, Compare Documents in Associate, Review Tables and Tabular Reports: none of the four articles says whether an answer or cell cites a document, page or passage | SOURCED (absence on these pages only) | https://help.spellbook.legal/en/articles/10438749-ask-questions-across-multiple-documents ; https://help.spellbook.legal/en/articles/10438718-compare-documents-in-associate ; https://help.spellbook.legal/en/articles/12002974-review-tables ; https://help.spellbook.legal/en/articles/16042055-tabular-reports |
| D6 | The Review help article contains no sentence about verification or human review (checked by exact-string request) | SOURCED (absence on this page) | https://help.spellbook.legal/en/articles/9940733-examine-documents-with-reviews |
| D7 | No page read describes a mechanism that checks a generated answer against its cited text | SOURCED (absence on pages read); existence in product UNVERIFIED | (all help-centre URLs above) |
| D8 | ToS §5.4: customer will not "solely rely on Output as constituting formal legal advice, and will ensure, when appropriate, that any Output is reviewed or vetted accordingly by a duly licensed and qualified lawyer" | SOURCED | https://spellbook.com/legal/terms-of-service |
| D9 | ToS §8.4: output "IS NOT (AND IS NOT INTENDED TO BE) FORMAL LEGAL ADVICE"; customer "ULTIMATELY RESPONSIBLE FOR ALL DECISIONS" | SOURCED (fragments) | https://spellbook.com/legal/terms-of-service |
| D10 | Verification is placed contractually on the customer's lawyer and in the UI on per-suggestion Apply / accept-reject, not on a documented system check | INFERRED from D1–D9 | — |
| D11 | Spellbook Labs "Humans Hallucinate Too": 3,019 EDGAR contracts, 60% with drafting errors, 2.5% high-risk, 1.15 issues per contract, "deliberately conservative", "the floor, not a full account"; no human-validation count or false-positive rate found on re-read | SOURCED (re-read; confirms `SPELLBOOK.md` §4) | https://spellbook.com/blog/humans-hallucinate-too |

### E. Security and retention

| # | Claim | Marker | URL |
|---|---|---|---|
| E1 | "Spellbook has negotiated agreements with both OpenAI and Anthropic for zero data retention (ZDR)… customer data … is not persisted and exists only in memory in order to process a request" | SOURCED | https://spellbook.com/security |
| E2 | "cloud providers with data centers in Canada and US for storing and processing customer data"; AWS named as primary cloud provider | SOURCED | https://spellbook.com/security |
| E3 | SOC 2 Type II, HIPAA (BAAs in Trust Center), GDPR; EU AI Act low-risk opinion from CMS; SSO/MFA via Microsoft Entra; "law firms in over 80 countries" | SOURCED (vendor statements; certificates not inspected) | https://spellbook.com/security |
| E4 | India data residency: not offered on the security page (only Canada and US named) | SOURCED (as stated on page); whether available by contract UNVERIFIED | https://spellbook.com/security |
| E5 | ToS §4.1(b): Customer Data sent to Third Party LLMs "will not be used to train, improve, or develop the AI models" of those LLMs; ZDR required by DPA | UNVERIFIED (source check 2026-09-14: the training sentence is verbatim, but at §4.1(b)(iv), not bare §4.1(b). The page does not say ZDR is required by the DPA. §4.1(b)(ii) says a data processing agreement exists "to ensure they are responsible for processing Customer Data in compliance with Privacy/Security Laws". §4.1(b)(iii) puts ZDR in separate "agreements with all Third Party LLMs prohibiting them from storing or retaining any Customer Data", qualified by "unless otherwise agreed or directed by Customer". Both the DPA link and the missing caveat are unsupported) | https://spellbook.com/legal/terms-of-service |
| E6 | **ToS §4.1(c)(iv) Quality Assurance:** inputs and outputs may be retained "for no longer than 90 days from the date of collection, then permanently deleted", accessed by "authorized Spellbook personnel on an as-needed basis" | SOURCED | https://spellbook.com/legal/terms-of-service |
| E7 | ToS §4.1(c)(iii): processing permitted "to calibrate its internal systems for User-specific personalization", with de-identification | SOURCED (paraphrase with quoted fragment) | https://spellbook.com/legal/terms-of-service |
| E8 | ToS §4.2(d): Spellbook may derive "anonymous data and statistics from Customer Data" for its own business purposes if it "cannot reasonably be used or reverse-engineered to identify" customer or users | SOURCED | https://spellbook.com/legal/terms-of-service |
| E9 | Privacy policy "does not apply to document data that Spellbook processes on behalf of its customers"; that is governed by customer agreements | SOURCED | https://spellbook.com/legal/privacy-policy |
| E10 | Google Drive data retained "only for as long as you maintain the corresponding Spellbook library"; deleting the library removes files, metadata, tokens | SOURCED | https://spellbook.com/legal/privacy-policy |
| E11 | Preference Learning fragments "retained for 1 year after generation"; not "used to train models across customers"; deletable by the user | SOURCED | https://help.spellbook.legal/en/articles/12641177-preference-learning |
| E12 | Trial end: "your projects become inaccessible unless you upgrade"; data reappears on resubscription. No deletion timeline given | SOURCED | https://help.spellbook.legal/en/articles/15031616-data-retention-from-trial-to-paid-subscription |
| E13 | FAQ: "Spellbook doesn't store your files, so cancelling doesn't put your documents at risk" | SOURCED (vendor statement) | https://help.spellbook.legal/en/articles/11525950-frequently-asked-questions-faq |
| E14 | E13 is in tension with Library uploads being stored until deleted (A7, E10), Ask attachments kept 3 days (B3), and QA retention up to 90 days (E6). Most likely it means Spellbook is not the system of record, not that no copy exists | INFERRED | (E13, A7, B3, E6 URLs) |
| E15 | Access controls: sharing to teams or whole organisation, "but **not individual users**"; roles Admin/Editor/Viewer/Consumer; "No — audit logs for role changes or resource sharing are not currently supported."; "Removing users currently requires assistance from your Customer Success Manager (CSM) or Support team." | SOURCED (exact) | https://help.spellbook.legal/en/articles/12650543-access-controls |
| E16 | Subprocessor list | UNVERIFIED (trust centre is client-rendered; not readable by our fetch; no login attempted) | https://trust.spellbook.com/subprocessors |

---

## Evidence quality

- **Much stronger than the 2026-09-03 read.** The public help centre (`help.spellbook.legal`) is
  operational documentation: limits, file types, failure behaviour, retention windows, permission
  roles. It is the vendor's own, so it is authoritative *about what the vendor says*, not about
  runtime behaviour.
- **The ToS is the strongest single source on retention and training** — it is contractual, dated
  (27 Jul 2026), and more specific than the marketing security page.
- **Internally inconsistent in four places** (B10, B11, B12, E14). Help articles carry relative
  dates only, so which statement is current cannot be settled from outside.
- **Marketing claims are unmeasured** ("Accurate answers, with citations", "10 million contracts
  reviewed"). The one accuracy publication remains self-graded with no false-positive rate (D11).
- **Stale-risk rows:** C15 (2024 blog), C24 (model names: 2025 post and an undated homepage line).
- **Not independent.** No third-party test, audit report or press investigation was used. Every
  SOURCED row is the vendor describing itself.
- **Fetch-tool paraphrase risk** is real for rows marked "paraphrase". The load-bearing rows (B1,
  B3, B4, B5, B7, B8, C1, C2, C16, C17, D1, E15) were re-requested as exact strings.

---

## Result

### 1. How documents enter

Five surfaces (A2–A10): the **Word add-in** (single document, 4 MB), the **Google Docs add-in**
(same limit), **Associate** (web + desktop, multi-document, 20 MB per file, now with its own
document editor), the **Library** (uploads or connected storage, used to pull clauses — not whole
documents — into projects), and **ACM Intake** (email / Slack / Salesforce / CLM; GA stated for
Summer 2026). Bulk review is **Tabular Reports**, capped at a pooled 500 documents per account
before extra fees (A9). iManage is fetched per request with no persistent sync (A8).

**Scanned documents are not OCR'd.** A scanned PDF "will upload" but its content cannot be
referenced (B7). No page describes a warning to the user (B13). Associate recommends avoiding
heavy photos, tables and complex formatting (B5), and advises splitting large files (B6).

### 2. How documents are analysed

Party-aware clause review at three sensitivities with per-issue reasoning, a jump-to-location
link, and tracked-change redlines authored under the user's name (C1–C6). Playbooks are structured
rules — fallback positions, risk levels, preferred language, named approvers — generated from
templates, model documents or descriptions, with version history and conflict detection (C8–C12),
and they can be run on counterparty redlines (C12). Benchmarks score rule *coverage* against LLM-
generated standards (C13). Compare to Market reports aggregated deal-point statistics from a user
pool (C16–C17). Associate runs fixed-step workflows (C20) and question-by-document review tables (C22).

### 3. How outputs are checked

- **Ask over reference documents cites at paragraph or bullet granularity**, shown as an exact
  quote on hover (D1). Not character spans, not page numbers.
- **Legal Sources** cites via hover and lists the sources searched (D2). No currency or amendment-
  date handling is described (D4).
- **Multi-document answers, comparisons, review tables and tabular reports have no documented
  citation** (D5).
- **No page describes a check of the answer against the cited text** (D7).
- Verification is the customer's job, in the contract (D8–D9), and in the UI through per-suggestion
  Apply — softened by Apply All (C7).

### 4. Security and retention

LLM-provider ZDR with OpenAI and Anthropic; Canada/US on AWS; SOC 2 Type II, HIPAA, GDPR (E1–E3).
Spellbook's own retention is **not zero**: QA inputs/outputs up to 90 days with staff access (E6);
Ask attachments 3 days (B3); Library until deleted (E10); preference fragments 1 year (E11);
anonymised derived statistics permitted (E8) and used for Market (C16). **No audit log for sharing
or role changes** (E15). No India region named (E4).

### 5. Against our prior documents

| Prior statement | File | Verdict | Basis |
|---|---|---|---|
| Surfaces: Word and Google Docs; intake from email, Slack, Salesforce; ZDR with OpenAI and Anthropic; Canada and US; SOC 2 Type II, HIPAA, GDPR | `SPELLBOOK.md` §1 | **CONFIRMED** | A2, A10, E1–E3 |
| `docs.spellbook.legal`, `/product/associate`, `/ask` do not resolve | `SPELLBOOK.md` header; `SPELLBOOK_INFERRED_ARCHITECTURE.md` §4a | **CONFIRMED but misleading.** Still true on 2026-09-14, but a full public help centre lives at `help.spellbook.legal`, and `/associate` and `/features/ask` resolve | URL checks; help-centre index |
| "No amount of further public reading will close them [the OPEN markers]. Only the vendor can." | `SPELLBOOK_INFERRED_ARCHITECTURE.md` §4a | **CONTRADICTED in part.** The help centre partly closes Ask citation granularity and the Market corpus source (below). Q2 (checked vs retrieved) and playbook conformance mechanism remain open | D1, C16–C18 |
| Ask OPEN: citation resolves to a passage or a document (Vendor Q1) | both | **Partly UPGRADED to SOURCED:** for reference documents, paragraph or bullet, exact quote on hover. For Legal Sources and all multi-document features, still OPEN | D1, D2, D5 |
| Ask OPEN: cited text checked against the answer (Vendor Q2) | both | **Still OPEN.** Nothing read describes such a check | D7 |
| Compare OPEN: where the corpus comes from | both | **Partly UPGRADED:** the Market pool is (at least) customers' aggregated, anonymised deal-point statistics under "Give to Get". Whether it also contains non-customer data remains OPEN | C16–C18 |
| Compare LIKELY: dense-vector retrieval; "the strongest argument that their architecture is built around similarity" | `SPELLBOOK_INFERRED_ARCHITECTURE.md` §2 | **WEAKENED (INFERRED, not SOURCED).** Market's own example is a statistic over an extracted deal point, which is extraction + aggregation, not neighbour search. Similarity retrieval may still exist (Library "pull relevant clauses", A7; Benchmarks "matching algorithm", C15) but Market is not the evidence for it | C17, C19, A7, C15 |
| Playbooks OPEN: rule engine or a model judging conformance (Vendor Q10) | both | **Still OPEN, narrowed.** Rules are structured records (C10); Benchmarks standards are LLM-generated by a "Rules Engine" (C13); playbook results carry "AI Reasoning" (C8). That makes a model judge LIKELY (INFERRED). The conformance step itself is not described | C8, C10, C13 |
| Review/redline LIKELY: hard part is a tracked change that survives Word's revision model | both | **CONSISTENT, not proven.** Redlines are tracked changes "under your name", with a location link (C2, C6). Nothing on engineering difficulty | C2, C6 |
| Associate/ACM OPEN: fixed graph or model-chosen plan | both | **Partly UPGRADED:** user-authored Associate workflows are a fixed sequence of typed steps (C20). Free-form Associate prompts "break goals down into tasks" (C21) — mechanism still OPEN | C20, C21 |
| "Zero data retention with the LLM providers is narrower than 'we do not train on your data'. Their security page does not address the second" | `SPELLBOOK_INFERRED_ARCHITECTURE.md` §2 | **EXTENDED.** The homepage and ToS §4.1(b) now address training for *third-party* LLMs. The narrower-scope point is sharpened, not overturned: Spellbook itself retains QA data up to 90 days, keeps preference fragments a year, and derives anonymous statistics | E5–E8, E11 |
| Pricing per seat, not published, 7-day trial | both §1–2 | **Not re-checked** (out of R2 scope). One extension: bulk Tabular Reports is metered by a pooled 500-document quota, i.e. per-document pricing exists alongside per-seat | A9 |
| Point-in-time law for a 2019 contract (Vendor Q7) | both | **Still OPEN.** No page discusses as-of-date law | D4 |
| "Humans Hallucinate Too" has no false-positive rate | both §4 | **CONFIRMED** on re-read | D11 |

---

## What this means for PLAN_12 (document intake architecture)

All of this section is INFERRED design reasoning built on the SOURCED rows cited.

1. **The most useful finding is a failure mode to design against: "upload succeeded" ≠ "content
   readable".** Spellbook accepts a scanned PDF and then cannot reference it (B7), with no warning
   described (B13). For a verdict-producing audit layer, a silently unreadable page is the worst
   case — it reads as "no defect found". PLAN_12's intake must make readability a per-page
   *verdict* at upload: text layer / needs OCR / OCR failed gate → **abstain on that page, and say
   which page**. This is the D1 census and the role-13 gate. It is where we should be visibly
   stricter than the incumbent, not merely different.

2. **Size caps are a design choice, not an embarrassment.** A funded vendor caps the Word surface at
   4 MB and Associate at 20 MB, and tells users to split files (B1, B5, B6). A 300-page scheme of
   arrangement with scanned annexures will exceed that. PLAN_12 should state explicit caps per
   surface (add-in vs server upload), and put large documents on the server path by construction —
   the add-in is a *viewer of findings*, not the intake for an F8-scale document.

3. **Do not adopt "pull relevant clauses, not the full document".** Library works on retrieved
   fragments (A7). PLAN_11 already requires whole-section context where verbatim quotability
   depends on it (`PROVIDER_DECISION` §2). The contrast is worth writing into PLAN_12 as a rejected
   alternative, with this row as the citation.

4. **Citation granularity is our clearest separable claim.** Spellbook's best documented citation is
   a paragraph or bullet quote on hover, for reference documents only (D1); multi-document tables
   have none documented (D5). PLAN_12's page + offset spans on every fact, with cell-level
   abstention in the F8 table, go further on both granularity and coverage. **Adopt the UX, not the
   granularity:** hover-to-see-exact-quote is the right interaction; the anchor under it should be
   page + char span.

5. **Human approval: keep verdicts out of any "Apply All".** Spellbook's review is per-suggestion
   Apply, then added Apply All (C7). That is fine for redlines. For VERIFIED / POTENTIAL_ISSUE
   verdicts a bulk-accept breaks the evidence chain. PLAN_12 should not expose bulk acceptance of
   findings.

6. **Retention must be declared per artefact class, and ZDR is not the whole answer.** Spellbook is
   ZDR with its LLM providers yet retains QA inputs/outputs up to 90 days, attachments 3 days,
   library until deleted, preferences a year (E1, E6, B3, E10, E11). PLAN_12 (with PLAN_07) should
   list each class — raw upload, page images, OCR text, extracted facts, findings, QA/eval logs,
   hashes — with its own retention, and state that a document *hash* may outlive its *content*.
   Provider-side ZDR belongs in the provider-adapter row, not as the retention policy.

7. **Integration pattern worth copying: fetch on demand, honour the source's permissions.** The
   iManage design — no persistent sync, ethical walls respected (A8) — is the right default for a
   firm's DMS and also minimises what we hold. Record it as the default for any future DMS adapter.

8. **Audit log is a gap to exceed, cheaply.** Spellbook documents no audit log for role changes or
   sharing (E15). An evidence-backed audit product without its own intake and access log is
   incoherent. PLAN_12 intake events (upload, hash, sniff, scan result, page verdicts, who viewed
   which finding) should go to the existing event log from day one.

9. **Residency is a real differentiator, not just a compliance row.** Only Canada and US are named
   (E2, E4). This does not prove India is unavailable by contract (UNVERIFIED), but it supports
   PLAN_12's residency-first design option and the India-region cloud mapping table.

10. **Excel is a first-class input for the incumbent's multi-document product** (B5). Ind AS
    financial statements and annexures often travel as spreadsheets (to be confirmed by R5). PLAN_12
    should decide explicitly whether .xlsx is in or out of intake, rather than inherit PDF-only.

11. **Aggregated customer statistics are a product for them and a non-goal for us.** "Give to Get"
    pools customer deal points by default (C16). A statutory audit layer has no need for
    cross-tenant statistics, and PLAN_12 should say so, so derived-data rights are not written into
    our terms by imitation.

---

## Unresolved issues

1. **Vendor Q2** — is cited text checked against the answer? No public page addresses it (D7).
2. **Vendor Q10** — is playbook conformance judged by a model or a deterministic engine? Narrowed,
   not settled (C8, C10, C13).
3. **Citations in multi-document features** — do Review Table / Tabular Report cells cite a page or
   passage? Undocumented (D5).
4. **Scanned-PDF behaviour at upload** — is the user warned? Undocumented (B13).
5. **Format list conflicts** — Excel vs .txt in Associate (B11); PDFs in the Word add-in (B10); "any
   contract length" vs 4 MB (B12).
6. **Market pool composition** — customer-only, or also public/licensed data (C18)?
7. **Subprocessors** — trust centre not readable without client-side rendering (E16).
8. **India** — no Indian legal source named (D3); no India region named (E4). Both are "not found on
   pages read", not "does not exist".
9. **Current model routing** — undated homepage line vs a 2025 blog (C24).
10. **ACM GA status** as of 2026-09-14 (A11).
11. **Termination deletion timeline** for Library and Associate projects — ToS and help centre give
    none (E12).
12. **Fetch-tool paraphrase** — rows marked "paraphrase" need a human read before this file is
    relied on in PLAN_12.

---

## Recommended next action

1. **Adversarial source check** (required by PLAN_11 before commit): a second reader opens every
   URL above and confirms the exact-string rows (B1, B3, B4, B5, B7, B8, C1, C2, C16, C17, D1, E6,
   E15) against the live page, noting the relative "Updated" label on each help article.
2. **Update `docs/VENDOR_QUESTIONS.md`** (a separate task; this file does not edit it): mark Q1 as
   partly answered from public docs (D1), keep Q2/Q7/Q10 open, and add: (a) behaviour on upload of a
   scanned PDF with no text layer; (b) do Review Table / Tabular Report cells cite page or passage;
   (c) what is in the Market pool besides "Give to Get" contributions; (d) retention of Library and
   Associate documents after termination; (e) readable subprocessor list; (f) India region by contract.
3. **Update `SPELLBOOK.md` / `SPELLBOOK_INFERRED_ARCHITECTURE.md`** (separate task) with the
   verdict table in Result §5 — in particular retire "no amount of further public reading will close
   them" and the claim that Compare is the strongest evidence for similarity retrieval.
4. **Feed PLAN_12**: take items 1, 2, 4, 6 and 8 of the PLAN_12 section above as explicit
   requirements or rejected alternatives, each citing its row ID here.
5. **Read the trust centre with a JS-rendering browser** (still public, no login) to recover the
   subprocessor list and any published retention schedule; record as a follow-up row, not an edit
   to this table.
