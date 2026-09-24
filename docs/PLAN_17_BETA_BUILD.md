# PLAN_17 — the beta: what to build, in what order, and the prompt for each step

Written 2026-09-24. Status vocabulary is [PLAN_00_INDEX](PLAN_00_INDEX.md)'s.
Companion documents: [PLAN_16](PLAN_16_RESEARCH_PROGRAMME.md) (the research the
design rests on) and [STUDY_GUIDE_THEMIS](STUDY_GUIDE_THEMIS.md) (the concepts,
explained for the founder).

**How to use this file.** Work the milestones in order. Each one has a goal, the
files it touches, what "done" means, and a **prompt block to paste into Claude
Code** as it stands. Do not start a milestone until the previous one's "done when"
is met. Milestones marked **HUMAN** are yours; no agent can do them.

---

## 0. What "beta" means here

A beta is not a demo. It is the smallest system a real in-house legal team can
use on real matters for a month without anyone faking anything.

| A beta HAS | A beta does NOT have |
|---|---|
| Real sign-in with a company Microsoft account; invite-only companies | Self-serve sign-up, billing |
| Matters, and a Vault that keeps uploaded documents under the customer's control | Connectors to iManage, SharePoint, email |
| An Ask screen: statute answers with citations or a visible refusal; summaries of the customer's own documents traced to spans | Answers about law we do not hold (decision 2) |
| A document forensics report | Case-outcome or market prediction |
| A watch inbox: Gazette changes, counterparty insolvency (IBBI), sanctions (OFAC) | Push email alerts (in-app only for beta) |
| A feedback button on every answer, and a "known limitations" page | Any accuracy claim |
| Audit log, retention settings, delete-my-data | SOC 2 (planned, not held) |

**Beta exit criteria:** one in-house team uses it on real matters, unprompted,
at least twice a week for four weeks (PLAN_05's retention gate); zero
cross-tenant data incidents; every served legal claim traced or refused; at
least 59 answers labelled by the team's lawyers with consent (enough for the
first certified-abstention measurement, PLAN_16 C1).

---

## 1. Positioning, measured against the nearest competitor

**GC AI** sells to in-house teams at a published **$500 per seat per month**,
claims **1,900+ in-house teams**, and already ships **character-level "Exact
Quote" citations**, contract playbooks and a Word add-in (vendor's own blog;
UNVERIFIED beyond that). So span-traced citations are **not** our moat on their
own.

What no one we have found sells for India:
1. **Statutory currency** — the answer says which amending notification it rests
   on and notices when the law has moved (the s.2(85) incident; the Gazette
   watcher).
2. **Deterministic obligations** for a specific company, with abstention where a
   fact or a rule is missing (`checker/obligations.py`).
3. **Document forensics** against Indian sources — signature and tamper checks
   (CCA India chain), self-contradiction, stale law recited, counterparty
   insolvency or sanctions.

The beta is built to make those three visible on day one.

---

## 2. The architecture as shells

Each shell may depend only on shells **inside** it. This is the ring firewall's
rule (`checker/rings.py`) applied to the whole system.

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │ SHELL 5  OPERATIONS    monitoring, audit review, eval loop, security    │
 │ ┌───────────────────────────────────────────────────────────────────┐ │
 │ │ SHELL 4  SURFACES     web app (Next.js) · MCP · CLI · Word add-in    │ │
 │ │ ┌───────────────────────────────────────────────────────────────┐ │ │
 │ │ │ SHELL 3  PLATFORM   gateway · identity · tenancy · Vault · jobs │ │ │
 │ │ │ ┌───────────────────────────────────────────────────────────┐ │ │ │
 │ │ │ │ SHELL 2  INTELLIGENCE  orchestrator pipeline · router ·     │ │ │ │
 │ │ │ │                        sufficiency gate · tracing · certify │ │ │ │
 │ │ │ │ ┌───────────────────────────────────────────────────────┐ │ │ │ │
 │ │ │ │ │ SHELL 1  EVIDENCE   feeds · entity graph · events ·    │ │ │ │ │
 │ │ │ │ │                     operations · document extraction   │ │ │ │ │
 │ │ │ │ │ ┌───────────────────────────────────────────────────┐ │ │ │ │ │
 │ │ │ │ │ │ SHELL 0  LEGAL CORE  statute corpus · obligations · │ │ │ │ │ │
 │ │ │ │ │ │   deciders · as_of · currency · admission · scope   │ │ │ │ │ │
 │ │ │ │ │ └───────────────────────────────────────────────────┘ │ │ │ │ │
 │ │ │ │ └───────────────────────────────────────────────────────┘ │ │ │ │
 │ │ │ └───────────────────────────────────────────────────────────┘ │ │ │
 │ │ └───────────────────────────────────────────────────────────────┘ │ │
 │ └───────────────────────────────────────────────────────────────────┘ │
 └───────────────────────────────────────────────────────────────────────┘
