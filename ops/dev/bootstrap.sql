-- One-time elevated steps that no migration can do, run as the superuser AFTER migrations.
-- Idempotent. Production ran the same once by hand (gateway/migrations/026_accounts.sql).
--   psql -v tenant=<uuid> -v actor=<uuid> -f ops/dev/bootstrap.sql

-- 1. The sign-in lookup functions must be owned by a BYPASSRLS role, or nobody can sign in.
--    Same statements as scripts/rls_integration.py `_ensure_authn_role`.
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'placedon_authn') AS need_authn \gset
\if :need_authn
CREATE ROLE placedon_authn NOSUPERUSER NOLOGIN BYPASSRLS;
\endif
GRANT USAGE ON SCHEMA public TO placedon_authn;
GRANT SELECT ON actors, sessions, invites TO placedon_authn;
ALTER FUNCTION auth_find_login(text)      OWNER TO placedon_authn;
ALTER FUNCTION auth_resolve_session(text) OWNER TO placedon_authn;
ALTER FUNCTION invite_find_by_token(text) OWNER TO placedon_authn;
GRANT EXECUTE ON FUNCTION auth_find_login(text), auth_resolve_session(text),
                          invite_find_by_token(text) TO placedon_app;

-- 2. The local tenant and the service actor the gateway key acts as (.env).
INSERT INTO tenants (tenant_id, name) VALUES (:'tenant', 'local dev')
    ON CONFLICT (tenant_id) DO NOTHING;
INSERT INTO actors (actor_id, tenant_id, label, role) VALUES (:'actor', :'tenant', 'local service', 'lawyer')
    ON CONFLICT (actor_id) DO NOTHING;
