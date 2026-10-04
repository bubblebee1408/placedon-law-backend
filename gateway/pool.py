#!/usr/bin/env python3
"""A bounded Postgres connection pool. Every checkout sets the tenant, with no exception.

A1. `PostgresQueue._conn`, `PostgresBackend._conn` and the worker each call
`psycopg.connect` per operation, so a busy API opens and closes a connection per request and a
flood of them can exhaust the server's `max_connections` -- at which point nothing connects,
including the worker that would drain the queue.

## The hard cap is the point, and it refuses rather than exceeding

`max_size` is a ceiling, not a target. When every connection is checked out, a caller WAITS up
to `acquire_timeout` and is then REFUSED. It does not open connection `max_size + 1`: a pool
that quietly exceeds its cap under load is the thing this is for, and the API and the workers
have separate caps (`API_MAX_SIZE`, `WORKER_MAX_SIZE`) so a bulk ingest cannot take every slot
the API needs to answer anyone.

## ⚠ Every checkout sets app.tenant_id. This is a tenant-isolation property, not a convenience.

`set_config('app.tenant_id', <id>, false)` is SESSION-scoped -- `is_local=false` -- so it
persists for the connection's life. Measured on PostgreSQL 18.6, 04-10-2026: set it once and
every later statement on that connection still reads it back. So a pooled connection handed to
another tenant WITHOUT a reset is a cross-tenant read, because the row-level-security policies
compare against exactly that value.

That is why `connection()` takes `tenant_id` as a required argument and sets it on every
checkout, before the caller gets the connection, every time -- not "if it changed". There is no
code path that yields a connection without setting it, and `_test()` asserts that by handing
one tenant's returned connection to another and reading the setting back.

## What this does NOT do, stated rather than assumed

No background reconnection, no idle eviction beyond `max_idle_seconds`, no prepared-statement
cache, no async. A connection found closed or unusable on checkout is discarded and replaced,
which covers a server restart at the cost of one refused acquire. `psycopg_pool` does all of
the above properly and is the upgrade path; it is not used here because it is a new dependency
and because the tenant contract above is the part that matters, and owning the checkout is how
that gets tested.

Run: PYTHONPATH=. python3 gateway/pool.py --test
"""
from __future__ import annotations

import queue as _queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

__all__ = ["Pool", "PoolExhausted", "API_MAX_SIZE", "WORKER_MAX_SIZE",
           "ACQUIRE_TIMEOUT_SECONDS", "MAX_IDLE_SECONDS"]

# Separate caps so bulk work cannot take every slot the API needs. Their sum is what the
# server must be able to serve; a deployment that raises either must raise max_connections.
API_MAX_SIZE = 10
WORKER_MAX_SIZE = 4

# Long enough to ride out a slow query holding a connection; short enough that a request fails
# while someone is still watching rather than hanging.
ACQUIRE_TIMEOUT_SECONDS = 5.0

# An idle connection older than this is closed on checkout rather than reused, so a pool does
# not hold sockets open across a quiet night.
MAX_IDLE_SECONDS = 300.0


class PoolExhausted(RuntimeError):
    """Every connection is in use and the wait expired. The cap held, which is its job."""


@dataclass
class _Held:
    conn: object
    idle_since: float


