"""Choosing a backend (`database_url`, `select`) and `AuthLookup`, the cross-tenant sign-in reads."""
from __future__ import annotations

import os

from gateway.store.core import Backend, MEMORY, POSTGRES, StoreError, URL_ENV
from gateway.store.memory import MemoryBackend
from gateway.store.postgres import PostgresBackend


def database_url() -> str | None:
    """The configured URL, or None. Read through checker.env so .env is honoured."""
    try:
        from checker.env import load
        load()
    except Exception:                                            # noqa: BLE001
        pass
    return os.getenv(URL_ENV) or None


def select(*, tenant_id: str | None = None, url: str | None = None) -> Backend:
    """Postgres when a URL is configured, memory otherwise. The ONLY selection point.

    A URL that is set but unusable is an ERROR, never a silent fall back to memory: an
    operator who configured a database and got an in-memory store would be told everything
    is fine while nothing persists and no policy isolates anyone.
    """
    url = url if url is not None else database_url()
    if not url:
        return MemoryBackend(tenant_id=tenant_id or MemoryBackend().tenant_id)
    if not tenant_id:
        raise StoreError(f"{URL_ENV} is set but no tenant was given; a Postgres backend "
                         f"cannot be built without one")
    return PostgresBackend(url, tenant_id=tenant_id)


