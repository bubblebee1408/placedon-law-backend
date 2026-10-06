# Overnight report — 5 October 2026

Execution of `.claude/plans/loop-overnight-twenty-moves-2026-10-05.md`, **all twenty
moves**.
Baseline on `main` at `f4c7b5e`: `HARNESS_RESULT suites=303 failed=0 nocount=0
floor_breach=0 status=GREEN`.

**Every commit is green on the full gate.** No test was skipped, disabled or quarantined.
`SKIP_TESTS=1` was never used. No external network call was made and no key was used.

## Status of each move

| # | Move | State | Where |
|---|---|---|---|
| 1 | Vault reachable over HTTP; `vault.verify` one line per check | **DONE** | PR #67 `970526d` |
| 2 | `review_table.status` carries PAUSED_BUDGET | **DONE** | PR #67 `55ea6b3` |
| 3 | Cells dispatch locally; never a silent PENDING | **DONE** | PR #67 `39b7d9d`, `dda5135`, `6d75214` |
| 4 | Runbook `docs/guides/RUN_LOCALLY.md` | **DONE** | PR #67 `6a622b7` |
| 5 | The "classifier regression" | **DONE** (premise was wrong) | PR #67 `668e77b` |
| 6 | T1: `law_versions` on every run and in the envelope | **DONE** | PR #68 `b8c4715`, `ab92b30` |
| 7 | T2: citation tiers enforced | **DONE** | PR #68 `d9c879b` |
| 8 | `document.verify`, one line per check | **DONE** | PR #69 `96f10ff` |
| 9 | `checker/doc_validity` — status decided by code | **DONE** | PR #69 `190f1b7` |
| 10 | Action + `document_checks` + RLS | **DONE** | PR #69 `4c6d788` |
| 11 | Frontend: render `document.verify` | **BLOCKED** | needs #69 on main |
| 12 | R0: SSE on `ask` | **DONE** | PR #71 `6cbb8a2` |
| 13 | Frontend: stream rendering | **BLOCKED** | needs #71 on main |
| 14 | MA1: plan schema + code validation | **DONE** | PR #71 `41eb667` |
| 15 | MA1: fan-out runner + chaos injection | **DONE** | PR #71 `6998173` |
| 16 | `runs.preview` (T4) | **DONE** | PR #71 `1243282` |
| 17 | G1 connector skeletons | **DONE** | PR #72 `37d8afe` |
| 18 | `.env.example` + integrations checklist | **DONE** | PR #72 `ceb649d` |
| 19 | Decide `gateway/jobs.py` pooling | **DONE** (decision) | PR #72 `8d22778` |
| 20 | `scripts/demo_e2e.py` | **DONE** | PR #72 `8d22778` |

**18 of 20 done. 2 blocked, both frontend, both on the never-stack rule rather than on a
defect** — move 11 needs #69 on `main` and move 13 needs #71.

Five draft PRs plus this report, each cut from `origin/main` and targeting `main`:

- **#67** `claude/overnight-a` — Phase A, moves 1–5
- **#68** `claude/overnight-b` — Phase B, moves 6–7
- **#69** `claude/overnight-c` — Phase C, moves 8–10
- **#71** `claude/overnight-d` — Phases D+E, moves 12 and 14–16
- **#72** `claude/overnight-f` — Phase F, moves 17–20
- **#70** `claude/overnight-report` — this document

### Why the branches are not stacked

The plan said to cut each phase from the previous one. The standing rule says **never stack
PRs**: every branch from `origin/main`, every PR targets `main`, and if a dependency is not
on main, stop and say so. The standing rule won. Phases B and C touch nothing Phase A
changed, so nothing was blocked by the choice — except move 11, which genuinely needs #69's
verb and is recorded as BLOCKED rather than built on an unmerged branch.

One consequence worth knowing before merging: **migration numbers.** `022_grid_budget_state`
is on #67 and `023_document_checks` is on #69. They do not collide, and the gap in #69's
sequence is deliberate and documented in its header.

## What the night actually found

Ten of the fourteen defects fixed were invisible to the test suite, and the reason is one
sentence: **every existing test used `MemoryBackend`, which has no foreign keys, no file
store and no money.** The work that found them was running the product, not reading it.

### Nothing queued could run on Postgres at all

`jobs.run_id` references `runs(run_id)`. `_runs_submit` writes the run row first and its
comment says exactly why. Neither `vault.upload` nor `review_table.create` did, so **every
enqueue raised `ForeignKeyViolation`** on a real database. Worse, `_vault_upload`'s bare
`except Exception` swallowed it and reported *"No queue is configured, so nothing will ingest
it"* — while a queue was configured and answering.

### The worker could not start

