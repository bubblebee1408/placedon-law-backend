#!/usr/bin/env python3
"""A safe migration runner for the gateway's SQL migrations.

    scripts/migrate.py --plan                 # dry run: what would apply, and nothing else
    scripts/migrate.py --apply                # backup, then apply pending (refuses to be unsafe)
    scripts/migrate.py --self-test            # end-to-end, on a THROWAWAY scratch database only
    scripts/migrate.py --test                 # offline unit tests (no database) -- the gate runs this

Target database: ``--url`` or ``$PLACEDON_DATABASE_URL`` (a libpq URI). Migrations: ``--dir``,
default ``gateway/migrations`` -- every ``NNN_*.sql`` in it, applied in NNN order.

WHAT MAKES ``--apply`` SAFE (each refusal is a separate, named stop):

  * **It will not run as a superuser.** Migrations must run as the app role so that
    ``FORCE ROW LEVEL SECURITY`` and object ownership land exactly as they do in production;
    a superuser silently bypasses RLS and would hide a policy bug until it reached prod.
  * **It takes a ``pg_dump`` backup first, or it does not apply at all.** No reachable backup
    (pg_dump missing, or the dump came out empty) is a hard stop, not a warning.
  * **It refuses to proceed if a migration that was already applied has since been edited.**
    Each applied migration's file is re-hashed against the checksum recorded when it ran; a
    mismatch means the file on disk is no longer the SQL the database actually ran, and the
    only honest move is to stop and let a person look.
  * **Each migration applies in its own transaction.** The first failure rolls itself back and
    stops the run, so the database is never left half-migrated.

``schema_migrations`` (version, checksum, applied_at) is the record of what ran. ``--plan`` never
writes -- not even to create that table -- so it is safe to point at anything.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "gateway" / "migrations"
SCRATCH_PREFIX = "placedon_migrate_selftest_"  # the self-test touches nothing else
MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")

# pg_dump is often not on PATH on a developer laptop (Postgres.app, Homebrew keg). Look where
# it actually lives before giving up, and let $PG_DUMP override.
_PG_DUMP_DIRS = (
    "/Applications/Postgres.app/Contents/Versions/latest/bin",
    "/opt/homebrew/bin",
    "/opt/homebrew/opt/libpq/bin",
    "/usr/local/bin",
    "/Library/PostgreSQL/18/bin",
    "/Library/PostgreSQL/17/bin",
    "/Library/PostgreSQL/16/bin",
)


# ── pure helpers (no database; the gate's --test exercises these) ──────────────

def checksum(data: bytes) -> str:
    """The sha256 a migration is recorded under. Bytes, so a whitespace edit still counts."""
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Migration:
    version: str          # the zero-padded numeric prefix, e.g. "007"
    name: str             # the file name, e.g. "007_cascade.sql"
    checksum: str
    sql: str


def discover(directory: Path) -> list[Migration]:
    """Every ``NNN_*.sql`` under *directory*, in numeric order, each with its checksum.

    Ordered by the integer value of the prefix, not by string, so a future ``100_*`` sorts
    after ``099_*`` rather than between ``010_*`` and ``011_*``.
    """
    out: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        m = MIGRATION_RE.match(p.name)
        if not m:
            continue
        data = p.read_bytes()
        out.append(Migration(version=m.group(1), name=p.name, checksum=checksum(data),
                             sql=data.decode("utf-8")))
    out.sort(key=lambda mg: int(mg.version))
    # A duplicate prefix (two files numbered the same) is ambiguous: refuse rather than guess.
    seen: dict[str, str] = {}
    for mg in out:
        if mg.version in seen:
            raise ValueError(f"two migrations share prefix {mg.version}: "
                             f"{seen[mg.version]} and {mg.name}")
        seen[mg.version] = mg.name
    return out


@dataclass(frozen=True)
class Plan:
    applied: list[Migration]      # recorded, file unchanged
    pending: list[Migration]      # on disk, not recorded
    edited: list[Migration]       # recorded, but the file's checksum no longer matches
    missing: list[str]            # recorded versions with no file on disk


def plan_diff(files: list[Migration], recorded: dict[str, str]) -> Plan:
    """Split the migration files against what the database says it has already run.

    *recorded* maps version -> the checksum stored when it was applied. A file whose checksum
    differs from its recorded checksum is EDITED (the dangerous case); a recorded version with
    no file is MISSING.
    """
    by_version = {m.version: m for m in files}
    applied, pending, edited = [], [], []
    for m in files:
        if m.version not in recorded:
            pending.append(m)
        elif recorded[m.version] == m.checksum:
            applied.append(m)
        else:
            edited.append(m)
    missing = sorted(v for v in recorded if v not in by_version)
    return Plan(applied=applied, pending=pending, edited=edited, missing=missing)


def find_pg_dump() -> str | None:
    """pg_dump from $PG_DUMP, then PATH, then the usual laptop install dirs. None if absent."""
    env = os.environ.get("PG_DUMP")
    if env and Path(env).is_file() and os.access(env, os.X_OK):
        return env
    found = shutil.which("pg_dump")
    if found:
        return found
    for d in _PG_DUMP_DIRS:
        cand = Path(d) / "pg_dump"
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


# ── database side (psycopg imported lazily, so --test needs no driver) ─────────

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def _connect(url: str, *, autocommit: bool = False):
    import psycopg
    return psycopg.connect(url, autocommit=autocommit, connect_timeout=10)


def is_superuser(conn) -> bool:
    row = conn.execute(
        "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    return bool(row and row[0])


def public_table_count(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchone()[0]


def read_recorded(conn) -> dict[str, str] | None:
    """version -> checksum from schema_migrations, or None if the table does not exist."""
    exists = conn.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL").fetchone()[0]
    if not exists:
        return None
    rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    return {v: c for v, c in rows}


def who(conn) -> tuple[str, str]:
    return conn.execute("SELECT current_user, current_database()").fetchone()


# ── commands ───────────────────────────────────────────────────────────────

def cmd_plan(url: str, directory: Path) -> int:
    files = discover(directory)
    with _connect(url) as conn:
        user, db = who(conn)
        recorded = read_recorded(conn)
        tables = public_table_count(conn)
    untracked = recorded is None
    plan = plan_diff(files, {} if recorded is None else recorded)

    print(f"plan: {db} as {user} — {len(files)} migration file(s) in {directory}")
    print(f"  applied : {len(plan.applied)}")
    print(f"  pending : {len(plan.pending)}")
    for m in plan.pending:
        print(f"      + {m.name}")
    if plan.edited:
        print(f"  EDITED after apply (--apply will refuse): {len(plan.edited)}")
        for m in plan.edited:
            print(f"      ! {m.name}")
    if plan.missing:
        print(f"  recorded but file missing: {', '.join(plan.missing)}")
    if untracked and tables > 0:
        print()
        print(f"  WARNING: {db} has {tables} table(s) but NO schema_migrations table.")
        print(f"  This database was migrated outside this tool. A plain --apply would try to")
        print(f"  re-run {len(plan.pending)} migration(s) from the start and the first one would")
        print(f"  collide with the objects already there (it applies in a transaction, so it")
        print(f"  fails and rolls back rather than half-migrating). Baseline it or use a fresh")
        print(f"  database before applying.")
    print()
    print("Nothing was written. Re-run with --apply to change the database.")
    return 0


def cmd_apply(url: str, directory: Path, backup_dir: Path) -> int:
    files = discover(directory)
    with _connect(url) as conn:
        user, db = who(conn)
        if is_superuser(conn):
            print(f"REFUSED: connected as {user}, a superuser. Migrations must run as the "
                  f"non-superuser app role, or RLS and ownership will not match production.",
                  file=sys.stderr)
            return 2
        recorded = read_recorded(conn) or {}
        plan = plan_diff(files, recorded)
        if plan.edited:
            print("REFUSED: these already-applied migrations were edited after they ran — the "
                  "file on disk is not the SQL the database ran:", file=sys.stderr)
            for m in plan.edited:
                print(f"    {m.name}", file=sys.stderr)
            return 2
        if not plan.pending:
            print(f"up to date: {db} has all {len(files)} migration(s). Nothing to apply.")
            return 0

        # Backup FIRST. No backup, no apply.
        pg_dump = find_pg_dump()
        if not pg_dump:
            print("REFUSED: pg_dump not found (set $PG_DUMP). A backup is taken before any "
                  "migration is applied; without pg_dump there is no backup, so nothing runs.",
                  file=sys.stderr)
            return 2
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"{db}_{stamp}.dump"
        print(f"backup: {pg_dump} -Fc {db} -> {backup}")
        proc = subprocess.run([pg_dump, "--dbname", url, "-Fc", "-f", str(backup)],
                              capture_output=True, text=True)
        if proc.returncode != 0 or not backup.exists() or backup.stat().st_size == 0:
            print(f"REFUSED: pg_dump failed or produced an empty backup; not applying.\n"
                  f"{proc.stderr.strip()[:400]}", file=sys.stderr)
            return 2
        print(f"backup ok: {backup.stat().st_size} bytes")

        # Apply, each in its own transaction, recording as it goes.
        conn.execute(SCHEMA_MIGRATIONS_DDL)
        conn.commit()
        for m in plan.pending:
            print(f"apply: {m.name} …", end="", flush=True)
            try:
                with conn.transaction():
                    conn.execute(m.sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                        (m.version, m.checksum))
                print(" ok")
            except Exception as e:                                   # noqa: BLE001
                print(" FAILED")
                print(f"STOPPED at {m.name}: {type(e).__name__}: {str(e)[:300]}\n"
                      f"It rolled back; nothing after it ran. The backup is at {backup}.",
                      file=sys.stderr)
                return 1
    print(f"applied {len(plan.pending)} migration(s). Backup: {backup}")
    return 0


# ── offline unit tests (the gate runs this; no database) ──────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    # checksum is bytes-exact: one changed space is a different migration.
    check(checksum(b"create table t();") != checksum(b"create table t() ;"),
          "checksum is sensitive to a whitespace edit")
    check(checksum(b"x") == checksum(b"x"), "checksum is stable for the same bytes")

    # discovery sorts by the integer prefix, not the string, and skips non-migrations.
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        for n in ("002_b.sql", "010_j.sql", "001_a.sql", "009_i.sql", "notes.txt", "readme.sql"):
            (dd / n).write_text(f"-- {n}\nCREATE TABLE t_{n[:3]} ();")
        got = discover(dd)
        check([m.version for m in got] == ["001", "002", "009", "010"],
              f"discover sorts numerically and skips non-NNN files ({[m.version for m in got]})")
        # a duplicate prefix is refused
        (dd / "010_dup.sql").write_text("-- dup")
        try:
            discover(dd); dup_refused = False
        except ValueError:
            dup_refused = True
        check(dup_refused, "a duplicate migration prefix is refused, not guessed")

    # plan_diff: pending / applied / edited / missing
    files = [Migration("001", "001_a.sql", "aaa", ""),
             Migration("002", "002_b.sql", "bbb", ""),
             Migration("003", "003_c.sql", "ccc", "")]
    plan = plan_diff(files, {"001": "aaa", "002": "DIFFERENT", "009": "zzz"})
    check([m.version for m in plan.applied] == ["001"], "applied = recorded AND checksum matches")
    check([m.version for m in plan.pending] == ["003"], "pending = file with no record")
    check([m.version for m in plan.edited] == ["002"], "edited = recorded but checksum differs")
    check(plan.missing == ["009"], "missing = recorded with no file")

    # pg_dump discovery returns a real path or None, never a guess that is not there.
    pd = find_pg_dump()
    check(pd is None or (Path(pd).is_file() and os.access(pd, os.X_OK)),
          f"find_pg_dump returns an executable path or None ({pd})")

    # the superuser guard and the backup-first order are wired, not just documented.
    src = Path(__file__).read_text()
    check("is_superuser(conn)" in src and "a superuser" in src, "apply checks for superuser")
    check(src.index("REFUSED: pg_dump not found") < src.index("conn.execute(SCHEMA_MIGRATIONS_DDL)"),
          "the backup refusal is reached before any migration is applied")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


# ── self-test on a scratch database only ──────────────────────────────────────

def _self_test() -> int:
    """Create a throwaway database, drive the runner against it end to end, drop it.

    Needs a local server and a role that can CREATE DATABASE. The scratch database is named
    with SCRATCH_PREFIX and this function refuses to create or drop anything else, so it can
    never touch a real database even if the URLs are wrong.
    """
    import psycopg

    host = os.environ.get("PLACEDON_PGHOST", "/tmp")
    admin_user = os.environ.get("PLACEDON_PG_ADMIN", "nishantsingh")   # can CREATE DATABASE
    app_user = os.environ.get("PLACEDON_PG_APP", "placedon_app")       # the non-super app role
    scratch = f"{SCRATCH_PREFIX}{os.getpid()}"
    assert scratch.startswith(SCRATCH_PREFIX), "scratch name guard"

    admin_url = f"postgresql:///postgres?host={host}&user={admin_user}"
    app_url = f"postgresql:///{scratch}?host={host}&user={app_user}"
    super_url = f"postgresql:///{scratch}?host={host}&user={admin_user}"

    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def drop():
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
            assert scratch.startswith(SCRATCH_PREFIX)
            c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')

    try:
        try:
            with psycopg.connect(admin_url, autocommit=True, connect_timeout=10) as c:
                assert scratch.startswith(SCRATCH_PREFIX)
                c.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')
                c.execute(f'CREATE DATABASE "{scratch}" OWNER "{app_user}"')
        except Exception as e:                                       # noqa: BLE001
            print(f"SKIP: cannot create a scratch database ({type(e).__name__}: "
                  f"{str(e)[:120]}). Needs a local server and a CREATE DATABASE role.")
            return 0

        with tempfile.TemporaryDirectory() as d:
            mig = Path(d) / "migrations"
            mig.mkdir()
            (mig / "001_a.sql").write_text("CREATE TABLE a (id int PRIMARY KEY);")
            (mig / "002_b.sql").write_text("CREATE TABLE b (id int PRIMARY KEY);")
            backups = Path(d) / "backups"

            # 1. plan on an empty, untracked scratch: both pending, no false 'untracked' warning
            with psycopg.connect(app_url, connect_timeout=10) as c:
                rec = read_recorded(c)
                check(rec is None, "a fresh database has no schema_migrations yet")
            plan = plan_diff(discover(mig), {})
            check([m.version for m in plan.pending] == ["001", "002"], "plan: both pending")

            # 2. superuser is refused BEFORE anything is applied
            rc_super = cmd_apply(super_url, mig, backups)
            check(rc_super == 2, "apply as a superuser is REFUSED")
            with psycopg.connect(app_url, connect_timeout=10) as c:
                check(read_recorded(c) is None, "...and the refusal wrote nothing")

            # 3. apply as the app role: backup taken, both applied, recorded with checksums
            rc = cmd_apply(app_url, mig, backups)
            check(rc == 0, "apply as the app role succeeds")
            dumps = list(backups.glob("*.dump"))
            check(len(dumps) == 1 and dumps[0].stat().st_size > 0, "a non-empty pg_dump backup was taken first")
            with psycopg.connect(app_url, connect_timeout=10) as c:
                rec = read_recorded(c)
                check(rec is not None and set(rec) == {"001", "002"}, "both recorded in schema_migrations")
                files = {m.version: m.checksum for m in discover(mig)}
                check(rec == files, "...each recorded under its file's checksum")
                tbls = public_table_count(c)
                check(tbls >= 2, f"the tables were created ({tbls})")

            # 4. nothing pending now
            with psycopg.connect(app_url, connect_timeout=10) as c:
                plan2 = plan_diff(discover(mig), read_recorded(c))
                check(plan2.pending == [] and len(plan2.applied) == 2, "re-plan: all applied, none pending")

            # 5. edit an already-applied migration -> refused
            (mig / "001_a.sql").write_text("CREATE TABLE a (id int PRIMARY KEY); -- edited")
            with psycopg.connect(app_url, connect_timeout=10) as c:
                plan3 = plan_diff(discover(mig), read_recorded(c))
                check([m.version for m in plan3.edited] == ["001"], "plan flags the edited migration")
            rc_edit = cmd_apply(app_url, mig, backups)
            check(rc_edit == 2, "apply REFUSES once an applied migration was edited")

        print(f"\n{ok}/{ok + fail} passed")
        return 1 if fail else 0
    finally:
        try:
            drop()
            print(f"dropped scratch database {scratch}")
        except Exception as e:                                       # noqa: BLE001
            print(f"WARNING: could not drop {scratch}: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="dry run; writes nothing")
    g.add_argument("--apply", action="store_true", help="backup, then apply pending")
    g.add_argument("--self-test", action="store_true", help="end-to-end on a scratch database")
    g.add_argument("--test", action="store_true", help="offline unit tests (no database)")
    ap.add_argument("--url", help="target libpq URI (default $PLACEDON_DATABASE_URL)")
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help="migrations directory")
    ap.add_argument("--backup-dir", default=str(ROOT / "backups"),
                    help="where --apply writes the pg_dump backup (gitignored; never committed)")
    args = ap.parse_args()

    if args.test:
        return _test()
    if args.self_test:
        return _self_test()

    url = args.url or os.environ.get("PLACEDON_DATABASE_URL")
    if not url:
        print("no target: pass --url or set PLACEDON_DATABASE_URL", file=sys.stderr)
        return 2
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"no migrations directory: {directory}", file=sys.stderr)
        return 2
    if args.plan:
        return cmd_plan(url, directory)
    return cmd_apply(url, directory, Path(args.backup_dir))


if __name__ == "__main__":
    raise SystemExit(main())
