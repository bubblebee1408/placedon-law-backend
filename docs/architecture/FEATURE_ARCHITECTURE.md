# Feature architecture — how each feature is built

Written 2026-10-02 against `main` at b8beaad. One card per feature in
[PLATFORM_FEATURES_AND_INTEGRATIONS.md](PLATFORM_FEATURES_AND_INTEGRATIONS.md) §1 (F1–F33):
where the request enters, the steps it runs, the files that do the work, the tables it writes,
the models and sources it may use, the gate that stops a wrong answer, what is left to build,
and the test that proves it. Pipeline, rings and hosting are in [ARCHITECTURE.md](ARCHITECTURE.md);
this page does not repeat them. Where this page and the code disagree, the code wins.

---

## 0. The shared spine every feature uses

Every feature is the same seven layers with different steps in the middle. A card below only
names what is specific to it.

| Layer | Component | Files | What it guarantees |
|---|---|---|---|
| L1 Surface | REST `/v2`, MCP, CLI, web `/app` | `gateway/verbs.py`, `gateway/app.py`, `gateway/cli.py`, `checker/mcp/` | One verb entry → all three surfaces; write verbs never on MCP |
| L2 Gate | Auth, tenant, role, limits, audit | `gateway/auth.py`, `roles.py`, `limits.py`, `audit.py` | Key → tenant; FORCE RLS on every tenant table; metadata-only, hash-chained audit |
| L3 Plan | Intake → fixed plan | `agents/intake.py`, `agents/plans.py` | A model may **pick** a plan from the table; it can never invent steps |
| L4 Run | Durable queue + workers | `gateway/jobs.py`, `gateway/worker.py`, `agents/runtime.py`, `agents/state.py` | SKIP LOCKED, idempotent steps, 3 attempts → dead letter, saga cancel |
| L5 Engine | Law, dates, retrieval | `checker/scope.py`, `as_of.py`, `text_search.py`, `obligations.py`, `events.py` | Code decides law and dates (Ring 0, never imports a model) |
| L6 Model gateway | Router, cascade, cost | `checker/router.py`, `model_cascade.py`, `backend/` | Data class → allowed region; budget caps; UNPRICED never ₹0 |
| L7 Verify + record | Quote check, critic, envelope, human gate | `quoted_span.py`, `ground_span.py`, `entailment_gate.py`, `critic.py`, `gateway/envelope.py`, `reviews.py` | No sentence ships without a byte-matched quote; critic removes, never adds; lawyer sign-off for VERIFIED |

Status words: **BUILT** · **PARTIAL** · **TODO** · **NEEDS PERMISSION** · **NOT DOING**.

---

## 1. Ask and research

### F1 Assistant — BUILT
- **Entry:** `conversation.send` / `ask` (MCP `themis.ask`); web `/app` Ask screen.
- **Flow:** intake → scope check (`ask_scope.py`, refuses DECLARED bodies by name) → answer cache
  (`answer_cache.py`, keyed on question + corpus hash) → retrieve (`text_search.py`, BM25 + IDF)
  → model drafts sentences → each sentence's quote byte-matched to the held provision → critic
  → envelope (ANSWERED / PARTIAL / NEEDS_LAWYER / ABSTAINED).
- **Data:** `conversations`, `messages`, `runs`, `run_steps`, `citations`, `answer_cache` (migrations 002, 010, 014).
- **Models:** extraction/phrasing on the small model; escalate to the large one only when the verifier rejects.
- **Gate:** no quote → sentence dropped; nothing left → ABSTAINED, never an unquoted answer.
- **Next:** `law_versions` on every run (T1).
- **Proof:** gold set dev split (`eval/goldset/run.py`); refusal rows 16/17.

