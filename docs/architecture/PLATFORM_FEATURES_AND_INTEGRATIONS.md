# Placedon — features, integrations and the multi-agent design

Written 2026-10-02 against `main` at 8f4b60a. Companion to [ARCHITECTURE.md](ARCHITECTURE.md),
which holds the pipeline, data model, model gateway and build order; this document holds the
**feature list for Indian law users**, **every outside integration** (government, legal
publishers, MCP, CLI, API), **how a scanned document is verified**, **how Central and State law
are kept apart**, and **how agents run side by side**. Where this and the code disagree, the code
wins; fix this page.

Status words used throughout:

| Word | Meaning |
|---|---|
| BUILT | in `main`, behind tests |
| PARTIAL | some of it in `main`; the gap is named |
| TODO | designed here, not written |
| NEEDS PERMISSION | cannot be built until an outside body grants access; §8 lists who and how |
| NOT DOING | decided against, with the reason |
| OPEN / UNVERIFIED | we could not confirm it; "could not confirm" is not "does not exist" |

---

## 1. The feature list for Indian law users

How each feature is built (entry, flow, files, tables, gate, proof): [FEATURE_ARCHITECTURE.md](FEATURE_ARCHITECTURE.md).

Buyers in order: in-house legal teams, then law firms, then individual lawyers. Every feature
obeys one rule: **a model reads, extracts, labels and phrases; code decides law, dates and
authority; a lawyer signs off.** Anything not proven is NEEDS_LAWYER or a refusal that names
what is missing.

### 1.1 Ask and research

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F1 | **Assistant** | A chat that answers Indian corporate-law questions with the exact provision, amending instrument and operative date, or refuses by name | BUILT (`checker/ask.py`, conversations C2) |
| F2 | **Knowledge — multi-domain research** | One question fanned out across every body of law it touches (Companies Act, SEBI, FEMA, stamp duty, GST, labour, State Acts). Each body answers, refuses, or asks for a missing fact (e.g. "which State?") | PARTIAL: only Companies Act held; others refuse by name (`checker/scope.py`). Parallel fan-out is TODO (MA1, §7) |
| F3 | **Central/State resolver** | Every question is tagged Central, State or Concurrent before research; a State question without a State and a date is not answered | TODO (§3) |
| F4 | **Point-in-time law** | "What did Section 135 say on 1 April 2019?" | BUILT for Companies Act (`checker/as_of.py`); boundary-proved on three sections only |
| F5 | **Case law** | Judgments interpreting a provision, with pinpoint quotes | NEEDS PERMISSION (Indian Kanoon key; §5) |
| F6 | **Event map** | "We are allotting shares to a foreign investor" → which bodies of law it engages and which we hold | BUILT (`checker/events.py`, not lawyer-reviewed) |

