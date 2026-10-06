#!/usr/bin/env python3
"""MA1: what a supervisor may propose, and the four reasons code refuses it.

`agents/plans.py` holds the FIXED pipelines: one plan per intent, declared in advance, the
same tuple every time. This is the other thing — a supervisor proposing a fan-out for a
question nobody wrote a template for — and the whole of this module is the part that says no.

## Why a schema at all

A supervisor is a model. A plan it proposes is a model's output, which means it is a
suggestion and not an instruction, and `docs/architecture/PLATFORM_FEATURES_AND_INTEGRATIONS.md`
§5 bounds it for the obvious reason: an unbounded fan-out is an unbounded bill, and an
unbounded bill arrives as a surprise rather than as a decision.

Four bounds, each with its own refusal:

    UNKNOWN_AGENT          only agents declared HERE may be used
    TOO_MANY_WORKERS       at most eight, and the cap is a written number
    WORKER_SPAWNS_WORKERS  a worker may not be an agent that can fan out
    NO_BUDGET              the worst case must fit, reserved before anything runs

## Registered agents only, and why a list rather than a scan

`WORKER_AGENTS` is written out. A registry built by scanning `agents/` would grow silently:
a module added for one purpose becomes a thing a model may invoke, and nobody decided that.
The list is the decision, and `_test` asserts every name in it resolves to a real module --
so it cannot rot in the other direction either.

## No worker spawns workers

Structural, not a request a plan makes. `SPAWNING_AGENTS` names the agents that may fan out,
and a plan naming one as a WORKER is refused. A supervisor that could appoint a second
supervisor is a recursion whose depth is decided by a model, and the eight-worker cap would
then bound one level of a tree rather than the tree.

## The budget is RESERVED, not estimated

`validate` takes a budget and calls `reserve()` once per worker, holding each worst case
before anything runs. On any refusal it RELEASES everything it took: a validator that
charged for the plans it turned away would ratchet itself shut, which is the same reason
`budget.reserve` itself writes nothing when it refuses.

Run: PYTHONPATH=. python3 agents/multi_plan.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The agents a supervisor may fan out to. WRITTEN OUT, never scanned: a scan would make
# every module added to `agents/` into something a model may invoke, and nobody decided that.
WORKER_AGENTS = (
    "research_question",     # one legal question against the held corpus
    "review_document",       # SS-1/SS-2 checks over one filing
    "review_contract",       # one contract against the playbook
    "review_grid_cell",      # one cell of a review table
    "vault_ingest",          # read, classify, chunk and tag one document
)

# Agents that may themselves fan out. A plan naming one of these as a WORKER is refused: a
# supervisor that could appoint a second supervisor is a recursion whose depth a model
# decides.
SPAWNING_AGENTS = ("supervisor",)

# PLATFORM_FEATURES_AND_INTEGRATIONS.md §5. Eight, written down rather than derived, so
# raising it is a visible edit to this line and not a consequence of something else.
MAX_WORKERS = 8

# What one worker is assumed to cost at worst. The same shape as a review cell
# (`agents/review_grid.CELL_*`), because a worker sends one document's relevant text and
# asks one question -- not an average, which under-reserves half the time, and the half that
# matters.
WORKER_INPUT_TOKENS = 4_000
WORKER_MAX_TOKENS = 600

UNKNOWN_AGENT = "UNKNOWN_AGENT"
TOO_MANY_WORKERS = "TOO_MANY_WORKERS"
WORKER_SPAWNS_WORKERS = "WORKER_SPAWNS_WORKERS"
NO_BUDGET = "NO_BUDGET"
NO_WORKERS = "NO_WORKERS"
NOT_A_PLAN = "NOT_A_PLAN"

REFUSALS = (UNKNOWN_AGENT, TOO_MANY_WORKERS, WORKER_SPAWNS_WORKERS, NO_BUDGET,
            NO_WORKERS, NOT_A_PLAN)


@dataclass(frozen=True)
class Task:
    """One worker's job. `agent` must be in WORKER_AGENTS; `task` is what it is asked."""
    agent: str
    task: str

    def to_dict(self) -> dict:
        return {"agent": self.agent, "task": self.task}


@dataclass(frozen=True)
class MultiPlan:
    """A supervisor's proposal. Read-only workers, exactly one writer that merges."""
    goal: str
    workers: tuple[Task, ...]

    def to_dict(self) -> dict:
        return {"goal": self.goal, "workers": [w.to_dict() for w in self.workers],
                "worker_count": len(self.workers)}


