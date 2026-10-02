# Placedon — the architecture

The one document that describes the whole system: every product, every feature, how they share
data, how a request flows, how agents work, which models and sources are used, how it stays fast
and safe, and what is built versus still to build. Written 2026-10-02 against `main` at 9aeb5f3.
Where this document and the code disagree, the code wins; fix this document.
Rules every change obeys are in [../CLAUDE.md](../CLAUDE.md). Per-file index: [REPO_MAP.md](REPO_MAP.md).

---

## 1. What Placedon is

An evidence-backed legal work platform for Indian in-house legal teams. A lawyer asks, uploads or
delegates; Placedon returns work that is **cited to the exact source, verified in code, and
refused by name** when the law it would need is not held. A lawyer signs off before anything is
final.

Three rules hold everywhere:

1. **Models read, extract, label and phrase. Code decides** legal status, authority and dates.
2. **Client data stays in India.** The model gateway refuses any non-India provider for CLIENT data.
3. **Nothing unproven reaches the lawyer as fact.** It is verified, refused by name, or NEEDS_LAWYER.

## 2. Products

| Product | Buyer | Contains |
|---|---|---|
| **Placedon Team** | In-house legal team (50–500 staff companies) | Assistant, Vault, Document Check, Contract Review, Knowledge, Review Tables, Drafts, Agents, Compliance Calendar, Event Map, Command Center (ops) |
| **Placedon Enterprise** | Larger teams, firm ↔ in-house work | Team + Spaces (matter rooms with guests), saved workflows, scheduled runs |
| **Themis** | Teams that must know when the law moved | Horizon Scanning (Gazette/SEBI/RBI watch), Recall of past answers, state packs, legal-ops analytics |

Themis is a separate branch and plugs in through `law_versions` (§6). It never decides law.

## 3. System layout

### 3.1 Processes

| Process | Code | Owns | Scales by |
|---|---|---|---|
| API | `gateway/app.py`, `gateway/verbs.py` | auth, validation, enqueue, read results; never slow work | more instances |
| Worker | `gateway/worker.py` | executes queued jobs: ingest, OCR, extract, cells, agents, drafts | more workers |
| PostgreSQL | `gateway/migrations/` | all state: data, queue, ledger, audit | managed instance |
| File store | vault FileStore | raw file bytes, encrypted, per-tenant prefix | object storage |
| Model gateway | `checker/router.py` | every model call | stateless |

No state lives in process memory. Any API or worker process can die and the next continues from
Postgres.

### 3.2 One verb table, three surfaces

`gateway/verbs.py` declares every action once. REST, MCP tools and the CLI are generated from it,
with a parity test. Write verbs are never exposed on MCP.

### 3.3 Rings (the firewall)

`checker/rings.py`, enforced by an AST walk in the gate:
Ring 0 legal core (law, dates, deciders) · Ring 1 tenant and entity facts · Ring 2 feeds,
gateway, sources · Ring 3 agents, forecasting. Ring 0 may never import Ring 2 or 3: a
probability can never reach a legal decision.

## 4. The shared data model

Features never call each other. They read and write the same tables, scoped
`tenant_id → matter_id`, with FORCE row-level security on every tenant table.

```
tenant ─< user (role: admin | lawyer | viewer | guest)            018_users_roles
   └─< matter ─┬─< document ─< chunk (BM25, clause tags)          019_matters, 020_vault
               │      └── file bytes (sha256, per-tenant prefix)
               ├─< conversation ─< message ─> run                  010_conversations
               ├─< run ─< step ─< job (queue: lanes, attempts)     001–006
               │      ├─< citation (quote, sha256, provision, tier)
               │      └── law_versions {provision → sha256}        (T1: on every run)
               ├─< review_grid ─< cell ─> document                 011, 013
               ├─< draft ─< version ─> run                         012
               ├─< decision (approve/reject + reason) ─> run       → calibration labels
               └── company_profile → calendar items, event map
ledger (provider, region, tokens, ₹) ─> run | cell
audit (who, what, when — never document text)
answer_cache 014 · failure_category 015 · critic_enabled 016 · nonconformity 017
```

