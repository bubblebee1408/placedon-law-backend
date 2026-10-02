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

## WHAT THIS FOUND, 02-10-2026, and what was done about it

First run: **100 of 100 interleaved requests saw the other tenant's rows.** Too total to be a
race, and it was not one -- driven serially, tenant B saw tenant A's matter with no concurrency
at all. `MemoryBackend` consults `tenant_id` in NONE of its 21 read methods, and its rows do not
carry one.

That is consistent with `gateway/app.py`'s own comment -- "one shared backend in memory, so two
requests in a process see each other's rows" -- so the memory store never claimed to isolate
tenants. What was wrong is that `create_app` served multi-tenant traffic on it anyway whenever no
database was configured, and nothing said so where a deployer would see it. **Postgres was never
affected**: 24 tenant-scoped tables carry FORCE ROW LEVEL SECURITY, proved against a live server
by `scripts/rls_integration.py --run`.

**The fix was to fail CLOSED, not to retrofit filtering.** `backend_for` now refuses the second
distinct tenant by name, at both surfaces, with 503 and a reason naming
`PLACEDON_DATABASE_URL`. Filtering twenty-one read methods would have made the memory store
look like it enforced isolation, and it would be a dict comprehension standing where Postgres
has a policy the database applies to every query -- including the ones nobody remembered to
filter.

So the property below is no longer "two tenants do not see each other" on the memory path. It is
**"a second tenant is refused"**, which is the guarantee that actually exists. The real
multi-tenant concurrency proof is `rls_integration.py --run` against a live server, and this
says so rather than standing in for it.

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
    """Fifty threads, two tenants, one memory-backed gateway: the second tenant is REFUSED.

    On the memory path there is no isolation to test -- see the docstring. What is tested is
    that the refusal holds under concurrency: whichever tenant arrives first is served, the
    other gets 503, and NO response ever contains the other tenant's rows. A guard that held
    serially and raced open under load would be worse than none, because the serial test would
    say it was fine.
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
    statuses: Counter = Counter()
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
            statuses[made.status_code] += 1
            statuses[seen.status_code] += 1
            leaks.extend(b for b in bad if b)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, range(workers * 2)))

    return {"requests": workers * 2, "tenants": len(TENANTS),
            "cross_tenant_rows_seen": sorted(set(leaks)),
            # String keys: JSON turns an int key into a string on the way out, so an int-keyed
            # dict does not survive a round trip and "is this serialisable" quietly fails.
            "statuses": {str(k): v for k, v in sorted(statuses.items())},
            # The guard must actually have fired, or this measured one tenant twice.
            "refused_503": statuses.get(503, 0),
            "served_200": statuses.get(200, 0),
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
               if xt["cross_tenant_rows_seen"] else [])
            # A run where the guard never fired proves nothing about the guard: it would
            # mean both halves of the pool happened to be the same tenant.
            + (["the single-tenant guard never fired, so this measured one tenant twice"]
               if not xt["refused_503"] else [])
            + (["the FIRST tenant was never served, so the guard refused everything"]
               if not xt["served_200"] else [])),
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
        f"    served 200 {x['served_200']}, refused 503 {x['refused_503']}  "
        f"(the memory store has no isolation, so the second tenant is refused)",
        f"    cross-tenant rows visible {len(x['cross_tenant_rows_seen'])}",
        f"    write+read p50 {x['p50_ms']:.3f} ms  p95 {x['p95_ms']:.3f} ms",
        "",
        "  p95 is REPORTED, not gated: a latency target on a laptop under a thread pool",
        "  measures the laptop. R0 specifies the targets, against the hosted deployment.",
        "  The real multi-tenant proof is scripts/rls_integration.py --run, against a live",
        "  server. This does not stand in for it.",
    ]
    if r["broken"]:
        lines += ["", "  BROKEN:"] + [f"    {b}" for b in r["broken"]]
    else:
        lines += ["", "  Nothing ran twice and no tenant saw another's rows."]
    return "\n".join(lines)


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

    print("concurrency_test")

    # Smaller than the headline run so the gate stays quick; still 50 real OS threads,
    # because the thread count is the variable under test and 5 would prove nothing.
    r = measure(workers=WORKERS, jobs=60)
    d, x = r["double_execution"], r["cross_tenant"]

    check(d["workers"] == WORKERS, f"{WORKERS} real threads raced ({d['workers']})")
    check(d["claims"] == d["queued"],
          f"every queued job was claimed ({d['claims']}/{d['queued']}) -- a claim total "
          f"below the queue size would mean a job was lost, not merely delayed")
    check(not d["claimed_more_than_once"],
          f"NO job was claimed twice -- a job run twice is a document charged for twice "
          f"({d['claimed_more_than_once']})")
    check(d["distinct"] == d["queued"],
          f"...and the distinct count matches, so the claims are {d['queued']} different "
          f"jobs rather than one job {d['claims']} times")

    check(not x["cross_tenant_rows_seen"],
          f"no response contained another tenant's rows ({x['cross_tenant_rows_seen'][:3]})")
    check(x["refused_503"] > 0,
          f"...and the single-tenant guard actually FIRED ({x['refused_503']} refusals) -- "
          f"a run where it never fired would have measured one tenant twice")
    check(x["served_200"] > 0,
          f"...while the first tenant WAS served ({x['served_200']}), so the guard is not "
          f"simply refusing everything")
    check(not r["broken"], f"nothing broken ({r['broken']})")

    # The harness must be able to report a break, or the clean result above is decoration.
    probe = dict(r, cross_tenant=dict(x, cross_tenant_rows_seen=["a-matter-1"]))
    probe["broken"] = ["1 cross-tenant row(s) visible"]
    check("BROKEN" in report(probe),
          "a leak IS reported as BROKEN when one exists")

    text = report(r)
    check("rls_integration" in text,
          "the report points at the live-server proof rather than standing in for it")
    check("not gated" in text, "...and says the latency figure is reported, not asserted")
    check(json.loads(json.dumps(r)) == r, "the result is JSON-serialisable")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    res = measure()
    if "--json" in sys.argv:
        print(json.dumps(res, indent=2))
    else:
        print(report(res))
    raise SystemExit(1 if res["broken"] else 0)