`main()` called `store.select()` with no tenant, which `select()` refuses for Postgres. The
worker died on `StoreError` before claiming a single job, and the only symptom anywhere was a
document that stayed PENDING for ever.

### A well-formed request answered with HTTP 500

`review_grid_cells.document_id` is CHECKed `^[0-9a-f]{64}$` — a grid addresses documents by
content hash so a table is replayable — while a vault `document_id` is a uuid. Passing one
reached the database and came back as a stack trace.

### Cells were wired to a fixture, and leaked money

`_review_grid_cell` read documents only from `ctx.documents`, an injected dict the gate
filled and no running process ever did. And `schedule()` has always passed `reservation_id`
into each cell's args *"so the worker settles the exact reservation this cell holds"* —
`reservation_id` appeared **nowhere** in `gateway/verbs.py`, so every cell that ran held its
worst-case price until the day rolled over. Measured live: ₹2.00 outstanding for a cell that
had already finished.

### Three identities for one fact

`008_decision_evidence.sql` fixed the identity for `runs.law_versions`: *"The same identity
`public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer cache) compare one
thing."* `law_versions_of` carried its own copy of git's blob formula, and move 6 nearly
added a third under a different name. Now one implementation, with a check asserting `sha1`
no longer appears in the gateway's copy.

### Only HELD law can verify, and nothing checked

`VERIFYING_TIERS = (HELD,)` was correct and unconsulted. A proposition is `"VERIFIED" if
s.traced else "UNVERIFIED"`, and `verify_sentence` — which decides `traced` — had no tier
information at all. A sentence quoting a real, byte-matched span of a LICENSED judgment would
have been VERIFIED. No connector exists yet, which is precisely why this was the moment:
move 17 adds two.

### A hardcoded statutory type, in four places

`draft.create` defaulted `kind` to `"agm_notice"` — an instrument carrying s.96 and s.101
obligations — for any caller who did not say otherwise. The plan recorded this as a
classifier regression. **There is no classifier on that path**; `agm_notice` is not a class
label anywhere in the repository. A constant wearing the clothes of a judgement is worse than
a wrong classification, because it cannot be argued with.

## The pattern, named

**"Wired and unreachable"** is now the most common defect class in this codebase: a mechanism
built, a caller never connected, and a test that injected what production never supplies. It
appeared **eight times** across the twenty moves:

1. `vault_ingest` enqueued by a verb and absent from `QUEUED_INTENTS`
2. per-cell reservations wired into `schedule()` with no caller passing a budget
3. `reservation_id` passed into every cell job and consumed by nothing
4. review cells reading documents from a dict only the gate filled
5. `instruments_for` reading a record key no record has — `[]` for every question while
   **201 of 527 records carried a citation**
6. `VERIFYING_TIERS` correct and never consulted
7. `document.check` passing no validity rule, so three of five actions are unreachable
   through the verb — in code I had just written, found before committing it
8. `VERIFYING_TIERS = (HELD,)` correct since it was written, and consulted by nothing on the
   path that assigns VERIFIED

The cheapest detector is the same every time: **run it against the real thing and count.**

## What the second half found

### A measurement that said the opposite of the truth

Move 12's done-when said the first-event latency must be **measured**, not asserted. Timing
`client.post` measures the answer. `client.stream` looks correct and is not: **Starlette's
ASGI transport collects the whole response before `iter_lines` yields**, so every frame
arrived at one instant and the first reported **100% of total** — a number that says "this
route does not stream" about a route that streams fine.

Over a real loopback socket: **first frame 1.3 ms, answer 3860 ms.** Had the done-when said
"assert", the route would have shipped with me believing a false thing about my own test.

### Three identities for one fact, nearly four

`008_decision_evidence.sql` fixed the identity for `runs.law_versions` and said why: *"the
same identity `public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer cache)
compare one thing."* `law_versions_of` was carrying its own copy of git's blob formula, and
move 6 was about to add a third under a different name. Now one implementation, with a check
that `sha1` no longer appears in the gateway's copy.

### A test that passed vacuously next to one that failed

`store.conformance`'s sixth uuid-vs-str divergence: Postgres returns a uuid column as
`uuid.UUID`, MemoryBackend stores the `str` the caller passed. `read_renewals()` returned the
right row and `row["document_id"] == did` was False — so one check reported an empty result
against a table that held it, **and the check before it passed vacuously for the same
reason.** The failing one is why the passing one got looked at.

### A bug found by writing a test for something else

Move 16's done-when — preview → start → result balancing to zero — found that move 15's
runner called `validate` **again**, so a caller that had already reserved collided with its
own still-held ids. `_reservation_id` is stable per (goal, index, agent) deliberately, and
that property is what made the double call fail loudly instead of silently charging twice.

### Three times a branch's reality corrected a demo

