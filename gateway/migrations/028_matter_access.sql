-- 028_matter_access.sql — who may use which matter, enforced by the database.
--
-- ## What changes
--
-- Until now a tenant (a firm) was the only boundary: any signed-in person could read any
-- matter's conversations, documents, drafts and runs by naming its id. 019's own comment
-- said so ("matter scoping is an access-and-tidiness rule about one query shape"). This
-- makes a matter an ACCESS boundary:
--
--   * A matter is readable only by an actor with an ACTIVE grant in `matter_memberships`.
--     Grants are explicit. Nothing here infers one from tenant membership, and existing
--     matters start with NO members: an authenticated firm admin grants access through the
--     `matters.grant` API after this migration is applied.
--   * Unfiled work (matter_id IS NULL) belongs to the actor who created it. Unfiled vault
--     documents are uploader-private unless the uploader SHARES them firm-wide.
--   * Work that predates owner tracking -- unfiled vault documents, and drafts, review
--     tables and conversations written without an actor -- is readable by NOBODY until an
--     admin gives it an owner or a matter (`access.reassign`, listed by
--     `matters.access_report`). That is the cost of not guessing whose it was.
--   * Admins see matter METADATA (names, members) so they can administer access. They do
--     not see a matter's contents, or anyone's unfiled work, without a grant or a
--     reassignment, each of which is recorded.
--
-- ## How identity reaches the policies
--
-- Every connection sets, on every checkout (gateway/pool.py, store.py, jobs.py):
--
--   app.tenant_id    as before
--   app.actor_id     the authenticated actor, or '' for none
--   app.actor_scope  '' for a person, or ONE of three narrow scopes, each named only in
--                    the policies it needs and nowhere else:
--
--     queue            gateway/jobs.py's own connections. The only scope that reads
--                      `jobs`. Reaches `runs` only to set a PLANNED/RUNNING run whose job
--                      is DEAD to FAILED, and nothing else under this rule: no finished
--                      run, run step, conversation, message, document, chunk, draft, grid
--                      or matter.
--     grant_bootstrap  store.write_matter, transaction-local: the creator's OWN first
--                      owner grant on the matter it just inserted. INSERT on
--                      matter_memberships only, and only a self-grant of `owner`.
--     reassign         store.list_unowned / reassign_work, transaction-local, behind the
--                      admin-only verbs. The metadata row of UNFILED work that has NO
--                      owner (a document, draft, review table or conversation) -- never a
--                      filed row, never someone's own unfiled work, never a content table
--                      (chunks, tags, messages, versions, cells).
--
-- A connection with no actor sees no matter-bound or unfiled row: the policies fail CLOSED.
-- Identity and scope are both set by the application role, as app.tenant_id always was, so
-- the database cannot stop a compromised application from claiming them. What it DOES
-- guarantee is that every ordinary query is filtered by the actor -- including queries
-- nobody remembered to filter -- and that a code path holding a scope reaches only what
-- that scope names.
--
-- ## Restrictive policies
--
-- Each policy below is AS RESTRICTIVE, so it is ANDed with the existing permissive
-- `tenant_isolation` policy rather than widening it. A row must be in the caller's tenant
-- AND pass the matter rule.

BEGIN;

CREATE TABLE IF NOT EXISTS matter_memberships (
    membership_id uuid        PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES tenants (tenant_id),
    matter_id     uuid        NOT NULL REFERENCES matters (matter_id),
    actor_id      uuid        NOT NULL REFERENCES actors (actor_id),
    role          text        NOT NULL CHECK (role IN ('owner', 'member', 'viewer')),
    granted_by    uuid        NOT NULL REFERENCES actors (actor_id),
    granted_at    timestamptz NOT NULL DEFAULT now(),
    grant_reason  text        NOT NULL CHECK (length(btrim(grant_reason)) > 0),
    revoked_at    timestamptz,
    revoked_by    uuid        REFERENCES actors (actor_id),
    revoke_reason text,

    CONSTRAINT matter_memberships_revoked_together CHECK (
        (revoked_at IS NULL) = (revoked_by IS NULL)
        AND (revoked_at IS NULL) = (revoke_reason IS NULL)),
    CONSTRAINT matter_memberships_revoked_after_grant CHECK (
        revoked_at IS NULL OR revoked_at >= granted_at)
);

