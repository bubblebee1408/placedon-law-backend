# Research appendix D: code audit of the orchestration and God's Eye (architect agent, 2026-09-30)

**What was audited.** The snapshot of branch `claude/harvey-india-platform-analysis-d2mmqi` at head `89370dc` (H), the `t0/finish` branch (T0), and `bilawalsidhu/gods-eye-view` at `e7707d9` (GEV). The audit was read-only.

**Self-tests run in H:**

- **Passed:** plans 24/24, runtime 20/20, state 14/14, review_document 23/23, jobs 28/28, worker 29/29, store 55/55, router 57/57, mcp/server 24/24, mcp/tools 43/43, feeds 29/29, observation_store 20/20, operations 55/55, rings 44/44.
- **verbs 89/90:** probably caused by the environment (no Azure `.env`).
- **models.py and public_only.py crash outside a git checkout.** See F7.

## A. PLAN_23's 12 layers against the code

| # | Layer | State | Evidence |
|---|---|---|---|
| 0 | Gate | PARTIAL | Hashed keys map to (tenant, actor) (`auth.py`). MCP identity is only a claim. There is no gateway rate limit |
| 1 | Intake | PARTIAL | 5 fixed intents (`plans.py:30-38`). Only 3 are queue-able (`verbs.py:462-466`) |
| 2 | Plan compiler | PARTIAL | A **linear tuple** of `StepSpec`, not a DAG. No budgets or timeouts. **No gateway code calls `plans.template`** |
| 3 | Durable executor | PARTIAL, **unreachable** | `jobs.py` claims with `FOR UPDATE SKIP LOCKED` and has lease, attempts and cancel. But no daemon runs, and no surface's `Context` carries a queue, so `runs.submit` always returns NO_STORE. `agents/runtime.execute` is a second executor, not imported by the gateway |
| 4 | Modes | workflow only | No fan-out, no ≤4 decomposition, no watch mode |
| 5 | Router | PARTIAL | Preference table with fallback on availability. **Does not escalate on verifier rejection**; NOTHING_TRACED refuses |
| 6 | L0 verify | BUILT | `quoted_span` → `lawyer_summary`; `review_contract.verify`; review_document is all code |
| 7 | Critic | NOT BUILT | A name only. `checker/orchestrator.run` is not wired to any verb |
| 8 | Synthesis | PARTIAL | `Summary.prose()` works within one intent. Nothing combines results across intents |
| 9 | Human gate | PARTIAL | `runs.approve/reject` checks exist, but they run **after** the answer is served. The runtime's `AWAITING_HUMAN` is unused. `quote_viewed` exists only in T0 |
| 10 | Record | PARTIAL | runs / run_steps / propositions, provider, region, cost_inr, cost_note, idempotency key. **Missing:** law_versions (T0 only), MAST tag, as_of, behaviour_version |
| 11 | Recall | NOT BUILT | `currency.affected_by()` exists. Nothing links runs to provisions |

**How `ask` flows:**

1. `POST /v2/ask` → `verbs._ask`.
2. `rq.evidence`: structural_retrieve → section_index → corpus → `public_only.clear_text` (a git blob check).
3. `models.serve`: SERVEABLE = {azure}, then router → azure llama-3-3-70b.
4. `rq.answer` → `quoted_span.summarise`. `verify_prompt` runs before the socket opens.
5. `_persist_run`.

**How `review_document` flows:** ss.classify, then ss.scan. No model is called.

**Resume behaviour.** Steps are idempotent by key, but the worker runs the whole handler first. Only generator handlers resume step by step, and no production handler is a generator. So:

- a resumed job **re-runs every model call**;
- cancelling only stops persistence;
- the timeout is checked after the work has already happened.

**Budgets.**

- Step timeout is 90 s; the lease is 120 s with no renewal.
- An Azure call can take 180 s × 3 tries, so it can outlive the lease.
- **The ₹3,500 cap never binds on Azure,** because Azure calls are recorded at ₹0.
- gpt-5-mini is unpriced.

## B. Model layer

**Router providers:** anthropic, gemini, ollama, azure. Sarvam and voyage are candidates but not routed.

**Chains:**

- NARRATION: Sonnet → azure llama-70b → azure gpt-5-mini → Flash → Flash-Lite.
- EXTRACTION: Opus → azure llama → Ollama.
- The gateway serves Azure only.

**Origin gate:**

- `public_only` (clear_file/text via git blob, clear_matter allows azure only, refuse_matter, verify_prompt).
- The UAE North region is refused for matter text unless `PLACEDON_ACCEPT_REGION` is set.

**Model interface:** `Callable[[str], str]`.

**A new free provider needs:**

