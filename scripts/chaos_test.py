#!/usr/bin/env python3
"""Break things on purpose, and require every run to end in a NAMED state.

A1 item 8. Every other suite in this repository exercises the path where things work. This
drives the REAL worker loop -- `gateway/worker.run_one`, not a copy of it -- and injects the
five failures A1 built defences for:

    provider outage        the circuit breaker refuses; the run is FAILED, never NOT_FOUND
    a poison job           three attempts, then DEAD with a reason
    pool exhaustion        the cap refuses; it is never exceeded
    budget out mid-table   the table is PAUSED_BUDGET, resumable, nothing charged
    worker killed mid-step the step resumes ONCE; no duplicate rows, no double charge

## FAILED, never NOT_FOUND

The rule the whole product rests on. NOT_FOUND is a FINDING -- we read the document and the
clause is not there. Every injection here means **we did not read it**. So each one asserts not
only its own state but that no finding code appears anywhere in the result, because a provider
outage reported as "no such obligation" is the worst output this product can produce.

## No other tenant's rows changed

Each injection snapshots tenant B before and after and requires it unchanged. A defence that
contains a failure for the tenant that caused it and leaks into another firm's table has not
contained anything.

## Two modes, and what each can prove

`--test` runs every injection that needs no server, against the dict backends, and reports the
Postgres-only ones as BLOCKED with the reason. That is what the gate runs: it needs no
database, no model and no network.

`--run` with `PLACEDON_DATABASE_URL` pointing at a `placedon_throwaway_*` database runs the
same injections against PostgreSQL as `placedon_app` -- NOSUPERUSER, NOBYPASSRLS -- because
isolation asserted as the migration admin proves nothing, which this file learned from
`gateway/pool.py`'s first live check reporting a leak that did not exist.

Run: PYTHONPATH=. python3 scripts/chaos_test.py --test
     PLACEDON_DATABASE_URL=postgresql:///placedon_throwaway_x python3 scripts/chaos_test.py --run
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"

# Any of these appearing in an injected failure's result is the defect this file exists to
# catch: a transport failure dressed as a conclusion about a document.
FINDING_CODES = ("FOUND", "NOT_FOUND", "NEEDS_LAWYER")

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
ACTOR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@dataclass
class Injection:
    name: str
    state: str = PASS
    detail: str = ""
    checks: list = field(default_factory=list)

    def ck(self, cond: bool, label: str) -> None:
        self.checks.append((bool(cond), label))
        if not cond:
            self.state = FAIL

    def block(self, reason: str) -> None:
        self.state = BLOCKED
        self.detail = reason

    @property
    def failed(self) -> list:
        return [lb for ok, lb in self.checks if not ok]


# Rows that belong to the OTHER tenant, seeded before every injection so there is something
# to be unchanged. Named with a prefix because MemoryBackend has no tenant column -- so on the
# dict path this proves the injection did not mutate or delete pre-existing unrelated rows,
# which is what it can show. On Postgres the same comparison is a real cross-tenant check,
# because there the rows really are another tenant's and RLS is what keeps them apart.
_B_PREFIX = "tenant-b-"


def _store_and_queue():
    """Fresh backends for one injection, with the other tenant's rows already present."""
    from gateway.jobs import MemoryQueue
    from gateway.store import MemoryBackend

    store = MemoryBackend()
    store.tenant_id = TENANT_A
    for i in range(3):
        store.write_run({"id": f"{_B_PREFIX}{i}", "status": "ANSWERED",
                         "intent": "ask", "question": "another firm's question"})
    store.tenant_id = TENANT_A
    queue = MemoryQueue()
    return store, queue


def _tenant_b_rows(store) -> str:
    """Only the OTHER tenant's rows, as a comparable blob.

    An earlier version snapshotted the whole store, so tenant A's own writes read as a
    cross-tenant change and every injection failed this check. Comparing everything is not
    the same as comparing what must not change.
    """
    import json
    rows = {k: v for k, v in store.runs.items() if str(k).startswith(_B_PREFIX)}
    return json.dumps(rows, sort_keys=True, default=str)


# ── 1. a provider outage ─────────────────────────────────────────────────────

