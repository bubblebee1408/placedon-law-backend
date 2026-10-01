-- 012_drafts.sql — H3's drafts and their versions. Tenant-scoped, FORCE RLS.
--
-- A draft is a document a company may file or send. Its versions are the record of what
-- was written, what was supported, and who approved it — which is exactly what a dispute
-- about a filing turns on two years later.
--
-- Numbered 012. 011 is `review_grids`.
--
--     ALTER TABLE x ENABLE ROW LEVEL SECURITY;   -- exempts the table OWNER
--     ALTER TABLE x FORCE  ROW LEVEL SECURITY;   -- and now it does not
--
-- ## (draft_id, version) is the primary key, and versions are APPEND-ONLY
--
-- There is no UPDATE path for the content of a version in the application, and the CHECK
-- below cannot express that on its own — so the discipline is the primary key plus a
-- revoked UPDATE grant at deploy time. What the key does buy: two concurrent saves cannot
-- both become version 3. One conflicts, and `draft.revise` reports it rather than
-- silently overwriting a colleague's revision.
--
-- ## approved_by and approved_at travel together, and neither can appear while blocked
--
-- `blocking_slots` is computed from the slots, which live in `slots` as jsonb. The database
-- cannot evaluate `checker/provenance_slots` — so it enforces the half it can see: an
-- approval carries both a reviewer and a time, and `blocking_count` (written by the
-- application from the same function that gates approval) must be 0 for an approved row.
--
-- A denormalised count is usually a smell. Here it is the only way the database can refuse
-- the row that matters most: approved while unsupported. The application computes it from
-- `provenance_slots.blocking_slots()`, the same call `Version.approve()` uses, so the two
-- cannot disagree without the code disagreeing with itself.
--
-- ## slots is jsonb and NOT NULL
--
-- A draft with no slots is prose that mentions the law, which is the thing
-- `provenance_slots` exists to refuse. `'[]'` is a legitimate value for an empty template;
-- NULL would mean "we did not record where anything came from".

BEGIN;

CREATE TABLE IF NOT EXISTS drafts (
    draft_id   uuid        PRIMARY KEY,
    tenant_id  uuid        NOT NULL REFERENCES tenants(tenant_id),
    actor_id   uuid        REFERENCES actors(actor_id),
    kind       text        NOT NULL DEFAULT 'agm_notice'
                           CHECK (length(btrim(kind)) > 0),
    title      text        NOT NULL CHECK (length(btrim(title)) > 0),
    run_id     uuid        REFERENCES runs(run_id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS draft_versions (
    draft_id       uuid        NOT NULL REFERENCES drafts(draft_id) ON DELETE CASCADE,
    tenant_id      uuid        NOT NULL REFERENCES tenants(tenant_id),
    version        integer     NOT NULL CHECK (version >= 1),
    title          text        NOT NULL CHECK (length(btrim(title)) > 0),
    body           text        NOT NULL DEFAULT '',
    slots          jsonb       NOT NULL DEFAULT '[]'::jsonb,
    citations      jsonb       NOT NULL DEFAULT '[]'::jsonb,
    -- Written by the application from provenance_slots.blocking_slots(), the same call
    -- Version.approve() gates on. 0 means every value is supported.
    blocking_count integer     NOT NULL DEFAULT 0 CHECK (blocking_count >= 0),
    approved_by    text,
    approved_at    timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),

    -- Two concurrent saves cannot both be version 3: one conflicts, and the caller is told
    -- rather than silently overwriting a colleague's revision.
    PRIMARY KEY (draft_id, version),

    CONSTRAINT draft_versions_slots_array CHECK (jsonb_typeof(slots) = 'array'),
    CONSTRAINT draft_versions_citations_array CHECK (jsonb_typeof(citations) = 'array'),

    -- An approval carries both a reviewer and a time, or neither.
    CONSTRAINT draft_versions_approval_paired CHECK (
        (approved_by IS NULL) = (approved_at IS NULL)
    ),
    -- THE one that matters: a version cannot be recorded as approved while any slot still
    -- blocks approval. `checker/draft_versions.Version` refuses to construct that; this
    -- refuses to store it, because a second writer reaches the table and not the API --
    -- the same reasoning as 005's reason check and 008's quote_viewed.
    CONSTRAINT draft_versions_no_approval_while_blocked CHECK (
        approved_by IS NULL OR blocking_count = 0
    ),
    CONSTRAINT draft_versions_reviewer_named CHECK (
        approved_by IS NULL OR length(btrim(approved_by)) > 0
    )
);

CREATE INDEX IF NOT EXISTS draft_versions_latest_idx
    ON draft_versions (draft_id, version DESC);
CREATE INDEX IF NOT EXISTS drafts_tenant_idx ON drafts (tenant_id, updated_at DESC);

ALTER TABLE drafts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE drafts         FORCE  ROW LEVEL SECURITY;
ALTER TABLE draft_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_versions FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON drafts;
CREATE POLICY tenant_isolation ON drafts USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON draft_versions;
CREATE POLICY tenant_isolation ON draft_versions USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE draft_versions IS
  'Append-only history. (draft_id, version) is the primary key, so two concurrent saves '
  'cannot both become version 3 -- one conflicts and the caller is told.';
COMMENT ON COLUMN draft_versions.blocking_count IS
  'From provenance_slots.blocking_slots(), the same call Version.approve() gates on. A '
  'denormalised count, kept because it is the only way the database can refuse the row '
  'that matters most: approved while unsupported.';

COMMIT;
