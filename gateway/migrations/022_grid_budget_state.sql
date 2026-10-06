-- 022: a review table remembers that the budget paused it.
--
-- Move 2 of the 5-Oct overnight runbook. Architect record:
-- .claude/loops/DECISION_grid_budget_state.md
--
-- `placedon-claude-legal-3300` PR #3 found it live: `review_table.status` returned no key
-- that mentioned the budget, so a table paused part-way read as a table whose cells are
-- PENDING -- and PENDING already means "not attempted yet". A1 put `paused_budget` on the
-- Scheduled object that `create` returns ONCE, so the only way to know was to have kept
-- that response. A state a caller can learn only once is not a state.
--
-- Three columns, not a JSONB blob: a CHECK cannot see inside jsonb, so the reason could go
-- missing and the database could not refuse it. 013 and 021 made the same choice.
--
-- Nothing is removed and nothing is rewritten. Every existing row defaults to "never
-- paused", which is what those rows mean.

ALTER TABLE review_grids
  ADD COLUMN IF NOT EXISTS paused_budget boolean NOT NULL DEFAULT false,
  -- Empty unless paused. See the CHECK below.
  ADD COLUMN IF NOT EXISTS pause_reason text NOT NULL DEFAULT '',
  -- How many cells were never dispatched because the reservation was refused. The
  -- dispatched count is derived (cells - this), so there is one number to keep true.
  ADD COLUMN IF NOT EXISTS cells_not_dispatched integer NOT NULL DEFAULT 0
      CHECK (cells_not_dispatched >= 0);

-- A paused table with no nameable reason is indistinguishable from one nobody looked at,
-- and a reason on a table that is not paused is a reason for nothing. Same shape as 021's
-- jobs_dead_reason_iff_dead, for the same reason.
ALTER TABLE review_grids DROP CONSTRAINT IF EXISTS review_grids_pause_reason_iff_paused;
ALTER TABLE review_grids ADD CONSTRAINT review_grids_pause_reason_iff_paused
  CHECK ((paused_budget) = (length(btrim(pause_reason)) > 0));

-- A table that is not paused cannot have refused cells: the count is what the pause left
-- undispatched, so it is zero whenever there was no pause.
ALTER TABLE review_grids DROP CONSTRAINT IF EXISTS review_grids_undispatched_iff_paused;
ALTER TABLE review_grids ADD CONSTRAINT review_grids_undispatched_iff_paused
  CHECK (paused_budget OR cells_not_dispatched = 0);