### F2 Knowledge — multi-domain research — BUILT (stand-in phrasing until live model, B1)
- **Entry:** `research.multi` verb — REST `POST /v2/research/multi`, MCP (read-only) and CLI, all from the one verb table; `ask` still covers one body. A dedicated verb, not a branch of `ask`: `conversation.send` derives its body table from `ask`'s body-level shape (`_bodies_from_ask`, which re-reads `ask_scope` and has no per-State notion), so the per-State supervisor shape lives on its own verb and leaves `ask`/`conversation.send` untouched.
- **Flow:** intake extracts subjects → event/body map (`events.py`, `claim_bodies.py`) → one
  **researcher worker per (body, State)**, in parallel on the queue → each returns provisions
  with quotes or a named refusal → blackboard → critic → synthesis (code assembles, model phrases).
- **Data:** a run with N child jobs; blackboard rows in `run_steps` (typed JSON, schema-validated).
- **Gate:** only HELD bodies can produce statements of law; DECLARED → refusal row, never a guess.
- **Next:** the live model that only PHRASES the verified quote (B1); the frontend screen for compound answers. The verb is reachable now; what is deferred is swapping the deterministic held-corpus stand-in for a served model.
- **Built (stand-ins):** `agents/multi_supervisor.py` — decompose by (body, State), held-body workers run
  in parallel (injected executor; the gate's is a thread pool, production rides the job queue), each result
  verified before the blackboard (`multi_runner`), code synthesis, named refusals for not-held bodies, and
  case law as LICENSED supporting authority (never VERIFIED). Done-when passes: the Bengaluru/Mumbai lease +
  Singapore-allotment question returns PARTIAL with the Companies Act answered+quoted and FEMA + each State's
  stamp duty refused by name. The plan validator is `agents/multi_plan.validate` (code).
- **Reachable (07-10-2026):** proven over HTTP, not a direct ctx call — a `TestClient` POST of the done-when question to `/v2/research/multi` returns PARTIAL with the Companies Act part ANSWERED and byte-quoted, FEMA NOT_HELD, Karnataka + Maharashtra stamp duty named (NEED_FACT), one section per (body, State), and the plan (workers, bodies, States) both in the response and, step by step, in `runs.trace`. Held worker/verifier are the deterministic held-corpus stand-ins (no model, no key); the served model that phrases the quote arrives with B1.
- **Proof:** a question touching a held and a declared body returns PARTIAL with exactly one refusal row naming the declared body.

### F3 Central/State resolver — BUILT (triage; Seventh-Schedule basis UNVERIFIED)
- **Entry:** internal step after intake; no verb of its own.
- **Flow:** subject → new module `checker.jurisdiction` table lookup → CENTRAL / STATE / CONCURRENT;
  STATE without State or date → `NEED_FACT`.
- **Data:** the table is a reviewed file (like `events.py`); every row cites the Seventh-Schedule
  entry it rests on, acquired as held text first.
- **Gate:** a model may suggest the State from an address; code confirms it against the user's facts; mismatch shown.
- **Proof:** "stamp duty on a lease" with no State returns NEED_FACT("which State?"), never an answer.
- **Built:** `checker/jurisdiction.py` (routing only; every row's constitutional basis is UNVERIFIED
  until the Seventh Schedule is acquired and counsel-reviewed). Bengaluru→Karnataka, Mumbai→Maharashtra;
  a State topic with no State OR no date → NEED_FACT.

### F4 Law on a past date — BUILT (Companies Act)
- **Entry:** any ask with `as_of`.
- **Flow:** `as_of.py` reconstructs the provision text for the date from the amendment chain
  (`amendment.py`, `commencement.py`) → retrieval runs over that text, not today's.
- **Gate:** if reconstruction for that date is not EXACT (substituted span without witness) → the answer says so.
- **Proof:** `scripts/prove_temporal.py` — 6/6 boundaries on s.177, s.447, s.35.

### F5 Case law — NEEDS PERMISSION
- **Entry:** `case_law` worker inside F2; `sources.search` with tier LICENSED.
- **Flow:** new module `checker.sources.indiankanoon` → search → fetch judgment → store hashed →
  quote must byte-match stored text → Evidence row, tier LICENSED.
- **Gate:** LICENSED can support, never make VERIFIED (`checker/sources/tiers.py`); terms record in `terms.py` or the connector refuses to load.
- **Next:** owner's Indian Kanoon key; read API terms.

### F6 Event map — BUILT (not lawyer-reviewed)
- **Entry:** `events.assess` (MCP `themis.events.assess`).
- **Flow:** event type + facts → `events.py` table → bodies engaged → each checked against `scope.py` → HELD / DECLARED list.
- **Next:** lawyer review of the event table.

---

## 2. Documents

### F7 Vault — BUILT (local) / S3 TODO
- **Entry:** `vault.upload`, `documents.upload`; `vault.find/summarize/research/compile`.
- **Flow:** upload → sha256 (dedupe) → `gateway/filestore.py` → `agents/vault_ingest.py` job:
  text (`pdf_text.py`; OCR via Textract when AWS is ready) → classify → chunk
  (`structural_chunk.py`) → index (`vault_search.py`).
- **Data:** `vault_documents`, chunks (migration 020, `source_documents` 009); files on disk → S3 (ap-south-1).
- **Models:** classification fallback only; OCR is Textract (CLIENT data, India region).
- **Gate:** page-by-page processing; a failed page marks the document PARTIAL, never silently skipped.
- **Proof:** upload twice → one stored file; tenant B cannot list tenant A's vault (RLS test).

### F8 Document authenticity — PARTIAL
- **Entry:** `vault.verify` (BUILT); `document.verify` (T3).
- **Flow:** `doc_verification.py` runs each dimension independently:
  byte ranges (`pdf_signature.py`) → PKCS#7 (`asn1.py`) → chain to CCA root (`checker/certs/`)
  → validity at signing → revocation (`revocation.py`, CRL) → timestamp → issuer licensed →
  official record (NOT_CHECKED until §4.3 permissions).
- **Gate:** overall COMPLETE only when every needed dimension is established; else INCOMPLETE_VERIFICATION.
- **Next:** OCSP; official-record verifiers one per permission (SHCIL, DigiLocker, GSTN).
- **Proof:** `scripts/verify_document.py --test`; a re-saved signed PDF → MODIFIED.

### F9 Document validity and action — TODO (T3)
- **Entry:** `document.verify`.
- **Flow:** F8 dimensions + extracted dates (`document_date.py`, `derived_date.py`) +
  company policy (renewal window per tenant) → new module `checker.doc_validity` →
  status CURRENT / EXPIRES_ON / EXPIRED / SUPERSEDED / REVOKED / NOT_DETERMINED →
  action KEEP / RENEW_BY / REPLACE / REMOVE / NEEDS_LAWYER, each with its reason.
- **Data:** `document_checks` (new migration, FORCE RLS); RENEW_BY rows feed F20 calendar.
- **Gate:** any rule resting on law fires only if that law is HELD; else NOT_DETERMINED naming the law.
- **Proof:** an expired document never returns KEEP; any NOT_CHECKED dimension blocks KEEP.

### F10 Document review — BUILT
- **Entry:** `review_document` (MCP `themis.review_document`).
- **Flow:** classify first → only rules for that document type run (`checker/ss/` scanner,
  `agents/review_document.py`) → each finding with rule id, source, date, quote.
- **Gate:** minutes rules never fire on a notice; unknown type → classification uncertainty only.

### F11 Classification — BUILT
- **Entry:** `intake.classify`; internal first step of F7–F10.
- **Flow:** `doc_classifier.py` (rules) → `classify.py` → model fallback → label + confidence band.
- **Gate:** UNKNOWN is a valid answer and stops substantive checks.

---

## 3. Contracts

### F12 Playbook review — BUILT
- **Entry:** `review_contract` (MCP); web Contracts screen.
- **Flow:** `clauses.py` splits clauses → `clause_tags.py` tags → each playbook rule
  (`playbooks/nda_v1.json`) evaluated → MATCHES / DEVIATES / MISSING / NEEDS_LAWYER with the quoted clause.
- **Gate:** playbook is DRAFT until a lawyer approves; a finding is a POTENTIAL_ISSUE against a company standard, never a statement of law.
- **Next:** playbook editor; more playbooks (vendor MSA, employment).

### F13 Review tables — BUILT
- **Entry:** `review_table.create/status/export/cancel`.
- **Flow:** documents × columns → one queue job per cell (`agents/review_grid.py`) →
  extractor answers FOUND (quote) / NOT_FOUND / NEEDS_LAWYER → `checker/review_grid.py` stores → CSV export.
- **Data:** `review_grids`, cells with cost (migrations 011, 013).
- **Gate:** FOUND without byte-matched quote is rejected; cell cost recorded per cell.
- **Proof:** CUAD per-column precision/recall with Wilson intervals (evaluation only; CUAD never shown to users).

### F14 Renewal and obligations calendar — PARTIAL
- **Entry:** review-table date columns → `calendar.upcoming`.
- **Flow:** extracted contract dates (expiry, notice window, lock-in) → `DerivedDate`
  arithmetic (interval text must appear verbatim in the clause) → calendar rows → reminders (SES, TODO).
- **Gate:** a date that cannot be re-derived exactly is not put on the calendar.
- **Next:** C1x — wire contract dates into `compliance_calendar.py`.

### F15 Stamp-duty check — NOT DOING (until a State pack)
- **Would be:** instrument type + State + execution date + consideration → State schedule (held) → duty due vs. e-stamp amount (F8/F9).
- **Blocked by:** no State stamp law held. Today: refusal naming the State and the body.

### F16 Clause comparison — TODO
- **Flow:** F13 extraction of one clause type across N contracts → `comparer` agent groups by
  deviation from the playbook standard → table with quotes.
- **Gate:** comparison is of quoted text; no "market standard" claims (no Indian contract corpus to support them).

---

## 4. Drafting

### F17 Drafts with versions — BUILT
- **Entry:** `draft.create/revise/status/versions/diff/export`.
- **Flow:** `draft_prose.py` writes → each sentence bound by `provenance_slots.py`: statement of
  law → must bind a verified claim + citation; otherwise MODEL_SUGGESTION → every save a version (`draft_versions.py`) → exact diff.
- **Data:** `drafts`, versions (migration 012).
- **Gate:** approval blocked while any MODEL_SUGGESTION is unaccepted.

### F18 Templates — BUILT
- **Flow:** `draft_templates.py` / `drafting.py` fill fixed slots (AGM notice, board resolutions) from facts; unknown slot → UNKNOWN, blocks approval.

### F19 Word add-in — TODO (frontend repo, H5)
- **Flow:** Office.js panel → calls `/v2` through the web server (key stays server-side) → our own
  diff → suggestions inserted as tracked changes; comments carry citations.
- **Gate:** never a silent overwrite; transport error shown as error, never as abstention.

---

## 5. Compliance and monitoring

### F20 Compliance calendar — BUILT
- **Entry:** `calendar.upcoming`.
- **Flow:** company facts → `obligations.py` (which duties apply) → `compliance_calendar.py` → due dates via `derived_date.py`.
- **Gate:** a missing fact gives "which fact is missing", not a date.

### F21 Company facts — BUILT (upload) / live NEEDS PERMISSION
- **Entry:** `company_facts.extract`.
- **Flow:** user uploads MCA master-data PDF → `checker/sources/mca_master_data.py` parses → facts with
  character spans, status UNCONFIRMED until the user confirms → `company_profile.py`.
- **Gate:** never scrapes MCA; OGD dataset (data.gov.in key) as the second route.

### F22 Horizon scanning (Themis) — PARTIAL
- **Flow:** feeds (`checker/feeds/`: `egazette.py`, `ibbi.py` built; SEBI TODO; RBI read-only, never cached) → new instrument →
  `instrument_registry.py` → affected provisions → **recall**: runs whose `law_versions` hold the
  old hash → list of answers to re-check.
- **Data:** `law_versions` on runs (T1) — the join key between the law and past answers.
- **Gate:** Ring 3 (forecast) may never feed Ring 0; recall lists, never rewrites, old answers.
- **Next:** T1, then Themis T4 on its own branch.

---

## 6. Work management

### F23 Matters and users — BUILT
- `matters.create/list`; `users`, roles, per-matter access (migrations 018, 019); `gateway/passwords.py`.

### F24 Agents and saved workflows — TODO (MA1, T5)
- **Flow:** supervisor proposes a plan from the **agent registry** → plan validator (code): registry
  agents only, ≤ 8, depth 1, budget and time cap, data class per model → `runs.preview` shows the
  plan and estimated cost → lawyer approves → jobs fan out → blackboard → critic → synthesis.
- **Saved workflow:** a stored, validated plan template (new module `agents.workflows`) that can only reference registered intents.
- **Gate:** stop conditions — PAUSED_BUDGET, time cap, two verifier rejections → that branch NEEDS_LAWYER.

### F25 Schedules — TODO (T6)
- **Flow:** `schedules` table (cron + workflow id) → scheduler enqueues a run → same path as F24; a law-change trigger from F22 can also enqueue.

### F26 Spaces — TODO (T8)
- **Flow:** `spaces`, `space_members` (guest role), `space_items` (pointers to documents/answers,
  never copies) → guests see only shared items → every view audited.
- **Gate:** RLS on space membership; a guest can never reach the tenant's vault.

### F27 Command Center — TODO (T7)
- **Entry:** `ops.summary`.
- **Flow:** aggregates over `runs`, ledger, review queue: volume, turnaround, refusal rate, spend,
  open NEEDS_LAWYER items — per team and matter.
- **Gate:** no per-person ranking; no metric without its denominator.

---

## 7. Ways to connect

### F28 REST API — BUILT
`/v1` engine routes (forwarded byte for byte); `/v2` verbs, API-key authenticated.

### F29 MCP server — BUILT
`checker/mcp/` generates read-only tools (`themis.*`) from the verb table; `READ_ONLY_TOOLS == KNOWN_TOOLS`
is a test. Next: OAuth per user (PLAN_22 D7).

### F30 CLI — BUILT
`gateway/cli.py`, prog `placedon`; `runs.get` → `placedon runs-get`, each field a `--flag`.

### F31 File connectors — TODO
SharePoint/OneDrive (Graph), Google Drive, Outlook/Gmail → customer OAuth, read-only → each file
enters through F7 (hash, classify, index). A connector never feeds a model directly.

### F32 Licensed legal databases — NEEDS PERMISSION
`checker/sources/<publisher>.py` + `terms.py` record → tier LICENSED. Indian Kanoon first; SCC Online
by agreement or bring-your-own-licence (credentials per tenant in Secrets Manager).

### F33 Webhooks — TODO
`webhooks` table (tenant, URL, secret) → on run finished / law changed → signed POST, retried via the queue.

---

## 8. Build order for the features (from today)

| Order | Step | Features it completes | Depends on |
|---|---|---|---|
| 1 | T1 `law_versions` on every run, envelope v2 | F1, F22 | — |
| 2 | A1 robustness (lanes, dead letter, circuit breaker) | all | — |
| 3 | T3 `document.verify` validity + action | F8, F9 | T1 |
| 4 | J1 jurisdiction resolver | F3, F2 | — |
| 5 | MA1 supervisor + registry + parallel workers | F2, F16, F24 | T1, A1 |
| 6 | C1x contract dates → calendar | F14 | T3 |
| 7 | T5/T6 workflows and schedules | F24, F25 | MA1 |
| 8 | T7 Command Center | F27 | ledger |
| 9 | T8 Spaces | F26 | — |
| 10 | L1 Indian Kanoon | F5, F32 | key |
| 11 | H5 Word add-in (frontend) | F19 | — |
| 12 | Connectors, webhooks | F31, F33 | a pilot that needs them |
| — | State pack (one State) | F15 | a paying pilot in that State |