-- One ACTIVE grant per person per matter. A role change is a revoke plus a new grant, so
-- the table is its own history and nothing is overwritten.
CREATE UNIQUE INDEX IF NOT EXISTS matter_memberships_active_idx
    ON matter_memberships (matter_id, actor_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS matter_memberships_actor_idx
    ON matter_memberships (tenant_id, actor_id) WHERE revoked_at IS NULL;

-- Append-only apart from the single revocation. An audit trail that can be edited is not one.
CREATE OR REPLACE FUNCTION matter_memberships_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'matter_memberships is append-only: revoke a grant, never delete it';
    END IF;
    IF OLD.revoked_at IS NOT NULL
       OR NEW.membership_id IS DISTINCT FROM OLD.membership_id
       OR NEW.tenant_id     IS DISTINCT FROM OLD.tenant_id
       OR NEW.matter_id     IS DISTINCT FROM OLD.matter_id
       OR NEW.actor_id      IS DISTINCT FROM OLD.actor_id
       OR NEW.role          IS DISTINCT FROM OLD.role
       OR NEW.granted_by    IS DISTINCT FROM OLD.granted_by
       OR NEW.granted_at    IS DISTINCT FROM OLD.granted_at
       OR NEW.grant_reason  IS DISTINCT FROM OLD.grant_reason THEN
        RAISE EXCEPTION 'matter_memberships is append-only: only an active grant may be revoked, once';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS matter_memberships_append_only ON matter_memberships;
CREATE TRIGGER matter_memberships_append_only
    BEFORE UPDATE OR DELETE ON matter_memberships
    FOR EACH ROW EXECUTE FUNCTION matter_memberships_append_only();

-- Who uploaded a vault document, and whether it was shared firm-wide while unfiled.
-- NULL uploaded_by on existing rows is deliberate: see the header.
ALTER TABLE vault_documents ADD COLUMN IF NOT EXISTS uploaded_by uuid REFERENCES actors (actor_id);
ALTER TABLE vault_documents ADD COLUMN IF NOT EXISTS shared_with_firm_at timestamptz;
ALTER TABLE vault_documents ADD COLUMN IF NOT EXISTS shared_by uuid REFERENCES actors (actor_id);
ALTER TABLE vault_documents DROP CONSTRAINT IF EXISTS vault_documents_share_shape;
ALTER TABLE vault_documents ADD CONSTRAINT vault_documents_share_shape CHECK (
    (shared_with_firm_at IS NULL) = (shared_by IS NULL)
    AND (shared_with_firm_at IS NULL OR matter_id IS NULL));

-- Duplicate detection was per TENANT: the same bytes twice in a firm were one document.
-- Under per-matter access that is a disclosure -- lawyer B uploading a file would learn that
-- someone else in the firm already holds it, and be handed a document id B cannot read.
-- The same bytes are now one document per MATTER, or per UPLOADER while unfiled. The blob
-- store is content-addressed and nothing deletes a blob by hash, so two rows sharing bytes
-- is safe.
ALTER TABLE vault_documents DROP CONSTRAINT IF EXISTS vault_documents_tenant_sha;
CREATE UNIQUE INDEX IF NOT EXISTS vault_documents_matter_sha
    ON vault_documents (tenant_id, matter_id, sha256) WHERE matter_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS vault_documents_owner_sha
    ON vault_documents (tenant_id, uploaded_by, sha256) WHERE matter_id IS NULL;

-- Every change to who can reach a piece of work other than a matter grant: sharing a
-- document firm-wide, and an admin reassigning an owner or a matter.
CREATE TABLE IF NOT EXISTS access_events (
    event_id      uuid        PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES tenants (tenant_id),
    resource_kind text        NOT NULL CHECK (resource_kind IN
                                  ('vault_document', 'draft', 'review_grid', 'conversation')),
    resource_id   uuid        NOT NULL,
    action        text        NOT NULL CHECK (action IN ('share', 'unshare', 'reassign')),
    by_actor      uuid        NOT NULL REFERENCES actors (actor_id),
    from_actor    uuid        REFERENCES actors (actor_id),
    to_actor      uuid        REFERENCES actors (actor_id),
    from_matter   uuid        REFERENCES matters (matter_id),
    to_matter     uuid        REFERENCES matters (matter_id),
    reason        text        NOT NULL CHECK (length(btrim(reason)) > 0),
    at            timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION access_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'access_events is append-only';
END $$;

DROP TRIGGER IF EXISTS access_events_append_only ON access_events;
CREATE TRIGGER access_events_append_only
    BEFORE UPDATE OR DELETE ON access_events
    FOR EACH ROW EXECUTE FUNCTION access_events_append_only();

-- ── the rule, once ────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION placedon_actor() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.actor_id', true), '')::uuid
$$;

CREATE OR REPLACE FUNCTION placedon_scope(name text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT coalesce(current_setting('app.actor_scope', true), '') = name
$$;

CREATE OR REPLACE FUNCTION placedon_is_admin() RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM actors a
                   WHERE a.actor_id = placedon_actor() AND a.role = 'admin'
                     AND a.disabled_at IS NULL)
$$;

CREATE OR REPLACE FUNCTION placedon_matter_role(m uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT mm.role FROM matter_memberships mm
    JOIN actors a ON a.actor_id = mm.actor_id AND a.disabled_at IS NULL
    WHERE mm.matter_id = m AND mm.actor_id = placedon_actor() AND mm.revoked_at IS NULL
$$;

-- Unfiled rows belong to `owner`; filed rows to the matter's members.
CREATE OR REPLACE FUNCTION placedon_can_read(m uuid, owner uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN m IS NULL THEN owner IS NOT NULL AND owner = placedon_actor()
        ELSE placedon_matter_role(m) IS NOT NULL END
$$;

CREATE OR REPLACE FUNCTION placedon_can_write(m uuid, owner uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN m IS NULL THEN owner IS NOT NULL AND owner = placedon_actor()
        ELSE coalesce(placedon_matter_role(m) IN ('owner', 'member'), false) END
$$;

-- A vault document's content is readable exactly when the document is.
CREATE OR REPLACE FUNCTION placedon_doc_readable(d uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM vault_documents v WHERE v.document_id = d
        AND (placedon_can_read(v.matter_id, v.uploaded_by)
             OR (v.matter_id IS NULL AND v.shared_with_firm_at IS NOT NULL)))
$$;

CREATE OR REPLACE FUNCTION placedon_doc_writable(d uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM vault_documents v WHERE v.document_id = d
        AND placedon_can_write(v.matter_id, v.uploaded_by))
$$;

-- The queue's one reach into `runs` (see the runs policies below): the run of a DEAD job,
-- while it is still PLANNED or RUNNING, and as the FAILED row the reconcile leaves (an
-- UPDATE's new row is checked against the read policy too). Never an ANSWERED, REFUSED or
-- ABSTAINED run, which is where answers live. Reads `jobs`, which only the queue scope
-- can see, so it is false for everyone else.
CREATE OR REPLACE FUNCTION placedon_queue_reconciles(r uuid, status text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT placedon_scope('queue') AND status IN ('PLANNED', 'RUNNING', 'FAILED')
       AND EXISTS (SELECT 1 FROM jobs j WHERE j.run_id = r AND j.status = 'DEAD')
$$;

-- Four restrictive policies per table: read, insert, update, delete.
CREATE OR REPLACE FUNCTION pg_temp.matter_policies(t text, r text, w text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('DROP POLICY IF EXISTS matter_read ON %I', t);
    EXECUTE format('DROP POLICY IF EXISTS matter_insert ON %I', t);
    EXECUTE format('DROP POLICY IF EXISTS matter_update ON %I', t);
    EXECUTE format('DROP POLICY IF EXISTS matter_delete ON %I', t);
    EXECUTE format('CREATE POLICY matter_read ON %I AS RESTRICTIVE FOR SELECT USING (%s)', t, r);
    EXECUTE format('CREATE POLICY matter_insert ON %I AS RESTRICTIVE FOR INSERT WITH CHECK (%s)', t, w);
    EXECUTE format('CREATE POLICY matter_update ON %I AS RESTRICTIVE FOR UPDATE USING (%s) WITH CHECK (%s)', t, w, w);
    EXECUTE format('CREATE POLICY matter_delete ON %I AS RESTRICTIVE FOR DELETE USING (%s)', t, w);
END $$;

-- Parents: the row carries its own matter and owner. (The reassign scope's reach into
-- the four reassignable parents is added below, with the vault.)
SELECT pg_temp.matter_policies(t, 'placedon_can_read(matter_id, actor_id)',
                               'placedon_can_write(matter_id, actor_id)')
FROM unnest(ARRAY['conversations', 'drafts', 'review_grids']) AS t;

-- `runs` admits the queue scope for ONE thing, gateway/jobs.py's reconcile: a run still
-- PLANNED or RUNNING whose job is DEAD, set to FAILED (placedon_queue_reconciles). Not a finished run (which holds
-- the answer), not a live job's run, and nothing the queue could insert or delete.
SELECT pg_temp.matter_policies('runs',
    'placedon_can_read(matter_id, actor_id) OR placedon_queue_reconciles(runs.run_id, runs.status)',
    'placedon_can_write(matter_id, actor_id)');
DROP POLICY IF EXISTS matter_update ON runs;
CREATE POLICY matter_update ON runs AS RESTRICTIVE FOR UPDATE
    USING (placedon_can_write(matter_id, actor_id)
           OR (placedon_queue_reconciles(run_id, status) AND status <> 'FAILED'))
    WITH CHECK (placedon_can_write(matter_id, actor_id)
                OR (placedon_queue_reconciles(run_id, status) AND status = 'FAILED'));

-- Children: the parent's matter and owner are checked HERE, explicitly. A child policy
-- that only asked "is the parent visible?" would inherit every scope the parent admits,
-- and a scope that may see a parent's metadata row is not thereby allowed its contents.
SELECT pg_temp.matter_policies('messages',
    'EXISTS (SELECT 1 FROM conversations p WHERE p.conversation_id = messages.conversation_id '
    'AND placedon_can_read(p.matter_id, p.actor_id))',
    'EXISTS (SELECT 1 FROM conversations p WHERE p.conversation_id = messages.conversation_id '
    'AND placedon_can_write(p.matter_id, p.actor_id))');
SELECT pg_temp.matter_policies(t,
    format('EXISTS (SELECT 1 FROM runs p WHERE p.run_id = %I.run_id '
           'AND placedon_can_read(p.matter_id, p.actor_id))', t),
    format('EXISTS (SELECT 1 FROM runs p WHERE p.run_id = %I.run_id '
           'AND placedon_can_write(p.matter_id, p.actor_id))', t))
FROM unnest(ARRAY['run_steps', 'propositions', 'decisions', 'cascade_runs']) AS t;
SELECT pg_temp.matter_policies('draft_versions',
    'EXISTS (SELECT 1 FROM drafts p WHERE p.draft_id = draft_versions.draft_id '
    'AND placedon_can_read(p.matter_id, p.actor_id))',
    'EXISTS (SELECT 1 FROM drafts p WHERE p.draft_id = draft_versions.draft_id '
    'AND placedon_can_write(p.matter_id, p.actor_id))');
SELECT pg_temp.matter_policies(t,
    format('EXISTS (SELECT 1 FROM review_grids p WHERE p.grid_id = %I.grid_id '
           'AND placedon_can_read(p.matter_id, p.actor_id))', t),
    format('EXISTS (SELECT 1 FROM review_grids p WHERE p.grid_id = %I.grid_id '
           'AND placedon_can_write(p.matter_id, p.actor_id))', t))
FROM unnest(ARRAY['review_grid_columns', 'review_grid_cells']) AS t;

-- Jobs carry a question's words and the ids of what it names in `args`. Only the queue
-- (gateway/jobs.py, every connection under the queue scope) claims, writes and lists
-- them; no person's connection reads another's job. jobs.dead filters to the caller's
-- own jobs in the application, and the worker runs each job as that job's actor.
DROP POLICY IF EXISTS queue_only ON jobs;
CREATE POLICY queue_only ON jobs AS RESTRICTIVE USING (placedon_scope('queue'))
    WITH CHECK (placedon_scope('queue'));

-- The answer cache holds a lawyer's question in their own words. An entry is filed to the
-- matter it was asked in, or owned by the actor who asked it unfiled, and is reused only
-- inside that boundary (gateway/verbs.py `_cache_partition`). Entries written before 028
-- carry neither and are reachable by nobody: they are derived, so the cost is a re-answer.
ALTER TABLE answer_cache ADD COLUMN IF NOT EXISTS actor_id uuid REFERENCES actors (actor_id);
ALTER TABLE answer_cache ADD COLUMN IF NOT EXISTS matter_id uuid REFERENCES matters (matter_id);
SELECT pg_temp.matter_policies('answer_cache',
    'placedon_can_read(matter_id, actor_id)', 'placedon_can_write(matter_id, actor_id)');

-- The vault: a shared unfiled document is readable by the firm, writable by its uploader.
SELECT pg_temp.matter_policies('vault_documents',
    'placedon_can_read(matter_id, uploaded_by) '
    'OR (matter_id IS NULL AND shared_with_firm_at IS NOT NULL)',
    'placedon_can_write(matter_id, uploaded_by)');

-- The reassign scope, on the four reassignable parents. It sees and may change an
-- ORPHAN: unfiled, with no owner. The row it produces (now owned, or filed to a matter)
-- stays in its reach only for the rest of the transaction that recorded the change in
-- access_events -- Postgres checks an UPDATE's new row against the read policy too, and
-- this is the narrowest condition that lets the change land without widening what the
-- scope can see. Another person's unfiled work is never in reach.
CREATE OR REPLACE FUNCTION placedon_reassigning(kind text, id uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT placedon_scope('reassign') AND EXISTS (
        SELECT 1 FROM access_events e
        WHERE e.resource_kind = kind AND e.resource_id = id AND e.action = 'reassign'
          AND e.by_actor = placedon_actor()
          AND e.xmin = pg_current_xact_id_if_assigned()::xid)
$$;
DO $$
DECLARE t text; k text; i text; o text; extra text;
BEGIN
    FOR t, k, i, o IN VALUES
            ('conversations', 'conversation', 'conversation_id', 'actor_id'),
            ('drafts', 'draft', 'draft_id', 'actor_id'),
            ('review_grids', 'review_grid', 'grid_id', 'actor_id'),
            ('vault_documents', 'vault_document', 'document_id', 'uploaded_by') LOOP
        extra := CASE WHEN t = 'vault_documents'
                      THEN ' OR (matter_id IS NULL AND shared_with_firm_at IS NOT NULL)'
                      ELSE '' END;
        EXECUTE format('DROP POLICY IF EXISTS matter_read ON %I', t);
        EXECUTE format('CREATE POLICY matter_read ON %I AS RESTRICTIVE FOR SELECT '
                       'USING (placedon_can_read(matter_id, %I)%s '
                       '       OR (placedon_scope(''reassign'') AND matter_id IS NULL '
                       '           AND %I IS NULL) '
                       '       OR placedon_reassigning(%L, %I))', t, o, extra, o, k, i);
        EXECUTE format('DROP POLICY IF EXISTS matter_update ON %I', t);
        EXECUTE format('CREATE POLICY matter_update ON %I AS RESTRICTIVE FOR UPDATE '
                       'USING (placedon_can_write(matter_id, %I) '
                       '       OR (placedon_scope(''reassign'') AND matter_id IS NULL '
                       '           AND %I IS NULL)) '
                       'WITH CHECK (placedon_can_write(matter_id, %I) '
                       '            OR placedon_reassigning(%L, %I))', t, o, o, o, k, i);
    END LOOP;
END $$;
SELECT pg_temp.matter_policies(t,
    format('placedon_doc_readable(%I.document_id)', t),
    format('placedon_doc_writable(%I.document_id)', t))
FROM unnest(ARRAY['vault_chunks', 'vault_tags', 'document_checks']) AS t;

-- Matters themselves: members and admins see a matter exists; creating one is ordinary.
-- No scope reaches this table.
DROP POLICY IF EXISTS matter_read ON matters;
CREATE POLICY matter_read ON matters AS RESTRICTIVE FOR SELECT
    USING (placedon_matter_role(matter_id) IS NOT NULL OR placedon_is_admin());
DROP POLICY IF EXISTS matter_update ON matters;
CREATE POLICY matter_update ON matters AS RESTRICTIVE FOR UPDATE
    USING (placedon_matter_role(matter_id) = 'owner' OR placedon_is_admin());
DROP POLICY IF EXISTS matter_delete ON matters;
CREATE POLICY matter_delete ON matters AS RESTRICTIVE FOR DELETE
    USING (placedon_is_admin());

-- Grants: you see your own; admins see and write all. The one other writer is a matter's
-- creator granting ITSELF owner, under grant_bootstrap, inside the creating transaction
-- (gateway/store.py write_matter).
ALTER TABLE matter_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE matter_memberships FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON matter_memberships;
CREATE POLICY tenant_isolation ON matter_memberships USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS membership_read ON matter_memberships;
CREATE POLICY membership_read ON matter_memberships AS RESTRICTIVE FOR SELECT
    USING (actor_id = placedon_actor() OR placedon_is_admin());
DROP POLICY IF EXISTS membership_insert ON matter_memberships;
CREATE POLICY membership_insert ON matter_memberships AS RESTRICTIVE FOR INSERT
    WITH CHECK (placedon_is_admin()
                OR (placedon_scope('grant_bootstrap') AND role = 'owner'
                    AND actor_id = placedon_actor() AND granted_by = placedon_actor()));
DROP POLICY IF EXISTS membership_update ON matter_memberships;
CREATE POLICY membership_update ON matter_memberships AS RESTRICTIVE FOR UPDATE
    USING (placedon_is_admin());

ALTER TABLE access_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE access_events FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON access_events;
CREATE POLICY tenant_isolation ON access_events USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
-- Written only as the actor who made the change; read by admins and by that actor.
DROP POLICY IF EXISTS event_read ON access_events;
CREATE POLICY event_read ON access_events AS RESTRICTIVE FOR SELECT
    USING (by_actor = placedon_actor() OR placedon_is_admin());
DROP POLICY IF EXISTS event_insert ON access_events;
CREATE POLICY event_insert ON access_events AS RESTRICTIVE FOR INSERT
    WITH CHECK (by_actor = placedon_actor());

COMMENT ON TABLE matter_memberships IS
  'Explicit, append-only grants. Never inferred from tenant membership. Revoke, never delete.';
COMMENT ON COLUMN vault_documents.uploaded_by IS
  'NULL for documents uploaded before 028: readable by nobody until an admin reassigns them.';
COMMENT ON TABLE access_events IS
  'Append-only: every share, unshare and admin reassignment, with who, why and from what.';

COMMIT;