- an adapter with `as_text_model(origin)` that calls `refuse_matter` and `verify_prompt`;
- a `_PREFERENCE` row (only after a bake-off);
- an entry in `providers_available`;
- `SERVEABLE` and a `serve` branch;
- a quota in `budget.py`.

**PLAN_22 D3 forbids non-Azure hosts apart from Gemini for public text, so adding a provider needs a D3 amendment.**

## C. Surfaces

- The verb table has 10 verbs, 5 of them writes.
- REST, CLI and MCP are all generated from it, with a parity test.
- MCP runs over stdio, and identity is only a claim.

**Caveats:**

- `themis.ask` on MCP is the /v1 engine ask, not `verbs._ask`. Parity holds by name only.
- Generated MCP tools run with a bare `Context()`, so `runs.get` and `runs.trace` return NO_STORE.
- `themis.review_contract` (marked read_only) can make a **billed Azure call** from an unauthenticated stdio caller who may also claim `test_data` [I: risk].

## D. God's Eye

**Architecture.** Providers are Vite middleware plugins, and `common/` is small:

- `http.js`: capped body reads, and single-flight coalescing;
- an opt-in rate limiter;
- a request body cap;
- `source-root`.

**Live data.** Polling uses TTL + single-flight + disk cache + serve-stale. AIS is a WebSocket stream. The client polls through `getSnapshot` with `LiveSourceError.retryAfterMs`.

**Licence.** The code is MIT; the data is under separate licences (NC, SA, ODbL). Port code patterns only. This has already been done in shape: `checker/feeds/__init__.py`.

**What Themis feeds lack:** TTL/staleness, 429/Retry-After handling and partial-success records. `RateGovernor` is used by no adapter.

**Five patterns to port:**

1. **Stale-with-TTL and a status route.** Add `common/cache.latest()` returning the data's age, emit STALENESS_WARNING, and report per-feed last-good time in `/v1/health`.
2. **Per-source partial success.** When a source is unreadable, open a HUMAN_REVIEW operation instead of staying silent.
3. **Atomic admission.** A non-empty feed whose rows are all invalid counts as unavailable. Record `complete` and `rejectedCount`, and do not advance the high-water mark if the batch is incomplete.
4. **Error taxonomy with Retry-After.**
5. **Liveness proof.** A feed is live only if it admitted at least one recognised record.

## E. Integration seams

1. **Ring 3 package.**
   - Register it in `rings.PACKAGE_RINGS`.
   - Read from `observation_store`.
   - Add a read-only verb, a plan intent and a bundles capability.
   - Add migration 007 with `runs.dataset_version`.
2. **Labelling queue.**
   - Extend `_decide` and `store.write_decision`.
   - Land T0's `quote_viewed` and `law_versions` as **007** (006 collides between the branches).
   - Add a `reviews.next` read verb.
   - Define labels as a view over decisions ⨝ propositions ⨝ run_steps.
   - **Fix F2 first.**
   - The agent may sort the queue but never decide.
3. **Scheduler.** None exists. `watch_gazette.py` and `watch_ofac.py` are single-shot scripts with exit codes 0/2/1. The path is cron → script → `observation_store.append` → `operations` → `operation_store`. Do not route this through jobs/worker.
4. **Free models.** See B. Needs a D3 amendment.

## F. Defects and contradictions

1. **The worker records FAILED and PARTIAL as ANSWERED** (`worker.py:146-147`). **Confirmed by the main session.**
2. **`ask` propositions never carry a source.** `getattr(s, "citation")` is used, but `Sentence.citations` is plural (`verbs.py:215-216`). Every `source_ref` is None, so `runs.approve` on an ask run returns NOT_FOUND and recall has nothing to join. **Confirmed by the main session.**
3. **The durable executor is unreachable,** and it is not step-level.
4. **The verbs test says the trace "is the plan";** the plan has 7 steps and the trace has 3.
5. **"A date filter runs before the model" (PLAN_23 §1.11, repeated in PLAN_24) is false.** `rq.answer` has no `as_of`.
6. **"Escalate on verifier rejection" is not implemented.**
7. **Outside a git checkout, every `ask` is refused as "retrieval abstained"** because `public_only` shells out to git. The stated reason is false, and container deploys break.
8. **PLAN_24 is stale against this branch:**
   - `ontology.py` and `derivation.py` exist.
   - Migrations are 001–006, not 001–005.
   - No feed writes to `observation_store`.
   - There is no matter column.
9. **Migration 006 collides** (T0 `006_decision_evidence` vs H `006_jobs`), and there is no migration ledger table.
10. **Stale details:**
    - `runtime.py` comments are out of date.
    - `documents.upload` stays in memory even on Postgres.
    - The MCP tool count is 17, not 13.
