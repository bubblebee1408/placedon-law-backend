#!/usr/bin/env python3
"""Per-tenant rate and request-size limits, shared by both HTTP surfaces.

P2. One noisy tenant must not be able to spend the deployment's capacity, and one oversized
body must not be able to spend its memory. Both limits live here rather than in a route
because there are TWO surfaces -- `/v1/{rest:path}` and the `/v2` routes generated from the
verb table -- and a limit wired into one of them is a limit the other does not have. That is
the sibling-caller mistake, and it is the usual way a guard ends up half-applied.

## The rate limit is a token bucket, not a fixed window

A fixed window permits a double burst across its boundary: sixty requests at 11:59:59 and
sixty more at 12:00:00 is a hundred and twenty in one second, which is exactly the load the
limit exists to prevent. A bucket refills continuously, so the only burst it allows is the one
it is configured to allow -- `BURST`, stated rather than emergent.

The clock is injected. A rate limiter tested with `sleep` is a slow test that still cannot
reach the boundary cases, and the boundary is the whole behaviour.

## What the size limit does and does NOT protect

`Content-Length` is checked first, when the client sends one, so an oversized request is
refused before its body is read. Then the ACTUAL length is checked, because Content-Length is
a claim by the sender and a lying one must not get a free pass.

But by the time a handler holds `raw`, an ASGI server has already buffered it. **So this cap
bounds what the application will PROCESS, not what the machine will RECEIVE.** Bounding the
latter is the server's job -- Caddy and uvicorn each have a setting for it -- and H1's
deployment scripts are where that belongs. Saying this cap stops a memory exhaustion attack
would be claiming protection it does not give.

Binary upload is not built yet: `vault.upload` takes text in a JSON field, and its own
docstring says a binary route is the shape it will take. When that route exists it needs a
STREAMING cap, because this one reads the body to measure it.

Run: PYTHONPATH=. python3 gateway/limits.py --test
"""
from __future__ import annotations

import time
import threading
import asyncio
import logging
from decimal import Decimal, ROUND_CEILING
from dataclasses import dataclass, field

__all__ = ["MAX_BODY_BYTES", "RATE_PER_MINUTE", "BURST", "Refusal", "Limiter",
           "PostgresLimiter",
           "check_body_size", "TOO_LARGE", "RATE_LIMITED"]

# 10 MiB. A 200-page agreement as text is about 1 MB, so this is generous for every path that
# exists; it is not a guess at what a binary upload route will need.
MAX_BODY_BYTES = 10 * 1024 * 1024

RATE_PER_MINUTE = 60        # sustained, per tenant
BURST = 120                 # the bucket's depth: what a tenant may spend at once

TOO_LARGE = "REQUEST_TOO_LARGE"
RATE_LIMITED = "RATE_LIMITED"
RATE_LIMIT_UNAVAILABLE = "RATE_LIMIT_UNAVAILABLE"
_LOG = logging.getLogger(__name__)
_LOG_LOCK = threading.Lock()
_LAST_UNAVAILABLE_LOG = 0.0


def _log_limiter_unavailable(failure_kind: str) -> None:
    """Emit a sampled, identifier-free signal so an outage cannot flood logs."""
    global _LAST_UNAVAILABLE_LOG
    now = time.monotonic()
    with _LOG_LOCK:
        if now - _LAST_UNAVAILABLE_LOG < 30:
            return
        _LAST_UNAVAILABLE_LOG = now
    _LOG.warning("shared_rate_limiter_unavailable", extra={"failure_kind": failure_kind})


@dataclass(frozen=True)
class Refusal:
    """Why a request was refused, and what the caller should do about it."""
    code: str
    detail: str
    http_status: int
    retry_after: int | None = None


