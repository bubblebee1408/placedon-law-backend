# PLAN_18 — technical design for the beta

Written 2026-09-24. Status vocabulary is [PLAN_00_INDEX](PLAN_00_INDEX.md)'s.

[PLAN_17](PLAN_17_BETA_BUILD.md) says **what** to build and **in what order**. This
document says **how**: deployment, components and their interfaces, data model
(DDL), API, the Ask pipeline in pseudocode, security, observability, budgets,
testing, configuration, and the repository layout. Concepts are explained in
[STUDY_GUIDE_THEMIS](STUDY_GUIDE_THEMIS.md).

**Ground rule for this design:** it *extends* interfaces that exist today on
`loop/bookmark-godseye-v0` (`325e60a`) and never replaces them. Names in `code`
are real unless marked **NEW**.

---

## 1. Deployment topology (Azure, Central India)

```
                     Internet
                        │
          ┌─────────────┴──────────────┐
          │                            │
   placedon.com (Vercel, bom1)   app.placedon.com
   marketing site, no client     Azure Container Apps (Central India)
   data                          │
                                 ├── web      Next.js app (logged-in)        NEW
                                 ├── gateway  FastAPI + in-process engine    NEW
                                 └── worker   job runner (same image)        NEW
                                       │  managed identity; private endpoints only
          ┌──────────────┬─────────────┼──────────────┬──────────────────┐
          │              │             │              │                  │
   PostgreSQL       Blob Storage   Key Vault    Azure OpenAI      Document Intelligence
   Flexible Server  per-tenant     (tenant       (regional        (Central India)
   (RLS, CMK)       encryption     keys, secrets) Standard, India)
                    scopes
          │
   Log Analytics — metadata only, never document or prompt text
```

Decisions and their status:

| Choice | Reason | Status |
|---|---|---|
| Engine runs **in-process** inside the gateway (import `checker.api.handle`) | One process, no second network hop; the loopback HTTP engine (`scripts/serve_api.py`) stays for local development only | Design |
| Web app calls **only** the gateway, from the server side | Keeps the AGENTS.md rule: no engine origin or token in any client bundle | Repo rule |
| Private endpoints for Postgres, Blob, Key Vault, Azure OpenAI, Document Intelligence; no public network access | Nothing holding client data is reachable from the internet | Design |
| Managed identity from Container Apps to every Azure resource | No stored cloud credentials | Design |
| Infrastructure as code in **Bicep** (`infra/`) | Microsoft first-party; no runtime dependency | NEW tool — reason stated |
| Per-tenant **Blob encryption scopes** with customer-managed keys in Key Vault | Per-tenant key without writing our own cryptography; disabling a tenant's key makes its blobs unreadable | **UNVERIFIED** detail — confirm encryption-scope + CMK behaviour at M0 |

---

## 2. Components and interfaces

### 2.1 Gateway (`gateway/`, NEW)

```
gateway/
  app.py          FastAPI app, router registration, middleware order
  auth.py         Entra token validation → Principal
  tenancy.py      DB session factory: SET LOCAL app.tenant_id / app.user_id
  audit.py        append-only audit writer (metadata only)
  errors.py       error envelope (§4.3)
  sse.py          server-sent-events helpers for /ask
  routes/
    matters.py documents.py ask.py reports.py watch.py
    operations.py settings.py feedback.py engine.py me.py health.py
```

**Middleware order (every request):**

1. Assign `request_id` (UUIDv7).
2. `auth.authenticate(request) -> Principal | 401`. Not applied to `/v1/health`.
3. `tenancy.open_session(principal)`: begin a transaction, then
   `SET LOCAL app.tenant_id = :tenant`, `SET LOCAL app.user_id = :user`.
4. `policy.decide(Request(tool=route_name, action=READ|WRITE, actor=user_id,
   tenant=tenant_id, matter=matter_id, purpose=route_name))` — reuse of
   `checker/mcp/policy.py`. `ATTEST` is never reachable from the gateway.
5. Handler.
6. `audit.write(...)` in the same transaction; commit.

```python
@dataclass(frozen=True)
class Principal:            # NEW, gateway/auth.py
    tenant_id: UUID         # our tenant id, mapped from the Entra tid
    entra_tid: str
    user_id: UUID
    email: str
    roles: frozenset[str]   # {"member"} or {"member", "admin"}
```

`auth.authenticate` accepts a bearer token only if **all** hold:
signature valid against Entra JWKS (cached, refreshed on unknown `kid`);
`iss` matches `https://login.microsoftonline.com/{tid}/v2.0`; `aud` is the gateway
API's application ID URI; `exp`/`nbf` valid with ≤ 60 s skew; `tid` is in
`tenants.entra_tid` with `status = 'active'` (the beta allow-list); the account is
a work account (personal Microsoft accounts carry a fixed consumer `tid` — reject
it explicitly). First sign-in of a user in an allowed tenant creates the `users`
row with role `member`; admins are set by us.

### 2.2 Engine access (unchanged engine, one wrapper)

