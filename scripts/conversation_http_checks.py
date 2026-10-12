"""Deterministic overload, body-cap and file-race regressions; no model or network calls."""
from __future__ import annotations
import asyncio
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
from pathlib import Path


def _test():
    from gateway.admission import BoundedExecutor
    from gateway.app import create_app
    from gateway.auth import KeyStore
    from gateway.filestore import LocalFileStore
    from gateway.limits import Limiter, MAX_BODY_BYTES
    import gateway.verbs as verbs
    import httpx
    ok = fail = 0
    def check(cond, label):
        nonlocal ok, fail
        ok += bool(cond); fail += not bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    async def exercise():
        keys = KeyStore()
        key, _ = keys.mint(tenant_id="11111111-1111-1111-1111-111111111111", actor="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", role="admin")
        entered, release = threading.Event(), threading.Event()
        def work(args, ctx):
            if args.get("question") == "fail":
                raise RuntimeError("PRIVATE CLIENT TEXT secret-token")
            entered.set(); release.wait(5)
            return {"status": "ANSWERED", "answer": "fixture"}
        original = verbs.VERBS
        verbs.VERBS = tuple(replace(v, run=work) if v.name == "ask" else v for v in original)
        pool = BoundedExecutor(workers=2, per_tenant=1, readers=2, readers_per_tenant=1)
        try:
            app = create_app(keys=keys, db_url="", admission=pool)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + key}) as client:
                first = asyncio.create_task(client.post("/v2/ask", json={"question": "held request"}))
                check(await asyncio.to_thread(entered.wait, 2), "accepted work starts outside the event loop")
                blocked = await asyncio.gather(*[client.post("/v2/ask", json={"question": "burst"}) for _ in range(25)])
                check(all(r.status_code == 429 and r.headers.get("retry-after") for r in blocked), "25 simultaneous over-capacity requests receive recoverable 429 + Retry-After")
                health, sources = await asyncio.gather(client.get("/v1/health"), client.post("/v2/sources/list", json={}))
                # sources.list is generated as GET on this deployment.
                if sources.status_code == 405:
                    sources = await client.get("/v2/sources/list")
                check(health.status_code == 200, "health remains responsive while work is blocked")
                check(sources.status_code == 200, f"reserved read capacity serves source controls ({sources.status_code})")
                stream = await client.post("/v2/ask/stream", json={"question": "burst"})
                check(stream.status_code == 429, "SSE refuses overload before sending an accepted frame")
                release.set()
                check((await first).status_code == 200, "admitted work completes successfully")
                failure = await client.post("/v2/ask", json={"question": "fail"})
                check(failure.status_code == 503 and "PRIVATE" not in failure.text and "secret-token" not in failure.text, "exceptions return safe recovery copy without private details")
                oversized = await client.post("/v2/ask", content=b"{}", headers={"Content-Length": str(MAX_BODY_BYTES+1)})
                check(oversized.status_code == 413, "oversized declared request is refused before parsing")
                body_release = asyncio.Event()
                bodies_started = [asyncio.Event(), asyncio.Event()]
                async def slow_body(i):
                    yield b'{"question":"'
                    bodies_started[i].set()
                    await body_release.wait()
                    yield b'body test"}'
                uploads = [asyncio.create_task(client.post("/v2/ask", content=slow_body(i))) for i in range(2)]
                await asyncio.gather(*(event.wait() for event in bodies_started))
                third = await client.post("/v2/ask", json={"question": "third body"})
                check(third.status_code == 429, "body capacity refuses excess uploads before reading them")
                body_release.set()
                await asyncio.gather(*uploads)
                app.state.body_timeout_seconds = 0.02
                async def incomplete():
                    yield b'{'
                    await asyncio.Event().wait()
                expired = await client.post("/v2/ask", content=incomplete())
                check(expired.status_code == 408, "incomplete upload expires and releases its body slot")
                app.state.limiter = Limiter(burst=0)
                export = await client.get("/v2/drafts/example/export.docx")
                check(export.status_code == 429, f"binary downloads use the same rate limiter ({export.status_code})")
        finally:
            release.set(); pool.close(); verbs.VERBS = original
    asyncio.run(exercise())
    from gateway.jobs import MemoryQueue, QueueFull
    queue = MemoryQueue(max_pending=7)
    with ThreadPoolExecutor(max_workers=30) as callers:
        def enqueue(i):
            try:
                queue.enqueue(run_id=f"run-{i}", intent="test", args={})
                return True
            except QueueFull:
                return False
        accepted = list(callers.map(enqueue, range(100)))
    check(sum(accepted) == 7 and queue.depth() == 7, "atomic backlog cap admits exactly 7 of 100 simultaneous submissions")
    with ThreadPoolExecutor(max_workers=30) as callers:
        claims = list(callers.map(lambda i: queue.claim(worker=f"worker-{i}"), range(100)))
    claimed = [job.job_id for job in claims if job]
    check(len(claimed) == len(set(claimed)) == 7, "100 memory workers claim each admitted job once")
    with tempfile.TemporaryDirectory() as temp:
        store = LocalFileStore(Path(temp))
        data = b"synthetic duplicate document" * 10000
        with ThreadPoolExecutor(max_workers=30) as callers:
            hashes = list(callers.map(store.put, [data] * 100))
        check(len(set(hashes)) == 1 and store.get(hashes[0]) == data, "100 concurrent identical uploads preserve one complete readable file")
        check(not list(Path(temp).rglob("*.part")), "concurrent uploads leave no partial files")
    print(f"\n{ok}/{ok+fail} passed")
    return int(bool(fail))

if __name__ == "__main__":
    raise SystemExit(_test())