def check_body_size(raw: bytes | None, *, content_length: str | None = None,
                    limit: int = MAX_BODY_BYTES) -> Refusal | None:
    """None if the body is acceptable. A Refusal naming the size if it is not."""
    claimed = None
    if content_length is not None:
        try:
            claimed = int(content_length)
        except (TypeError, ValueError):
            claimed = None          # an unparseable header is not a size claim
    if claimed is not None and claimed > limit:
        return Refusal(TOO_LARGE,
                       f"the request declares {claimed} bytes, over the {limit}-byte limit",
                       413)
    actual = len(raw or b"")
    if actual > limit:
        return Refusal(TOO_LARGE,
                       f"the request body is {actual} bytes, over the {limit}-byte limit"
                       + ("" if claimed is None else
                          f" (it declared {claimed}, which is why the declared size alone "
                          f"is not trusted)"),
                       413)
    return None


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class Limiter:
    """Per-tenant token buckets. One instance per deployment, shared by both surfaces."""
    per_minute: int = RATE_PER_MINUTE
    burst: int = BURST
    clock: object = time.monotonic
    _buckets: dict = field(default_factory=dict)
    _lock: object = field(default_factory=threading.Lock, repr=False)

    def check(self, tenant_id: str, *, cost: int = 1) -> Refusal | None:
        """Spend `cost` tokens for this tenant. None if allowed, a Refusal if not.

        Refusing does NOT spend a token. A limiter that charged for refusals would push the
        recovery time out every time a blocked client retried, which turns a brief limit into
        an indefinite one.
        """
        if not tenant_id or not isinstance(cost, int) or cost < 1 or cost > self.burst:
            raise ValueError("tenant and a positive cost within the bucket burst are required")
        with self._lock:
            now = float(self.clock())
            rate = self.per_minute / 60.0
            b = self._buckets.get(tenant_id)
            if b is None:
                b = self._buckets[tenant_id] = _Bucket(float(self.burst), now)
            else:
                b.tokens = min(float(self.burst), b.tokens + (now - b.updated) * rate)
                b.updated = now
            if b.tokens < cost:
                short = cost - b.tokens
                return Refusal(RATE_LIMITED,
                               f"tenant {tenant_id} is over its rate limit of "
                               f"{self.per_minute} requests/minute (burst {self.burst})",
                               429, retry_after=max(1, int(short / rate) + 1))
            b.tokens -= cost
            return None

    def tokens_for(self, tenant_id: str) -> float:
        """What this tenant has left RIGHT NOW. A pure read: it refills but does not mutate.

        Returning the stored count without applying the refill reported a stale number -- a
        bucket idle for an hour still read as empty. That is wrong for a test and worse for
        usage reporting, which is the other caller. For deciding, use `check`.
        """
        with self._lock:
            b = self._buckets.get(tenant_id)
            if b is None:
                return float(self.burst)
            elapsed = float(self.clock()) - b.updated
            return min(float(self.burst), b.tokens + elapsed * (self.per_minute / 60.0))


def _refilled(tokens: Decimal, updated_at, now, *, per_minute: int,
              burst: int) -> tuple[Decimal, object]:
    """Refill from a database timestamp, clamping backward wall-clock corrections."""
    effective_now = max(now, updated_at)
    elapsed = Decimal(str((effective_now - updated_at).total_seconds()))
    rate = Decimal(per_minute) / Decimal(60)
    return min(Decimal(burst), tokens + elapsed * rate), effective_now


