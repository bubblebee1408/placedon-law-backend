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
from dataclasses import dataclass, field

__all__ = ["MAX_BODY_BYTES", "RATE_PER_MINUTE", "BURST", "Refusal", "Limiter",
           "check_body_size", "TOO_LARGE", "RATE_LIMITED"]

# 10 MiB. A 200-page agreement as text is about 1 MB, so this is generous for every path that
# exists; it is not a guess at what a binary upload route will need.
MAX_BODY_BYTES = 10 * 1024 * 1024

RATE_PER_MINUTE = 60        # sustained, per tenant
BURST = 120                 # the bucket's depth: what a tenant may spend at once

TOO_LARGE = "REQUEST_TOO_LARGE"
RATE_LIMITED = "RATE_LIMITED"


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

    def check(self, tenant_id: str, *, cost: int = 1) -> Refusal | None:
        """Spend `cost` tokens for this tenant. None if allowed, a Refusal if not.

        Refusing does NOT spend a token. A limiter that charged for refusals would push the
        recovery time out every time a blocked client retried, which turns a brief limit into
        an indefinite one.
        """
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
        b = self._buckets.get(tenant_id)
        if b is None:
            return float(self.burst)
        elapsed = float(self.clock()) - b.updated
        return min(float(self.burst), b.tokens + elapsed * (self.per_minute / 60.0))


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
    for r in (check_body_size(b"x" * (MAX_BODY_BYTES + 1)), at()[0].check("t", cost=BURST + 1)):
        check(r.code and r.detail and r.http_status >= 400,
              f"every refusal carries a code, a reason and a status ({r.code})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