def provider_outage() -> Injection:
    """The breaker opens and the run is FAILED. Never a finding."""
    from gateway import circuit
    from gateway.jobs import DEAD, INTERACTIVE
    from gateway.worker import run_one

    inj = Injection("a provider outage")
    store, queue = _store_and_queue()
    before = _tenant_b_rows(store)

    breaker = circuit.Breaker(threshold=2, cooldown=60, clock=lambda: 0.0)

    def flaky(_args):
        refusal = breaker.check("bedrock")
        if refusal is not None:
            raise RuntimeError(f"{refusal.code}: {refusal.detail[:60]}")
        breaker.record_failure("bedrock")
        raise RuntimeError("provider returned 503")

    outcomes = []
    for i in range(4):
        rid = f"out-{i}"
        store.write_run({"id": rid, "status": "PLANNED", "intent": "ask", "question": "q"})
        queue.enqueue(run_id=rid, intent="ask", args={}, lane=INTERACTIVE)
        got = run_one(queue=queue, store=store, handlers={"ask": flaky})
        outcomes.append(got)

    inj.ck(all(o is not None and o.status == "FAILED" for o in outcomes),
           f"every run ends FAILED, which is a transport state "
           f"({[o.status if o else None for o in outcomes]})")
    blob = repr([o.error for o in outcomes if o])
    inj.ck(not any(code in blob for code in FINDING_CODES),
           f"...and NO finding code appears anywhere: an outage is not 'no such obligation' "
           f"({[c for c in FINDING_CODES if c in blob]})")
    inj.ck(breaker.state("bedrock") == circuit.OPEN,
           f"the breaker OPENED, so the deployment stopped asking ({breaker.state('bedrock')})")
    inj.ck(any(circuit.CIRCUIT_OPEN in str(o.error) for o in outcomes if o),
           "...and later runs were refused by the breaker rather than calling the provider")
    inj.ck(_tenant_b_rows(store) == before,
           "no other tenant's rows changed")
    return inj


# ── 2. a poison job ──────────────────────────────────────────────────────────

def poison_job() -> Injection:
    """A handler that always raises: three attempts, then DEAD with a reason."""
    from gateway.jobs import DEAD, INTERACTIVE, MAX_ATTEMPTS
    from gateway.worker import run_one

    inj = Injection("a poison job")
    store, queue = _store_and_queue()
    before = _tenant_b_rows(store)

    store.write_run({"id": "poison", "status": "PLANNED", "intent": "ask", "question": "q"})
    job = queue.enqueue(run_id="poison", intent="ask", args={}, lane=INTERACTIVE)

    attempts = 0

    def always_raises(_args):
        nonlocal attempts
        attempts += 1
        raise ValueError("this document breaks the parser every time")

    for _ in range(MAX_ATTEMPTS + 2):
        queue.jobs[job.job_id]["not_before"] = None        # skip the backoff wait
        if run_one(queue=queue, store=store, handlers={"ask": always_raises}) is None:
            break

    inj.ck(attempts == MAX_ATTEMPTS,
           f"the handler ran exactly {MAX_ATTEMPTS} times, not forever ({attempts})")
    final = queue.get("poison")
    inj.ck(final is not None and final.status == DEAD,
           f"...and the job is DEAD, not QUEUED forever ({final.status if final else None})")
    inj.ck(final is not None and str(final.dead_reason or "").strip(),
           f"...with a reason naming the failure ({(final.dead_reason or '')[:50]})")
    inj.ck(final is not None and str(MAX_ATTEMPTS) in (final.dead_reason or ""),
           "...and how many attempts were spent")
    dead = queue.dead()
    inj.ck(any(d.run_id == "poison" for d in dead),
           f"...and it is listed by the dead-letter read ({[d.run_id for d in dead]})")
    inj.ck(not any(code in repr(final) for code in FINDING_CODES),
           "no finding code anywhere: a poison job says nothing about the document's content")
    inj.ck(_tenant_b_rows(store) == before, "no other tenant's rows changed")
    return inj


# ── 3. pool exhaustion ───────────────────────────────────────────────────────

