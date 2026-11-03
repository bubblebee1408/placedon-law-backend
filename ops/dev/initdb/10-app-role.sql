-- The application role, exactly as .github/workflows/gate.yml creates it: a login role with
-- no superuser and no BYPASSRLS, so FORCE ROW LEVEL SECURITY binds it as it does in production.
-- The password is a local throwaway, the same one CI uses; production's is in its secret store.
CREATE ROLE placedon_app LOGIN PASSWORD 'local-only-not-a-secret' NOSUPERUSER NOBYPASSRLS;
