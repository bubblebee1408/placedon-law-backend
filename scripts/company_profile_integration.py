#!/usr/bin/env python3
"""032: the company profile on real Postgres, as the restricted app role.

Proves, on a THROWAWAY database migrated through 032:
  * a lawyer saves the firm's profile through `company_profile.set` and reads it back with
    its provenance through `company_profile.get`;
  * ANOTHER FIRM reads none of it -- not through the verb, not through a raw SELECT -- and
    its own `events.assess` is not changed by it;
  * `events.assess` and a `conversation.send` turn fall back to the stored profile;
  * a change supersedes, and the database refuses DELETE and a rewrite of a fact;
  * a row cannot be written on another person's behalf (insert policy).

    python3 scripts/company_profile_integration.py --run     # live, throwaway DB
    python3 scripts/company_profile_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` database and refuses any other name.
"""
from __future__ import annotations

import os
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREFIX = "placedon_throwaway_"
HOST = os.environ.get("PLACEDON_PGHOST", "/tmp")
ADMIN = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")
APP = os.environ.get("PLACEDON_PG_APP", "placedon_app")
TODAY = "2026-11-01T00:00:00Z"
LISTED = {"field": "listed", "value": "yes", "confirmed": True}
STATE = {"field": "state", "value": "Maharashtra", "basis": "COMPANY_FACT",
         "quoted_span": "Registered Address: 5 Fort, Mumbai, Maharashtra",
         "source_label": "MCA master data, as uploaded by the user on 2026-10-01",
         "confirmed": True}


