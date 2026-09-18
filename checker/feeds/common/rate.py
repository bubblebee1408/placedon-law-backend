"""Per-source rate governor -- the one idea from gods-eye-view worth porting outright.

`server/providers/common/rate-limit.js` (STEP 1) is a fixed 60s-window limiter that is
OPT-IN: an unset, zero, or non-numeric env value collapses to "unlimited" and the
factory returns `null` rather than a limiter, so the ~20 adapters that never need a cap
pay nothing for one that does. That "governor per key, lazily built, absent by default"
shape is exactly right here: a feed with a CONTRACTED rate (Axis D's `CONTRACT_ONLY`
sources most of all -- a licensed MCA aggregator's terms typically state calls/minute
in the contract itself) should be capped because the contract says so, not because
this module guessed at a number. A feed with no such term should pay nothing.

`makeOptInRateLimiter` also lazily builds its limiter "once, then reused, so its per-IP
window state persists across requests" -- ported here as: a governor is stateful by
construction (one instance per source, held by whoever owns that source's fetch loop),
and `allow()` is the only thing that reads or advances that state.

## Determinism, for the same reason acquisition_log.py takes a timestamp as a parameter

`checker/acquisition_log.py` never reads the clock internally so that identical inputs
produce identical digests, testably. `RateGovernor.allow()` follows the same discipline:
it defaults to `time.monotonic()` for real use, but every test below passes `now`
explicitly, so a window boundary is provable rather than flaky.

Run: python3 checker/feeds/common/rate.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateGovernor:
    """A fixed-window call limiter, one instance per source.

    Not frozen -- the one stateful object in checker/feeds/common, deliberately: a
    governor that could not remember previous calls would not govern anything.
    Construct with `make_governor()` rather than directly in most call sites, so
    the opt-in-unlimited case is handled in one place.
    """

    max_calls: int
    window_s: float = 60.0
    _window_start: float = field(default=0.0, init=False, repr=False)
    _count: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_calls <= 0:
            raise ValueError(
                "max_calls must be positive; use make_governor() for the opt-in "
                "unlimited case (None/0/negative -> no governor at all)")
        if self.window_s <= 0:
            raise ValueError("window_s must be positive")

    def allow(self, *, now: float | None = None) -> bool:
        """May a call happen now? Checking IS claiming: a call that is allowed
        counts against the window immediately, so two rapid callers cannot both
        read "allowed" before either one's call is recorded."""
        t = now if now is not None else time.monotonic()
        if t - self._window_start >= self.window_s:
            self._window_start = t
            self._count = 0
        if self._count >= self.max_calls:
            return False
        self._count += 1
        return True

    def remaining(self, *, now: float | None = None) -> int:
        """Calls left in the current window, without consuming one. Peeking, not claiming."""
        t = now if now is not None else time.monotonic()
        if t - self._window_start >= self.window_s:
            return self.max_calls
        return max(0, self.max_calls - self._count)


def make_governor(max_calls_per_window: int | None, *, window_s: float = 60.0) -> RateGovernor | None:
    """Opt-in construction, mirroring rate-limit.js's makeOptInRateLimiter: a
    None/zero/negative cap means unlimited and returns None so the caller can skip
    the check entirely -- a runtime no-op, not a governor with an infinite limit
    that still pays for a dict lookup and a window comparison on every call.
    """
    if max_calls_per_window is None or max_calls_per_window <= 0:
        return None
    return RateGovernor(max_calls=max_calls_per_window, window_s=window_s)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("feeds.common.rate")

    # ── opt-in: unset/zero/negative means unlimited, and unlimited means None ─
    check(make_governor(None) is None, "no cap given -> no governor (unlimited)")
    check(make_governor(0) is None, "a zero cap collapses to unlimited, like rate-limit.js")
    check(make_governor(-5) is None, "a negative cap collapses to unlimited, not an error")
    g = make_governor(3)
    check(isinstance(g, RateGovernor) and g.max_calls == 3,
          "a positive cap builds a real governor")

    # ── construction refuses nonsense directly ────────────────────────────────
    try:
        RateGovernor(max_calls=0)
        check(False, "RateGovernor(max_calls=0) must raise directly (use make_governor instead)")
    except ValueError:
        check(True, "RateGovernor(max_calls=0) raises directly")
    try:
        RateGovernor(max_calls=1, window_s=0)
        check(False, "a zero window_s must raise")
    except ValueError:
        check(True, "a zero window_s raises")

    # ── the window, driven entirely by an injected clock ──────────────────────
    g = RateGovernor(max_calls=3, window_s=60.0)
    check(g.allow(now=0.0) and g.allow(now=1.0) and g.allow(now=2.0),
          "three calls inside one window are all allowed")
    check(not g.allow(now=3.0), "a fourth call in the same window is refused")
    check(not g.allow(now=59.9), "...still refused right up to the window boundary")
    check(g.allow(now=60.0), "a call exactly at the window boundary starts a fresh window")
    check(g.remaining(now=60.0) == 2, "remaining() reflects the call that just consumed the new window")

    # ── determinism: identical inputs give identical decisions ───────────────
    g1 = RateGovernor(max_calls=2, window_s=10.0)
    g2 = RateGovernor(max_calls=2, window_s=10.0)
    seq = [0.0, 1.0, 2.0, 11.0, 12.0]
    r1 = [g1.allow(now=t) for t in seq]
    r2 = [g2.allow(now=t) for t in seq]
    check(r1 == r2, "two independently-constructed governors given the same clock sequence agree exactly")
    src = __import__("pathlib").Path(__file__).read_text(encoding="utf-8").split("def _test(")[0]
    check("time.time()" not in src and "datetime.now" not in src,
          "no wall clock is read anywhere in the code under test (time.monotonic default excepted)")

    # ── per-source: governors do not share state ──────────────────────────────
    src_a = RateGovernor(max_calls=1, window_s=60.0)
    src_b = RateGovernor(max_calls=1, window_s=60.0)
    check(src_a.allow(now=0.0) and src_b.allow(now=0.0),
          "two different sources' governors are independent -- one source's traffic "
          "does not consume another source's budget")
    check(not src_a.allow(now=0.5) and not src_b.allow(now=0.5),
          "...but each is still individually enforced")

    # ── peeking never consumes ────────────────────────────────────────────────
    g3 = RateGovernor(max_calls=2, window_s=60.0)
    check(g3.remaining(now=0.0) == 2, "remaining() before any call reports the full budget")
    check(g3.remaining(now=0.0) == 2, "...and calling it again does not consume anything")
    g3.allow(now=0.0)
    check(g3.remaining(now=0.0) == 1, "remaining() reflects a call that actually happened")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
