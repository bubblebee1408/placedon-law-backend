-- 018_users_roles.sql — who a person is, and what they are allowed to do.
--
-- 8a. `actors` already existed with a label and a tenant; it is the user row, so this
-- extends it rather than adding a second table that would immediately disagree with it
-- about who exists.
--
-- ## role
--
-- The three from gateway/roles.py, restated as a CHECK because the application is not the
-- only thing that can write this column, and a row saying role='superuser' would be read
-- by `may()` as an unknown role and refused -- correct, but only after the row exists.
-- Refusing it at the door is better.
--
-- DEFAULT 'viewer' is the safe default: a row created without a role can read and change
-- nothing. The dangerous default is the other one, and it is the one that gets chosen
-- when the column is added to a table that already has rows.
--
-- ## password_hash
--
-- scrypt, from gateway/passwords.py, in its self-describing form. NULL means this actor
-- has no password -- an API-key-only service account, or a person who has been invited
-- and has not accepted. NULL is NOT "any password works", and `verify_password` refuses
-- an empty stored hash, which is the second place that is enforced.
--
-- ## invites
--
-- A token HASH, never the token: the same discipline as api_keys, for the same reason.
-- The raw token goes in one email and exists nowhere else.
--
-- Single use is enforced by `accepted_at`, and the partial unique index below is what
-- makes "one live invite per email per tenant" true in the database rather than in a
-- handler that forgets. An expired or accepted invite does not block a new one.
--
-- STATUS: applied 2026-10-02 by scripts/rls_integration.py to a fresh PostgreSQL 18.6
-- database as 001-018 together, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS):
-- 271 checks, 0 failures, then dropped. `invites` is the TWENTIETH tenant-scoped table and
-- is proved like the rest: A sees its own and none of B's, the policy dropped fails CLOSED,
-- RLS disabled LEAKS B's row, restoring returns to isolation.

BEGIN;

ALTER TABLE actors ADD COLUMN IF NOT EXISTS role          text NOT NULL DEFAULT 'viewer';
ALTER TABLE actors ADD COLUMN IF NOT EXISTS email         text;
ALTER TABLE actors ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE actors ADD COLUMN IF NOT EXISTS disabled_at   timestamptz;

ALTER TABLE actors DROP CONSTRAINT IF EXISTS actors_role_known;
ALTER TABLE actors ADD CONSTRAINT actors_role_known
    CHECK (role IN ('viewer', 'lawyer', 'admin'));

-- A password hash is scrypt in its self-describing form, or nothing at all. A column that
-- accepted a bare hex digest would accept a SHA-256 of a password, which is the mistake
-- gateway/passwords.py exists to make impossible.
ALTER TABLE actors DROP CONSTRAINT IF EXISTS actors_password_is_scrypt;
ALTER TABLE actors ADD CONSTRAINT actors_password_is_scrypt
    CHECK (password_hash IS NULL OR password_hash LIKE 'scrypt$%');

-- One account per email per tenant, case-insensitively. Partial, so the many service
-- actors with no email do not collide with each other.
CREATE UNIQUE INDEX IF NOT EXISTS actors_tenant_email_idx
    ON actors (tenant_id, lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS invites (
    invite_id   uuid        PRIMARY KEY,
    tenant_id   uuid        NOT NULL REFERENCES tenants(tenant_id),
    email       text        NOT NULL CHECK (position('@' in email) > 1),
    role        text        NOT NULL CHECK (role IN ('viewer', 'lawyer', 'admin')),
    token_hash  text        NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    invited_by  uuid        NOT NULL REFERENCES actors(actor_id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    accepted_at timestamptz,
    accepted_by uuid        REFERENCES actors(actor_id),

    -- An invite expires. One with no horizon is a credential, and a credential sitting in
    -- an inbox for a year is the one that gets used by whoever buys the laptop.
    CONSTRAINT invites_expires_after_creation CHECK (expires_at > created_at),
    -- Accepted means accepted BY someone. Half a record of who joined is worse than none:
    -- it reads as an accepted invite whose user cannot be found.
    CONSTRAINT invites_accepted_together CHECK (
        (accepted_at IS NULL AND accepted_by IS NULL) OR
        (accepted_at IS NOT NULL AND accepted_by IS NOT NULL))
);

-- One LIVE invite per email per tenant. An accepted or expired one does not block a new
-- one, which is why this is partial rather than a plain unique constraint.
CREATE UNIQUE INDEX IF NOT EXISTS invites_live_per_email_idx
    ON invites (tenant_id, lower(email)) WHERE accepted_at IS NULL;

CREATE INDEX IF NOT EXISTS invites_token_idx ON invites (token_hash)
    WHERE accepted_at IS NULL;

ALTER TABLE invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE invites FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON invites;
CREATE POLICY tenant_isolation ON invites USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

COMMENT ON COLUMN actors.role IS
  'viewer | lawyer | admin, ordered. gateway/roles.py is the authority on what each may '
  'call; this CHECK stops a row naming a role that does not exist from being written at '
  'all. DEFAULT viewer because the safe default is the one that can change nothing.';
COMMENT ON COLUMN actors.password_hash IS
  'scrypt from gateway/passwords.py. NULL means NO password -- a service account or an '
  'unaccepted invite -- and never "any password works".';
COMMENT ON TABLE invites IS
  'The token HASH, never the token: the raw value goes in one email and exists nowhere '
  'else. Single use via accepted_at, enforced by a partial unique index.';

COMMIT;