class AuthLookup:
    """The cross-tenant reads authentication needs, and the tenant-blind login_attempts
    ledger. NEVER bound to one tenant -- unlike every Backend above, which refuses to be
    constructed without one.

    DECISION_ACCOUNTS.md Decision 4 names two cross-tenant reads of tenant data
    (auth_find_login, auth_resolve_session); building invites.accept surfaced a third,
    `find_invite`, with the identical shape keyed by token instead of email. See the
    top-of-file note in gateway/migrations/026_accounts.sql for why, and the deviation it
    records. `record_attempt`/`recent_failures` are not cross-tenant reads of tenant data
    at all -- login_attempts holds no tenant column to begin with.
    """

    def __init__(self, *, db_url: str | None = None, memory: "MemoryBackend | None" = None):
        if bool(db_url) == bool(memory):
            raise StoreError(
                "AuthLookup needs EXACTLY one of db_url or memory -- it is never bound to "
                "a tenant, so it cannot also be bound to neither or both a backend")
        self._url = db_url
        self._memory = memory

    @property
    def kind(self) -> str:
        return POSTGRES if self._url else MEMORY

    def _pg(self):
        import psycopg
        return psycopg.connect(self._url, autocommit=True)

    def find_logins(self, email: str) -> list[dict]:
        """Every actor whose email matches (case-insensitively) and who HAS a password.

        More than one row is the ambiguous-email case (Decision 7): auth.login must
        refuse rather than guess a tenant.
        """
        want = str(email or "").strip().lower()
        if not want:
            return []
        if self._memory is not None:
            # The shared dict has no tenant filter to begin with (see backend_for in
            # gateway/app.py), so this already searches every tenant that has used this
            # process's memory backend -- exactly the cross-tenant behaviour the real
            # function provides, for free, because memory never had isolation to bypass.
            # Individual rows carry NO tenant_id in MemoryBackend (isolation there is one
            # backend instance pinned to one tenant, not a per-row column) -- so the
            # backend's OWN current tenant is what every row found in it belongs to.
            tenant_id = self._memory.tenant_id
            return [{"actor_id": row["actor_id"], "tenant_id": tenant_id,
                     "password_hash": row["password_hash"],
                     "disabled_at": row.get("disabled_at")}
                    for row in self._memory.actors.values()
                    if row.get("password_hash")
                    and str(row.get("email") or "").lower() == want]
        with self._pg() as c:
            rows = c.execute("SELECT actor_id, tenant_id, password_hash, disabled_at "
                             "FROM auth_find_login(%s)", (want,)).fetchall()
        return [{"actor_id": str(r[0]), "tenant_id": str(r[1]), "password_hash": r[2],
                 "disabled_at": r[3].isoformat() if r[3] else None} for r in rows]

    def resolve_session(self, token_hash: str) -> dict | None:
        """At most one row: actor_id, tenant_id, role, expires_at, revoked_at, disabled_at.

        `role` and `disabled_at` are read from `actors` LIVE (joined inside the SQL
        function on Postgres; read fresh here for memory), never cached on the session.
        """
        th = str(token_hash or "")
        if not th:
            return None
        if self._memory is not None:
            row = next((s for s in self._memory.sessions.values()
                       if s.get("token_hash") == th), None)
            if row is None:
                return None
            actor = self._memory.actors.get(row["actor_id"]) or {}
            return {"actor_id": row["actor_id"], "tenant_id": self._memory.tenant_id,
                    "role": actor.get("role") or "viewer",
                    "expires_at": row["expires_at"], "revoked_at": row.get("revoked_at"),
                    "disabled_at": actor.get("disabled_at")}
        with self._pg() as c:
            r = c.execute("SELECT actor_id, tenant_id, role, expires_at, revoked_at, "
                          "disabled_at FROM auth_resolve_session(%s)", (th,)).fetchone()
        if r is None:
            return None
        return {"actor_id": str(r[0]), "tenant_id": str(r[1]), "role": r[2],
                "expires_at": r[3].isoformat(),
                "revoked_at": r[4].isoformat() if r[4] else None,
                "disabled_at": r[5].isoformat() if r[5] else None}

    def find_invite(self, token_hash: str) -> dict | None:
        """invite_id, tenant_id, email, role, expires_at, accepted_at -- or None.

        Never the token_hash: the caller already holds the raw token, which is strictly
        more than its hash.
        """
        th = str(token_hash or "")
        if not th:
            return None
        if self._memory is not None:
            row = next((i for i in self._memory.invites.values()
                       if i.get("token_hash") == th), None)
            if row is None:
                return None
            # No per-row tenant_id in MemoryBackend (see find_logins); the backend's own
            # current tenant is the invite's tenant.
            out = {k: row.get(k) for k in
                  ("invite_id", "email", "role", "expires_at", "accepted_at")}
            out["tenant_id"] = self._memory.tenant_id
            return out
        with self._pg() as c:
            r = c.execute("SELECT invite_id, tenant_id, email, role, expires_at, "
                          "accepted_at FROM invite_find_by_token(%s)", (th,)).fetchone()
        if r is None:
            return None
        return {"invite_id": str(r[0]), "tenant_id": str(r[1]), "email": r[2],
                "role": r[3], "expires_at": r[4].isoformat(),
                "accepted_at": r[5].isoformat() if r[5] else None}

    def record_attempt(self, *, email_hash: str, ip_hash: str, ok: bool) -> None:
        """Append-only, like the table it mirrors: nothing here is ever updated."""
        if self._memory is not None:
            import datetime as _dt
            self._memory.login_attempts.append(
                {"email_hash": email_hash, "ip_hash": ip_hash, "ok": bool(ok),
                 "at": _dt.datetime.now(_dt.timezone.utc)})
            return
        with self._pg() as c:
            c.execute("INSERT INTO login_attempts (email_hash, ip_hash, ok) "
                     "VALUES (%s,%s,%s)", (email_hash, ip_hash, bool(ok)))

    def recent_failures(self, *, email_hash: str, ip_hash: str, since) -> tuple[int, int]:
        """(failures for this email, failures for this IP), each counted at or after `since`.

        Two counts, not one OR-ed count, because the lockout holds them to different lines
        (gateway/accounts.py): an office behind one address must not inherit one person's
        per-email lockout.

        `since` is a timezone-aware `datetime`, never a formatted string: two different
        ISO-8601 renderings (microseconds present or not, 'Z' vs '+00:00') do not compare
        correctly as strings at a boundary a few seconds wide, which is exactly where a
        lockout window is evaluated.
        """
        if self._memory is not None:
            failed = [row for row in self._memory.login_attempts
                      if not row["ok"] and row["at"] >= since]
            return (sum(1 for row in failed if row["email_hash"] == email_hash),
                    sum(1 for row in failed if row["ip_hash"] == ip_hash))
        with self._pg() as c:
            r = c.execute(
                "SELECT count(*) FILTER (WHERE email_hash = %s), "
                "count(*) FILTER (WHERE ip_hash = %s) "
                "FROM login_attempts WHERE NOT ok AND at >= %s "
                "AND (email_hash = %s OR ip_hash = %s)",
                (email_hash, ip_hash, since, email_hash, ip_hash)).fetchone()
        return int(r[0]), int(r[1])