```

| Shell | Exists today | Built in this plan |
|---|---|---|
| 0 Legal core | **BUILT**: `checker/obligations.py`, `s185/186/188.py`, `as_of.py`, `currency.py`, `admission.py`, `scope.py`; 529 sections | Nothing new. Only fixes |
| 1 Evidence | **BUILT**: `feeds/` (eGazette, OFAC, IBBI), `entity_graph.py`, `event_log.py`, `operations.py`, `pdf_pages.py`, `document_extract.py` | Operation store (M6); forensics report assembly (M8) |
| 2 Intelligence | **PARTLY**: `router.py`, `ask.py`, `lawyer_summary.py`, `claim_verifier.py`, `prompt_safety.py` | Azure adapters and data-class routing (M2); the Ask v2 pipeline with a sufficiency gate (M7) |
| 3 Platform | **NOT BUILT**: `api.handle()` exists but is unauthenticated and single-tenant | Gateway (M3), database with tenant isolation (M4), Vault (M5), job runner (M5) |
| 4 Surfaces | **PARTLY**: marketing site, MCP server (13 tools), Word add-in, Ask prototype | The logged-in web app (M10); CLI (M3); MCP authorisation (M9b) |
| 5 Operations | **PARTLY**: `run_tests.sh`, red-team docs | CI (M1), audit review, backups, runbook, eval loop (M11–M12) |

### 2.1 Request flow for one Ask, end to end

```
 1  Browser → POST /v1/matters/{m}/ask          (session cookie from Entra sign-in)
 2  Gateway: validate token → tenant, user; check the user is on matter m;
            policy.decide(); write an audit row (no document text in it)
 3  Scope gate          scope.py: is the question about held law?  no → refusal
 4  Retrieve            statute: structural BM25, filtered as-of the question date
                        Vault:   Postgres full-text, scoped to matter m, tenant t
 5  Sufficiency gate    is the retrieved context enough? not enough → refusal
                        (the gate may only withhold; it can never permit)
 6  Decide              obligations / deciders for any company facts supplied
 7  Narrate             router picks a CLIENT-safe model; prompt carries
                        prompt_safety.UNTRUSTED_CLAUSE
 8  Trace               lawyer_summary: each clause → byte-identical span, or refused
 9  Serve               stream the answer; refused clauses shown as refused;
                        evidence panel lists every span with its source and date