### 1.2 Documents

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F7 | **Vault** | Upload 10–20k documents per matter; each hashed, classified, indexed, searchable | BUILT (local storage); S3/Textract TODO until AWS is ready |
| F8 | **Document Check — authenticity** | Is this file what it claims to be? Signature, certificate chain, tampering, issuer match, official-record match, each a separate line | PARTIAL: `checker/doc_verification.py` + `scripts/verify_document.py` (CCA chain, PKCS#7, byte ranges). Official-record checks NEEDS PERMISSION (§4) |
| F9 | **Document Check — validity and action** | Is it current, expired, due for renewal, superseded or revoked, and what to do: KEEP / RENEW by date / REPLACE / REMOVE | TODO (T3, §4.4) |
| F10 | **Document Review** | A corporate document (minutes, notice, resolution) checked against the rules for its type | BUILT (`agents/review_document.py`, `checker/ss/`) |
| F11 | **Classification** | What type of document this is, before any rule fires; unknown type gives uncertainty, never defects | BUILT (`agents/intake.py`, document classifier) |

### 1.3 Contract intelligence

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F12 | **Playbook review** | A contract checked against the company's own playbook: MATCHES / DEVIATES / MISSING / NEEDS_LAWYER, each with the quoted clause | BUILT (NDA playbook, DRAFT until a lawyer approves) |
| F13 | **Review tables** | Pick 2,000 contracts, define columns (party, term, renewal date, governing law, liability cap); each cell FOUND with a quote, NOT_FOUND, or NEEDS_LAWYER; CSV export | BUILT (H4: `checker/review_grid.py`) |
| F14 | **Obligations and renewal calendar** | Dates extracted from contracts (expiry, notice-to-terminate window, lock-in, renewal) turned into a calendar with reminders; the arithmetic is code (`DerivedDate`) | PARTIAL: compliance calendar BUILT; contract dates TODO |
| F15 | **Stamp-duty adequacy check** | Was this agreement stamped for the right amount in the right State? | NOT DOING until a State stamp pack is held (§3.4) |
| F16 | **Clause library and comparison** | "Show every limitation-of-liability clause across our vendor contracts and how they differ" | TODO (comparer agent, MA1) |

### 1.4 Drafting

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F17 | **Drafts with versions** | Memos, emails, board notes. Statements of law bind to verified claims; everything else is marked MODEL_SUGGESTION and blocks approval until a person accepts it | BUILT (H3) |
| F18 | **Templates** | Board resolutions, AGM notices from fixed templates | BUILT (`checker/draft_templates.py`) |
| F19 | **Word add-in** | Run a playbook inside Word; suggestions land as tracked changes | TODO (H5, frontend repo) |

### 1.5 Compliance and monitoring

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F20 | **Compliance calendar** | Statutory deadlines for a company, computed from facts the user supplies | BUILT |
| F21 | **Company facts** | CIN, status, directors, paid-up capital from the MCA master-data PDF the user uploads | BUILT (S2-alt); live lookup NEEDS PERMISSION |
| F22 | **Horizon scanning (Themis)** | A Gazette notification, SEBI circular or RBI direction arrives → which held provisions changed → **which past answers relied on them** (recall via `law_versions`) | PARTIAL: Themis on its own branch; `law_versions` on every run is T1 |

### 1.6 Work management

| # | Feature | What the user gets | Status |
|---|---|---|---|
| F23 | **Matters and users** | Matters, roles, per-matter access | BUILT (migrations 018, 019) |
| F24 | **Agents and workflows** | Saved multi-step jobs ("onboard a vendor": authenticate → extract → review → memo); a plan is shown before it runs | TODO (MA1, T5) |
| F25 | **Schedules** | Run a workflow every Monday; re-check all contracts when a law changes | TODO (T6) |
| F26 | **Spaces** | A shared room with outside counsel or a counterparty: chosen documents and answers only, guest roles, everything audited | TODO (T8) |
| F27 | **Command Center** | Volumes, turnaround, refusals, spend, open NEEDS_LAWYER items — aggregates only, never ranking individual people | TODO (T7) |

### 1.7 Integration surfaces

| # | Feature | Status |
|---|---|---|
| F28 | REST API `/v1` (engine) and `/v2` (gateway verbs) | BUILT |
| F29 | MCP server — Placedon inside Claude, ChatGPT, Copilot | BUILT (read-only tools, `checker/mcp/`) |
| F30 | CLI generated from the same verb table | BUILT (`gateway/verbs.py`) |
| F31 | Connectors — SharePoint, OneDrive, Google Drive, Outlook/Gmail | TODO (customer OAuth consent) |
| F32 | Licensed legal databases (§5) | NEEDS PERMISSION, per publisher |
| F33 | Webhooks out (run finished, law changed) | TODO |

---

## 2. How the whole system fits together

```
 USERS                     SURFACES                         ORCHESTRATION                     KNOWLEDGE
 ─────                     ────────                         ─────────────                     ─────────
 in-house lawyer ─┐        Web app (Next.js)  ─┐
 law firm        ─┼──────► Word add-in         ├─► gateway/ (auth, tenant, RLS, ─► agents/ ─► checker/ (R0 law core)
 other AI tools  ─┘        MCP server  ────────┤   budget, audit)                   intake      scope, as_of, obligations
 (Claude/ChatGPT)          CLI / REST API ─────┘        │                           plan        verification (byte-exact)
                                                        ▼                           supervisor  ─────────────
                                               durable queue (Postgres SKIP LOCKED)   workers    sources/ (R2, tiered)
                                               worker processes, priority lanes       critic       HELD corpus
                                                        │                             synthesis    OFFICIAL_LIVE (Gazette, SEBI…)
                                                        ▼                                          LICENSED (Indian Kanoon, SCC…)
                                               model gateway (router.py)                           CLIENT (vault, connectors)
                                               India-region for client data                        WEB (facts only)
                                               budget caps, UNPRICED never ₹0
                                                        │
                                                        ▼
                                               answer envelope + law_versions ─► human gate ─► VERIFIED
                                                                                       │
                                               Themis (horizon scan) ◄── law change ───┘ recall past answers
```

Three facts make this one system rather than many:

1. **One verb table** (`gateway/verbs.py`) generates the REST routes, the MCP tools and the CLI.
   A new feature is one entry; all three surfaces get it, with a parity test.
2. **One source interface** (`checker/sources/`). Government sites, licensed publishers, the
   client's own documents and the web all return `Evidence` rows carrying a **tier**. Only HELD
   can make a statement of law VERIFIED. A new integration is a new source file plus a terms
   record; nothing downstream changes.
3. **One envelope.** Every answer, from any surface, has the same shape: status, cited sentences,
   refusals by name, `law_versions`, cost, trace id.

---

## 3. Central law and State law

### 3.1 Why this needs its own layer

India's Constitution splits legislative power in the Seventh Schedule into the Union List,
the State List and the Concurrent List. The same transaction can therefore be governed by a
Central Act and by a different rule in each State. The examples the product meets most often:

| Area | Who legislates | Effect on an answer |
|---|---|---|
| Stamp duty | Rates on a short list of instruments (e.g. share transfers, debentures, bills of exchange) are Central; rates on other instruments (leases, agreements, conveyances) are set by each State, many under their own Stamp Acts or State amendments to the Indian Stamp Act, 1899 | A lease stamped correctly in Karnataka may be under-stamped in Maharashtra. No answer without the State and the execution date |
| Indirect tax | GST is shared (CGST + SGST/IGST). Alcohol for human consumption and five petroleum products stay outside GST, so States levy VAT/sales tax on them at their own rates | A question about fuel or liquor cost is a State VAT question, not a GST one |
| Shops & Establishments | Each State has its own Act and rules | Registration, working hours and leave differ by State |
| Professional tax | Levied by States within a constitutional ceiling | Some States levy it, some do not |
| Labour codes | Central codes, but many operative details are in State rules | Central text alone is incomplete |
| Rent and land | State subject | Out of corporate scope; refused |

**These constitutional allocations are stated here to explain the design, not as answers.** Before
any rule uses them, the relevant entries of the Seventh Schedule and articles of the Constitution
are acquired, hashed and cited like any other held text (CLAUDE.md: never hand-type statute).

### 3.2 The jurisdiction resolver (F3)

```
question ─► intake extracts: subject, instrument type, State(s), date, parties
          ─► resolver (code, a table — not a model) maps subject → {CENTRAL | STATE | CONCURRENT}
          ─► CENTRAL      → the Central body in scope.py
             STATE        → needs State + date; missing → NEED_FACT("which State?") 
             CONCURRENT   → both, and the answer shows both side by side
          ─► each (body, State) pair is checked against scope.py: HELD / CURRENT_ONLY / DECLARED
```

The resolver table is a reviewed file like `checker/events.py`, with each row citing the
constitutional entry it rests on. A model may suggest which State a document belongs to (from
the address in it); code confirms it against the user's stated facts, and a mismatch is shown.

### 3.3 State packs

A **State pack** is one State's held law for one area, acquired like the Companies Act corpus:
official source → hash → cross-check → lawyer spot-check → HELD. Contents for stamp duty, for
example: the State's Stamp Act or amendments, its schedule of rates with every amending
notification and operative date, and its e-stamping rules.

Order of acquisition: **one State per paying pilot**, chosen by where the pilot's contracts are
executed. Which States in-house teams cluster in is a hypothesis to test in pilot interviews,
not a fact we hold.

### 3.4 What happens today

Every State body is DECLARED in `checker/scope.py` (stamp duty is listed there). A State question
gets: the body of law, what it covers, which State, and "not held — answer refused". Never a
guess from Central text.

---

## 4. Document verification — scan a document, and what is checked

### 4.1 The principle (already in code)

`checker/doc_verification.py` refuses to say "real" or "fake". A file can be cryptographically
perfect and a forgery of something never issued, or genuinely issued and broken by a re-save.
So verification returns **separate dimensions**, and the overall status is COMPLETE only when
every dimension that matters was actually established. Otherwise it is INCOMPLETE_VERIFICATION —
a statement about our knowledge, not about the document.

### 4.2 The flow when a user scans or uploads a document

```
upload / scan / connector
  │
  ▼ 1. INTAKE         sha256, page count, file type, OCR (Textract, India region) if scanned
  ▼ 2. CLASSIFY       document type (e-stamp, board resolution, NDA, GST certificate, DSC-signed filing…)
  ▼ 3. EXTRACT        model reads: issuer, certificate no., dates, parties, CIN/GSTIN/DIN, amounts
  │                   every extracted value carries its character span in the file
  ▼ 4. VERIFY (code, in parallel — one worker per dimension)
  │     ├─ file integrity        byte ranges hash as signed                         BUILT
  │     ├─ signature             PKCS#7 verifies                                    BUILT
  │     ├─ certificate chain     chains to CCA India root (RCAI)                    BUILT
  │     ├─ validity at signing   certificate in date when it signed                 BUILT
  │     ├─ revocation            CRL of the issuing CA (checker/revocation.py);     PARTIAL
  │     │                        unreachable CRL → UNKNOWN, never VALID; OCSP TODO
  │     ├─ trusted timestamp     RFC 3161 token, not the signer's own clock         BUILT (reads it)
  │     ├─ issuer identity       issuing CA is CCA-licensed                         BUILT
  │     ├─ official record match the issuer's own register says this exists         NEEDS PERMISSION (§4.3)
  │     ├─ party match           CIN/GSTIN in the document = the company it claims  PARTIAL (uploaded MCA PDF)
  │     └─ injection scan        instructions in extracted text flagged, kept       PARTIAL
  │                              (text only; instructions printed in a scanned image are an open gap — CLAUDE.md)
  ▼ 5. VALIDITY (code)   CURRENT / EXPIRES_ON date / EXPIRED / SUPERSEDED / REVOKED / NOT_DETERMINED
  ▼ 6. ACTION (code)     KEEP / RENEW_BY date / REPLACE / REMOVE / NEEDS_LAWYER — each with its reason
  ▼ 7. ENVELOPE          every line: dimension, result, evidence, source, checked-at time
  ▼ 8. LAWYER            confirms or overrides; override reason stored
```

Steps 5 and 6 are rules over extracted dates, never a model's opinion. A validity rule that rests
on law (e.g. how long a particular certificate or registration lasts, when an instrument must be
renewed or re-stamped) fires only when that law is HELD; otherwise the line says NOT_DETERMINED
and names the law missing.

### 4.3 The official record checks, document by document

"Verify from the portal" means asking the body that issued the document whether it exists. Each
issuer is a separate integration with its own access conditions.

| Document | Who issued it | How it can be checked | Access route for us | Status |
|---|---|---|---|---|
| Digitally signed PDF (DSC) | Licensed Certifying Authority under CCA | Certificate chain to Root CA of India; CA's CRL/OCSP | Public: root certificates and CRLs are published by CCA | BUILT; revocation PARTIAL (CRL only) |
| Aadhaar eSign signature | eSign Service Provider (a licensed CA) | Same chain check; the signature carries the ESP certificate | Public chain check. **Becoming** an eSign signer (ASP) needs empanelment with an ESP — only if we ever collect signatures | Chain BUILT; ASP NOT DOING |
| e-Stamp certificate | Stock Holding Corporation of India (SHCIL) as Central Record-Keeping Agency, for most States | SHCIL's "Verify e-Stamp" page: State, certificate number, issue date, session/unique id | No official public API found (UNVERIFIED either way). Options: the user verifies on SHCIL and uploads the result page; or a licensed aggregator API under contract; or a written request to SHCIL | NEEDS PERMISSION |
| Documents in DigiLocker (issued certificates) | The issuing department, via DigiLocker | DigiLocker returns the issuer's own copy | Register as a **Requester** on API Setu; each fetch needs the citizen's consent. Eligibility of a private company is OPEN — confirm with API Setu | NEEDS PERMISSION |
| Company (CIN, status, directors) | MCA / Registrar of Companies | MCA master data | MCA has no public API and its site is WAF-protected — **never scraped**. Routes: user-uploaded master-data PDF (BUILT); OGD dataset on data.gov.in (free key, GODL licence); licensed aggregators | PARTIAL |
| Director (DIN) | MCA | DIN status on MCA master data | Same as above | PARTIAL |
| GST registration (GSTIN) | GSTN | Public taxpayer search: legal name, status (active/cancelled), registration date | Programmatic access is through a GST Suvidha Provider (GSP). Either become a GSP partner customer (ASP agreement) or use the public search manually | NEEDS PERMISSION |
| Listed-company disclosures | BSE / NSE | Exchange announcement archives | Read under each exchange's terms; terms not yet read | TODO |
| Court orders | High Courts, district courts (eCourts) | CNR number on eCourts | eCourts is **not** on CLAUDE.md's permitted-source list; adding it is a separate decision. Third-party eCourts APIs exist (UNVERIFIED quality) | NOT DOING (until decided) |
| Insolvency status | IBBI / NCLT | IBBI public announcements | Read IBBI public pages | TODO (Themis feed) |
| PAN | Income Tax Department / Protean | PAN verification service | Restricted to eligible entities under the department's rules; eligibility OPEN | NEEDS PERMISSION |
| Aadhaar number itself | UIDAI | — | **NOT DOING.** We never collect, store or verify Aadhaar numbers | NOT DOING |

Every row above becomes one file in `checker/sources/` (or `checker/verifiers/`) with a terms
record. No terms record, no fetch. A 200 response carrying HTML where JSON or a PDF was expected
is an error, never an empty result (the India Code soft-404 lesson in CLAUDE.md).

### 4.4 Validity and action rules (F9)

| Situation (computed) | Action | Basis shown |
|---|---|---|
| Signature valid, all record checks done, expiry date in the future | KEEP, with the expiry on the calendar | Each dimension line |
| Expiry within the renewal window the user's policy sets (e.g. 60 days) | RENEW_BY date | The extracted date + the policy |
| Expired | REPLACE (if still needed) or REMOVE (if the matter is closed) | Extracted date; matter status |
| Superseded by a later version in the vault | REMOVE old from active set, keep archived | Both document hashes |
| Certificate revoked, or official record says it does not exist | NEEDS_LAWYER, flagged as POTENTIAL_ISSUE | The issuer's response, stored verbatim |
| Any dimension NOT_CHECKED | No KEEP; INCOMPLETE_VERIFICATION | Which dimension and why |

"Renewal window" is a **company policy**, entered by the customer, not law. Where law sets a
period, the rule waits for that law to be held.

---

## 5. Legal publishers and databases

### 5.1 What we found (checked 2026-10-02)

| Provider | Country / content | Developer access found | Relationship with other legal-AI platforms | Our route |
|---|---|---|---|---|
| **Indian Kanoon** | India: Supreme Court, High Courts, tribunals | Paid API with public pricing; public-private key auth; attribution and logo required; terms page exists (our fetch was blocked — read it before code depends on it) | Open to any API customer | **First integration.** Tier LICENSED. Key pending (user) |
| **SCC Online** (EBC) | India: judgments, journals, statutes | No public developer API found (UNVERIFIED) | Partnered with Harvey to make SCC content a knowledge source inside Harvey | Enterprise request letter; or **bring-your-own-licence** (§5.3) |
| **Manupatra** | India: judgments, statutes, journals | No public developer API found (UNVERIFIED) | Announced Jan 2026 an **exclusive** partnership with Legora: "the only legal AI platform" with Manupatra content | Likely unavailable while exclusivity holds; ask, do not plan on it |
| **LexisNexis** (Lexis India, Protégé) | Global; India content via Lexis India | **Protégé API** exists; LexisNexis has published an evaluation of MCP-based legal workflows; May 2026 integrated Anthropic's Claude legal plugins into Protégé | Own platform | Licensed customer route only; India content scope UNVERIFIED |
| **Thomson Reuters** (Westlaw, CoCounsel) | Mostly US/UK/CA/AU | **CoCounsel Legal MCP** server, usable from Claude (Aug 2026) | Built on Anthropic's Agent SDK | US-centric content; out of our India-only data rule for answers. Could be a customer's own MCP alongside ours |
| **Wolters Kluwer** (CCH India) | Tax and accounting in India | No developer API found (UNVERIFIED) | — | Ask; relevant once GST/income-tax bodies are in scope |
| **Taxmann**, **CaseMine**, **EBC Reader** | India | Not checked | — | Later; same pattern |
| Gyldendal Rettsdata | Norway | — | — | **NOT DOING** — not Indian law (owner decision 2026-09-30: Indian sources only) |
| FromCounsel | UK practice content | — | — | NOT DOING (same reason) |
| Otto Schmidt | Germany | — | — | NOT DOING |
| Lefebvre | France / Spain | — | — | NOT DOING |
| Tirant lo Blanch | Spain / Latin America | — | — | NOT DOING |

The foreign publishers would matter only for cross-border work, which is refused by name today
and revisited when a paying Indian client needs it.

### 5.2 The three ways a publisher can connect

```
 A. API connector (ours)        B. Their MCP server            C. Our MCP inside their platform
 ───────────────────────        ───────────────────            ────────────────────────────────
 checker/sources/<pub>.py       researcher agent calls         their assistant calls
 + terms.py record              their MCP as a client          themis.ask / themis.search_law
 → Evidence rows, tier          → Evidence rows, tier          → our envelope inside their UI
   LICENSED                       LICENSED
 we control caching,            they control the tool;         they control the UI;
 quoting, cost                  we still verify quotes         our refusals still travel
```

All three end at the same verifier. A licensed judgment can **support** an answer as cited
authority with a byte-matched quote; it can never make a statement VERIFIED on its own, because
VERIFIED requires HELD statutory text plus lawyer sign-off. That rule is in `checker/sources/tiers.py`
and is tested.

### 5.3 Bring-your-own-licence (BYOL)

Most firms already pay for SCC Online or Manupatra. Reselling that content needs a distribution
deal we do not have. BYOL means: the customer connects **their own** subscription (credentials or
OAuth stored per tenant in Secrets Manager), queries run under their licence, and results are
cached only as the publisher's terms allow. This is the realistic route to Indian publisher
content before any partnership exists. Whether each publisher's terms permit programmatic use
under a user licence is OPEN, per publisher.

---

## 6. API, MCP and CLI — the full list

### 6.1 Placedon's own surfaces (one verb table → three surfaces)

| Verb (REST `/v2/...`) | MCP tool | CLI | What it does | Status |
|---|---|---|---|---|
| `ask` | `themis.ask` | `placedon ask` | One question, cited answer or refusal | BUILT |
| `review-contract` | `themis.review_contract` | `placedon review-contract` | Playbook review | BUILT |
| `review-document` | `themis.review_document` | `placedon review-document` | Corporate document rules | BUILT |
| `events.assess` | `themis.events.assess` | `placedon events-assess` | Which bodies an event engages | BUILT |
| `runs/{id}`, `runs/{id}/trace` | `themis.runs.get`, `.trace` | `placedon runs-get`, `runs-trace` | Result and step trace | BUILT |
| `sources.list`, `sources.search` | `themis.sources.*` | `placedon sources-search` | What sources exist; search with tiers | BUILT |
| `documents/upload` | — (write) | `placedon documents-upload` | Into the vault | BUILT |
| `review_table.create/status/export` | `status/export` only | `placedon review-table-create` etc. | Review tables | BUILT |
| `draft.create/revise/versions/diff/export` | read verbs only | `placedon draft-create` etc. | Drafts | BUILT |
| `vault.verify` | — (`mcp=False`) | `placedon vault-verify` | Authenticity dimensions for a vault document | BUILT |
| `document.verify` | `themis.document.verify` | `placedon document-verify` | Adds validity + action (§4.4) to the dimensions | TODO (T3) |
| `research.multi` | read result only | `placedon research-multi` | Parallel multi-agent research | TODO (MA1) |
| `runs.preview/approve/cancel` | preview only | `placedon runs-preview` | See the agent plan before it runs | TODO |
| `workflow.save/run`, `schedule.create` | — (write) | `placedon workflow-save` etc. | Saved workflows, schedules | TODO (T5/T6) |
| `space.create/invite/share` | — (write) | `placedon space-create` etc. | Spaces | TODO (T8) |
| `ops.summary` | — | `placedon ops-summary` | Command Center numbers | TODO (T7) |

CLI names are generated, not chosen: `gateway/verbs.py:cli_command` turns `runs.get` into
`placedon runs-get`, and each field becomes a `--flag`. Rules: write verbs never appear on MCP (`mcp_tools()` refuses to generate them); some read verbs
are also off MCP on purpose (client lists, matters). Every call is audited with tenant, user,
verb and cost, never document text.

### 6.2 MCP servers and clients we connect to

| MCP | Direction | Purpose | Status |
|---|---|---|---|
| Placedon MCP (`checker/mcp/`) | We serve | Placedon inside Claude, ChatGPT, Copilot, other agents | BUILT (gateway key today; OAuth per user TODO, PLAN_22 D7) |
| Microsoft 365 / SharePoint (Graph) | We call | Pull contracts from SharePoint/OneDrive; Outlook attachments | TODO; customer Entra app consent |
| Google Drive | We call | Same | TODO; customer OAuth |
| iManage / NetDocuments | We call | DMS sync | TODO; partner access UNVERIFIED |
| Publisher MCP servers (e.g. CoCounsel Legal MCP) | We call, if the customer licenses them | Extra authority, tier LICENSED | Later; India content limited |
| Agent-to-agent protocol (A2A) | Either | Agent discovery across vendors | NOT DOING now: MCP covers our needs; revisit if a customer's agent platform requires A2A |

### 6.3 Outside APIs (full catalogue in ARCHITECTURE §17)

- **Models:** AWS Bedrock (Claude Haiku/Sonnet, Llama 3 70B) in ap-south-1; self-hosted open
  models on an AWS GPU per run; Sarvam for Indian scripts if India hosting is confirmed in writing;
  free tiers (Gemini, OpenRouter, Mistral) for public and synthetic data only.
- **Documents:** AWS Textract (Mumbai) for OCR.
- **Government:** India Code REST (open), e-Gazette, data.gov.in OGD, SEBI, RBI (read only,
  never cached), IBBI, CCA root certificates and CRLs; with permission: SHCIL e-stamp,
  DigiLocker (API Setu Requester), GSTN via a GSP, PAN via the authorised service.
- **Publishers:** Indian Kanoon first; SCC Online and others by request or BYOL.
- **Infrastructure:** S3, SES, Secrets Manager, Budgets (all Mumbai).

---

## 7. Agents that run side by side

### 7.1 What the research says

| Source | Finding | What we take from it |
|---|---|---|
| Anthropic, *How we built our multi-agent research system* (June 2025) | Lead agent plans and spawns 3–5 subagents in parallel, then a separate citation pass; beat a single agent by 90.2% on their internal research eval; about **15× the tokens** of a chat | Parallel workers suit **breadth-first** work (many documents, many bodies of law). Use only where the value justifies 15× cost |
| Anthropic, *Building effective agents* (Dec 2024) | Prefer simple workflows: prompt chaining, routing, **parallelization** (sectioning and voting), **orchestrator-workers**, evaluator-optimizer; agents only when steps cannot be fixed in advance | Most of our features are fixed workflows; the supervisor is used only for open-ended research |
| Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST, NeurIPS 2025) | 14 failure modes in 3 groups — specification, inter-agent misalignment, task verification — from 1,600+ traces; failures come mostly from **system design**, not the model | Typed specs per agent, typed messages (no free chat), verification after every worker |
| Cognition, *Don't Build Multi-Agents* (2025) | Splitting context across agents causes conflicting decisions; share full context, keep **decisions single-threaded** | Workers **read** in parallel; **one** writer decides and synthesises; workers never decide law |
| Agent2Agent protocol (Google, donated to Linux Foundation 2025) | Standard for agents of different vendors to discover each other and hand off tasks | Not needed now; MCP covers tool access |

