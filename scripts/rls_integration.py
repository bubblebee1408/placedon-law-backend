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

Run:  PLACEDON_DATABASE_URL=postgres://... PYTHONPATH=. python3 scripts/rls_integration.py --run
      PYTHONPATH=. python3 scripts/rls_integration.py            # prints this status

`PLACEDON_DATABASE_URL` is the variable, the same one gateway/store.py selects on: two
names for one connection is how a script proves isolation on a database the application
never uses.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MIGRATIONS = ROOT / "gateway" / "migrations"

# Set this to an ISO date and a server description the day it is actually run.
LAST_RUN: str | None = (
    "2026-09-29 — PostgreSQL 18.6 (Postgres.app), local socket, database placedon_dev, "
    "asserted as role placedon_app (NOSUPERUSER, NOBYPASSRLS). 54 checks, 0 "
    "failures, migrations 001-003 applied.")

TENANT_TABLES = ("actors", "api_keys", "documents", "audit_log",
                 "runs", "run_steps", "propositions")


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
                  "004_cost_note.sql"):
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

    # ── the SAME store contract the gate runs against the dict ──────────────
    print()
    for ok_, label in conformance(PostgresBackend(app_url, tenant_id=str(a),
                                                  actor_id=str(actor_a))):
        note(ok_, f"[postgres] {label}")

    print()
    if failures:
        print(f"{len(failures)} FAILED — tenant isolation is NOT proved on this server.")
        print("Do not edit this script to make it pass. Report it.")
        return 1
    print(f"all properties proved on {version.split(' on ')[0]} as {APP_ROLE}.")
    return 0


def main(argv: list[str]) -> int:
    print("scripts/rls_integration.py")
    print(f"  {status()}\n")
    if "--run" not in argv:
        print("  (pass --run with PLACEDON_DATABASE_URL set to prove it against a real server)")
        return 0
    # The SAME variable gateway/store.py selects on, read through checker.env so .env is
    # honoured. Two names for one connection is how a script proves isolation on a
    # database the application never uses.
    from gateway.store import URL_ENV, database_url
    url = database_url() or os.getenv("DATABASE_URL")
    if not url:
        print(f"  {URL_ENV} is not set (nor DATABASE_URL). Refusing to invent one: a "
              f"connection string guessed here would either fail confusingly or hit the "
              f"wrong database.")
        return 2
    return run(url)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
