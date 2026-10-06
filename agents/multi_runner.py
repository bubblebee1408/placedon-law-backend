#!/usr/bin/env python3
"""MA1: run a validated plan. Read-only workers fan out; ONE writer merges.

Move 15. `agents/multi_plan.validate` says whether a plan may run. This runs it, and the
interesting parts are all refusals and partial outcomes.

## Every result passes the verifier BEFORE any other agent sees it

This is the rule the whole design exists for. A worker's output is a model's output, and if
worker B can read worker A's unverified text then one hallucination becomes the premise of
four more -- and the merge at the end cannot tell which sentence was the original mistake.
So `run` verifies each result as it lands, and an unverified result is NEVER passed on. The
verifier is injected: this module calls no model and reaches for nothing.

## Two verifier rejections in a row make the branch NEEDS_LAWYER

Not three, not a retry ladder. A worker whose first answer failed verification and whose
second also failed is not having bad luck -- it is being asked something it cannot answer
from the evidence, and a third attempt spends money to learn the same thing. NEEDS_LAWYER is
what "a person has to look at this" means here, and it is the same word
`agents/review_grid.py` uses for the same reason.

## A worker that fails three times is dead-lettered, and the RUN is PARTIAL

`gateway/jobs.MAX_ATTEMPTS` is 3 and DEAD is already a terminal state distinct from FAILED.
A dead worker does not fail the run: the other seven answers are real and paid for. The run
is PARTIAL and **names the gap**, because a PARTIAL that did not say what was missing would
be read as a complete answer with fewer findings.

## Nothing here is parallel yet, and the module says so

The workers are READ-ONLY and may run in any order, which is what makes them parallelisable.
This runner executes them sequentially through an injected `call`. Parallelism is a property
of the executor the caller supplies, not of this file -- and claiming concurrency this does
not have would be the kind of thing the rest of this repository refuses. A-023.

Run: PYTHONPATH=. python3 agents/multi_runner.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agents import multi_plan as mp

# Two in a row, not three. See the module docstring: a third attempt spends money to learn
# the same thing.
VERIFY_STRIKES = 2

ANSWERED = "ANSWERED"
PARTIAL = "PARTIAL"
NEEDS_LAWYER = "NEEDS_LAWYER"
REFUSED = "REFUSED"

OUTCOMES = (ANSWERED, PARTIAL, NEEDS_LAWYER, REFUSED)

# Per-worker states.
W_OK = "OK"
W_NEEDS_LAWYER = "NEEDS_LAWYER"
W_DEAD = "DEAD"

WORKER_STATES = (W_OK, W_NEEDS_LAWYER, W_DEAD)


class Rejected(RuntimeError):
    """The verifier refused this result. Raised by a verifier, caught here."""


@dataclass(frozen=True)
class WorkerResult:
    index: int
    agent: str
    state: str
    text: str = ""
    attempts: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {"index": self.index, "agent": self.agent, "state": self.state,
                "text": self.text, "attempts": self.attempts, "reason": self.reason}


@dataclass(frozen=True)
class RunOutcome:
    status: str
    results: tuple[WorkerResult, ...] = ()
    merged: str = ""
    gaps: tuple[str, ...] = ()
    note: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Only ANSWERED. PARTIAL and NEEDS_LAWYER are NOT complete, and naming that here
        stops a caller reading "not refused" as "done"."""
        return self.status == ANSWERED

    def to_dict(self) -> dict:
        return {"status": self.status, "complete": self.complete,
                "results": [r.to_dict() for r in self.results],
                "merged": self.merged, "gaps": list(self.gaps),
                "note": self.note, "detail": self.detail}


