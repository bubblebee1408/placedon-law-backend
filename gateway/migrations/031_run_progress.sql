-- 031_run_progress.sql — live progress of a queued run, for the waiting turn.
--
-- run_steps is written only after a handler returns (A-022), so a user waiting on an
-- answer saw nothing until the end. gateway/progress.py now writes a small value here
-- while the run is RUNNING: {"current": "<step>", "done": ["<step>", ...]}. Display
-- only; nothing decides anything from it.
--
-- Additive: one nullable column on runs. The existing runs row-level security policies
-- govern it unchanged, so another firm cannot read it. No row is rewritten or removed.

BEGIN;

ALTER TABLE runs ADD COLUMN IF NOT EXISTS progress jsonb;

COMMIT;
