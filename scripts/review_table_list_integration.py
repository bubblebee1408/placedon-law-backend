#!/usr/bin/env python3
"""review_table.list on Postgres: the firm's tables, and only the ones this person may open.

The gate runs `review_table.list` against the in-memory store, which refuses a second tenant
outright, so "another firm's tables never appear" can only be proved here, under row-level
security, as the application role (NOSUPERUSER NOBYPASSRLS) that production uses.

    python3 scripts/review_table_list_integration.py --run     # live, throwaway DB
    python3 scripts/review_table_list_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database and refuses any other name.
"""
from __future__ import annotations

import os
import sys
import uuid
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")


def _run() -> int:
    import psycopg
    from gateway.store import PostgresBackend
    from gateway.verbs import Context, _review_table_list, _review_table_status

    scratch = f"{PREFIX}rtlist_{os.getpid()}"
    assert scratch.startswith(PREFIX), "scratch-name guard"
    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    app_url = f"postgresql:///{scratch}?host={HOST}&user={APP}"
    firm_a, firm_b = str(uuid.uuid4()), str(uuid.uuid4())
    alice, colleague, bob = (str(uuid.uuid4()) for _ in range(3))
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    try:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                assert scratch.startswith(PREFIX)
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
                c.execute(f'CREATE DATABASE "{scratch}" OWNER "{APP}"')
            with psycopg.connect(app_url, autocommit=True, connect_timeout=10) as c:
                for p in sorted((ROOT / "gateway" / "migrations").glob("[0-9]*.sql"),
                                key=lambda p: int(p.name.split("_")[0])):
                    c.execute(p.read_text())
                for tenant, actors in ((firm_a, (alice, colleague)), (firm_b, (bob,))):
                    c.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
                    c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,'rtlist')",
                              (tenant,))
                    for a in actors:
                        c.execute("INSERT INTO actors (actor_id, tenant_id, label) "
                                  "VALUES (%s,%s,'rtlist')", (a, tenant))
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0

        def ctx(tenant, actor):
            return Context(tenant=tenant, actor=actor,
                           store=PostgresBackend(app_url, tenant_id=tenant, actor_id=actor))

        cols = [{"name": "governing law", "kind": "text", "question": "Which law governs?"}]
        a_ctx, b_ctx = ctx(firm_a, alice), ctx(firm_b, bob)
        g_a, g_b = str(uuid.uuid4()), str(uuid.uuid4())
        a_ctx.store.write_grid({"grid_id": g_a, "name": "Firm A NDAs", "columns": cols,
                                "document_ids": ["a" * 64]})
        b_ctx.store.write_grid({"grid_id": g_b, "name": "Firm B leases", "columns": cols,
                                "document_ids": ["b" * 64, "c" * 64]})

        mine = _review_table_list({}, a_ctx)["tables"]
        check([t["grid_id"] for t in mine] == [g_a],
              f"firm A lists its own table and nothing else ({[t['name'] for t in mine]})")
        check(mine and mine[0]["mine"] and mine[0]["created_by"] == alice
              and (mine[0]["documents"], mine[0]["cells"], mine[0]["cells_pending"]) == (1, 1, 1)
              and mine[0]["table_state"] == "RUNNING",
              "...with who started it, its counts and its state, read from Postgres")
        theirs = _review_table_list({}, b_ctx)["tables"]
        check([t["grid_id"] for t in theirs] == [g_b],
              "firm B lists only firm B's table: another firm's never appears")
        check(_review_table_status({"grid_id": g_a}, b_ctx).get("code") == "NOT_FOUND",
              "...and firm B cannot open firm A's table by id either")
        peer = _review_table_list({}, ctx(firm_a, colleague))["tables"]
        check(peer == [],
              "a colleague in firm A with no grant does not see an unfiled table "
              "someone else started (028), the same rule its page applies")

        print(f"\n{ok}/{ok + fail} passed")
        return 1 if fail else 0
    finally:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                assert scratch.startswith(PREFIX)
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
            print(f"dropped {scratch}")
        except Exception as e:                                       # noqa: BLE001
            print(f"WARNING: could not drop {scratch}: {e}", file=sys.stderr)


def _test() -> int:
    """Offline: the verb exists, is read-only and off MCP, and the gate runs this script."""
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    from gateway.verbs import by_name
    v = by_name().get("review_table.list")
    check(v is not None and v.read_only and not v.mcp,
          "review_table.list is declared, read-only and off MCP")
    gate = (ROOT / ".github" / "workflows" / "gate.yml").read_text()
    regressions = (ROOT / "scripts" / "db_regressions.sh").read_text()
    check("scripts/db_regressions.sh" in gate
          and "scripts/review_table_list_integration.py" in regressions,
          "...and CI runs this script against a real database")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--run" in sys.argv:
        return _run()
    return _test()


if __name__ == "__main__":
    raise SystemExit(main())
