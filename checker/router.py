"""The model router: which model runs a task, decided by facts rather than taste.

This is the orchestration layer. Spellbook and Harvey both describe a middleware
that routes sub-tasks to the model best suited to each; this is that, with two
differences that are not stylistic.

## Difference 1 — the router is not a model

In their descriptions a "manager agent" decides. Here routing is a deterministic
function of four declared facts:

    modality      is this a page of pixels or a string of text?
    consequence   does an error here become a WRONG LEGAL ANSWER, or a slower one?
    volume        one document, or twenty thousand?
    availability  which keys exist, and how much budget is left?

None of those is a judgement. A model that picks the model is one step from a
model that picks the answer, and every other refusal in this system exists to
keep that step from being taken.

## Difference 2 — it refuses rather than degrading, where the stakes require it

A HIGH-consequence task whose preferred model is unavailable is **refused**. It
does not quietly fall back to a cheaper model, because "we could not afford the
good model so we used the weak one" is exactly the decision a user must be told
about rather than have made for them. LOW-consequence tasks may degrade, and the
route says that it did.

## The routing table, and the evidence under it

    PAGE_IMAGE  -> Gemini 2.5 Flash    86.3 chrF++ on real Devanagari scans, the
                                       best independently measured, ahead of
                                       Claude Opus 82.2, EasyOCR 58.3, olmOCR 40.5
    TEXT/HIGH   -> Claude Opus 5       extraction: an error becomes a wrong answer
    TEXT/LOW    -> Claude Haiku 4.5    classification, measured Rs 0.97/call
    NARRATE     -> Claude Sonnet 5     cannot introduce a fact -- review() drops
                                       the whole sentence if it tries

This is NOT cost routing, which measurably buys nothing: routers with hard numbers
target *retaining* 90-95% of the best model's quality more cheaply. It is routing
to the measured winner per modality, which is a different claim.

## What this layer deliberately does not do

**It does not decompose a request into sub-tasks.** Spellbook splits a contract
into ~15 clause-checks because each needs judgement. Our obligations are decided
by deterministic code, so there is nothing to decompose -- and the negative
literature is clear that decomposition is not free: MAST (1,600 annotated traces
across 7 frameworks) found multi-agent gains "often minimal" against the
complexity added, and a single judge beat multi-agent debate on human alignment.

Fan-out here is over DOCUMENTS, not over reasoning steps. That parallelism is
real and safe; agentic decomposition of a legal question is neither.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── task shape ────────────────────────────────────────────────────────────────
TEXT = "TEXT"
PAGE_IMAGE = "PAGE_IMAGE"
MODALITIES = (TEXT, PAGE_IMAGE)

HIGH = "HIGH"      # an error becomes a wrong legal answer
LOW = "LOW"        # an error costs time, not correctness
CONSEQUENCES = (HIGH, LOW)

ANTHROPIC = "anthropic"
GEMINI = "gemini"


class NoRoute(LookupError):
    """No model is available for this task, and substituting one is not allowed."""


@dataclass(frozen=True)
class Task:
    name: str
    modality: str
    consequence: str
    volume: int = 1

    def __post_init__(self) -> None:
        if self.modality not in MODALITIES:
            raise ValueError(f"unknown modality {self.modality!r}")
        if self.consequence not in CONSEQUENCES:
            raise ValueError(f"unknown consequence {self.consequence!r}")
        if self.volume < 1:
            raise ValueError("volume must be at least 1")


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    why: str
    est_cost_inr: float
    batch: bool = False
    degraded: bool = False


# ── the table. Preference order per (modality, consequence). ──────────────────
from checker.anthropic_model import CLASSIFY, EXTRACT, NARRATE, cost_inr
from checker.gemini_model import FLASH

_PREFERENCE = {
    (PAGE_IMAGE, HIGH): [(GEMINI, FLASH,
        "86.3 chrF++ on real Devanagari scans, the best independently measured")],
    (PAGE_IMAGE, LOW): [(GEMINI, FLASH, "free tier, and best on Indic pages")],
    (TEXT, HIGH): [(ANTHROPIC, EXTRACT,
        "extraction: an error here becomes a wrong legal answer")],
    (TEXT, LOW): [(ANTHROPIC, CLASSIFY, "measured Rs 0.97 per call on this shape"),
                  (GEMINI, FLASH, "free tier")],
}

# Rough per-unit token shapes, for a cost estimate that is derived rather than
# guessed. Real usage is recorded by the callables themselves.
_SHAPE = {TEXT: (10_000, 1_500), PAGE_IMAGE: (1_500, 200)}

# Above this many units, a non-urgent task should go through the Batch API, which
# is half price. Bulk review is definitionally non-urgent.
BATCH_THRESHOLD = 50


def estimate_inr(provider: str, model: str, task: Task) -> float:
    tin, tout = _SHAPE[task.modality]
    if provider == GEMINI:
        return 0.0                       # free tier; paid rates UNVERIFIED here
    return round(cost_inr(model, tin * task.volume, tout * task.volume), 2)


def route(task: Task, *, available: tuple[str, ...],
          budget_inr: float | None = None) -> Route:
    """Pick a model, or refuse. Never substitutes silently on a HIGH task."""
    options = _PREFERENCE.get((task.modality, task.consequence), [])
    if not options:
        raise NoRoute(f"no route declared for {task.modality}/{task.consequence}")

    first = True
    for provider, model, why in options:
        if provider not in available:
            first = False
            continue
        est = estimate_inr(provider, model, task)
        if budget_inr is not None and est > budget_inr:
            # Affordability is not a reason to quietly use a weaker model on a
            # HIGH task. It is a reason to say the budget is the blocker.
            if task.consequence == HIGH:
                raise NoRoute(
                    f"{task.name}: {model} would cost Rs {est} and Rs {budget_inr} "
                    f"remains. This is HIGH consequence, so it refuses rather than "
                    f"dropping to a weaker model — that is a decision for a person, "
                    f"not a fallback.")
            first = False
            continue
        return Route(provider, model, why, est,
                     batch=task.volume >= BATCH_THRESHOLD,
                     degraded=not first)
    raise NoRoute(
        f"{task.name}: no available model for {task.modality}/{task.consequence}. "
        f"Available providers: {', '.join(available) or '(none)'}. This system does "
        f"not substitute a model it has not measured for the job.")


def providers_available() -> tuple[str, ...]:
    from checker import anthropic_model, gemini_model
    out = []
    if anthropic_model.available():
        out.append(ANTHROPIC)
    if gemini_model.available():
        out.append(GEMINI)
    return tuple(out)


def plan(tasks: tuple[Task, ...], *, available: tuple[str, ...],
         budget_inr: float | None = None) -> str:
    """A readable routing plan with a total. For deciding before spending."""
    lines, total = ["ROUTING PLAN", ""], 0.0
    for t in tasks:
        try:
            r = route(t, available=available, budget_inr=budget_inr)
            total += r.est_cost_inr
            flags = " [batch]" if r.batch else ""
            flags += " [degraded]" if r.degraded else ""
            lines.append(f"  {t.name:26} {r.provider}/{r.model}{flags}")
            lines.append(f"  {'':26} Rs {r.est_cost_inr:<9} {r.why}")
        except NoRoute as e:
            lines.append(f"  {t.name:26} REFUSED")
            lines.append(f"  {'':26} {e}")
        lines.append("")
    lines.append(f"  estimated total: Rs {round(total, 2)}")
    return "\n".join(lines)


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

    print("router")
    BOTH = (ANTHROPIC, GEMINI)

    # ── routes by modality, on the measured evidence ─────────────────────────
    r = route(Task("ocr-scan", PAGE_IMAGE, HIGH), available=BOTH)
    check(r.provider == GEMINI, f"a scanned page goes to Gemini ({r.provider})")
    check("Devanagari" in r.why, "...because of the measured Devanagari result")
    check(r.est_cost_inr == 0.0, "...on the free tier")

    r2 = route(Task("extract", TEXT, HIGH), available=BOTH)
    check(r2.model == EXTRACT, f"high-consequence text goes to Opus ({r2.model})")
    check("wrong legal answer" in r2.why, "...because an error becomes a wrong answer")

    r3 = route(Task("classify", TEXT, LOW), available=BOTH)
    check(r3.model == CLASSIFY, f"low-consequence text goes to Haiku ({r3.model})")

    # ── refuses rather than substituting ─────────────────────────────────────
    try:
        route(Task("extract", TEXT, HIGH), available=(GEMINI,))
        check(False, "with Anthropic unavailable, a HIGH text task refuses")
    except NoRoute as e:
        check("does not substitute a model it has not measured" in str(e),
              "with Anthropic unavailable, a HIGH text task refuses rather than "
              "using whatever is to hand")

    try:
        route(Task("ocr", PAGE_IMAGE, HIGH), available=())
        check(False, "with nothing available it refuses")
    except NoRoute as e:
        check("(none)" in str(e), "with nothing available it refuses, listing what it has")

    # ── LOW tasks may degrade, and the route SAYS it degraded ────────────────
    r4 = route(Task("classify", TEXT, LOW), available=(GEMINI,))
    check(r4.provider == GEMINI and r4.degraded,
          f"a LOW task falls back to the second choice and is marked degraded "
          f"({r4.provider}, degraded={r4.degraded})")
    check(not r3.degraded, "...while a first-choice route is not marked degraded")

    # ── budget: a HIGH task refuses rather than dropping tier ────────────────
    try:
        route(Task("extract-bulk", TEXT, HIGH, volume=500), available=BOTH,
              budget_inr=100)
        check(False, "an unaffordable HIGH task refuses")
    except NoRoute as e:
        check("a decision for a person, not a fallback" in str(e),
              "an unaffordable HIGH task refuses — using a weaker model because "
              "the good one is unaffordable is a decision for a person")

    r5 = route(Task("classify-bulk", TEXT, LOW, volume=5000), available=BOTH,
               budget_inr=10)
    check(r5.provider == GEMINI,
          f"an unaffordable LOW task degrades to free rather than refusing ({r5.provider})")

    # ── batch above the threshold ────────────────────────────────────────────
    check(route(Task("bulk", TEXT, LOW, volume=200), available=BOTH).batch,
          "a bulk task is routed through the Batch API, which is half price")
    check(not route(Task("one", TEXT, LOW, volume=1), available=BOTH).batch,
          "...and a single task is not")

    # ── estimates are derived from the price table, not guessed ──────────────
    one = route(Task("x", TEXT, HIGH), available=BOTH).est_cost_inr
    ten = route(Task("x", TEXT, HIGH, volume=10), available=BOTH).est_cost_inr
    check(abs(ten - one * 10) < 0.5, f"cost scales with volume ({one} -> {ten})")

    # ── bad tasks are rejected at construction ───────────────────────────────
    for bad in (dict(modality="AUDIO", consequence=HIGH),
                dict(modality=TEXT, consequence="MAYBE"),
                dict(modality=TEXT, consequence=HIGH, volume=0)):
        try:
            Task("bad", **bad); check(False, f"a malformed task is rejected: {bad}")
        except ValueError:
            check(True, f"a malformed task is rejected at construction: "
                        f"{list(bad.values())[0]}")

    # ── the plan reads, and totals ───────────────────────────────────────────
    p = plan((Task("classify", TEXT, LOW),
              Task("extract", TEXT, HIGH),
              Task("ocr", PAGE_IMAGE, HIGH, volume=400)), available=BOTH)
    check("estimated total" in p and "batch" in p,
          "the plan totals the spend and flags what batches")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