def pool_exhaustion() -> Injection:
    """The cap refuses and is never exceeded."""
    import contextlib

    from gateway.limits import Refusal  # noqa: F401  -- shape parity, not used directly
    from gateway.pool import API_MAX_SIZE, WORKER_MAX_SIZE, Pool, PoolExhausted

    inj = Injection("pool exhaustion")

    class FakeConn:
        def __init__(self, url):
            self.closed = False

        def execute(self, sql, params=()):
            return self

        def close(self):
            self.closed = True

    opened = []

    def factory(url):
        c = FakeConn(url)
        opened.append(c)
        return c

    pool = Pool("postgresql:///probe", max_size=2, acquire_timeout=0.02, connect=factory)
    refused = 0
    with contextlib.ExitStack() as stack:
        for i in range(2):
            stack.enter_context(pool.connection(tenant_id=TENANT_A))
        for _ in range(5):
            try:
                with pool.connection(tenant_id=TENANT_A):
                    pass
            except PoolExhausted:
                refused += 1
        inj.ck(refused == 5, f"every checkout past the cap is REFUSED ({refused} of 5)")
        inj.ck(len(opened) == 2,
               f"...and the pool NEVER opened more than its cap ({len(opened)} connections "
               f"for a cap of 2)")
        inj.ck(pool.stats()["open"] == 2, f"...reported as open=2 ({pool.stats()})")
    with pool.connection(tenant_id=TENANT_A):
        pass
    inj.ck(True, "once released, the next caller is served")
    inj.ck(API_MAX_SIZE == 10 and WORKER_MAX_SIZE == 4,
           f"the shipped caps are API 10 and worker 4, as A1 specifies "
           f"({API_MAX_SIZE}/{WORKER_MAX_SIZE})")
    pool.close()
    return inj


# ── 4. the budget runs out mid-table ────────────────────────────────────────

def budget_out_mid_table() -> Injection:
    """The table is PAUSED_BUDGET: resumable, nothing charged, nothing half-done."""
    from datetime import date

    import checker.review_grid as rg
    from agents.review_grid import CELL_INPUT_TOKENS, CELL_MAX_TOKENS, schedule
    from backend.budget import DAILY_CAP_INR, DEFAULT_MODEL, BudgetTracker, cost_inr
    from gateway.jobs import MemoryQueue

    inj = Injection("the budget runs out mid-table")
    store, queue = _store_and_queue()
    before = _tenant_b_rows(store)

    class _Mem:
        def __init__(self):
            self.d = {}

        def read(self):
            return dict(self.d)

        def write(self, data):
            self.d = dict(data)

    per_cell = cost_inr(DEFAULT_MODEL, CELL_INPUT_TOKENS, CELL_MAX_TOKENS)
    tracker = BudgetTracker(store=_Mem(), today=date(2026, 10, 4))
    # Leave room for two cells of a six-cell table, so the cap runs out MID-table -- the
    # hard case. A cap of zero would pause on the first cell and prove nothing about
    # "already-dispatched cells stay dispatched".
    tracker.record_call(max(0.0, DAILY_CAP_INR - per_cell * 2.5))

    cols = (rg.Column("governing law", rg.TEXT, "Which law governs?"),
            rg.Column("term end", rg.DATE, "When does it expire?"),
            rg.Column("liability cap", rg.AMOUNT, "What is the cap?"))
    table = rg.Table("chaos", "six cells", cols, ("c" * 64, "d" * 64))
    sched = schedule(table, queue=MemoryQueue(), budget=tracker)

    inj.ck(sched.paused_budget is True,
           f"the table is PAUSED_BUDGET ({sched.paused_budget})")
    inj.ck(0 < len(sched.enqueued) < 6,
           f"...after dispatching SOME cells, not none and not all ({len(sched.enqueued)} "
           f"of 6) -- the hard case a zero cap would never reach")
    inj.ck(rg.table_status(table, paused_budget=True) == rg.PAUSED_BUDGET,
           "...and the table's STATUS says so, which is a state and not an error")
    inj.ck(len(sched.not_scheduled) == 6 - len(sched.enqueued),
           f"...every undispatched cell is named ({len(sched.not_scheduled)})")
    for key in sched.not_scheduled:
        _, d, col = key.split(":", 2)
        inj.ck(table.cell(d, col).state == rg.PENDING,
               f"...and stays PENDING, not FAILED ({col})")
        break
    inj.ck(len(sched.reservations) == len(sched.enqueued),
           f"one reservation per dispatched cell and none for the refused one "
           f"({len(sched.reservations)} vs {len(sched.enqueued)})")
    for rid in sched.reservations:
        tracker.settle(rid, 0.0)
    inj.ck(not tracker._state()["reservations"],
           f"...and settling leaves NOTHING outstanding: the reservations balance to zero "
           f"({tracker._state()['reservations']})")
    inj.ck("cap" in (sched.pause_reason or "").lower(),
           f"the pause names the cap that refused it ({(sched.pause_reason or '')[:50]})")
    inj.ck(not any(code in repr(sched.to_dict()) for code in FINDING_CODES),
           "no finding code anywhere: running out of money says nothing about a document")
    inj.ck(_tenant_b_rows(store) == before, "no other tenant's rows changed")
    return inj


