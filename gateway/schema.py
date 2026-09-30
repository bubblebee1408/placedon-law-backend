"""The migrations, checked statically, because the live check cannot be in the gate.

`scripts/rls_integration.py` proves tenant isolation against a real Postgres and is
deliberately outside scripts/run_tests.sh: a suite needing a server either gets skipped --
and a skipped security test reads as a passing one -- or it makes the whole gate conditional
on infrastructure.

What CAN be checked without a server is the SQL text, and the failure that check catches is
the likely one: somebody adds a table with a tenant_id and forgets a line.

## The line that is easy to forget, and fatal

    ALTER TABLE x ENABLE ROW LEVEL SECURITY;   -- exempts the table OWNER
    ALTER TABLE x FORCE  ROW LEVEL SECURITY;   -- and now it does not

ENABLE alone does not apply to the owner, and the owner is who the application connects as
in most deployments. A schema with ENABLE and no FORCE reads as isolated and is not, and
nothing about it looks wrong. So this module derives the set of tenant-scoped tables FROM
THE SQL -- every CREATE TABLE carrying a tenant_id column -- rather than from a list
someone maintains, and requires all three declarations for each. A new table is in scope
the moment it has a tenant_id, whether or not anyone remembered this file.

Run: PYTHONPATH=. python3 gateway/schema.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "gateway" / "migrations"
GATE = ROOT / "scripts" / "run_tests.sh"
LIVE_CHECK = ROOT / "scripts" / "rls_integration.py"

# Tables that hold no tenant data and are therefore not tenant-scoped. Listed explicitly,
# because "it has no tenant_id" must be a decision someone wrote down rather than an
# omission nobody noticed.
NOT_TENANT_SCOPED = frozenset({"tenants"})


def migrations() -> tuple[Path, ...]:
    return tuple(sorted(MIGRATIONS.glob("*.sql")))


def sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in migrations())


def tables(text: str | None = None) -> dict[str, str]:
    """{table name: its CREATE TABLE body}, from the SQL itself."""
    text = sql() if text is None else text
    out = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);",
                         text, re.DOTALL):
        out[m.group(1)] = m.group(2)
    return out


def tenant_scoped(text: str | None = None) -> set[str]:
    """Every table with a tenant_id column. Derived, never listed."""
    return {name for name, body in tables(text).items()
            if re.search(r"\btenant_id\b", body) and name not in NOT_TENANT_SCOPED}


def declares(kind: str, table: str, text: str | None = None) -> bool:
    text = sql() if text is None else text
    return bool(re.search(rf"ALTER TABLE\s+{table}\s+{kind}\s+ROW LEVEL SECURITY\s*;",
                          text, re.IGNORECASE))


def has_policy(table: str, text: str | None = None) -> bool:
    text = sql() if text is None else text
    m = re.search(rf"CREATE POLICY\s+\w+\s+ON\s+{table}\s+USING\s*\((.*?)\)\s*;",
                  text, re.DOTALL | re.IGNORECASE)
    # The policy must compare against a SESSION setting, not a column the caller supplies.
    # `tenant_id = tenant_id` would be a policy, and would be a filter rather than a bound.
    return bool(m and "current_setting" in m.group(1))


def unprotected(text: str | None = None) -> list[tuple[str, str]]:
    """(table, what is missing) for every tenant-scoped table that is not fully bound."""
    text = sql() if text is None else text
    bad = []
    for t in sorted(tenant_scoped(text)):
        for kind in ("ENABLE", "FORCE"):
            if not declares(kind, t, text):
                bad.append((t, f"{kind} ROW LEVEL SECURITY"))
        if not has_policy(t, text):
            bad.append((t, "a policy using current_setting"))
    return bad


def live_check_is_outside_gate() -> bool:
    return "rls_integration" not in GATE.read_text(encoding="utf-8")


def live_check_status() -> str:
    from importlib import util
    spec = util.spec_from_file_location("_rls", LIVE_CHECK)
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return "UNRUN" if mod.LAST_RUN is None else str(mod.LAST_RUN)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    files = [p.name for p in migrations()]
    check(files == ["001_core.sql", "002_runs.sql", "003_step_provenance.sql",
                    "004_cost_note.sql", "005_decisions.sql", "006_jobs.sql",
                    "007_cascade.sql", "008_decision_evidence.sql"],
          f"every migration exists, in order ({files})")
    step_sql = (MIGRATIONS / "003_step_provenance.sql").read_text(encoding="utf-8")
    for col in ("provider", "region", "cost_inr"):
        check(f"ADD COLUMN IF NOT EXISTS {col}" in step_sql,
              f"003 adds run_steps.{col}, idempotently")
    cost_sql = (MIGRATIONS / "004_cost_note.sql").read_text(encoding="utf-8")
    check("ADD COLUMN IF NOT EXISTS cost_note" in cost_sql,
          "004 adds run_steps.cost_note")
    check("run_steps_billed_never_zero" in cost_sql
          and "cost_inr <> 0" in cost_sql,
          "...and a CHECK constraint so a BILLED provider cannot record a zero cost -- the "
          "database enforces it too, because the application is not the only thing that "
          "can write a row")
    check("PLAN_22 D3" in step_sql and "region" in step_sql,
          "...and says why the region is on the STEP: a region in a deployment note is a "
          "region nobody checks")

    t = tables()
    check({"tenants", "actors", "api_keys", "documents", "audit_log",
           "runs", "run_steps", "propositions", "decisions", "jobs",
           "cascade_runs"} <= set(t),
          f"every table the gateway needs is declared ({sorted(t)})")

    scoped = tenant_scoped()
    check("tenants" not in scoped,
          "the tenants table is not tenant-scoped, and that is written down rather than "
          "inferred from a missing column")
    check(scoped == {"actors", "api_keys", "documents", "audit_log", "runs", "run_steps",
                     "propositions", "decisions", "jobs", "cascade_runs"},
          f"every other table is tenant-scoped, DERIVED from having a tenant_id ({sorted(scoped)})")

    # ── the check this module exists for ────────────────────────────────────
    check(not unprotected(),
          f"every tenant-scoped table declares ENABLE, FORCE and a policy ({unprotected()})")
    for tbl in sorted(scoped):
        check(declares("FORCE", tbl),
              f"{tbl}: FORCE ROW LEVEL SECURITY -- ENABLE alone exempts the table owner, "
              f"which is who the application connects as")

    # ── and it must be able to fail ─────────────────────────────────────────
    forgot = """
