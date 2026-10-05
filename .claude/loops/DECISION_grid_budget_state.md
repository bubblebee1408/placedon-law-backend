# DECISION: where a review table's PAUSED_BUDGET lives

Move 2 of `loop-overnight-twenty-moves-2026-10-05.md`. Written before the migration, per
standing rule 9.

## The problem, measured

`placedon-claude-legal-3300` PR #3 found it live: `review_table.status` returns no key that
mentions the budget. A1 put `paused_budget` on `Scheduled`, which `review_table.create`
returns **once**. So a table that paused part-way reads, on every subsequent poll, as a
table whose cells are PENDING — and PENDING already means "not attempted yet". The frontend
had to keep the pause from the create response and say, on the status panel, that this
response cannot speak to it.

A state a caller can only learn once, from a response it may not have kept, is not a state.

## Chosen

**Option A: three columns on `review_grids`, written when `create` pauses.**

    paused_budget      boolean NOT NULL DEFAULT false
    pause_reason       text    NOT NULL DEFAULT ''
    cells_not_dispatched int   NOT NULL DEFAULT 0

`status` reads them and reports PAUSED_BUDGET with the dispatched and refused counts.

A CHECK ties the reason to the state, the way `jobs_dead_reason_iff_dead` does in 021: a
paused table with no reason is indistinguishable from one nobody looked at.

## Rejected, in writing

- **B, derive it in `status` from the cells.** There is nothing to derive from. A cell that
  was never dispatched and a cell waiting its turn are both PENDING, and the difference is
  exactly what the budget refusal knows and the cells do not. This is the option the
  frontend was forced into, and it is why it had to print a disclaimer.
- **C, keep it only on `create`'s response and have callers cache it.** That is the current
  behaviour. It makes correctness depend on a client keeping a response, and a second client
  — the CLI, an MCP tool, a lawyer reloading a page — has no way to learn it at all.
- **D, a JSONB `meta` column.** Cheaper to add and worse to query: a CHECK cannot see inside
  it, so the reason could go missing and the database could not refuse. 013 and 021 both
  chose real columns with real CHECKs for the same reason.
- **E, a separate `grid_budget_pauses` table.** One row per grid at most, so it is a
  one-to-one table — a join for no benefit, and a second place a grid's state lives.

## Reversal condition

If a table can ever be paused more than once, or paused for a reason other than the budget,
these columns stop being sufficient: the state becomes a history, and a history belongs in
its own table with a timestamp per entry. The moment `schedule()` can refuse for a second
reason, revisit this and take option E.

## Risk

The columns default to `false`/`''`/`0`, so every existing row reads "never paused", which
is what those rows mean. Nothing is rewritten and nothing is removed, so no running
deployment's accepted work changes behaviour.
