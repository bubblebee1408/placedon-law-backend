#!/usr/bin/env python3
"""035: the shared spend ledger, on real Postgres as the app role.

Proves, on a THROWAWAY database migrated through 035 and connected as placedon_app
(NOSUPERUSER NOBYPASSRLS):
  * concurrent reservations from many threads, each with its own ledger object (as separate
    App Service instances would have), never take a cap past its limit: the global daily
    cap, a firm's daily share, and a user's daily cap;
  * one firm at its daily share is refused while another firm still reserves;
  * settle refunds the unused part of a hold, a repeated settle is not charged twice, and a
    settle with unknown usage commits the whole hold;
  * a hold made by one ledger object is claimed and settled by another;
  * a provider spend-cap flag recorded by one instance stops every instance.

    python3 scripts/spend_ledger_integration.py --run     # live, throwaway DB
    python3 scripts/spend_ledger_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database and refuses any other name.
"""
from __future__ import annotations

import os
import pathlib
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")
MIGRATIONS = ROOT / "gateway" / "migrations"
M035 = "035_model_spend.sql"
DAY = date(2026, 11, 2)


def _run() -> int:
    import psycopg
    from backend import budget as B
    from backend.budget_pg import PostgresBudget

    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    db = f"{PREFIX}spend035_{os.getpid()}"
    assert db.startswith(PREFIX), "scratch-name guard"
    url = f"postgresql:///{db}?host={HOST}&user={APP}"
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def ledger(firm=None, user=None):
        base = PostgresBudget(url, today=DAY)
        return base.attributed(firm, user) if firm else base

    def hold(firm, user, amount):
        return ledger(firm, user).reserve(input_tokens=0, max_tokens=0, amount_inr=amount)

    def counter(scope, period="day"):
        d = DAY if period == "day" else DAY.replace(day=1)
        with psycopg.connect(url) as c:
            row = c.execute("SELECT spent_inr FROM model_spend WHERE scope=%s AND period=%s "
                            "AND day=%s", (scope, period, d)).fetchone()
        return float(row[0]) if row else 0.0

    def race(calls):
        with ThreadPoolExecutor(16) as pool:
            return list(pool.map(lambda a: hold(*a), calls))

    try:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
                c.execute(f'CREATE DATABASE "{db}" OWNER "{APP}"')
            with psycopg.connect(url, autocommit=True, connect_timeout=10) as c:
                for p in sorted(MIGRATIONS.glob("[0-9]*.sql"), key=lambda p: int(p.name[:3])):
                    c.execute(p.read_text())
                bypass = c.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles "
                                   "WHERE rolname = current_user").fetchone()[0]
        except Exception as e:                                        # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0
        check(bypass is False, "connected as the app role, which cannot bypass RLS")

        # ── a firm's daily share under a race: more ₹1 holds than it allows, from as many people ──
        firm_a = str(uuid.uuid4())
        tries = int(B.TENANT_DAILY_CAP_INR) + 20
        got = race([(firm_a, str(uuid.uuid4()), 1.0) for _ in range(tries)])
        admitted = sum(r.id is not None for r in got)
        check(admitted == int(B.TENANT_DAILY_CAP_INR),
              f"{tries} concurrent ₹1 holds for one firm: {admitted} admitted, the firm's share "
              f"₹{B.TENANT_DAILY_CAP_INR} allows {int(B.TENANT_DAILY_CAP_INR)}")
        check(counter(f"tenant:{firm_a}") <= B.TENANT_DAILY_CAP_INR,
              f"...and the firm's day never passed its cap ({counter(f'tenant:{firm_a}')})")
        refused = [r for r in got if r.id is None]
        check(all(r.verdict.mode == "budget" for r in refused),
              "...and every refusal is a budget refusal, not a database error")
        firm_b = str(uuid.uuid4())
        check(hold(firm_b, str(uuid.uuid4()), 1.0).id is not None,
              "another firm still reserves while firm A is at its share")

        # ── the global daily cap under a race: many firms, ₹5 each ──
        got = race([(str(uuid.uuid4()), str(uuid.uuid4()), 5.0) for _ in range(40)])
        g = counter("global")
        check(g <= B.DAILY_CAP_INR, f"40 concurrent ₹5 holds across firms: the deployment's "
              f"day stays within ₹{B.DAILY_CAP_INR} ({g})")
        check(B.DAILY_CAP_INR - g < 5.0,
              f"...and it was filled, not refused early (₹{B.DAILY_CAP_INR - g:.2f} left)")
        check(counter("global", "month") <= B.MONTHLY_CAP_INR, "...and within the month")

        # A new day: settle and refund are checked on a clean slate.
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("DELETE FROM model_spend"); c.execute("DELETE FROM model_spend_holds")

        # ── a user's daily cap under a race ──
        firm_c, user = str(uuid.uuid4()), str(uuid.uuid4())
        with patch.object(B, "USER_DAILY_CAP_INR", 6.0):
            got = race([(firm_c, user, 1.0) for _ in range(20)])
            admitted = sum(r.id is not None for r in got)
            check(admitted == 6, f"20 concurrent ₹1 holds for one person with a ₹6 cap: "
                  f"{admitted} admitted")
            check(hold(firm_c, str(uuid.uuid4()), 1.0).id is not None,
                  "...while a colleague in the same firm still reserves")

        # ── settle refunds; a second settle is not charged twice ──
        firm_d, u = str(uuid.uuid4()), str(uuid.uuid4())
        r = hold(firm_d, u, 10.0)
        check(counter(f"tenant:{firm_d}") == 10.0, "a ₹10 hold counts ₹10 against the firm")
        v = ledger(firm_d, u).settle(r.id, 2.5)
        check(v.allowed and counter(f"tenant:{firm_d}") == 2.5 and counter(f"user:{u}") == 2.5,
              f"settling at ₹2.50 refunds ₹7.50 to the firm and the person "
              f"({counter(f'tenant:{firm_d}')}, {counter(f'user:{u}')})")
        ledger(firm_d, u).settle(r.id, 2.5)
        check(counter(f"tenant:{firm_d}") == 2.5, "a repeated settle is not charged twice")
        r2 = hold(firm_d, u, 4.0)
        ledger(firm_d, u).settle(r2.id, None)
        check(counter(f"tenant:{firm_d}") == 6.5,
              "a settle with unknown usage commits the whole hold")
        usage = ledger().usage(tenant_id=firm_d, user_id=u)
        check(usage["tenant"]["day_inr"] == 6.5 and usage["global"]["month_held_inr"] == 4.0,
              f"usage() reads the same figures ({usage['tenant']['day_inr']}, held "
              f"{usage['global']['month_held_inr']})")

        # ── a hold made on one instance is claimed and settled on another ──
        r3 = hold(firm_d, u, 1.0)
        other = ledger(firm_d, u)
        check(other.reservation_amount(r3.id) == 1.0, "another instance sees the live hold")
        check(other.claim_reservations((r3.id,), "run-1", 1.0) is True,
              "...claims it for one run")
        check(ledger(firm_d, u).claim_reservations((r3.id,), "run-2", 1.0) is False,
              "...and a second run cannot claim it too")
        other.settle(r3.id, 0.0, actual_calls=0)
        check(other.reservation_amount(r3.id) is None, "...and settles it")

        # ── the reservation is refused, and writes nothing, with no firm ──
        before = counter("global")
        check(PostgresBudget(url, today=DAY).attributed("", None).reserve(input_tokens=0, max_tokens=0, amount_inr=1.0).id is None
              and counter("global") == before, "an unattributed gateway hold writes nothing")

        # ── a provider spend cap recorded on one instance stops all ──
        ledger().record_provider_spend_cap()
        check(hold(str(uuid.uuid4()), str(uuid.uuid4()), 0.1).id is None,
              "a provider spend cap recorded once stops every instance")

        print(f"\n{ok}/{ok + fail} passed")
        return 1 if fail else 0
    finally:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                assert db.startswith(PREFIX)
                c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
            print(f"dropped {db}")
        except Exception as e:                                        # noqa: BLE001
            print(f"WARNING: could not drop {db}: {e}", file=sys.stderr)