10  Feedback            thumbs / correction → stored only if the tenant consented
```

### 2.2 Decisions this plan fixes

| Area | Choice | Reason | Status |
|---|---|---|---|
| Cloud | **Azure, Central India** (South India as backup) | India data residency; Azure OpenAI and Document Intelligence both process in-region for regional deployments | SOURCED (search-level) — confirm in the portal at M0 |
| LLM for client data | **Azure OpenAI, regional "Standard" deployment in India** | Regional deployments process in the deployment region. Which GPT models exist in Central/South India changes monthly | Model list **UNVERIFIED** — confirm at M0 |
| Zero retention | Apply for **Modified Abuse Monitoring** | Without it Azure keeps prompts 30 days for abuse review. It needs an **Enterprise Agreement or Microsoft Customer Agreement** — not pay-as-you-go — and an application | SOURCED (search-level). **M0 blocker** |
| Claude | **Off for client data** until Anthropic's India in-country inference on Bedrock is confirmed live and zero-retention terms are signed | Announced Aug 2026 "in the coming weeks". The earlier Bedrock route for India is **global** cross-region inference: data may be processed outside India | Watch; re-decide at M11 |
| OCR for scans | **Azure Document Intelligence**, Central India | Documented in-region processing. Replaces Gemini for client scans | SOURCED (search-level) |
| Gemini free tier, Sarvam | **Public documents only** | Free-tier inputs may be used by Google; Sarvam trains by default unless opted out (`sarvam_model.py`) | BUILT guard for Sarvam; Gemini guard is M2 |
| Database | **Azure Database for PostgreSQL Flexible Server** + **row-level security** per tenant | RLS makes tenant isolation a database property, not an application convention; customer-managed keys supported | SOURCED |
| Vault search | **Postgres full-text search** first; dense vectors only after a bake-off | `NON_GOALS.md`: BM25 wins on entity-rich exact match at our size; no new vector dependency until measured | Repo rule |
| Documents | **Azure Blob Storage**, one container per tenant, envelope encryption with a per-tenant key in Key Vault | Deleting the tenant key makes every copy unreadable ("crypto-shredding") | Design |
| Identity | **Microsoft Entra ID**, multi-tenant app restricted to **work accounts**, plus an **allow-list of approved customer tenants** | In-house teams already run on Microsoft 365; allow-list = invite-only beta | SOURCED (search-level) |
| Jobs | A **Postgres job table** (`SELECT … FOR UPDATE SKIP LOCKED`) | No extra queue service for beta volumes | Design |
| Gateway | **FastAPI** (already pinned in `requirements.txt`) wrapping `checker.api.handle()` | Declared dependency; the engine itself stays standard-library | Repo |
| Web app host | Logged-in app on **Azure Container Apps, Central India**; marketing site stays on Vercel | Client documents never pass through a third-party host outside our cloud | Design; confirm Container Apps in Central India at M0 |

---

## 3. Milestones

Sizing: **S** ≈ one focused session, **M** ≈ 2–4 sessions, **L** ≈ a week of
sessions. These are relative sizes, not promises.

Every prompt below assumes Claude Code is started inside
`placedon-law-backend` (or `placedon-claude-legal-3300` for M10), so `CLAUDE.md`
/ `AGENTS.md` load automatically. The prompts repeat the rules that matter most
anyway, because a rule that is not in the prompt is the one that gets skipped.

---

### M0 — Prerequisites · **HUMAN** · blocks M2 onward

| # | Task | Why |
|---|---|---|
| 0.1 | Azure subscription under an **EA or MCA**, region Central India | Zero-retention approval is not available on pay-as-you-go |
| 0.2 | Create an Azure OpenAI resource in Central India; **write down which models the portal offers for a regional Standard deployment** | Decides the model table in M2 |
| 0.3 | Submit the **Modified Abuse Monitoring** application | Until approved, prompts are retained 30 days by Microsoft |
| 0.4 | Register the Entra app (multi-tenant, work accounts only) | Sign-in for M3 |
| 0.5 | Confirm Azure Container Apps, Blob, Key Vault, PostgreSQL Flexible Server in Central India | Hosting for M3–M5 |
| 0.6 | Counsel: privacy notice, terms, DPA template, the DPDP position on third-party personal data in customer documents | DPDP consent-manager rules start Nov 2026; core obligations May 2027 |
| 0.7 | Name the pilot customer and one champion lawyer there | Everything after M10 needs them |
| 0.8 | Merge `loop/bookmark-godseye-v0` into `main` (MCP surface, lawyer-summary fixes) and push the local PoSH deletion | The plan builds on the latest branch |

**Done when:** 0.1–0.5 recorded in `docs/INFRA_DECISIONS.md` with the exact model
names and regions seen in the portal; 0.7 named; 0.8 merged.

---

### M1 — Make the engine trustworthy from a clean checkout · Shell 0/5 · **S**

Why first: five suites fail anywhere but the founder's laptop, CI is off, and the
lawyer-facing sentence about G.S.R. 880(E) is false.

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: the test suite passes from a fresh clone, CI runs on every push, and the
false "Nobody has read the instrument yet" sentence is fixed.

Do these as separate commits, one logical change each, tests first:

1. Reproduce the failures from a clean clone: `pip install -r requirements-dev.txt`,
   then `./scripts/run_tests.sh`. Known causes: pypdf missing; checker/provenance.py's
   unreadable-file test assumes a non-root user (a chmod 000 file is readable as
   root) — make that test skip with a printed reason when os.geteuid() == 0, never
   delete it; checker/s96_slice.py needs a cached copy of Act 1 of 2018 that is not
   in the repo — either commit the cached witness (check the source terms first:
   Indian Kanoon attribution) or make the suite report "witness not held" as a
   SKIP with a reason, not a pass; scripts/review.py --test fails rendering a PDF.
   Find each root cause. Do not weaken any assertion.
2. Enable CI: move ci/tests.yml.pending to .github/workflows/tests.yml. Update its
   stale "~4s" comment and timeout to the measured suite time.
3. Fix checker/mcp/tools.py (the sentence_for_a_lawyer around line 188) and
   checker/operations.py (the R0 "Acquire and attest" requirement, ~lines 279-294):
   if the instrument is attested (use the register script's is_attested(), or a
   shared helper — do not duplicate the rule), say it is held and attested, from
   which source and date, and do not create the "acquire" requirement; if not,
   keep today's wording. Tests must assert BOTH branches, and the old test that
   pinned the false wording must change.

Rules: CLAUDE.md applies. No new runtime dependency. Every suite green via
./scripts/run_tests.sh before each commit. Report: files changed, tests added,
commands run, results, known limitations, commit hashes.
```

