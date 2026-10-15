-- 026_accounts.sql — sign-in, sessions, and the cross-tenant reads authentication needs.
--
-- Design authority: .claude/loops/DECISION_ACCOUNTS.md (Decisions 1-7). Read it first.
--
-- ## The hard problem, restated
--
-- Every tenant table is isolated by `current_setting('app.tenant_id')` under FORCE ROW
-- LEVEL SECURITY. At sign-in we have only an email; when a session token arrives we have
-- only the token. Neither names a tenant, so a normal query under RLS returns nothing
-- rather than everything -- correct for every other table, and exactly the problem for
-- these three reads, which must run BEFORE a tenant is known.
--
-- ## Three SECURITY DEFINER functions, not two
--
-- DECISION_ACCOUNTS.md Decision 4 says "these two functions are the only cross-tenant
-- reads of tenant data" -- auth_find_login and auth_resolve_session. Building invites.accept
-- surfaced a THIRD: `invites` is tenant-scoped exactly like `actors`, and an invite's raw
-- token does not name its tenant either, so resolving "which invite does this token belong
-- to" has the identical authentication-precedes-tenant-knowledge shape as auth_find_login,
-- keyed by token instead of email. `invite_find_by_token` is added here on that reasoning,
-- flagged as a DEVIATION from Decision 4's count -- the design doc should be amended to say
-- three. The SPEND itself (`accept_invite` in gateway/store.py, unchanged) stays a normal,
-- tenant-scoped, single-row UPDATE once the tenant is known, so the single-use guarantee
-- (`accepted_at IS NULL` in its WHERE clause) is untouched: only the lookup that finds which
-- tenant to run that UPDATE under is new.
--
-- ## Why SECURITY DEFINER alone is not enough here, and what IS required at deploy time
--
-- `actors` and `invites` carry FORCE ROW LEVEL SECURITY, and FORCE applies the policy to
-- the table OWNER too (001_core.sql's own comment: "FORCE applies the policy to the owner
-- too"). Migrations run as `placedon_app` (scripts/migrate.py refuses to run as a
-- superuser), so a SECURITY DEFINER function left owned by `placedon_app` -- the role that
-- creates it here -- would still be filtered by RLS like any other `placedon_app` query: it
-- would see nothing with no tenant set, which defeats the whole point.
--
-- A SECURITY DEFINER function bypasses RLS only when its OWNER does: a superuser, or a role
-- with the BYPASSRLS attribute. Granting BYPASSRLS requires a superuser and `placedon_app`
-- is deliberately NOSUPERUSER/NOBYPASSRLS (scripts/rls_integration.py), so this migration
-- CANNOT do that reassignment itself. It is a one-time, elevated, OUT-OF-MIGRATION bootstrap
-- step -- the same category as `scripts/rls_integration.py`'s own `_ensure_app_role`, which
-- already creates `placedon_app` before any migration runs as it:
--
--     -- run ONCE, as a superuser (e.g. the role that can CREATE ROLE), AFTER this
--     -- migration has created the three functions below:
--     CREATE ROLE placedon_authn NOSUPERUSER NOLOGIN BYPASSRLS;
--     GRANT USAGE ON SCHEMA public TO placedon_authn;
--     GRANT SELECT ON actors, sessions, invites TO placedon_authn;
--     ALTER FUNCTION auth_find_login(text)      OWNER TO placedon_authn;
--     ALTER FUNCTION auth_resolve_session(text) OWNER TO placedon_authn;
--     ALTER FUNCTION invite_find_by_token(text) OWNER TO placedon_authn;
--
-- BYPASSRLS alone is not enough: it bypasses row-level POLICIES, not the ordinary GRANT a
-- role still needs to read a table at all. Measured live against a real server: the first
-- version of this bootstrap granted only BYPASSRLS, and every one of the three functions
-- failed with "permission denied for table actors" -- a different, earlier gate than RLS,
-- and the GRANT SELECT lines above are what it actually takes to pass it.
--
-- `scripts/rls_integration.py` performs exactly this bootstrap in its elevated `--run` path
-- (see `_ensure_authn_role`), so the live proof exercises the real bypass, not merely the
-- function text. Until that reassignment happens on a deployment, these three functions
-- return nothing cross-tenant (the SAFE failure direction: a login or an invite accept
-- would see no match rather than another tenant's row) -- noted so a missing bootstrap step
-- reads as "nobody can sign in", not as a silent leak.
--
-- `search_path` is pinned in each definition so a caller cannot shadow `actors`, `invites`
-- or `sessions` with a same-named object earlier in its own search_path.
--
-- ## sessions: tenant-scoped, FORCE RLS, proved like every other table
--
-- Created and revoked through the NORMAL tenant-scoped path once a tenant is known
-- (Decision 4: "set app.tenant_id and insert normally") -- the only tenant-blind operation
-- on this table is the lookup-by-token-hash function below.
--
-- ## login_attempts: NOT tenant-scoped, on purpose
--
-- Brute-force defence must count failures for an email or an IP *before* any tenant is
-- known and ACROSS all tenants, so a tenant_id column would defeat its own purpose. It
-- still gets FORCE ROW LEVEL SECURITY, with an explicit `USING (true)` policy that says "no
-- row restriction, on purpose" -- it holds only one-way hashes (`email_hash`, `ip_hash`) and
-- a boolean, so there is no tenant content to isolate and no SECURITY DEFINER escape hatch
-- is needed for it: any connection may read and write it freely by design.
--
-- STATUS: UNAPPLIED until scripts/rls_integration.py's elevated bootstrap and `--run` have
-- proved it against a real server (see that script's docstring for the dated result).

BEGIN;

CREATE TABLE IF NOT EXISTS sessions (
    session_id  uuid        PRIMARY KEY,
    tenant_id   uuid        NOT NULL REFERENCES tenants(tenant_id),
    actor_id    uuid        NOT NULL REFERENCES actors(actor_id),
    -- The HASH, never the token -- the same discipline as api_keys (001) and invites (018).
    token_hash  text        NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    CONSTRAINT sessions_expires_after_creation CHECK (expires_at > created_at)
);

-- Global, not per-tenant: a token is looked up by its hash alone, before the tenant is
-- known, which is exactly why auth_resolve_session exists.
CREATE UNIQUE INDEX IF NOT EXISTS sessions_token_hash_idx ON sessions (token_hash);
CREATE INDEX IF NOT EXISTS sessions_actor_idx ON sessions (actor_id) WHERE revoked_at IS NULL;

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON sessions;
CREATE POLICY tenant_isolation ON sessions USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);

CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_id  bigserial   PRIMARY KEY,
    -- sha256 of the lowercased email / of the client IP. One-way; never the value itself.
    email_hash  text        NOT NULL CHECK (email_hash ~ '^[0-9a-f]{64}$'),
    ip_hash     text        NOT NULL CHECK (ip_hash ~ '^[0-9a-f]{64}$'),
    at          timestamptz NOT NULL DEFAULT now(),
    ok          boolean     NOT NULL
);

