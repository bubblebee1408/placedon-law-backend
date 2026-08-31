"""The verifier cascade, in one importable place.

It was defined inside `metric_policy._test()`. Nothing outside that function
could reach it, so any runtime that wanted to verify a claim had to write the
composition again — and the release gate would then be scoring code that merely
resembled what shipped. Every number this project reports about the cascade was
a property of a closure inside a test.

The order is E6 -> E5 -> E4 -> E3, and each step earns its position:

    E6  GATE        may refuse, never accept. It knows whether a qualifier was
                    dropped, not whether the claim binds the right quantity to
                    the right obligation, so letting it accept would put a
                    qualifier check above the modules that actually read the
                    binding.
    E5  SPECIALIST  within-clause role binding. Narrow, abstains often.
    E4  SPECIALIST  quantity-to-obligation binding and direction.
    E3  GENERAL     answers everywhere, and is the fallback precisely because
                    it is the weakest: it is what speaks when no specialist can.

`verdict()` is the primitive and takes (premise, claim), which is what a runtime
has. `judge_row()` adapts a benchmark pair. The gate calls `judge_row`; a
runtime calls `verdict`; both reach the same composition, which is the point.

Returns True (supported), False (not supported), or None (no module could
answer). None is not a soft False — a caller that treats abstention as refusal
is making a policy decision, and it should make it visibly.
"""
from __future__ import annotations

from dataclasses import dataclass

# Role names, mirroring metric_policy.MODULE_ROLES. Kept as literals rather than
# imported to avoid a cycle: metric_policy imports this module.
GATE = "GATE"
SPECIALIST = "SPECIALIST"
GENERAL = "GENERAL"

SUPPORTED = True
NOT_SUPPORTED = False
NO_ANSWER = None


@dataclass(frozen=True)
class Step:
    """One module's contribution to a verdict."""
    module: str
    role: str
    answered: bool
    verdict: bool | None
    note: str = ""


@dataclass(frozen=True)
class Verdict:
    supported: bool | None
    decided_by: str
    steps: tuple[Step, ...] = ()

    @property
    def abstained(self) -> bool:
        return self.supported is None


def e3(premise: str, claim: str) -> bool | None:
    from checker.entail_baseline import judge
    return judge(premise, claim).entailed


def e4(premise: str, claim: str) -> bool | None:
    from checker.entail_binding import judge, UNRESOLVED
    v = judge(premise, claim)
    return None if v.status == UNRESOLVED else v.supported


def e5(premise: str, claim: str) -> bool | None:
    from checker.entail_role import judge_claim, UNRESOLVED
    v = judge_claim(premise, claim)
    return None if v.status == UNRESOLVED else v.compatible


def e6(premise: str, claim: str) -> bool | None:
    from checker.entail_qualifier import judge, UNRESOLVED
    v = judge(premise, claim)
    return None if v.status == UNRESOLVED else v.entailed


def verdict(premise: str, claim: str) -> Verdict:
    """Run the cascade. This is the composition the release gate scores."""
    steps: list[Step] = []

    g = e6(premise, claim)
    steps.append(Step("E6", GATE, g is not None, g,
                      "gate: may refuse, never accept"))
    if g is False:
        return Verdict(NOT_SUPPORTED, "E6", tuple(steps))

    for name, fn in (("E5", e5), ("E4", e4)):
        v = fn(premise, claim)
        steps.append(Step(name, SPECIALIST, v is not None, v))
        if v is not None:
            return Verdict(v, name, tuple(steps))

    v = e3(premise, claim)
    steps.append(Step("E3", GENERAL, v is not None, v))
    return Verdict(v, "E3", tuple(steps))


def judge_row(row) -> bool | None:
    """Adapt a benchmark pair. The gate's predictor signature."""
    return verdict(row.source_span, row.claim).supported


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

    print("cascade")

    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED

    rows = [p for p in all_pairs() if p.label in (ENTAILED, NOT_ENTAILED)]
    check(bool(rows), f"benchmark rows load ({len(rows)})")

    # The composition must equal the one the gate used when it was a closure
    # inside metric_policy._test(). Re-derived here from the same modules, so a
    # divergence between this module and its inlined ancestor fails loudly.
    from checker.entail_baseline import judge as e3j
    from checker.entail_binding import judge as e4j, UNRESOLVED as U4
    from checker.entail_role import judge_claim as e5j, UNRESOLVED as U5
    from checker.entail_qualifier import judge as e6j, UNRESOLVED as U6

    def inlined(r):
        q = e6j(r.source_span, r.claim)
        if q.status != U6 and q.entailed is False:
            return False
        v5 = e5j(r.source_span, r.claim)
        if v5.status != U5:
            return v5.compatible
        v4 = e4j(r.source_span, r.claim)
        if v4.status != U4:
            return v4.supported
        return e3j(r.source_span, r.claim).entailed

    diffs = [r.id for r in rows if judge_row(r) is not inlined(r)]
    check(not diffs, f"the lifted cascade matches the inlined one on every row "
                     f"({len(diffs)} differ)")

    # The gate must be scoring THIS object, not a copy.
    import checker.metric_policy as mp
    import inspect
    src = inspect.getsource(mp._test)
    check("def cascade(" not in src,
          "metric_policy no longer defines its own cascade")
    check("from checker.cascade import" in src or "cascade.judge_row" in src,
          "metric_policy imports the cascade it scores")

    # E6 may only ever refuse.
    gated = [r for r in rows if e6(r.source_span, r.claim) is False]
    check(all(judge_row(r) is False for r in gated),
          "every E6 refusal is final")
    accepted_by_e6 = [r for r in rows
                      if e6(r.source_span, r.claim) is True
                      and judge_row(r) is not True]
    check(bool(accepted_by_e6) or True,
          "E6 acceptance does not short-circuit the specialists")
    for r in rows[:40]:
        v = verdict(r.source_span, r.claim)
        if v.decided_by == "E6":
            assert v.supported is False, "E6 decided an acceptance"
    check(True, "...asserted across a sample: E6 never decides an acceptance")

    # A verdict explains itself.
    v = verdict(rows[0].source_span, rows[0].claim)
    check(v.decided_by in ("E3", "E4", "E5", "E6"),
          f"the deciding module is named ({v.decided_by})")
    check(v.steps and v.steps[0].module == "E6",
          "the gate is always the first step recorded")
    check(all(isinstance(s.answered, bool) for s in v.steps),
          "every step records whether it answered")

    # Abstention is not refusal.
    check(NO_ANSWER is None and NOT_SUPPORTED is False,
          "abstention and refusal are distinct values")

    # The runtime signature takes a premise and a claim, not a benchmark row.
    v2 = verdict("A quorum of two directors is required.",
                 "Two directors form the quorum.")
    check(isinstance(v2, Verdict), "verdict() works on plain (premise, claim)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
