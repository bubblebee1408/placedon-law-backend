"""The verifier cascade, in one importable place.

It was defined inside `metric_policy._test()`. Nothing outside that function
could reach it, so any runtime that wanted to verify a claim had to write the
composition again — and the release gate would then be scoring code that merely
resembled what shipped. Every number this project reports about the cascade was
a property of a closure inside a test.

The order is E7 -> E6 -> E5 -> E4 -> E3, and each step earns its position:

    E7  GATE        may refuse, never accept. A single-token substitution that
                    changes the rule -- "shall not" to "shall", "shall" to "may",
                    "thirty" to "sixty" -- is refused before any module that scores
                    term overlap sees it, because `not` and `no` are stopwords in
                    all three of those modules and digits match none of their
                    patterns, so the swap is invisible to every one of them.
                    Measured: 264/268 negation mutations accepted without it.
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


def e7(premise: str, claim: str) -> bool | None:
    from checker.entail_substitution import judge, UNRESOLVED
    v = judge(premise, claim)
    return None if v.status == UNRESOLVED else v.entailed


def verdict(premise: str, claim: str) -> Verdict:
    """Run the cascade. This is the composition the release gate scores."""
    steps: list[Step] = []

    for name, gate in (("E7", e7), ("E6", e6)):
        g = gate(premise, claim)
        steps.append(Step(name, GATE, g is not None, g,
                          "gate: may refuse, never accept"))
        if g is False:
            return Verdict(NOT_SUPPORTED, name, tuple(steps))

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
    from checker.entail_substitution import judge as e7j, UNRESOLVED as U7

    def inlined(r):
        sub = e7j(r.source_span, r.claim)
        if sub.status != U7 and sub.entailed is False:
            return False
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
    # A gate may refuse and may abstain. It may NOT accept: an acceptance here would put
    # a qualifier check above the modules that read the binding, and the same for a
    # substitution check. Asserted over every benchmark row, for both gates.
    #
    # This check read `bool(accepted_by_e6) or True` until 02-10-2026, which cannot fail
    # and so proved nothing -- it passed just as readily on a gate that accepted every
    # row. Rewritten as the invariant it was describing.
    for label, gate in (("E6", e6), ("E7", e7)):
        accepted = [r for r in rows if gate(r.source_span, r.claim) is True]
        decided = [r.id for r in accepted if verdict(r.source_span, r.claim).decided_by == label]
        check(not decided,
              f"{label} may RETURN True, but it never DECIDES on one -- the cascade reads "
              f"only its refusal, so an acceptance cannot rule above the specialists "
              f"({len(accepted)} accepted, {decided[:3]} decided)")

    # E7 goes further: it cannot accept at all, and that is structural rather than a
    # policy the composition enforces on its behalf. Its only non-abstaining verdict is a
    # refusal, so there is no True for a future caller to misread.
    from checker.entail_substitution import SUBSTITUTED, UNRESOLVED as _U7
    from checker.entail_substitution import judge as _e7j
    _vs = {_e7j(r.source_span, r.claim).status for r in rows}
    check(_vs <= {SUBSTITUTED, _U7} and not any(
              _e7j(r.source_span, r.claim).entailed is True for r in rows),
          f"E7 returns only a refusal or an abstention, never an acceptance ({_vs})")
    for r in rows[:40]:
        v = verdict(r.source_span, r.claim)
        if v.decided_by == "E6":
            assert v.supported is False, "E6 decided an acceptance"
    check(True, "...asserted across a sample: E6 never decides an acceptance")

    # A verdict explains itself.
    v = verdict(rows[0].source_span, rows[0].claim)
    check(v.decided_by in ("E3", "E4", "E5", "E6", "E7"),
          f"the deciding module is named ({v.decided_by})")
    check(v.steps and [x.module for x in v.steps][:2] == ["E7", "E6"],
          f"both gates run first, in order ({[x.module for x in v.steps]})")
    check(all(s.role == GATE for s in v.steps if s.module in ("E6", "E7")),
          "...and both are recorded as gates")

    # Every E7 refusal is final, the same contract E6 has.
    refused = [r for r in rows if e7(r.source_span, r.claim) is False]
    check(all(judge_row(r) is False for r in refused),
          f"every E7 refusal is final ({len(refused)} refused)")
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
