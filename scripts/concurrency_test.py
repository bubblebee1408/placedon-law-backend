#!/usr/bin/env python3
"""Fifty at once: nothing runs twice, no tenant reads another's rows, and p95 is recorded.

P2. Every other test in this repository runs one thing at a time, so every race it contains is
invisible to all of them. This runs the three properties that only break under concurrency:

    no double execution   N jobs, 50 workers claiming at once -> each job claimed EXACTLY
                          once, and the claim total equals N. A job run twice is a document
                          charged for twice.
    no cross-tenant read  two tenants, 50 interleaved requests -> each sees its own rows and
                          none of the other's. Serial tests pass this trivially because
                          nothing is interleaved.
    p95 latency           recorded, not asserted against a target. See below.

## p95 is REPORTED, not gated

A latency target on a laptop under a thread pool measures the laptop. The number is printed so
a regression is visible across runs on the same machine, and `--gate` asserts only the two
CORRECTNESS properties -- which do not depend on how fast the machine is. R0 is where latency
targets are specified, and they belong against the hosted deployment (H1), not here.

## In-memory, and what that does not cover

The gate has no database, so this runs against `MemoryQueue` and `MemoryBackend` with real OS
threads. That finds a race in OUR code and finds nothing about Postgres's. Row-level security
and `SELECT ... FOR UPDATE SKIP LOCKED` are proved separately, against a live server, by
`scripts/rls_integration.py --run`. Both are needed and neither replaces the other: this one
can run anywhere, that one tests what actually ships.

## ⚠ WHAT THIS FOUND, 02-10-2026, and why it is not in the gate yet

First run: **100 of 100 interleaved requests saw the other tenant's rows.** Too total to be a
race, and it is not one -- driven serially, tenant B sees tenant A's matter with no concurrency
at all. `MemoryBackend` consults `tenant_id` in NONE of its 21 read methods, and its rows do
not carry one.

That is consistent with `gateway/app.py`'s own comment -- "one shared backend in memory, so two
requests in a process see each other's rows" -- so the memory store never claimed to isolate
tenants. The risk is that `create_app` will serve multi-tenant traffic on it anyway whenever no
database is configured, and nothing says so where a deployer would see it. **Postgres is
unaffected**: 24 tenant-scoped tables carry FORCE ROW LEVEL SECURITY, proved against a live
server by `scripts/rls_integration.py --run`.

This script is therefore committed but **NOT registered in `scripts/run_tests.sh`**: it
currently reports BROKEN, and registering a failing test would turn the gate red for a finding
rather than a regression. The fix is to make the memory path **fail closed** -- refuse a second
distinct tenant rather than pretend to isolate -- and the registration lands with it.

Run: PYTHONPATH=. python3 scripts/concurrency_test.py
     PYTHONPATH=. python3 scripts/concurrency_test.py --test
"""
from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

WORKERS = 50
JOBS = 200
TENANTS = ("11111111-1111-1111-1111-111111111111",
           "22222222-2222-2222-2222-222222222222")