def run(plan, *, call, verify, merge, budget=None, max_attempts: int = 3,
        reservations: tuple = ()) -> RunOutcome:
    """Run a validated plan. `call`, `verify` and `merge` are INJECTED.

      call(task)          -> text, or raises for a transport failure
      verify(text, task)  -> text (possibly narrowed); raises `Rejected` to refuse it
      merge(results)      -> the merged answer. Sees ONLY verified results.

    Injected rather than imported, so the gate runs this deterministically at a cost of ₹0
    and a worker runs it against whatever `gateway/models.py` serves. That is the same shape
    `agents/review_grid.run_cell` uses, for the same reason.

    `reservations` are the ids `validate` took. Each is settled as its worker finishes --
    including a dead one, which settles at 0.0 because it never billed.
    """
    # Validated WITHOUT the budget when the caller already reserved. `_reservation_id` is
    # stable per (goal, index, agent) -- deliberately, so a resumed plan cannot double-hold
    # -- which means re-reserving ids the caller is still holding raises "already
    # outstanding". Found by `runs.preview`'s own test: preview -> start -> result went
    # through validate twice and the second call collided with the first's reservations.
    #
    # The structural checks still run either way. What is skipped is only the reservation,
    # because the money is already held and taking it twice is the bug, not the check.
    verdict = mp.validate(plan, budget=(None if reservations else budget))
    if not verdict.ok:
        return RunOutcome(REFUSED, note=verdict.reason,
                          detail={"code": verdict.code, **verdict.detail})
    held = list(reservations or verdict.reservations)

    def settle(i: int, actual: float) -> None:
        if budget is not None and i < len(held):
            budget.settle(held[i], actual)

    results: list[WorkerResult] = []
    verified: list[WorkerResult] = []
    gaps: list[str] = []
    for i, task in enumerate(plan.workers):
        attempts = 0
        strikes = 0
        outcome = None
        while attempts < max_attempts:
            attempts += 1
            try:
                text = call(task)
            except Exception as e:                               # noqa: BLE001
                # A transport failure. Retried up to MAX_ATTEMPTS, exactly as the queue
                # does -- and the reason is kept, because a dead worker with no reason is
                # indistinguishable from one nobody looked at.
                outcome = WorkerResult(i, task.agent, W_DEAD, "", attempts,
                                       f"{type(e).__name__}: {str(e)[:140]}")
                continue
            try:
                checked = verify(text, task)
            except Rejected as e:
                strikes += 1
                outcome = WorkerResult(i, task.agent, W_NEEDS_LAWYER, "", attempts,
                                       f"the verifier refused this result: {str(e)[:140]}")
                if strikes >= VERIFY_STRIKES:
                    break
                continue
            outcome = WorkerResult(i, task.agent, W_OK, checked, attempts)
            break
        else:
            # The while loop ran out of attempts without breaking: every attempt was a
            # transport failure, so this worker is DEAD.
            outcome = WorkerResult(i, task.agent, W_DEAD, "", attempts,
                                   (outcome.reason if outcome else "")
                                   or f"gave up after {attempts} attempt(s)")

        if outcome.state == W_NEEDS_LAWYER and strikes >= VERIFY_STRIKES:
            outcome = WorkerResult(i, task.agent, W_NEEDS_LAWYER, "", attempts,
                                   f"the verifier refused {strikes} results in a row. A "
                                   f"worker asked something it cannot answer from the "
                                   f"evidence will not answer it on a third try, and "
                                   f"spending another call learns the same thing")
        results.append(outcome)
        # Settled whatever happened. A worker that died never billed, so 0.0; a worker that
        # answered is settled by the caller's accounting, which this module does not have --
        # so 0.0 here too, and the reservation is RELEASED rather than left outstanding.
        # Holding money for finished work is the leak move 3 measured at ₹2.00 a cell.
        settle(i, 0.0)
        if outcome.state == W_OK:
            verified.append(outcome)
        else:
            gaps.append(f"worker {i} ({task.agent}): {outcome.state} -- {outcome.reason}")

    # ONLY verified results reach the merger. An unverified result passed on would make one
    # hallucination the premise of the next worker's answer.
    merged = merge(tuple(verified)) if verified else ""

    if not verified:
        return RunOutcome(NEEDS_LAWYER, tuple(results), "", tuple(gaps), note=(
            "every worker either died or was refused by the verifier, so there is nothing "
            "to merge. Not an empty answer -- an empty answer would read as 'we looked and "
            "found nothing'"), detail={"verified": 0, "workers": len(results)})
    if any(r.state == W_NEEDS_LAWYER for r in results):
        return RunOutcome(NEEDS_LAWYER, tuple(results), merged, tuple(gaps), note=(
            f"{sum(1 for r in results if r.state == W_NEEDS_LAWYER)} branch(es) were "
            f"refused by the verifier twice in a row and a person has to look at them. The "
            f"{len(verified)} verified result(s) are merged and real; the gaps are named"),
            detail={"verified": len(verified), "workers": len(results)})
    if gaps:
        return RunOutcome(PARTIAL, tuple(results), merged, tuple(gaps), note=(
            f"{len(verified)} of {len(results)} workers answered and were verified. The "
            f"rest are NAMED above: a PARTIAL that did not say what was missing would be "
            f"read as a complete answer with fewer findings"),
            detail={"verified": len(verified), "workers": len(results)})
    return RunOutcome(ANSWERED, tuple(results), merged, (), note=(
        f"all {len(results)} workers answered and every result passed the verifier before "
        f"the merge saw it"), detail={"verified": len(verified), "workers": len(results)})


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

    print("multi_runner")

    def plan_of(n: int) -> mp.MultiPlan:
        return mp.MultiPlan("merge several sub-answers",
                            tuple(mp.Task("research_question", f"sub-question {i}")
                                  for i in range(n)))

    SEEN: list = []

    def merge(results) -> str:
        SEEN.append(tuple(r.index for r in results))
        return " | ".join(r.text for r in results)

    # ── everything answers and verifies ─────────────────────────────────────
    out = run(plan_of(3), call=lambda t: f"answer to {t.task}",
              verify=lambda text, t: text, merge=merge)
    check(out.status == ANSWERED and out.complete,
          f"three workers, all verified, is ANSWERED ({out.status})")
    check(len(out.results) == 3 and all(r.state == W_OK for r in out.results),
          "...with every worker OK")
    check(out.merged.count("|") == 2 and not out.gaps,
          f"...merged, with no gaps ({out.merged[:40]}…)")
    check(all(r.attempts == 1 for r in out.results),
          "...on one attempt each, so a passing worker is not retried")

    # ── the verifier gates the MERGE: only verified results are passed on ───
    SEEN.clear()

    def verify_odd(text, t):
        if "1" in t.task:
            raise Rejected("that span is not in the evidence")
        return text

    out = run(plan_of(3), call=lambda t: f"answer to {t.task}",
              verify=verify_odd, merge=merge)
    check(SEEN and 1 not in SEEN[-1],
          f"the merger NEVER saw the refused worker's result -- an unverified result passed "
          f"on makes one hallucination the premise of the next answer ({SEEN[-1]})")
    check(SEEN[-1] == (0, 2),
          f"...and it saw exactly the verified ones ({SEEN[-1]})")

    # ── two verifier rejections in a row -> NEEDS_LAWYER for that branch ────
    calls: dict = {}

    def count_calls(t):
        calls[t.task] = calls.get(t.task, 0) + 1
        return f"answer to {t.task}"

    out = run(plan_of(2), call=count_calls,
              verify=lambda text, t: (_ for _ in ()).throw(Rejected("not supported")),
              merge=merge)
    check(out.status == NEEDS_LAWYER,
          f"every branch refused twice gives NEEDS_LAWYER ({out.status})")
    check(all(r.attempts == VERIFY_STRIKES for r in out.results),
          f"...after exactly {VERIFY_STRIKES} attempts, not three: a worker asked something "
          f"it cannot answer will not answer it on a third try "
          f"({[r.attempts for r in out.results]})")
    check(all(v == VERIFY_STRIKES for v in calls.values()),
          f"...and the model was called exactly twice per worker, so the strike limit is "
          f"real money saved ({calls})")
    check("will not answer it on a third try" in out.results[0].reason,
          f"...and the reason says why ({out.results[0].reason[:60]}…)")
    check(not out.complete,
          "NEEDS_LAWYER is NOT complete, so a caller cannot read 'not refused' as 'done'")

    # One refused branch among several: NEEDS_LAWYER, and the good results are KEPT.
    out = run(plan_of(3), call=lambda t: f"answer to {t.task}",
              verify=verify_odd, merge=merge)
    check(out.status == NEEDS_LAWYER and out.merged,
          f"one refused branch among three is NEEDS_LAWYER and still MERGES the two that "
          f"were verified -- they are real and paid for ({out.status})")
    check(len(out.gaps) == 1 and "worker 1" in out.gaps[0],
          f"...with the gap NAMED ({out.gaps})")

    # ── a worker that fails three times is DEAD, and the run is PARTIAL ─────
    attempts_seen: dict = {}

    def flaky(t):
        attempts_seen[t.task] = attempts_seen.get(t.task, 0) + 1
        if "1" in t.task:
            raise ConnectionError("the model host closed the connection")
        return f"answer to {t.task}"

    out = run(plan_of(3), call=flaky, verify=lambda text, t: text, merge=merge)
    check(out.status == PARTIAL,
          f"a dead worker makes the run PARTIAL, not FAILED: the other answers are real and "
          f"paid for ({out.status})")
    check(out.results[1].state == W_DEAD and out.results[1].attempts == 3,
          f"...the worker is DEAD after three attempts, matching gateway/jobs.MAX_ATTEMPTS "
          f"({out.results[1].state}, {out.results[1].attempts})")
    check("ConnectionError" in out.results[1].reason,
          f"...and keeps the REASON: a dead worker with none is indistinguishable from one "
          f"nobody looked at ({out.results[1].reason[:50]}…)")
    check(len(out.gaps) == 1 and "DEAD" in out.gaps[0],
          f"...named in the gaps ({out.gaps})")
    check("would be read as a complete answer" in out.note,
          "...and the note says why naming the gap matters")
    check(not out.complete, "PARTIAL is not complete")

    # Every worker dead: NEEDS_LAWYER, not an empty ANSWERED.
    out = run(plan_of(2), call=lambda t: (_ for _ in ()).throw(TimeoutError("gone")),
              verify=lambda text, t: text, merge=merge)
    check(out.status == NEEDS_LAWYER and not out.merged,
          f"every worker dead is NEEDS_LAWYER with nothing merged -- an empty answer would "
          f"read as 'we looked and found nothing' ({out.status})")

    # ── a refused PLAN never runs a worker ──────────────────────────────────
    ran: list = []
    out = run(mp.MultiPlan("g", (mp.Task("nope", "x"),)),
              call=lambda t: ran.append(t) or "x",
              verify=lambda text, t: text, merge=merge)
    check(out.status == REFUSED and not ran,
          f"a plan the validator refuses runs NO worker and spends nothing ({out.status}, "
          f"{len(ran)} call(s))")
    check(out.detail.get("code") == mp.UNKNOWN_AGENT,
          f"...carrying the validator's own code ({out.detail.get('code')})")

    # ── reservations are settled, whatever happened ─────────────────────────
    from datetime import date as _date
    from backend.budget import BudgetTracker

    class _Mem:
        def __init__(self) -> None:
            self.d: dict = {}

        def read(self) -> dict:
            return dict(self.d)

        def write(self, data: dict) -> None:
            self.d = dict(data)

    def outstanding(t) -> dict:
        return {k: v for k, v in (t._state().get("reservations") or {}).items()
                if k.startswith("ma1-")}

    t = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
    out = run(plan_of(3), call=flaky, verify=lambda text, t: text, merge=merge, budget=t)
    check(out.status in (PARTIAL, ANSWERED),
          f"a budgeted run completes ({out.status})")
    check(not outstanding(t),
          f"...and leaves NOTHING reserved -- including for the worker that DIED, which "
          f"never billed. Holding money for finished work is the leak move 3 measured at "
          f"₹2.00 a cell ({outstanding(t)})")

    # ── a caller that already reserved is not charged twice ────────────────
    # `_reservation_id` is stable per (goal, index, agent), so re-reserving ids the caller
    # still holds raises "already outstanding". `run` therefore validates WITHOUT the budget
    # when `reservations` are supplied. Found by runs.preview's own test, not by reading.
    t5 = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
    v5 = mp.validate(plan_of(3), budget=t5)
    check(v5.ok and len(outstanding(t5)) == 3,
          f"the caller reserves three ({len(outstanding(t5))})")
    out5 = run(plan_of(3), call=lambda t: "a", verify=lambda x, t: x, merge=merge,
               budget=t5, reservations=v5.reservations)
    check(out5.status == ANSWERED,
          f"...and the run accepts them rather than reserving again ({out5.status})")
    check(not outstanding(t5),
          f"...settling exactly those, so the ledger balances to zero "
          f"({outstanding(t5)})")
    # And the structural checks still run on that path: a bad plan with reservations
    # supplied is still refused.
    _bad_with_res = run(mp.MultiPlan("g", (mp.Task("nope", "x"),)), call=lambda t: "a",
                        verify=lambda x, t: x, merge=merge, budget=t5,
                        reservations=("ma1-whatever",))
    check(_bad_with_res.status == REFUSED
          and _bad_with_res.detail.get("code") == mp.UNKNOWN_AGENT,
          "...while the structural checks still run on that path: what is skipped is the "
          "reservation, not the validation")

    # ── the vocabulary ──────────────────────────────────────────────────────
    check(len(set(OUTCOMES)) == 4 and len(set(WORKER_STATES)) == 3,
          f"four run outcomes, three worker states ({OUTCOMES}, {WORKER_STATES})")
    reach = {
        run(plan_of(2), call=lambda t: "a", verify=lambda x, t: x, merge=merge).status,
        run(plan_of(3), call=flaky, verify=lambda x, t: x, merge=merge).status,
        run(plan_of(2), call=lambda t: "a",
            verify=lambda x, t: (_ for _ in ()).throw(Rejected("no")),
            merge=merge).status,
        run(mp.MultiPlan("g", ()), call=lambda t: "a", verify=lambda x, t: x,
            merge=merge).status,
    }
    check(reach == set(OUTCOMES),
          f"every outcome is REACHABLE -- one nothing returns does not exist ({sorted(reach)})")
    check(VERIFY_STRIKES == 2, f"two strikes, as the design says ({VERIFY_STRIKES})")

    # Everything ran on injected callables. No model, no network, ₹0.
    # By AST, not by text. The first version searched the source for "import", which the
    # docstring's own word "imported" matched -- a check that can be defeated by prose.
    import ast as _ast
    import inspect as _inspect
    _tree = _ast.parse(_inspect.getsource(run).lstrip())
    _imports = [n for n in _ast.walk(_tree)
                if isinstance(n, (_ast.Import, _ast.ImportFrom))]
    check(not _imports,
          f"`run` contains NO import statement: `call`, `verify` and `merge` are injected, "
          f"so the gate runs this deterministically at ₹0 and a worker runs it against "
          f"whatever gateway/models.py serves ({len(_imports)} found)")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
