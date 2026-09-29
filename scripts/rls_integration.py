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

## STATUS: UNRUN

    LAST_RUN = None

**No Postgres has ever run this.** Until that line carries a date and a server, the
isolation claim in gateway/migrations/*.sql is a claim about SQL text and not about a
database, and gateway/app.py reports store.kind = "in-memory" for that reason. Do not read
a green gate as evidence of tenant isolation; the gate has never seen a tenant.

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
LAST_RUN: str | None = None

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


def _seed(cur, tenant, actor, tag: str) -> None:
    """One row per tenant-scoped table, for this tenant. Enough to be leaked."""
    import uuid
    cur.execute("SET app.tenant_id = %s", (str(tenant),))
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
    """Apply the migrations and prove the properties. Returns an exit code."""
    import uuid
    a, b = uuid.uuid4(), uuid.uuid4()
    actor_a, actor_b = uuid.uuid4(), uuid.uuid4()
    failures: list[str] = []

    def note(ok: bool, label: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(label)

    with _connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        print(f"  server: {version.split(' on ')[0]}\n")

        for f in ("001_core.sql", "002_runs.sql"):
            cur.execute(sql(f))
            print(f"  applied {f}")
        print()

        for t in (a, b):
            cur.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s) "
                        "ON CONFLICT DO NOTHING", (t, f"t-{t}"))
        _seed(cur, a, actor_a, "alpha")
        _seed(cur, b, actor_b, "bravo")

        # ── (a) isolation, on EVERY tenant-scoped table, as the table OWNER ──
        cur.execute("SET app.tenant_id = %s", (str(a),))
        for tbl in TENANT_TABLES:
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s", (b,))
            other = cur.fetchone()[0]
            cur.execute(f"SELECT count(*) FROM {tbl}")
            mine = cur.fetchone()[0]
            note(other == 0 and mine >= 1,
                 f"{tbl}: tenant A sees {mine} of its own rows and {other} of tenant B's")

        cur.execute("SELECT relname FROM pg_class WHERE relname = ANY(%s) "
                    "AND relforcerowsecurity", (list(TENANT_TABLES),))
        forced = {r[0] for r in cur.fetchall()}
        note(forced == set(TENANT_TABLES),
             f"pg_class says FORCE is set on every tenant table "
             f"(missing {sorted(set(TENANT_TABLES) - forced)})")

        # ── (b) the test must be able to FAIL ────────────────────────────────
        print()
        leaked_anywhere = False
        for tbl in TENANT_TABLES:
            cur.execute(f"DROP POLICY tenant_isolation ON {tbl}")
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s", (b,))
            leaked = cur.fetchone()[0]
            leaked_anywhere = leaked_anywhere or leaked > 0
            note(leaked > 0,
                 f"{tbl}: with the policy DROPPED, tenant B's rows appear ({leaked}) -- "
                 f"so the check above was measuring the policy, not an empty table")
            cur.execute(f"CREATE POLICY tenant_isolation ON {tbl} USING "
                        f"(tenant_id = current_setting('app.tenant_id', true)::uuid)")
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE tenant_id = %s", (b,))
            note(cur.fetchone()[0] == 0, f"{tbl}: restoring the policy closes it again")

        # ── append-only ─────────────────────────────────────────────────────
        print()
        for op in ("UPDATE audit_log SET outcome = 'tampered'", "DELETE FROM audit_log"):
            try:
                cur.execute(op)
                note(False, f"audit_log refuses {op.split()[0]}")
            except Exception:                                   # noqa: BLE001
                note(True, f"audit_log refuses {op.split()[0]} even as the owner")

        # ── the SAME store contract the gate runs against the dict ───────────
        print()
        from gateway.store import PostgresBackend, conformance
        for ok_, label in conformance(PostgresBackend(url, tenant_id=str(a),
                                                      actor_id=str(actor_a))):
            note(ok_, f"[postgres] {label}")

    print()
    if failures:
        print(f"{len(failures)} FAILED — tenant isolation is NOT proved on this server.")
        print("Do not edit this script to make it pass. Report it.")
        return 1
    print(f"all properties proved on {version.split(' on ')[0]}.")
    print("Set LAST_RUN in this file to the date and the server.")
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
