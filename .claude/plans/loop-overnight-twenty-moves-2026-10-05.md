# Loop runbook: overnight, the next twenty moves (5 Oct 2026)

Written 2026-10-04 against `main` at `f4c7b5e` (A1 merged; docs/ filed into folders). Lives at `.claude/plans/loop-overnight-twenty-moves-2026-10-05.md`. Move 1 was done before
this file reached the repository; start at move 2.

**Goal by morning:** the prototype runs end to end on a laptop, from upload to verify,
review table, draft and calendar. Document Check (T3) and streaming (R0) are built. The
bounded multi-agent runner (MA1) works against stub models. Every external integration
has a fail-closed skeleton waiting only for its key. **No external key is used tonight.**
Keys and permissions are tomorrow's session.

**Pattern: sequential. ONE subagent at a time, never two in parallel.** This is from
`loop-twenty-moves-2026-09-26.md`: on 25-09, five of six parallel subagents died on the
shared usage limit, and two parallel agents on 26-09 died together. A subagent may *do* a
move; the main session reviews it, runs the gate and commits.

## Standing rules

1. **The gate is the contract.** Run `./scripts/verify_green.sh` and read the
   `HARNESS_RESULT` line. Baseline on `main` at `f4c7b5e`: record it before move 1. A move
   that adds a failure is reverted, not debugged forward.
2. **Run one gate at a time.** `serve_ask.py --test` binds a fixed port. Never run two
   gates, even in two worktrees.
3. **Never use `SKIP_TESTS=1`.** Never skip, disable or quarantine a test.
4. **Write the failing check first, then the fix.** One logical change per commit, with
   the gate line in the commit body.
5. **Prove isolation as `placedon_app`,** never as the migration admin role (lesson from
   A1). Force the hard case: two writers, `max_size=1`, a page that fails.
6. **No new dependency** without a written reason in the commit.
7. **No external network calls and no keys.** Any connector built tonight must fail closed
   with `KEY_MISSING`, and is tested against fixtures.
8. **Stage explicit paths.** Never `git add -A`. Another session may share the tree.
9. **Write an architect record** (`.claude/loops/DECISION_<SLUG>.md`, with a reversal
   condition) before any migration, ring change or new verb family.
10. **Never claim legal accuracy.** Write OPEN or UNVERIFIED wherever evidence is missing.

**Branches:** one branch per phase (`claude/overnight-a` … `claude/overnight-f`), each cut
from the previous one. Push each branch and open a draft PR when the phase is green.
Frontend moves go in `placedon-claude-legal-3300` on `claude/overnight-ui`.

## The twenty moves

### Phase A: make the demo run (the gaps placedon-claude-legal-3300 PR #3 found live)

| # | Move | Done when |
|---|---|---|
| 1 | **DONE `e300249`** (suites=303 failed=0, GREEN; also: `vault.verify` now returns one line per check). **Vault reachable over HTTP.** Add `create_app(files=...)`, defaulting from `PLACEDON_FILES_DIR` to `gateway/filestore.LocalFileStore`. Set `ctx.files` at **both** `Context(...)` sites in `gateway/app.py`. With no file store configured, `vault.upload` still refuses `NO_VAULT`, and `/v1/health` reports which file store is in use. | An **HTTP** test goes upload → INGESTED → `vault.verify`. A direct ctx test does not count: that is how `gateway/screens.py` proved a verb nobody could reach. |
| 2 | **`review_table.status` carries the budget state.** Store PAUSED_BUDGET on the table when `create` pauses it. | A table paused at create reports PAUSED_BUDGET through `status`, with the dispatched and refused counts. |
| 3 | **Cells dispatch locally.** The local gateway passes a queue and the runbook runs `gateway.worker`. If nothing is dispatching, `status` says "not dispatched: no worker". A silent PENDING is never acceptable. | A cell reaches FOUND against local Postgres. |
| 4 | **Runbook.** Write `docs/guides/RUN_LOCALLY.md` (backend): a fresh database with migrations 001–021, why upgrading in place fails (008 `VALIDATE` against stale rows), and minting a **lawyer** key rather than a viewer key. | A clean clone follows the doc and reaches move 1's HTTP flow. |
| 5 | **Classifier regression.** "Board resolution" was classified as `agm_notice`. Add the case to the classifier's self-test, then fix it. If the label is genuinely uncertain, the output is classification uncertainty, not a guessed type. | Self-test covers it; no other classifier case changes. |

### Phase B: law versions and citation tiers (build order T1, T2)

| # | Move | Done when |
|---|---|---|
| 6 | **T1: `law_versions` on every run and in the envelope.** Which corpus hash and which instrument versions answered. | Every envelope carries it, and two runs on different corpus hashes are distinguishable. |
| 7 | **T2: citation tiers enforced.** Only HELD can be VERIFIED; LICENSED and PUBLIC can support but never verify. | A synthetic LICENSED-only answer cannot reach VERIFIED (test). |

### Phase C: Document Check (T3, `docs/architecture/FEATURE_ARCHITECTURE.md` F8 + F9)