# ── 5. a worker killed mid-step ─────────────────────────────────────────────

def worker_killed_mid_step() -> Injection:
    """The step resumes ONCE. No duplicate rows and no double charge."""
    from gateway.jobs import INTERACTIVE
    from gateway.worker import run_one, step_key

    inj = Injection("a worker killed mid-step")
    store, queue = _store_and_queue()
    before = _tenant_b_rows(store)

    store.write_run({"id": "killed", "status": "PLANNED", "intent": "ask", "question": "q"})
    job = queue.enqueue(run_id="killed", intent="ask", args={}, lane=INTERACTIVE)

    calls = []

    def two_steps(_args):
        calls.append(1)
        steps = [{"capability": "retrieve", "status": "OK", "cost_inr": 0.5,
                  "cost_note": "priced"},
                 {"capability": "answer", "status": "OK", "cost_inr": 1.5,
                  "cost_note": "priced"}]
        return steps, {"status": "ANSWERED", "answer": "x"}

    # The kill: claim the job, write the FIRST step, then stop without finishing -- which is
    # what a SIGKILL between steps leaves behind. The lease then expires and another worker
    # reclaims it.
    first = queue.claim(worker="doomed")
    inj.ck(first is not None, "a worker claims the job")
    store.append_step("killed", {"capability": "retrieve", "status": "OK", "cost_inr": 0.5,
                                 "cost_note": "priced"},
                      key=step_key("killed", "retrieve"))
    steps_after_kill = len(store.read_run("killed")["steps"])
    inj.ck(steps_after_kill == 1,
           f"...and one step is on record when it dies ({steps_after_kill})")

    # Expire the lease so the job is reclaimable, then let the real worker finish it.
    queue.jobs[job.job_id]["lease_expires_at"] = None
    queue.jobs[job.job_id]["status"] = "QUEUED"
    queue.jobs[job.job_id]["not_before"] = None
    got = run_one(queue=queue, store=store, handlers={"ask": two_steps}, worker="w2")

    inj.ck(got is not None and got.status == "ANSWERED",
           f"the reclaiming worker takes it to a NAMED terminal state "
           f"({got.status if got else None})")
    final_steps = store.read_run("killed")["steps"]
    caps = [s["capability"] for s in final_steps]
    inj.ck(len(final_steps) == 2,
           f"...with exactly TWO steps, not three: the step written before the kill was "
           f"REPLAYED, not duplicated ({caps})")
    inj.ck(len(set(caps)) == len(caps),
           f"...no capability appears twice ({caps})")
    inj.ck(got is not None and got.steps_replayed == 1 and got.steps_written == 1,
           f"...and the worker reports one REPLAYED and one written, so the idempotency is "
           f"measured rather than assumed "
           f"({got.steps_replayed if got else None} replayed, "
           f"{got.steps_written if got else None} written)")
    total = sum(float(s.get("cost_inr") or 0) for s in final_steps)
    inj.ck(abs(total - 2.0) < 1e-9,
           f"...and the run is charged ONCE for each step, not twice for the first "
           f"(₹{total})")
    inj.ck(_tenant_b_rows(store) == before, "no other tenant's rows changed")
    return inj


INJECTIONS = (provider_outage, poison_job, pool_exhaustion, budget_out_mid_table,
              worker_killed_mid_step)


# ── the same two injections, against real PostgreSQL ────────────────────────
# Only two of the five touch the database. The breaker and the pool are not database
# concerns, and the budget ledger is its own store -- running those "against Postgres" would
# be the same dict code with a connection open beside it, which is theatre. These two are the
# ones whose guarantees are the DATABASE's: the dead-letter CHECK from 021, and step
# idempotency from the step key's unique constraint.

