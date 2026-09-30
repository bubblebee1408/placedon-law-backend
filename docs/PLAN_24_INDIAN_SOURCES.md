# PLAN 24 — Indian sources: case law, company records, regulators, and what "real time" means

2026-09-30 · extends `.claude/loops/DECISION_harvey_parity.md` (steps H1 and H1b) · India-only by
owner decision. No US or other foreign legal data enters the product.

## 1. What an Indian in-house lawyer asks for, and which source answers it

| Need | Example question | Source | What the source may do |
|---|---|---|---|
| The provision, on a date | "What did Section 62 say on 1 April 2017?" | Our corpus (`corpus/companies_act/`) | **Verify law.** The only tier that can |
| Cases on a provision | "Which NCLT orders discuss Section 62(1)(c) valuations?" | Indian Kanoon API | **Find cases.** A judgment is shown as found and quoted, never as verified law |
| Facts about a company | "Is [company] listed? Where is its registered office?" | MCA company master data on the Open Government Data platform | **Company facts**, attributed, confirmed by the user before use |
| What a listed company disclosed | "What did [company] announce about the allotment?" | BSE / NSE announcements | **Company facts** (a disclosure is the company's statement, not law) |
| What a regulator issued | "Is there a SEBI circular on this?" | SEBI circulars and orders, RBI notifications and master directions | **Current text** until the individual notifications are held (a consolidation has no history) |
| Whether the law changed | "Did anything amend Section 62 this year?" | e-Gazette, SEBI, RBI | Found here on request. **Watching** for changes is Project Themis's job |

## 2. The rule every source obeys

Each result carries a **tier**, set by the connector's code, never by a model:

| Tier | Sources | Can it make an answer VERIFIED? | Label the user sees |
|---|---|---|---|
| `HELD` | our hash-stamped corpus | **Yes**, the only one | Verified |
| `OFFICIAL_LIVE` | e-Gazette, India Code, MCA, SEBI, RBI fetched now | No, until ingested and checked | Official, read on [date] |
| `LICENSED` | Indian Kanoon | No | Found in case law · Powered by IKanoon |
| `COMPANY_FACT` | MCA open data, BSE/NSE disclosures | No; facts only, and the user confirms | Company record, [source], [date] |
| `CLIENT` | the tenant's own uploads and repositories | No; it is the document under review | Your document |

A connector that cannot state its tier does not load. A model never assigns a tier.

## 3. The source register: nothing is fetched on an unread term

`checker/sources/terms.py` holds one record per source: URL of the terms, the date read, the
exact clauses that govern caching, attribution, commercial use and rate limits, and the robots.txt
result for every path we fetch. **A connector refuses to load without its record.** Status as of
2026-09-30 (read from search results only; the cloud session's network could not reach the
sites, so the laptop session must fetch and quote each one itself):

| Source | Terms | Robots | Cost |
|---|---|---|---|
| Indian Kanoon API | Attribution required when results are shown to users, **including as RAG context**: "Powered by IKanoon". Caching clauses not yet read → OPEN | OPEN | Prepaid. ₹500 free on sign-up; search ≈ ₹5 per 100 results; full text +₹0.20 per record (https://api.indiankanoon.org/pricing/) |
| MCA data on data.gov.in | Government Open Data License – India: commercial and non-commercial use permitted with attribution (provider, source, licence, URL). **Personal data is exempt from the licence** → director names and DINs are not covered by it (https://www.data.gov.in/Godl) | OPEN | Free, API key |
| BSE / NSE announcements | OPEN | OPEN | OPEN |
| SEBI, RBI, e-Gazette | OPEN | OPEN | Free |
| eCourts, NCLT websites | **Not on CLAUDE.md's permitted list.** Separate owner decision; not in this plan | — | — |
| SCC Online, Manupatra | No public API found (INCONCLUSIVE, not "none exists") | — | Enterprise, ask the publishers |

Never bypass a WAF, a robots rule or an access control (CLAUDE.md). A blocked source is recorded
as blocked, not worked around.

## 4. Architecture

```
question / event ─► plan compiler ─► sources.search(query, tiers, as_of) ─► per-source connector
                                                                             │ terms record ✓
                                                                             │ robots ✓  TLS ✓
                                                                             │ Content-Type + magic bytes ✓
                                                                             ▼
                                                          Evidence{tier, source, url|doc_id, fetched_at,
                                                                   sha256, quoted_span, attribution}
                                                                             │
                                          stored once in source_documents (public, hashed)
                                                                             │
                              verifier: only HELD may support a legal claim; every other tier
                              needs a byte-matching quote and appears under its own label
```

- **Interface:** `Source.search(query, *, as_of) -> list[Evidence]` and `Source.fetch(ref) -> Document`.
- **Storage:** public material goes into one hash-stamped `source_documents` table, shared across
  tenants because it is public; caching follows each source's terms record. Client material stays in
  the tenant-scoped tables under FORCE RLS.
- **Untrusted text:** every system prompt that shows fetched text carries `UNTRUSTED_CLAUSE`;
  `wrap_untrusted()` only where text is concatenated into a prompt (`checker/prompt_safety.py`).
  An instruction found in a judgment or a disclosure is flagged and kept verbatim, never removed.
- **Cost:** every paid call is recorded in the same ledger as model calls (`backend/budget.py`),
  with its price source. A source without a recorded price is UNPRICED, never ₹0.
- **Freshness:** every Evidence says when it was read. "Real time" in this product means **read
  at the moment you ask**, with the time shown. Watching for changes is Project Themis's job; it
  hands this side a change event, and "What changed" consumes it.
- **Verbs:** `sources.list`, `sources.search` (read-only, so also MCP), through the one verb table.

## 5. Build order

| Step | Job | Done when |
|---|---|---|
| **S0** | Terms register: fetch and quote each source's terms and robots.txt; write `checker/sources/terms.py` | Every source in §3 has a dated record or is marked BLOCKED/OPEN; a connector without a record fails to load (test) |
| **S1** | Framework (H1): tiers, Evidence, interface, `source_documents` migration, `HELD` and `CLIENT` adapters, verbs | A non-HELD result can never make VERIFIED (test); every Evidence has hash, time and tier |
| **S2** | MCA company records (free, GODL): look up by CIN; feed `events.py` facts. The registered office State answers the stamp-duty question, **shown to the user to confirm, never applied silently**. Director personal data not stored | A CIN lookup fills `listed` and `state` as COMPANY_FACT with attribution; the user confirms before use |
| **S3** | Indian Kanoon (spend: start on the ₹500 free credit): search and fetch; paragraph quotes; "Powered by IKanoon" wherever a result or its text is shown | Attribution on every rendered result (test); cost recorded per call; a judgment never becomes VERIFIED |
| **S4** | SEBI, RBI and e-Gazette fetched on request; BSE/NSE announcements for listed companies, if their terms allow | Each fetch checks Content-Type and magic bytes; a 200 with HTML where a PDF was expected is an error |
| **S5** | Hand-off contract with Themis: the change-event schema "What changed" reads. Themis builds the watcher; this side only consumes | Schema agreed in a doc both branches reference; no Themis files edited here |

## 6. What we will measure, and what we won't claim

- Per source: fetch success, blocked responses, wrong-content-type responses, cost per query,
  time to read.
- Case search usefulness needs **human labels** (a lawyer marks whether each case was on point).
  Until there are enough, no relevance or accuracy figure is stated.

## 7. Decisions for the owner

1. Indian Kanoon spend: begin with the free ₹500 credit; any top-up is your call.
2. eCourts and NCLT sites: out until you decide to add them to the permitted list.
3. Director data (names, DINs): personal data, outside GODL. Recommendation: do not store it.
4. The DPDP question about our own processing of client documents remains OPEN for counsel.