**Done when:** CI green on a PR from a clean runner; `themis.get_instrument_impact("880")`
says held and attested; `themis_slice.py --demo` no longer asks to acquire 880(E).

---

### M2 — Providers and the data-class rule · Shell 2 · **M**

Why: decision 4 must be enforced in code, not in a policy document.

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: the router knows whether a task carries CLIENT data or PUBLIC data, and a
CLIENT task can only reach a provider on an explicit CLIENT-safe list.

1. Read checker/router.py fully first. Add a field `data_class` to Task with values
   PUBLIC and CLIENT. Default is CLIENT (fail closed: an unlabelled task is treated
   as client data).
2. Add CLIENT_SAFE: a frozenset of (provider, deployment) pairs that are allowed
   to see client data. Start it with Azure OpenAI and Azure Document Intelligence
   ONLY. Gemini (any tier) and Sarvam are never in it. Anthropic is not in it
   until docs/INFRA_DECISIONS.md records India in-country inference plus
   zero-retention terms.
3. route(): a CLIENT task whose preferred providers are not CLIENT-safe is
   REFUSED with a reason, never degraded to a non-safe provider.
4. Move eval/realrun/azure_model.py's adapter into checker/azure_model.py as a
   production adapter (fail-closed on missing key/endpoint, same style as
   anthropic_model.py). Add checker/azure_docintel.py for page OCR. Both read
   endpoint, deployment name and region from environment variables documented in
   .env.example; refuse to run if the configured region is not an Indian region.
5. Tests: a CLIENT page image never routes to Gemini; a CLIENT text task with only
   Gemini available is refused; PUBLIC tasks keep today's routing; the region
   guard refuses "eastus". Include a negative control proving the guard can fail.

Rules: CLAUDE.md. The router stays deterministic — no model picks a model. No
network in tests. Report in the required code-task format.
```

**Done when:** `router.py` suite covers every (data_class × provider) cell; no
code path sends a CLIENT task to Gemini or Sarvam (proven by test).

---

### M3 — The gateway, identity, and the CLI · Shell 3/4 · **M**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: a FastAPI gateway in a new top-level package `gateway/` that authenticates a
user, resolves their tenant, and calls the existing engine. Plus a `themis` CLI.

1. gateway/app.py: FastAPI (already pinned in requirements.txt). Every route
   requires a bearer token issued by Microsoft Entra ID. Validate issuer, audience,
   signature (JWKS), expiry. Accept only work accounts; reject any tenant id not in
   the TENANT_ALLOWLIST table/config. Map the token to (tenant_id, user_id, email).
2. Routes: /v1/health (no auth), and pass-throughs for the eight engine routes via
   checker.api.handle() — the same function scripts/serve_api.py and the MCP server
   call, so the three surfaces cannot drift. Add request ids.
3. Reuse checker/mcp/policy.py for the allow/deny decision on every call; write an
   append-only audit record (who, tenant, route, verdict, timestamp, request id).
   NEVER write request or document text into the audit record or logs.
4. The engine stays unauthenticated on 127.0.0.1; only the gateway is exposed.
5. scripts/themis_cli.py (stdlib argparse) with subcommands: ask, check <pdf>,
   pack <facts.json>, impact <instrument>, scope, watch {gazette,ofac,ibbi}. It calls
   checker.api.handle() directly for local use.
6. Tests: an unsigned token, a wrong audience, an expired token, a personal Microsoft
   account and a non-allow-listed tenant are all 401/403; an allowed token reaches
   /v1/ask; audit rows contain no request body. Use locally generated test keys —
   no network.

Rules: CLAUDE.md. Name the new dependency for JWT validation with its reason, or
implement RS256 verification with the stdlib + an already-pinned package if
possible; say which and why. Report in the required format.
```

