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
        # A1. NOT retryable: a missing handler is a deployment that does not have the code,
        # and two more leases only learn the same thing. Straight to DEAD, with the reason.
        queue.fail(job.job_id, f"no handler for intent {job.intent!r}", retryable=False)
        return Outcome(job.run_id, FAILED, error=f"no handler for intent {job.intent!r}")

    store.set_run(job.run_id, status=RUNNING)

    started = monotonic()
    try:
        steps, result = handler(job.args)
    except Exception as e:                                        # noqa: BLE001
        store.set_run(job.run_id, status=FAILED,
                      result={"error": f"{type(e).__name__}: {e}"})
        # A1. Retryable: a handler that raised may have hit a transport error. `fail` decides
        # retry-with-backoff or DEAD, so the policy is not restated here.
        queue.fail(job.job_id, f"{type(e).__name__}: {e}")
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
            queue.fail(job.job_id, f"StepTimeout: {step.get('capability')} exceeded "
                                   f"{timeout_seconds}s")
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


# ── the long-lived service ───────────────────────────────────────────────────
#
# `drain` empties the queue and returns; this keeps going. The difference that matters is
# not the loop -- it is WHERE it is allowed to stop.

# How long to wait for work before looking again, when nothing wakes us. A fallback, not
# the mechanism: on Postgres a NOTIFY wakes the wait immediately, and this only bounds how
# stale the health numbers can get if a notification is ever missed.
IDLE_SECONDS = 5.0


@dataclass
class ServiceReport:
    jobs: int = 0
    idle_waits: int = 0
    stopped_because: str = ""

    def to_dict(self) -> dict:
        return {"jobs": self.jobs, "idle_waits": self.idle_waits,
                "stopped_because": self.stopped_because}


def serve(*, queue, store, handlers, worker: str = "w1", should_stop=None, wait=None,
          max_jobs: int | None = None, idle_seconds: float = IDLE_SECONDS,
          **kw) -> ServiceReport:
    """Claim and run until asked to stop. Returns what it did.

    **The stop is checked BETWEEN jobs and never inside one.** A worker that dropped a job
    half-finished on SIGTERM would leave a run RUNNING with steps written and no outcome,
    and the next worker to pick it up could not tell that from a crash. Finishing the job
    in hand costs at most one job's time and is the whole of "graceful" here.

    `should_stop` and `wait` are INJECTED, so this loop is tested without a database, a
    signal, or a real sleep -- the three things that make a service loop usually untested.
    `main()` supplies the real ones.
    """
    report = ServiceReport()
    stop = should_stop or (lambda: False)
    idle = wait or (lambda timeout: __import__("time").sleep(timeout))
    while True:
        if stop():
            report.stopped_because = "asked to stop"
            return report
        if max_jobs is not None and report.jobs >= max_jobs:
            report.stopped_because = f"reached max_jobs={max_jobs}"
            return report
        outcome = run_one(queue=queue, store=store, handlers=handlers, worker=worker, **kw)
        if outcome is not None:
            report.jobs += 1
            continue
        # Nothing claimable. Wait to be told, or time out and look again.
        if stop():
            report.stopped_because = "asked to stop"
            return report
        report.idle_waits += 1
        idle(idle_seconds)


def listen_waiter(url: str, channel: str | None = None):
    """A `wait(timeout)` backed by Postgres LISTEN/NOTIFY.

    Returns a waiter that blocks until a NOTIFY arrives on `channel` or `timeout` passes.
    The timeout is not a formality: a notification sent while nobody was listening is
    gone, so a worker that only ever woke on NOTIFY would sleep through the job that was
    enqueued during its last run. The poll is the floor, the notification is the speed.
    """
    import psycopg
    from gateway.jobs import NOTIFY_CHANNEL
    channel = channel or NOTIFY_CHANNEL          # one string, named in gateway/jobs.py
    conn = psycopg.connect(url, autocommit=True)
    conn.execute(f"LISTEN {channel}")

    def wait(timeout: float) -> None:
        import select
        select.select([conn], [], [], timeout)
        # Drain whatever arrived; the content is irrelevant, only that something did.
        conn.execute("SELECT 1")

    wait.close = conn.close                              # type: ignore[attr-defined]
    return wait