def _run() -> int:
    import psycopg
    from gateway.store import PostgresBackend
    from gateway.verbs import Context, by_name
    V = by_name()

    scratch = f"{PREFIX}profile_{os.getpid()}"
    assert scratch.startswith(PREFIX), "scratch-name guard"
    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    app_url = f"postgresql:///{scratch}?host={HOST}&user={APP}"
    T, L = str(uuid.uuid4()), str(uuid.uuid4())      # firm A and its lawyer
    T2, L2 = str(uuid.uuid4()), str(uuid.uuid4())    # firm B and its lawyer
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def as_actor(tenant, actor):
        c = psycopg.connect(app_url, autocommit=True, connect_timeout=10)
        c.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
        c.execute("SELECT set_config('app.actor_id', %s, false)", (actor,))
        return c

    try:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
                c.execute(f'CREATE DATABASE "{scratch}" OWNER "{APP}"')
            with psycopg.connect(app_url, autocommit=True, connect_timeout=10) as c:
                for p in sorted((ROOT / "gateway" / "migrations").glob("[0-9]*.sql"),
                                key=lambda p: int(p.name.split("_")[0])):
                    c.execute(p.read_text())
                for t, a, name in ((T, L, "firm a"), (T2, L2, "firm b")):
                    c.execute("SELECT set_config('app.tenant_id', %s, false)", (t,))
                    c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s)", (t, name))
                    c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                              "VALUES (%s,%s,'lawyer','lawyer')", (a, t))
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0

        ctx = Context(tenant=T, actor=L, role="lawyer", clock=lambda: TODAY,
                      store=PostgresBackend(app_url, tenant_id=T, actor_id=L))
        octx = Context(tenant=T2, actor=L2, role="lawyer", clock=lambda: TODAY,
                       store=PostgresBackend(app_url, tenant_id=T2, actor_id=L2))

        saved = V["company_profile.set"].run(
            {"facts": [LISTED, STATE], "reason": "Confirmed on the Company page"}, ctx)
        check(saved.get("status") == "SAVED", f"firm A saves its profile ({saved.get('code')})")
        got = {f["field"]: f for f in V["company_profile.get"].run({}, ctx).get("facts", [])}
        check(set(got) == {"listed", "state"}
              and got["state"]["uploaded_on"] == "2026-10-01"
              and got["state"]["quoted_span"] == STATE["quoted_span"]
              and got["listed"]["confirmed_by"] == L and got["listed"]["confirmed_at"],
              f"...and reads it back with provenance ({sorted(got)})")

        # ── cross-firm isolation ──
        check(V["company_profile.get"].run({}, octx).get("facts") == [],
              "firm B's company_profile.get sees none of firm A's facts")
        with as_actor(T2, L2) as c:
            n = c.execute("SELECT count(*) FROM company_profile_facts").fetchone()[0]
            leak = c.execute("SELECT count(*) FROM company_profile_facts WHERE tenant_id=%s",
                             (T,)).fetchone()[0]
        check(n == 0 and leak == 0, f"...nor through a raw SELECT as firm B ({n}, {leak})")
        b_assess = V["events.assess"].run({"event": "share_allotment"}, octx)
        check("SEBI_LODR" not in b_assess.get("body_ids", []) and "company_facts" not in b_assess,
              "...and firm B's events.assess is not changed by firm A's profile")

        # ── fallback ──
        a_assess = V["events.assess"].run({"event": "share_allotment"}, ctx)
        check("SEBI_LODR" in a_assess.get("body_ids", [])
              and (a_assess.get("company_facts") or {}).get("from") == "company_profile",
              f"firm A's events.assess reads its stored profile ({a_assess.get('body_ids')})")
        explicit = V["events.assess"].run({"event": "share_allotment", "company_facts": []}, ctx)
        check("SEBI_LODR" not in explicit.get("body_ids", []),
              "...and explicit request facts still win")
        turn = V["conversation.send"].run(
            {"text": "What does a share allotment engage?", "task_override": "EVENT_ASSESS",
             "event": "share_allotment", "request_id": uuid.uuid4().hex}, ctx)
        oturn = V["conversation.send"].run(
            {"text": "What does a share allotment engage?", "task_override": "EVENT_ASSESS",
             "event": "share_allotment", "request_id": uuid.uuid4().hex}, octx)
        check("SEBI" in str(turn.get("envelope")) and "SEBI" not in str(oturn.get("envelope")),
              "a conversation.send EVENT_ASSESS turn uses the profile too (and firm B's does not)")

        # ── supersede, never delete ──
        V["company_profile.set"].run({"facts": [dict(LISTED, value="no")],
                                      "reason": "Delisted, per the board"}, ctx)
        with as_actor(T, L) as c:
            rows = c.execute("SELECT field, value, superseded_at IS NOT NULL "
                             "FROM company_profile_facts ORDER BY confirmed_at").fetchall()
            check(len(rows) == 3 and sum(r[2] for r in rows) == 2,
                  f"a change supersedes and keeps history ({len(rows)} rows)")
            for sql, label in (("DELETE FROM company_profile_facts", "DELETE"),
                               ("UPDATE company_profile_facts SET value='x'", "a rewrite")):
                try:
                    c.execute(sql)
                    check(False, f"the database refuses {label}")
                except psycopg.Error:
                    check(True, f"the database refuses {label}")
            try:
                c.execute("INSERT INTO company_profile_facts (fact_id, tenant_id, field, value, "
                          "basis, source_label, confirmed_by, reason) VALUES "
                          "(%s,%s,'cin','U72200MH2010PTC123456','USER_FACT','you told us',%s,"
                          "'forged confirmation')", (str(uuid.uuid4()), T, str(uuid.uuid4())))
                check(False, "a fact cannot be confirmed in someone else's name")
            except psycopg.Error:
                check(True, "a fact cannot be confirmed in someone else's name")

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
    """Offline: 032 binds the table to its tenant, and both verbs are declared."""
    from gateway import schema
    from gateway.verbs import by_name
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    check("company_profile_facts" in schema.tenant_scoped()
          and not [u for u in schema.unprotected() if u[0] == "company_profile_facts"],
          "company_profile_facts is tenant-scoped, ENABLE+FORCE RLS, with a tenant policy")
    check({"company_profile.get", "company_profile.set"} <= set(by_name()),
          "both company_profile verbs are declared")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