**Done when:** gateway suite green; `themis scope` prints held/declared bodies;
nothing reachable without a valid token except `/v1/health`.

---

### M4 — Tenancy in the database · Shell 3 · **M**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: a PostgreSQL schema where one tenant can never read another tenant's rows,
enforced by row-level security (RLS), with migrations and tests.

1. Tables: tenants, users, matters, matter_members (the ethical wall: a user sees a
   matter only if listed), documents, document_pages, operations, requirements,
   evidence, watchlist_companies, audit_log (append-only), consents, feedback, jobs.
   Every tenant-owned table has tenant_id NOT NULL.
2. RLS on every tenant-owned table: USING (tenant_id = current_setting('app.tenant_id')::uuid).
   The application role has no BYPASSRLS. The gateway sets app.tenant_id per request
   inside the transaction, never globally.
3. Matter walls: a second policy restricts matter-scoped tables to matters the
   current user is a member of (current_setting('app.user_id')).
4. Migrations as plain SQL files under db/migrations/ with a tiny stdlib runner.
   Name the Postgres driver dependency you add and why.
5. Tests against a disposable local Postgres (docker or testing.postgresql —
   say which): tenant A cannot SELECT, UPDATE or DELETE tenant B's rows through any
   table; forgetting to set app.tenant_id returns ZERO rows, not all rows; a user off
   a matter's member list sees none of its documents; audit_log rejects UPDATE and
   DELETE.

Rules: CLAUDE.md. A test that cannot fail is not evidence: include a negative
control that disables one policy and proves the suite goes red. Report in the
required format.
```

**Done when:** the isolation suite is green and its negative control is red when a
policy is removed.

---

### M5 — The Vault and the job runner · Shell 3 · **L**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: customers upload documents into a matter; each is stored encrypted under the
tenant's own key, extracted page by page, searchable within its matter, and
deletable for good.

1. Upload: the gateway issues a short-lived, write-only SAS URL for
   container tenant-{id}/matter-{id}/; the browser uploads directly to Azure Blob.
   Document text never passes through application logs.
2. Encryption: envelope encryption. One data key per tenant, wrapped by a Key Vault
   key. Store only the wrapped key in Postgres. Deleting a tenant = destroy its key,
   then delete blobs and rows (crypto-shredding first, so a missed copy is
   unreadable).
3. Jobs table with SELECT ... FOR UPDATE SKIP LOCKED. Job types: extract_text
   (checker/pdf_pages.py for text PDFs; Azure Document Intelligence via
   checker/azure_docintel.py for scans — CLIENT data class), verify_signature
   (checker/pdf_signature.py / scripts/verify_document.py logic), index_fulltext.
4. Pages go to document_pages with a Postgres tsvector index; search is always
   filtered by tenant AND matter.
5. Retention: a per-tenant retention policy (days); a nightly job deletes expired
   documents and records the deletion in audit_log (ids only).
6. Page text is DATA, never instructions: anything that later puts it into a
   prompt must go through checker/prompt_safety.py; do not strip or rewrite any
   instruction-like text found in a document (CLAUDE.md).
7. Tests: cross-matter search returns nothing; a deleted tenant's wrapped key is
   gone and its blobs unreadable; a scan routes to Document Intelligence and never
   to Gemini; a killed job is retried exactly once and never double-indexes.

Rules: CLAUDE.md; PLAN_07 as amended by PLAN_16 §1 (nothing kept as a side
effect; only deliberate Vault uploads persist). Report in the required format.
```

**Done when:** an uploaded PDF is searchable in its matter only, and a tenant
deletion leaves nothing readable.

---

### M6 — Operations become a real queue · Shell 1 · **M**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: operations persist per tenant, requirements can be satisfied with evidence,
and a BLOCKING requirement can only be closed by a human.

