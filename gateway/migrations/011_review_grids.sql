-- 011_review_grids.sql — H4's review grids. Tenant-scoped, FORCE RLS.
--
-- Documents down the side, columns across the top, one row per cell. A diligence grid is
-- the most concentrated client data in this schema: forty contracts, the questions a
-- lawyer thought worth asking about them, and a quote from each.
--
-- Numbered 011. 010 is `conversations`.
--
--     ALTER TABLE x ENABLE ROW LEVEL SECURITY;   -- exempts the table OWNER
--     ALTER TABLE x FORCE  ROW LEVEL SECURITY;   -- and now it does not
--
-- `gateway/schema.py` derives the tenant-scoped set FROM the SQL, so all three tables are
-- in scope for that check the moment they exist, and `scripts/rls_integration.py` adds
-- them to TENANT_TABLES, which is what puts them through the full proof.
--
-- ## One row per CELL, and the primary key is the idempotency key
--
-- `(grid_id, document_id, column_name)` is the primary key, and that is the whole of H4's
-- exactly-once guarantee: a worker that crashes after answering a cell and before marking
-- its job done will be handed the same cell again, and the insert conflicts. There is no
-- separate dedupe table and no "have I done this?" read before the write -- the key IS the
-- question, so two workers racing on one cell cannot both write it.
--
-- ## state, and the two that are not findings
--
--     FOUND         the answer, with the span it was read from. quote NOT NULL
--     NOT_FOUND     read, and the answer is not in the document. reason NOT NULL
--     NEEDS_LAWYER  a person must decide. reason NOT NULL
--     PENDING       queued, not yet run
--     FAILED        TRANSPORT ONLY: it did not run. Says nothing about the document
--
-- A FOUND row must carry a quote, and the CHECK says so, because a second writer reaches
-- the table and not the API -- the same reasoning as 005's reason check and 008's
-- quote_viewed. The database cannot verify the quote is IN the document (it does not hold
-- the document text); `checker/review_grid.found()` does that, and the CHECK stops the
-- cheapest version of the mistake.
--
-- ## cancelled_at, because cancel is a saga and not a delete
--
-- Cancelling a grid stops the cells that have not run. It does NOT delete the ones that
-- have: the work was done, it was paid for, and a lawyer who cancels a run at cell 30 of
-- 40 still wants the 29 answers. PLAN_23 §1.9.

BEGIN;

CREATE TABLE IF NOT EXISTS review_grids (
    grid_id      uuid        PRIMARY KEY,
    tenant_id    uuid        NOT NULL REFERENCES tenants(tenant_id),
    actor_id     uuid        REFERENCES actors(actor_id),
    name         text        NOT NULL CHECK (length(btrim(name)) > 0),
    run_id       uuid        REFERENCES runs(run_id) ON DELETE SET NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    cancelled_at timestamptz
);

CREATE TABLE IF NOT EXISTS review_grid_columns (
    grid_id     uuid    NOT NULL REFERENCES review_grids(grid_id) ON DELETE CASCADE,
    tenant_id   uuid    NOT NULL REFERENCES tenants(tenant_id),
    name        text    NOT NULL CHECK (length(btrim(name)) > 0),
    kind        text    NOT NULL
                        CHECK (kind IN ('text', 'date', 'amount', 'yes_no', 'clause')),
    -- The QUESTION asked of each document. A header is not a question, and a cell
    -- answered against a header is a cell nobody can check.
    question    text    NOT NULL CHECK (length(btrim(question)) > 0),
    ordinal     integer NOT NULL,

    PRIMARY KEY (grid_id, name),
    CONSTRAINT review_grid_columns_ordinal_unique UNIQUE (grid_id, ordinal)
);

CREATE TABLE IF NOT EXISTS review_grid_cells (
    grid_id     uuid        NOT NULL REFERENCES review_grids(grid_id) ON DELETE CASCADE,
    tenant_id   uuid        NOT NULL REFERENCES tenants(tenant_id),
    document_id text        NOT NULL CHECK (document_id ~ '^[0-9a-f]{64}$'),
    column_name text        NOT NULL,
    state       text        NOT NULL
                            CHECK (state IN ('FOUND', 'NOT_FOUND', 'NEEDS_LAWYER',
                                             'PENDING', 'FAILED')),
    value       text        NOT NULL DEFAULT '',
    quote       text        NOT NULL DEFAULT '',
    reason      text        NOT NULL DEFAULT '',
    job_id      uuid,
    answered_at timestamptz,

    -- The idempotency key IS the primary key. See the header.
    PRIMARY KEY (grid_id, document_id, column_name),
    FOREIGN KEY (grid_id, column_name)
        REFERENCES review_grid_columns(grid_id, name) ON DELETE CASCADE,

    -- A FOUND cell carries a value and a quote. The database cannot check the quote is in
    -- the document; it can refuse the empty case, which is the cheap half of the mistake.
    CONSTRAINT review_grid_cells_found_has_quote CHECK (
        state <> 'FOUND' OR (length(btrim(value)) > 0 AND length(btrim(quote)) >= 8)
    ),
    -- Everything that is not FOUND found nothing, so it carries no value and no quote,
    -- and must say WHY in words: a blank reason renders as an empty cell, and "the
    -- contract has no cap" and "we could not find the cap" are opposite facts.
    CONSTRAINT review_grid_cells_other_has_reason CHECK (
        state = 'FOUND' OR (length(btrim(value)) = 0 AND length(btrim(quote)) = 0
                            AND length(btrim(reason)) >= 10)
    )
);

CREATE INDEX IF NOT EXISTS review_grid_cells_grid_idx
    ON review_grid_cells (grid_id, document_id);
CREATE INDEX IF NOT EXISTS review_grid_cells_pending_idx
    ON review_grid_cells (grid_id) WHERE state = 'PENDING';
CREATE INDEX IF NOT EXISTS review_grids_tenant_idx
    ON review_grids (tenant_id, created_at DESC);

ALTER TABLE review_grids        ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_grids        FORCE  ROW LEVEL SECURITY;
ALTER TABLE review_grid_columns ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_grid_columns FORCE  ROW LEVEL SECURITY;
ALTER TABLE review_grid_cells   ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_grid_cells   FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON review_grids;
CREATE POLICY tenant_isolation ON review_grids USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON review_grid_columns;
CREATE POLICY tenant_isolation ON review_grid_columns USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON review_grid_cells;
CREATE POLICY tenant_isolation ON review_grid_cells USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE review_grid_cells IS
  'One row per (grid, document, column). The primary key IS the idempotency key: a worker '
  'handed the same cell twice conflicts rather than writing it twice.';
COMMENT ON COLUMN review_grid_cells.state IS
  'FAILED is TRANSPORT ONLY and says nothing about the document. A reader who takes it for '
  'NOT_FOUND concludes a clause is absent because our socket broke.';
COMMENT ON COLUMN review_grids.cancelled_at IS
  'Cancel stops the cells that have not run; it never deletes the ones that have. A lawyer '
  'who cancels at cell 30 of 40 still wants the 29 answers (PLAN_23 §1.9).';

COMMIT;
