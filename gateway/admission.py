"""Bounded synchronous work, with reserved capacity for status/cancel reads.

Limits are per gateway process. Deployments with multiple replicas also need ingress
rate limits and database connection budgets. Cancelling an HTTP waiter does not release
its slot while the underlying thread is still running.
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial


class Busy(RuntimeError):
    """Work was not admitted; callers can retry the same request ID later."""


class BoundedExecutor:
    def __init__(self, *, workers: int = 8, per_tenant: int = 4,
                 readers: int = 4, readers_per_tenant: int = 2):
        if min(workers, per_tenant, readers, readers_per_tenant) < 1:
            raise ValueError("admission limits must be positive")
        self._limits = {False: (workers, per_tenant), True: (readers, readers_per_tenant)}
        self._pools = {kind: ThreadPoolExecutor(max_workers=count, thread_name_prefix="gateway-read" if kind else "gateway-work")
                       for kind, (count, _) in self._limits.items()}
        self._counts = {False: 0, True: 0}
        self._tenants: dict[tuple[bool, str], int] = {}
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, tenant: str, fn, *args, control: bool = False, **kwargs):
        """Admit immediately, or refuse without an unbounded executor queue."""
        key = (control, tenant)
        with self._lock:
            total, per_tenant = self._limits[control]
            if self._closed or self._counts[control] >= total or self._tenants.get(key, 0) >= per_tenant:
                raise Busy("Capacity is currently in use. No new work was started.")
            self._counts[control] += 1
            self._tenants[key] = self._tenants.get(key, 0) + 1
        def release(_):
            with self._lock:
                self._counts[control] -= 1
                remaining = self._tenants[key] - 1
                if remaining:
                    self._tenants[key] = remaining
                else:
                    self._tenants.pop(key, None)
        try:
            ctx = contextvars.copy_context()
            future = self._pools[control].submit(ctx.run, partial(fn, *args, **kwargs))
        except BaseException:
            release(None)
            raise
        future.add_done_callback(release)
        return future

    async def run(self, tenant: str, fn, *args, control: bool = False, **kwargs):
        future = self.submit(tenant, fn, *args, control=control, **kwargs)
        # shield protects the concurrent future's lifecycle after client disconnect.
        return await await_work(future)

    def close(self):
        with self._lock:
            self._closed = True
        for pool in self._pools.values():
            pool.shutdown(wait=False, cancel_futures=True)


async def await_work(future):
    """Keep running work accounted for after disconnect without unhandled exceptions."""
    wrapped = asyncio.wrap_future(future)
    try:
        return await asyncio.shield(wrapped)
    except asyncio.CancelledError:
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        raise


def _test() -> int:
    from concurrent.futures import ThreadPoolExecutor as TestPool
    ok = fail = 0
    def check(cond, label):
        nonlocal ok, fail
        ok += bool(cond)
        fail += not bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    pool = BoundedExecutor(workers=2, per_tenant=1, readers=1, readers_per_tenant=1)
    release = threading.Event()
    try:
        first = pool.submit("a", release.wait)
        try:
            pool.submit("a", lambda: None)
            blocked = False
        except Busy:
            blocked = True
        check(blocked, "a tenant cannot consume another tenant's work slot")
        second = pool.submit("b", release.wait)
        check(pool.submit("a", lambda: "status", control=True).result() == "status", "status remains reachable with all work slots busy")
        with TestPool(max_workers=20) as callers:
            def probe(_):
                try:
                    pool.submit("c", lambda: None)
                    return False
                except Busy:
                    return True
            check(all(callers.map(probe, range(50))), "50 simultaneous arrivals refuse before enqueue when full")
        release.set(); first.result(); second.result()
        check(pool.submit("a", lambda: 7).result() == 7, "capacity recovers after completion")
        def fail_work():
            raise ValueError("test")
        try:
            pool.submit("a", fail_work).result()
        except ValueError:
            pass
        check(pool.submit("a", lambda: 8).result() == 8, "exceptions release capacity")
    finally:
        release.set(); pool.close()

    async def cancellation():
        executor = BoundedExecutor(workers=1, per_tenant=1)
        done = threading.Event(); entered = threading.Event()
        def work():
            entered.set(); done.wait()
        task = asyncio.create_task(executor.run("a", work))
        await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            executor.submit("a", lambda: None)
            retained = False
        except Busy:
            retained = True
        finally:
            done.set(); executor.close()
        return retained
    check(asyncio.run(cancellation()), "cancelled HTTP waiter retains slot until work actually stops")
    print(f"\n{ok}/{ok+fail} passed")
    return int(bool(fail))

if __name__ == "__main__":
    raise SystemExit(_test())