1. Store operations and requirements (checker/operations.py objects) in the M4
   tables, keyed by tenant. checker/mcp/tools.py themis.get_operation stops
   returning 501 and reads the store.
2. submit_evidence(requirement_id, evidence) — gateway route only (NOT an MCP tool:
   the MCP surface stays read-only). Evidence records its source, a hash, who
   submitted it and when.
3. A BLOCKING requirement moves to SATISFIED only when a human user confirms it; an
   API call carrying an agent/service identity is refused, with a test.
4. Watchlist per tenant: real CINs the customer adds. Gazette items create
   operations for that tenant's watched companies only.
5. The evidence budget (count of open blocking requirements) is shown on every
   operation; it is a count, never a score (L-15).

Rules: CLAUDE.md; rings.py must still pass (operations is Ring 2; no Ring 0
import of it). Report in the required format.
```

**Done when:** an operation created on Monday is still there on Tuesday, and only a
person can close its blocking work.

---

### M7 — Ask v2: the full pipeline · Shell 2 · **L**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: POST /v1/matters/{m}/ask runs the ten-step flow in PLAN_17 §2.1 and streams
the answer, with refusals visible.

Read first: checker/ask.py, checker/lawyer_summary.py, checker/claim_verifier.py,
checker/scope.py, checker/structural_retrieve.py, checker/prompt_safety.py,
web/assistant/contract.md.

1. Keep the placedon.ask/0 contract; extend it additively (new optional fields
   only) so the existing prototype and fixtures keep working.
2. Retrieval: statute spans filtered by as-of date; Vault spans from M5 full-text
   search scoped to the matter. Each span carries source, version, effective dates.
3. Sufficiency gate (Joren et al., ICLR 2025): a CLIENT-safe model rates whether the
   retrieved spans suffice to answer. The gate can only WITHHOLD: "insufficient" →
   refusal naming what is missing; "sufficient" → continue. It never adds
   content. Log the gate's decision for evaluation (no text, just ids and label).
4. Narration through router.py with data_class=CLIENT; system prompt carries
   prompt_safety.UNTRUSTED_CLAUSE; Vault text arrives as structured content, not
   concatenated into the prompt string, where the provider supports it.
5. Every clause through lawyer_summary tracing; refused clauses returned as
   refused, never dropped silently.
6. Streaming: server-sent events; the evidence panel data arrives with the answer.
7. Conversation threads per matter, stored in M4 tables.
8. Tests: an out-of-scope question (FEMA) refuses; a Companies Act question with no
   supporting span refuses via the sufficiency gate (use a stub rater in tests); a
   fabricated clause conjoined to a true one is refused (existing D4 kill tests stay
   green); a prompt-injection sentence inside a Vault document is not obeyed and is
   not deleted from the stored document.

Rules: CLAUDE.md. No general-knowledge answers (decision 2). Report in the required
format.
```

**Done when:** the acceptance runner (`web/assistant/tools/accept.mjs`) and the new
tests pass, and every answer's clauses are either traced or visibly refused.

---

### M8 — Document forensics report · Shell 1/2 · **M**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Goal: one report per Vault document that assembles checks the repository already
has, with a status per section and nothing asserted beyond its evidence.

Sections, each with VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / POTENTIAL_ISSUE /
STALENESS_WARNING / INAPPLICABLE (CLAUDE.md status labels):
1. Authenticity: digital signature validity and whether content was appended after
   signing (checker/pdf_signature.py, checker/revocation.py).
2. Identity consistency: does the document contradict itself about its own CIN or
   dates (the check behind commit beaf184; checker/document_date.py).
3. Currency: law recited in the document that has since changed (checker/ss scanner,
   staleness.py) — e.g. repealed auditor-ratification wording.
4. Extracted values: every figure traced to a span; OCR-over-scan pages flagged
   (never repaired).
5. Counterparties named in the document: IBBI insolvency and OFAC sanctions matches,
   labelled as CANDIDATES for a person to confirm, never as findings.
6. What was not checked, stated explicitly.