CREATE TABLE IF NOT EXISTS widgets (
    widget_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL
);
ALTER TABLE widgets ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON widgets USING
    (tenant_id = current_setting('app.tenant_id', true)::uuid);
"""
    bad = unprotected(sql() + forgot)
    check(("widgets", "FORCE ROW LEVEL SECURITY") in bad,
          "a new table with ENABLE, a policy and NO FORCE is caught -- the exact omission "
          "that reads as isolated and is not")
    check(len(bad) == 1, f"...and nothing else is flagged with it ({bad})")

    leaky = """
CREATE TABLE IF NOT EXISTS gadgets (
    gadget_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL
);
ALTER TABLE gadgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE gadgets FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON gadgets USING (tenant_id = tenant_id);
"""
    bad2 = unprotected(sql() + leaky)
    check(("gadgets", "a policy using current_setting") in bad2,
          "a policy that compares a column to itself is caught: it is a filter, not a "
          "boundary, and it would pass a naive 'has a policy' check")

    nofence = "\nCREATE TABLE IF NOT EXISTS gizmos (\n    tenant_id uuid NOT NULL\n);\n"
    check(("gizmos", "ENABLE ROW LEVEL SECURITY") in unprotected(sql() + nofence),
          "a tenant table with no RLS at all is caught")

    # ── the audit table records that a thing happened, never what was in it ──
    check("body" not in t["audit_log"] and "payload" not in t["audit_log"],
          "audit_log has no body or payload column, and is not going to get one")
    check("prev_digest" in t["audit_log"] and "digest" in t["audit_log"],
          "...it is hash-chained, like gateway/audit.py")
    check("body" in t["documents"],
          "documents DOES hold bytes -- that is the point of it, and why it is "
          "tenant-scoped and FORCE-bound")

    # ── the live check stays outside the gate, and says it has not run ───────
    check(LIVE_CHECK.is_file(), "scripts/rls_integration.py exists")
    check(live_check_is_outside_gate(),
          "...and is NOT in scripts/run_tests.sh: a suite that needs a server would be "
          "skipped, and a skipped security test reads as a passing one")
    st = live_check_status()
    check(st != "UNRUN",
          "...and is no longer UNRUN: it was run on 29-09-2026 against PostgreSQL 18.6")
    check("PostgreSQL" in st and "placedon_app" in st and "2026-" in st,
          f"...recording the DATE, the server and the ROLE it asserted as ({st[:60]}…). "
          f"The role is the load-bearing part: a superuser bypasses row-level security "
          f"unconditionally, so a run as one proves nothing")
    check("0 failures" in st, "...and that nothing failed")

    # ── R-016, decided ──────────────────────────────────────────────────────
    runs_sql = (MIGRATIONS / "002_runs.sql").read_text(encoding="utf-8")
    check("R-016" in runs_sql and "DERIVATION" in runs_sql,
          "002_runs.sql records WHICH question it was blocked on and how it was answered")
    check("refusal_code_iff_refused" in runs_sql,
          "...and agents/state.py's invariant is in the schema too: REFUSED carries a code "
          "and nothing else does")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