**How features compose through this model**

- Vault → Review Table: `vault.find(type=NDA, governing_law≠India)` returns document ids that
  become a table's rows.
- Any run → Draft: a draft is built from a finished run and may quote only that run's verified
  citations.
- Any run → Decision → Calibration: the lawyer's approve/reject is the label.
- Company profile → Calendar and Event Map: the same facts drive both.
- Run → law_versions → Themis Recall: when an instrument changes, every run that used it is listed.

## 5. The request pipeline

Every feature is a task on this one pipeline.

| Stage | What happens | Code |
|---|---|---|
| A Gateway | key/session → tenant, user, role; RLS set; size/rate/spend caps; audit row | `gateway/app.py`, `auth.py`, `audit.py`, `backend/budget.py` |
| B Files | upload → sha256 dedupe → text layer or OCR job → classify (rules first) → chunk + index | vault verbs |
| C Cache | same question + task + as_of + cited-law hashes → re-verify citations → serve | `checker/answer_cache.py` |
| D Intake | message + files → one of the fixed tasks; unclear → ask the user | `agents/intake.py` |
| E Scope | which bodies of law the task engages; unheld → named refusal | `checker/scope.py`, `events.py`, `claim_bodies.py` |
| F Plan | fixed step list for the task (or an agent plan validated by code, §8) | `agents/plans.py` |
| G Queue | each step a job; priority lanes; idempotent; crash-resumable; cancel = saga | `gateway/jobs.py`, `worker.py` |
| H Retrieve | BM25 over held law and the tenant's documents | `checker/text_search.py` |
| I Model | via the model gateway (§9): policy → budget → provider → call | `checker/router.py` |
| J Verify | byte-exact quote, law held, dates computed, schema | `quoted_span.py`, `ground_span.py`, `entailment_gate.py` |
| K Cascade | rejected → stronger model → rejected → NEEDS_LAWYER | `checker/model_cascade.py` |
| L Decompose | multi-part questions, at most 4 sub-questions | `checker/decompose.py` |
| M Critic | may FLAG or REMOVE a claim, never add | `checker/critic.py` |
| N Assemble | one answer envelope (§7) | `gateway/envelope.py` |
| O Record | ledger, failure category, nonconformity score, law_versions, cache | store |
| P Human | lawyer opens quotes, approves/rejects with a reason ≥10 chars | `runs.approve/reject` |

## 6. law_versions — the link to Themis

Every completed run records `{provision or instrument → sha256 of the exact text used}`. When
Themis observes a new Gazette instrument that touches a provision, it joins on this map and lists
every past answer that rested on the old text. Findings are never auto-edited; the lawyer re-runs.
Today law_versions is written on decisions only; job T1 writes it on every run and in the envelope.

## 7. The answer envelope

One versioned JSON schema (`gateway/schemas/answer_envelope.v1.json`) for every task:

```
{ status: ANSWERED | PARTIAL | NEEDS_LAWYER | ABSTAINED | NEEDS_CLARIFICATION | FAILED,
  task, as_of,
  text_blocks[{text, citation_ids[]}],
  bodies[{body_id, name, status: ANSWERED | NOT_HELD | CURRENT_ONLY | NEED_FACT | NOT_ENGAGED}],
  citations[{id, tier, instrument, provision, in_force_from, source, fetched_at, sha256, quote}],
  files[{file_id, name, state: READING | READ | CANNOT_READ, pages, reason}],
  law_versions, run_id, trace_url }
```

FAILED means transport only and is never shown as a refusal. Citation tier is set by code:
HELD · PLAYBOOK · CLIENT · OFFICIAL_LIVE · WEB; only HELD can verify law, WEB can never be
VERIFIED.

