-- 033_login_email_unique.sql — one sign-in per email, across every firm.
--
-- Why: sign-in is by email alone (auth_find_login, 026), and auth.login refuses an email
-- that matches more than one account (DECISION_ACCOUNTS.md Decision 7). Uniqueness was only
-- per firm (018 actors_tenant_email_idx), so an admin of firm B could invite a firm-A
-- person's email, accept the invite themselves, and lock that person out of sign-in for
-- good. With this index the second account cannot be created: accept_invite's INSERT hits
-- a unique violation, which gateway/store.py already turns into INVALID_INVITE.
--
-- Partial, to match exactly what auth_find_login reads: an actor with no email or no
-- password (a service actor, an API-key-only row) cannot sign in and stays unconstrained.
--
-- FAIL SAFE: this migration never deletes or edits a row. If two sign-in accounts already
-- share an email it REFUSES, naming how many emails collide (not which -- that is personal
-- data in a deploy log), and the transaction rolls back. An operator resolves each one by
-- hand (clear the password or change the email on the account that should not sign in)
-- and re-runs. To list them, as a superuser or BYPASSRLS role:
--
--     SELECT lower(email), count(*) FROM actors
--     WHERE email IS NOT NULL AND password_hash IS NOT NULL
--     GROUP BY 1 HAVING count(*) > 1;
--
-- The check reads tenant by tenant because migrations run as placedon_app, which FORCE RLS
-- confines to one app.tenant_id at a time; `tenants` has no RLS. The setting is
-- transaction-local and ends with this migration's transaction. If the check were ever
-- bypassed, CREATE UNIQUE INDEX itself fails on a duplicate (an index build is not subject
-- to RLS), so the backstop is the same refusal.

BEGIN;

DO $$
DECLARE
    t uuid;
    n integer;
BEGIN
    CREATE TEMP TABLE login_email_033 (e text) ON COMMIT DROP;
    FOR t IN SELECT tenant_id FROM tenants LOOP
        PERFORM set_config('app.tenant_id', t::text, true);
        -- tenant_id = t as well as the policy: a BYPASSRLS runner would otherwise read
        -- every firm on every pass and count each email once per firm.
        INSERT INTO login_email_033
            SELECT lower(email) FROM actors
            WHERE tenant_id = t AND email IS NOT NULL AND password_hash IS NOT NULL;
    END LOOP;
    SELECT count(*) INTO n FROM (
        SELECT e FROM login_email_033 GROUP BY e HAVING count(*) > 1) dup;
    IF n > 0 THEN
        RAISE EXCEPTION '033 refused: % email address(es) already have more than one sign-in account. Nothing was changed.', n
            USING HINT = 'Resolve each by hand (see the query at the top of 033_login_email_unique.sql), then re-run the migration.';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS actors_login_email_global_idx
    ON actors (lower(email)) WHERE email IS NOT NULL AND password_hash IS NOT NULL;

COMMIT;