@dataclass(frozen=True)
class Verdict:
    ok: bool
    code: str = ""
    reason: str = ""
    # Reservation ids held for an ACCEPTED plan, one per worker, for the runner to settle.
    # Empty on a refusal, and that is asserted: a refused plan holding money is the leak.
    reservations: tuple[str, ...] = ()
    reserved_inr: float = 0.0
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "reason": self.reason,
                "reservations": list(self.reservations),
                "reserved_inr": self.reserved_inr, "detail": self.detail}


def validate(plan, *, budget=None, max_workers: int = MAX_WORKERS) -> Verdict:
    """Accept or refuse one proposed plan. Never raises; refuses by naming a code.

    Cheap structural checks FIRST, the budget LAST. Reserving before checking the agent
    names would take money for a plan about to be refused for a typo -- and `budget.reserve`
    writes to a shared ledger, so a wasted reservation narrows the cap for everyone until it
    is released.
    """
    if not isinstance(plan, MultiPlan):
        return Verdict(False, NOT_A_PLAN,
                       f"a plan must be a MultiPlan, not {type(plan).__name__}. Refused "
                       f"rather than coerced: a dict shaped almost like a plan is the "
                       f"shape a model produces when it has misunderstood the question")
    if not str(plan.goal or "").strip():
        return Verdict(False, NOT_A_PLAN,
                       "a plan needs a goal. A fan-out with no stated purpose cannot be "
                       "reviewed by the lawyer who is about to pay for it")
    if not plan.workers:
        return Verdict(False, NO_WORKERS,
                       "a plan with no workers does nothing. Refused rather than run as an "
                       "empty success, which would look like a completed answer")

    if len(plan.workers) > max_workers:
        return Verdict(False, TOO_MANY_WORKERS,
                       f"{len(plan.workers)} workers, and the cap is {max_workers}. Every "
                       f"worker is a model call, so this is a bill and a queue depth rather "
                       f"than a bigger idea. Narrow the plan, or raise the cap deliberately",
                       detail={"proposed": len(plan.workers), "cap": max_workers})

    for i, w in enumerate(plan.workers):
        if not isinstance(w, Task) or not str(w.task or "").strip():
            return Verdict(False, NOT_A_PLAN,
                           f"worker {i} has no task. An agent invoked with nothing to do "
                           f"costs a call and returns a shrug")
        if w.agent in SPAWNING_AGENTS:
            return Verdict(False, WORKER_SPAWNS_WORKERS,
                           f"worker {i} is {w.agent!r}, which can fan out. A worker that "
                           f"spawns workers is a recursion whose depth a model decides, and "
                           f"the {max_workers}-worker cap would then bound one level of a "
                           f"tree rather than the tree",
                           detail={"worker": i, "agent": w.agent})
        if w.agent not in WORKER_AGENTS:
            return Verdict(False, UNKNOWN_AGENT,
                           f"worker {i} names {w.agent!r}, which is not a registered agent. "
                           f"Registered: {', '.join(WORKER_AGENTS)}. The list is a decision "
                           f"someone made, not a scan of what happens to be importable",
                           detail={"worker": i, "agent": w.agent,
                                   "registered": list(WORKER_AGENTS)})

    if budget is None:
        return Verdict(True, reason=(
            f"{len(plan.workers)} worker(s), every agent registered, none able to fan out. "
            f"NO BUDGET WAS CHECKED: nothing was reserved, so this plan is structurally "
            f"sound and not yet affordable"))

    taken: list[str] = []
    total = 0.0
    for i, w in enumerate(plan.workers):
        res = budget.reserve(input_tokens=WORKER_INPUT_TOKENS,
                             max_tokens=WORKER_MAX_TOKENS,
                             reservation_id=_reservation_id(plan, i))
        if res.id is None:
            # RELEASE everything already taken. A validator that charged for the plans it
            # turned away would ratchet itself shut -- the same reason `reserve` writes
            # nothing when it refuses.
            for rid in taken:
                budget.settle(rid, 0.0)
            return Verdict(False, NO_BUDGET,
                           f"worker {i} of {len(plan.workers)} could not be afforded: "
                           f"{res.verdict.reason} Nothing was reserved -- the "
                           f"{len(taken)} reservation(s) already taken were released, so a "
                           f"refused plan holds none of the firm's cap",
                           detail={"affordable_workers": i,
                                   "proposed": len(plan.workers)})
        taken.append(res.id)
        total += float(res.amount_inr or 0.0)
    return Verdict(True, reason=(
        f"{len(plan.workers)} worker(s), every agent registered, none able to fan out, and "
        f"the worst case is RESERVED before anything runs. The runner settles each "
        f"reservation at what its worker actually cost"),
        reservations=tuple(taken), reserved_inr=round(total, 4))