Unknown document type → classification uncertainty only, no substantive defects
(CLAUDE.md). Minutes checks never fire on notices. Report in the required format.
```

**Done when:** each of the public test documents in `corpus/testdocs/` produces a
report whose every non-INAPPLICABLE line cites its evidence.

---

### M9 — Monitoring and MCP authorisation · Shell 1/4 · **M**

```text
PROMPT (Claude Code, repo placedon-law-backend):

Part A — scheduled watchers. Run scripts/watch_gazette.py, watch_ofac.py and the
IBBI feed as jobs (M5 runner) on a schedule; results create per-tenant operations
for watched companies (M6) and entries in an in-app inbox. Log-then-state ordering
(RT-08) and regression detection (RT-07) must be preserved. A failed poll creates
no work and says so.

Part B — MCP to the current specification (2026-07-28). The server in
checker/mcp/server.py answers protocolVersion 2024-11-05. Upgrade to the current
revision: stateless core; the server as an OAuth 2.1 resource server that returns
401 pointing at its Protected Resource Metadata (RFC 9728) and rejects tokens not
issued for it. Identity comes from the Entra token, not from _actor/_tenant
arguments (keep those only for local stdio use, clearly marked). Tools stay
read-only. Read the specification text before writing code and cite the sections
you implement in the module docstring.

Rules: CLAUDE.md. Report in the required format.
```

**Done when:** the inbox shows real Gazette items for a test tenant; an MCP client
without a valid token gets 401 with resource metadata.

---

### M10 — The logged-in web app · Shell 4 · **L** · repo `placedon-claude-legal-3300`

```text
PROMPT (Claude Code, repo placedon-claude-legal-3300):

Goal: an authenticated app under /app for in-house teams, built on the existing
design tokens and AGENTS.md rules, talking only to the gateway, server-side.

Before coding: read AGENTS.md and fix its stale facts (it says six engine routes and
that /v1/ask does not exist; the engine serves eight, and the gateway is now the
only thing the web app calls). Read node_modules/next/dist/docs for this Next.js
version.

Screens:
1. Sign in with Microsoft (Entra); a non-allow-listed company sees a polite
   "request a pilot" page.
2. Matters list and matter page (members, documents, threads).
3. Ask: chat with streaming answer + evidence panel; refused clauses visibly
   refused; the abstain state uses the reserved cool grey only; answer classes
   distinguishable without colour.
4. Vault: upload (direct-to-blob SAS), document list, per-document forensics report.
5. Watch inbox: Gazette / IBBI / OFAC items and their operations with the evidence
   budget count.
6. Settings: retention, consent for evaluation use (off by default), delete data.
7. A feedback control on every answer; a "Known limitations" page linked from the
   footer of every app screen.

Rules: AGENTS.md (brand, voice, banned words, a11y AA, 360px, reduced motion). A
transport failure is never rendered as an abstention (EngineResult<T>). No
provider or token in any "use client" module. Update .env.example. tsc, eslint,
node tests/contracts.mjs and npm run build all clean. Report in the required
format.
```

**Done when:** a pilot user can sign in, upload, ask, read a forensics report and
see the inbox, on a 360px screen and with a keyboard only.

---

### M11 — Beta hardening · Shell 5 · **M** (agent + HUMAN)

| Item | Done when |
|---|---|
| Security review of M3–M10 (`/security-review`, plus an independent red-team agent) | Findings dispositioned in `docs/research/RED_TEAM_BETA.md`; FATAL/MAJOR fixed with tests |
| Backups and restore drill for Postgres and Blob | A restore performed and timed |
| Rate limits and per-tenant model budget (`backend/budget.py`) | A runaway loop is stopped by the budget, tested |
| Runbook: incidents, key rotation, tenant deletion, data-subject requests | `docs/RUNBOOK_BETA.md` |
| Legal pack from counsel: terms, privacy notice, DPA, AI-use disclosure | **HUMAN** |
| Re-decide Claude (Bedrock India in-country + zero-retention) | Recorded in `docs/INFRA_DECISIONS.md` |

---

### M12 — Pilot and the evaluation loop · Shell 5 · **HUMAN + agent**

1. **Preregister** the pilot evaluation before it starts (`docs/PILOT_PREREG.md`):
   the questions, the metrics, the analysis — Magesh et al.'s method.
2. Onboard the champion lawyer; weekly 30-minute review of flagged answers.
3. Consented feedback becomes labelled claims; stop at ≥ 59 for the first
   calibration (PLAN_16 C1), aim for 299.
4. Weekly metrics **with error bars** (Miller): traced rate, refusal rate,
   refusal-was-right rate, time saved as reported by the user.
5. Exit review against §0's criteria. Only then decide pricing and a second
   customer.

---

## 4. Research track, in parallel with M1–M10

| Step | Output | Depends on |
|---|---|---|
| R1 | P1 draft: calibration floors (PLAN_16 C2), re-derived by an independent agent | Nothing |
| R2 | P2 draft: non-interference in `rings.py` (C5) + the lattice (C6) | Nothing |
| R3 | Read in full the four temporal-legal-RAG papers (PLAN_16 §2.4); write the delta | A human with arXiv access |
| R4 | P3 draft (currency) for ICAIL 2027, deadline 28 Jan 2027 | R3; dated competitor captures |
| R5 | P4 (certified abstention) | M12 labelled data |

---

## 5. Dependency map

```
 M0 ──┬── M1 ── M2 ──┬── M7 ── M8 ──┐
      │             │              ├── M10 ── M11 ── M12
      └── M3 ── M4 ─┴── M5 ── M6 ── M9 ┘
 R1, R2 anytime · R3 → R4 · M12 → R5
