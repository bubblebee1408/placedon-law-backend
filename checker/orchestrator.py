"""The loop. Every gate in this repository existed; nothing drove them in order.

Six modules were already here and all of them were reachable only by hand:

    router        which model runs a task, decided by facts rather than taste
    bundles       which capability answers an intent, and refuses to fake one
    session       where the client document lives, and where it does not
    reasoning     what a model may propose, and what happens when it does not
    shadow        measure a model without any proposal reaching a user
    model_adapter the refusals that happen BEFORE a call is made

That is an engine with no crankshaft. This is the crankshaft, and it is
deliberately the least clever file in the repository.

## Why there is no manager agent

The obvious design is a model that reads the request and decides which tool to
use. This does not do that, and the reason is not taste. A manager agent is a
model making a routing decision with no ground truth to check it against -- and
every other decision in this system is checkable. `router.route()` decides on
modality, consequence and volume. `bundles.route()` decides on a declared intent
and raises `NoSuchCapability` when none matches. Both are functions of their
inputs. A wrong route is a bug someone can find, not a bad day the model had.

## The bounded correction, which is the actual new thing

`reasoning.review()` already drops what fails and names why. What did not exist
was the retry: a model told exactly which refusal it earned, given ONE more
attempt, and then abstention.

One, not three. A model that failed grounding twice is not converging on the
truth; it is sampling until something passes the checker, and a checker that
accepts the third sample is a slot machine with a citation format. The cap is
`MAX_CORRECTIONS = 1` and it is a constant so that raising it is a visible
decision in a diff.

And the retry may only ever SHRINK the claim. `_narrowed()` refuses a second
proposal that asserts more than the first -- a new fact, a new citation, a longer
narration. Correction means dropping what could not be supported, never
elaborating until something sticks.

## What the loop will not do

It will not call a model without a budget, a capability, or a session; those
refusals live in the modules that own them and this file does not re-implement
them. It will not return a proposal that failed review. It will not run at all
without a document date, because every temporal answer here turns on one.

Run: python3 checker/orchestrator.py
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field
from datetime import date
from typing import Callable

from checker import bundles, reasoning
from checker.reasoning import Proposal, Refusal, Review

# One retry. See the module docstring: a second failure is sampling, not
# converging, and the number is a constant so that changing it shows in a diff.
MAX_CORRECTIONS = 1

# ── outcomes ─────────────────────────────────────────────────────────────────
SERVED = "SERVED"                      # review clean, first pass
SERVED_AFTER_CORRECTION = "SERVED_AFTER_CORRECTION"
ABSTAINED = "ABSTAINED"                # corrections exhausted; nothing served
REFUSED_BEFORE_CALL = "REFUSED_BEFORE_CALL"   # a gate fired; no model ran
OUTCOMES = (SERVED, SERVED_AFTER_CORRECTION, ABSTAINED, REFUSED_BEFORE_CALL)


class OrchestrationRefused(RuntimeError):
    """A precondition failed. No model was called."""


@dataclass(frozen=True)
class Step:
    """One thing the loop did. The trace is the product, not a debug aid."""
    n: int
    what: str
    detail: str


@dataclass(frozen=True)
class Outcome:
    verdict: str
    review: Review | None
    steps: tuple[Step, ...]
    corrections_used: int = 0
    abstained_on: tuple[Refusal, ...] = _field(default_factory=tuple)

    @property
    def served(self) -> bool:
        return self.verdict in (SERVED, SERVED_AFTER_CORRECTION)

    def trace(self) -> str:
        return "\n".join(f"  {s.n}. {s.what}: {s.detail}" for s in self.steps)


def _asserted(p: Proposal) -> tuple[int, int, int]:
    """How much a proposal claims: facts, citations, narration length."""
    return (len(p.facts or {}), len(p.citations or ()),
            len((p.narration or "").split()))


def _narrowed(first: Proposal, second: Proposal) -> tuple[bool, str]:
    """A correction may drop claims. It may never add one.

    Without this the retry is an invitation to elaborate: a model told "that fact
    was not grounded" can add two more facts and a longer narration, and if the
    new material happens to pass the detectors the system has been talked into
    more than it started with. Correction shrinks.
    """
    f1, c1, n1 = _asserted(first)
    f2, c2, n2 = _asserted(second)
    # Named additions are checked BEFORE counts, so the trace says WHICH field
    # was introduced rather than only that the total grew. "2 facts where there
    # was 1" sends a reader hunting; "introduces turnover_rupees" does not.
    new_facts = set(second.facts or {}) - set(first.facts or {})
    if new_facts:
        return False, f"the correction introduces new fields: {sorted(new_facts)}"
    new_cites = set(second.citations or ()) - set(first.citations or ())
    if new_cites:
        return False, f"the correction introduces new citations: {sorted(new_cites)}"
    if f2 > f1:
        return False, f"the correction asserts {f2} facts where the first had {f1}"
    if c2 > c1:
        return False, f"the correction cites {c2} sources where the first had {c1}"
    if n2 > n1:
        return False, (f"the correction narrates {n2} words where the first had "
                       f"{n1}")
    return True, ""


def correction_brief(review: Review) -> str:
    """What the model is told on the retry. Refusals only -- never a hint.

    It is given the violation and the offending value, because that is what it
    got wrong. It is NOT given the right answer, because a model handed the
    expected value will echo it, and an echo passes every grounding check while
    establishing nothing.
    """
    lines = ["Your previous answer was rejected. Each line is a check it failed.",
             "Drop what you cannot support. Do not add anything new.", ""]
    for r in review.refusals:
        bit = f" (offending: {r.offending})" if r.offending else ""
        lines.append(f"- {r.violation}: {r.detail}{bit}")
    return "\n".join(lines)


def run(*, intent: str, document: str, document_date: date | None,
        model: Callable[[str], Proposal],
        pack_ids: tuple[str, ...] = (), verified_text: str = "",
        max_corrections: int = MAX_CORRECTIONS) -> Outcome:
    """Drive one task from intent to a served answer or an abstention."""
    steps: list[Step] = []
    n = 0

    def step(what: str, detail: str) -> None:
        nonlocal n
        n += 1
        steps.append(Step(n, what, detail))

    # ── preconditions. Each is owned elsewhere; none is re-implemented here ──
    if document_date is None:
        raise OrchestrationRefused(
            "no document date. Every temporal answer here compares the law at "
            "the document's date with the law now; without one it would compare "
            "today with today, which answers nothing.")
    try:
        bundle = bundles.route(intent)
    except bundles.NoSuchCapability as e:
        step("capability", f"REFUSED — {e}")
        return Outcome(REFUSED_BEFORE_CALL, None, tuple(steps))
    step("capability", f"{intent} -> {bundle.name}")
    step("date", f"document dated {document_date.isoformat()}")

    declared = bundles.capabilities()

    # ── first pass ──────────────────────────────────────────────────────────
    proposal = model(document)
    step("model", f"proposed {len(proposal.facts or {})} fact(s), "
                  f"{len(proposal.citations or ())} citation(s)")
    rev = reasoning.review(proposal, declared_intents=declared, document=document,
                           pack_ids=pack_ids, verified_text=verified_text)
    if rev.clean:
        step("review", "clean")
        return Outcome(SERVED, rev, tuple(steps))
    step("review", f"{len(rev.refusals)} refusal(s): "
                   f"{', '.join(r.violation for r in rev.refusals)}")

    # ── bounded correction ──────────────────────────────────────────────────
    used = 0
    first = proposal
    while used < max_corrections:
        used += 1
        brief = correction_brief(rev)
        retry = model(document + "\n\n" + brief)
        step("correction", f"attempt {used} of {max_corrections}")

        ok, why = _narrowed(first, retry)
        if not ok:
            # An elaborating retry is abandoned outright rather than reviewed. A
            # model that answers a rejection by claiming MORE has not understood
            # the rejection, and letting the checker adjudicate the new material
            # would reward the behaviour whenever it happened to pass.
            step("correction", f"ABANDONED — {why}")
            return Outcome(ABSTAINED, rev, tuple(steps), used, rev.refusals)

        rev2 = reasoning.review(retry, declared_intents=declared,
                                document=document, pack_ids=pack_ids,
                                verified_text=verified_text)
        if rev2.clean:
            step("review", "clean after correction")
            return Outcome(SERVED_AFTER_CORRECTION, rev2, tuple(steps), used)
        step("review", f"still {len(rev2.refusals)} refusal(s)")
        rev, first = rev2, retry

    step("abstain", f"{used} correction(s) used; nothing survived review")
    return Outcome(ABSTAINED, rev, tuple(steps), used, rev.refusals)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("orchestrator")
    DOC = ("Resolved on 14 June 2024 that the Company, a private company with "
           "paid-up share capital of Rs 4,00,00,000, do allot shares.")
    INTENT = bundles.capabilities()[0]
    D = date(2024, 6, 14)

    def clean_model(_: str) -> Proposal:
        return Proposal(intent=INTENT,
                        facts={"paid_up_capital_rupees":
                               {"value": 40000000,
                                "span": "paid-up share capital of Rs 4,00,00,000"}})

    out = run(intent=INTENT, document=DOC, document_date=D, model=clean_model)
    check(out.verdict == SERVED and out.served,
          f"a clean proposal is served on the first pass ({out.verdict})")
    check(out.corrections_used == 0, "...with no correction spent")
    check(len(out.steps) >= 4 and "capability" in out.trace(),
          f"the trace records what happened:\n{out.trace()}")

    # ── the bounded correction, both ways ───────────────────────────────────
    calls = {"n": 0}

    def fixes_itself(text: str) -> Proposal:
        calls["n"] += 1
        if calls["n"] == 1:
            return Proposal(intent=INTENT,
                            facts={"paid_up_capital_rupees":
                                   {"value": 40000000, "span": "never appears"}})
        return clean_model(text)

    out = run(intent=INTENT, document=DOC, document_date=D, model=fixes_itself)
    check(out.verdict == SERVED_AFTER_CORRECTION and out.corrections_used == 1,
          f"a model that fixes itself is served after ONE correction "
          f"({out.verdict}, {out.corrections_used} used)")
    check("Drop what you cannot support" in correction_brief(
              reasoning.review(Proposal(intent=INTENT,
                                        facts={"x": {"value": 1, "span": "nope"}}),
                               declared_intents=bundles.capabilities(),
                               document=DOC)),
          "the brief tells the model to drop, never to try again differently")

    def never_fixes(_: str) -> Proposal:
        return Proposal(intent=INTENT,
                        facts={"paid_up_capital_rupees":
                               {"value": 40000000, "span": "never appears"}})

    out = run(intent=INTENT, document=DOC, document_date=D, model=never_fixes)
    check(out.verdict == ABSTAINED and out.corrections_used == 1,
          f"a model that does not fix itself abstains after one try "
          f"({out.verdict})")
    check(out.abstained_on and not out.served,
          "...naming what it abstained on, and serving nothing")

    # ── the rule that makes the retry safe ──────────────────────────────────
    def elaborates(text: str) -> Proposal:
        if "rejected" in text:
            return Proposal(intent=INTENT,
                            facts={"paid_up_capital_rupees":
                                   {"value": 40000000,
                                    "span": "paid-up share capital of Rs 4,00,00,000"},
                                   "turnover_rupees":
                                   {"value": 400000000, "span": "invented"}},
                            citations=("s.2(85)",))
        return never_fixes(text)

    out = run(intent=INTENT, document=DOC, document_date=D, model=elaborates)
    check(out.verdict == ABSTAINED,
          "a correction that asserts MORE is abandoned, not reviewed")
    check("ABANDONED" in out.trace() and "turnover_rupees" in out.trace(),
          f"...and the trace names the field it tried to add")

    okn, why = _narrowed(
        Proposal(facts={"a": 1, "b": 2}, citations=("x", "y"), narration="one two"),
        Proposal(facts={"a": 1}, citations=("x",), narration="one"))
    check(okn, "a correction that drops claims is allowed")
    for worse in (Proposal(facts={"a": 1, "b": 2, "c": 3}),
                  Proposal(facts={"a": 1}, citations=("x", "y", "z"))):
        n_ok, _ = _narrowed(Proposal(facts={"a": 1, "b": 2}, citations=("x", "y")),
                            worse)
        check(not n_ok, "...and one that adds any is refused")

    # ── preconditions ───────────────────────────────────────────────────────
    try:
        run(intent=INTENT, document=DOC, document_date=None, model=clean_model)
        check(False, "a missing document date is refused")
    except OrchestrationRefused as e:
        check("compare today with today" in str(e),
              "no document date, no run -- and the message says why")

    out = run(intent="not_a_capability", document=DOC, document_date=D,
              model=clean_model)
    check(out.verdict == REFUSED_BEFORE_CALL,
          "an intent no bundle serves is refused BEFORE any model call")

    # ── the misbehaving models reasoning.py already ships ───────────────────
    for violation in ("FACT_WITHOUT_SPAN", "CONCLUSION_ASSERTED"):
        bad = reasoning.misbehaving_model(violation)
        out = run(intent=INTENT, document=DOC, document_date=D,
                  model=lambda _t, p=bad: p)
        check(not out.served,
              f"a model misbehaving with {violation} never reaches SERVED")

    check(MAX_CORRECTIONS == 1,
          "the cap is one -- a second failure is sampling, not converging, and "
          "the constant makes raising it visible in a diff")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