Move 20's `demo_e2e` asserted features that live on other branches, and each fix was to
**assert less rather than assume more**: `vault_ingest` is not a queue handler on `main`, so
it calls the agent and prints which path ran; `vault.verify`'s per-check lines are PR #67's,
so they are asserted when present and named when absent; and `calendar.upcoming` **refused my
company profile** because I sent `{"type", "listed"}` where the fields are `company_class`
and `is_listed` — its refusal says *"a caller who sent one believes it was taken into
account"*, and it was right.

## Two things deliberately not built

Both are recorded decisions rather than omissions.

**A migration for `runs.law_versions`** (move 6). Written, with CHECKs, a partial index and
an architect record — then deleted, because the column has existed since 008 and `ask`
already populates it. `.claude/loops/DECISION_law_versions_on_runs.md` records the decision
not to migrate.

**Pooling `claim()`** (move 19). `gateway/pool.py` creates connections `autocommit=True` and
`claim()` needs `autocommit=False` — a pooled connection would release the `FOR UPDATE SKIP
LOCKED` lock *before* the UPDATE it protects. The fix is a second entry point,
`pool.transaction(tenant_id=…)`, not a flag, because a flag makes the caller responsible for
a commit the pool depends on. The autocommit half is safe and worth having alone; the risky
half wants a live proof and an unhurried session.
`.claude/loops/DECISION_jobs_pooling.md`.

## Things that caught me, and were right to

- `checker/rings.py` refused a Ring 0 → Ring 2 import **twice**, both times inside a test.
- `gateway/roles.py` refused the build for each new verb until it declared a minimum role —
  *"the only kind of reminder that works"*.
- `store.conformance` found its **sixth** "wrote it, didn't select it" divergence: Postgres
  returns a uuid column as `uuid.UUID` while the dict stores the `str` the caller passed.
- `scripts/rls_integration.py` refused to pass on an **empty** `document_checks` table, so
  the seed was written only after the checks had reported 0 rows.
- `scripts/check_doc_refs.py` was right that two paths in the runbook do not exist in this
  repository — they are in the frontend repo.
- Three separate count assertions (`gateway/verbs.py`, `gateway/app.py`, the MCP opt-out set)
  mean a verb cannot be added without someone editing those lines.
- The move-2 ledger assertion caught a real leak from my own live run.

## My own mistakes

Listed because the pattern is more useful than the fixes:

- **Two unfalsifiable checks.** `kind == DRAFT_KIND_UNKNOWN` is true whatever the constant
  holds; a "no shadow declaration" check searched for a string the check itself contained.
  Both now compare literals or use the AST, and both have been watched going red and green.
- **The `__main__` second-module-copy trap, for the fourth time in this repository.** A
  module run as `__main__` is a different object from the one another module imports.
- A check landed in **production code**: the comment banner I anchored on existed twice and
  `replace(..., 1)` took the wrong one.
- `"g" * 64` as a document id — `g` is not a hex digit, so a refusal I had just written
  correctly rejected my own fixture.
- An `lru_cache` keyed on a directory path returned the **previous** digest after a byte
  changed, which defeats the only question a corpus hash exists to answer.
- A blanket tier refusal turned **25 of `lawyer_summary`'s checks red, and every one was
  right**: tracing a sentence to the client's document asserts nothing about law.
- `write_vault_chunks` takes strings and I passed dicts, so a fixture bug looked like a
  product one.

In one case the instinct was worth more than the code: `doc_validity` passed 45/45 on the
first run, which is suspicious, so I sabotaged both done-when paths and watched 11 checks go
red before restoring.

## A migration I wrote and then deleted

`023_run_law_versions.sql` was written, with CHECKs, a partial index and an architect record
arguing two named columns over JSONB. All of it was unnecessary: **`runs.law_versions jsonb`
has existed since `008_decision_evidence.sql`**, both backends read and write it, and — when
measured rather than read — `ask` already populates it, on ANSWERED and REFUSED runs alike.

`.claude/loops/DECISION_law_versions_on_runs.md` now records the decision **not** to migrate,
with its reversal condition. Reading `write_run` before editing it is the only reason this
repository does not have a duplicate column.

## What needs you

### `[NEEDS FOUNDER]` — a review table cell reaching FOUND

The chain is complete up to exactly one point. A cell dispatches, the worker claims it, loads
the document from the content-addressed store, and fails on `NO_MODEL`. The cell's own reason
says *"that is a failure of ours and says nothing about the document"*. Supplying a model key
is forbidden by standing rule 7.

### Four decisions recorded in `research/TASKS.md`

- **A-017** one worker drains one tenant. Draining several means re-setting `app.tenant_id`
  per claim — a ring-level change wanting an architect record. One worker per tenant needs
  none and cannot leak across tenants even by accident.
