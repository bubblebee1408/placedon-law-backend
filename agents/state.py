"""The vocabulary of a run, and the one distinction that must never blur.

## FAILED is not REFUSED

    REFUSED  we decided not to do it, and there is a reason we can name.
    FAILED   a socket died, a process was killed, a provider returned a 500.

Showing a transport error as a refusal tells a lawyer the system declined their question on
its merits. It did not. It fell over, and the honest answer is "try again", not "we will not
answer that". The reverse is worse still: a genuine refusal dressed as a glitch invites a
retry loop against a gate that is working correctly.

This is not left to callers to remember. `REFUSED` **requires** a code from `REFUSAL_CODES`,
`FAILED` **forbids** one, and `fail()` takes the transport error it is reporting. You cannot
construct a refusal without a reason or a failure with one.

## Statuses

Run:        PLANNED · RUNNING · AWAITING_HUMAN · ANSWERED · PARTIAL · REFUSED · FAILED
Proposition: VERIFIED · PARTIALLY_VERIFIED · UNVERIFIED · CONFLICTING · OUT_OF_SCOPE

Obligation states are NOT redefined here. They live in the legal core and this module has no
opinion about them -- restating them would create a second vocabulary that drifts.

Run: python3 agents/state.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

# ── run status ───────────────────────────────────────────────────────────────
PLANNED = "PLANNED"
RUNNING = "RUNNING"
AWAITING_HUMAN = "AWAITING_HUMAN"
ANSWERED = "ANSWERED"
PARTIAL = "PARTIAL"
REFUSED = "REFUSED"
FAILED = "FAILED"
RUN_STATUSES = (PLANNED, RUNNING, AWAITING_HUMAN, ANSWERED, PARTIAL, REFUSED, FAILED)
TERMINAL = (ANSWERED, PARTIAL, REFUSED, FAILED)

# ── proposition status ───────────────────────────────────────────────────────
VERIFIED = "VERIFIED"
PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
UNVERIFIED = "UNVERIFIED"
CONFLICTING = "CONFLICTING"
OUT_OF_SCOPE = "OUT_OF_SCOPE"
PROPOSITION_STATUSES = (VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, CONFLICTING, OUT_OF_SCOPE)

# ── refusal codes: every refusal names one ───────────────────────────────────
# An allowlist rather than free text, so a refusal cannot be invented at a call site and so
# a caller can branch on the reason without parsing prose.
NO_BUDGET = "NO_BUDGET"                  # the guard refused before any call
NO_MODEL = "NO_MODEL"                    # no route for the task, or the model is unavailable
UNKNOWN_INTENT = "UNKNOWN_INTENT"        # not in the declared list
OUT_OF_SCOPE_LAW = "OUT_OF_SCOPE_LAW"    # a body of law we do not hold
NOT_APPROVED = "NOT_APPROVED"            # a human declined at an approval gate
CANCELLED = "CANCELLED"                  # a human stopped the run
CORRECTIONS_EXHAUSTED = "CORRECTIONS_EXHAUSTED"
REFUSAL_CODES = (NO_BUDGET, NO_MODEL, UNKNOWN_INTENT, OUT_OF_SCOPE_LAW,
                 NOT_APPROVED, CANCELLED, CORRECTIONS_EXHAUSTED)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class StateError(ValueError):
    """A transition that must not happen. Raised rather than recorded."""


@dataclass(frozen=True)
class Step:
    """One executed step. Persisted; a resumed run replays these rather than re-running."""

    seq: int
    capability: str
    started_at: str
    ended_at: str
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_inr: float = 0.0
    verdict: str = ""
    refusal_code: str | None = None

    def __post_init__(self) -> None:
        if self.refusal_code is not None and self.refusal_code not in REFUSAL_CODES:
            raise StateError(f"{self.refusal_code!r} is not a declared refusal code")
        for name in ("started_at", "ended_at"):
            if not _ISO.match(getattr(self, name)):
                raise StateError(f"{name} must be an ISO-8601 UTC timestamp")


@dataclass(frozen=True)
class Proposition:
    id: str
    run_id: str
    text: str
    status: str
    cites: tuple = ()

    def __post_init__(self) -> None:
        if self.status not in PROPOSITION_STATUSES:
            raise StateError(f"{self.status!r} is not a proposition status")
        # A proposition asserting support must say where from. VERIFIED with no citation is
        # the shape this whole system exists to refuse.
        if self.status in (VERIFIED, PARTIALLY_VERIFIED) and not self.cites:
            raise StateError(
                f"a {self.status} proposition must carry citations; without them it is "
                f"UNVERIFIED, which is a real answer rather than a weaker version of this one")


@dataclass(frozen=True)
class Run:
    id: str
    tenant_id: str
    actor: str
    intent: str
    as_of: str
    status: str = PLANNED
    steps: tuple[Step, ...] = ()
    refusal_code: str | None = None
    error: str | None = None
    matter_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise StateError(f"{self.status!r} is not a run status; one of {RUN_STATUSES}")
        # The invariant this module exists for.
        if self.status == REFUSED and self.refusal_code not in REFUSAL_CODES:
            raise StateError(
                "REFUSED requires a code from REFUSAL_CODES. A refusal without a nameable "
                "reason is indistinguishable from a failure, and the two must never blur.")
        if self.status == FAILED:
            if self.refusal_code is not None:
                raise StateError(
                    "FAILED must NOT carry a refusal code. A transport or system error is not "
                    "a decision not to answer; reporting it as one tells the user we declined "
                    "their question on its merits.")
            if not self.error:
                raise StateError("FAILED must carry the transport or system error it reports")
        if self.status != REFUSED and self.refusal_code is not None:
            raise StateError(f"only a REFUSED run carries a refusal code (status={self.status})")

    # ── transitions: the only way to change status ──────────────────────────
    def start(self) -> "Run":
        if self.status != PLANNED:
            raise StateError(f"only a PLANNED run can start (status={self.status})")
        return replace(self, status=RUNNING)

    def with_step(self, step: Step) -> "Run":
        if self.status in TERMINAL:
            raise StateError(f"a {self.status} run is finished; it cannot gain a step")
        if step.seq != len(self.steps):
            raise StateError(
                f"step seq {step.seq} does not follow {len(self.steps)} existing steps: a "
                f"trace with a gap cannot be replayed, which is the point of persisting it")
        return replace(self, steps=self.steps + (step,))

    def refuse(self, code: str) -> "Run":
        """Decline, with a nameable reason. Never for a transport error -- use fail()."""
        if code not in REFUSAL_CODES:
            raise StateError(f"{code!r} is not a declared refusal code; one of {REFUSAL_CODES}")
        return replace(self, status=REFUSED, refusal_code=code, error=None)

    def fail(self, error: str) -> "Run":
        """A socket died, a process was killed, a provider 500'd. NOT a refusal."""
        if not error:
            raise StateError("fail() needs the error it is reporting")
        return replace(self, status=FAILED, error=error, refusal_code=None)

    def answered(self, *, partial: bool = False) -> "Run":
        return replace(self, status=PARTIAL if partial else ANSWERED)

    def awaiting_human(self) -> "Run":
        return replace(self, status=AWAITING_HUMAN)

    @property
    def resumable(self) -> bool:
        """A run that was killed mid-flight. Terminal runs are not resumed; they are read."""
        return self.status in (PLANNED, RUNNING, AWAITING_HUMAN)


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

    def attempt(fn):
        try:
            fn()
        except Exception as e:                      # noqa: BLE001
            return e
        return None

    print("agents.state")
    T = "2026-09-28T04:00:00Z"
    base = dict(id="r1", tenant_id="t1", actor="u1", intent="research_question",
                as_of="2026-09-28")

    # ── the invariant: FAILED is not REFUSED ────────────────────────────────
    r = Run(**base)
    check(r.status == PLANNED and r.resumable, "a new run is PLANNED and resumable")

    refused = r.refuse(NO_BUDGET)
    check(refused.status == REFUSED and refused.refusal_code == NO_BUDGET
          and refused.error is None,
          "refuse() gives REFUSED with a code and no error")
    failed = r.fail("ConnectionResetError: peer closed")
    check(failed.status == FAILED and failed.refusal_code is None and failed.error,
          "fail() gives FAILED with an error and NO refusal code")

    e = attempt(lambda: Run(**base, status=REFUSED))
    check(isinstance(e, StateError) and "without a nameable reason" in str(e),
          "a REFUSED run with no code is refused at construction")
    e = attempt(lambda: Run(**base, status=FAILED, error="x", refusal_code=NO_BUDGET))
    check(isinstance(e, StateError) and "not a decision not to answer" in str(e),
          "a FAILED run carrying a refusal code is refused -- the two cannot blur")
    e = attempt(lambda: Run(**base, status=FAILED))
    check(isinstance(e, StateError) and "transport" in str(e),
          "a FAILED run with no error is refused: FAILED must say what broke")
    e = attempt(lambda: Run(**base, status=ANSWERED, refusal_code=NO_BUDGET))
    check(isinstance(e, StateError), "only a REFUSED run may carry a refusal code")
    e = attempt(lambda: r.refuse("MADE_UP"))
    check(isinstance(e, StateError) and "declared refusal code" in str(e),
          "a refusal code invented at the call site is refused")

    # ── steps and replay ────────────────────────────────────────────────────
    s0 = Step(seq=0, capability="intake", started_at=T, ended_at=T)
    running = r.start().with_step(s0)
    check(running.status == RUNNING and len(running.steps) == 1, "a step is appended")
    e = attempt(lambda: running.with_step(Step(seq=5, capability="x",
                                               started_at=T, ended_at=T)))
    check(isinstance(e, StateError) and "cannot be replayed" in str(e),
          "a step with a gap in its seq is refused -- a trace with a hole is not a trace")
    e = attempt(lambda: refused.with_step(s0))
    check(isinstance(e, StateError) and "finished" in str(e),
          "a terminal run cannot gain a step")
    check(not refused.resumable and not failed.resumable and running.resumable,
          "terminal runs are read, not resumed")

    # ── propositions ────────────────────────────────────────────────────────
    e = attempt(lambda: Proposition(id="p", run_id="r1", text="x", status=VERIFIED))
    check(isinstance(e, StateError) and "UNVERIFIED, which is a real answer" in str(e),
          "a VERIFIED proposition with no citation is refused")
    p = Proposition(id="p", run_id="r1", text="x", status=UNVERIFIED)
    check(p.status == UNVERIFIED, "...while UNVERIFIED needs none: it claims nothing")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
