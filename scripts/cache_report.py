#!/usr/bin/env python3
"""The answer cache's hit rate, and what the number does not include.

O9's reporting half. Deliberately a script and not a verb: every read-only verb in
`gateway/verbs.py` is exported as an MCP tool with no opt-out, and a cache hit rate is an
operator's number, not a capability an agent should hold.

Three counts, and the third is the interesting one:

    hits     an answer was served again, and every citation re-verified at that moment
    misses   nothing was stored for that question, task, date and source set
    stale    something WAS stored and was refused, because a provision it cited had
             changed since

`stale` is not a cache fault. It is the corpus moving, and it is the number that shows the
re-verification gate does anything at all. It is counted as a lookup, so folding it into
`hits` is not available: that would flatter the rate with the exact cases where the cache
was about to be wrong.

A rate over no lookups is reported as **no rate**, never as 0%.

Run: PYTHONPATH=. python3 scripts/cache_report.py
     PLACEDON_DATABASE_URL=postgres://... PYTHONPATH=. python3 scripts/cache_report.py
"""
from __future__ import annotations

import sys


def report(stats: dict) -> str:
    """The printable report, from a {hits, misses, stale} dict. Pure."""
    from checker.answer_cache import Stats
    s = Stats(hits=int(stats.get("hits") or 0), misses=int(stats.get("misses") or 0),
              stale=int(stats.get("stale") or 0))
    d = s.to_dict()
    rate = "no rate yet" if d["hit_rate"] is None else f"{d['hit_rate'] * 100:.1f}%"
    return (f"answer cache\n"
            f"  lookups : {d['lookups']}\n"
            f"  hits    : {d['hits']}\n"
            f"  misses  : {d['misses']}\n"
            f"  stale   : {d['stale']}  (found, and the law had moved)\n"
            f"  hit rate: {rate}\n"
            f"\n  {d['note']}")


def main() -> int:
    from gateway.store import select
    try:
        backend = select()
    except Exception as e:                                       # noqa: BLE001
        print(f"no store: {type(e).__name__}: {str(e)[:160]}")
        return 2
    print(report(backend.read_cache_stats()))
    return 0


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

    print("cache_report")
    empty = report({})
    check("no rate yet" in empty,
          "a cache nobody has queried reports NO RATE, not 0.0%")
    check("not a rate of zero" in empty, "...and says in words that it is not zero")
    r = report({"hits": 3, "misses": 1, "stale": 1})
    check("60.0%" in r, f"the rate is hits over ALL lookups, stale included (3/5 = 60%)")
    check("stale   : 1" in r and "the law had moved" in r,
          "...and the stale count is shown with what it means")
    check("hits" in report({"hits": 1}), "a partial dict reports rather than raising")
    # The one that must not be true: folding stale into hits to flatter the rate.
    check("75.0%" not in r,
          "a stale find is NOT counted as a hit -- 3/4 would be the rate if the cases "
          "where the cache was about to be wrong were quietly dropped")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main())