## 8. Agents (bounded multi-agent)

Multi-agent systems beat single agents on broad tasks and fail by mis-coordination, drift and
non-termination (MAST, 1,642 traces). Placedon's design keeps the first and blocks the second.

```
goal + files → SUPERVISOR plans using the registry only
            → code validates: registry agents only, ≤8 agents, depth 1, budget, time, data class
            → lawyer previews plan + estimated cost → starts
            → workers run as parallel queue jobs
            → each writes TYPED records to the run blackboard (no free-text agent chat)
            → every record verified in code before another agent may consume it
            → critic (flag/remove) → drafter (verified findings only) → nudges → lawyer
            → stop: complete | budget | timeout | all remaining NEEDS_LAWYER
```

| Agent | Job | Tools | Model tier |
|---|---|---|---|
| supervisor | plan from the registry | registry, caps | strong |
| doc_auth | real/signed/expired/stamped | signature checker, hashes | code first |
| extractor | clauses and values with exact quotes | vault read | small |
| comparer | clause vs playbook | playbook | code + small |
| researcher | held-law answers, named refusals | corpus search, sources | small → strong |
| summarizer | per-document/folder summaries, every line quoted | vault read | small |
| drafter | email/memo from verified findings | finished runs only | small |
| critic | flag/remove weak claims | read-only | strong |
| watcher (Themis) | law-change alerts and recall | Gazette feed | code |

Saved workflows ("custom agents") are a tenant-saved composition of registered agents and a
playbook; scheduled runs put the same composition on a timer. Simple questions keep the cheaper
single-workflow path.

## 9. Model gateway

One adapter interface (OpenAI-compatible) for every provider. Each call declares a **job**
(ocr, classify, extract, search, prose, critic) and a **data class** (PUBLIC, SYNTHETIC, CLIENT).

1. Policy gate: CLIENT → India-region providers only, refused by name otherwise.
2. Budget gate: worst-case cost reserved against global ₹3,500/month, per-tenant and per-user caps.
3. Choice: cheapest allowed provider that won the bake-off for that job; rate counters with fallback.
4. Call: keep-alive connection pool, timeout, retry on 429, circuit breaker.
5. Verify in code; cascade on rejection only.
6. Ledger: provider, region, tokens, ₹ (FREE_TIER, priced with provenance, or UNPRICED).

| Provider | Region | Allowed data | Use |
|---|---|---|---|
| AWS Bedrock: Claude Haiku / Sonnet, Llama 3 70B | ap-south-1 / India geography | CLIENT | main extract, prose, critic |
| AWS Textract | ap-south-1 | CLIENT | OCR, English handwriting |
| Sarvam | India if confirmed in writing | CLIENT only if confirmed | Indian scripts, Hindi handwriting |
| Self-hosted vLLM (open models) on AWS GPU | ap-south-1 | CLIENT if India | batch bake-offs, started and stopped per run |
| Azure Foundry Llama | UAE North | PUBLIC/SYNTHETIC | test backup |
| Gemini, OpenRouter free, Mistral free | foreign | PUBLIC/SYNTHETIC | development, comparison |
| Voyage | US | PUBLIC law only | semantic search bake-off |

No Google Cloud hosting. No local models. Search is BM25 unless a bake-off proves otherwise.

## 10. Features, one by one

The full feature list for Indian law users, every outside integration, document verification,
Central/State law and the parallel-agent design are in
[PLATFORM_FEATURES_AND_INTEGRATIONS.md](PLATFORM_FEATURES_AND_INTEGRATIONS.md).

Status: **BUILT** (on main, tested), **PARTIAL**, **TODO**.

