-- 002_runs.sql — runs, run_steps, propositions.
--
-- This file was BLOCKED on research/TASKS.md R-016, which asked the founder to choose
-- between two models of the same interaction:
--
--   threads/turns        the SERVED ANSWER is authoritative. Cheap, and it matches
--                        checker.api.handle, which takes a payload and returns a response
--                        with no intermediate state.
--   runs/run_steps/      the DERIVATION is authoritative. You can ask why a clause was
--   propositions         said, and re-run one step against a corrected corpus.
--
-- **Decided 29-09-2026 by the founder, in favour of the DERIVATION** — the shape named in
-- the build-order instruction for this migration. It is materially more schema, more write
-- volume, and it requires every pipeline stage to emit a typed step. It is also the shape
-- the product's thesis needs: the product is the watching, not the answering. Retrofitting
-- it later would mean backfilling derivations that were never recorded, which is why the
-- question blocked this file rather than being deferred past it.
--
-- STATUS: UNAPPLIED, like 001. See scripts/rls_integration.py.

BEGIN;

-- A run is one intent, planned in code (agents/plans.py) and executed step by step.
CREATE TABLE IF NOT EXISTS runs (
    run_id      uuid PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_id    uuid NOT NULL,
    intent      text NOT NULL,
    status      text NOT NULL,
    refusal_code text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    -- agents/state.py's invariant, in the schema rather than only in Python: REFUSED
    -- carries a code and every other terminal status does not. A run that is refused
    -- without saying which refusal is the thing the code exists to prevent.
    CONSTRAINT runs_status_known CHECK (status IN
        ('PLANNED','RUNNING','AWAITING_HUMAN','ANSWERED','PARTIAL','REFUSED','FAILED')),
    CONSTRAINT runs_refusal_code_iff_refused CHECK (
        (status = 'REFUSED' AND refusal_code IS NOT NULL) OR
        (status <> 'REFUSED' AND refusal_code IS NULL))
);

-- One row per step, in order, so a killed run resumes to an identical trace.
CREATE TABLE IF NOT EXISTS run_steps (
    run_id      uuid NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ordinal     integer NOT NULL CHECK (ordinal >= 0),
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    capability  text NOT NULL,
    engine_capability text,
    status      text NOT NULL,
    model       text,
    degraded    boolean NOT NULL DEFAULT false,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (run_id, ordinal)
);

-- A proposition is one thing the run asserted, with the verdict L0 reached about it.
-- `span_start`/`span_end` are offsets into a source, not the text: the text lives in the
-- corpus or the document, and copying it here would make this table a second, divergent
-- copy of evidence that must be byte-identical to be evidence at all.
CREATE TABLE IF NOT EXISTS propositions (
    proposition_id uuid PRIMARY KEY,
    run_id      uuid NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    ordinal     integer NOT NULL CHECK (ordinal >= 0),
    status      text NOT NULL,
    source_ref  text,
    span_start  integer CHECK (span_start IS NULL OR span_start >= 0),
    span_end    integer CHECK (span_end IS NULL OR span_end >= 0),
    CONSTRAINT propositions_status_known CHECK (status IN
        ('VERIFIED','PARTIALLY_VERIFIED','UNVERIFIED','CONFLICTING','OUT_OF_SCOPE')),
    CONSTRAINT propositions_span_ordered CHECK (
        span_start IS NULL OR span_end IS NULL OR span_end >= span_start)
);

CREATE INDEX IF NOT EXISTS run_steps_by_run ON run_steps (run_id, ordinal);
CREATE INDEX IF NOT EXISTS propositions_by_run ON propositions (run_id, ordinal);

-- ── isolation, on every one of them ─────────────────────────────────────────
ALTER TABLE runs         ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs         FORCE  ROW LEVEL SECURITY;
ALTER TABLE run_steps    ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_steps    FORCE  ROW LEVEL SECURITY;
ALTER TABLE propositions ENABLE ROW LEVEL SECURITY;
ALTER TABLE propositions FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON runs;
CREATE POLICY tenant_isolation ON runs USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON run_steps;
CREATE POLICY tenant_isolation ON run_steps USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON propositions;
CREATE POLICY tenant_isolation ON propositions USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMIT;