```

---

## 6. Risks that would stop the beta

| Risk | Early signal | Response |
|---|---|---|
| No EA/MCA, so no zero-retention approval | M0.1 stalls | Do not put client documents through any model until approved; run the beta on public documents only |
| Wanted GPT model not deployable in an Indian region | M0.2 | Use what is available regionally; model choice is a cost lever here, not a correctness lever (PROVIDER_DECISION) |
| Pilot finds refusals annoying | M12 week 1–2 feedback | This is PLAN_00 falsifier 1 — learn which refusals, fix coverage, do not remove refusal |
| Cross-tenant leak | M4 tests, M11 red team | Stop the beta; incident runbook |
| Scope creep (general chat, prediction) | Requests from the pilot | Decision 2 and PLAN_16 §4 "will not claim" |

---

## 7. What this plan does not claim

- That any vendor fact in §2.2 is current: every one marked SOURCED here was
  confirmed from search results and vendor/press pages on 2026-09-24, not from
  the vendor portal. M0 confirms them.
- That the beta is accurate. That is what M12 measures.
- Any date. Sizes are relative.

## Sources (checked 2026-09-24)

- Azure OpenAI regional data processing — https://learn.microsoft.com/en-us/answers/questions/5576384/where-does-my-data-processed-in-standard-type-depl · https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability
- Modified abuse monitoring / zero retention — https://larryjameshenry.com/posts/mastering-zero-data-retention-modified-abuse-monitoring/ · https://meetily.ai/llm-privacy/azure
- Claude on Bedrock in India (global cross-region) — https://aws-news.com/article/2026-03-09-access-anthropic-claude-models-in-india-on-amazon-bedrock-with-global-cross-region-inference
- Claude in-country inference in India (announced) — https://www.business-standard.com/technology/artificial-intelligence/anthropic-brings-claude-in-country-inference-to-india-via-aws-cloud-126080301168_1.html · https://anthropic.com/news/bengaluru-office-partnerships-across-india
- Document Intelligence in-region processing — https://learn.microsoft.com/en-us/answers/questions/5679952/clarification-on-india-only-data-residency-for-azu
- PostgreSQL CMK and multitenant RLS — https://learn.microsoft.com/en-us/azure/postgresql/security/security-data-encryption · https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/service/postgresql
- Entra sign-in audience — https://learn.microsoft.com/en-us/entra/identity-platform/howto-modify-supported-accounts
- MCP 2026-07-28 — https://modelcontextprotocol.io/specification/2026-07-28 · https://blog.modelcontextprotocol.io/posts/2026-07-28/
- DPDP Rules 2025 phases — https://www.azbpartners.com/bank/indias-digital-personal-data-protection-act-phased-rollout-and-key-compliance-milestones/
- Harvey Vault and security — https://www.harvey.ai/platform/vault · https://www.harvey.ai/security
- GC AI (competitor, vendor claims) — https://gc.ai/blog/best-legal-ai-tools-for-in-house-counsel
- Sufficient context method — https://research.google/blog/deeper-insights-into-retrieval-augmented-generation-the-role-of-sufficient-context/