```python
# gateway/routes/engine.py  NEW — thin pass-through for the 8 existing routes
def engine(method: str, path: str, body: dict | None) -> tuple[int, dict]:
    return checker.api.handle(method, path, body, generated_at=utc_now_iso())
```

The existing routes are exposed under `/v1/engine/*` unchanged, so the MCP
server, the CLI and the web app share one function and cannot drift.

### 2.3 Router: data classes and provider guard (`checker/router.py`, extended)

```python
PUBLIC = "PUBLIC"; CLIENT = "CLIENT"          # NEW
DATA_CLASSES = (PUBLIC, CLIENT)

@dataclass(frozen=True)
class Task:
    name: str
    modality: str
    consequence: str
    volume: int = 1
    data_class: str = CLIENT                  # NEW — fail closed when unlabelled

AZURE_OPENAI = "azure_openai"                 # NEW
AZURE_DOCINTEL = "azure_docintel"             # NEW

CLIENT_SAFE: frozenset[str] = frozenset({AZURE_OPENAI, AZURE_DOCINTEL})   # NEW
INDIA_REGIONS = frozenset({"centralindia", "southindia"})                 # NEW
```

Routing rule (pseudocode):

```
route(task, available, budget):
    options = PREFERENCE[(task.modality, task.consequence, task.data_class)]
    for (provider, model, why) in options:
        if provider not in available: continue
        if task.data_class == CLIENT and provider not in CLIENT_SAFE:
            continue                                   # never a candidate
        if provider in {AZURE_OPENAI, AZURE_DOCINTEL} and configured_region(provider) not in INDIA_REGIONS:
            raise NoRoute("provider configured outside India")
        if over_budget(...): ...                       # existing behaviour
        return Route(...)
    if task.data_class == CLIENT:
        raise NoRoute("no India-resident, zero-retention provider is available for client data")
    ... existing HIGH/LOW behaviour
```

The preference table gains a `data_class` key. `PUBLIC` rows keep today's
routing (Gemini Flash for public scans, Anthropic for public text). `CLIENT` rows:

| (modality, consequence, CLIENT) | Provider | Model |
|---|---|---|
| PAGE_IMAGE, * | `AZURE_DOCINTEL` | `prebuilt-layout` (or `prebuilt-read`) |
| TEXT, HIGH | `AZURE_OPENAI` | deployment name from `AZURE_OPENAI_DEPLOYMENT_HIGH` |
| TEXT, LOW | `AZURE_OPENAI` | deployment name from `AZURE_OPENAI_DEPLOYMENT_LOW` |

Deployment names are configuration, set at M0 from what the portal actually
offers in the region.

### 2.4 The Ask pipeline (`checker/pipeline.py`, NEW)

A single orchestrating function. It never decides law itself; every stage either
passes typed data forward or produces a **refusal**.

```python
@dataclass(frozen=True)
class AskInput:                       # NEW
    question: str                     # ≤ ask.MAX_QUESTION_CHARS
    as_of: date
    tenant_id: UUID
    matter_id: UUID
    facts: dict | None = None         # same shape ask.answer accepts
    provisions: tuple[str, ...] = ()
    document_ids: tuple[UUID, ...] = ()   # Vault documents in scope for this turn
    parent_turn_id: str | None = None

@dataclass(frozen=True)
class Refusal:                        # NEW
    code: str                         # one of REFUSAL_CODES (§2.4.1)
    reason: str                       # user-facing, on-voice
    stage: str
    detail: dict = field(default_factory=dict)
```

```
run(inp) -> Iterator[Event]:                     # events stream to SSE (§4.2)
  yield Stage(1, "scope + engine")
  turn = ask.answer(request_from(inp), generated_at=now)     # existing, deterministic
  #   ask.answer already calls ask_scope.read(question, provisions) and returns
  #   state "out_of_scope" with scope.refusal_for(key) — the pipeline reuses that
  #   decision rather than scoping a second time.
  #   → placedon.ask/0 turn: statute text, obligations, evidence_pack, law_version
  if turn["state"] == "out_of_scope":
      yield Refusal(OUT_OF_SCOPE, turn["reason"]); yield Final(turn); return

  yield Stage(2, "retrieve")
  vault_spans = vault.search(inp.tenant_id, inp.matter_id, inp.question,
                             document_ids=inp.document_ids, k=VAULT_K)   # NEW, §2.5
  sources = [lawyer_summary.engine_source(turn)] +
            [lawyer_summary.document_source(s.doc_ref, s.text) for s in vault_spans]

  if nothing_to_narrate(turn, vault_spans): yield Final(turn); return    # no model call

  yield Stage(3, "sufficiency")
  verdict = sufficiency.rate(inp.question, sources, route=Task("sufficiency", TEXT, LOW, data_class=CLIENT))
  if verdict.sufficient is not True:                # False, None, or unparsable → refuse
      yield Refusal(CONTEXT_INSUFFICIENT, missing_sentence(verdict.missing)); yield Final(turn); return

  yield Stage(4, "narrate + trace")
  summary = lawyer_summary.summarise(sources, question=inp.question, client=azure_client, model=deployment_high)
  #   existing: blocks → check_blocks → every clause TRACED or refused with a verdict

  for s in summary.sentences:
      yield Clause(text=s.text, verdict=s.verdict, anchors=s.anchors, reasons=s.reasons)

  yield Final(merge(turn, summary))                # placedon.ask/0, additive fields only
```