- **A-018** a review table is not wired to the vault. The console cannot turn a vault
  document into a grid row without carrying the content hash itself, and nothing resolves a
  hash back to a name for display. **A product decision about which identifier the table
  speaks.**
- **A-019** `012_drafts.sql` still carries `DEFAULT 'agm_notice'`. Now unreachable from our
  code, still a loaded gun. A column-default migration wants an architect record.
- **A-020** `doc_classifier` has no `board_resolution` class at all, while having
  `board_minutes`, `board_notice` and `shareholder_resolution`. **A legal-taxonomy decision.**
- **A-021** no validity-rule registry, so `document.check` is NOT_DETERMINED for every
  document. **Needs counsel**, not code: a per-document-class rule table citing HELD
  provisions. Deliberately not solved by taking a rule from the caller — nothing checks a
  caller's quote against the held corpus.
- **A-022** SSE `step` events are emitted on completion, not live. `_persist_run` rebinds the
  step list at the end rather than appending, so there is nothing to observe mid-flight; each
  event carries `live: false` and says so. Making them incremental touches every handler.
- **A-023** MA1's fan-out is sequential. Stated in the module's own docstring, not discovered
  later. What is missing is not a thread pool but a decision about how many model calls may
  be in flight against the provider's rate limit.
- **A-015** is now a *decision* rather than a deferral — see "Two things deliberately not
  built".

### Three pre-existing unfalsifiable checks

`eval/goldset/run.py:287` and `scripts/record_interview.py:293` still need your call.
(`checker/cascade.py`'s was fixed during A1.)

## Verified live, not asserted

Against `placedon_runbook_check`, created empty, following `docs/guides/RUN_LOCALLY.md` from
the top:

```
store: postgres (FORCE ROW LEVEL SECURITY by tenant_id)
files: {"configured": true, "kind": "local"}
upload  -> job_id 5f723e64…, queue_error None, state PENDING
worker  -> state INGESTED, 2 clause tags, each with its quote and span
verify  -> PASS  the document is not deleted
           PASS  the file store holds its bytes
           PASS  the bytes hash to the key they are stored under
find    -> 1 hit
table   -> uuid refused BAD_REQUEST (was HTTP 500)
           content hash enqueues 1 cell, dispatched, claimed,
           FAILED on NO_MODEL
```

Against `placedon_throwaway_rls023`, migrations 001–021 + 023, asserted as `placedon_app`
(NOSUPERUSER, NOBYPASSRLS): **365 checks, 0 failures.**

Against the real corpus: `s.92` → Act 1 of 2018, Act 22 of 2019, Act 29 of 2020, S.O. 1177
(E), read from the records rather than from memory.

## Suite growth

| | baseline | now |
|---|---|---|
| suites | 303 | **307** (Phase F) |
| `gateway/verbs.py` checks | 451 | 480 |
| `checker/lawyer_summary.py` checks | 92 | 100 |
| live RLS checks | 348 | **365** |
| new Ring 0 modules | — | `law_versions`, `tier_rules`, `doc_validity` |
| new Ring 2/3 modules | — | `connector_base`, `indiankanoon`, `data_gov_in`, `multi_plan`, `multi_runner` |
| chaos injections | 5 | **6** |
| VERBS | 42 | **45** across the branches (44 on #69, 43 on #71) |
| architect records | — | 4 written, 1 of them a decision NOT to migrate |

## Next, in order

1. **Merge #67, #68, #69, #71, #72.** All five are independent and all target `main`. Merging
   #69 unblocks move 11; merging #71 unblocks move 13. One thing to know:
   `022_grid_budget_state` is on #67 and `023_document_checks` is on #69 — they do not
   collide, and the gap in #69's sequence is deliberate and documented in its header.
2. **Moves 11 and 13**, the two frontend renders, in `placedon-claude-legal-3300` on
   `claude/overnight-ui`: `document.verify` as one line per check in `/app/vault`, and stream
   rendering on Ask including a killed server mid-stream.
3. **`docs/guides/INTEGRATIONS_CHECKLIST.md` is the keys session, in order.** Start with
   Bedrock, and request model access before anything else — a fresh account can call no model
   family until each is requested, and the request is not instant.
4. The **autocommit half** of the jobs pooling, which is safe today and strictly better than
   now. `claim()` after that, with `pool.transaction()` and a live proof.
5. The five recorded decisions, two of which are not coding tasks: which identifier a review
   table speaks (**A-018**), and the per-document-class validity rules (**A-021**, needs
   counsel).

**No accuracy claim is made anywhere in this work, and nothing in it asserts legal
correctness.** Every status this night added — NOT_CHECKED, NOT_DETERMINED, UNVERIFIED,
NEEDS_LAWYER, `TIER_CANNOT_VERIFY` — exists to say what was *not* established.
