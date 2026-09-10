# Data sources — verified access mechanics

Six research passes, 2026-09-09. Every claim carries a URL or a status marker.
Where a source could not be reached, the block is recorded rather than worked
around, per this repo's source policy.

## The finding that shapes the product

**There is no authoritative machine-readable feed of new Gazette instruments.**
Not on e-Gazette, not on MCA, not on India Code. The only live feed found in the
entire stack is SEBI's undocumented `sebirss.xml`, and it is an unfiltered
firehose of circulars, enforcement orders and press releases with no type field.

Worse, verified against our own test case: **G.S.R. 880(E), notified 01-12-2025,
was still absent from India Code's index in September 2026** — nine months later.
The government's own consolidated-law site does not carry the current law.

**This is the moat, not an obstacle.** No competitor can automate their way to
currency either. It requires deliberate human-in-the-loop acquisition, which is
what this architecture already is. Anyone shipping a wrapper on a frontier model
inherits the staleness.

## Statute and Gazette

| Source | Machine-accessible? | Feed? | Notes |
|---|---|---|---|
| **e-Gazette** | PDF fetchable **only if the numeric ID is already known**; search is session-stateful ASP.NET | None | No robots.txt (404). G.S.R. 880(E) verified at `WriteReadData/2025/268124.pdf` |
| **MCA** | **No — Akamai 403 on every path tested**, confirmed by two independent tools | None | Recorded as a hard block. Route around via e-Gazette |
| **India Code** | Undocumented DSpace 9.1 REST API at `/server/api` | "newest accessioned" is polluted by 1940s digitisation backfill | `www.` subdomain has a cert SAN mismatch — use the bare domain. ~40% 502 rate in a small sample |
| **SEBI** | Yes — robots permissive | **`sebirss.xml`**, live, undocumented | The only real feed found anywhere |

**Licence:** Copyright Act 1957 s.52(1)(q)(ii) permits reproducing an Act only
together with original matter. A public repository of clean statutory text is an
Act download — which is why the corpus is excluded from the public plan repo.

## Company data

**A Verified Company Card cannot be built on free data alone.** Verified.

- **`data.gov.in` Company Master Data** gives CIN, name, status, class, capital,
  RoC, incorporation date, registered address — under GODL-India. It has **no
  director/DIN field, no s.77 charges, no s.164 disqualification join.**
- Disqualified-director and struck-off lists exist as static per-RoC HTML/PDF on
  **mca.gov.in — which is bot-blocked.**
- **No official MCA developer API or bulk-licensing programme was found**, in
  contrast to GSTN's formal GSP/ASP model.
- The statutory route is Rule 12, Companies (Registration Offices and Fees) Rules
  2014: **₹100 per company** document inspection.

**On aggregators — the important finding:** *no* vendor examined could be verified
as an authorised MCA reseller. FileSure is at least explicit, publishing ₹5/call
and ₹330/company/year and describing itself as automating the same paid public
portal. Treat all of them as automation-of-a-public-source until one produces an
actual data-sharing agreement. "Sourced directly from MCA" describes provenance,
not a licence.

**No LEI-keyed ownership graph exists for India.** LEIL coverage is limited to
RBI/SEBI-mandated entities; s.90 SBO data exists only as per-company BEN-2 forms
behind the same paid inspection route.

## Case law and tribunals — more open than assumed

- **Indian Kanoon has a real documented API** with published per-call pricing
  (search ₹0.50, document ₹0.20, metadata ₹0.02) and a mandatory attribution
  requirement. This is the cleanest acquisition path available.
- **NCLT / NCLAT / IBBI orders are natively text PDFs.** Six real order PDFs were
  downloaded and text-extracted cleanly — **no OCR required** for the recent
  corpus. Pre-2021 archive format is UNVERIFIED (domain unreachable).
- **NJDG / eCourts bulk API is government-only** — not licensable by a private
  company.
- **India has no Shepard's/KeyCite.** Citation treatment exists only as a UI
  feature inside SCC Online and Manupatra, not as licensable data.
- Copyright Act s.52(1)(q)(iv) permits reproducing judgments unless the court
  prohibits it — but **publisher headnotes and edited text retain copyright.**

## OCR — the gate on bulk document review

The only rigorous independent benchmark on **real** Devanagari scans found a
76-point spread that synthetic tests completely hide: Gemini 2.5 Flash 86.3,
Claude Opus 4.7 82.2, EasyOCR 58.3 (down from 93.6 on synthetic), olmOCR 40.5.
**Synthetic benchmarks massively overstate real-world Indic OCR.**

A study on ~60 real scanned Marathi legal documents with handwriting, stamps and
seals concluded current systems **lack the precision needed for legal-grade work.**

Practical consequences:
- **AWS Textract does not support Devanagari at all** — the Mumbai region does not
  help.
- **Azure Document Intelligence** is the best of the big three for Devanagari and
  has a genuine on-prem path, gated at **100k pages/month on a 1-year commitment.**
- Cost is **not** the blocker: $0.05–$0.50 per document all-in including VLM
  fallback and human QA.
- **No published OCR benchmark exists for genuinely scanned Indian legal paper.**
  Existing Indian legal NLP corpora all work from already-extractable text. That
  gap is an opportunity, not just a hole.

## Distribution and integration

- **Word add-in, admin-deployed, is the fastest path to a user.** Microsoft 365
  Admin Center deployment requires **no AppSource review, no Partner Center
  enrolment, no public listing.**
- **iManage/NetDocuments in India is a top-20-firm play** — a connector-first
  strategy targets almost nobody. The Indian substrate is M365/SharePoint, plus
  PracticeLeague (independently reported across major Indian corporate firms) and
  Provakil (named large-corporate in-house customers including manufacturers).
- **Bloomberg Law has no verifiable India presence.** No incumbent to displace —
  and no proof of demand either.
- **The adoption blocker is workflow fit and IT friction, not price and not a
  confidentiality veto** — top Indian firms already send client-matter data to
  Harvey, a US cloud vendor.

## Competitive evidence — the staleness problem, live

Checked 2026-09-09, nine months after G.S.R. 880(E):

| Site | Shows | Status |
|---|---|---|
| Vakilsearch ("FY 2026 Guide") | ₹4cr/₹40cr, "in effect since 15 September 2022" | STALE |
| IndiaFilings | internally contradictory on one page | STALE |
| PatronAccounting | ₹4cr/₹40cr | STALE |
| IncorpX (dated 2026) | ₹20cr/₹200cr | **fabricated — neither figure** |
| TaxGuru | one stale article and one correct, both live | MIXED |
| ca2013.com (CAIRR) | correct, with dated citations — **inside a hover tooltip** | CORRECT, unsurfaced |

**No product found on the Indian market sells point-in-time statutory correctness
as a feature.** And the Supreme Court ruled in 2026 that citing AI-hallucinated
authority is professional misconduct.

## Open questions

- Whether any vendor holds a real MCA data-sharing agreement — **UNVERIFIED**, and
  worth one direct email each.
- Pre-2021 NCLT archive format — **UNVERIFIED**.
- Indian Kanoon's terms on building a competing product — the attribution clause
  was read; competitive-use was not addressed. Needs a lawyer's eye before
  committing engineering.
