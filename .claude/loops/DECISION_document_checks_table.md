# Decision: `document_checks` — one row per check run, not one per document

**Date** 2026-10-05 · **Move** 10 (T3) · **Branch** `claude/overnight-c`

## What is being stored

The outcome of a Document Check: the verification status (move 8), the validity status
(move 9), and the ACTION a lawyer should take — KEEP / RENEW_BY / REPLACE / REMOVE /
NEEDS_LAWYER — with the reason that produced it.

## One row per CHECK, keyed on (document_id, checked_at)

Not one row per document, updated in place. Three reasons, in order of weight:

1. **A check is an event, and the answer changes without the document changing.** A
   certificate valid in March is expired in October, and the same bytes produce a different
   action. A table that overwrote would answer "what is the status" and lose "what did we
   tell them in March" — which is the question that matters when a client asks why they were
   not warned.
2. **RENEW_BY rows feed `calendar.upcoming`.** A deadline the calendar showed last week and
   does not show today is either a renewal that happened or a bug, and with one row per
   document those are indistinguishable.
3. `runs` already works this way, and `decisions` copies its run's `law_versions` at the
   moment it is made (008). An append-only check history is the same shape as the audit
   records around it.

## Columns, and what is deliberately absent

| column | why |
|---|---|
| `check_id` uuid PK | one row per check |
| `tenant_id` | the RLS key, same as every other tenant table |
| `document_id` | FK to `vault_documents` |
| `checked_at` timestamptz | when, not what order someone inserted |
| `as_of` date | the date the validity question was asked ABOUT, which is not `checked_at` |
| `verification_status` text | COMPLETE_VERIFICATION / INCOMPLETE_VERIFICATION / VERIFICATION_FAILED |
| `validity_status` text | the six of `checker/doc_validity.STATUSES` |
| `action` text | the five actions |
| `action_reason` text | NOT NULL, non-blank — see below |
| `expires_on` date NULL | NULL is "no end date derived", never "no expiry" |
| `renew_by` date NULL | the calendar's input; NULL unless the action is RENEW_BY |
| `law_versions` jsonb NULL | which held text the validity rule rested on, same identity as `runs` (008) |

**`action_reason` is NOT NULL with a length CHECK.** An action with no reason is a verdict
nobody can check, and this table is read months later by someone who was not here. The CHECK
is in the database and not only in Python because a second writer reaches the table and not
the API — the same reasoning `005_decisions.sql` gives for its own reason check.

**`renew_by` is CHECKed to be present exactly when the action is RENEW_BY,** and absent
otherwise. A RENEW_BY with no date is a deadline the calendar cannot show; a date on a KEEP is
a deadline that would appear for a document needing nothing.

**No `expires_on` default and no `0000-00-00` sentinel.** NULL means no end date was derived —
`doc_validity` returns NOT_DETERMINED in that case and the reason says why.

**NOT stored: the individual verification check lines.** Eight of them per document, they are
derived from the bytes, and the bytes are content-addressed and immutable — so re-running
`document.verify` on the same sha256 reproduces them exactly. Storing them would be a second
copy of a derivable fact, and the one thing that is NOT derivable is the as-of-date judgement,
which is what this table holds. If that turns out to be wrong, see the reversal condition.

## RLS

`ENABLE` + `FORCE ROW LEVEL SECURITY`, with a policy on
`current_setting('app.tenant_id')` — the same shape as every tenant table since 002. FORCE so
the table owner is not exempt; a migration-admin role that could read every tenant's documents
is the hole the FORCE exists to close.

**Proven as `placedon_app`, never as the migration admin.** This is A1's lesson and it was
learned the hard way: the pool's first live check connected as admin and reported a leak that
did not exist, because a superuser bypasses RLS. `scripts/rls_integration.py` applies 023 in
sequence and asserts isolation as the application role.

## Reversal condition

Reverse the one-row-per-check shape if the table grows faster than it is read — a document
checked nightly for three years is a thousand rows to answer "what is it now". The fix then is
a `document_check_latest` view or a partial index on the newest row per document, NOT an
overwrite: the history is the reason the table exists.

Reverse the decision not to store the check lines if `document.verify` ever stops being
reproducible from the bytes alone — the moment an official-record check reaches a live
registry (move 17 onward), its answer depends on when it was asked, and an unstored answer is
unrecoverable. That is the condition to watch, and it is coming.

## Migration number

**023.** `022_grid_budget_state.sql` belongs to `claude/overnight-a` (PR #67, still open).
Branches are cut from `origin/main` and never stacked, so it is not on this branch, and
reusing 022 would put two different migrations at one number the moment #67 merges.
