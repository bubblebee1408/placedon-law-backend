"""Row-level security, proved against a REAL Postgres. Deliberately outside the gate.

## Why this is not in scripts/run_tests.sh

The gate must run offline, on a laptop, in minutes. This needs a live Postgres, a superuser
to apply migrations and a second role to connect as. A suite that needs a server either
gets skipped -- and a skipped security test reads as a passing one, which is worse than no
test -- or it makes the whole gate conditional on infrastructure. So it stays out, and
`gateway/schema.py` performs the STATIC half inside the gate: every tenant-scoped table
declares ENABLE and FORCE row level security and a policy. Static checks catch a migration
that forgot the discipline. Only this file catches a server where the discipline does not
hold.

## STATUS: RUN — 2026-09-29, PostgreSQL 18.6, 59 checks, 0 failures

    LAST_RUN = None

Both migrations are applied and every property below is proved on a real server. The gate
still has never seen a tenant -- it runs on the in-memory backend and cannot assert
anything about a database -- so this file remains the only evidence of isolation, and it
has to be re-run after any migration change.

## The role it connects as, which is the whole experiment

**Isolation is verified as a NON-SUPERUSER role**, created here if absent, and that is not a
detail. PostgreSQL superusers and roles with BYPASSRLS bypass row-level security
unconditionally; `FORCE ROW LEVEL SECURITY` extends the policy to the table OWNER, and to
nobody beyond that. Measured 29-09-2026: connected as the (superuser) macOS account, tenant
A saw every row and dropping the policy changed nothing -- the run "failed" while proving
only that a superuser is a superuser.

So there are two connections. The ADMIN one applies the migrations, creates the role and
seeds the rows. The APP one -- `placedon_app`, no superuser, no BYPASSRLS -- is the only one
whose visibility is ever asserted. A deployment that connects as a superuser has no tenant
isolation whatever this file says, and the run prints the roles it used for that reason.

## What it proves, and the one that matters

    1. tenant A cannot SELECT tenant B's rows                    isolation
    2. ...including as the table OWNER                           FORCE, not merely ENABLE
    3. dropping the policy makes the leak APPEAR                 the test can fail
    4. audit_log refuses UPDATE and DELETE                       append-only

(3) is the important one. A test that only ever asserts "no rows leaked" passes just as
happily against a table with no policy at all, an empty database, or a typo in the tenant
id. So this drops `tenant_isolation`, asserts the other tenant's rows become visible,
and restores it. If that middle step does NOT leak, the test FAILS -- because then it was
never measuring the policy.

Run:  createdb placedon_throwaway_now
      PLACEDON_DATABASE_URL=postgresql:///placedon_throwaway_now PYTHONPATH=. \\
          python3 scripts/rls_integration.py --run
      dropdb placedon_throwaway_now

      The name is not decoration: --run only touches a database whose name starts
      with `placedon_throwaway_`, and it reads PLACEDON_DATABASE_URL and nothing
      else. See THROWAWAY_PREFIX for why.

      `--test` exercises those two guards and needs no server. It is deliberately
      NOT in scripts/run_tests.sh, and `gateway/schema.py` has a check that keeps
      it out: a green "scripts/rls_integration.py" line in the gate would read as
      the ISOLATION PROOF having passed, when all that ran was the guard. That is
      the same failure the invariant already names -- a skipped security test
      reading as a passing one -- wearing a different hat. Run it by hand:

          PYTHONPATH=. python3 scripts/rls_integration.py --test
      PYTHONPATH=. python3 scripts/rls_integration.py            # prints this status

`PLACEDON_DATABASE_URL` is the variable, the same one gateway/store.py selects on: two
names for one connection is how a script proves isolation on a database the application
never uses.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MIGRATIONS = ROOT / "gateway" / "migrations"

# Set this to an ISO date and a server description the day it is actually run.
LAST_RUN: str | None = (
    "2026-09-30 — PostgreSQL 18.6 (Postgres.app), local socket, database placedon_dev, "
    "asserted as role placedon_app (NOSUPERUSER, NOBYPASSRLS). 121 checks, 0 failures, "
    "migrations 001-007 applied. `cascade_runs` is the TENTH tenant-scoped table: it holds "
    "which bodies another firm's question touched and the reason a model's output was "
    "rejected, and it is proved the same way as the other nine -- A sees its own row and "
    "none of B's; with the policy dropped it fails CLOSED and A sees nothing, not even its "
    "own; with RLS disabled B's row APPEARS, which is what shows the check measures the "
    "protection rather than an empty table. "
    "008_decision_evidence (quote_viewed, law_versions; numbered 006 on t0/finish) was "
    "proved SEPARATELY on a fresh database placedon_t0_rls on top of 001-005: 77 checks, "
    "0 failures. "
    "2026-09-30, at the merge of PR #22: 001-008 applied TOGETHER to a fresh throwaway "
    "database on PostgreSQL 16.13 (Ubuntu, cloud container, local socket), asserted as "
    "placedon_app: 127 checks, 0 failures, including the database refusing an approval "
    "whose quote was not viewed. "
    "2026-10-01: 001-009 applied TOGETHER to a fresh throwaway database on PostgreSQL "
    "18.6 (Postgres.app, local socket), asserted as placedon_app (NOSUPERUSER, "
    "NOBYPASSRLS): 137 checks, 0 failures, adding 009_source_documents. That table "
    "INVERTS every other check in this file -- it is not row-level-security bound and "
    "both tenants see the SAME public row, because one SEBI circular is one row shared on "
    "purpose. What keeps a client contract out of it is a CHECK the database enforces, "
    "proved by seven refused inserts: tier CLIENT, tier HELD, an unknown tier, a "
    "terms_basis too short to be a quoted permission, a LICENSED row with no attribution, "
    "a fetch dated in the future, and a plain-http url. A CHECK can only be SHOWN to "
    "refuse on a live server, which is why those are here and not in gateway/schema.py. "
    "placedon_dev still cannot take 008: it holds 64 APPROVED seed rows from earlier runs "
    "of this script, written before quote_viewed existed, and 008's VALIDATE refuses them "
    "by design -- \"the pre-existing approvals must be looked at by a person, not "
    "defaulted\". They are this script's own synthetic seeds, so a fresh database is the "
    "answer and not a change to 008. "
    "2026-10-01, C2: 001-010 applied TOGETHER to a fresh throwaway database on PostgreSQL "
    "18.6 (Postgres.app, local socket), asserted as placedon_app (NOSUPERUSER, "
    "NOBYPASSRLS): 145 checks, 0 failures, adding 010_conversations. `conversations` and "
    "`messages` are the ELEVENTH and TWELFTH tenant-scoped tables and they are the most "
    "obviously private things in the schema -- a lawyer's questions in their own words, "
    "and the envelope we answered with, citations included. Both are proved the way the "
    "other ten are: A sees its own and none of B's; with the policy dropped they fail "
    "CLOSED and A sees nothing, not even its own; with RLS disabled B's rows APPEAR (1 "
    "conversation, 2 messages), which is what shows the check measures the protection "
    "rather than an empty table; restoring returns to isolation. The store's chat methods also run through gateway/store.conformance() HERE, against Postgres, and that is what caught a real divergence: the dict raised StoreError on a duplicate ordinal while Postgres raised psycopg UniqueViolation, so one `except StoreError` handled the memory backend and crashed on the real one. PostgresBackend now translates IntegrityError into StoreError. Re-run after the fix: 165 checks, 0 failures. "
    "2026-10-01, H4: 001-011 applied TOGETHER to a fresh throwaway database on PostgreSQL "
    "18.6 (Postgres.app, local socket), asserted as placedon_app (NOSUPERUSER, "
    "NOBYPASSRLS), adding 011_review_grids. review_grids, review_grid_columns and "
    "review_grid_cells are the THIRTEENTH to FIFTEENTH tenant-scoped tables and they hold "
    "the most concentrated client data in the schema: another firm's contracts, the "
    "questions their lawyer thought worth asking, and a quote from each. All three are "
    "proved the way the other twelve are -- A sees its own and none of B's; the policy "
    "dropped fails CLOSED; RLS disabled LEAKS, which is what shows the check measures the "
    "protection; restoring returns to isolation. "
    "2026-10-01, H3: 001-012 applied TOGETHER to a fresh throwaway database on PostgreSQL "
    "18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding 012_drafts. "
    "`drafts` and `draft_versions` are the SIXTEENTH and SEVENTEENTH tenant-scoped tables: "
    "a draft version holds what another company was about to FILE and the name of the "
    "person who signed it off. Both are proved the way the others are, and the database "
    "additionally REFUSES a version recorded as approved while blocking_count > 0, which "
    "is the row that matters most. "
    "2026-10-01, job 3b: 001-013 applied TOGETHER to a fresh throwaway database on "
    "PostgreSQL 18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding "
    "013_grid_cell_cost: 229 checks, 0 failures. No new table -- three columns on "
    "review_grid_cells -- so the isolation proof is unchanged; what 013 adds is refused "
    "rows. review_grid_cells_ran_has_cost_note refused THIS SCRIPT'S OWN SEED on the first "
    "run, because the seed inserted a FOUND cell with neither a cost nor a note saying "
    "there is none. That is the constraint catching its own omission on a real server, and "
    "the seed now carries a debit. "
    "2026-10-01, O9: 001-014 applied TOGETHER to a fresh throwaway database on "
    "PostgreSQL 18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding "
    "014_answer_cache: 248 checks, 0 failures. `answer_cache` and `answer_cache_stats` "
    "are the EIGHTEENTH and NINETEENTH tenant-scoped tables. A cached answer holds the "
    "question a lawyer asked in their own words and the citations we gave them, which is "
    "why 014 scopes every row to a tenant and does NOT share even a purely statutory "
    "answer -- PLAN_23 would permit that, and the cost of being wrong once about which "
    "bucket an answer is in is one firm seeing another's document. The conformance list "
    "also caught its own fault here: its cache checks asserted statistics START AT ZERO, "
    "which held on an empty dict and failed on a live database this script had already "
    "seeded. They now measure DELTAS -- a conformance check that only holds on an empty "
    "table is not a conformance check. "
    "2026-10-02, O8: 001-015 applied TOGETHER to a fresh throwaway database on "
    "PostgreSQL 18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding "
    "015_failure_category: 254 checks, 0 failures. No new table -- two columns on runs -- "
    "so the isolation proof is unchanged. The conformance list caught a real divergence "
    "again: set_run wrote failure_category on Postgres and read_run did not SELECT it, so "
    "the value was stored and invisible to every reader. Green on the dict, wrong on the "
    "backend that ships. "
    "2026-10-02, job 8: 001-016 applied TOGETHER to a fresh throwaway database on "
    "PostgreSQL 18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding "
    "015_failure_category and 016_critic_enabled: 255 checks, 0 failures. Neither adds a "
    "table, so the isolation proof is unchanged. "
    "2026-10-02, CAL-1 score: 001-017 applied TOGETHER to a fresh throwaway database "
    "on PostgreSQL 18.6, asserted as placedon_app (NOSUPERUSER, NOBYPASSRLS), adding "
    "017_nonconformity: 258 checks, 0 failures. The conformance list caught one more "
    "divergence, this time in ITSELF: it wrote a run with status REFUSED and no "
    "refusal_code, which 002's runs_refusal_code_iff_refused forbids. The dict "
    "accepted it and Postgres refused it, so a row that could never exist in "
    "production passed the gate. MemoryBackend.write_run now restates that CHECK.")

TENANT_TABLES = ("actors", "api_keys", "documents", "audit_log",
                 "runs", "run_steps", "propositions", "decisions", "jobs",
                 "cascade_runs",
                 # C2's chat layer. Listed here rather than checked separately, because
                 # this tuple drives the whole proof below -- A sees its own rows and none
                 # of B's, the policy dropped fails CLOSED, RLS disabled LEAKS, restoring
                 # returns to isolation. A conversation is the most obviously private
                 # thing in the schema: it is a lawyer's questions in their own words.
                 "conversations", "messages",
                 # H4's review grids. A diligence grid is forty of another firm's
                 # contracts, the questions their lawyer thought worth asking, and a quote
                 # from each -- the most concentrated client data in the schema.
                 "review_grids", "review_grid_columns", "review_grid_cells",
                 # H3's drafts. A draft version holds what a company was about to FILE,
                 # and who stood behind it.
                 "drafts", "draft_versions",
                 # O9: the answer cache. A cached answer carries the question a lawyer
                 # asked and the citations we gave them, so it is proved like the rest.
                 "answer_cache", "answer_cache_stats",
                 # 8a: invites. The leak would be another firm's staff email addresses and
                 # which of them was being made an admin.
                 "invites")


class RlsFailure(AssertionError):
    """The database does not isolate tenants. Not a test bug until proved otherwise."""


def status() -> str:
    if LAST_RUN is None:
        return ("UNRUN — no Postgres has run this file. The isolation in "
                "gateway/migrations/*.sql is a property of SQL text and not yet of any "
                "database. gateway/app.py reports store.kind='in-memory' accordingly.")
    return f"LAST RUN: {LAST_RUN}"


def sql(name: str) -> str:
    return (MIGRATIONS / name).read_text(encoding="utf-8")


def _connect(url: str):
    import psycopg
    return psycopg.connect(url, autocommit=True)


APP_ROLE = "placedon_app"


ADMIN_URL_ENV = "PLACEDON_ADMIN_DATABASE_URL"


def _admin_url(url: str) -> str:
    """The connection that may CREATE TABLE. Not the application's.

    PLACEDON_DATABASE_URL names the application role, and that role deliberately cannot
    create tables -- which is correct, and means this script cannot use it to apply
    migrations. PLACEDON_ADMIN_DATABASE_URL names the owner; absent, it is derived by
    swapping the user back to the OS account, which is how Postgres.app is set up.
    """
    import getpass
    import os as _os
    import re as _re
    explicit = _os.getenv(ADMIN_URL_ENV)
    if explicit:
        return explicit
    return _re.sub(r"user=[^&]+", f"user={getpass.getuser()}", url)


def _app_url(admin_url: str) -> str:
    """The same database, connected as the non-superuser role."""
    import re as _re
    if "user=" in admin_url:
        return _re.sub(r"user=[^&]+", f"user={APP_ROLE}", admin_url)
    sep = "&" if "?" in admin_url else "?"
    return f"{admin_url}{sep}user={APP_ROLE}"


def _ensure_app_role(cur) -> None:
    """A login role with no superuser and no BYPASSRLS. Created idempotently."""
    if not cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (APP_ROLE,)).fetchone():
        cur.execute(f"CREATE ROLE {APP_ROLE} LOGIN")
    cur.execute(f"ALTER ROLE {APP_ROLE} NOSUPERUSER NOBYPASSRLS")
    cur.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f"TO {APP_ROLE}")
    cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")


import json as _json


def _seed(cur, tenant, actor, tag: str) -> None:
    """One row per tenant-scoped table, for this tenant. Enough to be leaked."""
    import uuid
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant),))
    cur.execute("INSERT INTO actors (actor_id, tenant_id, label) VALUES (%s,%s,%s)",
                (actor, tenant, tag))
    cur.execute("INSERT INTO api_keys (key_hash, key_id, tenant_id, actor_id, label) "
                "VALUES (%s,%s,%s,%s,%s)",
                (uuid.uuid4().hex + uuid.uuid4().hex, tag[:8], tenant, actor, tag))
    cur.execute("INSERT INTO documents (sha256, tenant_id, name, byte_count) "
                "VALUES (%s,%s,%s,%s)",
                (uuid.uuid4().hex + uuid.uuid4().hex, tenant, f"{tag}.txt", 10))
    cur.execute(
        "INSERT INTO audit_log (tenant_id, request_id, actor_id, ts, action, route, "
        "resource, outcome, http_status, prev_digest, digest) VALUES "
        "(%s,%s,%s,now(),'READ','GET /v1/health','/v1/health','served',200,%s,%s)",
        (tenant, uuid.uuid4(), actor, "0" * 64, uuid.uuid4().hex + uuid.uuid4().hex))
    rid = uuid.uuid4()
    cur.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status) "
                "VALUES (%s,%s,%s,'review_contract','ANSWERED')", (rid, tenant, actor))
    cur.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, status) "
                "VALUES (%s,0,%s,'intake','ANSWERED')", (rid, tenant))
    cur.execute("INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                "status) VALUES (%s,%s,%s,0,'VERIFIED')", (uuid.uuid4(), rid, tenant))
    # A human decision. This is the row whose leak would matter most: it carries a named
    # reviewer's words about another firm's document.
    cur.execute("INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, decision, "
                "reason, quoted_span, quote_viewed, actor_id) "
                "VALUES (%s,%s,%s,%s,'APPROVED',%s,%s,true,%s)",
                (uuid.uuid4(), rid, tenant, "ss:T1.2",
                 f"{tag}: inspected the book, every page initialled.",
                 f"{tag} physical minutes book not inspected", actor))
    # A conversation and its two messages. The leak that would matter most to a CLIENT:
    # not a finding about their document but the question they asked in their own words,
    # and the answer we gave. The envelope is stored, so a leak would carry the citations
    # too.
    conv = uuid.uuid4()
    cur.execute("INSERT INTO conversations (conversation_id, tenant_id, actor_id, title) "
                "VALUES (%s,%s,%s,%s)", (conv, tenant, actor, f"{tag}: board meeting"))
    cur.execute("INSERT INTO messages (message_id, conversation_id, tenant_id, ordinal, "
                "role, text, file_ids) VALUES (%s,%s,%s,0,'user',%s,%s)",
                (uuid.uuid4(), conv, tenant,
                 f"{tag}: are we late filing MGT-7 for FY24?", json.dumps([])))
    cur.execute("INSERT INTO messages (message_id, conversation_id, tenant_id, ordinal, "
                "role, text, task, envelope) VALUES (%s,%s,%s,1,'assistant',%s,%s,%s)",
                (uuid.uuid4(), conv, tenant, f"{tag}: answer",
                 "RESEARCH_QUESTION",
                 json.dumps({"schema": "answer_envelope.v1", "status": "PARTIAL",
                             "task": "RESEARCH_QUESTION", "tenant_marker": tag})))

    # A review grid, its column and one answered cell. The cell carries a QUOTE from
    # another firm's contract, which is the leak a client would care about most.
    grid = uuid.uuid4()
    cur.execute("INSERT INTO review_grids (grid_id, tenant_id, actor_id, name) "
                "VALUES (%s,%s,%s,%s)", (grid, tenant, actor, f"{tag}: NDA diligence"))
    cur.execute("INSERT INTO review_grid_columns (grid_id, tenant_id, name, kind, "
                "question, ordinal) VALUES (%s,%s,'liability cap','amount',%s,0)",
                (grid, tenant, f"{tag}: what is the cap on aggregate liability?"))
    # 013: the cell carries its debit. A FOUND cell with neither a cost nor a note is
    # refused by review_grid_cells_ran_has_cost_note, which this seed proved on its first
    # run against a real server.
    cur.execute("INSERT INTO review_grid_cells (grid_id, tenant_id, document_id, "
                "column_name, state, value, quote, provider, cost_inr, cost_note) "
                "VALUES (%s,%s,%s,'liability cap','FOUND',%s,%s,'azure',%s,%s)",
                (grid, tenant, ("a" if tag.startswith("A") else "b") * 64,
                 "INR 50,00,000",
                 f"{tag}: aggregate liability shall not exceed INR 50,00,000",
                 0.0412, f"{tag}: one extraction call, priced from reported tokens"))

    # 8a: an invite. The leak would be another firm's staff email addresses and which of
    # them was being made an admin.
    cur.execute("INSERT INTO invites (invite_id, tenant_id, email, role, token_hash, "
                "invited_by, expires_at) VALUES (%s,%s,%s,'lawyer',%s,%s,"
                "now() + interval '7 days')",
                (uuid.uuid4(), tenant, f"{tag}-joiner@example.com",
                 ("a" if tag.startswith("A") else "b") * 64, actor))

    # O9: a cached answer. The leak would carry the QUESTION another firm's lawyer asked
    # and the answer we gave them -- the same kind of private thing `conversations` holds,
    # which is why 014 scopes every row to a tenant rather than sharing statutory answers.
    cur.execute("INSERT INTO answer_cache (tenant_id, lookup_key, content_key, question, "
                "task, as_of, sources, citations, payload) "
                "VALUES (%s,%s,%s,%s,'RESEARCH_QUESTION','2026-10-01','[]'::jsonb,"
                "%s::jsonb,%s::jsonb)",
                (tenant, ("a" if tag.startswith("A") else "b") * 64,
                 ("c" if tag.startswith("A") else "d") * 64,
                 f"{tag}: when must the board meet?",
                 _json.dumps([{"id": "c1", "provision": "s.173", "sha256": "e" * 64,
                               "quote": f"{tag}: four meetings every year"}]),
                 _json.dumps({"status": "ANSWERED"})))
    cur.execute("INSERT INTO answer_cache_stats (tenant_id, day, hits, misses, stale) "
                "VALUES (%s, DATE '2026-10-01', 3, 1, 1)", (tenant,))

    # A draft and two versions: one blocked, one approved. The leak would carry what
    # another company was about to file and the name of the person who signed it off.
    draft = uuid.uuid4()
    cur.execute("INSERT INTO drafts (draft_id, tenant_id, actor_id, kind, title) "
                "VALUES (%s,%s,%s,'agm_notice',%s)",
                (draft, tenant, actor, f"{tag}: notice of annual general meeting"))
    cur.execute("INSERT INTO draft_versions (draft_id, tenant_id, version, title, body, "
                "slots, blocking_count) VALUES (%s,%s,1,%s,%s,%s,1)",
                (draft, tenant, f"{tag}: AGM notice",
                 f"{tag}: Notice is hereby given.",
                 json.dumps([{"name": "venue", "type": "MODEL_SUGGESTION"}])))
    cur.execute("INSERT INTO draft_versions (draft_id, tenant_id, version, title, body, "
                "slots, blocking_count, approved_by, approved_at) "
                "VALUES (%s,%s,2,%s,%s,%s,0,%s,now())",
                (draft, tenant, f"{tag}: AGM notice",
                 f"{tag}: Notice is hereby given to the members.",
                 json.dumps([{"name": "venue", "type": "USER_FACT"}]),
                 f"{tag} reviewer"))

    # A queued job. This is the row whose leak would be worst OPERATIONALLY: a worker that
    # could see another tenant's job would execute another firm's document.
    cur.execute("INSERT INTO jobs (job_id, run_id, tenant_id, actor_id, intent, args) "
                "VALUES (%s,%s,%s,%s,'review_document',%s)",
                (uuid.uuid4(), rid, tenant, actor, json.dumps({"tag": tag})))
    # A cascade record. It carries which bodies another firm's question touched and the
    # reason a model's output was rejected -- one more row that must not cross.
    cur.execute("INSERT INTO cascade_runs (cascade_id, run_id, tenant_id, status, "
                "attempts, body_ids, total_cost_inr) "
                "VALUES (%s,%s,%s,'PARTIAL',%s::jsonb,%s,%s)",
                (uuid.uuid4(), rid, tenant,
                 json.dumps([{"stage": "small_model", "outcome": "REJECTED",
                              "reason": f"{tag}: NO_CITATION"}]),
                 ["CA2013"], 0.02))


class _SeededQueue:
    """The Postgres queue, with run ids that already have a `runs` row.

    `gateway/jobs.conformance` invents run ids, which is right for the dict and impossible
    on Postgres: `jobs.run_id` references `runs`. This hands out pre-created ids instead of
    weakening the foreign key, because the foreign key is what stops a job pointing at a run
    nobody can read.
    """

    def __init__(self, inner, run_ids):
        self._inner = inner
        self._ids = list(run_ids)
        self._map: dict[str, str] = {}

    def _real(self, run_id: str) -> str:
        if run_id not in self._map:
            self._map[run_id] = self._ids.pop(0) if self._ids else run_id
        return self._map[run_id]

    def _fake(self, job):
        """Translate the run id BACK, so the suite compares against the ids it invented.
        Without this the adapter is a one-way mirror and every assertion about which run a
        job belongs to fails for a reason that has nothing to do with the queue."""
        if job is None:
            return None
        import dataclasses
        for fake, real in self._map.items():
            if real == job.run_id:
                return dataclasses.replace(job, run_id=fake)
        return job

    def enqueue(self, *, run_id, intent, args):
        return self._inner.enqueue(run_id=self._real(run_id), intent=intent, args=args)

    def claim(self, **kw):
        return self._fake(self._inner.claim(**kw))

    def finish(self, job_id, status):
        return self._inner.finish(job_id, status)

    def request_cancel(self, run_id):
        return self._inner.request_cancel(self._real(run_id))

    def get(self, run_id):
        return self._fake(self._inner.get(self._real(run_id)))

    def depth(self):
        return self._inner.depth()


def run(url: str) -> int:
    """Apply the migrations as admin, then prove isolation as a NON-SUPERUSER. Exit code."""
    import uuid
    a, b = uuid.uuid4(), uuid.uuid4()
    actor_a, actor_b = uuid.uuid4(), uuid.uuid4()
    failures: list[str] = []

    def note(ok: bool, label: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    app_url = _app_url(url)
    url = _admin_url(url)

    with _connect(url) as admin:
        cur = admin.cursor()
        version = cur.execute("SELECT version()").fetchone()[0]
        who, su = cur.execute(
            "SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)"
        ).fetchone()
        print(f"  server : {version.split(' on ')[0]}")
        print(f"  admin  : {who} (superuser={su}) — applies migrations, seeds rows")
        print(f"  app    : {APP_ROLE} (superuser=False, bypassrls=False) — the only role "
              f"whose visibility is asserted\n")

        for f in ("001_core.sql", "002_runs.sql", "003_step_provenance.sql",
                  "004_cost_note.sql", "005_decisions.sql", "006_jobs.sql",
                  "007_cascade.sql", "008_decision_evidence.sql",
                  "009_source_documents.sql", "010_conversations.sql",
                  "011_review_grids.sql", "012_drafts.sql",
                  "013_grid_cell_cost.sql", "014_answer_cache.sql",
                  "015_failure_category.sql",
                  "016_critic_enabled.sql",
                  "017_nonconformity.sql",
                  "018_users_roles.sql"):
            cur.execute(sql(f))
            print(f"  applied {f}")
        _ensure_app_role(cur)
        print(f"  ensured role {APP_ROLE}\n")

        for t in (a, b):
            cur.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s) "
                        "ON CONFLICT DO NOTHING", (t, f"t-{t}"))
        _seed(cur, a, actor_a, "alpha")
        _seed(cur, b, actor_b, "bravo")

        r = cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=%s",
                        (APP_ROLE,)).fetchone()
        note(r == (False, False),
             f"{APP_ROLE} is NOT a superuser and does NOT have BYPASSRLS {r} -- without "
             f"this, nothing below measures the policy")

    # ── (a) isolation, as the application role, on EVERY tenant-scoped table ──
    print()
    before: dict[str, tuple[int, int]] = {}
    with _connect(app_url) as app:
        c = app.cursor()
        c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
        for tbl in TENANT_TABLES:
            other = c.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s",
                              (b,)).fetchone()[0]
            mine = c.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            before[tbl] = (mine, other)
            note(other == 0 and mine >= 1,
                 f"{tbl}: tenant A sees {mine} row(s), none of tenant B's ({other})")

    with _connect(url) as admin:
        cur = admin.cursor()
        cur.execute("SELECT relname FROM pg_class WHERE relname = ANY(%s) "
                    "AND relforcerowsecurity", (list(TENANT_TABLES),))
        forced = {r[0] for r in cur.fetchall()}
        note(forced == set(TENANT_TABLES),
             f"pg_class says FORCE is set on every tenant table "
             f"(missing {sorted(set(TENANT_TABLES) - forced)})")

    # ── (b) the proof must be able to FAIL, and Postgres has TWO ways ───────
    # Dropping the policy while RLS is still forced does NOT leak: with no policy at all
    # Postgres applies a default-deny, and tenant A stops seeing even its own rows. That
    # is worth asserting -- it fails CLOSED -- but it demonstrates nothing about a leak.
    # Removing row-level security itself is what exposes the data, so both are checked:
    # protection removed one way hides everything, the other way reveals everything, and
    # restoring returns to isolation. A check that only ever asserts "nothing leaked"
    # passes just as happily against an empty table.
    print()
    for tbl in TENANT_TABLES:
        with _connect(url) as admin:
            admin.execute(f"DROP POLICY tenant_isolation ON {tbl}")
        with _connect(app_url) as app:
            c = app.cursor()
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
            own_nopolicy = c.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]

        with _connect(url) as admin:
            admin.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
        with _connect(app_url) as app:
            c = app.cursor()
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
            leaked = c.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s",
                               (b,)).fetchone()[0]

        with _connect(url) as admin:
            admin.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
            admin.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
            admin.execute(f"CREATE POLICY tenant_isolation ON {tbl} USING "
                          f"(tenant_id = current_setting('app.tenant_id', true)::uuid)")
        with _connect(app_url) as app:
            c = app.cursor()
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
            after_other = c.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s",
                                    (b,)).fetchone()[0]
            after_own = c.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]

        note(own_nopolicy == 0,
             f"{tbl}: policy DROPPED (rls still forced) -> default-deny, tenant A sees "
             f"{own_nopolicy} rows, not even its own. It fails CLOSED")
        note(before[tbl][1] == 0 and leaked > 0,
             f"{tbl}: RLS DISABLED -> {leaked} of tenant B's rows APPEAR, where {before[tbl][1]} "
             f"were visible with it on. The check was measuring the protection")
        note(after_other == 0 and after_own >= 1,
             f"{tbl}: restored -> tenant A sees its own {after_own} again and {after_other} "
             f"of tenant B's")

    # ── source_documents (009): the one table whose SHARING is the property ──
    #
    # Every check above asks "can tenant A see tenant B's row". This table inverts the
    # question: public fetched material is shared on purpose, so BOTH tenants must see the
    # same row, and what keeps a client contract out of it is a CHECK rather than a policy.
    # Only a live server can prove a CHECK refuses a row, which is why this is here and not
    # in gateway/schema.py.
    print()
    import datetime as _dt
    _sha = "a" * 64
    _basis = ("Material featured on this Website may be reproduced free of charge after "
              "taking proper permission by sending a mail to us.")
    with _connect(url) as admin:
        cur = admin.cursor()
        cur.execute("INSERT INTO source_documents (sha256, tier, source_id, url, "
                    "fetched_at, payload_kind, bytes, attribution, terms_basis) "
                    "VALUES (%s,'OFFICIAL_LIVE','sebi','https://www.sebi.gov.in/x.html',"
                    "now(),'HTML',%s,%s,%s)",
                    (_sha, b"<html>a circular</html>", "SEBI, prominently acknowledged",
                     _basis))
        note(True, "source_documents: a public OFFICIAL_LIVE row inserts")

        # The load-bearing refusal. A client contract in a cross-tenant table is the worst
        # bug this schema could ship, and the database refuses it, not the application.
        for tier, why in (("CLIENT", "a client document belongs in `documents` under FORCE "
                                     "RLS, never in a shared table"),
                          ("HELD", "HELD is the git corpus, not fetched material"),
                          ("NONSENSE", "an unknown tier is not a tier")):
            try:
                cur.execute("INSERT INTO source_documents (sha256, tier, source_id, url, "
                            "fetched_at, payload_kind, bytes, terms_basis) VALUES "
                            "(%s,%s,'x','https://x/','2026-09-30','HTML',%s,%s)",
                            ("b" * 64, tier, b"x", _basis))
                note(False, f"source_documents REFUSES tier {tier}: {why}")
            except Exception:                                   # noqa: BLE001
                admin.rollback() if not admin.autocommit else None
                note(True, f"source_documents REFUSES tier {tier} -- {why}")

        for label, cols, vals in (
            ("terms_basis under 20 chars (a permission must be in words, not a boolean)",
             "sha256, tier, source_id, url, fetched_at, payload_kind, bytes, terms_basis",
             ("c" * 64, "OFFICIAL_LIVE", "sebi", "https://x/", "2026-09-30", "HTML",
              b"x", "fine")),
            ("a LICENSED row with no attribution (Indian Kanoon's terms require it for "
             "RAG context, not only for display)",
             "sha256, tier, source_id, url, fetched_at, payload_kind, bytes, terms_basis",
             ("d" * 64, "LICENSED", "indiankanoon", "https://x/", "2026-09-30", "HTML",
              b"x", _basis)),
            ("a fetch dated in the future",
             "sha256, tier, source_id, url, fetched_at, payload_kind, bytes, terms_basis",
             ("e" * 64, "OFFICIAL_LIVE", "sebi", "https://x/", "2027-01-01", "HTML",
              b"x", _basis)),
            ("a plain-http url",
             "sha256, tier, source_id, url, fetched_at, payload_kind, bytes, terms_basis",
             ("f" * 64, "OFFICIAL_LIVE", "sebi", "http://x/", "2026-09-30", "HTML",
              b"x", _basis)),
        ):
            try:
                cur.execute(f"INSERT INTO source_documents ({cols}) VALUES "
                            f"({','.join(['%s'] * len(vals))})", vals)
                note(False, f"source_documents refuses {label}")
            except Exception:                                   # noqa: BLE001
                note(True, f"source_documents refuses {label}")

    with _connect(url) as admin:
        forced = admin.execute(
            "SELECT relrowsecurity OR relforcerowsecurity FROM pg_class "
            "WHERE relname = 'source_documents'").fetchone()[0]
        note(not forced,
             "source_documents is NOT row-level-security bound -- public material is "
             "shared deliberately, and the tier CHECK is what makes that safe")

    # Both tenants see the SAME row. The inverse of every other check in this file.
    seen = {}
    for who, tenant in (("A", a), ("B", b)):
        with _connect(app_url) as app:
            c = app.cursor()
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant),))
            seen[who] = c.execute("SELECT count(*) FROM source_documents WHERE sha256=%s",
                                  (_sha,)).fetchone()[0]
    note(seen["A"] == 1 and seen["B"] == 1,
         f"source_documents: tenant A and tenant B BOTH see the same public row "
         f"(A={seen['A']}, B={seen['B']}) -- one SEBI circular, one row, which is the "
         f"point of it not being tenant-scoped")

    # ── append-only, as the application role ────────────────────────────────
    print()
    with _connect(app_url) as app:
        c = app.cursor()
        c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
        for op in ("UPDATE audit_log SET outcome = 'tampered'", "DELETE FROM audit_log"):
            try:
                c.execute(op)
                note(False, f"audit_log refuses {op.split()[0]}")
            except Exception:                                   # noqa: BLE001
                note(True, f"audit_log refuses {op.split()[0]}")

    # ── one tenant cannot overwrite another's run ───────────────────────────
    # Found the hard way: write_run uses ON CONFLICT DO UPDATE, and ON CONFLICT resolves
    # against the INDEX, which sees rows the policy hides. So a second tenant writing the
    # same run id reaches the first tenant's row -- and RLS refuses the update. That is the
    # isolation working, and it is worth an assertion of its own rather than a surprise.
    print()
    from gateway.store import PostgresBackend, conformance
    shared_id = str(uuid.uuid4())
    ba = PostgresBackend(app_url, tenant_id=str(a), actor_id=str(actor_a))
    bb = PostgresBackend(app_url, tenant_id=str(b), actor_id=str(actor_b))
    ba.write_run({"id": shared_id, "intent": "ask", "status": "ANSWERED",
                  "steps": [], "propositions": []})
    note(ba.read_run(shared_id) is not None, "tenant A writes a run and reads it back")
    note(bb.read_run(shared_id) is None,
         "...and tenant B cannot READ it, though it knows the id")
    try:
        bb.write_run({"id": shared_id, "intent": "ask", "status": "REFUSED",
                      "refusal_code": "NO_MODEL", "steps": [], "propositions": []})
        note(False, "...nor OVERWRITE it")
    except Exception as e:                                       # noqa: BLE001
        note("row-level security" in str(e).lower(),
             f"...nor OVERWRITE it: the database refuses, not the application "
             f"({type(e).__name__})")
    still = ba.read_run(shared_id)
    note(still and still["status"] == "ANSWERED" and still["intent"] == "ask",
         "...and tenant A's run is untouched by the attempt")

    # ── the database refuses a billed provider claiming a call was free ─────
    print()
    with _connect(app_url) as app:
        c = app.cursor()
        c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
        rid2 = str(uuid.uuid4())
        c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status) "
                  "VALUES (%s,%s,%s,'ask','ANSWERED')", (rid2, a, actor_a))
        try:
            c.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                      "status, provider, cost_inr) VALUES (%s,0,%s,'research','ANSWERED',"
                      "'azure',0)", (rid2, a))
            note(False, "the database refuses cost_inr=0 from a billed provider")
        except Exception as e:                                   # noqa: BLE001
            note("run_steps_billed_never_zero" in str(e),
                 "the DATABASE refuses cost_inr=0 from a billed provider, not only the "
                 "application -- the application is not the only thing that can write")
        c.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, status, "
                  "provider, cost_inr, cost_note) VALUES (%s,1,%s,'research','ANSWERED',"
                  "'azure',NULL,'UNPRICED: no verified price on record')", (rid2, a))
        note(True, "...while NULL with a reason is accepted, which is what UNPRICED is")
        c.execute("INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, status, "
                  "provider, cost_inr) VALUES (%s,2,%s,'classify','ANSWERED','gemini',0)",
                  (rid2, a))
        note(True, "...and a FREE provider may record 0, because its marginal cost is zero")

        # PLAN_23 §1.8 in the schema (008): an approval must record the quote as viewed.
        c.execute("INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                  "status, source_ref) VALUES (%s,%s,%s,0,'VERIFIED','ss:T1.2')",
                  (uuid.uuid4(), rid2, a))
        try:
            c.execute("INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, "
                      "decision, reason, quoted_span, quote_viewed, actor_id) VALUES "
                      "(%s,%s,%s,'ss:T1.2','APPROVED','Looks right to me here.','x',"
                      "false,%s)", (uuid.uuid4(), rid2, a, actor_a))
            note(False, "the database refuses an APPROVAL whose quote was not viewed")
        except Exception as e:                                   # noqa: BLE001
            note("decisions_approval_saw_quote" in str(e),
                 "the DATABASE refuses an approval whose quote was not viewed, not only "
                 "the API -- a backfill reaches the table, not the verb")
        c.execute("INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, "
                  "decision, reason, quoted_span, quote_viewed, actor_id) VALUES "
                  "(%s,%s,%s,'ss:T1.2','REJECTED','Not what the book says.','x',false,%s)",
                  (uuid.uuid4(), rid2, a, actor_a))
        note(True, "...while a REJECTION without it is recorded, as not viewed")
        try:
            c.execute("UPDATE runs SET law_versions = '[\"a\"]'::jsonb WHERE run_id = %s",
                      (rid2,))
            note(False, "the database refuses law_versions that are not a map")
        except Exception as e:                                   # noqa: BLE001
            note("runs_law_versions_object" in str(e),
                 "...and law_versions must be a {path: blob} map, not any JSON at all")

    # ── the SAME store contract the gate runs against the dict ──────────────
    print()
    for ok_, label in conformance(PostgresBackend(app_url, tenant_id=str(a),
                                                  actor_id=str(actor_a))):
        note(ok_, f"[postgres] {label}")

    # ── and the SAME queue contract (PLAN_23 O2) ────────────────────────────
    # The gate runs this against a dict. Here it runs against SELECT ... FOR UPDATE SKIP
    # LOCKED, which is the only implementation that has to survive two workers at once.
    print()
    from gateway.jobs import PostgresQueue, conformance as queue_conformance
    pq = PostgresQueue(app_url, tenant_id=str(a), actor_id=str(actor_a))
    # conformance() enqueues against run ids of its own, so the runs have to exist first.
    import uuid as _u
    with _connect(url) as _c:
        _c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
        _queue_runs = []
        for _ in range(6):
            _r = _u.uuid4()
            _c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status) "
                       "VALUES (%s,%s,%s,'review_document','PLANNED')", (_r, a, actor_a))
            _queue_runs.append(str(_r))
    for ok_, label in queue_conformance(_SeededQueue(pq, _queue_runs)):
        note(ok_, f"[postgres queue] {label}")

    # Two workers, one queue: the assertion SKIP LOCKED exists for. Without it the second
    # claim blocks on the first's lock instead of stepping over it.
    with _connect(url) as _c:
        _c.execute("SELECT set_config('app.tenant_id', %s, false)", (str(a),))
        _r1, _r2 = _u.uuid4(), _u.uuid4()
        for _r in (_r1, _r2):
            _c.execute("INSERT INTO runs (run_id, tenant_id, actor_id, intent, status) "
                       "VALUES (%s,%s,%s,'review_document','PLANNED')", (_r, a, actor_a))
    pq.enqueue(run_id=str(_r1), intent="review_document", args={})
    pq.enqueue(run_id=str(_r2), intent="review_document", args={})
    j_a = pq.claim(worker="worker-1")
    j_b = pq.claim(worker="worker-2")
    note(j_a is not None and j_b is not None and j_a.job_id != j_b.job_id,
         f"[postgres queue] two workers claiming at once get two DIFFERENT jobs "
         f"({j_a and j_a.job_id[:8]} vs {j_b and j_b.job_id[:8]}) -- this is what FOR "
         f"UPDATE SKIP LOCKED buys, and it is the check that fails if it is dropped")
    note(pq.claim(worker="worker-3") is None,
         "[postgres queue] ...and a third worker finds nothing claimable rather than "
         "blocking on a lease someone else holds")
    for _j in (j_a, j_b):
        if _j:
            pq.finish(_j.job_id, "DONE")

    print()
    if failures:
        print(f"{len(failures)} FAILED — tenant isolation is NOT proved on this server.")
        print("Do not edit this script to make it pass. Report it.")
        return 1
    print(f"all properties proved on {version.split(' on ')[0]} as {APP_ROLE}.")
    return 0


# ── which database this script may destroy, and which variable names it ──────
#
# `--run` applies every migration, seeds rows, DROPS POLICIES and DISABLES RLS to show the
# checks measure something. On a real database that sequence is destructive, and on
# 2026-10-01 it was pointed at one: `DATABASE_URL=postgresql:///placedon_throwaway_013` was
# set, `main` read `database_url() or os.getenv("DATABASE_URL")`, `database_url()` found
# the .env's PLACEDON_DATABASE_URL first, and migrations 001-007 ran against placedon_dev.
# 008 rolled back whole on its own BEGIN/COMMIT so nothing was lost -- by luck of how that
# file is written, not by anything here.
#
# Two guards, because two separate things went wrong: the WRONG VARIABLE was consulted, and
# NOTHING checked which database the connection named.

# The one variable, named where every function can see it. `gateway/store.py` owns the
# name; importing it rather than restating it is what stops the script and the application
# from disagreeing about which variable holds the connection.
from gateway.store import URL_ENV

THROWAWAY_PREFIX = "placedon_throwaway_"

# Refused by name as well as by prefix. A generic "wrong prefix" message would not say that
# this is the database the incident actually touched, and the one a developer is most
# likely to have in their shell.
REFUSED_BY_NAME = frozenset({"placedon_dev", "placedon_t0_rls", "postgres", "template1"})


def database_name(url: str) -> str:
    """The database a connection string names, or "" when it names none.

    Handles both libpq forms: a URL (`postgresql://user@host:5432/name?opts`) and a keyword
    string (`dbname=name user=me`). Returns "" rather than guessing, because a default here
    would be a guess about which database is about to be rewritten.
    """
    text = (url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        for part in text.split():
            if part.startswith("dbname="):
                return part.split("=", 1)[1].strip()
        return ""
    from urllib.parse import urlsplit
    return urlsplit(text).path.lstrip("/").split("?")[0].strip()


def refuse_target(url: str) -> str | None:
    """The reason this database may not be used, or None when it may be."""
    name = database_name(url)
    if not name:
        return (f"this connection string names no database, so there is no way to tell "
                f"what --run would rewrite. It must name one whose name starts with "
                f"{THROWAWAY_PREFIX!r}.")
    if name in REFUSED_BY_NAME:
        return (f"{name!r} is refused BY NAME. --run applies every migration, seeds rows, "
                f"drops policies and disables RLS; on {name!r} that is destructive. On "
                f"2026-10-01 this script ran migrations 001-007 against placedon_dev "
                f"because the wrong variable was set, and only 008's own transaction "
                f"stopped it going further. Create a database named "
                f"{THROWAWAY_PREFIX}<something> and drop it afterwards.")
    if not name.startswith(THROWAWAY_PREFIX):
        return (f"{name!r} does not start with {THROWAWAY_PREFIX!r}. --run is destructive "
                f"-- it drops policies and disables RLS to prove the checks measure "
                f"something -- so it will only touch a database whose NAME says it exists "
                f"to be thrown away.")
    return None


def resolve_url(env) -> tuple[str | None, str | None]:
    """(url, refusal) from the environment. Reads PLACEDON_DATABASE_URL and nothing else.

    `DATABASE_URL` is not a fallback. It used to be, and the two names are close enough
    that setting one while the other is in a .env is a mistake nobody notices until the
    wrong database has been written to -- which is precisely what happened. Setting only
    `DATABASE_URL` is therefore a LOUD failure and not a quiet substitution.
    """
    url = (env.get(URL_ENV) or "").strip()
    other = (env.get("DATABASE_URL") or "").strip()
    if url:
        return url, None                      # DATABASE_URL is ignored, never merged
    if other:
        return None, (
            f"DATABASE_URL is set but {URL_ENV} is not. This script reads {URL_ENV} ONLY. "
            f"The two names are one word apart, and reading both is how a --run aimed at a "
            f"throwaway database ended up applying migrations to placedon_dev on "
            f"2026-10-01. Set {URL_ENV} explicitly.")
    return None, (
        f"{URL_ENV} is not set. Refusing to invent one: a connection string guessed here "
        f"would either fail confusingly or hit the wrong database.")


def main(argv: list[str]) -> int:
    print("scripts/rls_integration.py")
    print(f"  {status()}\n")
    if "--run" not in argv:
        print("  (pass --run with PLACEDON_DATABASE_URL set to prove it against a real server)")
        return 0
    # PLACEDON_DATABASE_URL only, and only a database whose name says it is disposable.
    # `database_url()` reads it through checker.env so a .env is honoured -- which is
    # exactly why the environment is consulted here too: a .env value and a shell value
    # must not be able to disagree silently.
    from gateway.store import database_url
    shell = dict(os.environ)
    # The mix-up is judged on the SHELL environment, before a .env is allowed to fill the
    # variable in. On this machine .env supplies PLACEDON_DATABASE_URL=...placedon_dev, so
    # merging first would mean `DATABASE_URL=... --run` always looked like a correctly
    # configured run aimed at the wrong database -- the incident, with the one message
    # that would have explained it suppressed.
    if shell.get("DATABASE_URL") and not shell.get(URL_ENV):
        print(f"  REFUSED: {resolve_url(shell)[1]}")
        return 2
    env = dict(shell)
    if not env.get(URL_ENV):
        from_file = database_url()
        if from_file:
            env[URL_ENV] = from_file
    url, refusal = resolve_url(env)
    if refusal:
        print(f"  REFUSED: {refusal}")
        return 2
    target = refuse_target(url)
    if target:
        print(f"  REFUSED: {target}")
        return 2
    print(f"  target : {database_name(url)} (matches {THROWAWAY_PREFIX}*)\n")
    return run(url)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("rls_integration (the guard; the proof itself needs a server and --run)")

    # ── which database this script is allowed to destroy ────────────────────
    for url, name in (
            ("postgresql:///placedon_throwaway_1", "placedon_throwaway_1"),
            ("postgresql://me@localhost:5432/placedon_throwaway_x", "placedon_throwaway_x"),
            ("postgres://u:p@h:5432/placedon_dev?sslmode=require", "placedon_dev"),
            ("dbname=placedon_dev user=me", "placedon_dev"),
            ("postgresql:///placedon_dev", "placedon_dev")):
        check(database_name(url) == name,
              f"the database name is read out of {url[:38]!r} -> {name}")
    check(database_name("postgresql://host/") == "",
          "...and a url naming no database reads as empty, never as a default")

    check(refuse_target("postgresql:///placedon_throwaway_013") is None,
          "a placedon_throwaway_ database is allowed: that is what this script is for")
    for bad, why in (("postgresql:///placedon_dev", "placedon_dev"),
                     ("dbname=placedon_dev user=me", "placedon_dev in key=value form"),
                     ("postgresql:///placedon_rls_013", "a name I invented on the day"),
                     ("postgresql:///postgres", "the cluster's own database"),
                     ("postgresql:///placedon_t0_rls", "an older real database"),
                     ("postgresql://host/", "a url naming no database at all")):
        reason = refuse_target(bad)
        check(bool(reason), f"REFUSED: {why}")
        check(bool(reason) and THROWAWAY_PREFIX in (reason or ""),
              f"...and the reason names the prefix it wanted ({(reason or '')[:40]!r})")
    check("by name" in (refuse_target("postgresql:///placedon_dev") or "").lower(),
          "placedon_dev is refused BY NAME, with its own reason -- it is the database that "
          "actually got migrations run against it on 2026-10-01, and a generic prefix "
          "message would not say so")
    check(refuse_target("postgresql:///placedon_dev")
          != refuse_target("postgresql:///placedon_rls_013"),
          "...so its reason is not the same sentence every other refusal gets")

    # ── which environment variable is read ─────────────────────────────────
    url, refusal = resolve_url({"PLACEDON_DATABASE_URL": "postgresql:///placedon_throwaway_a"})
    check(url == "postgresql:///placedon_throwaway_a" and refusal is None,
          "PLACEDON_DATABASE_URL is read")
    url2, refusal2 = resolve_url({"DATABASE_URL": "postgresql:///placedon_throwaway_b"})
    check(url2 is None and bool(refusal2),
          "DATABASE_URL ALONE is refused, not used")
    check("DATABASE_URL" in (refusal2 or "") and "PLACEDON_DATABASE_URL" in (refusal2 or ""),
          f"...and the refusal names BOTH variables, because the whole failure is that "
          f"they look alike ({(refusal2 or '')[:60]!r})")
    url3, refusal3 = resolve_url({"PLACEDON_DATABASE_URL": "postgresql:///placedon_throwaway_c",
                                  "DATABASE_URL": "postgresql:///somewhere_else"})
    check(url3 == "postgresql:///placedon_throwaway_c" and refusal3 is None,
          "with both set, PLACEDON_DATABASE_URL wins and DATABASE_URL is ignored -- never "
          "merged, never preferred")
    url4, refusal4 = resolve_url({})
    check(url4 is None and bool(refusal4) and "DATABASE_URL is set" not in (refusal4 or ""),
          "neither set is refused, and NOT with the mistaken-variable message")

    # The incident this exists for, replayed.
    _, _r = resolve_url({"DATABASE_URL": "postgresql:///placedon_throwaway_013"})
    check(bool(_r),
          "THE 2026-10-01 INCIDENT: `DATABASE_URL=...throwaway python3 "
          "scripts/rls_integration.py --run` is refused outright. It previously fell "
          "through to `database_url() or os.getenv('DATABASE_URL')`, where the .env's "
          "PLACEDON_DATABASE_URL won and migrations 001-007 ran against placedon_dev")

    # The ordering that makes the mix-up message reachable at all.
    _shell = {"DATABASE_URL": "postgresql:///placedon_throwaway_013"}
    _merged = dict(_shell, **{URL_ENV: "postgresql:///placedon_dev"})   # as a .env would
    check(resolve_url(_merged)[1] is None,
          "once a .env supplies the variable, resolve_url is satisfied by it...")
    check("DATABASE_URL is set" in (resolve_url(_shell)[1] or ""),
          "...which is why `main` judges the MIX-UP on the shell environment first: "
          "merging the .env in beforehand would hide the one message that explains what "
          "the user actually did wrong")

    check(THROWAWAY_PREFIX == "placedon_throwaway_",
          f"the prefix is {THROWAWAY_PREFIX!r}")
    check(URL_ENV == "PLACEDON_DATABASE_URL",
          f"the variable is gateway/store.py's own URL_ENV, imported and not restated, so "
          f"the script and the application cannot disagree about it ({URL_ENV})")
    check("placedon_dev" in REFUSED_BY_NAME, "placedon_dev is in the by-name refusal list")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main(sys.argv))
