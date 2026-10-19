#!/usr/bin/env python3
"""Real-Postgres proof for the shared limiter, restricted to a named scratch database.

    PLACEDON_DATABASE_URL=... python3 scripts/limiter_integration.py

The database name MUST start with ``placedon_rate_limit_test_`` and the connected role must
not be a superuser. Run migrations into that disposable database first. The script writes two
synthetic tenant rows and bucket rows; it never cleans up or mutates any other database.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gateway.limits import PostgresLimiter, RATE_LIMITED  # noqa: E402
from gateway.store import database_url  # noqa: E402


async def run(url: str) -> int:
    import psycopg

    passed = failed = 0

    def check(ok: bool, label: str) -> None:
        nonlocal passed, failed
        passed += int(ok)
        failed += int(not ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    async with await psycopg.AsyncConnection.connect(url, autocommit=True,
                                                      connect_timeout=3) as conn:
        row = await (await conn.execute(
            "SELECT current_database(), current_user, r.rolsuper, r.rolbypassrls "
            "FROM pg_roles r WHERE r.rolname = current_user")).fetchone()
    db_name, _user, is_superuser, bypasses_rls = row
    if not str(db_name).startswith("placedon_rate_limit_test_"):
        print("REFUSED: database name must start with placedon_rate_limit_test_.")
        return 2
    if is_superuser or bypasses_rls:
        print("REFUSED: role must neither be superuser nor BYPASSRLS, so FORCE RLS is exercised.")
        return 2

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    async with await psycopg.AsyncConnection.connect(url, autocommit=True,
                                                      connect_timeout=3) as conn:
        await conn.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s),(%s,%s)",
                           (tenant_a, "synthetic limiter tenant A",
                            tenant_b, "synthetic limiter tenant B"))

    # Two independent limiter objects simulate separate web-worker processes. The database
    # row lock, not a Python lock, must decide who gets the finite initial burst.
    left = PostgresLimiter(url, per_minute=1, burst=3, max_concurrent_checks=8)
    right = PostgresLimiter(url, per_minute=1, burst=3, max_concurrent_checks=8)
    results = await asyncio.gather(*(
        (left if n % 2 else right).check_async(tenant_a) for n in range(12)))
    allowed = sum(result is None for result in results)
    blocked = [r for r in results if r is not None]
    check(allowed == 3 and len(blocked) == 9,
          f"two instances share one exact burst under concurrent calls ({allowed} allowed)")
    left_stats, right_stats = left._pool.stats(), right._pool.stats()
    check(left_stats["peak"] <= 8 and right_stats["peak"] <= 8
          and left_stats["open"] + right_stats["open"] <= 16,
          "two independent workers reuse connections without exceeding either pool cap")
    check(all(r.code == RATE_LIMITED and r.http_status == 429 and r.retry_after >= 1
              for r in blocked), "exhausted calls return 429 with Retry-After")

    restarted = PostgresLimiter(url, per_minute=1, burst=3)
    after_restart = await restarted.check_async(tenant_a)
    check(after_restart is not None and after_restart.code == RATE_LIMITED,
          "creating a new limiter instance does not reset the stored bucket")
    other_tenant = await restarted.check_async(tenant_b)
    check(other_tenant is None, "a separate tenant receives an independent burst")

    # A normal app role connection with no tenant sees no rows. Under tenant B it cannot
    # read or mutate tenant A's bucket even when explicitly naming A's UUID.
    async with await psycopg.AsyncConnection.connect(url, autocommit=False,
                                                      connect_timeout=3) as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_b,))
            visible = await (await conn.execute(
                "SELECT tenant_id FROM gateway_rate_limits WHERE tenant_id = %s",
                (tenant_a,))).fetchall()
            updated = await conn.execute(
                "UPDATE gateway_rate_limits SET tokens = 9999 WHERE tenant_id = %s",
                (tenant_a,))
            check(not visible and updated.rowcount == 0,
                  "FORCE RLS prevents tenant B from reading or changing tenant A's bucket")
    async with await psycopg.AsyncConnection.connect(url, autocommit=False,
                                                      connect_timeout=3) as conn:
        async with conn.transaction():
            no_context = await (await conn.execute(
                "SELECT tenant_id FROM gateway_rate_limits")).fetchall()
            check(not no_context, "unset app.tenant_id sees no limiter rows")

    print(f"\n{passed}/{passed + failed} passed (database: {db_name})")
    return int(bool(failed))


def main() -> int:
    url = database_url()
    if not url:
        print("Set PLACEDON_DATABASE_URL to a migrated scratch database.")
        return 2
    return asyncio.run(run(url))


if __name__ == "__main__":
    raise SystemExit(main())