CREATE INDEX IF NOT EXISTS login_attempts_email_idx ON login_attempts (email_hash, at);
CREATE INDEX IF NOT EXISTS login_attempts_ip_idx ON login_attempts (ip_hash, at);

ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_attempts FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS global_access ON login_attempts;
CREATE POLICY global_access ON login_attempts USING (true);

-- ── Decision 1: auth_find_login ──────────────────────────────────────────────
--
-- Every actors row whose lower(email) matches and whose password_hash IS NOT NULL. More
-- than one row means the email is ambiguous across tenants; auth.login refuses generically
-- rather than guessing (Decision 7). Exactly these four columns: no tenant content, no name,
-- no role -- a password hash that is already one-way and useless without the password, and
-- enough to decide disabled/ambiguous/unknown.
CREATE OR REPLACE FUNCTION auth_find_login(p_email text)
RETURNS TABLE (actor_id uuid, tenant_id uuid, password_hash text, disabled_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT a.actor_id, a.tenant_id, a.password_hash, a.disabled_at
    FROM actors a
    WHERE lower(a.email) = lower(p_email) AND a.password_hash IS NOT NULL;
$$;

REVOKE ALL ON FUNCTION auth_find_login(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_find_login(text) TO placedon_app;

-- ── Decision 2: auth_resolve_session ─────────────────────────────────────────
--
-- At most one row (token_hash is globally unique). `role` and `disabled_at` are joined from
-- actors LIVE, not cached on the session row, so a role change or a disablement takes effect
-- on the very next request without needing the session re-minted. No token_hash, no tenant
-- content beyond the two ids the caller already has by holding a valid session.
CREATE OR REPLACE FUNCTION auth_resolve_session(p_token_hash text)
RETURNS TABLE (actor_id uuid, tenant_id uuid, role text, expires_at timestamptz,
               revoked_at timestamptz, disabled_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT s.actor_id, s.tenant_id, a.role, s.expires_at, s.revoked_at, a.disabled_at
    FROM sessions s
    JOIN actors a ON a.actor_id = s.actor_id
    WHERE s.token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION auth_resolve_session(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION auth_resolve_session(text) TO placedon_app;

-- ── invite_find_by_token (the third function; see the top-of-file note) ─────
--
-- Which tenant and what role an unguessable invite token names, so invites.accept can set
-- app.tenant_id and run the EXISTING, tenant-scoped, single-use accept_invite() UPDATE
-- (gateway/store.py) under normal RLS. Returns nothing for an unknown token; never the
-- token_hash itself (the caller already holds the raw token, which is strictly more).
CREATE OR REPLACE FUNCTION invite_find_by_token(p_token_hash text)
RETURNS TABLE (invite_id uuid, tenant_id uuid, email text, role text,
               expires_at timestamptz, accepted_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
    SELECT i.invite_id, i.tenant_id, i.email, i.role, i.expires_at, i.accepted_at
    FROM invites i
    WHERE i.token_hash = p_token_hash;
$$;

REVOKE ALL ON FUNCTION invite_find_by_token(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION invite_find_by_token(text) TO placedon_app;

COMMENT ON TABLE sessions IS
  'A person''s signed-in session. The HASH of the token, never the token. Tenant-scoped and '
  'FORCE RLS like every other table; the one tenant-blind read is auth_resolve_session.';
COMMENT ON TABLE login_attempts IS
  'email_hash/ip_hash/at/ok only -- no tenant content, so USING (true) is deliberate, not an '
  'oversight. Brute-force counting must span tenants by construction.';
COMMENT ON FUNCTION auth_find_login(text) IS
  'SECURITY DEFINER cross-tenant read #1 of 3. Must be owned by a BYPASSRLS role (NOT '
  'placedon_app) for the bypass to work under FORCE ROW LEVEL SECURITY -- see the top-of-file '
  'note and scripts/rls_integration.py:_ensure_authn_role.';
COMMENT ON FUNCTION auth_resolve_session(text) IS
  'SECURITY DEFINER cross-tenant read #2 of 3. Same ownership requirement as auth_find_login.';
COMMENT ON FUNCTION invite_find_by_token(text) IS
  'SECURITY DEFINER cross-tenant read #3 of 3 -- added beyond DECISION_ACCOUNTS.md Decision '
  '4''s count of two; see the top-of-file note. Same ownership requirement.';

COMMIT;
