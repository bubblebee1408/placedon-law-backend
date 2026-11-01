-- 032_company_profile.sql — the firm's company profile, entered once and reused.
--
-- Design: docs/architecture/COMPANY_PROFILE.md. One profile per tenant: the buyer is an
-- in-house legal team, so the firm IS the company. Per-matter profiles could be added later
-- with a nullable matter_id; nothing here forecloses it.
--
-- One row per CONFIRMED fact. A change never edits a row: the old row is marked superseded
-- (by whom, when) and a new row is inserted, so the table is its own history and nothing is
-- ever deleted. The current profile is the rows with superseded_at IS NULL, at most one per
-- field (company_profile_facts_current_idx).
--
-- Additive: one new table, its trigger and its policies. No existing row is touched.

BEGIN;

CREATE TABLE IF NOT EXISTS company_profile_facts (
    fact_id       uuid        PRIMARY KEY,
    tenant_id     uuid        NOT NULL REFERENCES tenants (tenant_id),
    -- checker/sources/company_facts.FIELDS, plus company_class (the calendar's one
    -- required class field; see the design note for why figures are NOT here).
    field         text        NOT NULL CHECK (field IN ('cin', 'name', 'status', 'roc',
                                  'address', 'state', 'incorporated_on', 'listed',
                                  'company_class')),
    value         text        NOT NULL CHECK (length(btrim(value)) > 0),
    -- USER_FACT: typed by a person. COMPANY_FACT: read from an MCA master-data page.
    basis         text        NOT NULL CHECK (basis IN ('USER_FACT', 'COMPANY_FACT')),
    source_label  text        NOT NULL CHECK (length(btrim(source_label)) > 0),
    quoted_span   text        NOT NULL DEFAULT '',
    uploaded_on   date,
    confirmed_by  uuid        NOT NULL REFERENCES actors (actor_id),
    confirmed_at  timestamptz NOT NULL DEFAULT now(),
    reason        text        NOT NULL CHECK (length(btrim(reason)) > 0),
    superseded_at timestamptz,
    superseded_by uuid        REFERENCES actors (actor_id),

    CONSTRAINT company_profile_facts_superseded_together CHECK (
        (superseded_at IS NULL) = (superseded_by IS NULL)),
    -- A typed fact has no document to quote; a document fact must quote it and date it.
    CONSTRAINT company_profile_facts_provenance CHECK (
        (basis = 'USER_FACT' AND quoted_span = '' AND uploaded_on IS NULL)
        OR (basis = 'COMPANY_FACT' AND length(btrim(quoted_span)) > 0
            AND uploaded_on IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS company_profile_facts_current_idx
    ON company_profile_facts (tenant_id, field) WHERE superseded_at IS NULL;

-- Append-only apart from superseding a current row, once.
CREATE OR REPLACE FUNCTION company_profile_facts_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'company_profile_facts is append-only: supersede a fact, never delete it';
    END IF;
    IF OLD.superseded_at IS NOT NULL
       OR NEW.fact_id      IS DISTINCT FROM OLD.fact_id
       OR NEW.tenant_id    IS DISTINCT FROM OLD.tenant_id
       OR NEW.field        IS DISTINCT FROM OLD.field
       OR NEW.value        IS DISTINCT FROM OLD.value
       OR NEW.basis        IS DISTINCT FROM OLD.basis
       OR NEW.source_label IS DISTINCT FROM OLD.source_label
       OR NEW.quoted_span  IS DISTINCT FROM OLD.quoted_span
       OR NEW.uploaded_on  IS DISTINCT FROM OLD.uploaded_on
       OR NEW.confirmed_by IS DISTINCT FROM OLD.confirmed_by
       OR NEW.confirmed_at IS DISTINCT FROM OLD.confirmed_at
       OR NEW.reason       IS DISTINCT FROM OLD.reason THEN
        RAISE EXCEPTION 'company_profile_facts is append-only: only a current fact may be superseded, once';
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS company_profile_facts_append_only ON company_profile_facts;
CREATE TRIGGER company_profile_facts_append_only
    BEFORE UPDATE OR DELETE ON company_profile_facts
    FOR EACH ROW EXECUTE FUNCTION company_profile_facts_append_only();

ALTER TABLE company_profile_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_profile_facts FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON company_profile_facts;
CREATE POLICY tenant_isolation ON company_profile_facts USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
-- Firm-wide reads (every person in the firm uses the profile). A write is recorded as the
-- actor making it, never on someone else's behalf; the LAWYER minimum is gateway/roles.py.
DROP POLICY IF EXISTS profile_insert ON company_profile_facts;
CREATE POLICY profile_insert ON company_profile_facts AS RESTRICTIVE FOR INSERT
    WITH CHECK (confirmed_by = placedon_actor());
DROP POLICY IF EXISTS profile_update ON company_profile_facts;
CREATE POLICY profile_update ON company_profile_facts AS RESTRICTIVE FOR UPDATE
    USING (placedon_actor() IS NOT NULL) WITH CHECK (superseded_by = placedon_actor());

COMMENT ON TABLE company_profile_facts IS
  'One confirmed company fact per row, per firm. Supersede, never delete or edit.';

COMMIT;