@dataclass
class Pool:
    url: str
    max_size: int = API_MAX_SIZE
    acquire_timeout: float = ACQUIRE_TIMEOUT_SECONDS
    max_idle: float = MAX_IDLE_SECONDS
    name: str = "api"
    # Injected so the suite can run without a server and without a clock.
    connect: object = None
    clock: object = time.monotonic

    _idle: _queue.LifoQueue = field(default_factory=_queue.LifoQueue)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _open: int = 0
    _peak: int = 0
    _refusals: int = 0

    def _new(self):
        if self.connect is not None:
            return self.connect(self.url)
        import psycopg
        return psycopg.connect(self.url, autocommit=True)

    @staticmethod
    def _dead(conn) -> bool:
        return bool(getattr(conn, "closed", False))

    def _take(self):
        """An open connection, or None if the cap is reached and none is idle."""
        deadline = float(self.clock()) + self.acquire_timeout
        while True:
            try:
                held = self._idle.get_nowait()
            except _queue.Empty:
                held = None
            if held is not None:
                aged = float(self.clock()) - held.idle_since > self.max_idle
                if self._dead(held.conn) or aged:
                    self._close(held.conn)
                    continue                  # discard and look again
                return held.conn
            with self._lock:
                if self._open < self.max_size:
                    self._open += 1
                    self._peak = max(self._peak, self._open)
                    making = True
                else:
                    making = False
            if making:
                try:
                    return self._new()
                except Exception:
                    with self._lock:
                        self._open -= 1
                    raise
            if float(self.clock()) >= deadline:
                return None
            time.sleep(0.01)

    def _close(self, conn) -> None:
        try:
            conn.close()
        except Exception:                     # noqa: BLE001 -- a close that fails is closed
            pass
        with self._lock:
            self._open = max(0, self._open - 1)

    @contextmanager
    def connection(self, *, tenant_id: str):
        """A connection with `app.tenant_id` set to `tenant_id`. Always set, every checkout.

        `tenant_id` is required and is applied before the caller sees the connection. See the
        module docstring: the setting is session-scoped and survives on a pooled connection,
        so skipping it would hand this caller the PREVIOUS tenant's identity and every policy
        compares against it.
        """
        if not str(tenant_id or "").strip():
            raise ValueError(
                "a pooled connection needs a tenant_id. A connection with none set sees no "
                "rows under the policies -- and a connection with the PREVIOUS caller's id "
                "still set sees theirs, which is worse")
        conn = self._take()
        if conn is None:
            with self._lock:
                self._refusals += 1
            raise PoolExhausted(
                f"the {self.name} pool's {self.max_size} connections are all in use and the "
                f"{self.acquire_timeout}s wait expired. No connection was opened beyond the "
                f"cap, which is what the cap is for")
        try:
            conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant_id),))
            yield conn
        except Exception:
            # A connection whose transaction state is unknown is not returned to the pool.
            self._close(conn)
            raise
        else:
            self._idle.put(_Held(conn, float(self.clock())))

    def stats(self) -> dict:
        return {"name": self.name, "max_size": self.max_size, "open": self._open,
                "idle": self._idle.qsize(), "peak": self._peak,
                "refusals": self._refusals}

    def close(self) -> None:
        while True:
            try:
                self._close(self._idle.get_nowait().conn)
            except _queue.Empty:
                return


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("pool")

    class FakeConn:
        """Records what was executed on it, and remembers the tenant like a real session."""
        def __init__(self, url):
            self.url = url
            self.closed = False
            self.tenant = None
            self.sets = 0

        def execute(self, sql, params=()):
            if "app.tenant_id" in sql:
                self.tenant = params[0]
                self.sets += 1
            return self

        def close(self):
            self.closed = True

    made: list = []

    def factory(url):
        c = FakeConn(url)
        made.append(c)
        return c

    def pool(**kw):
        return Pool("postgresql:///probe", connect=factory, **kw)

    # ── the tenant contract, which is the reason this file exists ───────────
    p = pool(max_size=1)
    with p.connection(tenant_id="firm-a") as c:
        check(c.tenant == "firm-a", "a checkout sets app.tenant_id before the caller sees it")
    first = made[-1]
    with p.connection(tenant_id="firm-b") as c:
        check(c is first,
              "...the SAME connection is reused, which is the point of a pool")
        check(c.tenant == "firm-b",
              "...and it is RE-SET for the new tenant. Without this the pool would hand "
              "firm-b a session still identified as firm-a, and every RLS policy compares "
              "against exactly that value")
    check(first.sets == 2,
          f"...set on EVERY checkout, not 'if it changed' ({first.sets} sets for 2 checkouts)")

    # Same tenant twice still re-sets: "if it changed" is the optimisation that becomes the
    # bug the first time a connection is shared by a path that forgot to set it.
    with p.connection(tenant_id="firm-b"):
        pass
    check(first.sets == 3, f"...including the same tenant twice ({first.sets})")

    for bad in ("", "   ", None):
        try:
            with p.connection(tenant_id=bad):
                pass
            check(False, f"a blank tenant_id ({bad!r}) is refused")
        except ValueError as e:
            check("previous caller" in str(e).lower(),
                  f"a blank tenant_id ({bad!r}) is REFUSED, and the reason names the worse "
                  f"case: a connection still carrying the PREVIOUS caller's id")

    # ── the hard cap refuses rather than exceeding ─────────────────────────
    p2 = pool(max_size=2, acquire_timeout=0.05)
    held = []
    import contextlib
    with contextlib.ExitStack() as stack:
        for i in range(2):
            held.append(stack.enter_context(p2.connection(tenant_id=f"t{i}")))
        check(p2.stats()["open"] == 2, f"two connections open at the cap ({p2.stats()})")
        try:
            with p2.connection(tenant_id="t3"):
                check(False, "a third checkout past the cap is refused")
        except PoolExhausted as e:
            check("cap is for" in str(e),
                  "a checkout past the cap is REFUSED after the wait, not served by opening "
                  "one more -- a pool that exceeds its cap under load is the thing this is for")
        check(p2.stats()["open"] == 2,
              f"...and no connection was opened beyond the cap ({p2.stats()['open']})")
        check(p2.stats()["refusals"] == 1, "...and the refusal is counted")
    # Released, so the next caller is served.
    with p2.connection(tenant_id="t4") as c:
        check(c is not None, "once one is released the next caller is served")

    # ── separate caps for API and workers ──────────────────────────────────
    check(API_MAX_SIZE > WORKER_MAX_SIZE,
          f"the API cap ({API_MAX_SIZE}) exceeds the worker cap ({WORKER_MAX_SIZE}), so bulk "
          f"work cannot take every slot the API needs to answer anyone")
    a, w = pool(max_size=API_MAX_SIZE, name="api"), pool(max_size=WORKER_MAX_SIZE,
                                                         name="worker")
    check(a.max_size != w.max_size and a.name != w.name,
          "the two pools are separate objects with separate caps, not one shared budget")

    # ── a dead connection is discarded, not handed out ─────────────────────
    p3 = pool(max_size=1)
    with p3.connection(tenant_id="t"):
        pass
    stale = made[-1]
    stale.closed = True
    with p3.connection(tenant_id="t") as c:
        check(c is not stale and not c.closed,
              "a connection found CLOSED on checkout is discarded and replaced, so a server "
              "restart costs one acquire rather than every later query")

    # ── an aged idle connection is not reused ──────────────────────────────
    now = [0.0]
    p4 = Pool("postgresql:///probe", connect=factory, max_size=1, max_idle=10.0,
              clock=lambda: now[0])
    with p4.connection(tenant_id="t"):
        pass
    aged = made[-1]
    now[0] = 11.0
    with p4.connection(tenant_id="t") as c:
        check(c is not aged,
              "an idle connection older than max_idle is closed rather than reused, so a pool "
              "does not hold sockets open across a quiet night")

    # ── a raising caller does not return a connection of unknown state ─────
    p5 = pool(max_size=1)
    try:
        with p5.connection(tenant_id="t") as c:
            broken = c
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    check(broken.closed and p5.stats()["idle"] == 0,
          "a connection whose caller RAISED is closed rather than returned: its transaction "
          "state is unknown, and the next caller would inherit it")

    # ── it is not merely refusing everything ───────────────────────────────
    p6 = pool(max_size=4)
    served = 0
    for i in range(40):
        with p6.connection(tenant_id=f"t{i % 3}"):
            served += 1
    check(served == 40,
          f"forty sequential checkouts are ALL served from four connections ({served}) -- a "
          f"pool that refused anything by default would pass every check above")
    check(p6.stats()["peak"] <= 4, f"...and never opened more than the cap ({p6.stats()})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
