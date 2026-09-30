"""The durable executor. One job, one step at a time, resumable and cancellable.

PLAN_23 layer 3 and O2. What changed from executing inside the HTTP request: a run is now
exactly as durable as the DATABASE rather than as the socket that asked for it. Kill the
process mid-run and the work is not lost, not half-recorded, and not repeated.

## The four properties, and where each is enforced

**Resumable.** Every step is appended under a key derived from `(run_id, capability)`, so a
reclaimed job re-walks the same plan and each step it already wrote appends nothing.
`store.append_step` returns False in that case, which is how this file tells a replay from
new work without keeping any state of its own between attempts.

**No double-billing.** `cost_inr` rides on the step row, so a duplicate step IS a duplicate
charge. The idempotency key is the same control for both, deliberately: they cannot drift
apart because they are one write.

**A timeout is FAILED, never REFUSED.** `agents/state.py` says a refusal is a decision with
a nameable reason and a failure is not a decision at all. A step that ran out of time
decided nothing, so it is FAILED with the error attached. Writing `REFUSED / TIMEOUT` would
tell a lawyer we declined their question on its merits.

**Cancellation is a saga, not a kill.** The flag is read at a STEP BOUNDARY. Steps already
written stay exactly as they are; a final `CANCELLED` step is appended saying where it
stopped; the run is REFUSED with code CANCELLED. Nothing is deleted — a trace that hid the
work done before a cancellation would misrepresent what the tenant was charged for.

## What this file does not do

It does not decide what a step means. The handler for an intent is injected, and it is the
same callable the synchronous verb uses, so the queue path and the request path cannot
answer differently.

Run: PYTHONPATH=. python3 gateway/worker.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from gateway import jobs as q
from gateway.store import step_key

# Terminal run statuses this worker writes. Imported names would pull agents.state into the
# gateway ring for four strings; they are asserted equal to it in the self-test instead.
ANSWERED = "ANSWERED"
REFUSED = "REFUSED"
FAILED = "FAILED"
RUNNING = "RUNNING"

CANCELLED_CODE = "CANCELLED"

# A step that has not returned by now decided nothing. Not a tuning knob to raise quietly:
# it must stay under the queue's lease, or a worker finishes a step it no longer holds.
STEP_TIMEOUT_SECONDS = 90


class StepTimeout(TimeoutError):
    """A step ran out of time. A transport failure, never a refusal."""


@dataclass(frozen=True)
class Outcome:
    run_id: str
    status: str
    refusal_code: str | None = None
    steps_written: int = 0
    steps_replayed: int = 0
    error: str | None = None


def _now_iso(clock) -> str:
    return clock() if clock else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run_one(*, queue, store, handlers: dict[str, Callable], worker: str = "w1",
            clock=None, timeout_seconds: int = STEP_TIMEOUT_SECONDS,
            monotonic=time.monotonic) -> Outcome | None:
    """Claim one job and take it to a terminal state. None when the queue is empty.

    `handlers` maps an intent to `handler(args) -> (steps, result)`. It is injected so this
    module reaches no model and no network, exactly as `agents/runtime.py` injects one.
    """
    job = queue.claim(worker=worker)
    if job is None:
        return None

    handler = handlers.get(job.intent)
    if handler is None:
        # Not a refusal: nobody decided anything about the question. The deployment is
        # missing a handler, which is our fault and is reported as ours.
        store.set_run(job.run_id, status=FAILED, result=None)
        queue.finish(job.job_id, q.FAILED)
        return Outcome(job.run_id, FAILED, error=f"no handler for intent {job.intent!r}")

    store.set_run(job.run_id, status=RUNNING)

    started = monotonic()
    try:
        steps, result = handler(job.args)
    except Exception as e:                                        # noqa: BLE001
        store.set_run(job.run_id, status=FAILED,
                      result={"error": f"{type(e).__name__}: {e}"})
        queue.finish(job.job_id, q.FAILED)
        return Outcome(job.run_id, FAILED, error=f"{type(e).__name__}: {e}")

    written = replayed = 0
    for step in steps:
        # THE BOUNDARY. Checked before each step, never inside one: stopping mid-step would
        # leave a half-written step with no record of why, which is worse than one more.
        live = queue.get(job.run_id)
        if live is not None and live.cancel_requested:
            store.append_step(
                job.run_id,
                {"capability": step.get("capability", "?"), "status": "CANCELLED",
                 "cost_note": "a person cancelled the run before this step ran, so no "
                              "model was called and there is nothing to price"},
                key=step_key(job.run_id, f"cancel:{step.get('capability', '?')}"))
            store.set_run(job.run_id, status=REFUSED, refusal_code=CANCELLED_CODE,
                          result={"cancelled_before": step.get("capability")})
            queue.finish(job.job_id, q.CANCELLED)
            return Outcome(job.run_id, REFUSED, CANCELLED_CODE, written, replayed)

        if monotonic() - started > timeout_seconds:
            # FAILED, and the distinction is the point. See the module docstring.
            store.append_step(
                job.run_id,
                {"capability": step.get("capability", "?"), "status": "FAILED",
                 "cost_note": "the step did not return within the deployment's limit; no "
                              "cost is claimed for a call whose outcome is unknown"},
                key=step_key(job.run_id, f"timeout:{step.get('capability', '?')}"))
            store.set_run(job.run_id, status=FAILED, result={
                "error": f"StepTimeout: {step.get('capability')} exceeded "
                         f"{timeout_seconds}s"})
            queue.finish(job.job_id, q.FAILED)
            return Outcome(job.run_id, FAILED, None, written, replayed,
                           error=f"StepTimeout: {step.get('capability')}")

        key = step_key(job.run_id, step.get("capability", "?"))
        if store.append_step(job.run_id, step, key=key):
            written += 1
        else:
            replayed += 1

    status = result.get("status") if isinstance(result, dict) else None
    final = REFUSED if status == "REFUSED" else ANSWERED
    code = result.get("code") if final == REFUSED and isinstance(result, dict) else None
    store.set_run(job.run_id, status=final, refusal_code=code, result=result)
    queue.finish(job.job_id, q.DONE)
    return Outcome(job.run_id, final, code, written, replayed)


def drain(*, queue, store, handlers, limit: int = 100, **kw) -> list[Outcome]:
    """Work until the queue is empty. The shape a `while True` loop would have in a daemon,
    bounded so a test cannot spin."""
    out = []
    for _ in range(limit):
        o = run_one(queue=queue, store=store, handlers=handlers, **kw)
        if o is None:
            return out
        out.append(o)
    raise RuntimeError(f"drain() hit its limit of {limit} jobs; the queue is not draining")


# ── self-test ────────────────────────────────────────────────────────────────

def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    import uuid

    from agents import state as st
    from gateway.store import MemoryBackend

    check((ANSWERED, REFUSED, FAILED, RUNNING) ==
          (st.ANSWERED, st.REFUSED, st.FAILED, st.RUNNING),
          "the statuses written here are agents/state.py's, not a second vocabulary")
    check(CANCELLED_CODE in st.REFUSAL_CODES,
          "CANCELLED is a declared refusal code, so a cancelled run is REFUSED with a "
          "nameable reason rather than FAILED")
    check(STEP_TIMEOUT_SECONDS < q.DEFAULT_LEASE_SECONDS,
          f"the step timeout ({STEP_TIMEOUT_SECONDS}s) is under the queue lease "
          f"({q.DEFAULT_LEASE_SECONDS}s), or a worker finishes a step it no longer holds")

    THREE = [{"capability": "intake", "status": "ANSWERED", "cost_inr": None,
              "cost_note": "no model on this step"},
             {"capability": "document", "status": "ANSWERED", "provider": "azure",
              "region": "UAE North", "cost_inr": 0.05, "cost_note": "priced from tokens"},
             {"capability": "verify", "status": "ANSWERED", "cost_inr": None,
              "cost_note": "no model on this step"}]

    def fresh(steps=THREE, result=None):
        queue, store = q.MemoryQueue(), MemoryBackend()
        rid = str(uuid.uuid4())
        store.write_run({"id": rid, "intent": "review_document", "status": "PLANNED",
                         "steps": [], "propositions": []})
        queue.enqueue(run_id=rid, intent="review_document", args={"text": "t"})
        handlers = {"review_document": lambda a: (steps, result or {"doc_type": "minutes"})}
        return queue, store, rid, handlers

    # ── the ordinary path ───────────────────────────────────────────────────
    queue, store, rid, handlers = fresh()
    check(store.read_run(rid)["status"] == "PLANNED",
          "the run is PLANNED before a worker touches it -- POST returned an id, not an "
          "answer")
    o = run_one(queue=queue, store=store, handlers=handlers)
    check(o and o.status == ANSWERED and o.steps_written == 3,
          f"the worker takes it to ANSWERED, writing every step ({o and o.steps_written})")
    check(store.read_run(rid)["status"] == ANSWERED, "...and the run row says so")
    check(store.read_run(rid)["result"] == {"doc_type": "minutes"},
          "...and the result is there for a poller to read")
    check(run_one(queue=queue, store=store, handlers=handlers) is None,
          "...and an empty queue returns None rather than spinning")

    # ── THE CRASH TEST: kill mid-run, restart, identical trace ──────────────
    # A worker that dies after two steps. `attempts` is what makes the resumed run
    # recognisable; the trace is what must not change.
    now = [__import__("datetime").datetime(2026, 9, 30, 12, 0, tzinfo=
                                           __import__("datetime").timezone.utc)]
    queue = q.MemoryQueue(clock=lambda: now[0])
    store = MemoryBackend()
    rid = str(uuid.uuid4())
    store.write_run({"id": rid, "intent": "review_document", "status": "PLANNED",
                     "steps": [], "propositions": []})
    queue.enqueue(run_id=rid, intent="review_document", args={})

    class Killed(RuntimeError):
        pass

    def dies_after_two(args):
        def gen():
            yield THREE[0]
            yield THREE[1]
            raise Killed("kill -9")
        return gen(), {}

    try:
        run_one(queue=queue, store=store, handlers={"review_document": dies_after_two})
    except Killed:
        pass
    partial = store.read_run(rid)
    check(len(partial["steps"]) == 2,
          f"the crash left two steps written and durable ({len(partial['steps'])})")

    # The lease lapses; a new worker takes the SAME job and re-walks the SAME plan.
    now[0] += __import__("datetime").timedelta(seconds=q.DEFAULT_LEASE_SECONDS + 1)
    o2 = run_one(queue=queue, store=store, handlers={"review_document":
                                                     lambda a: (THREE, {"ok": True})},
                 worker="replacement")
    trace = store.read_run(rid)
    check(o2 and o2.status == ANSWERED, "the restarted worker completes the run")
    check(o2.steps_replayed == 2 and o2.steps_written == 1,
          f"...replaying the two it already had and writing only the third "
          f"({o2.steps_replayed} replayed, {o2.steps_written} written)")
    check([s["capability"] for s in trace["steps"]] == ["intake", "document", "verify"],
          f"...and the trace is IDENTICAL to an uninterrupted run "
          f"({[s['capability'] for s in trace['steps']]})")
    check(len(trace["steps"]) == 3, "...with no duplicate steps")
    costs = [s["cost_inr"] for s in trace["steps"] if s["cost_inr"]]
    check(costs == [0.05],
          f"...and the billed step is billed ONCE ({costs}): cost rides on the step row, so "
          f"a duplicate step would be a duplicate charge")
    check(queue.get(rid).attempts == 2,
          f"...while the attempt count records that a retry happened ({queue.get(rid).attempts})")

    # ── cancellation: a saga, at a boundary ─────────────────────────────────
    queue, store, rid, handlers = fresh()
    seen = []

    def cancel_after_first(args):
        def gen():
            yield THREE[0]
            queue.request_cancel(rid)       # a person clicks Cancel mid-run
            seen.append("cancelled")
            yield THREE[1]
            yield THREE[2]
        return gen(), {}

    o3 = run_one(queue=queue, store=store,
                 handlers={"review_document": cancel_after_first})
    t = store.read_run(rid)
    check(o3 and o3.status == REFUSED and o3.refusal_code == CANCELLED_CODE,
          f"a cancelled run is REFUSED with a nameable code ({o3 and o3.refusal_code}), "
          f"never FAILED -- a person decided this")
    caps = [s["capability"] for s in t["steps"]]
    statuses = [s["status"] for s in t["steps"]]
    check("intake" in caps and t["steps"][0]["status"] == "ANSWERED",
          f"...the work already done is KEPT, exactly as it was ({caps})")
    check("CANCELLED" in statuses,
          f"...and a CANCELLED step says where it stopped ({statuses})")
    check(len(t["steps"]) >= 2,
          "...so the trace shows both what ran and where it was stopped; nothing deleted")
    check(queue.get(rid).status == q.CANCELLED, "...and the job is CANCELLED, not retried")

    # ── a timeout is FAILED, and carries no refusal code ────────────────────
    queue, store, rid, handlers = fresh()
    ticks = iter([0.0, 0.0, 1000.0, 2000.0, 3000.0, 4000.0])
    o4 = run_one(queue=queue, store=store, handlers=handlers,
                 timeout_seconds=10, monotonic=lambda: next(ticks))
    row = store.read_run(rid)
    check(o4 and o4.status == FAILED and o4.refusal_code is None,
          f"a step timeout is FAILED with NO refusal code ({o4 and o4.status}/"
          f"{o4 and o4.refusal_code}) -- it decided nothing, and calling it a refusal "
          f"would tell a lawyer we declined on the merits")
    check("StepTimeout" in (o4.error or ""), "...and the error names the timeout")
    check(any(s["status"] == "FAILED" for s in row["steps"]),
          "...with a FAILED step in the trace saying which one did not return")
    check(all(s["cost_inr"] is None for s in row["steps"] if s["status"] == "FAILED"),
          "...and no cost claimed for a call whose outcome is unknown")

    # ── an unknown intent is the deployment's fault, reported as ours ───────
    queue, store, rid, _ = fresh()
    o5 = run_one(queue=queue, store=store, handlers={})
    check(o5 and o5.status == FAILED and o5.refusal_code is None,
          "a job with no handler is FAILED, not REFUSED: a missing handler is our defect, "
          "not a decision about the question")

    # ── a handler that raises is FAILED with the error attached ─────────────
    queue, store, rid, _ = fresh()
    def boom(args):
        raise ConnectionError("socket died")
    o6 = run_one(queue=queue, store=store, handlers={"review_document": boom})
    check(o6 and o6.status == FAILED and "ConnectionError" in (o6.error or ""),
          f"a transport error out of the handler is FAILED with the error ({o6 and o6.error})")
    check(store.read_run(rid)["refusal_code"] is None,
          "...and carries no refusal code, which agents/state.py would refuse to construct")

    # ── drain, and a handler whose result is itself a refusal ───────────────
    queue, store, rid, _ = fresh(result={"status": "REFUSED", "code": "NO_EVIDENCE"})
    outs = drain(queue=queue, store=store,
                 handlers={"review_document": lambda a: (THREE, {"status": "REFUSED",
                                                                 "code": "NO_EVIDENCE"})})
    check(len(outs) == 1 and outs[0].status == REFUSED
          and outs[0].refusal_code == "NO_EVIDENCE",
          "a handler that REFUSES gives a REFUSED run carrying its code, not ANSWERED")
    check(drain(queue=queue, store=store, handlers={}) == [],
          "...and draining an empty queue does nothing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
