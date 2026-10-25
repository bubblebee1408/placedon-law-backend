"""026 accounts over HTTP against real PostgreSQL: invite -> accept -> sign in -> who am I.

Opt-in, like the other *_postgres tests: PLACEDON_CONVERSATION_TEST_DATABASE_URL (the app
role) and PLACEDON_CONVERSATION_TEST_ADMIN_URL (a superuser), on a `placedon_throwaway_`
database migrated through 028. The superuser performs 026's one-time sign-in bootstrap
(the three SECURITY DEFINER functions owned by a BYPASSRLS role), as an operator would.
"""
import os
import unittest
import uuid
from urllib.parse import urlparse

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")
AUTHN_BOOTSTRAP = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='placedon_authn') "
    "THEN CREATE ROLE placedon_authn NOSUPERUSER NOLOGIN BYPASSRLS; END IF; END $$",
    "GRANT USAGE ON SCHEMA public TO placedon_authn",
    "GRANT SELECT ON actors, sessions, invites TO placedon_authn",
    "ALTER FUNCTION auth_find_login(text) OWNER TO placedon_authn",
    "ALTER FUNCTION auth_resolve_session(text) OWNER TO placedon_authn",
    "ALTER FUNCTION invite_find_by_token(text) OWNER TO placedon_authn",
    "GRANT EXECUTE ON FUNCTION auth_find_login(text), auth_resolve_session(text), "
    "invite_find_by_token(text) TO placedon_app",
)


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class AccountsPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only explicitly named throwaway databases may be used")
        self.tenant, self.admin = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            for sql in AUTHN_BOOTSTRAP:
                c.execute(sql)
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'accounts test')",
                      (self.tenant,))
            c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                      "VALUES (%s,%s,'synthetic admin','admin')", (self.admin, self.tenant))
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        keys = KeyStore()
        self.key, _ = keys.mint(tenant_id=self.tenant, actor=self.admin, role="admin")
        self.client = TestClient(create_app(db_url=APP_URL, keys=keys))
        self.email = f"lawyer-{self.tenant[:8]}@example.test"

    def post(self, path, body, bearer=None):
        headers = {"Authorization": "Bearer " + bearer} if bearer else {}
        return self.client.post(path, json=body, headers=headers)

    def test_an_invited_lawyer_accepts_signs_in_and_is_themselves(self):
        invite = self.post("/v2/invites/create", {"email": self.email, "role": "lawyer"},
                           self.key).json()
        self.assertTrue(invite.get("token"))
        accepted = self.post("/v2/invites/accept",
                             {"token": invite["token"], "password": "a long synthetic passphrase"})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["role"], "lawyer", "the role comes from the invite")
        login = self.post("/v2/auth/login",
                          {"email": self.email, "password": "a long synthetic passphrase"})
        self.assertEqual(login.status_code, 200, login.text)
        me = self.post("/v2/auth/me", {}, login.json()["token"]).json()
        self.assertEqual((me["actor_id"], me["tenant_id"], me["role"]),
                         (accepted.json()["actor_id"], self.tenant, "lawyer"),
                         "the session token IS the person: their actor, their firm")

        again = self.post("/v2/invites/accept",
                          {"token": invite["token"], "password": "a second synthetic passphrase"})
        self.assertEqual(again.json().get("code"), "INVALID_INVITE", "an invite is single-use")
        import psycopg
        with psycopg.connect(ADMIN_URL) as c:
            n = c.execute("SELECT count(*) FROM actors WHERE email = %s", (self.email,)).fetchone()[0]
        self.assertEqual(n, 1, "a refused second accept leaves no second account behind")


if __name__ == "__main__":
    unittest.main()
