"""028 per-matter access against real PostgreSQL, as the restricted app role.

Opt-in, like the other *_postgres tests: set PLACEDON_CONVERSATION_TEST_DATABASE_URL (the
app role) and PLACEDON_CONVERSATION_TEST_ADMIN_URL (a superuser, used only to create
synthetic tenants/actors and legacy rows), both naming a `placedon_throwaway_` database
migrated through 028. Every test uses its own synthetic tenant.
"""
import os
import unittest
import uuid
from dataclasses import replace
from urllib.parse import urlparse

from gateway.jobs import PostgresQueue
from gateway.store import PostgresBackend
from gateway.verbs import Context, by_name
from gateway.worker import ACCESS_REVOKED, run_one

APP_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_DATABASE_URL", "")
ADMIN_URL = os.environ.get("PLACEDON_CONVERSATION_TEST_ADMIN_URL", "")
V = by_name()


@unittest.skipUnless(APP_URL and ADMIN_URL, "Explicit throwaway PostgreSQL URLs required")
class MatterAccessPostgres(unittest.TestCase):
    def setUp(self):
        import psycopg
        for url in (APP_URL, ADMIN_URL):
            if not urlparse(url).path.removeprefix("/").startswith("placedon_throwaway_"):
                raise ValueError("Only explicitly named throwaway databases may be used")
        import tempfile
        from gateway.filestore import LocalFileStore
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.files = LocalFileStore(self._dir.name)
        self.tenant = str(uuid.uuid4())
        self.admin, self.a, self.b, self.viewer = (str(uuid.uuid4()) for _ in range(4))
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'matter access test')",
                      (self.tenant,))
            for actor, role in ((self.admin, "admin"), (self.a, "lawyer"),
                                (self.b, "lawyer"), (self.viewer, "lawyer")):
                c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                          "VALUES (%s,%s,'synthetic',%s)", (actor, self.tenant, role))
        with psycopg.connect(APP_URL) as c:
            self.assertFalse(c.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles "
                                       "WHERE rolname = current_user").fetchone()[0],
                             "the tests must run as the restricted application role")
        self.matter = self.call("matters.create", {"name": "Acme " + self.tenant[:8]},
                                self.a)["matter_id"]
        self.call("matters.grant", {"matter_id": self.matter, "actor_id": self.viewer,
                                    "role": "viewer", "reason": "read-only reviewer"}, self.admin)

    # ── helpers ──
    def ctx(self, actor, tenant=None):
        tenant = tenant or self.tenant
        role = "admin" if actor == self.admin else "lawyer"
        return Context(tenant=tenant, actor=actor, role=role,
                       store=PostgresBackend(APP_URL, tenant_id=tenant, actor_id=actor),
                       queue=PostgresQueue(APP_URL, tenant_id=tenant, actor_id=actor),
                       files=self.files, clock=lambda: "2026-10-25T00:00:00Z")

    def call(self, verb, args, actor, tenant=None):
        return V[verb].run(args, self.ctx(actor, tenant))

    def upload(self, actor, name, matter=None):
        store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=actor)
        did = str(uuid.uuid4())
        store.write_vault_document({"document_id": did, "matter_id": matter,
                                    "sha256": uuid.uuid4().hex * 2, "name": name,
                                    "byte_count": 4, "state": "INGESTED"})
        store.write_vault_chunks(did, [f"chunk of {name} about indemnity"])
        return did

    def sql_count(self, sql, actor="", scope=""):
        import psycopg
        from gateway.pool import set_identity
        with psycopg.connect(APP_URL, autocommit=True) as c:
            set_identity(c, self.tenant, actor, scope)
            return c.execute(sql).fetchone()[0]

    # ── same firm, with and without access ──
    def test_same_firm_lawyer_without_grant_sees_identical_not_found(self):
        missing = self.call("vault.list", {"matter_id": str(uuid.uuid4())}, self.b)
        hidden = self.call("vault.list", {"matter_id": self.matter}, self.b)
        self.assertEqual(hidden, missing)
        self.assertEqual(hidden["code"], "NOT_FOUND")
        self.assertEqual(self.call("conversation.list", {"matter_id": self.matter}, self.b),
                         self.call("conversation.list", {"matter_id": str(uuid.uuid4())}, self.b))
        self.assertEqual(self.call("matters.list", {}, self.b)["matters"], [])

    def test_filed_document_is_member_only_in_verbs_search_and_sql(self):
        did = self.upload(self.a, "acme-spa.pdf", self.matter)
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.a)["name"], "acme-spa.pdf")
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.b)["code"], "NOT_FOUND")
        self.assertEqual(len(self.call("vault.find", {"query": "indemnity"}, self.a)["hits"]), 1)
        self.assertEqual(self.call("vault.find", {"query": "indemnity"}, self.b)["hits"], [])
        # The database itself, not only the verbs.
        self.assertEqual(self.sql_count("SELECT count(*) FROM vault_chunks", self.a), 1)
        self.assertEqual(self.sql_count("SELECT count(*) FROM vault_chunks", self.b), 0)
        self.assertEqual(self.sql_count("SELECT count(*) FROM vault_chunks"), 0,
                         "a connection with NO actor sees nothing: the policy fails closed")

    def test_lawyer_without_grant_cannot_write_into_the_matter(self):
        sent = self.call("conversation.send", {"text": "What is the quorum for a board meeting?",
                                               "matter_id": self.matter}, self.b)
        self.assertEqual(sent["code"], "NOT_FOUND")
        self.assertEqual(self.call("vault.upload", {"name": "x.txt", "text": "x",
                                                    "matter_id": self.matter}, self.b)["code"],
                         "NOT_FOUND")

    # ── viewers ──
    def test_matter_viewer_reads_but_cannot_write(self):
        did = self.upload(self.a, "acme-minutes.pdf", self.matter)
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.viewer)["name"],
                         "acme-minutes.pdf")
        self.assertEqual(self.call("conversation.send", {"text": "Draft a notice.",
                                                         "matter_id": self.matter},
                                   self.viewer)["code"], "FORBIDDEN")
        self.assertEqual(self.call("vault.delete", {"document_id": did}, self.viewer)["code"],
                         "FORBIDDEN")
        # And by policy: an UPDATE as the viewer touches nothing.
        import psycopg
        from gateway.pool import set_identity
        with psycopg.connect(APP_URL, autocommit=True) as c:
            set_identity(c, self.tenant, self.viewer)
            self.assertEqual(c.execute("UPDATE vault_documents SET name='x' WHERE document_id=%s",
                                       (did,)).rowcount, 0)

    def test_tenant_viewer_role_is_refused_writes_over_http(self):
        from fastapi.testclient import TestClient
        from gateway.app import create_app
        from gateway.auth import KeyStore
        keys = KeyStore()
        key, _ = keys.mint(tenant_id=self.tenant, actor=self.viewer, role="viewer")
        with TestClient(create_app(db_url=APP_URL, keys=keys)) as client:
            r = client.post("/v2/conversation/send", headers={"Authorization": "Bearer " + key},
                            json={"text": "hello", "matter_id": self.matter})
        self.assertEqual(r.status_code, 403)

    # ── cross tenant ──
    def test_other_tenant_sees_nothing_and_gets_the_same_not_found(self):
        import psycopg
        other_tenant, other = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s, 'other')", (other_tenant,))
            c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) VALUES "
                      "(%s,%s,'x','admin')", (other, other_tenant))
        did = self.upload(self.a, "acme.pdf", self.matter)
        ctx = Context(tenant=other_tenant, actor=other, role="admin",
                      store=PostgresBackend(APP_URL, tenant_id=other_tenant, actor_id=other))
        self.assertEqual(V["matters.list"].run({}, ctx)["matters"], [])
        self.assertEqual(V["vault.status"].run({"document_id": did}, ctx)["code"], "NOT_FOUND")
        self.assertEqual(V["matters.grant"].run({"matter_id": self.matter, "actor_id": other,
                                                 "role": "owner", "reason": "cross-tenant try"},
                                                ctx)["code"], "NOT_FOUND")

    # ── unfiled documents ──
    def test_unfiled_document_is_uploader_private_until_shared(self):
        did = self.upload(self.a, "a-private.docx")
        for actor in (self.b, self.admin):
            self.assertEqual(self.call("vault.status", {"document_id": did}, actor)["code"],
                             "NOT_FOUND")
        self.assertEqual(self.call("vault.list", {}, self.b)["documents"], [])
        shared = self.call("vault.share", {"document_id": did, "reason": "firm precedent"}, self.a)
        self.assertEqual(shared["status"], "SHARED")
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.b)["name"],
                         "a-private.docx")
        self.assertEqual(self.call("vault.delete", {"document_id": did}, self.b)["code"],
                         "FORBIDDEN")
        self.assertEqual(self.call("vault.share", {"document_id": did, "reason": "trying to share a colleague file"},
                                   self.b)["code"], "FORBIDDEN")
        self.assertEqual(self.sql_count("SELECT count(*) FROM access_events", self.admin), 1)
        self.assertEqual(self.sql_count("SELECT count(*) FROM access_events", self.b), 0,
                         "who shared what is visible to admins and the sharer, not the firm")

    def test_same_bytes_uploaded_by_two_lawyers_are_two_private_documents(self):
        verb_args = {"name": "same.txt", "text": "identical synthetic bytes"}
        import tempfile
        from gateway.filestore import LocalFileStore
        with tempfile.TemporaryDirectory() as d:
            files = LocalFileStore(d)
            first = V["vault.upload"].run(verb_args, replace(self.ctx(self.a), files=files))
            second = V["vault.upload"].run(verb_args, replace(self.ctx(self.b), files=files))
        self.assertNotEqual(first["document_id"], second["document_id"])
        self.assertFalse(second.get("duplicate"), "B learns nothing about A's identical file")

    # ── revoked memberships ──
    def test_revoked_member_loses_access_immediately_and_history_is_kept(self):
        did = self.upload(self.a, "acme.pdf", self.matter)
        self.call("matters.grant", {"matter_id": self.matter, "actor_id": self.b,
                                    "role": "member", "reason": "joined the deal team"}, self.admin)
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.b)["name"], "acme.pdf")
        out = self.call("matters.revoke", {"matter_id": self.matter, "actor_id": self.b,
                                           "reason": "left the deal team"}, self.admin)
        self.assertEqual(out["status"], "REVOKED")
        self.assertEqual(self.call("vault.status", {"document_id": did}, self.b)["code"], "NOT_FOUND")
        history = self.call("matters.members", {"matter_id": self.matter, "include_revoked": True},
                            self.admin)["memberships"]
        revoked = [m for m in history if m["actor_id"] == self.b]
        self.assertEqual(len(revoked), 1)
        self.assertEqual(revoked[0]["revoke_reason"], "left the deal team")
        with self.assertRaises(Exception):  # append-only: a grant row cannot be deleted
            import psycopg
            with psycopg.connect(ADMIN_URL, autocommit=True) as c:
                c.execute("DELETE FROM matter_memberships WHERE actor_id=%s", (self.b,))

    def test_only_an_admin_can_grant_even_bypassing_the_verbs(self):
        with self.assertRaises(Exception):
            PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.b).grant_matter_access(
                matter_id=self.matter, actor_id=self.b, role="owner", granted_by=self.b,
                reason="self promotion")
        self.assertEqual(self.call("matters.grant", {"matter_id": self.matter, "actor_id": self.b,
                                                     "role": "owner", "reason": "self promotion"},
                                   self.a)["code"], "FORBIDDEN")

    # ── queued jobs after revocation ──
    def _queued_job(self, actor):
        store = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=actor)
        queue = PostgresQueue(APP_URL, tenant_id=self.tenant, actor_id=actor)
        run_id = str(uuid.uuid4())
        store.write_run({"id": run_id, "intent": "research_question", "status": "PLANNED",
                         "actor_id": actor, "matter_id": self.matter})
        queue.enqueue(run_id=run_id, intent="research_question", args={"matter_id": self.matter})
        return run_id

    def _bind(self, handler):
        def bind(job):
            return (PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=job.actor_id),
                    {"research_question": handler})
        return bind

    def test_job_queued_before_revocation_never_runs(self):
        self.call("matters.grant", {"matter_id": self.matter, "actor_id": self.b,
                                    "role": "member", "reason": "temporary help"}, self.admin)
        run_id = self._queued_job(self.b)
        self.call("matters.revoke", {"matter_id": self.matter, "actor_id": self.b,
                                     "reason": "help no longer needed"}, self.admin)
        called = []
        worker_q = PostgresQueue(APP_URL, tenant_id=self.tenant)
        outcome = run_one(queue=worker_q, store=PostgresBackend(APP_URL, tenant_id=self.tenant),
                          handlers={}, bind_job=self._bind(lambda a: called.append(a)))
        self.assertEqual((outcome.status, outcome.error), ("FAILED", ACCESS_REVOKED))
        self.assertEqual(called, [])
        self.assertEqual(worker_q.get(run_id).status, "DEAD")
        run = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.a).read_run(run_id)
        self.assertEqual(run["status"], "FAILED")
        self.assertNotIn("answer", str(run["result"]))

    def test_revocation_while_running_blocks_publication(self):
        self.call("matters.grant", {"matter_id": self.matter, "actor_id": self.b,
                                    "role": "member", "reason": "temporary help"}, self.admin)
        run_id = self._queued_job(self.b)

        def handler(args):
            # The grant is revoked while the handler is working.
            self.call("matters.revoke", {"matter_id": self.matter, "actor_id": self.b,
                                         "reason": "revoked mid-flight"}, self.admin)
            return [], {"status": "ANSWERED", "answer": "confidential conclusion"}
        worker_q = PostgresQueue(APP_URL, tenant_id=self.tenant)
        outcome = run_one(queue=worker_q, store=PostgresBackend(APP_URL, tenant_id=self.tenant),
                          handlers={}, bind_job=self._bind(handler))
        self.assertEqual(outcome.error, ACCESS_REVOKED)
        run = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.a).read_run(run_id)
        self.assertEqual(run["status"], "FAILED")
        self.assertNotIn("confidential conclusion", str(run))

    # ── the three scopes reach only what they name ──
    def test_queue_scope_reaches_runs_only_never_contents(self):
        self.upload(self.a, "acme.pdf", self.matter)
        sent = self.call("conversation.send", {"text": "What is the quorum for a board meeting?",
                                               "matter_id": self.matter,
                                               "task_override": "COMPANY_STANDING"}, self.a)
        self.assertIn("conversation_id", sent)
        self._queued_job(self.a)
        for table in ("conversations", "messages", "vault_documents", "vault_chunks",
                      "drafts", "review_grids", "matters", "matter_memberships"):
            self.assertEqual(self.sql_count(f"SELECT count(*) FROM {table}", scope="queue"), 0,
                             f"the queue scope reads nothing from {table}")
        self.assertEqual(self.sql_count("SELECT count(*) FROM runs", scope="queue"), 0,
                         "...nor a run that is not stuck behind a DEAD job")

    def test_reassign_scope_reaches_unfiled_metadata_never_contents_or_filed_rows(self):
        self.upload(self.a, "filed.pdf", self.matter)
        self.upload(self.a, "unfiled.pdf")
        import psycopg
        orphan = str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:   # as pre-028 code left it
            c.execute("INSERT INTO vault_documents (document_id, tenant_id, sha256, name, "
                      "byte_count, state) VALUES (%s,%s,%s,'orphan.pdf',1,'INGESTED')",
                      (orphan, self.tenant, uuid.uuid4().hex * 2))
            c.execute("INSERT INTO vault_chunks (document_id, tenant_id, ordinal, text) "
                      "VALUES (%s,%s,0,'orphan text')", (orphan, self.tenant))
        self.assertEqual(self.sql_count("SELECT count(*) FROM vault_documents", scope="reassign"), 1,
                         "only the ORPHAN document's metadata row: not filed, not A's own")
        self.assertEqual(self.sql_count(
            f"SELECT count(*) FROM vault_documents WHERE document_id = '{orphan}'",
            scope="reassign"), 1)
        for table in ("vault_chunks", "vault_tags", "messages", "draft_versions",
                      "review_grid_cells", "runs", "matters"):
            self.assertEqual(self.sql_count(f"SELECT count(*) FROM {table}", scope="reassign"), 0,
                             f"the reassign scope reads nothing from {table}")

    def test_grant_bootstrap_admits_only_a_self_grant_of_owner(self):
        import psycopg
        from gateway.pool import set_identity
        for actor_id, role in ((self.b, "owner"), (self.a, "member")):
            with self.subTest(actor_id=actor_id, role=role):
                with psycopg.connect(APP_URL, autocommit=True) as c:
                    set_identity(c, self.tenant, self.a, "grant_bootstrap")
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        c.execute("INSERT INTO matter_memberships (membership_id, tenant_id, "
                                  "matter_id, actor_id, role, granted_by, grant_reason) "
                                  "VALUES (%s,%s,%s,%s,%s,%s,'bootstrap abuse')",
                                  (str(uuid.uuid4()), self.tenant, self.matter, actor_id, role,
                                   self.a))
        self.assertEqual(self.sql_count("SELECT count(*) FROM vault_chunks",
                                        scope="grant_bootstrap"), 0)

    def test_an_unknown_scope_is_refused_before_any_query(self):
        import psycopg
        from gateway.pool import set_identity
        with psycopg.connect(APP_URL, autocommit=True) as c:
            with self.assertRaises(ValueError):
                set_identity(c, self.tenant, "", "service")

    # ── every child table, populated by ANOTHER actor, under each scope ──
    CHILDREN = ("messages", "run_steps", "propositions", "decisions", "cascade_runs",
                "draft_versions", "review_grid_columns", "review_grid_cells", "vault_chunks",
                "vault_tags", "document_checks")
    PARENTS = ("conversations", "runs", "drafts", "review_grids", "vault_documents")
    OTHER = ("jobs", "answer_cache", "matters", "matter_memberships", "access_events")

    def _seed_work(self, c, owner, matter, tag):
        """A full set of work -- every child table -- as the pre-RLS superuser writes it.
        `owner` None makes an orphan (pre-028 rows), `matter` None leaves it unfiled."""
        import json
        u = lambda: str(uuid.uuid4())                                    # noqa: E731
        rid, conv, draft, grid, doc = u(), u(), u(), u(), u()
        t = self.tenant
        c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, matter_id, "
                  "result) VALUES (%s,%s,%s,'research_question','ANSWERED',%s,%s)",
                  (rid, t, owner or self.a, matter,
                   json.dumps({"answer": f"{tag}: confidential conclusion"})))
        c.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, status) "
                  "VALUES (%s,0,%s,'intake','ANSWERED')", (rid, t))
        c.execute("INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                  "status) VALUES (%s,%s,%s,0,'VERIFIED')", (u(), rid, t))
        c.execute("INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, decision, "
                  "reason, quoted_span, quote_viewed, actor_id) VALUES "
                  "(%s,%s,%s,'ss:1','APPROVED',%s,%s,true,%s)",
                  (u(), rid, t, f"{tag}: reviewed", f"{tag}: quoted span", owner or self.a))
        c.execute("INSERT INTO cascade_runs (cascade_id, run_id, tenant_id, status) "
                  "VALUES (%s,%s,%s,'PARTIAL')", (u(), rid, t))
        c.execute("INSERT INTO jobs (job_id, run_id, tenant_id, actor_id, intent, args) "
                  "VALUES (%s,%s,%s,%s,'research_question',%s)",
                  (u(), rid, t, owner or self.a, json.dumps({"question": f"{tag}: secret"})))
        c.execute("INSERT INTO conversations (conversation_id, tenant_id, actor_id, title, "
                  "matter_id) VALUES (%s,%s,%s,%s,%s)", (conv, t, owner, f"{tag}: chat", matter))
        c.execute("INSERT INTO messages (message_id, conversation_id, tenant_id, ordinal, "
                  "role, text, run_id) VALUES (%s,%s,%s,0,'user',%s,%s)",
                  (u(), conv, t, f"{tag}: are we late filing MGT-7?", rid))
        c.execute("INSERT INTO drafts (draft_id, tenant_id, actor_id, title, run_id, matter_id) "
                  "VALUES (%s,%s,%s,%s,%s,%s)", (draft, t, owner, f"{tag}: memo", rid, matter))
        c.execute("INSERT INTO draft_versions (draft_id, tenant_id, version, title, body) "
                  "VALUES (%s,%s,1,%s,%s)", (draft, t, f"{tag}: memo", f"{tag}: draft body"))
        c.execute("INSERT INTO review_grids (grid_id, tenant_id, actor_id, name, matter_id) "
                  "VALUES (%s,%s,%s,%s,%s)", (grid, t, owner, f"{tag}: diligence", matter))
        c.execute("INSERT INTO review_grid_columns (grid_id, tenant_id, name, kind, question, "
                  "ordinal) VALUES (%s,%s,'cap','amount',%s,0)", (grid, t, f"{tag}: the cap?"))
        c.execute("INSERT INTO review_grid_cells (grid_id, tenant_id, document_id, column_name, "
                  "state, value, quote, provider, cost_inr, cost_note) VALUES "
                  "(%s,%s,%s,'cap','FOUND','INR 5','a quote from the contract','azure',0.01,"
                  "'one call')", (grid, t, uuid.uuid4().hex * 2))
        c.execute("INSERT INTO vault_documents (document_id, tenant_id, matter_id, sha256, "
                  "name, byte_count, state, uploaded_by) VALUES "
                  "(%s,%s,%s,%s,%s,4,'INGESTED',%s)",
                  (doc, t, matter, uuid.uuid4().hex * 2, f"{tag}.pdf", owner))
        c.execute("INSERT INTO vault_chunks (document_id, tenant_id, ordinal, text) "
                  "VALUES (%s,%s,0,%s)", (doc, t, f"{tag}: the term is five years"))
        c.execute("INSERT INTO vault_tags (document_id, tenant_id, tag, quote) "
                  "VALUES (%s,%s,'Term',%s)", (doc, t, f"{tag}: five years"))
        c.execute("INSERT INTO document_checks (check_id, tenant_id, document_id, as_of, "
                  "verification_status, validity_status, action, action_reason) VALUES "
                  "(%s,%s,%s,'2026-10-05','INCOMPLETE_VERIFICATION','CURRENT',"
                  "'KEEP',%s)", (u(), t, doc, f"{tag}: in force, and nothing in it needs renewing"))
        c.execute("INSERT INTO answer_cache (tenant_id, lookup_key, content_key, question, "
                  "task, as_of, citations, payload, actor_id, matter_id) VALUES "
                  "(%s,%s,%s,%s,'RESEARCH_QUESTION','2026-10-01','[{\"id\":\"c\"}]',"
                  "'{}',%s,%s)", (t, uuid.uuid4().hex * 2, uuid.uuid4().hex * 2,
                                  f"{tag}: may Acme buy back its shares?", owner, matter))
        return {"run": rid, "conversation": conv, "draft": draft, "grid": grid, "doc": doc}

    def _populate(self):
        import psycopg
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:
            self.filed = self._seed_work(c, self.a, self.matter, "filed")
            self.unfiled = self._seed_work(c, self.a, None, "unfiled")
            self.orphan = self._seed_work(c, None, None, "orphan")
            # A run still PLANNED whose job is DEAD: the one row the queue may reconcile.
            self.stuck = str(uuid.uuid4())
            c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                      "matter_id) VALUES (%s,%s,%s,'research_question','PLANNED',%s)",
                      (self.stuck, self.tenant, self.a, self.matter))
            c.execute("INSERT INTO jobs (job_id, run_id, tenant_id, actor_id, intent, status, "
                      "dead_reason) VALUES (%s,%s,%s,%s,'research_question','DEAD',"
                      "'attempts exhausted')",
                      (str(uuid.uuid4()), self.stuck, self.tenant, self.a))

    def counts(self, actor="", scope=""):
        return {t: self.sql_count(f"SELECT count(*) FROM {t}", actor, scope)
                for t in self.CHILDREN + self.PARENTS + self.OTHER}

    def test_seed_is_populated_so_every_zero_below_measures_a_policy(self):
        self._populate()
        mine = self.counts(self.a)
        for t in self.CHILDREN + self.PARENTS + ("answer_cache", "matters"):
            self.assertGreater(mine[t], 0, f"A reads its own {t}: the seed is not empty")
        self.assertEqual(mine["jobs"], 0, "not even its own jobs: only the queue reads jobs")

    def test_colleague_and_no_actor_read_nothing_of_anothers_work(self):
        self._populate()
        for actor in (self.b, ""):
            for t, n in self.counts(actor).items():
                with self.subTest(actor=actor or "none", table=t):
                    self.assertEqual(n, 0)

    def test_queue_scope_reads_jobs_and_one_reconcilable_run_and_no_contents(self):
        self._populate()
        for actor in ("", self.b):
            got = self.counts(actor, "queue")
            with self.subTest(actor=actor or "none"):
                self.assertEqual(got.pop("jobs"), 4, "the queue reads every job")
                self.assertEqual(got.pop("runs"), 1, "...and ONLY the stuck run, not a finished one")
                self.assertEqual({t: n for t, n in got.items() if n}, {},
                                 "...and no child table, conversation, document or cache entry")
        import psycopg
        from gateway.pool import set_identity
        with psycopg.connect(APP_URL, autocommit=True) as c:
            set_identity(c, self.tenant, "", "queue")
            self.assertEqual(c.execute("SELECT run_id::text, result FROM runs").fetchall(),
                             [(self.stuck, None)],
                             "a finished run's answer is never in the queue's reach")
            self.assertEqual(c.execute("UPDATE runs SET status='FAILED' WHERE run_id=%s",
                                       (self.filed["run"],)).rowcount, 0)
            self.assertEqual(c.execute("UPDATE runs SET status='FAILED', failure_category="
                                       "'TRANSPORT', failure_reason='dead' WHERE run_id=%s",
                                       (self.stuck,)).rowcount, 1,
                             "...while the stuck run can still be dead-lettered")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                          "status) VALUES (%s,9,%s,'x','ANSWERED')", (self.stuck, self.tenant))

    def test_reassign_scope_reads_orphan_metadata_only(self):
        self._populate()
        for actor in ("", self.admin):
            got = self.counts(actor, "reassign")
            base = self.counts(actor)
            with self.subTest(actor=actor or "none"):
                for t in ("conversations", "drafts", "review_grids", "vault_documents"):
                    self.assertEqual(got[t] - base[t], 1, f"the one ORPHAN {t} row, not A's")
                for t in self.CHILDREN + ("runs", "jobs", "answer_cache"):
                    self.assertEqual(got[t], 0, f"the reassign scope reads nothing from {t}")
        out = self.call("access.reassign", {"kind": "conversation",
                                            "id": self.unfiled["conversation"],
                                            "to_actor": self.admin,
                                            "reason": "take a colleague's private thread"},
                        self.admin)
        self.assertEqual(out["status"], "REFUSED", "an owner's unfiled work is not an admin's")
        self.assertEqual(self.call("conversation.get",
                                   {"conversation_id": self.unfiled["conversation"]},
                                   self.admin)["code"], "NOT_FOUND")

    def test_grant_bootstrap_scope_reads_nothing(self):
        self._populate()
        for t, n in self.counts("", "grant_bootstrap").items():
            with self.subTest(table=t):
                self.assertEqual(n, 0)

    def test_answer_cache_entry_is_reused_only_by_who_could_read_it(self):
        entry = {"lookup_key": uuid.uuid4().hex * 2, "content_key": uuid.uuid4().hex * 2,
                 "question": "May Acme buy back its shares?", "task": "RESEARCH_QUESTION",
                 "as_of": "2026-10-01", "citations": [{"id": "c1"}], "payload": {}}
        a = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.a)
        b = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.b)
        v = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.viewer)
        self.assertTrue(a.write_cache_entry(entry))
        self.assertIsNotNone(a.read_cache_entry(entry["lookup_key"]))
        self.assertIsNone(b.read_cache_entry(entry["lookup_key"]),
                          "a colleague cannot read another actor's unfiled question")
        filed = dict(entry, lookup_key=uuid.uuid4().hex * 2, matter_id=self.matter)
        self.assertTrue(a.write_cache_entry(filed))
        self.assertIsNotNone(v.read_cache_entry(filed["lookup_key"]), "a matter member can")
        self.assertIsNone(b.read_cache_entry(filed["lookup_key"]), "a non-member cannot")

    # ── pooled connections ──
    def test_pooled_connection_never_carries_one_actor_into_the_next(self):
        from gateway.pool import Pool
        did = self.upload(self.a, "acme.pdf", self.matter)
        pool = Pool(APP_URL, max_size=1, name="probe")   # ONE connection, so it IS reused
        try:
            as_a = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.a, pool=pool)
            as_b = PostgresBackend(APP_URL, tenant_id=self.tenant, actor_id=self.b, pool=pool)
            nobody = PostgresBackend(APP_URL, tenant_id=self.tenant, pool=pool)
            for _ in range(3):
                self.assertIsNotNone(as_a.read_vault_document(did))
                self.assertIsNone(as_b.read_vault_document(did))
                self.assertIsNone(nobody.read_vault_document(did))
            with pool.connection(tenant_id=self.tenant) as c:
                row = c.execute("SELECT current_setting('app.actor_id', true), "
                                "current_setting('app.actor_scope', true)").fetchone()
            self.assertEqual(row, ("", ""))
            self.assertEqual(pool.stats()["peak"], 1)
        finally:
            pool.close()

    # ── existing data regains access only through the admin path ──
    def test_legacy_unowned_work_is_listed_and_reassigned_by_an_admin(self):
        import psycopg
        legacy_doc, legacy_draft = str(uuid.uuid4()), str(uuid.uuid4())
        with psycopg.connect(ADMIN_URL, autocommit=True) as c:   # as pre-028 code left it
            c.execute("INSERT INTO vault_documents (document_id, tenant_id, sha256, name, "
                      "byte_count, state) VALUES (%s,%s,%s,'legacy.pdf',1,'INGESTED')",
                      (legacy_doc, self.tenant, uuid.uuid4().hex * 2))
            c.execute("INSERT INTO drafts (draft_id, tenant_id, kind, title) VALUES "
                      "(%s,%s,'research_memo','Legacy memo')", (legacy_draft, self.tenant))
        self.assertEqual(self.call("vault.status", {"document_id": legacy_doc}, self.a)["code"],
                         "NOT_FOUND")
        report = self.call("matters.access_report", {}, self.admin)
        self.assertIn(legacy_doc, [d["id"] for d in report["unowned"]["vault_document"]])
        self.assertIn(legacy_draft, [d["id"] for d in report["unowned"]["draft"]])
        for kind, rid in (("vault_document", legacy_doc), ("draft", legacy_draft)):
            out = self.call("access.reassign", {"kind": kind, "id": rid, "to_actor": self.a,
                                                "reason": "A created this before 028"}, self.admin)
            self.assertEqual(out["status"], "REASSIGNED")
        self.assertEqual(self.call("vault.status", {"document_id": legacy_doc}, self.a)["name"],
                         "legacy.pdf")
        self.assertEqual(self.call("draft.status", {"draft_id": legacy_draft}, self.a)["draft_id"],
                         legacy_draft)
        self.assertEqual(self.call("vault.status", {"document_id": legacy_doc}, self.admin)["code"],
                         "NOT_FOUND", "reassigning to A grants the admin nothing")


if __name__ == "__main__":
    unittest.main()