| Feature | What the user does | Task / verbs | How it works | Status |
|---|---|---|---|---|
| Assistant | types a question, drops files | `conversation.send/list/get` | intake → task → pipeline → envelope; SSE streaming (TODO) | BUILT (streaming TODO) |
| Knowledge | asks a legal question | `RESEARCH_QUESTION`, `citation.get` | held corpus, BM25, cascade, named refusal, tiered citations | BUILT (tiers: T2) |
| Vault | uploads up to 20,000 files | `vault.upload/status/find/verify/summarize/research/compile/delete` | sha256 dedupe, OCR job, classifier, BM25 per tenant, CUAD clause tags | BUILT (S3/Textract BLOCKED until AWS) |
| Document Check | "is this real, signed, expired?" | `DOC_AUTHENTICATE` | integrity, hash, PKCS#7 + CCA chain, face date vs as_of, term expiry, stamp/execution, party match, injection flagged | TODO (T3) |
| Contract Review | reviews an NDA against the playbook | `REVIEW_CONTRACT`, `contract.playbook_review` | extract with quotes → code compare → MATCHES/DIFFERS/MISSING/NEEDS_LAWYER → sign-off | BUILT |
| Document Review | checks minutes/notices | `REVIEW_DOCUMENT` | SS-1/SS-2 checks, type-aware | BUILT |
| Review Tables | same questions across many documents | `review_table.create/status/export/cancel` | one job per cell, cap 500, cost reserved, CSV formula-safe | BUILT |
| Drafts | email/memo from a run | `DRAFT`, `draft.create/revise/versions/diff/export` | law only from verified citations, model prose = suggestion, versions, .docx | BUILT |
| Event Map | "what applies to this allotment?" | `EVENT_ASSESS`, `events.assess` | event → bodies of law → held/declared/need-fact | BUILT |
| Compliance Calendar | upcoming deadlines | `calendar.upcoming` | obligations + DerivedDate; unknown when a fact is missing | BUILT |
| Matters, users, roles | organise and control access | `matters.*`, users/roles | RLS on matter_id; role checked per verb | BUILT (guests: T8) |
| Agents | delegate a multi-step goal | `MULTI_AGENT`, `runs.preview/start` | §8 | TODO (MA1) |
| Saved workflows, schedules | "run this every Monday" | saved composition, schedules table | registered agents only; worker-read schedules | TODO (T5, T6) |
| Command Center | runs, cost, approve rate, queue | `ops.summary`, `usage.status`, `cache.stats` | aggregates from ledger and runs; no per-person scoring | PARTIAL (T7) |
| Spaces | firm ↔ in-house matter room | guest on one matter | RLS on matter_id, share selected files/envelopes, audit, revoke | TODO (T8) |
| Sources | where knowledge comes from | `sources.list/search` | tiers, terms register, robots, connectors | BUILT (G1 connectors TODO) |
| Horizon Scanning (Themis) | "what changed and what does it affect" | `WATCH.*`, `RECALL` | Gazette/SEBI/RBI → affected provisions → join law_versions | Themis branch, after T1 |

## 11. Sources

| Source | Access | Data | Status |
|---|---|---|---|
| India Code | open REST + PDF | Acts, sections, footnotes | corpus BUILT; live connector G1 |
| e-Gazette | PDF | notifications | G1, terms first |
| data.gov.in (OGD) | free key, GODL | company master data | G1, key pending |
| SEBI | pages/PDF | regulations, circulars | G1 |
| RBI | read-only, never cached | FEMA directions | G1, currently BLOCKED |
| Indian Kanoon | paid key, logo attribution | judgments | G1, key pending |
| User uploads | vault | client documents | BUILT |

Never bypass a WAF, robots rule or terms. A source without a terms record is never fetched.

## 12. Speed and reliability