Invariants (each has a test):

1. `ask.answer` runs first and its output is never modified, only extended.
2. Statute text reaches the narrator **only** through `engine_source(turn)`; law
   assertions citing a `DOCUMENT` source are refused (`LAW_FROM_DOCUMENT`,
   existing).
3. The sufficiency gate can only withhold. Any exception, timeout or unparsable
   output counts as insufficient.
4. No clause is dropped silently: every sentence reaches the client with its verdict.
5. Vault text reaches the model as a structured content block, never concatenated
   into a prompt string; the system prompt carries
   `prompt_safety.UNTRUSTED_CLAUSE` (CLAUDE.md, both halves).

#### 2.4.1 Refusal codes

| Code | Raised by | Meaning to the user |
|---|---|---|
| `OUT_OF_SCOPE` | `ask.answer` via `ask_scope.read` | This body of law is not held; names what would be needed |
| `FACT_MISSING` | `ask.answer` / obligations | A company fact needed to decide is missing |
| `RULE_NOT_HELD` | obligations `blocked_by` | A delegated rule the provision depends on is not held |
| `INSTRUMENT_NOT_ATTESTED` | admission / thresholds | The figure rests on an instrument not yet attested |
| `CONTEXT_INSUFFICIENT` | sufficiency gate | What was found does not answer the question; names what is missing |
| `CLAUSE_UNTRACED` | tracing | Per clause, with the `lawyer_summary` verdict |
| `PROVIDER_NOT_PERMITTED` | router `NoRoute` | No India-resident, zero-retention model is available right now |
| `BUDGET_EXHAUSTED` | `backend/budget.py` | The tenant's model budget for the period is spent |

A **transport or server failure is not a refusal** and is returned as an error
(§4.3), matching the frontend's `EngineResult<T>` rule.

### 2.5 Retrieval

**Statute:** unchanged — `ask.answer` uses `retrieve.retrieve` /
`structural_retrieve` over structural chunks, with `law_version` from
`evidence_pack` stating the point in time.

**Vault (NEW, `checker/vault_search.py` + SQL):**

```sql
-- candidate spans for one question, one matter, one tenant (RLS applies too)
SELECT p.document_id, p.page_no, p.span_start, p.span_end,
       ts_rank_cd(p.tsv, q) AS score
FROM   document_passages p,
       websearch_to_tsquery('english', :question) q
WHERE  p.matter_id = :matter_id
  AND  (:doc_ids IS NULL OR p.document_id = ANY(:doc_ids))
  AND  p.tsv @@ q
ORDER  BY score DESC
LIMIT  :k;
```

- Passages are built at extraction time along structure where detectable
  (headings, numbered clauses, resolutions), else ~1,200-character windows on
  sentence boundaries, each with exact character offsets into the page text.
- Passage **text is read from the page text by offset** when building a
  `Source`, so the span the model cites is byte-identical to what is stored.
- `english` configuration first. Hindi/regional text: flagged by script
  detection and **not** searched in beta (stated in "Known limitations").
- Dense retrieval: only after it beats BM25 on the enlarged eval under
  `router.py`'s `adopt_when` rule (PLAN_16 §6.5).

### 2.6 Sufficiency gate (`checker/sufficiency.py`, NEW)

After Joren et al. (ICLR 2025): a model rates whether the context suffices.

- **Input:** question + the same `sources` the narrator will see (engine source
  first).
- **Output schema (strict JSON):**
  `{"sufficient": true|false, "missing": [string, ...]}` — `missing` names
  facts/provisions absent from the context, in ≤ 20 words each.
- **Parser:** rejects any other shape → treated as insufficient.
- **Model:** `Task("sufficiency", TEXT, LOW, data_class=CLIENT)`.
- **Logging:** `(turn_id, sufficient, len(missing), model, latency)` — no text.
- **Evaluation:** agreement with lawyer labels on the pilot set; the gate's
  false-refusal rate is reported with a Wilson interval before it is trusted.
- **Later:** the paper combines the label with the model's self-rated confidence
  in a logistic regression. That needs labelled data (M12); beta ships the binary
  gate only.

### 2.7 Certification (`checker/conformal.py`, NEW — shipped disabled)

Mohri & Hashimoto's back-off, specified now so the pilot collects the right data:

```
calibrate(examples, alpha):
    # each example: list of (claim_score, is_true) for one answer, labelled by a lawyer
    r_i = max(score for (score, true) in ex if not true) or -inf   # per answer
    n   = len(examples)
    k   = ceil((n + 1) * (1 - alpha))
    if k > n: raise Underpowered(n, alpha)          # same spirit as calibration_contract
    tau = sorted(r_i)[k - 1]
    return tau

serve(claims, tau): keep claims with score > tau; the rest are refused as
                    CLAUSE_UNTRACED-style "withheld: below certified threshold"
```

