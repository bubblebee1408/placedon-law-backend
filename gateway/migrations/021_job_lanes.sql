-- 021: priority lanes, retry backoff and a dead-letter state for jobs.
--
-- A1. Three columns and one widened CHECK. No table, so the isolation proof in
-- scripts/rls_integration.py is unchanged -- `jobs` is already tenant-scoped with FORCE ROW
-- LEVEL SECURITY and a policy on current_setting('app.tenant_id').
--
-- Nothing is removed and nothing is rewritten: existing rows get the slowest lane, no
-- not_before (claimable immediately) and no dead_reason, which is exactly their current
-- behaviour. A migration that changed how a queued job is treated would be changing what a
-- running deployment does to work it has already accepted.

ALTER TABLE jobs
  -- The DEFAULT is the slowest lane on purpose: a writer that does not say what a job is
  -- gets served last and can never consume capacity reserved for interactive work. Wrong in
  -- the direction that costs latency, not the direction that starves a waiting person.
  ADD COLUMN IF NOT EXISTS lane text NOT NULL DEFAULT 'BULK',
  -- NULL means claimable now. A timestamp means a failed attempt is waiting out its backoff,
  -- which is different from a job that does not exist and different from one in flight.
  ADD COLUMN IF NOT EXISTS not_before timestamptz,
  -- Empty on every status but DEAD. See the CHECK below.
  ADD COLUMN IF NOT EXISTS dead_reason text NOT NULL DEFAULT '';

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_lane_known;
ALTER TABLE jobs ADD CONSTRAINT jobs_lane_known
  CHECK (lane IN ('INTERACTIVE', 'REVIEW_CELL', 'BULK'));

-- DEAD joins the terminal states. FAILED stays, and the two are NOT the same thing: FAILED is
-- one attempt that did not work and may be retried, DEAD is "we stopped trying". Collapsing
-- them would make "it failed" unanswerable about whether anything will happen next.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_known;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_known
  CHECK (status IN ('QUEUED', 'LEASED', 'DONE', 'FAILED', 'CANCELLED', 'DEAD'));

-- A dead job with no nameable reason is indistinguishable from one nobody looked at, so the
-- database refuses it. And a reason on a job that is not dead would be a reason for nothing.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_dead_reason_iff_dead;
ALTER TABLE jobs ADD CONSTRAINT jobs_dead_reason_iff_dead
  CHECK ((status = 'DEAD') = (length(btrim(dead_reason)) > 0));

-- The claim query's index: lane rank, then age, among rows that are claimable now. Partial,
-- because LEASED and terminal rows are not candidates and an index over them would be larger
-- for no read it serves.
CREATE INDEX IF NOT EXISTS jobs_claimable
  ON jobs (lane, created_at)
  WHERE status = 'QUEUED';

-- Dead jobs are listed newest first by jobs.dead, per tenant.
CREATE INDEX IF NOT EXISTS jobs_dead_recent
  ON jobs (tenant_id, created_at DESC)
  WHERE status = 'DEAD';