ACTORS = ("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * len(ordered) + 0.5)) - 1))
    return ordered[k]


def no_double_execution(*, jobs: int = JOBS, workers: int = WORKERS) -> dict:
    """Every queued job is claimed exactly once, however many workers race for it."""
    from gateway.jobs import MemoryQueue

    q = MemoryQueue()
    for i in range(jobs):
        q.enqueue(run_id=f"run-{i}", intent="answer", args={"i": i})

    claimed: list[str] = []
    lock = threading.Lock()
    latencies: list[float] = []

    def drain(worker: int) -> None:
        while True:
            t0 = time.perf_counter()
            job = q.claim(worker=f"w{worker}")
            dt = time.perf_counter() - t0
            if job is None:
                return
            with lock:
                claimed.append(job.run_id)
                latencies.append(dt * 1000.0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(drain, range(workers)))

    counts = Counter(claimed)
    twice = {rid: n for rid, n in counts.items() if n > 1}
    return {"queued": jobs, "workers": workers, "claims": len(claimed),
            "distinct": len(counts), "claimed_more_than_once": twice,
            "p50_ms": _percentile(latencies, 50), "p95_ms": _percentile(latencies, 95)}


def no_cross_tenant_read(*, workers: int = WORKERS) -> dict:
    """Two tenants hammering the REAL gateway at once, each reading only its own runs.

    Driven through `starlette.testclient` rather than against a backend directly, because the
    race this is looking for is in `gateway/app.backend_for`, not in the store: on the memory
    path it mutates ONE shared backend's `tenant_id` per request, so two interleaved requests
    can have one tenant's read land after the other's assignment. app.py says in terms that
    for Postgres a backend is built per request and bound to the tenant RLS compares against;
    the memory path has no such binding, and only a concurrent test can see the difference.
    """
    from starlette.testclient import TestClient

    from checker.api import handle
    from gateway.app import create_app
    from gateway.auth import KeyStore

    keys = KeyStore()
    tokens = {}
    for i, tenant in enumerate(TENANTS):
        # `actor` must be a UUID: gateway/auth refuses anything else because audit.py does,
        # and a request that cannot be written to the audit chain must not be served.
        tokens[tenant], _ = keys.mint(tenant_id=tenant, actor=ACTORS[i],
                                      label="load", role="admin")
    app = create_app(handler=handle, keys=keys, db_url="")
    app.state.limiter = _unlimited()

    leaks: list[str] = []
    latencies: list[float] = []
    lock = threading.Lock()

    def work(n: int) -> None:
        tenant = TENANTS[n % 2]
        client = TestClient(app, headers={"Authorization": f"Bearer {tokens[tenant]}"})
        t0 = time.perf_counter()
        made = client.post("/v2/matters/create",
                           json={"name": f"{'ab'[n % 2]}-matter-{n}"})
        seen = client.post("/v2/matters/list", json={})
        dt = time.perf_counter() - t0
        bad = []
        if seen.status_code == 200:
            other = "ba"[n % 2]
            bad = [m.get("name") for m in (seen.json().get("matters") or [])
                   if str(m.get("name") or "").startswith(f"{other}-matter-")]
        with lock:
            latencies.append(dt * 1000.0)
            leaks.extend(b for b in bad if b)
            if made.status_code not in (200, 409):
                leaks.append(f"create returned {made.status_code}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, range(workers * 2)))

    return {"requests": workers * 2, "tenants": len(TENANTS),
            "cross_tenant_rows_seen": sorted(set(leaks)),
            "p50_ms": _percentile(latencies, 50), "p95_ms": _percentile(latencies, 95)}


def _unlimited():
    """A limiter that never refuses. The rate limit is tested in gateway/limits.py; here it
    would simply turn fifty concurrent requests into forty-eight 429s and measure nothing."""
    from gateway.limits import Limiter
    return Limiter(per_minute=10 ** 9, burst=10 ** 9)


def measure(*, workers: int = WORKERS, jobs: int = JOBS) -> dict:
    dbl = no_double_execution(jobs=jobs, workers=workers)
    xt = no_cross_tenant_read(workers=workers)
    return {
        "double_execution": dbl,
        "cross_tenant": xt,
        "broken": (
            ([f"{len(dbl['claimed_more_than_once'])} job(s) claimed more than once"]
             if dbl["claimed_more_than_once"] else [])
            + ([f"claims {dbl['claims']} != queued {dbl['queued']}"]
               if dbl["claims"] != dbl["queued"] else [])
            + ([f"{len(xt['cross_tenant_rows_seen'])} cross-tenant row(s) visible"]
               if xt["cross_tenant_rows_seen"] else [])),
    }


def report(r: dict) -> str:
    d, x = r["double_execution"], r["cross_tenant"]
    lines = [
        f"  {d['workers']} workers racing for {d['queued']} jobs",
        f"    claims {d['claims']}, distinct {d['distinct']}, "
        f"claimed twice {len(d['claimed_more_than_once'])}",
        f"    claim latency p50 {d['p50_ms']:.3f} ms  p95 {d['p95_ms']:.3f} ms",
        "",
        f"  {x['requests']} interleaved requests across {x['tenants']} tenants",
        f"    cross-tenant rows visible {len(x['cross_tenant_rows_seen'])}",
        f"    write+read p50 {x['p50_ms']:.3f} ms  p95 {x['p95_ms']:.3f} ms",
        "",
        "  p95 is REPORTED, not gated: a latency target on a laptop under a thread pool",
        "  measures the laptop. R0 specifies the targets, against the hosted deployment.",
    ]
    if r["broken"]:
        lines += ["", "  BROKEN:"] + [f"    {b}" for b in r["broken"]]
    else:
        lines += ["", "  Nothing ran twice and no tenant saw another's rows."]
    return "\n".join(lines)
