# Overnight report — 5 October 2026

Execution of `.claude/plans/loop-overnight-twenty-moves-2026-10-05.md`, moves 1–10.
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
| 12–20 | SSE streaming, MA1, G1, `.env.example`, jobs pooling, `demo_e2e` | **NOT STARTED** | — |

Three draft PRs, each cut from `origin/main` and targeting `main`:

- **#67** `claude/overnight-a` — Phase A, moves 1–5
- **#68** `claude/overnight-b` — Phase B, moves 6–7
- **#69** `claude/overnight-c` — Phase C, moves 8–10

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
appeared **seven times** in ten moves:

1. `vault_ingest` enqueued by a verb and absent from `QUEUED_INTENTS`
2. per-cell reservations wired into `schedule()` with no caller passing a budget
3. `reservation_id` passed into every cell job and consumed by nothing
4. review cells reading documents from a dict only the gate filled
5. `instruments_for` reading a record key no record has — `[]` for every question while
   **201 of 527 records carried a citation**
6. `VERIFYING_TIERS` correct and never consulted
7. `document.check` passing no validity rule, so three of five actions are unreachable
   through the verb — in code I had just written, found before committing it

The cheapest detector is the same every time: **run it against the real thing and count.**

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
  provisions.

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
| suites | 303 | 304 (Phase C) / 305 (Phase B) |
| `gateway/verbs.py` checks | 451 | 480 |
| `checker/lawyer_summary.py` checks | 92 | 100 |
| live RLS checks | 348 | **365** |
| new Ring 0 modules | — | `law_versions`, `tier_rules`, `doc_validity` |
| VERBS | 42 | **44** |

## Next, in order

1. **Merge #67, #68, #69.** Move 11 is blocked only by #69 not being on main.
2. Move 11: render `document.verify` in `/app/vault`, one line per check, live capture.
3. Moves 12–13: SSE on `ask`, with the first-event latency **measured** rather than asserted.
4. Moves 14–16: MA1 against stub models at ₹0.
5. Moves 17–18: G1 connector skeletons failing closed with `KEY_MISSING`, then
   `.env.example` and `INTEGRATIONS_CHECKLIST.md` — which is the agenda for the keys session.
6. Move 19: decide `gateway/jobs.py` pooling (A-015) with an architect record first.
7. Move 20: `scripts/demo_e2e.py` from a clean database.

**No accuracy claim is made anywhere in this work, and nothing in it asserts legal
correctness.** Every status this night added — NOT_CHECKED, NOT_DETERMINED, UNVERIFIED,
NEEDS_LAWYER, `TIER_CANNOT_VERIFY` — exists to say what was *not* established.