| Concern | Design | Status |
|---|---|---|
| Interactive work stuck behind bulk | priority lanes | A1 |
| Poison jobs | 3 attempts, backoff, dead-letter | A1 |
| Connection exhaustion | pooled, hard caps | A1 |
| Provider outage | circuit breaker → next provider; FAILED, never NOT_FOUND | A1 |
| Budget mid-table | cost reserved upfront; PAUSED_BUDGET | A1 |
| Large files | page-by-page, per-file caps | A1 |
| Concurrent draft edits | optimistic lock | A1 |
| Latency | auth+RLS < 10 ms, cache < 50 ms, deterministic < 100 ms, dispatch < 20 ms, first token < 1 s via SSE | R0 |

## 13. Security and tenancy

FORCE RLS on every tenant table, proven by `scripts/rls_integration.py` against a throwaway
database as a NOSUPERUSER NOBYPASSRLS role. Audit is metadata-only and hash-chained. Keys are
stored hashed. Untrusted document text never becomes instructions; injected instructions are
flagged and kept. No training on client data. Deletion removes file, chunks and index entries
and is audited.

## 14. Hosting (pilot stage)

AWS Mumbai only: Lightsail 4 GB (API + worker, Caddy HTTPS), Lightsail managed PostgreSQL,
S3 (SSE, versioning) for vault files and nightly backups, Bedrock, Textract, budget alerts at
$20/$50/$80. About $40/month fixed plus usage; the $100 AWS credit covers roughly two months.
Scripts in `scripts/deploy/` (job H1), blocked until AWS credentials exist.

## 15. Measured, not claimed

No accuracy figure is stated anywhere a user sees. What is measured: gold-set dev split (no human
labels yet), retrieval recall/MRR/nDCG with intervals (M3), verifier false-accept rates by statute
mutation (M1), date-maths properties (M4), CUAD cell precision/recall with Wilson intervals,
cascade cost per stage, latency per hop. Calibration (CAL-1) routes answers to a second reviewer
once ≥100 lawyer labels exist per (task, body of law); it never gates an answer.

## 16. Build order from here

| # | Job | Delivers |
|---|---|---|
| 1 | P2 | hardening, per-tenant/per-user caps, usage.status |
| 2 | A1 | robustness (§12) |
| 3 | R0 | model gateway (§9), latency budgets, SSE |
| 4 | G1 | government and case-law connectors (§11) |
| 5 | T1 | law_versions on every run and in the envelope |
| 6 | T2 | citation tiers enforced |
| 7 | T3 | Document Check |
| 8 | MA1 | bounded multi-agent (§8) |
| 9 | T4–T7 | plan preview, schedules, saved workflows, Command Center |
| 10 | T8 | Spaces |
| 11 | H1 + B1 | AWS hosting and live Bedrock, when AWS is ready |
| 12 | Themis T4 | Horizon Scanning + Recall, on its branch |

---

## 17. API catalogue — every external API, what it is for, what it may see

All model APIs are called only through the model gateway (`checker/router.py`); all data APIs only
through `checker/sources/` behind a `terms.py` record. No other code calls an external API.

### 17.1 Model and document APIs

| API | Job | Data class allowed | Billing | Key |
|---|---|---|---|---|
| AWS Bedrock — Claude Haiku (ap-south-1 / India geography) | extract, classify fallback, prose, cells | CLIENT | per token | AWS |
| AWS Bedrock — Claude Sonnet | escalation on verifier rejection, critic, supervisor | CLIENT | per token | AWS |
| AWS Bedrock — Llama 3 70B (open source) | bake-off alternative | CLIENT | per token | AWS |
| AWS Textract (ap-south-1) | OCR, tables, English handwriting | CLIENT | per page | AWS |
| Self-hosted vLLM on AWS GPU (open models: gpt-oss, Llama, Mistral) | batch bake-offs, started and stopped per run | CLIENT if ap-south-1 | per GPU hour | AWS |
| Sarvam (Vision + language) | Indian scripts, Hindi handwriting | CLIENT only if India hosting confirmed in writing | per call | have |
| Voyage `voyage-law-2` | semantic search bake-off | PUBLIC law only | per token | have |
| Gemini (free tier) | comparison, backup | PUBLIC / SYNTHETIC | free | have |
| OpenRouter free models | comparison across open models | PUBLIC / SYNTHETIC | free, 50/day | get |
| Mistral free tier | bulk public jobs (CUAD, synthetic documents) | PUBLIC / SYNTHETIC (trains on inputs) | free | get |
| Azure Foundry Llama 3.3 70B (UAE North) | test backup | PUBLIC / SYNTHETIC | per token | have |