### 7.2 Our design: parallel readers, one writer, code in charge

```
                      ┌──────────────── SUPERVISOR (Sonnet) ────────────────┐
 user request ───────►│ proposes a plan: which registry agents, on what      │
                      │ inputs, in which order, with what budget             │
                      └───────────────┬──────────────────────────────────────┘
                                      ▼
                      PLAN VALIDATOR (code, not a model)
                        · registry agents only · ≤ 8 agents · depth 1 (no agent spawns agents)
                        · budget ₹ and time cap · data class allowed for each model
                        · shown to the lawyer as a preview before it runs
                                      ▼
            ┌──────────── QUEUE (Postgres SKIP LOCKED, priority lanes) ────────────┐
            ▼                  ▼                  ▼                 ▼               ▼
      researcher(CA)    researcher(SEBI)    researcher(State:MH)  doc_auth ×N   extractor ×N    ← run side by side
            │                  │                  │                 │               │
            ▼                  ▼                  ▼                 ▼               ▼
      VERIFY each result before anyone else can use it: exact quote byte-match, tier check, scope check
            │                  │                  │                 │               │
            └──────────────────┴────────► BLACKBOARD (typed rows, not chat) ◄────────┘
                                                  ▼
                                   comparer / critic (flag or remove only, never add)
                                                  ▼
                                   SYNTHESIS — single writer: code assembles verified rows;
                                   the drafter model only phrases them; unverified → NEEDS_LAWYER
                                                  ▼
                                   envelope + law_versions + per-agent cost and trace
```

