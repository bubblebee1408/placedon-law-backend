-- 013_grid_cell_cost.sql — what each review-table cell cost, on the cell.
--
-- Job 3b. A review table is the most expensive thing this product does: one model call per
-- cell, and a 40x6 table is 240 calls. Until now the only record of that spend was a
-- `cost_note` on the cell's run step saying "one extraction call for one cell" -- a
-- sentence, with no number, no provider and no model. So a table could be run and nobody
-- could say what it cost, which is the question a legal team's budget holder asks first.
--
-- The debit goes on the CELL and not only on the run step, for one reason: `review_table
-- .status` already reads every cell in one query, and a running total that cost 240 extra
-- reads per poll would be a total nobody polls. The run step is still written -- that is
-- the ledger `run_steps` has been since 003 -- and this is the same numbers where the
-- feature can add them up.
--
-- ## cost_inr is nullable, and NULL is not zero
--
-- The same rule as 004, for the same reason, and it is worth repeating because this is the
-- third table to need it: a recorded 0.00 is a CLAIM THAT THE CALL WAS FREE. Azure calls
-- bill against Azure for Students credit. When `backend/azure_pricing.py` holds no verified
-- price for a deployment the cost is NULL and `cost_note` begins "UNPRICED:".
--
-- NULL therefore has three readings here and the note is what distinguishes them:
--
--   "UNPRICED: ..."          a call was made and it cannot be priced
--   "no billed call ..."     a stub or deterministic answerer served the cell
--   note IS NULL             the cell has not run yet, and PENDING is the only state
--                            where that is allowed
--
-- A zero would collapse all three into "free", and none of them is.
--
-- ## Why provider is here
--
-- Not for display. It is what makes the billed-never-zero CHECK below enforceable by the
-- database rather than only by `azure_pricing.check_recordable` in Python, exactly as
-- 004 did for run_steps. The application is not the only thing that can write a row.
--
-- No column is dropped and no row is deleted: three nullable columns are added, and every
-- cell written before this migration keeps its state, value, quote and reason, with a NULL
-- cost that says "not recorded" rather than "free".
--
-- STATUS: applied 2026-10-01 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database (Postgres.app, local socket) as 001-013 together, asserted as placedon_app
-- (NOSUPERUSER, NOBYPASSRLS): 229 checks, 0 failures. The database then dropped.
--
-- review_grid_cells_ran_has_cost_note earned its place on that first run: the script's own
-- seed inserted a FOUND cell with no cost and no note and was REFUSED, which is the
-- constraint catching the exact omission it exists for, on real data, before any of this
-- reached a table a lawyer reads.

BEGIN;

ALTER TABLE review_grid_cells ADD COLUMN IF NOT EXISTS provider  text;
ALTER TABLE review_grid_cells ADD COLUMN IF NOT EXISTS cost_inr  numeric(12, 4);
ALTER TABLE review_grid_cells ADD COLUMN IF NOT EXISTS cost_note text;

ALTER TABLE review_grid_cells DROP CONSTRAINT IF EXISTS review_grid_cells_cost_not_negative;
ALTER TABLE review_grid_cells ADD CONSTRAINT review_grid_cells_cost_not_negative
    CHECK (cost_inr IS NULL OR cost_inr >= 0);

-- A billed provider may not claim a call was free. Mirrors 004's run_steps constraint.
ALTER TABLE review_grid_cells DROP CONSTRAINT IF EXISTS review_grid_cells_billed_never_zero;
ALTER TABLE review_grid_cells ADD CONSTRAINT review_grid_cells_billed_never_zero
    CHECK (provider IS NULL OR provider NOT IN ('azure', 'anthropic') OR cost_inr <> 0);

-- A NULL cost must say why. PENDING is the one state that may say nothing, because nothing
-- has happened to it; every cell that RAN carries either a number or a reason there is no
-- number.
--
-- NOT VALID **and deliberately not VALIDATED**, which is where this departs from 008. Every
-- cell answered before this migration is in a terminal state with no cost_note, so a
-- VALIDATE would fail on any database that has ever run a review table -- and the fix for
-- that would be to backfill a note, which means writing a sentence about a call nobody
-- measured. NOT VALID binds every new row and makes NO retroactive claim about the old
-- ones, which is the true state of affairs: their cost was never recorded. 008 validated
-- because an unvalidated approval constraint would let an un-reviewed approval through;
-- here the old rows are answers whose price is simply unknown, and saying so is honest.
ALTER TABLE review_grid_cells DROP CONSTRAINT IF EXISTS review_grid_cells_ran_has_cost_note;
ALTER TABLE review_grid_cells ADD CONSTRAINT review_grid_cells_ran_has_cost_note
    CHECK (state = 'PENDING' OR cost_inr IS NOT NULL OR cost_note IS NOT NULL) NOT VALID;

COMMENT ON COLUMN review_grid_cells.cost_inr IS
  'Rupees for this cell''s model call, derived from the tokens the provider REPORTED. NULL '
  'is UNPRICED or no-billed-call, never free; cost_note says which. A recorded 0.00 for a '
  'billed provider is refused by review_grid_cells_billed_never_zero.';
COMMENT ON COLUMN review_grid_cells.cost_note IS
  'Why the cost is what it is. Required once the cell has run, because a NULL beside a '
  'blank cannot be told from a NULL beside a reason.';

COMMIT;
