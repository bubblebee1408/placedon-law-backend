#!/usr/bin/env python3
"""A per-provider circuit breaker. An open breaker is a TRANSPORT failure, never a finding.

A1. When a provider starts refusing every call, the engine's default behaviour is to keep
asking: each run spends a lease, waits out a timeout and fails, and the next one does it
again. The breaker makes the deployment stop asking for a while.

## The distinction that matters most here

**An open breaker yields FAILED, never NOT_FOUND.** This repository already holds that line
elsewhere -- `agents/review_grid` asserts "an INJECTED transport error is the only route to
FAILED, and it is not a finding" -- and the breaker is the one new way to produce a transport
failure, so it is the one new way to get this wrong.

NOT_FOUND is a FINDING: we looked and the clause is not there. An open breaker means **we did
not look**. Reporting that as NOT_FOUND would write "no such obligation" into a review table on
the strength of a provider being down, which is the single worst output this product can
produce. So `Refusal.code` is `PROVIDER_CIRCUIT_OPEN`, its `outcome` is FAILED, and `_test()`
asserts both -- including that the code is not any of the finding codes.

## Three states, and why HALF_OPEN is not optional

    CLOSED     calls go through. Failures are counted.
    OPEN       calls are refused without being attempted, until the cooldown expires.
    HALF_OPEN  the cooldown has expired: ONE trial call is allowed through.

Without HALF_OPEN a breaker either stays open forever or reopens the floodgates on a timer. One
trial answers "is it back?" at the cost of one call; a success closes it, a failure re-opens it
for another cooldown. A breaker that reset to CLOSED on a timer would send the full load at a
provider that is still down, which is how a breaker makes an outage worse.

## Counted per provider, and successes reset the count

`FAILURE_THRESHOLD` consecutive failures opens it. CONSECUTIVE, because a provider that fails
one call in twenty is not down -- and a counter that never reset would open the breaker on a
provider that has been working for a month.

The clock is injected. A breaker tested with `sleep` is slow and still cannot reach the
boundary, which is the whole behaviour.

Run: PYTHONPATH=. python3 gateway/circuit.py --test
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

__all__ = ["Breaker", "Refusal", "CLOSED", "OPEN", "HALF_OPEN", "CIRCUIT_OPEN",
           "FAILURE_THRESHOLD", "COOLDOWN_SECONDS"]

CLOSED, OPEN, HALF_OPEN = "CLOSED", "OPEN", "HALF_OPEN"

# The refusal code. Deliberately NOT one of the finding codes: see the docstring.
CIRCUIT_OPEN = "PROVIDER_CIRCUIT_OPEN"

# Three in a row is a provider that is down, not a provider having a bad minute.
FAILURE_THRESHOLD = 3

# Long enough that a restarting provider has restarted; short enough that a brief blip does
# not cost a review table its afternoon.
COOLDOWN_SECONDS = 60


@dataclass(frozen=True)
class Refusal:
    """Why no call was made. `outcome` is FAILED because nothing was looked at."""
    code: str
    detail: str
    provider: str
    retry_after: int
    outcome: str = "FAILED"


@dataclass
class _State:
    failures: int = 0
    opened_at: float | None = None
    trial_in_flight: bool = False


@dataclass
class Breaker:
    threshold: int = FAILURE_THRESHOLD
    cooldown: int = COOLDOWN_SECONDS
    clock: object = time.monotonic
    _providers: dict = field(default_factory=dict)

    def _st(self, provider: str) -> _State:
        return self._providers.setdefault(provider, _State())

    def state(self, provider: str) -> str:
        st = self._st(provider)
        if st.opened_at is None:
            return CLOSED
        if float(self.clock()) - st.opened_at >= self.cooldown:
            return HALF_OPEN
        return OPEN

    def check(self, provider: str) -> Refusal | None:
        """None if a call may be made. A Refusal if the breaker is open.

        A HALF_OPEN breaker lets exactly ONE call through and then refuses again until that
        call reports back, so a hundred queued jobs do not all become the trial.
        """
        st = self._st(provider)
        where = self.state(provider)
        if where == CLOSED:
            return None
        if where == HALF_OPEN and not st.trial_in_flight:
            st.trial_in_flight = True
            return None
        left = max(1, int(self.cooldown - (float(self.clock()) - (st.opened_at or 0.0))) + 1)
        return Refusal(
            CIRCUIT_OPEN,
            f"{provider} failed {st.failures} calls in a row, so this deployment stopped "
            f"asking. No call was made, so nothing was looked at: this is a transport "
            f"failure and NOT a finding about the document",
            provider, retry_after=left)

    def record_success(self, provider: str) -> None:
        """A call worked. The breaker closes and the consecutive count resets."""
        self._providers[provider] = _State()

    def record_failure(self, provider: str) -> None:
        """A call failed on transport. Opens at the threshold; re-opens a failed trial."""
        st = self._st(provider)
        st.failures += 1
        if st.trial_in_flight:
            # The trial failed: the provider is still down. Re-open for another cooldown
            # rather than letting the next caller try again immediately.
            st.trial_in_flight = False
            st.opened_at = float(self.clock())
            return
        if st.failures >= self.threshold:
            st.opened_at = float(self.clock())

    def snapshot(self) -> dict:
        """Every provider's state. For usage reporting, not for deciding."""
        return {p: {"state": self.state(p), "failures": s.failures}
                for p, s in self._providers.items()}


