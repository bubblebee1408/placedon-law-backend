"""Intent -> a fixed step list, written in code. A model may pick, never invent.

## Why the plan is not a model's output

The obvious design is a model that reads the request and decides which steps to run.
`checker/router.py` already refuses that for model selection, and the reason carries here
unchanged: *"A model that picks the model is one step from a model that picks the answer,
and every other refusal in this system exists to keep that step from being taken."*

So a plan is a **constant**. `template(intent)` returns the same tuple every time for a
given intent, and `select()` is the only place a model's preference enters -- it may turn
DECLARED OPTIONAL steps on, and it can do nothing else. It cannot add a step, reorder the
list, or drop a required one. A model asking for a step that is not in the plan's optional
set is refused by name rather than ignored, because silently dropping a request is how you
end up debugging a plan that ran something nobody chose.

Required steps are always present and always in template order. That is what makes a run
replayable: the trace of a resumed run is the trace of the original because the step list
could not have differed.

Run: python3 agents/plans.py
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.state import UNKNOWN_INTENT

# ── the declared intents. Not a model's vocabulary -- ours. ──────────────────
RESEARCH_QUESTION = "research_question"
REVIEW_DOCUMENT = "review_document"
COMPANY_STANDING = "company_standing"
LAW_CHANGES = "law_changes"
INTENTS = (RESEARCH_QUESTION, REVIEW_DOCUMENT, COMPANY_STANDING, LAW_CHANGES)

# Runtime phases (founder's plan §1.4). `verify` is L0 only and never takes a model.
INTAKE = "intake"
RESEARCH = "research"
DOCUMENT = "document"
COMPANY = "company"
VERIFY = "verify"
CRITIC = "critic"
SYNTHESIS = "synthesis"
AUDIT = "audit"

# Engine capabilities, quoted from checker/bundles.capabilities() rather than restated, so a
# renamed capability breaks a test here instead of drifting silently.
CAP_MATRIX = "company.compliance_matrix"
CAP_CURRENCY = "document.currency_check"
CAP_GROUND = "document.ground_extraction"
CAP_EXPOSURE = "law.acquisition_exposure"
CAP_CHANGES = "law.changes"


class UnknownIntent(LookupError):
    """Not in INTENTS. Carries the refusal code so a caller need not map it."""

    code = UNKNOWN_INTENT


class StepNotOffered(ValueError):
    """A model asked for a step this plan does not offer as optional."""


@dataclass(frozen=True)
class StepSpec:
    capability: str
    optional: bool = False
    engine_capability: str | None = None    # set when the step calls the legal engine


@dataclass(frozen=True)
class Plan:
    intent: str
    steps: tuple[StepSpec, ...]

    @property
    def required(self) -> tuple[str, ...]:
        return tuple(s.capability for s in self.steps if not s.optional)

    @property
    def optional(self) -> tuple[str, ...]:
        return tuple(s.capability for s in self.steps if s.optional)


# Every plan opens with intake and closes with verify -> critic -> synthesis -> audit.
# `verify` is not optional in any plan: the deterministic check is the product.
_TAIL = (StepSpec(VERIFY), StepSpec(CRITIC), StepSpec(SYNTHESIS), StepSpec(AUDIT))

TEMPLATES: dict[str, Plan] = {
    RESEARCH_QUESTION: Plan(RESEARCH_QUESTION, (
        StepSpec(INTAKE),
        StepSpec(RESEARCH, engine_capability=CAP_EXPOSURE),
        StepSpec(DOCUMENT, optional=True, engine_capability=CAP_GROUND),
        StepSpec(COMPANY, optional=True, engine_capability=CAP_MATRIX),
    ) + _TAIL),
    REVIEW_DOCUMENT: Plan(REVIEW_DOCUMENT, (
        StepSpec(INTAKE),
        StepSpec(DOCUMENT, engine_capability=CAP_GROUND),
        StepSpec(RESEARCH, engine_capability=CAP_CURRENCY),
        StepSpec(COMPANY, optional=True, engine_capability=CAP_MATRIX),
    ) + _TAIL),
    COMPANY_STANDING: Plan(COMPANY_STANDING, (
        StepSpec(INTAKE),
        StepSpec(COMPANY, engine_capability=CAP_MATRIX),
        StepSpec(RESEARCH, optional=True, engine_capability=CAP_EXPOSURE),
    ) + _TAIL),
    LAW_CHANGES: Plan(LAW_CHANGES, (
        StepSpec(INTAKE),
        StepSpec(RESEARCH, engine_capability=CAP_CHANGES),
        StepSpec(COMPANY, optional=True, engine_capability=CAP_MATRIX),
    ) + _TAIL),
}


def template(intent: str) -> Plan:
    """The fixed plan for an intent. The same tuple every time, or UnknownIntent."""
    try:
        return TEMPLATES[intent]
    except KeyError:
        raise UnknownIntent(
            f"{intent!r} is not a declared intent; one of {INTENTS}. An intent nobody "
            f"declared is not an intent with an empty plan.") from None


def select(plan: Plan, chosen: frozenset[str] | set[str] | tuple = ()) -> tuple[StepSpec, ...]:
    """The steps to run: every required step, plus the chosen optional ones, in template order.

    `chosen` is the only place a model's preference enters. A name that is not one of this
    plan's optional steps is REFUSED -- not ignored -- because a silently dropped request
    leaves a plan that ran something nobody chose and no record of the disagreement.
    """
    chosen = frozenset(chosen)
    offered = frozenset(plan.optional)
    unknown = sorted(chosen - offered)
    if unknown:
        raise StepNotOffered(
            f"{plan.intent} does not offer {unknown} as optional steps. It offers "
            f"{sorted(offered) or 'none'}. A model may turn a declared optional step on; it "
            f"may not add a step, reorder the plan, or drop a required one.")
    return tuple(s for s in plan.steps if not s.optional or s.capability in chosen)


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

    print("agents.plans")

    check(all(i in TEMPLATES for i in INTENTS) and len(TEMPLATES) == len(INTENTS),
          f"every declared intent has a template, and no template lacks an intent ({len(INTENTS)})")
    e = attempt(lambda: template("please_do_anything"))
    check(isinstance(e, UnknownIntent) and e.code == UNKNOWN_INTENT,
          "an undeclared intent raises UnknownIntent, carrying its refusal code")

    # A plan is a CONSTANT. Two calls must be the same object-equal tuple, or a run could
    # not be replayed from the intent alone.
    check(template(RESEARCH_QUESTION) == template(RESEARCH_QUESTION),
          "template() is constant: the same intent gives the same plan every time")

    for intent, plan in TEMPLATES.items():
        check(plan.steps[0].capability == INTAKE,
              f"{intent} opens with intake")
        check(tuple(s.capability for s in plan.steps[-4:])
              == (VERIFY, CRITIC, SYNTHESIS, AUDIT),
              f"{intent} closes with verify -> critic -> synthesis -> audit")
        check(VERIFY in plan.required,
              f"{intent}: verify is REQUIRED -- the deterministic check is the product, "
              f"never an option a model can decline")

    # ── the rule: a model may pick, never invent ────────────────────────────
    p = template(RESEARCH_QUESTION)
    check([s.capability for s in select(p)] == list(p.required),
          "choosing nothing runs exactly the required steps, in template order")
    with_doc = [s.capability for s in select(p, {DOCUMENT})]
    check(DOCUMENT in with_doc and with_doc.index(RESEARCH) < with_doc.index(DOCUMENT)
          < with_doc.index(VERIFY),
          f"a chosen optional step runs in TEMPLATE order, not the order it was asked for "
          f"({with_doc})")
    e = attempt(lambda: select(p, {"exfiltrate_corpus"}))
    check(isinstance(e, StepNotOffered) and "may not add a step" in str(e),
          "a step the plan does not offer is REFUSED by name, not silently ignored")
    e = attempt(lambda: select(p, {VERIFY}))
    check(isinstance(e, StepNotOffered),
          "...including naming a REQUIRED step as if it were optional")
    check(all(s.capability in p.required or s.capability in p.optional for s in p.steps),
          "every step is either required or offered -- there is no third kind")

    # Engine steps must name a capability that checker/bundles actually declares, so a
    # renamed capability fails here rather than drifting.
    from checker import bundles
    declared = set(bundles.capabilities())
    named = {s.engine_capability for pl in TEMPLATES.values() for s in pl.steps
             if s.engine_capability}
    check(named <= declared,
          f"every engine capability a plan names is declared by checker.bundles "
          f"({sorted(named - declared) or 'all present'})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
