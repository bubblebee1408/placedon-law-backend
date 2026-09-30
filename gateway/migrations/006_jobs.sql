-- 006_jobs.sql — the durable job queue, and the two columns that make a retry safe.
--
-- PLAN_23 layer 3 and O2: "a saga; Postgres queue with SELECT … FOR UPDATE SKIP LOCKED;
-- idempotent, resumable, cancellable." Until this migration a run executed inside the HTTP
-- request, which means a run is exactly as durable as the socket that asked for it: kill
-- the process and the work is gone with no record that it was ever started.
--
-- ## Why a separate table and not a status on `runs`
--
-- `runs` is the AUDIT RECORD. `jobs` is scheduling state: leases, attempt counts, which
-- worker holds it. Putting a lease timestamp on the audit record would mean the trace of
-- what was decided changes every time a worker renews a lease, and "the run row changed"
-- would stop meaning "the answer changed". They are different objects with different
-- lifetimes -- a job is deleted-by-completion, a run is kept.
--
-- ## The lease, and why it is a timestamp rather than a boolean
--
-- A worker claims a job by setting `claimed_by` and `lease_expires_at`. A crashed worker
-- does not get to release anything -- that is what crashed means -- so the lease has to
-- expire on its own. `claim()` takes jobs that are QUEUED **or** whose lease has run out,
-- which is the whole recovery story: kill -9 the worker and the job is reclaimable the
-- moment the lease lapses, with `attempts` recording that it happened.
--
-- ## Cancellation is a REQUEST, not a kill
--
-- `cancel_requested` is a flag the worker reads at a step boundary. There is no way to stop
-- a step mid-flight and there should not be: a half-written step with no record of why is
-- worse than one more step. The saga is: stop at the next boundary, keep everything already
-- written, and append a CANCELLED step so the trace says where it stopped. Nothing is
-- deleted, ever -- PLAN_23 layer 3.

BEGIN;

CREATE TABLE IF NOT EXISTS jobs (
    job_id       uuid PRIMARY KEY,
    run_id       uuid NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    tenant_id    uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_id     uuid NOT NULL,
    intent       text NOT NULL,
    args         jsonb NOT NULL DEFAULT '{}'::jsonb,
    status       text NOT NULL DEFAULT 'QUEUED',
    attempts     integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    claimed_by   text,
    lease_expires_at timestamptz,
    cancel_requested boolean NOT NULL DEFAULT false,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT jobs_status_known CHECK (status IN
        ('QUEUED', 'LEASED', 'DONE', 'FAILED', 'CANCELLED')),
    -- A LEASED job always says who holds it and until when. Without both, a crashed
    -- worker's job is indistinguishable from one nobody has picked up, and the queue
    -- either stalls forever or hands the same work to two workers.
    CONSTRAINT jobs_lease_complete CHECK (
        (status = 'LEASED' AND claimed_by IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR status <> 'LEASED'),
    -- One job per run. A second job for the same run is the double-execution this whole
    -- file exists to prevent, and it is cheaper to refuse it here than to detect it later.
    CONSTRAINT jobs_one_per_run UNIQUE (run_id)
);

-- The claim query's index: QUEUED jobs oldest first, and expired leases alongside them.
CREATE INDEX IF NOT EXISTS jobs_claimable
    ON jobs (status, lease_expires_at, created_at);

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON jobs;
CREATE POLICY tenant_isolation ON jobs USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- ── idempotency: a retried step writes once ─────────────────────────────────
--
-- The key is derived from (run_id, capability) by the worker, not generated, so the SAME
-- step computed twice produces the SAME key and the second INSERT does nothing. That is
-- what stops a reclaimed job from appending a duplicate step -- and, because cost_inr
-- rides on the step row, from double-billing it.
--
-- Nullable because rows written before this migration have no key and are not retries of
-- anything. A UNIQUE index ignores NULLs, so those rows neither collide nor block.
ALTER TABLE run_steps ADD COLUMN IF NOT EXISTS idempotency_key text;
CREATE UNIQUE INDEX IF NOT EXISTS run_steps_idempotent
    ON run_steps (run_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- What the run produced, so a poller has something to read when the status goes final.
-- On `runs` rather than in the queue: the job is gone once it is done, and the answer is
-- not.
ALTER TABLE runs ADD COLUMN IF NOT EXISTS result jsonb;

COMMIT;
