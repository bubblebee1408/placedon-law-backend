-- 016_critic_enabled.sql — was the critic running when this answer was produced?
--
-- Job 8 addendum. `CRITIC_ENABLED` is read from the environment per call, which means the
-- setting leaves no trace of itself: an answer from last Tuesday cannot say whether a
-- layer that may REMOVE sentences was running when it was produced.
--
-- That matters because the critic's success case is INVISIBLE. "The critic found nothing"
-- and "the critic was off" produce the same clean answer, and without this column they are
-- indistinguishable afterwards -- including to whoever is deciding whether the critic is
-- worth keeping on.
--
-- `checker/critic.enabled()` is the one function that answers it, and `gateway/store`
-- records what it said at the moment the run was written.
--
-- NULL means NOT RECORDED: every run from before this migration. Not false -- the critic
-- did not exist for most of them, and writing false would claim we checked and it was off.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-016 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 255 checks, 0 failures, then the database dropped.

BEGIN;

ALTER TABLE runs ADD COLUMN IF NOT EXISTS critic_enabled boolean;

COMMENT ON COLUMN runs.critic_enabled IS
  'Whether CRITIC_ENABLED was on when this run was written. NULL is NOT RECORDED (every '
  'run from before 016), never false: false would claim we looked and it was off.';

COMMIT;