**Agent registry** (each is a typed spec: inputs, outputs, allowed models, data class, max cost):

| Agent | Reads | Writes to blackboard | Model |
|---|---|---|---|
| supervisor | the request, registry | a plan (validated by code) | Sonnet |
| researcher | one body of law (+ State) | provisions with quotes, or a named refusal | Haiku → Sonnet on rejection |
| doc_auth | one document | verification dimensions (§4) | mostly code; Haiku for extraction |
| extractor | one document | fields with character spans | Haiku |
| comparer | extracted rows | deviations against playbook | code + Haiku |
| case_law | LICENSED source | judgments with pinpoint quotes, tier LICENSED | Haiku |
| critic | blackboard | flags / removals with reasons | Sonnet |
| drafter | verified rows only | prose, marked where it is suggestion | Haiku |
| watcher (Themis) | law change feeds | affected provisions → affected past runs | code |

**Stop conditions:** budget reached → PAUSED_BUDGET (a state, not an error); time cap; two
consecutive verifier rejections on a worker → that branch becomes NEEDS_LAWYER; a worker
failure retries 3 times then dead-letters, and the run completes as PARTIAL naming the gap.

**When we do *not* use multiple agents:** a single question about one held provision; one
contract against one playbook. A single pipeline is cheaper and has fewer failure modes.