- **Score function:** start with the tracing coverage from `lawyer_summary`
  (fraction of a clause's distinctive terms present in its span). Record it for
  every clause from day one of the pilot.
- **Flag:** `CERTIFY_ENABLED=false` until n ≥ 19 (α = 0.05) *and* the
  independent audit sample reaches 59 clean answers (PLAN_16 C1). The UI never
  shows a percentage.

### 2.8 Vault storage and extraction

**Upload sequence:**

```
web → POST /v1/matters/{m}/documents:upload-url {filename, size, sha256_client}
gateway: check member of m; size ≤ MAX_UPLOAD_BYTES; content type in allow-list
         INSERT documents(state='awaiting_upload') → document_id
         issue write-only SAS for  tenant-{t}/{m}/{document_id}  (expiry 10 min,
         encryption scope = tenant-{t})
web → PUT blob (direct to Azure Blob)
web → POST /v1/matters/{m}/documents/{d}:complete
gateway: verify blob exists, size and sha256 (read via managed identity);
         UPDATE documents SET state='uploaded'; enqueue jobs:
         verify_signature(d), extract_text(d)
worker extract_text: text PDF → checker.pdf_pages.extract_pages
                     scan / image → Azure Document Intelligence (Task PAGE_IMAGE, CLIENT)
                     → document_pages rows (+ ocr=true where applicable, never repaired)
                     → enqueue index_passages(d)
worker index_passages: passages + tsvector; UPDATE documents SET state='ready'
```

**Keys and deletion:**

- One Key Vault key per tenant; one Blob encryption scope per tenant bound to it.
- Postgres uses a server-level customer-managed key (all tenants).
- **Delete document:** delete blob, delete rows, audit (ids only).
- **Delete tenant:** disable then delete the tenant key (blobs unreadable at
  once), delete blobs and rows, audit. **Stated limit:** Postgres point-in-time
  backups keep deleted rows until the backup retention window expires (7–35 days,
  set at M0); the DPA must say so.

### 2.9 Job runner (`gateway/worker.py`, NEW)

```sql
-- claim one job (worker role; see §3.3 for its policy on jobs)
UPDATE jobs SET state = 'running', attempts = attempts + 1, locked_at = now()
WHERE id = (
  SELECT id FROM jobs
  WHERE state = 'queued' AND run_after <= now()
  ORDER BY priority DESC, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1)
RETURNING *;
```

- The worker then opens a **second** transaction with
  `SET LOCAL app.tenant_id = job.tenant_id` for the actual work, so every read and
  write in the job is tenant-scoped by RLS.
- Idempotency: `jobs.idempotency_key` unique (e.g. `extract_text:{document_id}`);
  handlers are re-runnable.
- Retries: exponential back-off up to `max_attempts` (default 3), then
  `state='dead'` + an inbox item for our operators, never silent.
- Scheduled jobs (watchers): a `schedules` table and a tick that enqueues due
  jobs; the watchers keep their log-then-state ordering (RT-08).

### 2.10 Operations store

Maps `checker/operations.py` dataclasses 1:1 onto tables (§3.2). State machine
for a requirement:

| From | To | Who may do it | Condition |
|---|---|---|---|
| OPEN | SATISFIED | a **human user** for BLOCKING; any user for IMPORTANT/CONTEXT | evidence recorded meeting `minimum_evidence` |
| OPEN | BLOCKED | system or user | source not held / not permitted; reason required |
| BLOCKED | OPEN | user | reason required |
| SATISFIED | OPEN | user | reopened, reason required |

"Human" is enforced by the principal type: service and MCP identities carry no
`member` role for writes, and the route checks `principal.kind == "user"`. The
evidence budget is computed from rows, never stored.

### 2.11 Forensics report (`checker/forensics.py`, NEW)

```json
{
  "schema": "placedon.forensics/0",
  "document": {"id": "...", "sha256": "...", "pages": 18, "ocr_pages": [3, 4]},
  "generated_at": "...", "uses_model": false,
  "sections": [
    {"key": "authenticity", "status": "VERIFIED|PARTIALLY_VERIFIED|UNVERIFIED|POTENTIAL_ISSUE|INAPPLICABLE",
     "findings": [{"statement": "...", "evidence": {"source": "...", "span": [s, e]}, "rule_id": "...", "confidence": "..."}],
     "not_checked": ["..."]},
    {"key": "identity_consistency", "...": "..."},
    {"key": "currency", "...": "..."},
    {"key": "values", "...": "..."},
    {"key": "counterparties", "...": "... CANDIDATES only"}
  ],
  "not_checked": ["..."]
}
```

| Section | Produced by (existing) |
|---|---|
| authenticity | `pdf_signature.py`, `revocation.py`, `doc_verification.py` |
| identity_consistency | `document_date.py`; the CIN self-contradiction check (`beaf184`); `extraction_schema.CIN_GRAMMAR` |
| currency | `checker/ss/` scanner; `staleness.py` |
| values | `document_extract.py`, `field_binding.py` (value-support, misbinding) |
| counterparties | `feeds/ibbi.py`, `feeds/ofac_sdn.py` screens → candidates for a person |

Every finding carries source, date, rule ID, reasoning and confidence (CLAUDE.md).
Unknown document type → classification uncertainty only.

### 2.12 MCP authorisation

Upgrade `checker/mcp/server.py` to the 2026-07-28 specification over HTTP: the
server is an OAuth 2.1 resource server; an unauthenticated request gets `401` with
a pointer to its Protected Resource Metadata (RFC 9728); tokens are Entra tokens
whose audience is the MCP resource; identity comes from the token, not from
`_actor`/`_tenant` arguments (those remain for local stdio only). Tools remain
read-only and pass through the same `policy.decide`.

### 2.13 Web app (`placedon-claude-legal-3300`, `/app`, NEW)

| Route | Purpose |
|---|---|
| `/app` | Matter list |
| `/app/m/[matter]` | Matter: documents, threads, members |
| `/app/m/[matter]/ask` | Chat with streaming answer + evidence panel |
| `/app/m/[matter]/d/[doc]` | Document viewer + forensics report |
| `/app/inbox` | Watch inbox: Gazette / IBBI / OFAC operations |
| `/app/settings` | Retention, consent, members (admin), delete data |
| `/app/limits` | Known limitations |

- Sign-in: an OIDC library against Entra, obtaining an access token for the
  gateway API scope. Choose between Auth.js and `@azure/msal-node` at M10 after
  checking compatibility with this Next.js version; record the reason.
- All gateway calls from server components / route handlers; the browser only
  talks to our own origin. SSE from the gateway is proxied by a route handler.
- Rendering rules from `web/assistant/contract.md` §1 and AGENTS.md: refusals use
  the reserved abstain grey and a text label (never colour alone); errors use a
  distinct error state.

---

## 3. Data model

### 3.1 Conventions

- `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`; `created_at timestamptz NOT NULL DEFAULT now()`.
- Every tenant-owned table has `tenant_id uuid NOT NULL REFERENCES tenants(id)`.
- Two database roles: `app` (gateway) and `worker`. Neither has `BYPASSRLS`.
  Migrations run as a separate owner role.

### 3.2 Tables (DDL, abridged to the columns that matter)

```sql
CREATE TABLE tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entra_tid text UNIQUE NOT NULL,
  name text NOT NULL,
  status text NOT NULL CHECK (status IN ('active','suspended','deleting')),
  retention_days int NOT NULL DEFAULT 365 CHECK (retention_days BETWEEN 1 AND 3650),
  key_ref text NOT NULL,                       -- Key Vault key id for this tenant
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  entra_oid text NOT NULL, email text NOT NULL,
  role text NOT NULL CHECK (role IN ('member','admin')),
  UNIQUE (tenant_id, entra_oid));

CREATE TABLE matters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  name text NOT NULL, company_cin text,        -- CIN checked against extraction_schema grammar
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE matter_members (                  -- the ethical wall
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id),
  PRIMARY KEY (matter_id, user_id));

CREATE TABLE documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE,
  filename text NOT NULL, content_type text NOT NULL, size_bytes bigint NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('awaiting_upload','uploaded','extracting','ready','failed','deleted')),
  blob_path text NOT NULL,
  expires_at timestamptz NOT NULL,             -- from tenants.retention_days
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE document_pages (
  tenant_id uuid NOT NULL, matter_id uuid NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_no int NOT NULL, text text NOT NULL,
  ocr boolean NOT NULL DEFAULT false,          -- OCR text is flagged, never repaired
  script text,                                 -- detected script, e.g. 'Latn', 'Deva'
  PRIMARY KEY (document_id, page_no));

CREATE TABLE document_passages (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL, matter_id uuid NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_no int NOT NULL, span_start int NOT NULL, span_end int NOT NULL,
  tsv tsvector NOT NULL,
  CHECK (span_end > span_start));
CREATE INDEX ON document_passages USING gin (tsv);
CREATE INDEX ON document_passages (matter_id, document_id);

CREATE TABLE threads (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
  matter_id uuid NOT NULL REFERENCES matters(id) ON DELETE CASCADE, created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE turns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
  matter_id uuid NOT NULL, thread_id uuid NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  turn_id text NOT NULL,                       -- placedon.ask/0 turn_id
  body jsonb NOT NULL,                         -- the full served turn
  created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE watchlist_companies (tenant_id uuid NOT NULL, cin text NOT NULL, name text,
  added_by uuid NOT NULL, PRIMARY KEY (tenant_id, cin));

CREATE TABLE operations (
  id text PRIMARY KEY,                         -- operations.Operation.operation_id
  tenant_id uuid NOT NULL, intent text NOT NULL, trigger jsonb NOT NULL,
  companies text[] NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL);

CREATE TABLE requirements (
  id text PRIMARY KEY,                         -- Requirement.requirement_id
  tenant_id uuid NOT NULL, operation_id text NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
  question text NOT NULL, obligation_id text NOT NULL, provision text NOT NULL,
  specialist text NOT NULL CHECK (specialist IN ('LEGAL_RESEARCH','CORPORATE_DATA','FINANCIAL_DATA','HUMAN_REVIEW')),
  criticality text NOT NULL CHECK (criticality IN ('BLOCKING','IMPORTANT','CONTEXT')),
  minimum_evidence text NOT NULL, depends_on text[] NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('OPEN','SATISFIED','BLOCKED')), note text NOT NULL DEFAULT '');

CREATE TABLE evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
  requirement_id text NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
  source text NOT NULL, sha256 text, submitted_by uuid NOT NULL,
  submitted_at timestamptz NOT NULL DEFAULT now(), note text NOT NULL);

CREATE TABLE consents (                        -- evaluation / training use; off by default
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
  purpose text NOT NULL CHECK (purpose IN ('evaluation','training')),
  matter_ids uuid[] NOT NULL, granted_by uuid NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now(), withdrawn_at timestamptz);

CREATE TABLE feedback (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid NOT NULL,
  turn_id text NOT NULL, clause_index int, rating text CHECK (rating IN ('correct','wrong','unhelpful')),
  correction text, user_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE audit_log (
  id bigserial PRIMARY KEY, tenant_id uuid, request_id uuid NOT NULL,
  actor uuid, route text NOT NULL, action text NOT NULL, verdict text NOT NULL,
  object_ids text[] NOT NULL DEFAULT '{}',     -- ids only, never content
  at timestamptz NOT NULL DEFAULT now());

CREATE TABLE jobs (
  id bigserial PRIMARY KEY, tenant_id uuid NOT NULL, kind text NOT NULL,
  args jsonb NOT NULL, idempotency_key text UNIQUE NOT NULL,
  state text NOT NULL CHECK (state IN ('queued','running','done','dead')),
  priority int NOT NULL DEFAULT 0, attempts int NOT NULL DEFAULT 0, max_attempts int NOT NULL DEFAULT 3,
  run_after timestamptz NOT NULL DEFAULT now(), locked_at timestamptz, last_error text);
```

### 3.3 Row-level security

```sql
-- for every tenant-owned table T (generated by the migration runner):
ALTER TABLE T ENABLE ROW LEVEL SECURITY;
ALTER TABLE T FORCE ROW LEVEL SECURITY;           -- applies to the table owner too
CREATE POLICY tenant_isolation ON T
  USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
-- current_setting(..., true) is NULL when unset → the comparison is NULL → zero rows.

-- ethical wall on matter-scoped tables (documents, document_pages, document_passages,
-- threads, turns): a RESTRICTIVE policy is ANDed with the tenant policy.
CREATE POLICY matter_wall ON documents AS RESTRICTIVE
  USING (EXISTS (SELECT 1 FROM matter_members mm
                 WHERE mm.matter_id = documents.matter_id
                   AND mm.user_id = current_setting('app.user_id', true)::uuid));

-- the audit log is append-only for both application roles
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM app, worker;

-- the worker may claim any queued job, but does its work under SET LOCAL app.tenant_id
CREATE POLICY worker_claim ON jobs TO worker USING (true);
```

Tests (M4) cover: cross-tenant SELECT/UPDATE/DELETE on every table return zero
rows; unset `app.tenant_id` → zero rows; a non-member sees no matter content;
`UPDATE audit_log` is refused; **negative control:** dropping `tenant_isolation`
on one table turns the suite red.

The worker does matter-scoped work for system tasks (extraction, indexing), not
on behalf of a user, so the matter wall must admit it: set `app.user_id` to a
per-tenant system user that is added to every matter's members at matter
creation, and record in audit that the actor was the system.

---

## 4. API

### 4.1 Endpoints (gateway, all under `/v1`, all authenticated except health)

| Method | Path | Body → Response | Notes |
|---|---|---|---|
| GET | `/health` | → `{status, version, commit, corpus_version}` | no auth |
| GET | `/me` | → principal, tenant, role | |
| GET, POST | `/matters` | `{name, company_cin?}` → matter | creator becomes member |
| GET | `/matters/{m}` | → matter + members | member only |
| POST | `/matters/{m}/members` | `{user_id}` | admin only |
| POST | `/matters/{m}/documents:upload-url` | `{filename, size, sha256}` → `{document_id, upload_url, expires_at}` | |
| POST | `/matters/{m}/documents/{d}:complete` | → document | verifies size + sha256 |
| GET | `/matters/{m}/documents` | → list | |
| DELETE | `/matters/{m}/documents/{d}` | → 204 | audit |
| GET | `/matters/{m}/documents/{d}/report` | → `placedon.forensics/0` | 409 until `ready` |
| POST | `/matters/{m}/ask` | `AskRequest` → **SSE** (§4.2) | `Accept: text/event-stream` |
| GET | `/matters/{m}/threads[/{t}]` | → threads / turns | |
| POST | `/feedback` | `{turn_id, clause_index?, rating, correction?}` | stored; used for eval only with consent |
| GET, POST, DELETE | `/watchlist[/{cin}]` | `{cin, name?}` | CIN grammar validated |
| GET | `/inbox` | → operations with evidence budget | |
| GET | `/operations/{id}` | → operation + requirements | |
| POST | `/requirements/{id}/evidence` | `{source, sha256?, note}` | |
| POST | `/requirements/{id}:satisfy` | `{note}` | human user only for BLOCKING |
| GET, PUT | `/settings/retention` | `{retention_days}` | admin |
| GET, PUT | `/settings/consent` | `{purpose, matter_ids}` / withdraw | admin |
| POST | `/tenant:delete` then `/tenant:delete-confirm` | two-step, admin | crypto-shred then delete |
| * | `/engine/{route}` | the 8 existing engine routes, unchanged | read-only |

`AskRequest` = the existing `ask.REQUEST_KEYS` (`question, context, facts,
figures, provisions, as_of, parent_turn_id`) plus `thread_id?` and
`document_ids?`. Unknown keys are refused (existing rule).

### 4.2 Streaming events for `/ask`

```
event: stage     data: {"n": 1, "what": "scope"}
event: refusal   data: {"code": "CONTEXT_INSUFFICIENT", "reason": "...", "stage": "sufficiency", "detail": {...}}
event: clause    data: {"i": 0, "text": "...", "verdict": "TRACED", "anchors": ["engine [120:188]"], "reasons": []}
event: evidence  data: {"spans": [{"source": "...", "kind": "ENGINE|DOCUMENT", "start": 120, "end": 188,
                                  "version": "...", "valid_from": "...", "valid_to": null}]}
event: done      data: <the full placedon.ask/0 turn, with additive fields>
event: error     data: {"code": "server_error", "request_id": "..."}
```

`done` is always the last event of a successful stream and carries the complete
turn, so a client that ignores the intermediate events still renders correctly.

### 4.3 Error envelope

```json
{"error": {"code": "bad_request|unauthenticated|forbidden|not_found|conflict|rate_limited|server_error",
           "message": "operator-facing, never legal copy",
           "detail": "names the offending field on a 400",
           "request_id": "..."}}
```

These map one-to-one onto the frontend's `EngineErrorKind`. A refusal is **never**
sent as an error, and an error is never rendered as a refusal.

---

## 5. Security design

| Threat | Control | Test / evidence |
|---|---|---|
| Tenant A reads tenant B's data | RLS on every tenant table; `FORCE ROW LEVEL SECURITY`; per-request `SET LOCAL` | M4 isolation suite + negative control |
| Lawyer reads a walled matter | `matter_wall` restrictive policy | M4 |
| Forged or replayed token | JWKS signature, `iss`, `aud`, `exp`, allow-listed `tid`; consumer `tid` rejected | M3 |
| Prompt injection inside a customer document | Structured content blocks; `UNTRUSTED_CLAUSE`; tracing refuses unsupported clauses; the document is never edited | M7 test with an injected instruction |
| Image-borne injection (text inside a scan) | **Known limitation** (CLAUDE.md): string guards do not reach pixels; OCR text treated as untrusted; imperative sentences in scans flagged for review | Documented; not solved in beta |
| Model provider retains client data | Router `CLIENT_SAFE`; India region guard; modified abuse monitoring approval before go-live | M2 tests; M0 approval record |
| Agent writes or attests | No write/attest MCP tools; `policy.decide` refuses `ATTEST`; BLOCKING close requires a human principal | Existing MCP tests + M6 |
| SSRF / unsafe fetch in feeds | `checker/robots.py` (TLS verified, robots enforced, fail closed); redirect allow-lists (`feeds/common/fetch.py`) | Existing red-team fixes RT-04/05/14 |
| Secrets in code or logs | Managed identity; Key Vault; logging filter drops bodies; audit stores ids only | Log-scrubbing test |
| Supply chain | Pinned `requirements*.txt`; new dependencies only with a stated reason; CI on every push | CLAUDE.md rule; M1 |
| Data kept after deletion | Crypto-shred tenant key; delete rows/blobs; backup window disclosed | M5 test + DPA text |

---

## 6. Observability

- **Logs:** structured JSON with `request_id`, `tenant_id`, route, status,
  latency, stage timings, model deployment, token counts, refusal code. **Never**
  question text, document text, prompts or completions.
- **Metrics:** requests by route/status; p50/p95 latency per pipeline stage;
  refusal rate by code; sufficiency-gate insufficient rate; traced-clause rate;
  model tokens and ₹ cost per tenant (`backend/budget.py`); job queue depth and
  dead jobs; watcher last-success time.
- **Alerts:** any cross-tenant test failure in CI; dead jobs > 0; watcher silent
  > 26 h; error rate > 2% over 15 min; per-tenant budget at 80%.
- **Audit review:** a weekly query for denied requests and admin actions.

---

## 7. Performance and cost budgets

Targets are **INFERRED** starting points, to be measured at M11 and replaced with
real numbers:

| Stage | Target (p95) |
|---|---|
| Auth + policy + audit | 50 ms |
| `ask.answer` (deterministic) | 300 ms |
| Vault full-text search | 150 ms |
| Sufficiency gate (one model call) | 3 s |
| Narration + tracing (first clause streamed) | 6 s |
| Document extraction, 20-page text PDF | 30 s (async) |

Cost control: a per-tenant monthly ₹ budget in `backend/budget.py`; a request
that would exceed it is refused with `BUDGET_EXHAUSTED` (never degraded to a
non-safe provider). Estimate tokens from `router._SHAPE` until measured.

---

## 8. Testing strategy

| Layer | What | Where | Gate |
|---|---|---|---|
| Unit self-tests | Every module's `_test()` | `scripts/run_tests.sh` | pre-commit + CI |
| Contract | `placedon.ask/0` fixtures; `placedon.forensics/0` fixtures; SSE event order | `scripts/assistant_contract.py`, NEW contract tests | CI |
| Isolation | RLS and matter walls, with negative control | `db/tests/` NEW | CI (Postgres service container) |
| Router | every (data_class × provider × region) cell | `checker/router.py` | CI |
| Adversarial | 18 real-model cases scored without a model; add injection-in-Vault cases | `eval/realrun/` | before each release |
| Kill tests | mutate one rule, suite must go red | `lawyer_summary.py` pattern, extended to RLS and router | CI |
| Acceptance (UI) | `web/assistant/tools/accept.mjs` pattern for `/app` | frontend repo | before each release |
| Load | 20 concurrent asks, 50 concurrent uploads | `scripts/load_beta.py` NEW | M11 |
| Red team | independent agent against M3–M10 | `docs/research/RED_TEAM_BETA.md` | M11 |
| Pilot eval | preregistered; error bars (Miller) | `docs/PILOT_PREREG.md` | M12 |

---

## 9. Environments and configuration

| Env | Engine | DB | Models | Data |
|---|---|---|---|---|
| local | in-process | local Postgres (container) | stubs by default; Azure with explicit env | public test documents only |
| staging | in-process | Azure Postgres (staging) | Azure OpenAI (India) | public + synthetic only |
| prod | in-process | Azure Postgres (prod) | Azure OpenAI (India), approved for modified abuse monitoring | customer data |

Environment variables (all documented in `.env.example`; secrets from Key Vault
in Azure):

```
THEMIS_ENV=local|staging|prod
DATABASE_URL                      (local only; Azure uses managed identity)
ENTRA_TENANT_ALLOWLIST_SOURCE=db
ENTRA_API_AUDIENCE=api://placedon-gateway
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_REGION
AZURE_OPENAI_DEPLOYMENT_HIGH, AZURE_OPENAI_DEPLOYMENT_LOW
AZURE_DOCINTEL_ENDPOINT, AZURE_DOCINTEL_REGION
BLOB_ACCOUNT_URL
KEYVAULT_URL
MAX_UPLOAD_BYTES=52428800
VAULT_K=12
CERTIFY_ENABLED=false
TENANT_MONTHLY_BUDGET_INR
```

---

## 10. Repository layout after the beta

```
placedon-law-backend/
  checker/            engine (Shell 0–2); adds pipeline.py, sufficiency.py,
                      conformal.py, forensics.py, vault_search.py,
                      azure_model.py, azure_docintel.py
  checker/mcp/        MCP server (HTTP + OAuth resource server)
  gateway/            FastAPI app, auth, tenancy, audit, routes, worker     NEW
  db/migrations/      numbered .sql files + runner                         NEW
  db/tests/           isolation suite                                      NEW
  infra/              Bicep templates                                      NEW
  scripts/            existing tools + themis_cli.py, load_beta.py
  .github/workflows/  tests.yml (from ci/tests.yml.pending)

placedon-claude-legal-3300/
  src/app/(marketing)/   existing site
  src/app/app/           logged-in app                                     NEW
  src/lib/gateway/       server-only gateway client (EngineResult pattern) NEW
```

---

## 11. Migration from today

| Today | After |
|---|---|
| `scripts/serve_api.py` on 127.0.0.1:8020 | local development only; production uses the gateway |
| `eval/realrun/azure_model.py` | production adapter `checker/azure_model.py`; eval imports it |
| Web app `src/lib/engine/*` (6 routes, mock/http) | kept for the marketing product pages; the app uses `src/lib/gateway/*` |
| `web/assistant/` prototype | stays as the contract's reference renderer and acceptance target |
| `operations.py` in-memory | persisted (§2.10); in-memory path kept for `themis_slice.py` |
| MCP over stdio with claimed identity | HTTP + OAuth for remote; stdio kept for local |

---

## 12. Open technical questions (decide at the named milestone)

| # | Question | When |
|---|---|---|
| T1 | Exact Azure OpenAI models available as regional Standard deployments in Central/South India | M0 |
| T2 | Blob encryption scopes with per-scope CMK: confirm key-disable makes blobs unreadable immediately | M0/M5 |
| T3 | Postgres backup retention window (7–35 days) and its DPA wording | M4 |
| T4 | JWT validation library for the gateway (or stdlib + pinned crypto) | M3 |
| T5 | Postgres driver (`psycopg` 3 is the default candidate) | M4 |
| T6 | OIDC library for the Next.js app, compatible with its Next.js version | M10 |
| T7 | Whether Claude joins `CLIENT_SAFE` (India in-country inference live + zero retention) | M11 |
| T8 | Hindi/regional-language Vault search | after beta |
