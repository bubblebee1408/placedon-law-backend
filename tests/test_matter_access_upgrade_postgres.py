"""Upgrading a POPULATED pre-028 database through scripts/migrate.py, then regaining access.

Opt-in, like the other *_postgres tests: PLACEDON_CONVERSATION_TEST_DATABASE_URL (the app
role) and PLACEDON_CONVERSATION_TEST_ADMIN_URL (a superuser), on a `placedon_throwaway_`
database. Only their host and users are used: this test creates its OWN database,
`placedon_throwaway_upgrade_<pid>`, and drops it afterwards.

The order is production's: 001-027 applied by the migrator, rows written the way pre-028
code wrote them, then 028 applied by the same migrator -- refused while the only backup
role is the app role (FORCE RLS hides rows from pg_dump), applied once --backup-url names
a role that can read them. Then nobody inherits access, and an admin restores it.
"""
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlparse

from gateway.store import PostgresBackend
from gateway.verbs import Context, by_name
from scripts.migrate import DEFAULT_DIR, cmd_apply

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")
V = by_name()

T = "11111111-1111-1111-1111-111111111111"
ADM, A, B = (str(uuid.uuid4()) for _ in range(3))
M1, M2 = str(uuid.uuid4()), str(uuid.uuid4())
C1, C2, C3 = (str(uuid.uuid4()) for _ in range(3))
D1, D2 = str(uuid.uuid4()), str(uuid.uuid4())
F1, R1 = str(uuid.uuid4()), str(uuid.uuid4())