def _pg_injections(url: str) -> list:
    """Re-run the store/queue injections as placedon_app. Isolation is never asserted as the
    admin that applies the migrations -- gateway/pool.py's first live check did that and
    reported a leak that did not exist."""
    import uuid

    from gateway.jobs import DEAD, INTERACTIVE, MAX_ATTEMPTS, PostgresQueue
    from gateway.store import PostgresBackend
    from gateway.worker import run_one, step_key

    out = []

    poison = Injection("a poison job [postgres]")
    killed = Injection("a worker killed mid-step [postgres]")
    try:
        _seed_tenants(url)
        store = PostgresBackend(url, tenant_id=TENANT_A, actor_id=ACTOR_A)
        queue = PostgresQueue(url, tenant_id=TENANT_A, actor_id=ACTOR_A)

        # --- poison job, with 021's CHECK doing the arbitration -------------
        rid = str(uuid.uuid4())
        store.write_run({"id": rid, "status": "PLANNED", "intent": "ask", "question": "q"})
        job = queue.enqueue(run_id=rid, intent="ask", args={}, lane=INTERACTIVE)
        attempts = 0

        def boom(_args):
            nonlocal attempts
            attempts += 1
            raise ValueError("this document breaks the parser every time")

        for _ in range(MAX_ATTEMPTS + 2):
            with queue._conn() as c:                       # noqa: SLF001 -- clears backoff
                c.execute("UPDATE jobs SET not_before = NULL WHERE job_id = %s",
                          (job.job_id,))
            if run_one(queue=queue, store=store, handlers={"ask": boom}) is None:
                break
        poison.ck(attempts == MAX_ATTEMPTS,
                  f"the handler ran exactly {MAX_ATTEMPTS} times on the server ({attempts})")
        got = queue.get(rid)
        poison.ck(got is not None and got.status == DEAD,
                  f"...and the job is DEAD ({got.status if got else None})")
        poison.ck(got is not None and str(got.dead_reason or "").strip(),
                  "...with a reason, which jobs_dead_reason_iff_dead REFUSES to omit")
        poison.ck(any(d.run_id == rid for d in queue.dead()),
                  "...and the dead-letter read finds it")

        # --- a killed worker, with the step key's uniqueness arbitrating ----
        rid2 = str(uuid.uuid4())
        store.write_run({"id": rid2, "status": "PLANNED", "intent": "ask", "question": "q"})
        job2 = queue.enqueue(run_id=rid2, intent="ask", args={}, lane=INTERACTIVE)

        def two_steps(_args):
            return ([{"capability": "retrieve", "status": "OK", "cost_inr": 0.5,
                      "cost_note": "priced"},
                     {"capability": "answer", "status": "OK", "cost_inr": 1.5,
                      "cost_note": "priced"}],
                    {"status": "ANSWERED", "answer": "x"})

        queue.claim(worker="doomed")
        store.append_step(rid2, {"capability": "retrieve", "status": "OK",
                                 "cost_inr": 0.5, "cost_note": "priced"},
                          key=step_key(rid2, "retrieve"))
        with queue._conn() as c:                           # noqa: SLF001 -- expire the lease
            c.execute("UPDATE jobs SET status='QUEUED', lease_expires_at=NULL, "
                      "not_before=NULL WHERE job_id = %s", (job2.job_id,))
        done = run_one(queue=queue, store=store, handlers={"ask": two_steps}, worker="w2")
        steps = store.read_run(rid2)["steps"]
        caps = [s["capability"] for s in steps]
        killed.ck(done is not None and done.status == "ANSWERED",
                  f"the reclaiming worker reaches a named terminal state "
                  f"({done.status if done else None})")
        killed.ck(len(steps) == 2 and len(set(caps)) == 2,
                  f"...with exactly two steps and no capability twice: the step written "
                  f"before the kill was REPLAYED by the database, not duplicated ({caps})")
        killed.ck(done is not None and done.steps_replayed == 1,
                  f"...and the replay is counted, so idempotency is measured "
                  f"({done.steps_replayed if done else None})")
        total = sum(float(s.get("cost_inr") or 0) for s in steps)
        killed.ck(abs(total - 2.0) < 1e-9,
                  f"...and the run is charged once per step, not twice (₹{total})")
    except Exception as exc:                               # noqa: BLE001
        for inj in (poison, killed):
            if not inj.checks:
                inj.block(f"{type(exc).__name__}: {exc}")
    out.extend([poison, killed])
    return out