### 17.2 Legal and government data APIs

| API | Gives | Access | Status |
|---|---|---|---|
| India Code REST (`indiacode.gov.in/server/api`) + PDFs (`indiacode.nic.in`) | Acts, sections, footnotes | open, no key | corpus BUILT; live connector G1 |
| e-Gazette | notifications, commencement | PDF | G1, terms first |
| data.gov.in OGD | MCA company master data by CIN | free key, GODL attribution | G1, key pending |
| SEBI | regulations, circulars | pages/PDF, read-on-request | G1 |
| RBI | FEMA directions | read-only, never cached | G1, BLOCKED (418) |
| IBBI | IBC regulations | pages | Themis feed |
| Indian Kanoon | judgments | paid token, logo attribution | G1, key pending |

### 17.3 Infrastructure APIs

AWS S3 (vault files, backups) · AWS SES (invites, login, nudges) · AWS Secrets Manager (keys) ·
AWS Budgets (alerts) — all ap-south-1.

### 17.4 Placedon's own API (what customers and other systems call)

One verb table → REST `/v2/...`, MCP tools, CLI. Main verbs:
`conversation.send/list/get` · `runs.preview/start/get/trace/approve/reject/cancel` ·
`vault.upload/status/find/verify/summarize/research/compile/delete` · `contract.playbook_review` ·
`review_table.create/status/export/cancel` · `draft.create/revise/versions/diff/export` ·
`events.assess` · `calendar.upcoming` · `matters.create/list` · `sources.list/search` ·
`citation.get` · `usage.status` · `ops.summary` · `intake.classify`.

## 18. MCP — how Placedon connects to other AI tools

MCP (Model Context Protocol) is the standard way AI assistants call tools. Placedon uses it in two
directions.

### 18.1 Inbound: Placedon as an MCP server

Lawyers already use Claude, ChatGPT or Copilot. Placedon exposes its read-only verbs as MCP tools
(`checker/mcp/`, generated from the same verb table), so those assistants can ask Placedon for a
verified answer instead of guessing. Tool names today carry the prefix `themis.` (`themis.ask`,
`themis.search_law`, `themis.review_contract`, `themis.events.assess`, `themis.runs.get`,
`themis.sources.search`, ...; full list in `checker/mcp/policy.py` `KNOWN_TOOLS`). Renaming the
prefix is a separate decision because external clients bind to these names.

```
Lawyer in Claude / ChatGPT / Copilot
   → MCP tool call: themis.ask("AGM deadline for our company, as of 1 Oct 2026")
   → Placedon gateway: OAuth token → tenant + user + role, caps, audit
   → normal pipeline (§5): retrieve → verify → envelope with citations and law_versions
   ← tool result: status, cited sentences, refusals by name
   → the outside assistant shows Placedon's cited answer
```

Rules: read-only verbs only on MCP (no approve, create, delete), enforced by `mcp_tools()` and a test that `READ_ONLY_TOOLS == KNOWN_TOOLS`; some read verbs are also `mcp=False` on purpose (client lists, matters); OAuth per user (PLAN_22 D7, TODO — today the gateway key);
CLIENT data never leaves through MCP to a non-India model on the caller's side unless the tenant
admin enables it; every call audited.

### 18.2 Outbound: connectors as MCP clients

Placedon's agents read the customer's existing systems through MCP servers or APIs, each one a
registered source with a `terms.py` record and a data class:

| Connector | Through | Data class | Use |
|---|---|---|---|
| SharePoint / OneDrive | Microsoft Graph or its MCP server, OAuth, read-only | CLIENT | pull contracts into the vault |
| Google Drive | Drive API / MCP, OAuth, read-only | CLIENT | same |
| Email (Outlook/Gmail) | Graph / Gmail API, read-only, per-message consent | CLIENT | attachments into the vault |
| DMS (iManage, NetDocuments) | vendor API when licensed | CLIENT | later |

A connector result enters the vault like an upload (sha256, classify, index) and is then used by
the normal tasks. A connector never feeds a model directly.

## 19. External legal AI products and agents

Placedon does not run on another legal-AI company's agents. Reasons: their outputs are not
verified against held Indian law, their data paths are outside India, and a dependency on a
competitor is a business risk. What we use and how:

| External thing | Use | How |
|---|---|---|
| General models (Claude, Llama, open models) | the reading and writing inside our agents | via the model gateway (§9) |
| Anthropic's open-source `claude-for-legal` plugins (GitHub) | reference patterns for legal workflows and prompts; licence checked before reuse | study and adapt into our registry; never run as an unverified agent |
| Other legal-AI vendors' MCP servers | only if a customer already licenses one and wants interop | as a WEB/LICENSED-tier source; never VERIFIED |
| Indian Kanoon | case law | licensed source (§17.2) |

## 20. Worked examples (end to end)

### 20.1 "We are allotting shares to a Singapore investor — what applies?"

1. `conversation.send` → intake: EVENT_ASSESS, event = share allotment, foreign_investor = true.
2. `events.assess` → bodies engaged: Companies Act (HELD), FEMA (DECLARED), stamp duty (needs State).
3. Researcher agent (Haiku, India) on Companies Act → BM25 finds Section 62 → quote verified.
4. Envelope: PARTIAL; Section 62(1)(c) cited with sha256; FEMA NOT_HELD by name; stamp duty NEED_FACT
   ("which State?"); law_versions records Section 62's hash.
5. Lawyer approves. Months later the Gazette amends Section 62 → Themis recall lists this answer.

### 20.2 "Review these 40 vendor NDAs and draft a risk memo" (multi-agent)

1. Intake: MULTI_AGENT. Supervisor plans: doc_auth ×40 → extractor ×40 → comparer → critic → drafter.
2. Code validates the plan (registry only, ≤8 agent types, depth 1, budget ₹X) → lawyer previews → starts.
3. Jobs fan out on the bulk lane; each extraction is verified (exact quote) before comparison.
4. doc_auth flags 3 unsigned and 1 expired; comparer finds 7 governing-law deviations.
5. Critic removes one weak finding; drafter writes the memo from verified findings only, prose marked
   as suggestion. NEEDS_LAWYER items become nudges. Cost and per-agent trace in the ledger.

### 20.3 "Is this board resolution real?" (Document Check)

Upload → DOC_AUTHENTICATE: PDF integrity READ · sha256 NEW · PKCS#7 signature SIGNED_VALID against the
CCA chain · face date CURRENT · execution block PRESENT · party MATCHES the tenant's company ·
no injection text. Each line is a finding with its evidence; anything unverifiable is NEEDS_LAWYER.

### 20.4 Lawyer inside Claude asks Placedon (MCP)

Claude calls `themis.ask` → Placedon answers with cited, verified sentences or a named refusal →
Claude shows it. The outside model never decides the law; Placedon does, in code.

## 21. Features not built on purpose

- Free agents that invent their own steps (MAST failure FM-1.1); only registered agents run.
- Answers on state laws not acquired (Shops & Establishments, professional tax, stamp duty):
  refused by State name until a pilot funds acquiring one State pack.
- People-scoring ("should this associate be removed"): out. Command Center shows aggregates only.
- Benchmarks against other firms: no Indian contract corpus exists to support them.
- Case-outcome or judge prediction in the product: research only, after legal review.
