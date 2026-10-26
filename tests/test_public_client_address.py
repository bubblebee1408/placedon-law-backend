"""Sign-in lockout and public-verb rate limits behind the frontend proxy.

Every sign-in through the frontend reached the gateway from the frontend's own address,
and the lockout counts failures per email OR per address -- so five wrong passwords from
anyone locked out everyone. The fix trusts a forwarded client address ONLY from a request
carrying an API key minted as a client-address proxy; direct requests and other keys are
counted by their real socket address, and per-account (email) lockout is unchanged.

Opt-in, like the other *_postgres tests (PLACEDON_CONVERSATION_TEST_DATABASE_URL /
_ADMIN_URL on a placedon_throwaway_ database migrated through 029).
"""
import os
import unittest
import uuid
from urllib.parse import urlparse

from tests.test_accounts_postgres import AUTHN_BOOTSTRAP

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")
HEADER = "X-Placedon-Client-Address"
GOOD = "a long synthetic passphrase"


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class PublicClientAddress(unittest.TestCase):
    def setUp(self):
        import psycopg
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        from gateway.passwords import hash_password
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only explicitly named throwaway databases may be used")
        self.tenant, self.run = str(uuid.uuid4()), uuid.uuid4().hex[:8]
        self.emails = {n: f"{n}-{self.run}@example.test" for n in ("a", "b", "c")}
        pw = hash_password(GOOD)
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            for sql in AUTHN_BOOTSTRAP:
                c.execute(sql)
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'proxy test')", (self.tenant,))
            for email in self.emails.values():
                c.execute("INSERT INTO actors (actor_id, tenant_id, label, role, email, password_hash) "
                          "VALUES (%s,%s,'lawyer','lawyer',%s,%s)", (str(uuid.uuid4()), self.tenant, email, pw))
        keys = KeyStore()
        self.proxy_key, _ = keys.mint(tenant_id=self.tenant, actor=str(uuid.uuid4()), label="frontend",
                                      role="viewer", client_address_proxy=True)
        self.other_key, _ = keys.mint(tenant_id=self.tenant, actor=str(uuid.uuid4()), label="other",
                                      role="viewer")
        self.peer = f"192.0.2.{int(self.run[2:4], 16)}"
        self.client = TestClient(create_app(db_url=APP_URL, keys=keys), client=(self.peer, 50000))

    def addr(self, n):            # a fresh client address per test run
        return f"198.51.{int(self.run[:2], 16)}.{n}"

    def login(self, who, password, *, key=None, address=None):
        return self.login_as(self.emails[who], password, key=key, address=address)

    def login_as(self, email, password, *, key=None, address=None):
        headers = {}
        if key:
            headers["Authorization"] = "Bearer " + key
        if address is not None:
            headers[HEADER] = address
        r = self.client.post("/v2/auth/login", json={"email": email, "password": password}, headers=headers)
        return r.status_code, r.json()

    def test_one_users_failures_through_the_proxy_do_not_lock_out_a_colleague(self):
        for _ in range(6):
            self.login("a", "wrong password guess", key=self.proxy_key, address=self.addr(1))
        status, body = self.login("b", GOOD, key=self.proxy_key, address=self.addr(2))
        self.assertEqual((status, body.get("status")), (200, "ok"), body)
        self.assertEqual(self.login("a", GOOD, key=self.proxy_key, address=self.addr(1))[1].get("code"),
                         "LOCKED_OUT", "...while the failing account itself stays locked")

    def test_per_account_lockout_survives_a_rotating_client_address(self):
        for n in range(6):
            self.login("c", "wrong password guess", key=self.proxy_key, address=self.addr(10 + n))
        self.assertEqual(self.login("c", GOOD, key=self.proxy_key, address=self.addr(20))[1].get("code"),
                         "LOCKED_OUT")

    def test_a_forwarded_address_from_anyone_but_the_proxy_is_ignored(self):
        for key in (None, self.other_key):
            with self.subTest(key="none" if key is None else "non-proxy key"):
                # Direct requests claim fresh addresses; they are counted by socket address,
                # so the claim buys nothing and the socket's own budget runs out.
                # Different (unknown) emails each time, so only the ADDRESS bucket can lock.
                codes = [self.login_as(f"nobody-{self.run}-{key is None}-{n}@example.test", "wrong",
                                       key=key, address=f"203.0.113.{n}")[1].get("code")
                         for n in range(6)]
                self.assertEqual(codes[-1], "LOCKED_OUT", codes)
                self.client = self.client.__class__(self.client.app,
                                                    client=(self.peer[:-1] + "9", 50000))

    def test_a_malformed_forwarded_address_creates_no_bucket_of_its_own(self):
        for bad in ("198.51.100.1, 10.0.0.1", "not-an-address", "198.51.100.1:443", ""):
            with self.subTest(bad=bad):
                status, body = self.login("b", "wrong", key=self.proxy_key, address=bad)
                self.assertIn(status, (200, 429))
        self.login("b", "wrong", key=self.proxy_key, address="evil")
        self.assertEqual(self.login("b", GOOD, key=self.proxy_key, address="evil")[1].get("code"), "LOCKED_OUT",
                         "malformed values fall back to per-account counting, which still locks the account")
        status, body = self.login("a", GOOD, key=self.proxy_key, address="")
        self.assertEqual(body.get("status"), "ok", "...and they do not share one bucket with a colleague")

    def test_public_verbs_are_rate_limited_per_client_address(self):
        statuses = [self.client.post("/v2/invites/accept", json={"token": "x" * 43, "password": GOOD},
                                     headers={"Authorization": "Bearer " + self.proxy_key, HEADER: self.addr(40)}).status_code
                    for _ in range(40)]
        self.assertIn(429, statuses, "a flood from one client address is bounded")
        other = self.client.post("/v2/invites/accept", json={"token": "x" * 43, "password": GOOD},
                                 headers={"Authorization": "Bearer " + self.proxy_key, HEADER: self.addr(41)})
        self.assertEqual(other.status_code, 200, "another client behind the same proxy is not affected")
        direct = [self.client.post("/v2/invites/accept", json={"token": "x" * 43, "password": GOOD},
                                   headers={HEADER: f"203.0.113.{n}"}).status_code for n in range(40)]
        self.assertIn(429, direct, "a direct flood cannot spread itself across spoofed addresses")


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class InviteAcceptance(PublicClientAddress):
    """Tokens are unguessable; these pin the other three properties: single use under
    concurrency, expiry, and a per-client cap on how fast anyone can try."""

    def invite(self, *, expired=False):
        import psycopg
        from gateway.accounts import mint_token
        raw, token_hash = mint_token()
        email = f"invitee-{uuid.uuid4().hex[:8]}@example.test"
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            inviter = c.execute("SELECT actor_id FROM actors WHERE tenant_id = %s LIMIT 1",
                                (self.tenant,)).fetchone()[0]
            c.execute("INSERT INTO invites (invite_id, tenant_id, email, role, token_hash, invited_by, "
                      "created_at, expires_at) VALUES (%s,%s,%s,'lawyer',%s,%s, now() - interval '9 days', "
                      "now() + (CASE WHEN %s THEN interval '-1 day' ELSE interval '1 day' END))",
                      (str(uuid.uuid4()), self.tenant, email, token_hash, inviter, expired))
        return raw, email

    def accept(self, token, address):
        return self.client.post("/v2/invites/accept", json={"token": token, "password": GOOD},
                                headers={"Authorization": "Bearer " + self.proxy_key, HEADER: address}).json()

    def accounts_for(self, email):
        import psycopg
        with psycopg.connect(ADMIN_URL) as c:
            return c.execute("SELECT count(*) FROM actors WHERE email = %s", (email,)).fetchone()[0]

    def test_an_expired_invite_is_refused_and_creates_nothing(self):
        token, email = self.invite(expired=True)
        self.assertEqual(self.accept(token, self.addr(60)).get("code"), "INVALID_INVITE")
        self.assertEqual(self.accounts_for(email), 0)

    def test_concurrent_accepts_of_one_invite_create_exactly_one_account(self):
        from concurrent.futures import ThreadPoolExecutor
        token, email = self.invite()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda n: self.accept(token, self.addr(70 + n)), range(8)))
        self.assertEqual(sum(r.get("status") == "accepted" for r in results), 1, results)
        # The rest are refused, or turned away by the executor's cap before any work began.
        self.assertTrue(all(r.get("code") == "INVALID_INVITE" or r.get("error") == "busy"
                            for r in results if r.get("status") != "accepted"), results)
        self.assertTrue(any(r.get("code") == "INVALID_INVITE" for r in results), "some accepts really raced")
        self.assertEqual(self.accounts_for(email), 1)

    test_one_users_failures_through_the_proxy_do_not_lock_out_a_colleague = None
    test_per_account_lockout_survives_a_rotating_client_address = None
    test_a_forwarded_address_from_anyone_but_the_proxy_is_ignored = None
    test_a_malformed_forwarded_address_creates_no_bucket_of_its_own = None
    test_public_verbs_are_rate_limited_per_client_address = None


if __name__ == "__main__":
    unittest.main()
