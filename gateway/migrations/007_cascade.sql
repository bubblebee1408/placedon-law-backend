-- 007_cascade.sql — what the verified cascade actually did, kept.
--
-- PLAN_23 O3. `checker/model_cascade.py` records the stages it tried, the verifier's
-- rejection reason at each, the bodies the answer touched and the cost per stage.
-- `scripts/cascade_report.py` turns those into a rejection rate and an expected cost. Until
-- this migration the records existed only for as long as the process that made them, so the
-- report could only read a file somebody had remembered to write.
--
-- ## One table, not two
--
-- A cascade record is one run's worth of stages. Splitting attempts into their own table
-- would buy a join and cost the thing that makes the record worth keeping: the ORDER is the
-- record. Stage 2 only ran because stage 1 was rejected, and a row set that has to be
-- re-sorted to see that has lost it. The attempts are stored as jsonb, in order, and read
-- back as they were written.
--
-- ## Why `total_cost_inr` is nullable and has no default
--
-- NULL is UNPRICED. A DEFAULT 0 here would say every un-priced cascade was free, which is
-- the falsehood `backend/azure_pricing.py` and migration 004 both exist to prevent. The
-- CHECK below is the third place it is refused: a record claiming zero cost must say which
-- provider was free, and none of ours is.
--
-- ## Tenant-scoped, so FORCE RLS like the other nine
--
-- A cascade record carries the question's body attribution and the model's rejected output.
-- It is another firm's work. The tenth tenant-scoped table, isolated the same way and proved
-- the same way by scripts/rls_integration.py.

BEGIN;

CREATE TABLE IF NOT EXISTS cascade_runs (
    cascade_id   uuid PRIMARY KEY,
    run_id       uuid REFERENCES runs(run_id) ON DELETE CASCADE,
    tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
    status       text NOT NULL,
    error        text,
    -- Ordered. See the header: the order IS the record.
    attempts     jsonb NOT NULL DEFAULT '[]'::jsonb,
    body_ids     text[] NOT NULL DEFAULT '{}',
    claim_count  integer NOT NULL DEFAULT 0 CHECK (claim_count >= 0),
    refusal_count integer NOT NULL DEFAULT 0 CHECK (refusal_count >= 0),
    total_cost_inr numeric(12, 4),
    created_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT cascade_status_known CHECK (status IN
        ('ANSWERED', 'PARTIAL', 'NEEDS_LAWYER', 'FAILED')),
    -- The same invariant model_cascade.Result enforces in Python, in the schema too,
    -- because a backfill or a fixture reaches the table and not the dataclass.
    CONSTRAINT cascade_failed_carries_error CHECK (
        (status = 'FAILED' AND error IS NOT NULL) OR
        (status <> 'FAILED' AND error IS NULL)),
    -- UNPRICED is NULL. Zero would claim the calls were free.
    CONSTRAINT cascade_cost_never_zero CHECK (
        total_cost_inr IS NULL OR total_cost_inr > 0)
);

CREATE INDEX IF NOT EXISTS cascade_runs_by_run ON cascade_runs (run_id);
CREATE INDEX IF NOT EXISTS cascade_runs_by_time ON cascade_runs (created_at);

ALTER TABLE cascade_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE cascade_runs FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON cascade_runs;
CREATE POLICY tenant_isolation ON cascade_runs USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMIT;