@dataclass
class PostgresLimiter:
    """Tenant token buckets shared by gateway replicas through PostgreSQL.

    The caller must pass the tenant resolved from authenticated credentials. A short
    transaction sets that tenant for FORCE RLS, locks exactly its bucket row, refills with
    the database clock, and consumes only when allowed. Storage failures fail closed; this
    class never falls back to the process-local Limiter.
    """
    url: str
    per_minute: int = RATE_PER_MINUTE
    burst: int = BURST
    connect_timeout: int = 2
    statement_timeout_ms: int = 1200
    lock_timeout_ms: int = 700
    max_concurrent_checks: int = 10
    acquire_timeout: float = 0.25
    _slots: asyncio.Semaphore = field(init=False, repr=False)
    _pool: object = field(init=False, repr=False)

    def __post_init__(self):
        if (not self.url or self.per_minute < 1 or self.burst < 1 or self.burst > 10000
                or self.connect_timeout < 1 or self.statement_timeout_ms < 1
                or self.lock_timeout_ms < 1 or not 1 <= self.max_concurrent_checks <= 100
                or self.acquire_timeout <= 0):
            raise ValueError("invalid shared limiter configuration")
        self._slots = asyncio.Semaphore(self.max_concurrent_checks)
        # Reuse bounded process-local connections. The database remains the shared atomic
        # authority; this cap only limits sockets opened by this replica.
        from gateway.pool import Pool
        import psycopg
        self._pool = Pool(self.url, max_size=self.max_concurrent_checks,
                          acquire_timeout=self.acquire_timeout, name="rate-limit",
                          connect=lambda url: psycopg.connect(
                              url, autocommit=True, connect_timeout=self.connect_timeout))

    async def check_async(self, tenant_id: str, *, cost: int = 1) -> Refusal | None:
        """Consume shared tenant capacity, or return a stable, sanitized refusal."""
        if not tenant_id or not isinstance(cost, int) or cost < 1 or cost > self.burst:
            raise ValueError("tenant and a positive cost within the bucket burst are required")
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self.acquire_timeout)
        except TimeoutError:
            _log_limiter_unavailable("admission_timeout")
            return Refusal(RATE_LIMIT_UNAVAILABLE,
                           "Shared request limits are temporarily unavailable. Retry shortly.",
                           503, retry_after=2)
        work = asyncio.create_task(asyncio.to_thread(self._consume_sync, tenant_id, cost))
        try:
            # A cancelled request cannot stop a running thread. Keep its admission slot until
            # that DB transaction has actually finished, or repeated client disconnects could
            # bypass the connection cap while abandoned worker threads keep running.
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(work)
            except Exception:  # noqa: BLE001 - cancellation remains the caller's outcome.
                pass
            raise
        except Exception as exc:  # noqa: BLE001 - never include DSN, SQL or tenant details.
            _log_limiter_unavailable(type(exc).__name__)
            return Refusal(RATE_LIMIT_UNAVAILABLE,
                           "Shared request limits are temporarily unavailable. Retry shortly.",
                           503, retry_after=2)
        finally:
            self._slots.release()

    def close(self) -> None:
        """Close idle pooled connections during application shutdown."""
        self._pool.close()

    def _consume_sync(self, tenant_id: str, cost: int) -> Refusal | None:
        # The pool resets app.tenant_id on every checkout; set transaction-local values for
        # query and lock bounds. Keep all state changes in the same short transaction.
        with self._pool.connection(tenant_id=tenant_id) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.execute("SELECT set_config('statement_timeout', %s, true)",
                             (f"{self.statement_timeout_ms}ms",))
                conn.execute("SELECT set_config('lock_timeout', %s, true)",
                             (f"{self.lock_timeout_ms}ms",))
                conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
                conn.execute(
                    "INSERT INTO gateway_rate_limits (tenant_id, tokens, updated_at) "
                    "VALUES (%s, %s, clock_timestamp()) ON CONFLICT (tenant_id) DO NOTHING",
                    (tenant_id, Decimal(self.burst)))
                row = conn.execute(
                    "SELECT tokens, updated_at FROM gateway_rate_limits "
                    "WHERE tenant_id = %s FOR UPDATE", (tenant_id,)).fetchone()
                if row is None:
                    # RLS should make a missing row impossible after the insert. Do not
                    # reinterpret a policy/configuration error as a fresh full bucket.
                    raise RuntimeError("shared limiter row unavailable")
                stored_tokens, updated_at = row
                # Sample the clock only AFTER the row lock is held. Otherwise lock wait time
                # is lost from refill/retry calculations and can make contention unfair.
                now = conn.execute("SELECT clock_timestamp()").fetchone()[0]
                available, effective_now = _refilled(
                    stored_tokens, updated_at, now,
                    per_minute=self.per_minute, burst=self.burst)
                rate = Decimal(self.per_minute) / Decimal(60)
                allowed = available >= Decimal(cost)
                remaining = available - Decimal(cost) if allowed else available
                conn.execute(
                    "UPDATE gateway_rate_limits SET tokens = %s, updated_at = %s "
                    "WHERE tenant_id = %s", (remaining, effective_now, tenant_id))
                if allowed:
                    return None
                retry_after = int(((Decimal(cost) - available) / rate)
                                  .to_integral_value(rounding=ROUND_CEILING))
                return Refusal(
                    RATE_LIMITED,
                    f"the tenant is over its rate limit of {self.per_minute} requests/minute "
                    f"(burst {self.burst})",
                    429, retry_after=max(1, retry_after))


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

    print("limits")

    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 10, 17, tzinfo=timezone.utc)
    filled, effective = _refilled(Decimal(0), t0, t0 + timedelta(seconds=1),
                                  per_minute=60, burst=5)
    check(filled == Decimal(1), "database bucket refills one token per second")
    full, _ = _refilled(Decimal(4), t0, t0 + timedelta(minutes=10),
                        per_minute=60, burst=5)
    check(full == Decimal(5), "database bucket refill is capped at the configured burst")
    unchanged, effective = _refilled(Decimal(2), t0, t0 - timedelta(seconds=5),
                                     per_minute=60, burst=5)
    check(unchanged == Decimal(2) and effective == t0,
          "database clock moving backward cannot create tokens or move bucket time backward")

    async def async_refusals():
        # No database is touched: this verifies sanitized failure behavior and that a slow
        # store cannot create an unbounded wait for additional checks in the same process.
        class Broken(PostgresLimiter):
            def _consume_sync(self, _tenant_id, _cost):
                raise RuntimeError("dsn=secret tenant=private query=client text")

        broken = Broken("postgresql://sensitive", max_concurrent_checks=1,
                        acquire_timeout=0.01)
        import unittest
        with unittest.TestCase().assertLogs(_LOG, level="WARNING") as captured:
            refusal = await broken.check_async("tenant-id")
        safe = (refusal.code == RATE_LIMIT_UNAVAILABLE and refusal.http_status == 503
                and refusal.retry_after == 2 and "sensitive" not in refusal.detail
                and "tenant" not in refusal.detail and "query" not in refusal.detail
                and all(secret not in " ".join(captured.output)
                        for secret in ("sensitive", "private", "client text")))

        class Slow(PostgresLimiter):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.entered = threading.Event()
                self.release = threading.Event()

            def _consume_sync(self, _tenant_id, _cost):
                self.entered.set()
                self.release.wait()
                return None

        slow = Slow("postgresql://unused", max_concurrent_checks=1, acquire_timeout=0.01)
        first = asyncio.create_task(slow.check_async("tenant-id"))
        await asyncio.to_thread(slow.entered.wait)
        first.cancel()
        await asyncio.sleep(0)
        held_through_cancel = not first.done()
        second = await slow.check_async("tenant-id")
        slow.release.set()
        try:
            await first
        except asyncio.CancelledError:
            pass
        return (safe, second.code == RATE_LIMIT_UNAVAILABLE and second.http_status == 503
                and held_through_cancel)

    safe_failure, bounded = asyncio.run(async_refusals())
    check(safe_failure, "database failure returns sanitized fail-closed 503, never local fallback")
    check(bounded, "admission stays bounded through saturation and caller cancellation")

    def at(t0=0.0):
        """A limiter on a clock the test moves, so the boundary cases are reachable."""
        now = [t0]
        return Limiter(clock=lambda: now[0]), now

    # ── the bucket's depth is the burst, stated not emergent ────────────────
    lim, now = at()
    allowed = sum(1 for _ in range(BURST) if lim.check("firm-a") is None)
    check(allowed == BURST, f"a fresh tenant may spend exactly BURST requests ({allowed})")
    r = lim.check("firm-a")
    check(r is not None and r.code == RATE_LIMITED and r.http_status == 429,
          "...and the next one is refused with 429")
    check(r.retry_after and r.retry_after >= 1,
          f"...carrying a Retry-After the caller can act on ({r.retry_after}s)")

    # ── per TENANT, which is the whole point ───────────────────────────────
    check(lim.check("firm-b") is None,
          "a DIFFERENT tenant is unaffected -- one noisy firm must not spend another's "
          "capacity")

    # ── a refusal does not spend a token ───────────────────────────────────
    lim, now = at()
    for _ in range(BURST):
        lim.check("firm-a")
    before = lim.tokens_for("firm-a")
    for _ in range(50):
        lim.check("firm-a")
    check(lim.tokens_for("firm-a") == before,
          "fifty refused retries spend NO tokens -- charging for refusals would push the "
          "recovery time out every time a blocked client retried, turning a brief limit "
          "into an indefinite one")

    # ── it refills continuously ────────────────────────────────────────────
    lim, now = at()
    for _ in range(BURST):
        lim.check("firm-a")
    now[0] += 1.0
    check(lim.check("firm-a") is None,
          f"one second later the bucket has refilled by {RATE_PER_MINUTE / 60:.0f}/s and the "
          f"next request is allowed")
    now[0] += 3600.0
    check(lim.tokens_for("firm-a") == float(BURST),
          "...and an idle hour refills to BURST and no further: the bucket does not bank "
          "credit a tenant never earned")

    # ── the boundary a fixed window gets wrong ─────────────────────────────
    # Sixty at 11:59:59 and sixty at 12:00:00 is the double burst a window permits. The
    # bucket's answer is that only BURST is ever available at once, wherever the clock is.
    lim, now = at(t0=59.0)
    first = sum(1 for _ in range(BURST) if lim.check("firm-a") is None)
    now[0] = 60.0                      # the window boundary a fixed-window limiter resets on
    second = sum(1 for _ in range(BURST) if lim.check("firm-a") is None)
    check(first == BURST and second < BURST,
          f"crossing a minute boundary does NOT reset the allowance ({first} then {second}) "
          f"-- a fixed window would have allowed {BURST * 2} in one second")

    # ── request size ───────────────────────────────────────────────────────
    check(check_body_size(None) is None and check_body_size(b"") is None,
          "no body and an empty body are both acceptable")
    check(check_body_size(b"x" * MAX_BODY_BYTES) is None,
          "a body exactly at the limit is accepted")
    r = check_body_size(b"x" * (MAX_BODY_BYTES + 1))
    check(r is not None and r.code == TOO_LARGE and r.http_status == 413,
          "...and one byte over is refused with 413")
    check(str(MAX_BODY_BYTES + 1) in r.detail,
          f"...naming the actual size, so the caller knows by how much ({r.detail[:40]})")

    # Content-Length is a CLAIM. Both directions are checked.
    r = check_body_size(b"x" * 10, content_length=str(MAX_BODY_BYTES + 1))
    check(r is not None and r.http_status == 413,
          "an oversized Content-Length is refused BEFORE the body matters, so a declared "
          "giant does not get read")
    r = check_body_size(b"x" * (MAX_BODY_BYTES + 1), content_length="10")
    check(r is not None and "not trusted" in r.detail,
          "...and a body that LIES about its length is still refused on its real size, which "
          "is why the declared size alone is not trusted")
    check(check_body_size(b"x" * 10, content_length="not-a-number") is None,
          "an unparseable Content-Length is not a size claim, and does not refuse a small body")

    # ── a refusal is a named reason, never a bare drop ─────────────────────
    limited, _ = at()
    for _ in range(BURST):
        limited.check("t")
    for r in (check_body_size(b"x" * (MAX_BODY_BYTES + 1)), limited.check("t")):
        check(r.code and r.detail and r.http_status >= 400,
              f"every refusal carries a code, a reason and a status ({r.code})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