| # | Move | Done when |
|---|---|---|
| 8 | **`document.verify`, one line per check.** Reuse `checker/doc_verification.py`, `pdf_signature.py`, `asn1.py`, `checker/certs/` and `revocation.py`. Official-record checks are NOT_CHECKED until a permission exists. | A re-saved signed PDF reports MODIFIED. The overall result is COMPLETE only when every needed check is established. |
| 9 | **`checker/doc_validity.py`: status, decided by code.** CURRENT / EXPIRES_ON / EXPIRED / SUPERSEDED / REVOKED / NOT_DETERMINED, from `document_date.py` + `derived_date.py` against `as_of`. A rule that rests on law fires only when that law is HELD; otherwise the result is NOT_DETERMINED, naming the law. | An expired document never returns CURRENT, and a missing date returns NOT_DETERMINED. |
| 10 | **Action plus migration.** KEEP / RENEW_BY / REPLACE / REMOVE / NEEDS_LAWYER, each with a reason. New `document_checks` table with FORCE RLS (architect record first). RENEW_BY rows feed `calendar.upcoming`. Register the verb (REST, read-only MCP, CLI). | An expired document never returns KEEP, and any NOT_CHECKED check blocks KEEP. RLS is proven as `placedon_app`. |
| 11 | **Frontend: render `document.verify` in `/app/vault`.** One line per check, status and action shown as words (never colour alone). Add it to both providers and to `tests/contracts.mjs`. | lint, typecheck and build are clean; a live capture goes into `docs/app-screens/`. |

### Phase D: streaming (R0)

| # | Move | Done when |
|---|---|---|
| 12 | **SSE on `ask`.** Stream step events, then the answer. A transport failure is a distinct event and is never shown as an abstention. Keep the non-streaming route as it is. | A test reads the event sequence. The first event arrives in under 1 s locally, and that time is **measured**, not asserted. |
| 13 | **Frontend: stream rendering on Ask.** Show the steps as they happen. A dropped connection shows FAILED, never a refusal. | Captured live, including a killed server mid-stream. |

### Phase E: bounded multi-agent (MA1, `docs/architecture/PLATFORM_FEATURES_AND_INTEGRATIONS.md` §5). Stub models only.

| # | Move | Done when |
|---|---|---|
| 14 | **Plan schema plus code validation.** The supervisor proposes a plan. Code checks that it uses registered agents only, at most 8 workers, no worker spawning workers, and that it fits within the budget reserved through `backend/budget.reserve`. | Each violation has a refusal test. |
| 15 | **Fan-out runner on the job queue.** Read-only workers run in parallel, one writer merges, and each result passes the verifier before any other agent sees it. Two verifier rejections in a row turn that branch into NEEDS_LAWYER. A worker that fails 3 times is dead-lettered, and the run is PARTIAL, naming the gap. | `scripts/chaos_test.py` gains one multi-agent injection. Everything runs on stub/local models, at a cost of ₹0. |
| 16 | **`runs.preview` (T4).** The lawyer sees the plan, its agents and its reserved cost before anything runs. | Preview → start → result, with the reservation balancing to zero. |

### Phase F: ready for tomorrow's keys, plus a full demo

| # | Move | Done when |
|---|---|---|
| 17 | **G1 connector skeletons:** Indian Kanoon and data.gov.in (OGD). Each has a `terms.py` record, an interface under `checker/sources/`, and fixture tests. With no key they return `KEY_MISSING` and are never treated as "not found". | No network call happens in any test. Each skeleton is ready for its key. |
| 18 | **`.env.example` plus `docs/guides/INTEGRATIONS_CHECKLIST.md`.** For every key and permission: where it goes, which verb it unlocks, who issues it, and what it costs. Cover Indian Kanoon, data.gov.in, AWS Bedrock, Textract and S3, API Setu/DigiLocker, a GST Suvidha Provider, SHCIL and EBC. | It is tomorrow's agenda, in order. |
| 19 | **Decide pooling for `gateway/jobs.py`** (deferred from A1). Write an architect record first: holding a pooled connection across an explicit transaction. Build it only if the record says it is safe; otherwise add a row to `research/TASKS.md`. | Either a proven change or a recorded decision. |
| 20 | **`scripts/demo_e2e.py`.** Drive upload → `document.verify` → review table → draft → calendar against the local gateway and worker. Give it a `--test` mode and add it to the gate. Then write `docs/reports/OVERNIGHT_REPORT_2026_10_05.md`. | The demo passes from a clean database, and the report lists every move as DONE, PARTIAL or BLOCKED. |

## After each move

Report in CLAUDE.md's code-task format: Files changed · Tests added · Commands run ·
Results (`HARNESS_RESULT` line) · Known limitations · Commit hash. Add one line naming the
next move and whether its entry gate is met.

## Stop conditions

- The gate adds a failure after ONE fix attempt on my own change → revert that move,
  record it as BLOCKED, go to the next independent move.
- A red suite belonging to someone else → do not touch it; record it.
- A move needs a key, a permission, a paid service, or a legal judgement → record it as
  `[NEEDS FOUNDER]` and continue with the next move.
- A schema, ring or dependency change without an architect record.
- Three moves in a row with no commit → stop and write the report.
- Usage limit reached → commit what is green, push, and write the report so far.

## Not a stop condition

"All twenty are done." If time remains, re-run `scripts/chaos_test.py` and
`scripts/demo_e2e.py`, and fix whatever they find, using the same rules.
