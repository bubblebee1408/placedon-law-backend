-- 001_core.sql — tenants, actors, keys, documents, audit.
--
-- Every tenant-scoped table below gets BOTH of these, and the second is the one that
-- matters:
--
--     ALTER TABLE x ENABLE ROW LEVEL SECURITY;
--     ALTER TABLE x FORCE  ROW LEVEL SECURITY;
--
-- ENABLE alone exempts the table's OWNER, and the owner is whoever the application
-- connects as in most deployments — so a schema with ENABLE and no FORCE reads as isolated
-- and is not. FORCE applies the policy to the owner too. `scripts/rls_integration.py`
-- exists to prove this on a real server, and to fail if a later migration drops it.
--
-- Isolation is by `current_setting('app.tenant_id')`, set per request by the gateway and
-- never by the client. A policy that trusted a column the caller supplies would be a
-- filter, not a boundary.
--
-- STATUS: UNAPPLIED. No Postgres has run this file. gateway/app.py reports
-- store.kind = "in-memory" until it has.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   uuid PRIMARY KEY,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS actors (
    actor_id    uuid PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    label       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- The HASH, never the key. gateway/auth.py stores sha256(key) and returns the raw value
-- once; this column is the same discipline at rest. A UNIQUE index on the hash is what
-- makes a lookup a lookup rather than a scan-and-compare.
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    text PRIMARY KEY,
    key_id      text NOT NULL,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    actor_id    uuid NOT NULL REFERENCES actors(actor_id),
    label       text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz,
    CONSTRAINT api_keys_hash_is_sha256 CHECK (key_hash ~ '^[0-9a-f]{64}$')
);

-- A document is identified BY its sha256 (gateway/verbs.py does the same in memory), so
-- uploading the same bytes twice is one document and not two rows claiming to differ.
CREATE TABLE IF NOT EXISTS documents (
    sha256      text NOT NULL,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    name        text NOT NULL DEFAULT '',
    byte_count  bigint NOT NULL CHECK (byte_count >= 0),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    body        bytea,
    PRIMARY KEY (tenant_id, sha256),
    CONSTRAINT documents_sha256_shape CHECK (sha256 ~ '^[0-9a-f]{64}$')
);

-- Append-only and hash-chained, mirroring gateway/audit.py. There is no `body` column and
-- there will not be one: the chain records that a thing happened, never what was in it.
-- The absence of an UPDATE or DELETE grant is the append-only part; a trigger enforces it
-- against the owner too, for the same reason FORCE ROW LEVEL SECURITY exists.
CREATE TABLE IF NOT EXISTS audit_log (
    seq         bigserial PRIMARY KEY,
    tenant_id   uuid NOT NULL REFERENCES tenants(tenant_id),
    request_id  uuid NOT NULL,
    actor_id    uuid NOT NULL,
    ts          timestamptz NOT NULL,
    action      text NOT NULL CHECK (action IN ('READ', 'WRITE')),
    route       text NOT NULL,
    resource    text NOT NULL,
    outcome     text NOT NULL,
    http_status integer NOT NULL,
    prev_digest char(64) NOT NULL,
    digest      char(64) NOT NULL UNIQUE,
    CONSTRAINT audit_no_control_chars
        CHECK (route !~ '[\n\r\t]' AND resource !~ '[\n\r\t]' AND outcome !~ '[\n\r\t]')
);

CREATE OR REPLACE FUNCTION audit_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; % is refused', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_no_update ON audit_log;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_is_append_only();

-- ── isolation ───────────────────────────────────────────────────────────────
ALTER TABLE actors    ENABLE ROW LEVEL SECURITY;
ALTER TABLE actors    FORCE  ROW LEVEL SECURITY;
ALTER TABLE api_keys  ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys  FORCE  ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE  ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON actors;
CREATE POLICY tenant_isolation ON actors USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON api_keys;
CREATE POLICY tenant_isolation ON api_keys USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON documents;
CREATE POLICY tenant_isolation ON documents USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
DROP POLICY IF EXISTS tenant_isolation ON audit_log;
CREATE POLICY tenant_isolation ON audit_log USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMIT;
