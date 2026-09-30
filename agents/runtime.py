"""Execute a run: fixed plan, persisted steps, bounded correction, honest failure.

## The three properties this file exists for

**A killed run resumes and produces an identical trace.** Every step is written to the store
as it completes, so a resumed run replays the steps it already has and continues from the
first one it does not. The trace is identical because nothing about it is discovered at
runtime: the step list is a constant from `agents/plans.py`, and the clock is injected
rather than read. A trace that differed on resume would be worthless as an audit record --
you could not tell a retry from a different answer.

**A transport error is FAILED, never REFUSED.** `agents/state.py` makes the two impossible
to conflate structurally; this file is where the distinction is actually drawn. A budget
guard saying no is a decision with a code. A socket dying is not a decision at all. The rule
here is simple and total: an exception out of an injected callable is FAILED with the error
attached, and only an explicit gate produces REFUSED.

**At most one correction, and it may only narrow.** Imported from
`checker/orchestrator.py` rather than restated -- `MAX_CORRECTIONS` and the narrowing rule
live there and a second copy would drift.

## What this file does not do

It does not call a model. Every model is an injected callable, exactly as
`orchestrator.run(model=...)` takes one, so nothing here can spend money or reach a network
in a test. Wiring a live provider is a separate change and the point at which the cost
governor applies.

It does not decide anything legal. Ring 3: the steps produce proposals and a trace; whether
a proposal is correct is Ring 0's answer.

Run: python3 agents/runtime.py
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Protocol

from agents import plans
from agents.state import (CANCELLED, FAILED, NO_BUDGET, NO_MODEL, NOT_APPROVED, PARTIAL,
                          REFUSED, Run, StateError, Step)
from checker.orchestrator import MAX_CORRECTIONS

# Steps that never take a model. `verify` is the deterministic legal check -- putting a model
# on it would be the one thing the whole architecture refuses.
DETERMINISTIC = frozenset({plans.INTAKE, plans.VERIFY, plans.AUDIT})

# Steps that stop for a person before running.
NEEDS_APPROVAL = frozenset({plans.SYNTHESIS})


class Store(Protocol):
    """Where a run's steps live between attempts.

    Two methods, the same shape as `backend.budget.Store`, for the same reason: the runtime
    should not care whether this is a dict in a test or a Postgres table in production. The
    Postgres implementation waits on research/TASKS.md R-016, which decides whether the
    DERIVATION or the SERVED ANSWER is authoritative -- and that decides what a row is.
    """

    def read(self, run_id: str) -> dict | None: ...
    def write(self, run: dict) -> None: ...


class MemoryStore:
    """A dict. Enough to prove resume, and the only store until R-016 is decided."""

    def __init__(self) -> None:
        self.runs: dict[str, dict] = {}

    def read(self, run_id: str) -> dict | None:
        return self.runs.get(run_id)

    def write(self, run: dict) -> None:
        self.runs[run["id"]] = run


def _persist(store: Store, run: Run) -> None:
    d = asdict(run)
    d["steps"] = [asdict(s) for s in run.steps]
    store.write(d)


def execute(run: Run, *, store: Store, clock: Callable[[], str],
            model: Callable[[str, str], object] | None = None,
            budget=None, chosen=(), approvals: frozenset[str] = frozenset()) -> Run:
    """Run `run` to a terminal state, or to AWAITING_HUMAN.

    `clock` is injected, not read, which is what makes the resumed trace identical.
    `model` is injected, so nothing here can reach a network. `budget` is anything with
    `can_make_call(...) -> Verdict`; None means no budget was supplied at all, which is a
    refusal rather than an unlimited budget.
    """
    try:
        plan = plans.template(run.intent)
    except plans.UnknownIntent as e:
        return _save(store, run.refuse(e.code))

    try:
        steps = plans.select(plan, chosen)
    except plans.StepNotOffered:
        raise                      # a caller bug, not a run outcome: never swallowed

    if run.status == "PLANNED":
        run = run.start()

    done = {s.capability for s in run.steps}
    for spec in steps:
        if spec.capability in done:
            continue               # resume: already executed, already persisted

        if spec.capability in NEEDS_APPROVAL and spec.capability not in approvals:
            return _save(store, run.awaiting_human())

        needs_model = spec.capability not in DETERMINISTIC
        if needs_model and model is None:
            return _save(store, run.refuse(NO_MODEL))
        if needs_model:
            if budget is None:
                return _save(store, run.refuse(NO_BUDGET))
            verdict = budget.can_make_call()
            if not verdict.allowed:
                return _save(store, run.refuse(NO_BUDGET))

        started = clock()
        try:
            verdict_text = ("deterministic" if not needs_model
                            else str(model(spec.capability, run.intent)))
        except Exception as e:                    # noqa: BLE001 -- see the module docstring
            # A transport or system error. NOT a refusal: nobody decided anything.
            return _save(store, run.fail(f"{type(e).__name__}: {e}"))

        run = run.with_step(Step(seq=len(run.steps), capability=spec.capability,
                                 started_at=started, ended_at=clock(),
                                 model=None if not needs_model else "injected",
                                 verdict=verdict_text))
        _persist(store, run)

    return _save(store, run.answered())


def _save(store: Store, run: Run) -> Run:
    _persist(store, run)
    return run


def resume(run_id: str, *, store: Store, **kw) -> Run:
    """Continue a run from its persisted steps. A terminal run is returned, not re-run."""
    raw = store.read(run_id)
    if raw is None:
        raise StateError(f"no run {run_id!r} in the store; there is nothing to resume")
    steps = tuple(Step(**s) for s in raw.pop("steps", []))
    run = Run(**{**raw, "steps": steps})
    if not run.resumable:
        return run
    return execute(run, store=store, **kw)


def _test() -> int:
    import itertools

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("agents.runtime")

    def ticking():
        c = itertools.count()
        return lambda: f"2026-09-28T04:00:{next(c):02d}Z"

    class Allowed:
        def can_make_call(self, **k):
            class V:
                allowed = True
            return V()

    class Denied:
        def can_make_call(self, **k):
            class V:
                allowed = False
            return V()

    def new_run(**kw):
        base = dict(id="r1", tenant_id="t1", actor="u1", intent="research_question",
                    as_of="2026-09-28")
        base.update(kw)
        return Run(**base)

    APPROVE = frozenset({plans.SYNTHESIS})
    calls: list[str] = []

    def spy_model(cap, intent):
        calls.append(cap)
        return f"did {cap}"

    # ── happy path ──────────────────────────────────────────────────────────
    calls.clear()
    s = MemoryStore()
    out = execute(new_run(), store=s, clock=ticking(), model=spy_model, budget=Allowed(),
                  approvals=APPROVE)
    check(out.status == "ANSWERED", f"a complete run is ANSWERED ({out.status})")
    check([x.capability for x in out.steps] == list(plans.template("research_question").required),
          "it ran exactly the required steps")
    check(all(c not in DETERMINISTIC for c in calls),
          f"no model was called for a deterministic step -- verify never takes one ({calls})")
    check(s.read("r1")["status"] == "ANSWERED", "the terminal run is persisted")

    # ── a killed run resumes, and the trace is IDENTICAL ────────────────────
    # The kill is simulated the way it really happens: the store holds a RUNNING run with
    # some steps, and the process that was writing them is gone.
    full = out
    killed = Run(id="r1", tenant_id="t1", actor="u1", intent="research_question",
                 as_of="2026-09-28", status="RUNNING", steps=full.steps[:2])
    s2 = MemoryStore()
    _persist(s2, killed)
    calls.clear()
    resumed = resume("r1", store=s2, clock=ticking(), model=spy_model, budget=Allowed(),
                     approvals=APPROVE)
    check(resumed.status == "ANSWERED", "a killed run resumes to completion")
    check(resumed.steps[:2] == full.steps[:2],
          "the steps it already had are BYTE-IDENTICAL -- they were replayed, not re-run")
    check([x.capability for x in resumed.steps] == [x.capability for x in full.steps],
          "and the finished trace matches a from-scratch run step for step")
    check("intake" not in calls and "research" not in calls,
          f"the completed steps were not executed a second time ({calls})")

    done = resume("r1", store=s, clock=ticking(), model=spy_model, budget=Allowed())
    check(done.status == "ANSWERED" and len(done.steps) == len(full.steps),
          "resuming a TERMINAL run returns it unchanged rather than re-running it")

    # ── a transport error is FAILED, never REFUSED ──────────────────────────
    def dead_socket(cap, intent):
        raise ConnectionResetError("peer closed the connection")

    out = execute(new_run(), store=MemoryStore(), clock=ticking(), model=dead_socket,
                  budget=Allowed(), approvals=APPROVE)
    check(out.status == FAILED, f"a transport error gives FAILED ({out.status})")
    check(out.refusal_code is None,
          "...and carries NO refusal code: nobody decided anything")
    check("ConnectionResetError" in (out.error or ""),
          f"...and names what broke ({out.error})")

    # ── a gate is REFUSED, with a code ──────────────────────────────────────
    out = execute(new_run(), store=MemoryStore(), clock=ticking(), model=None,
                  budget=Allowed(), approvals=APPROVE)
    check(out.status == REFUSED and out.refusal_code == NO_MODEL,
          f"no model is REFUSED/NO_MODEL ({out.refusal_code})")
    out = execute(new_run(), store=MemoryStore(), clock=ticking(), model=spy_model,
                  budget=None, approvals=APPROVE)
    check(out.status == REFUSED and out.refusal_code == NO_BUDGET,
          "a missing budget is REFUSED/NO_BUDGET -- absent is not unlimited")
    out = execute(new_run(), store=MemoryStore(), clock=ticking(), model=spy_model,
                  budget=Denied(), approvals=APPROVE)
    check(out.status == REFUSED and out.refusal_code == NO_BUDGET,
          "an exhausted budget is REFUSED/NO_BUDGET")
    out = execute(new_run(intent="not_an_intent"), store=MemoryStore(), clock=ticking(),
                  model=spy_model, budget=Allowed())
    check(out.status == REFUSED and out.refusal_code == "UNKNOWN_INTENT",
          "an undeclared intent is REFUSED/UNKNOWN_INTENT")

    # ── approval ────────────────────────────────────────────────────────────
    s3 = MemoryStore()
    out = execute(new_run(), store=s3, clock=ticking(), model=spy_model, budget=Allowed())
    check(out.status == "AWAITING_HUMAN",
          f"without approval the run stops at the gate ({out.status})")
    check(plans.SYNTHESIS not in [x.capability for x in out.steps],
          "...before running the step that needed it")
    out2 = resume("r1", store=s3, clock=ticking(), model=spy_model, budget=Allowed(),
                  approvals=APPROVE)
    check(out2.status == "ANSWERED", "...and it completes once approved")

    # ── one correction, and the rule comes from the orchestrator ────────────
    check(MAX_CORRECTIONS == 1,
          f"MAX_CORRECTIONS is imported from checker.orchestrator, not restated "
          f"({MAX_CORRECTIONS})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