def _test() -> int:
    """Offline: 035 is additive, global on purpose, and the reserve is one conditional upsert."""
    from backend import budget_pg
    sql = (MIGRATIONS / M035).read_text(encoding="utf-8")
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    for t in ("model_spend", "model_spend_holds"):
        check(f"CREATE TABLE IF NOT EXISTS {t} (" in body, f"035 creates {t}, idempotently")
        check(f"ALTER TABLE {t} FORCE  ROW LEVEL SECURITY;" in body
              and f"CREATE POLICY global_access ON {t} USING (true);" in body,
              f"...{t} is FORCE RLS with an explicit global policy, like login_attempts")
    check("tenant_id" not in body, "035 has no tenant_id column: it is not tenant-scoped")
    check("PRIMARY KEY (scope, period, day)" in body, "counters are keyed by scope and day")
    check(not any(w in body.upper() for w in ("DELETE ", "DROP TABLE", "TRUNCATE", "ALTER TABLE ACTORS")),
          "035 never deletes or edits existing data")
    take = " ".join(budget_pg._TAKE.split())
    check("ON CONFLICT (scope, period, day) DO UPDATE" in take
          and "WHERE (%(cap)s::numeric IS NULL OR model_spend.spent_inr + EXCLUDED.spent_inr "
              "<= %(cap)s::numeric)" in take and "RETURNING" in take,
          "a reservation is one conditional upsert per scope")
    order = budget_pg.scopes(DAY, "t", "u", "m")
    check(order == sorted(order, key=lambda r: r[:3]) and order[0][0] == "global",
          "scopes are taken in one fixed order, global first")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
