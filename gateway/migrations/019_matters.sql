-- 019_matters.sql — the unit of work a firm actually organises around.
--
-- 8b. A tenant is a firm; a MATTER is one piece of work for one client inside it. Without
-- it, every conversation, run and draft in the firm is one undifferentiated list, and the
-- question "show me everything on the Acme acquisition" has no answer -- while the
-- question "show me everything" has one that includes matters this user has no business
-- reading.
--
-- ## matter_id is NULLABLE, and that is not laziness
--
-- Every row written before this migration has no matter. NULL means NOT FILED, and the
-- listing rule below treats it as its own bucket rather than as "belongs to whichever
-- matter you asked for". Backfilling every existing conversation into a default matter
-- would be inventing a client relationship that nobody recorded.
--
-- A NOT NULL column with a default would have been worse: it would make the invented
-- answer indistinguishable from a real one for ever after.
--
-- ## No cross-matter listing
--
-- The rule is enforced in `gateway/store.list_conversations`, which REQUIRES a matter_id
-- and refuses without one -- not by a policy on `app.matter_id`. A second RLS setting
-- would mean a user who legitimately moves between matters needs a new connection per
-- matter, and every cross-matter operational query (the failure report, the cache stats)
-- would silently return nothing. Tenant isolation is a security boundary and belongs in
-- the database; matter scoping is an access-and-tidiness rule about one query shape.
--
-- That distinction is the whole design, and it is why `matters` itself is FORCE RLS
-- (another firm must never see a client list) while `matter_id` on the work tables is an
-- ordinary indexed column.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-019 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 284 checks, 0 failures, then dropped. `matters` is the TWENTY-FIRST tenant-scoped table
-- and is proved like the rest: A sees its own and none of B's, the policy dropped fails
-- CLOSED, RLS disabled LEAKS B's row, restoring returns to isolation.

BEGIN;

CREATE TABLE IF NOT EXISTS matters (
    matter_id  uuid        PRIMARY KEY,
    tenant_id  uuid        NOT NULL REFERENCES tenants(tenant_id),
    name       text        NOT NULL CHECK (length(btrim(name)) > 0),
    -- The firm's own reference for the client. Free text on purpose: every firm already
    -- has a numbering scheme and none of them is ours to design.
    client_ref text        NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    closed_at  timestamptz,

    CONSTRAINT matters_closed_after_creation CHECK (
        closed_at IS NULL OR closed_at >= created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS matters_tenant_name_idx
    ON matters (tenant_id, lower(name));

ALTER TABLE conversations    ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(matter_id);
ALTER TABLE runs             ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(matter_id);
ALTER TABLE drafts           ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(matter_id);
ALTER TABLE review_grids     ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(matter_id);
ALTER TABLE documents        ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters(matter_id);

CREATE INDEX IF NOT EXISTS conversations_matter_idx ON conversations (tenant_id, matter_id);
CREATE INDEX IF NOT EXISTS runs_matter_idx          ON runs (tenant_id, matter_id);
CREATE INDEX IF NOT EXISTS drafts_matter_idx        ON drafts (tenant_id, matter_id);
CREATE INDEX IF NOT EXISTS review_grids_matter_idx  ON review_grids (tenant_id, matter_id);

ALTER TABLE matters ENABLE ROW LEVEL SECURITY;
ALTER TABLE matters FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON matters;
CREATE POLICY tenant_isolation ON matters USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON TABLE matters IS
  'One piece of work for one client. FORCE RLS because a client list is the most '
  'commercially sensitive thing a firm has -- it names who they act for.';
COMMENT ON COLUMN conversations.matter_id IS
  'NULL means NOT FILED to a matter, which is its own bucket and never "belongs to '
  'whichever matter you asked for". Backfilling would invent a client relationship.';

COMMIT;