LEGACY = [  # as the pre-028 code left it: no uploader, no draft author, no grants
    ("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'Legacy firm')", (T,)),
    ("INSERT INTO actors (actor_id, tenant_id, label, role) VALUES (%s,%s,'admin','admin'),"
     "(%s,%s,'lawyer A','lawyer'),(%s,%s,'lawyer B','lawyer')", (ADM, T, A, T, B, T)),
    ("INSERT INTO matters (matter_id, tenant_id, name) VALUES (%s,%s,'Acme acquisition'),"
     "(%s,%s,'Beta dispute')", (M1, T, M2, T)),
    ("INSERT INTO conversations (conversation_id, tenant_id, actor_id, title, matter_id) "
     "VALUES (%s,%s,%s,'Acme quorum',%s),(%s,%s,%s,'A unfiled',NULL),"
     "(%s,%s,NULL,'Orphan thread',NULL)", (C1, T, A, M1, C2, T, A, C3, T)),
    ("INSERT INTO messages (message_id, conversation_id, tenant_id, ordinal, role, text) "
     "VALUES (%s,%s,%s,0,'user','What is the quorum?'),"
     "(%s,%s,%s,0,'user','An orphaned question')",
     (str(uuid.uuid4()), C1, T, str(uuid.uuid4()), C3, T)),
    ("INSERT INTO vault_documents (document_id, tenant_id, matter_id, sha256, name, "
     "byte_count, state) VALUES (%s,%s,%s,repeat('a',64),'acme-minutes.pdf',10,'INGESTED'),"
     "(%s,%s,NULL,repeat('b',64),'unfiled-notice.pdf',10,'INGESTED')", (D1, T, M1, D2, T)),
    ("INSERT INTO vault_chunks (document_id, tenant_id, ordinal, text) VALUES "
     "(%s,%s,0,'Acme board minutes text'),(%s,%s,0,'Unfiled notice text')", (D1, T, D2, T)),
    ("INSERT INTO drafts (draft_id, tenant_id, kind, title) VALUES "
     "(%s,%s,'research_memo','Legacy memo')", (F1, T)),
    ("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status) VALUES "
     "(%s,%s,%s,'ask','ANSWERED')", (R1, T, A)),
]


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class MatterAccessUpgrade(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.db = f"placedon_throwaway_upgrade_{os.getpid()}"
        def on(url, db):   # the same server and user, another database
            u = urlparse(url)
            return f"{u.scheme}://{u.netloc}/{db}" + (f"?{u.query}" if u.query else "")
        app = urlparse(APP_URL)
        self.app_url, self.super_url = on(APP_URL, self.db), on(ADMIN_URL, self.db)
        server = on(ADMIN_URL, "postgres")
        app_user = app.username or dict(p.split("=", 1) for p in app.query.split("&")
                                        if "=" in p).get("user")
        with psycopg.connect(server, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{self.db}" WITH (FORCE)')
            c.execute(f'CREATE DATABASE "{self.db}" OWNER "{app_user}"')

        def drop():
            with psycopg.connect(server, autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{self.db}" WITH (FORCE)')
        self.addCleanup(drop)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def ctx(self, actor, role):
        return Context(tenant=T, actor=actor, role=role,
                       store=PostgresBackend(self.app_url, tenant_id=T, actor_id=actor))

    def run_verb(self, verb, args, actor, role="lawyer"):
        return V[verb].run(args, self.ctx(actor, role))

    def test_populated_database_upgrades_through_the_migrator_and_access_is_regained(self):
        import psycopg
        pre = self.tmp / "pre028"
        pre.mkdir()
        for f in sorted(DEFAULT_DIR.glob("0*.sql")):
            if int(f.name[:3]) < 28:
                shutil.copy(f, pre / f.name)
        backups = self.tmp / "backups"
        self.assertEqual(cmd_apply(self.app_url, pre, backups), 0, "001-027 apply")
        with psycopg.connect(self.super_url, autocommit=True) as c:
            for sql, params in LEGACY:
                c.execute(sql, params)

        # The supported procedure, and its refusal.
        self.assertEqual(cmd_apply(self.app_url, DEFAULT_DIR, backups), 2,
                         "the app role cannot back up rows RLS hides, so nothing applies")
        with psycopg.connect(self.super_url) as c:
            self.assertIsNone(c.execute("SELECT 1 FROM schema_migrations WHERE version='028'")
                              .fetchone())
        self.assertEqual(cmd_apply(self.app_url, DEFAULT_DIR, backups,
                                   backup_url=self.super_url), 0,
                         "with a backup role on the same database: backed up, then applied")
        dumps = sorted(backups.glob(f"{self.db}_*.dump"))
        self.assertGreater(dumps[-1].stat().st_size, 0)

        nf = lambda r: r.get("code") == "NOT_FOUND"                       # noqa: E731
        # Nobody inherits access from being in the firm.
        self.assertEqual(self.run_verb("matters.list", {}, A)["matters"], [])
        self.assertTrue(nf(self.run_verb("conversation.get", {"conversation_id": C1}, A)))
        self.assertEqual(self.run_verb("conversation.get", {"conversation_id": C2}, A)
                         ["conversation"]["conversation_id"], C2, "A's own unfiled thread")
        self.assertTrue(nf(self.run_verb("vault.status", {"document_id": D1}, A)))
        self.assertTrue(nf(self.run_verb("vault.status", {"document_id": D2}, A)))
        self.assertTrue(nf(self.run_verb("draft.status", {"draft_id": F1}, A)))
        self.assertEqual(self.run_verb("runs.get", {"run_id": R1}, A)["status"], "ANSWERED")
        self.assertTrue(nf(self.run_verb("conversation.get", {"conversation_id": C1}, ADM,
                                         "admin")), "an admin is not a member by being admin")

        report = self.run_verb("matters.access_report", {}, ADM, "admin")
        self.assertEqual(set(report["matters_without_members"]), {M1, M2})
        self.assertEqual([d["id"] for d in report["unowned"]["vault_document"]], [D2])
        self.assertEqual([d["id"] for d in report["unowned"]["draft"]], [F1])
        self.assertEqual([d["id"] for d in report["unowned"]["conversation"]], [C3],
                         "A's own unfiled thread is not 'unowned': it is A's")

        # Regaining access, only through the admin path.
        self.assertEqual(self.run_verb("matters.grant", {"matter_id": M1, "actor_id": A,
                                                         "role": "owner",
                                                         "reason": "A leads the Acme matter"},
                                       ADM, "admin")["status"], "GRANTED")
        for kind, rid, to in (("vault_document", D2, {"to_actor": A}),
                              ("draft", F1, {"to_actor": A}),
                              ("conversation", C3, {"to_matter": M1})):
            out = self.run_verb("access.reassign", dict(to, kind=kind, id=rid,
                                                        reason="placed by the admin after 028"),
                                ADM, "admin")
            self.assertEqual(out["status"], "REASSIGNED", (kind, out))
        self.assertEqual([m["matter_id"] for m in self.run_verb("matters.list", {}, A)
                          ["matters"]], [M1])
        self.assertEqual(len(self.run_verb("conversation.get", {"conversation_id": C1}, A)
                             ["messages"]), 1)
        self.assertEqual(len(self.run_verb("conversation.get", {"conversation_id": C3}, A)
                             ["messages"]), 1, "the orphan thread, filed to Acme, reaches A")
        self.assertEqual(self.run_verb("vault.status", {"document_id": D1}, A)["name"],
                         "acme-minutes.pdf")
        self.assertEqual(self.run_verb("vault.status", {"document_id": D2}, A)["name"],
                         "unfiled-notice.pdf")
        self.assertEqual(self.run_verb("draft.status", {"draft_id": F1}, A)["draft_id"], F1)
        self.assertEqual(len(self.run_verb("vault.find", {"query": "text"}, A)["hits"]), 2)

        # ...without granting anyone else in the firm.
        self.assertTrue(nf(self.run_verb("conversation.get", {"conversation_id": C1}, B)))
        self.assertEqual(self.run_verb("vault.find", {"query": "text"}, B)["hits"], [])
        self.assertTrue(nf(self.run_verb("conversation.get", {"conversation_id": C3}, ADM,
                                         "admin")), "placing work grants the admin nothing")
        self.assertEqual(self.run_verb("access.reassign",
                                       {"kind": "conversation", "id": C2, "to_actor": B,
                                        "reason": "move A's own thread"}, ADM, "admin")
                         ["status"], "REFUSED", "an owner's own work is not reassigned")
        with self.assertRaises(Exception):
            PostgresBackend(self.app_url, tenant_id=T, actor_id=B).grant_matter_access(
                matter_id=M1, actor_id=B, role="owner", granted_by=B, reason="self-promotion")
        events = self.run_verb("matters.access_report", {}, ADM, "admin")
        self.assertEqual(events["unowned"]["conversation"], [], "nothing left to place")


if __name__ == "__main__":
    unittest.main()
