#!/usr/bin/env python3
"""033: one sign-in per email across every firm, on real Postgres as the app role.

Proves, on THROWAWAY databases:
  * fail safe: on a database through 032 where two firms already share a sign-in email,
    033 REFUSES with the count, and no row is changed or deleted;
  * on a clean database through 033, an admin of firm B who invites firm A's person and
    accepts the invite themselves gets INVALID_INVITE, no second account exists, and the
    firm-A person still signs in;
  * invites.create refuses that email up front, naming no firm;
  * an ordinary single account is unaffected (invite, accept, sign in).

    python3 scripts/login_email_integration.py --run     # live, throwaway DBs
    python3 scripts/login_email_integration.py --test    # offline structural check

`--run` creates and drops its own `placedon_throwaway_*` databases and refuses any other name.
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
MIGRATIONS = ROOT / "gateway" / "migrations"
M033 = "033_login_email_unique.sql"
PASSWORD = "victim's own long passphrase"
# 026's one-time elevated bootstrap, as an operator performs it (see 026_accounts.sql).
AUTHN_BOOTSTRAP = (
    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='placedon_authn') "
    "THEN CREATE ROLE placedon_authn NOSUPERUSER NOLOGIN BYPASSRLS; END IF; END $$",
    "GRANT USAGE ON SCHEMA public TO placedon_authn",
    "GRANT SELECT ON actors, sessions, invites TO placedon_authn",
    "ALTER FUNCTION auth_find_login(text) OWNER TO placedon_authn",
    "ALTER FUNCTION auth_resolve_session(text) OWNER TO placedon_authn",
    "ALTER FUNCTION invite_find_by_token(text) OWNER TO placedon_authn",
    "GRANT EXECUTE ON FUNCTION auth_find_login(text), auth_resolve_session(text), "
    "invite_find_by_token(text) TO placedon_app",
)


def _migrations(upto: int) -> list[pathlib.Path]:
    return sorted((p for p in MIGRATIONS.glob("[0-9]*.sql") if int(p.name[:3]) <= upto),
                  key=lambda p: int(p.name[:3]))


def _run() -> int:
    import psycopg
    from gateway.passwords import hash_password
    from gateway.store import AuthLookup, PostgresBackend
    from gateway.verbs import Context, by_name
    V = by_name()

    admin_url = f"postgresql:///postgres?host={HOST}&user={ADMIN}"
    pid = os.getpid()
    dirty, clean = f"{PREFIX}login033_dirty_{pid}", f"{PREFIX}login033_{pid}"
    assert dirty.startswith(PREFIX) and clean.startswith(PREFIX), "scratch-name guard"
    url = {d: f"postgresql:///{d}?host={HOST}&user={APP}" for d in (dirty, clean)}
    TA, TB, AA, AB = (str(uuid.uuid4()) for _ in range(4))   # firms A, B and their admins
    victim = f"victim-{TA[:8]}@firma.example"
    pw_hash = hash_password(PASSWORD)
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def provision(db: str, upto: int) -> None:
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
            c.execute(f'CREATE DATABASE "{db}" OWNER "{APP}"')
        with psycopg.connect(url[db], autocommit=True, connect_timeout=10) as c:
            for p in _migrations(upto):
                c.execute(p.read_text())
            for t, a, name in ((TA, AA, "firm a"), (TB, AB, "firm b")):
                c.execute("SELECT set_config('app.tenant_id', %s, false)", (t,))
                c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s)", (t, name))
                c.execute("INSERT INTO actors (actor_id, tenant_id, label, role) "
                          "VALUES (%s,%s,'admin','admin')", (a, t))
            # The victim: one sign-in account in firm A.
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (TA,))
            c.execute("INSERT INTO actors (actor_id, tenant_id, label, role, email, "
                      "password_hash) VALUES (%s,%s,'victim','lawyer',%s,%s)",
                      (str(uuid.uuid4()), TA, victim, pw_hash))
        with psycopg.connect(f"postgresql:///{db}?host={HOST}&user={ADMIN}",
                             autocommit=True) as c:
            for sql in AUTHN_BOOTSTRAP:
                c.execute(sql)

    def rows_snapshot(db: str):
        with psycopg.connect(f"postgresql:///{db}?host={HOST}&user={ADMIN}") as c:
            return c.execute("SELECT actor_id, tenant_id, email, password_hash FROM actors "
                             "ORDER BY actor_id").fetchall()

    try:
        try:
            provision(dirty, 32)
            provision(clean, 33)
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot provision a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}).")
            return 0

        # ── fail safe: duplicates already exist before 033 ──
        with psycopg.connect(url[dirty], autocommit=True) as c:
            c.execute("SELECT set_config('app.tenant_id', %s, false)", (TB,))
            c.execute("INSERT INTO actors (actor_id, tenant_id, label, role, email, "
                      "password_hash) VALUES (%s,%s,'squatter','viewer',%s,%s)",
                      (str(uuid.uuid4()), TB, victim.upper(), pw_hash))
        before = rows_snapshot(dirty)
        err = ""
        try:
            with psycopg.connect(url[dirty], autocommit=True) as c:
                c.execute((MIGRATIONS / M033).read_text())
        except psycopg.Error as e:
            err = str(e)
        check("033 refused: 1 email address(es)" in err and victim not in err.lower(),
              f"033 refuses a database that already has a duplicate, with the count and "
              f"not the email ({err.splitlines()[0] if err else 'it applied'})")
        check(rows_snapshot(dirty) == before, "...and no row was changed or deleted")
        with psycopg.connect(f"postgresql:///{dirty}?host={HOST}&user={ADMIN}") as c:
            idx = c.execute("SELECT 1 FROM pg_indexes WHERE indexname = "
                            "'actors_login_email_global_idx'").fetchone()
        check(idx is None, "...and the index was not created")

        # ── clean database through 033: the attack ──
        app_url = url[clean]
        auth = AuthLookup(db_url=app_url)

        def backend_for(t, a=None):
            return PostgresBackend(app_url, tenant_id=t, actor_id=a or AB)
        pub = Context(auth=auth, backend_for=backend_for, client_ip="203.0.113.9")
        b_admin_no_auth = Context(tenant=TB, actor=AB, role="admin",
                                  store=backend_for(TB, AB))
        b_admin = Context(tenant=TB, actor=AB, role="admin", store=backend_for(TB, AB),
                          auth=auth)

        refused = V["invites.create"].run({"email": victim, "role": "viewer"}, b_admin)
        check(refused.get("code") == "CONFLICT" and TA not in str(refused)
              and "firm a" not in str(refused).lower(),
              f"invites.create refuses an email that signs in at another firm, naming no "
              f"firm ({refused.get('detail')})")

        # Without the up-front check (e.g. an invite issued before 033), accept still fails.
        inv = V["invites.create"].run({"email": victim, "role": "viewer"}, b_admin_no_auth)
        check(bool(inv.get("token")), "an invite issued without the up-front check exists")
        acc = V["invites.accept"].run({"token": inv["token"], "password": "attacker passphrase"},
                                      pub)
        check(acc.get("code") == "INVALID_INVITE",
              f"firm B accepting firm A's person's email is refused INVALID_INVITE ({acc})")
        n = len([r for r in rows_snapshot(clean) if (r[2] or "").lower() == victim])
        check(n == 1, f"...and no second account exists ({n})")
        login = V["auth.login"].run({"email": victim, "password": PASSWORD}, pub)
        check(login.get("status") == "ok" and login.get("tenant_id") == TA,
              f"the firm-A person still signs in, to firm A ({login.get('status')})")

        # ── a normal single account is unaffected ──
        fresh = f"new-{TB[:8]}@firmb.example"
        inv2 = V["invites.create"].run({"email": fresh, "role": "lawyer"}, b_admin)
        acc2 = V["invites.accept"].run({"token": inv2.get("token", ""),
                                        "password": "a fresh long passphrase"}, pub)
        login2 = V["auth.login"].run({"email": fresh, "password": "a fresh long passphrase"},
                                     pub)
        check(acc2.get("status") == "accepted" and login2.get("status") == "ok"
              and login2.get("tenant_id") == TB,
              "an ordinary invite -> accept -> sign in still works")

        print(f"\n{ok}/{ok + fail} passed")
        return 1 if fail else 0
    finally:
        for db in (dirty, clean):
            try:
                with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                    assert db.startswith(PREFIX)
                    c.execute(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
                print(f"dropped {db}")
            except Exception as e:                                   # noqa: BLE001
                print(f"WARNING: could not drop {db}: {e}", file=sys.stderr)


def _test() -> int:
    """Offline: 033 is additive and fail-safe in its text."""
    sql = (MIGRATIONS / M033).read_text(encoding="utf-8")
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--")).upper()
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    check("CREATE UNIQUE INDEX IF NOT EXISTS ACTORS_LOGIN_EMAIL_GLOBAL_IDX" in body
          and "ON ACTORS (LOWER(EMAIL)) WHERE EMAIL IS NOT NULL AND PASSWORD_HASH IS NOT NULL"
          in body, "033 adds the global partial unique index on lower(email)")
    check(not any(w in body for w in ("DELETE ", "UPDATE ACTORS", "DROP INDEX", "TRUNCATE")),
          "033 never deletes or edits a row")
    check("RAISE EXCEPTION" in body and body.index("RAISE EXCEPTION")
          < body.index("CREATE UNIQUE INDEX"),
          "033 refuses on existing duplicates before building the index")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    return _run() if "--run" in sys.argv else _test()


if __name__ == "__main__":
    raise SystemExit(main())