### 7.3 Example: one question, several bodies, side by side

*"We are signing 5-year office leases in Bengaluru and Mumbai and allotting shares to a Singapore
investor next month. What do we need to do?"*

1. Intake → MULTI_AGENT; facts: lease (Karnataka, Maharashtra), allotment, foreign investor, date.
2. Resolver: Companies Act (Central, HELD); FEMA/FDI (Central, DECLARED); stamp duty on leases
   (State, KA + MH, DECLARED); stamp duty on share issue (check which list applies — resolver
   table row); registration of leases (Central Act, not in scope → refused by name).
3. Supervisor plans 4 researchers in parallel + 1 critic; validator approves; lawyer sees preview
   with estimated cost.
4. Results: Companies Act researcher returns the allotment provisions with quotes (VERIFIED path);
   FEMA researcher returns NOT_HELD by name; two stamp researchers each return NOT_HELD for their
   State.
5. Synthesis: a PARTIAL answer with one verified section and three named gaps, each saying what
   would have to be acquired. Nothing is guessed from Central text.

---

## 8. Permissions you (the owner) need to obtain

Ordered by value to the first pilots. None of these can be done by an agent: each needs a
person, an account and acceptance of terms.

| # | What | From | Why | Cost (as found) | Status |
|---|---|---|---|---|---|
| P1 | Indian Kanoon API account | Indian Kanoon | Case law (F5) | Prepaid per request; free credit on sign-up; non-commercial plan after verification | User to do |
| P2 | data.gov.in API key | Open Government Data platform | MCA company master data where published | Free; GODL attribution | User to do |
| P3 | AWS account ready (IAM user, Bedrock access in Mumbai, budgets) | AWS | Models, OCR, hosting | Credits, then card | User to do |
| P4 | API Setu / DigiLocker Requester | MeitY (API Setu) | Official copies of issued documents, with citizen consent | OPEN | Ask eligibility |
| P5 | GSP access for GSTN public APIs | A licensed GST Suvidha Provider | GSTIN status checks | Commercial; varies | Ask quotes |
| P6 | SHCIL e-stamp verification access | SHCIL | e-Stamp record match | OPEN — no public API found | Write to SHCIL |
| P7 | SCC Online enterprise / BYOL terms | EBC | Indian case law and journals | OPEN | Write to EBC |
| P8 | Manupatra | Manupatra | Same | Exclusive with Legora (Jan 2026) | Ask; do not plan on it |
| P9 | Exchange data terms | BSE, NSE | Listed-company disclosures | Read terms | TODO |
| P10 | Microsoft Entra app registration | Microsoft (and each customer's admin) | SharePoint / Outlook connectors | Free to register | When a pilot asks |
| P11 | Counsel opinion on processing client documents | A lawyer | Our own data-protection position | Fee | Before the first live client document |

Never: scraping MCA or any WAF-protected site, using someone else's login, collecting Aadhaar
numbers, or storing a publisher's content beyond its terms.

---

## 9. Build order for this document

Continues ARCHITECTURE §16 (P2 → A1 → R0 → G1 → T1 → T2 → T3 → MA1 → …).

| Step | Delivers | Depends on |
|---|---|---|
| T3a | `document.verify` verb: existing dimensions + validity + action rules (§4.4), company-policy renewal window | T1 |
| T3b | OCSP alongside the existing CRL check, for CCA-licensed CAs | T3a |
| J1 | Jurisdiction resolver table + NEED_FACT("which State?") | R0 |
| MA1 | Supervisor, registry, plan validator, parallel researchers, blackboard, synthesis | T1, A1 |
| L1 | Indian Kanoon connector (tier LICENSED) | P1 key, terms read |
| C1x | Contract dates → obligations calendar (F14) | T3a |
| G2 | Official-record verifiers, one per permission as each arrives (P4–P6) | permissions |
| SP1 | First State pack (stamp duty, one State) | a paying pilot in that State |
| B1 | BYOL publisher connector framework | P7 answer |

---

## 10. Sources consulted (2026-10-02)

Research and engineering:
- Anthropic, How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic, Building effective agents — https://www.anthropic.com/research/building-effective-agents
- Cemri et al., Why Do Multi-Agent LLM Systems Fail? (MAST) — https://arxiv.org/abs/2503.13657
- Cognition, Don't Build Multi-Agents — https://cognition.ai/blog/dont-build-multi-agents
- LangChain, How and when to build multi-agent systems — https://blog.langchain.com/how-and-when-to-build-multi-agent-systems
- Agent2Agent protocol overview — https://tyk.io/learning-center/what-is-the-a2a-agent2agent-protocol/

Legal publishers:
- Harvey × SCC Online partnership — https://www.harvey.ai/blog/harvey-partners-with-scc-online
- Legora × Manupatra exclusive partnership — https://legora.com/newsroom/legora-and-manupatra-announce-exclusive-partnership
- LexisNexis Protégé API — https://www.lexisnexis.com/API ; MCP evaluation — https://www.lexisnexis.com/community/amp-pressroom/what-we-learned-from-evaluating-mcp-based-workflows-for-authoritative-legal-ai ; Claude legal plugins in Protégé — https://www.lexisnexis.com/community/pressroom/b/news/posts/lexisnexis-expands-lexis-with-protege-by-integrating-anthropics-claude-legal-plugin-suite
- Thomson Reuters CoCounsel next generation and MCP — https://www.lawnext.com/2026/06/thomson-reuters-opens-early-access-to-the-next-generation-of-cocounsel-legal-saying-beta-users-fing-loved-the-product.html
- Indian Kanoon API terms — https://api.indiankanoon.org/terms/ (not read in full: fetch blocked from this environment)

Government and verification:
- DigiLocker / API Setu requester specification — https://cf-media.api-setu.in/resources/Requester-APISpecification-V1_12.pdf
- CCA eSign empanelment guidelines — https://www.cca.gov.in/sites/files/pdf/esign/CCA-ESP.pdf ; Root CA of India — https://cca.gov.in/rcai.html
- GST public taxpayer search via GSPs — https://www.ginesys.in/blog/gst-public-api-empowering-taxpayers-real-time-compliance-and-data-accuracy (secondary)
- SHCIL e-stamp verification process — https://www.sansalegal.com/post/how-to-obtain-an-e-stamp-certificate-in-india-shcil-portal-process-and-verification (secondary)
- MCA master data public view — https://cleartax.in/s/what-is-mca21-portal (secondary)
- eCourts services — https://en.vikaspedia.in/viewcontent/e-governance/online-legal-services/how-to-check-court-case-status-online-in-india-a-complete-guide-to-ecourts-cnr-number-case-number-and-case-history?lgn=en

Secondary sources are marked so. Each must be replaced by the issuer's own page or written
confirmation before code depends on it.