def _reservation_id(plan: MultiPlan, index: int) -> str:
    """A stable id per (plan, worker). HASHED, not truncated.

    `agents/review_grid.reservation_id_for_cell` learned this the hard way: slicing an
    identifier to fit destroyed the one property that made it an identifier, and two cells of
    one document collided.
    """
    import hashlib
    key = f"{plan.goal}\x00{index}\x00{plan.workers[index].agent}"
    return "ma1-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


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

    print("multi_plan")

    def plan_of(n: int, agent: str = "research_question") -> MultiPlan:
        return MultiPlan(f"answer a question with {n} workers",
                         tuple(Task(agent, f"sub-question {i}") for i in range(n)))

    # ── a sound plan is accepted ────────────────────────────────────────────
    good = validate(plan_of(3))
    check(good.ok and not good.code, f"a three-worker plan of registered agents is accepted "
                                     f"({good.code or 'accepted'})")
    check("NO BUDGET WAS CHECKED" in good.reason,
          f"...and with no budget passed it says so, rather than implying the plan is "
          f"affordable ({good.reason[:60]}…)")
    check(good.reservations == () and good.reserved_inr == 0.0,
          "...holding no reservations, because none were taken")

    # ── UNKNOWN_AGENT ───────────────────────────────────────────────────────
    for bad_name in ("research", "Research_Question", "", "os.system", "worker"):
        v = validate(MultiPlan("g", (Task(bad_name, "do it"),)))
        check(not v.ok and v.code == UNKNOWN_AGENT,
              f"{bad_name!r} is refused as an unregistered agent ({v.code})")
    v = validate(MultiPlan("g", (Task("research_question", "a"), Task("nope", "b"))))
    check(not v.ok and v.code == UNKNOWN_AGENT and v.detail["worker"] == 1,
          f"...and the refusal names WHICH worker, so a supervisor can fix one line "
          f"({v.detail})")
    check("not a scan of what happens to be importable" in v.reason,
          "...and says the registry is a decision rather than a scan")

    # ── TOO_MANY_WORKERS ────────────────────────────────────────────────────
    check(validate(plan_of(MAX_WORKERS)).ok,
          f"exactly {MAX_WORKERS} workers is accepted -- the cap is inclusive, which is a "
          f"thing an off-by-one would get wrong silently")
    over = validate(plan_of(MAX_WORKERS + 1))
    check(not over.ok and over.code == TOO_MANY_WORKERS,
          f"{MAX_WORKERS + 1} workers is refused ({over.code})")
    check(over.detail == {"proposed": MAX_WORKERS + 1, "cap": MAX_WORKERS},
          f"...reporting both numbers ({over.detail})")
    check(validate(plan_of(3), max_workers=2).code == TOO_MANY_WORKERS,
          "...and the cap is a parameter, so a caller may lower it but the default is the "
          "written one")
    check(MAX_WORKERS == 8, f"the cap is eight, as §5 says ({MAX_WORKERS})")

    # ── WORKER_SPAWNS_WORKERS ───────────────────────────────────────────────
    for spawner in SPAWNING_AGENTS:
        v = validate(MultiPlan("g", (Task("research_question", "a"),
                                     Task(spawner, "fan out again"))))
        check(not v.ok and v.code == WORKER_SPAWNS_WORKERS,
              f"a worker naming {spawner!r} is refused ({v.code})")
        check("a tree rather than the tree" in v.reason,
              "...because the cap would bound one level of a recursion rather than all of it")
    # Checked BEFORE the unknown-agent rule, so a spawner that is also unregistered is
    # refused for the RIGHT reason. The two messages lead to different fixes.
    check(validate(MultiPlan("g", (Task("supervisor", "x"),))).code
          == WORKER_SPAWNS_WORKERS,
          "a spawning agent that is also unregistered is refused as a SPAWNER, because that "
          "is the reason that matters and the other message would send someone to the wrong "
          "fix")

    # ── NO_WORKERS and NOT_A_PLAN ───────────────────────────────────────────
    check(validate(MultiPlan("g", ())).code == NO_WORKERS,
          "a plan with no workers is refused rather than run as an empty success")
    check(validate(MultiPlan("", (Task("research_question", "a"),))).code == NOT_A_PLAN,
          "a plan with no goal is refused: a fan-out with no stated purpose cannot be "
          "reviewed by the lawyer about to pay for it")
    check(validate({"goal": "g", "workers": []}).code == NOT_A_PLAN,
          "a DICT shaped almost like a plan is refused rather than coerced -- which is the "
          "shape a model produces when it has misunderstood the question")
    check(validate(MultiPlan("g", (Task("research_question", "   "),))).code == NOT_A_PLAN,
          "a worker with a blank task is refused: an agent invoked with nothing to do costs "
          "a call and returns a shrug")

    # ── NO_BUDGET, and nothing held after a refusal ─────────────────────────
    from datetime import date as _date
    from backend.budget import BudgetTracker, DAILY_CAP_INR

    class _Mem:
        """A dict ledger. The caps are MODULE constants, so a small cap is made by
        pre-spending rather than by constructing a cheaper tracker."""

        def __init__(self, data: dict | None = None) -> None:
            self.d = dict(data or {})

        def read(self) -> dict:
            return dict(self.d)

        def write(self, data: dict) -> None:
            self.d = dict(data)

    def held(t) -> dict:
        return {k: v for k, v in (t._state().get("reservations") or {}).items()
                if k.startswith("ma1-")}

    t = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
    v = validate(plan_of(3), budget=t)
    check(v.ok and len(v.reservations) == 3,
          f"an affordable plan reserves one worst case PER WORKER before anything runs "
          f"({len(v.reservations)})")
    check(v.reserved_inr > 0.0,
          f"...and reports what it is holding ({v.reserved_inr})")
    check(len(held(t)) == 3,
          f"...which is really outstanding in the ledger, not just reported ({len(held(t))})")
    for rid in v.reservations:
        t.settle(rid, 0.0)
    check(not held(t), "settled, so the next check starts clean")

    # Force the refusal by SPENDING most of the day's cap first, which is how a real
    # deployment reaches it. `DAILY_CAP_INR` is derived from the monthly figure, so this
    # stays correct if the cap moves.
    t3 = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
    t3.record_call(DAILY_CAP_INR * 0.97)
    poor = validate(plan_of(6), budget=t3)
    check(not poor.ok and poor.code == NO_BUDGET,
          f"a plan the remaining cap cannot cover is refused NO_BUDGET ({poor.code})")
    check(not held(t3),
          f"...and NOTHING is left reserved: the reservations already taken were RELEASED, "
          f"so a refused plan holds none of the firm's cap ({held(t3)})")
    check(poor.reservations == () and poor.reserved_inr == 0.0,
          f"...and the verdict reports none, so a caller cannot settle something that was "
          f"released ({poor.reservations})")
    check(poor.detail.get("proposed") == 6
          and poor.detail.get("affordable_workers", -1) >= 0,
          f"...naming how many WOULD have fitted, which is what a supervisor needs to "
          f"narrow the plan ({poor.detail})")

    # The structural checks run BEFORE the budget. A plan refused for a typo must not have
    # taken money on the way.
    t4 = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
    check(validate(MultiPlan("g", (Task("nope", "a"),)), budget=t4).code == UNKNOWN_AGENT
          and not held(t4),
          "a plan refused for an unregistered agent reserved NOTHING -- cheap checks first, "
          "because `budget.reserve` writes to a shared ledger and a wasted reservation "
          "narrows the cap for everyone until it is released")
    check(validate(plan_of(MAX_WORKERS + 1), budget=t4).code == TOO_MANY_WORKERS
          and not held(t4),
          "...and so did one refused for being too large")

    # ── the registry is real, and the ids are stable ────────────────────────
    import importlib
    for name in WORKER_AGENTS:
        mod = {"review_grid_cell": "review_grid"}.get(name, name)
        try:
            importlib.import_module(f"agents.{mod}")
            check(True, f"the registered agent {name!r} resolves to agents/{mod}.py, so the "
                        f"list cannot rot into names nothing implements")
        except ImportError as e:
            check(False, f"{name!r} is registered and agents/{mod}.py does not import ({e})")
    p = plan_of(2)
    check(_reservation_id(p, 0) == _reservation_id(p, 0)
          and _reservation_id(p, 0) != _reservation_id(p, 1),
          "a reservation id is stable per worker and distinct between workers -- hashed, "
          "because truncating an identifier to fit destroyed exactly that property for "
          "review cells")
    check(len(set(REFUSALS)) == len(REFUSALS) == 6,
          f"six refusal codes, all distinct ({REFUSALS})")
    def _poor_tracker():
        _t = BudgetTracker(_Mem(), today=_date(2026, 10, 5))
        _t.record_call(DAILY_CAP_INR * 0.97)
        return _t

    reachable = {validate(x, budget=b).code for x, b in (
        (plan_of(3), None), (MultiPlan("g", ()), None),
        (MultiPlan("g", (Task("nope", "a"),)), None),
        (MultiPlan("g", (Task("supervisor", "a"),)), None),
        (plan_of(MAX_WORKERS + 1), None),
        ({"not": "a plan"}, None),
        (plan_of(6), _poor_tracker()))}
    check(reachable == set(REFUSALS) | {""},
          f"every refusal code is REACHABLE, plus acceptance -- a refusal nothing returns is "
          f"a refusal that does not exist ({sorted(reachable)})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