def main(argv=None) -> int:
    """The process. Signals here, never in `serve`.

    SIGTERM and SIGINT set a flag; `serve` reads it between jobs. launchd sends SIGTERM on
    `launchctl unload` and SIGKILL some seconds later, so finishing the job in hand has to
    be quick -- which it is, because `run_one` already caps a step at
    STEP_TIMEOUT_SECONDS.
    """
    import signal
    import sys
    from gateway.store import database_url, select
    from gateway.verbs import Context, queue_handlers
    from gateway.jobs import PostgresQueue, MemoryQueue

    argv = list(sys.argv if argv is None else argv)
    stopping = {"now": False, "why": ""}

    def _signal(signum, _frame):
        stopping["now"] = True
        stopping["why"] = signal.Signals(signum).name
        print(f"worker: {stopping['why']} received; finishing the job in hand",
              flush=True)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _signal)

    url = database_url()
    store = select()
    if url:
        queue = PostgresQueue(url, tenant_id=store.tenant_id)
        wait = listen_waiter(url)
    else:
        # A worker with no database is a worker whose queue vanishes on restart. Allowed
        # for a smoke test and said out loud, because "it ran and did nothing" and "there
        # was nothing to run" look identical in a log.
        print("worker: no PLACEDON_DATABASE_URL — running against an in-memory queue, "
              "which keeps nothing across a restart", flush=True)
        queue, wait = MemoryQueue(), None
    # `files` too, or the worker finds the vault_ingest handler and refuses NO_VAULT on
    # every document -- which is PENDING with a different reason, not progress. Defaulted
    # from PLACEDON_FILES_DIR by the same function the gateway uses, so a worker and a
    # gateway started from the same environment read the same directory rather than two.
    from gateway.app import default_file_store
    ctx = Context(store=store, queue=queue, files=default_file_store())
    report = serve(queue=queue, store=store, handlers=queue_handlers(ctx),
                   worker=f"launchd-{__import__('os').getpid()}",
                   should_stop=lambda: stopping["now"], wait=wait)
    report.stopped_because = stopping["why"] or report.stopped_because
    print(f"worker: stopped after {report.jobs} job(s) "
          f"({report.stopped_because or 'no reason recorded'})", flush=True)
    return 0


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

    # ── the long-lived service ──────────────────────────────────────────────
    from gateway.jobs import MemoryQueue

    def _svc(n_jobs: int):
        q, store2 = MemoryQueue(), MemoryBackend()
        for i in range(n_jobs):
            rid = str(uuid.uuid4())
            store2.write_run({"id": rid, "intent": "ask", "status": "PLANNED",
                              "steps": [], "propositions": []})
            q.enqueue(run_id=rid, intent="ask", args={"n": i})
        return q, store2

    _hand = {"ask": lambda args: ([{"capability": "research", "status": "ANSWERED"}],
                                  {"status": "ANSWERED", "answer": "x"})}

    # max_jobs bounds it, and the loop really stops.
    q3, s3 = _svc(5)
    r3 = serve(queue=q3, store=s3, handlers=_hand, max_jobs=2, wait=lambda t: None)
    check(r3.jobs == 2 and "max_jobs" in r3.stopped_because,
          f"serve stops at max_jobs ({r3.jobs}, {r3.stopped_because})")
    check(q3.depth() == 3, f"...leaving the rest QUEUED ({q3.depth()})")

    # It waits when the queue is empty rather than spinning.
    waits = []
    q4, s4 = _svc(1)
    serve(queue=q4, store=s4, handlers=_hand, wait=lambda t: waits.append(t),
          should_stop=lambda: len(waits) >= 2)
    check(waits and all(t == IDLE_SECONDS for t in waits),
          f"an empty queue WAITS rather than spinning, for IDLE_SECONDS ({waits})")

    # ── graceful: the stop is honoured BETWEEN jobs, never inside one ───────
    seen = []
    stop_after_first = {"n": 0}

    def _counting(args):
        seen.append(args.get("n"))
        stop_after_first["n"] += 1
        return [{"capability": "research", "status": "ANSWERED"}], {"status": "ANSWERED"}

    q5, s5 = _svc(4)
    r5 = serve(queue=q5, store=s5, handlers={"ask": _counting},
               should_stop=lambda: stop_after_first["n"] >= 1, wait=lambda t: None)
    check(r5.jobs == 1 and len(seen) == 1,
          f"a stop requested during the first job lets THAT job finish and starts no "
          f"other ({r5.jobs} run, {len(seen)} handler call(s))")
    check(q5.depth() == 3,
          "...and the unstarted jobs are still QUEUED, not failed: nothing went wrong "
          "with them")
    _ran = [r for r in s5.runs.values() if r.get("status") == "ANSWERED"]
    check(len(_ran) == 1,
          "...and exactly one run reached a terminal state. A worker that dropped a job "
          "half-finished would leave a run RUNNING with steps and no outcome, which the "
          "next worker cannot tell from a crash")
    check(r5.stopped_because == "asked to stop", "...and it says why it stopped")

    # ── the crash property: killed mid-job, the job finishes EXACTLY once ───
    # A kill is a worker that claims and never finishes. The lease is what makes that
    # recoverable, and the step key is what stops the retry writing a second time.
    q6, s6 = _svc(1)
    rid6 = next(iter(s6.runs))
    held = q6.claim(worker="doomed", lease_seconds=60)     # claimed and held
    check(held is not None and q6.claim(worker="other") is None,
          "a claimed job is not claimable by anyone else while the lease holds")
    # Now the "kill": the lease lapses with the job never finished.
    q6.jobs[held.job_id]["lease_expires_at"] = q6._now()
    o6 = run_one(queue=q6, store=s6, handlers=_hand, worker="restarted")
    check(o6 is not None and o6.run_id == rid6,
          f"once the lease EXPIRES a restarted worker claims and runs the SAME job -- "
          f"which is what makes a killed worker recoverable rather than a lost job "
          f"({o6 and o6.run_id == rid6})")
    terminal = [r for r in s6.runs.values() if r.get("status") in ("ANSWERED", "FAILED")]
    check(len(terminal) == 1,
          f"**the run reaches a terminal state exactly once** ({len(terminal)})")
    steps6 = (s6.read_run(rid6) or {}).get("steps") or []
    check(len([x for x in steps6 if x.get("capability") == "research"]) == 1,
          f"...and the step is written ONCE despite two attempts: the idempotency key is "
          f"derived from (run_id, capability), so the replay is a no-op "
          f"({len(steps6)} step(s))")

    check(IDLE_SECONDS > 0,
          "the idle wait is a FALLBACK with a real timeout: a NOTIFY sent while nobody "
          "was listening is gone, so a worker that only woke on notifications would sleep "
          "through the job enqueued during its last run")
    # Read from the PARSED function, not its text: the first version of this grepped the
    # source for "signal" and failed on the word in serve's own docstring -- the same
    # prose-for-structure mistake this repo has made five times.
    import ast as _ast
    import inspect as _inspect
    _tree = _ast.parse(_inspect.getsource(serve))
    _names = {n.id for n in _ast.walk(_tree) if isinstance(n, _ast.Name)}
    _attrs = {n.attr for n in _ast.walk(_tree) if isinstance(n, _ast.Attribute)}
    _imports = {a.name.split(".")[0] for n in _ast.walk(_tree)
                if isinstance(n, _ast.Import) for a in n.names}
    check("signal" not in _names | _imports and not {"SIGTERM", "SIGINT"} & _attrs,
          f"serve installs NO signal handler and imports no signal module: `should_stop` "
          f"is injected, which is what lets this loop be tested without a signal, a "
          f"database or a real sleep ({sorted(_imports)})")
    check("signal" in {a.name.split(".")[0] for n in _ast.walk(_ast.parse(
              _inspect.getsource(main))) if isinstance(n, _ast.Import) for a in n.names},
          "...while main() DOES import signal: the process handles signals, the loop does "
          "not")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    # `--serve` runs the service; BARE runs the tests. That looks backwards for a service
    # module and is deliberate: scripts/run_tests.sh invokes this file as
    # "gateway/worker.py" with no flag, so making the service the default would have the
    # gate start a worker and block until the timeout, on every run, for ever. The flag
    # costs one word in the launchd plist and removes that entirely.
    import sys as _sys
    if "--serve" in _sys.argv:
        raise SystemExit(main())
    _test()