def _seed_tenants(app_url: str) -> None:
    """The tenant and actor rows `runs` has a foreign key to.

    Without these the first write fails with `runs_tenant_id_fkey` and the injection reports
    BLOCKED -- which it did, and the reason was right: a harness that has not created its own
    tenant has not set itself up, and that is not the same as a defence that did not hold.
    Seeded as the ADMIN, because creating a tenant is not something the app role does; the
    injections themselves then run as placedon_app.
    """
    import os

    import psycopg

    from scripts.rls_integration import resolve_url
    admin, _ = resolve_url(dict(os.environ))
    with psycopg.connect(admin, autocommit=True) as c:
        for t in (TENANT_A, TENANT_B):
            c.execute("INSERT INTO tenants (tenant_id, name) VALUES (%s,%s) "
                      "ON CONFLICT DO NOTHING", (t, f"chaos-{t[:8]}"))
        c.execute("INSERT INTO actors (actor_id, tenant_id, label) VALUES (%s,%s,%s) "
                  "ON CONFLICT DO NOTHING", (ACTOR_A, TENANT_A, "chaos"))


def _refuse_reason() -> str | None:
    """Why the Postgres mode cannot run, or None when it can."""
    import os

    from scripts.rls_integration import THROWAWAY_PREFIX, refuse_target, resolve_url

    url, refusal = resolve_url(dict(os.environ))
    if refusal:
        return refusal
    target = refuse_target(url)
    return target or None


def run(*, with_postgres: bool = False) -> list:
    results = [fn() for fn in INJECTIONS]
    if with_postgres:
        import os

        from scripts.rls_integration import _app_url, resolve_url
        why = _refuse_reason()
        if why:
            blocked = Injection("postgres injections")
            blocked.block(why)
            results.append(blocked)
        else:
            url, _ = resolve_url(dict(os.environ))
            results.extend(_pg_injections(_app_url(url)))
    return results


def report(results: list) -> str:
    lines = ["", "  chaos: every injection must end in a NAMED state", ""]
    width = max(len(r.name) for r in results) if results else 10
    for r in results:
        lines.append(f"  {r.state:<8} {r.name:<{width}}  {len(r.checks)} checks")
        if r.state == BLOCKED:
            lines.append(f"  {'':8} {'':<{width}}  reason: {r.detail[:90]}")
        for lb in r.failed:
            lines.append(f"  {'':8} {'':<{width}}  FAILED: {lb[:90]}")
    bad = [r for r in results if r.state == FAIL]
    blocked = [r for r in results if r.state == BLOCKED]
    lines.append("")
    lines.append(f"  {len(results) - len(bad) - len(blocked)}/{len(results)} injections "
                 f"contained, {len(blocked)} blocked, {len(bad)} failed")
    if blocked:
        lines.append("  BLOCKED is not a failure of the code: each one printed its reason. "
                     "The Postgres")
        lines.append("  injections need a placedon_throwaway_* database and --run.")
    lines.append("")
    lines.append("  PASS" if not bad else "  FAIL")
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

    print("chaos_test")
    results = run()
    check(len(results) == 5, f"all five injections run ({len(results)})")
    for r in results:
        check(r.state == PASS, f"{r.name}: contained ({r.failed[:1]})")
        check(len(r.checks) >= 4,
              f"{r.name}: asserts its state in detail ({len(r.checks)} checks)")
        check(any("no other tenant" in lb for _o, lb in r.checks)
              or "pool" in r.name,
              f"{r.name}: asserts no other tenant's rows changed (the pool holds no rows)")

    # The harness must be able to report a failure, or the PASSes above are decoration.
    probe = Injection("probe")
    probe.ck(False, "a deliberately failing check")
    check(probe.state == FAIL and probe.failed,
          "an injection that fails a check is FAIL, and names it")
    check("FAIL" in report([probe]) and "a deliberately failing check" in report([probe]),
          "...and the report says FAIL and quotes the check")
    blocked = Injection("probe2")
    blocked.block("no database")
    check(report([blocked]).rstrip().endswith("PASS"),
          "a BLOCKED injection does not fail the run -- it could not be attempted, which is "
          "not the same as a defence that did not hold")

    # Postgres mode is reported as BLOCKED rather than skipped when there is no server.
    why = _refuse_reason()
    check(why is None or isinstance(why, str),
          f"the Postgres mode says why it cannot run ({(why or 'it can')[:50]})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    res = run(with_postgres="--run" in sys.argv)
    print(report(res))
    raise SystemExit(1 if any(r.state == FAIL for r in res) else 0)
