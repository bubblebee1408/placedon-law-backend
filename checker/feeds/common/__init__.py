"""Shared plumbing factored out of feed adapters, ported from gods-eye-view's
`server/providers/common/` (PLAN_15 §2, STEP 1). Three modules survived the port:

  fetch.py   one HTTP path, gated by checker.robots, streamed and capped
  cache.py   on-disk, content-hashed, dated storage -- an observation is an artifact
  rate.py    a per-source rate governor, opt-in and lazily built

`source-root.js` and `request.js` (also read in STEP 1) did not port: the first
resolves a filesystem path for ESM's `import.meta.url`, which Python has no
equivalent need for, and the second reads an inbound proxy REQUEST body, which has
no counterpart here -- this repository's feeds only ever originate outbound
requests. Their absence is a deliberate scoping decision, not an oversight; see the
final report for the full list of what this change does not build.

Re-exported here so a concrete feed adapter (not built in this change) needs one
import line rather than three.

Run: python3 checker/feeds/common/__init__.py
"""
from __future__ import annotations

from checker.feeds.common.cache import CacheEntry, CacheError, artifact_path, load, store
from checker.feeds.common.fetch import DEFAULT_MAX_BYTES, fetch
from checker.feeds.common.rate import RateGovernor, make_governor

__all__ = [
    "fetch", "DEFAULT_MAX_BYTES",
    "CacheEntry", "CacheError", "artifact_path", "store", "load",
    "RateGovernor", "make_governor",
]


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("feeds.common")

    for name in __all__:
        check(name in globals(), f"{name} is re-exported from checker.feeds.common")

    import checker.feeds.common as pkg
    for name in __all__:
        check(hasattr(pkg, name), f"...and reachable as checker.feeds.common.{name}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