def _test() -> int:
    import sys
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("circuit")

    def at(t0=0.0):
        now = [t0]
        return Breaker(clock=lambda: now[0]), now

    # ── it opens on CONSECUTIVE failures, not on a bad minute ───────────────
    b, now = at()
    check(b.check("bedrock") is None, "a fresh provider is CLOSED and calls go through")
    for _ in range(FAILURE_THRESHOLD - 1):
        b.record_failure("bedrock")
    check(b.check("bedrock") is None,
          f"...still closed below the threshold ({FAILURE_THRESHOLD - 1} of "
          f"{FAILURE_THRESHOLD} failures)")
    b.record_failure("bedrock")
    r = b.check("bedrock")
    check(r is not None and b.state("bedrock") == OPEN,
          "...and OPEN at the threshold")

    # ── the rule this file exists for ──────────────────────────────────────
    check(r.outcome == "FAILED",
          "an open breaker is a TRANSPORT failure: no call was made, so nothing was looked at")
    check(r.code == CIRCUIT_OPEN and "NOT_FOUND" not in r.code,
          f"...and its code is NOT a finding code ({r.code})")
    for finding in ("NOT_FOUND", "FOUND", "NEEDS_LAWYER", "PENDING"):
        check(r.code != finding,
              f"...specifically not {finding}: reporting a provider outage as a finding would "
              f"write a conclusion about a document nobody read")
    check("not a finding" in r.detail.lower(),
          "...and the reason says so in words, for whoever reads the trace")
    check(r.retry_after >= 1, f"...with a retry_after a caller can act on ({r.retry_after}s)")

    # ── per provider ───────────────────────────────────────────────────────
    check(b.check("sarvam") is None,
          "a DIFFERENT provider is unaffected -- one provider being down is not an outage")

    # ── a success resets the consecutive count ─────────────────────────────
    b2, _ = at()
    for _ in range(FAILURE_THRESHOLD - 1):
        b2.record_failure("gemini")
    b2.record_success("gemini")
    for _ in range(FAILURE_THRESHOLD - 1):
        b2.record_failure("gemini")
    check(b2.check("gemini") is None,
          "a success RESETS the count, so a provider that fails one call in twenty never "
          "opens -- a counter that never reset would open on a provider working for a month")

    # ── HALF_OPEN: one trial, not a flood ──────────────────────────────────
    b3, now3 = at()
    for _ in range(FAILURE_THRESHOLD):
        b3.record_failure("bedrock")
    check(b3.state("bedrock") == OPEN, "open after the threshold")
    now3[0] += COOLDOWN_SECONDS
    check(b3.state("bedrock") == HALF_OPEN,
          f"...and HALF_OPEN once the {COOLDOWN_SECONDS}s cooldown expires")
    check(b3.check("bedrock") is None, "...so ONE trial call is allowed through")
    second = b3.check("bedrock")
    check(second is not None,
          "...and the NEXT caller is still refused, so a hundred queued jobs do not all "
          "become the trial")

    # A failed trial re-opens for another cooldown rather than letting the next caller try.
    b3.record_failure("bedrock")
    check(b3.state("bedrock") == OPEN,
          "a FAILED trial re-opens the breaker -- resetting to CLOSED on a timer would send "
          "the full load at a provider that is still down, which makes an outage worse")
    now3[0] += COOLDOWN_SECONDS
    check(b3.check("bedrock") is None, "...and a second trial is allowed after the next wait")
    b3.record_success("bedrock")
    check(b3.state("bedrock") == CLOSED and b3.check("bedrock") is None,
          "a SUCCESSFUL trial closes the breaker and ordinary traffic resumes")

    # ── it is not merely refusing everything ───────────────────────────────
    b4, _ = at()
    allowed = sum(1 for _ in range(50) if b4.check("voyage") is None)
    check(allowed == 50,
          f"fifty calls to a healthy provider are ALL allowed ({allowed}) -- a breaker that "
          f"refused anything by default would pass every check above")

    snap = b4.snapshot()
    check(snap["voyage"]["state"] == CLOSED, f"snapshot reports state per provider ({snap})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
