-- 015_failure_category.sql — why a run did not answer, in one word.
--
-- PLAN_23 O8. Without it, "it did not work" is one undifferentiated pile and the two
-- questions that matter cannot be asked: is RETRIEVAL the problem or the VERIFIER, and are
-- we losing more runs this week than last. Those have different fixes, and a single
-- failure count hides which one is needed.
--
-- `checker/failure_tags.py` decides the word; this stores it. The value is computed in
-- `gateway/store.set_run`, which every terminal write routes through, so a caller cannot
-- forget to tag a run — the same reasoning as cost_inr riding on the step row (003/004).
--
-- ## NULL means NOT RECORDED, and that is most of the table
--
-- Every run written before this migration has NULL here, and nothing backfills them: the
-- classifier reads `refusal_code` and the result's own words, both of which those rows
-- still have, but a category computed today and stored as though it had been observed at
-- the time is a fabricated measurement. `scripts/failure_report.py` reports unclassified
-- runs as their own line rather than excluding them, so the denominator stays honest.
--
-- ## Why there is no CHECK on the value
--
-- Deliberate. The eight categories live in `checker/failure_tags.CATEGORIES`, and a CHECK
-- restating them here would be a second list to keep in step -- the failure this schema has
-- already had twice (the migration list in gateway/schema.py, the tenant-table tuple). A
-- new category would then need a migration to be storable, which is backwards: the
-- classifier is the authority, and `scripts/failure_report.py` reports any value it finds,
-- including one it does not recognise.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-015 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 254 checks, 0 failures, then the database dropped. No new table, so the isolation proof
-- is unchanged. The conformance list earned its place again on the first run: set_run
-- wrote the category on Postgres and read_run did not SELECT it, so the value existed and
-- was invisible to every reader -- green on the dict, wrong on the real backend.

BEGIN;

ALTER TABLE runs ADD COLUMN IF NOT EXISTS failure_category text;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS failure_reason   text;

-- An ANSWERED run has no failure to name. The database refuses the combination rather than
-- trusting every writer, because a success carrying a failure category would be counted as
-- a failure by every query that follows.
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_answered_has_no_failure;
ALTER TABLE runs ADD CONSTRAINT runs_answered_has_no_failure
    CHECK (status <> 'ANSWERED' OR failure_category IS NULL);

-- A category always says why it was chosen. A bare word in a weekly report is a number
-- nobody can check; the reason is what makes a wrong mapping findable.
ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_category_has_reason;
ALTER TABLE runs ADD CONSTRAINT runs_category_has_reason
    CHECK (failure_category IS NULL OR length(btrim(coalesce(failure_reason, ''))) > 0);

CREATE INDEX IF NOT EXISTS runs_failure_category_idx
    ON runs (tenant_id, failure_category) WHERE failure_category IS NOT NULL;

COMMENT ON COLUMN runs.failure_category IS
  'One of checker/failure_tags.CATEGORIES. NULL means NOT RECORDED -- every run from '
  'before 015 -- and is never backfilled: a category computed later and stored as though '
  'observed at the time is a fabricated measurement.';
COMMENT ON COLUMN runs.failure_reason IS
  'Why that category was chosen. Required whenever a category is set: a bare word in a '
  'weekly report is a number nobody can check.';

COMMIT;
