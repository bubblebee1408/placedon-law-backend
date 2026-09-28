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

    PAGE_IMAGE    -> Gemini Flash        86.3 chrF++ on real Devanagari scans, the
                                         best independently measured, ahead of
                                         Claude Opus 82.2, EasyOCR 58.3, olmOCR 40.5
    TEXT/HIGH     -> Claude Opus 5       extraction: an error becomes a wrong answer
      fallback    -> Ollama, local       no credit; UNMEASURED, requires_review set
    TEXT/LOW      -> Claude Haiku 4.5    classification, measured Rs 0.97/call
      fallback    -> Gemini Flash-Lite   free tier, then Gemini Flash
    NARRATION     -> Claude Sonnet 5     cannot introduce a fact -- review() drops
      fallback    -> Gemini Flash        the whole sentence if it tries

Three of those rows were prose until 28-09-2026. NARRATE was imported into this
file and appeared in no table, so every narration task raised "no route declared"
for a row this comment declares. The table is keyed on a TaskProfile now --
(modality, consequence, purpose) -- because narration and classification are both
LOW-consequence text and route to different models for different reasons.

## The fallbacks, and the rule they bend

The founder has no Anthropic credit: the key is live and the API answers HTTP 400.
Every Claude row above is still FIRST, because none of them has been beaten --
unreachable is not the same as wrong, and the day credit returns the routes return
with it.

Difference 2 below says a HIGH-consequence task REFUSES rather than degrading. That
is now bent, not abandoned: a HIGH task served by a fallback is served, because a
system that refuses everything helps nobody, and it carries `requires_review=True`.
`degraded` alone could not say it -- a degraded LOW classification is ordinary, and
a degraded HIGH extraction is a legal answer from a model nobody measured.

And "local" is checked rather than assumed. `ollama list` here returns
`kimi-k2.6:cloud` beside the local models: same client, same localhost URL, and the
prompt leaves the machine. The Ollama row refuses it by name, because not leaving
the machine is the entire reason that row is allowed to exist.

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

## Candidates are not preferences (D6, 18-09-2026)

`CANDIDATES` lists providers that are WIRED but not TRUSTED: Sarvam Document AI
for PAGE_IMAGE (`checker/sarvam_model.py`), Voyage `rerank-2.5` and `voyage-law-2`
for retrieval (`checker/voyage_model.py`). `route()` never reads that table, so a
candidate's key being present changes nothing: with only Sarvam available a scanned
page is REFUSED, not sent to Sarvam. A row moves into `_PREFERENCE` only after its
bake-off (`scripts/bakeoff_indic.py`, `scripts/bakeoff_retrieval.py`) shows a win
whose 95% interval does not overlap the incumbent's, and a person makes that edit.

Recorded while wiring them, because a bake-off is only as good as what it is compared
with: the PAGE_IMAGE row's "86.3 chrF++" is not this repo's measurement. It is
arXiv 2606.29213's corpus-level score for **Gemini 2.5 Flash** on 300 word- and
phrase-level crops sampled from the Sanskrit-OCR-Typed corpus (historical typeset
scans) -- not Indian corporate paper (docs/research/DOCUMENT_AI_PROVIDERS_INDIA.md,
I1-I6). The model pinned below, `gemini-3.6-flash`, has no measurement of its own,
because 2.5 Flash is closed to new keys (gemini_model.py). The preference stands until
a same-harness run replaces it; it is not re-derived here.
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
OLLAMA = "ollama"

# ── purpose: the axis the table's own docstring already used and the code did not ──
# The header above lists four rows, and one of them -- NARRATE -- was never routable:
# `anthropic_model.NARRATE` was imported here and appeared in no table, so every
# narration task fell through `_PREFERENCE.get(...)` to `[]` and raised NoRoute saying
# no route was DECLARED. It was declared, in prose, at the top of this file.
#
# (modality, consequence) cannot express it, because narration is LOW-consequence text
# and so is classification, and they route to different models for different reasons.
# The missing axis is what the model is being ASKED TO DO.
EXTRACTION = "EXTRACTION"          # read a document and quote what it said
CLASSIFICATION = "CLASSIFICATION"  # put a document in a bucket
NARRATION = "NARRATION"            # restate a decision already made, in plainer words
TRANSCRIPTION = "TRANSCRIPTION"    # turn pixels into characters
PURPOSES = (EXTRACTION, CLASSIFICATION, NARRATION, TRANSCRIPTION)


class NoRoute(LookupError):
    """No model is available for this task, and substituting one is not allowed."""


@dataclass(frozen=True)
class TaskProfile:
    """What is being routed, as the three facts the table is keyed on."""

    modality: str
    consequence: str
    purpose: str


@dataclass(frozen=True)
class Task:
    name: str
    modality: str
    consequence: str
    volume: int = 1
    # Defaulted, and derived rather than guessed: PAGE_IMAGE is transcription,
    # HIGH text is extraction, LOW text is classification -- which is exactly what the
    # three pre-existing rows meant, so every Task built before this field existed keeps
    # the route it had. NARRATION is the one that has to be asked for, because nothing
    # about (TEXT, LOW) distinguishes it from classification.
    purpose: str | None = None

    def __post_init__(self) -> None:
        if self.modality not in MODALITIES:
            raise ValueError(f"unknown modality {self.modality!r}")
        if self.consequence not in CONSEQUENCES:
            raise ValueError(f"unknown consequence {self.consequence!r}")
        if self.volume < 1:
            raise ValueError("volume must be at least 1")
        if self.purpose is not None and self.purpose not in PURPOSES:
            raise ValueError(f"unknown purpose {self.purpose!r}")

    @property
    def profile(self) -> TaskProfile:
        purpose = self.purpose or (
            TRANSCRIPTION if self.modality == PAGE_IMAGE else
            EXTRACTION if self.consequence == HIGH else CLASSIFICATION)
        return TaskProfile(self.modality, self.consequence, purpose)


@dataclass(frozen=True)
class Route:
    provider: str
    model: str
    why: str
    est_cost_inr: float
    batch: bool = False
    degraded: bool = False
    # A HIGH-consequence task served by anything but its first choice. Set by `route()`,
    # never by a caller. This file used to REFUSE that case outright; it now serves it,
    # because the founder has no Anthropic credit and a refused system helps nobody --
    # but the thing the old refusal protected must survive the change, and this flag is
    # what carries it. `degraded` alone would not: a degraded LOW classification is
    # ordinary, and a degraded HIGH extraction is a legal answer produced by a model
    # nobody measured on the job.
    requires_review: bool = False


# ── the table. Preference order per (modality, consequence). ──────────────────
from checker.anthropic_model import CLASSIFY, EXTRACT, NARRATE, cost_inr
from checker.gemini_model import FLASH, FLASH_LITE

# The Ollama row names no model. There is no default local model and there must not be:
# `ollama_runner` records the model in every attestation, so which artefact answered is
# an operator's decision. Resolved at route time from OLLAMA_MODEL, and refused if the
# operator named a `:cloud` one -- see ollama_runner.local_model().
OPERATOR_NAMED = "<OLLAMA_MODEL>"

# ── the fallback rows, added 28-09-2026 ──────────────────────────────────────
# The founder has no Anthropic credit: the key is live and the API answers HTTP 400,
# "Your credit balance is too low to access the Anthropic API". Every Claude row below
# is still FIRST, because none of them has been beaten -- they are unreachable today,
# which is a different thing from wrong, and the day credit returns the routes return
# with it and nothing here needs editing.
#
# What the fallbacks are NOT: cheaper models chosen to save money. Routing on price
# measurably buys nothing (see the header). These are the models that answer when the
# preferred one cannot be called at all, and every one of them is marked degraded.
_PREFERENCE = {
    TaskProfile(PAGE_IMAGE, HIGH, TRANSCRIPTION): [(GEMINI, FLASH,
        "86.3 chrF++ on Devanagari word/phrase crops (Sanskrit typeset, arXiv 2606.29213) -- the best independently measured, and UNVERIFIED here until reproduced")],
    TaskProfile(PAGE_IMAGE, LOW, TRANSCRIPTION): [(GEMINI, FLASH, "free tier, and best on Indic pages")],

    TaskProfile(TEXT, HIGH, EXTRACTION): [
        (ANTHROPIC, EXTRACT, "extraction: an error here becomes a wrong legal answer"),
        (OLLAMA, OPERATOR_NAMED,
         "no Anthropic credit, so extraction runs on the operator's own machine rather "
         "than not at all. UNMEASURED on this task and the route says so: requires_review "
         "is set, because a legal answer from a model nobody benchmarked is a draft")],

    TaskProfile(TEXT, LOW, CLASSIFICATION): [
        (ANTHROPIC, CLASSIFY, "measured Rs 0.97 per call on this shape"),
        (GEMINI, FLASH_LITE,
         "free tier; gemini-3.1-flash-lite answered on 28-09-2026 and is the cheapest "
         "thing that does. UNMEASURED on this task"),
        (GEMINI, FLASH, "free tier; the larger model, when Flash-Lite is refused or busy")],

    TaskProfile(TEXT, LOW, NARRATION): [
        (ANTHROPIC, NARRATE,
         "cannot introduce a fact -- reasoning.review() drops the whole sentence if it tries"),
        (GEMINI, FLASH,
         "free tier. Narration is the one job where the model choice is least load-bearing: "
         "the context is pre-retrieved and pre-gated, review() drops any sentence carrying "
         "a proposition that is not in the evidence, and an 8B model at temperature 0 would "
         "do it (PROVIDER_DECISION.md §4)"),
        (GEMINI, FLASH_LITE,
         "free tier, and the one that was actually answering on 28-09-2026 while "
         "gemini-3.6-flash returned 503 six times running"),
        (OLLAMA, OPERATOR_NAMED,
         "the operator's own machine: no key, no quota, no credit. Last because it is "
         "the slowest and unmeasured, and because it is the row that CANNOT run out -- "
         "the free tier is 20 requests/day/model (measured 28-09-2026), which is a "
         "demo's worth, so a system that only had free-tier rows would be down by "
         "mid-morning")],
}

# ── candidates: wired, not preferred. route() never reads this table. ─────────
VOYAGE = "voyage"
SARVAM = "sarvam"
RETRIEVAL_RERANK = "RETRIEVAL_RERANK"
RETRIEVAL_DENSE = "RETRIEVAL_DENSE"


@dataclass(frozen=True)
class Candidate:
    role: str
    provider: str
    model: str
    incumbent: str
    bakeoff: str
    adopt_when: str


from checker import sarvam_model as _sarvam  # noqa: E402
from checker import voyage_model as _voyage  # noqa: E402

_RETRIEVAL_RULE = ("p@1 on the frozen 70-case cross_section_eval, with a Wilson 95% "
                   "interval non-overlapping and above RRF's, and no non-overlapping "
                   "loss on recall@5")
CANDIDATES: tuple[Candidate, ...] = (
    Candidate(PAGE_IMAGE, SARVAM, _sarvam.MODEL, f"{GEMINI}/{FLASH}",
              "scripts/bakeoff_indic.py",
              "corpus chrF++ on the same pages as the incumbent's evidence, with a "
              "paired bootstrap 95% interval on the difference that is non-overlapping "
              "with zero"),
    Candidate(RETRIEVAL_RERANK, VOYAGE, _voyage.RERANK, "fusion.search (RRF, BM25 + MiniLM)",
              "scripts/bakeoff_retrieval.py", _RETRIEVAL_RULE),
    Candidate(RETRIEVAL_DENSE, VOYAGE, _voyage.LAW, "fusion.search (RRF, BM25 + MiniLM)",
              "scripts/bakeoff_retrieval.py", _RETRIEVAL_RULE),
)


def candidates(role: str | None = None) -> tuple[Candidate, ...]:
    return tuple(c for c in CANDIDATES if role is None or c.role == role)


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
    if provider == OLLAMA:
        # Zero MARGINAL cost, which is the number a budget gate needs. It is not zero
        # cost -- it is the founder's own hardware and the wall-clock of a laptop doing
        # inference -- and neither of those is billed to MONTHLY_CAP_INR.
        return 0.0
    return round(cost_inr(model, tin * task.volume, tout * task.volume), 2)


def route(task: Task, *, available: tuple[str, ...],
          budget_inr: float | None = None,
          exclude_models: frozenset[str] = frozenset()) -> Route:
    """Pick a model, or refuse. Never substitutes silently on a HIGH task.

    `exclude_models` skips models a caller has just found BUSY. A 503 is not the
    provider being unavailable -- the key works, the quota is fine, that one model is
    under load -- and dropping the whole provider on one would refuse a question the
    next row could answer. Measured 28-09-2026: gemini-3.6-flash returned 503 for six
    consecutive calls while gemini-3.1-flash-lite returned 200 throughout, so this is
    the ordinary case rather than an edge one. The exclusion is per-call and never
    persisted: a busy model is busy for a minute, and remembering it would be wrong by
    the time anyone read the memory.
    """
    profile = task.profile
    options = _PREFERENCE.get(profile, [])
    if not options:
        raise NoRoute(f"no route declared for {profile.modality}/{profile.consequence}/"
                      f"{profile.purpose}")

    first = True
    refusals: list[str] = []
    for provider, model, why in options:
        if provider not in available or model in exclude_models:
            first = False
            continue
        if provider == OLLAMA:
            # Resolved here rather than in the table, and a `:cloud` model is refused:
            # it reaches the same localhost URL through the same client and the prompt
            # still leaves the machine, which voids the only reason this row exists.
            from checker import ollama_runner
            try:
                model = ollama_runner.local_model()
            except ollama_runner.NotConfigured as e:
                refusals.append(f"{OLLAMA}: {e}")
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
        degraded = not first
        return Route(provider, model, why, est,
                     batch=task.volume >= BATCH_THRESHOLD,
                     degraded=degraded,
                     # A HIGH task on anything but its first choice is a legal answer
                     # produced by a model nobody measured on the job. It is served --
                     # refusing everything helps nobody when there is no credit -- but
                     # it is served as a draft, and this is the flag that says so.
                     requires_review=degraded and task.consequence == HIGH)
    raise NoRoute(
        f"{task.name}: no available model for {profile.modality}/{profile.consequence}/"
        f"{profile.purpose}. Available providers: {', '.join(available) or '(none)'}. "
        f"This system does not substitute a model it has not measured for the job."
        + (" " + " ".join(refusals) if refusals else ""))


def providers_available(*, credit_exhausted=None) -> tuple[str, ...]:
    """Which providers can actually be called, not which ones are configured.

    Every adapter's `available()` means A KEY EXISTS, and that is the wrong question the
    moment a key exists and does not work. The founder's ANTHROPIC_API_KEY is live and
    every call it makes returns HTTP 400, "Your credit balance is too low" -- so a router
    asking `anthropic_model.available()` is told yes, routes to Anthropic, and the whole
    free-tier fallback below never fires. Shipping that would be shipping a feature that
    cannot run.

    `credit_exhausted` is injected so this stays testable without a ledger on disk, in
    the same style as every other injected callable in this repo.
    """
    from checker import anthropic_model, gemini_model, ollama_runner
    if credit_exhausted is None:
        def credit_exhausted() -> bool:
            from backend.budget import BudgetTracker
            try:
                return BudgetTracker().credit_exhausted()
            except (OSError, ValueError):
                # An unreadable ledger is not evidence the balance is empty. Fail toward
                # offering the provider: the worst case is one wasted 400 that records
                # the fact properly.
                return False
    out = []
    if anthropic_model.available() and not credit_exhausted():
        out.append(ANTHROPIC)
    if gemini_model.available():
        out.append(GEMINI)
    if ollama_runner.available():
        out.append(OLLAMA)
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
            flags += " [REQUIRES REVIEW]" if r.requires_review else ""
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

    # ── candidates are listed, never routed to ───────────────────────────────
    preferred = {prov for opts in _PREFERENCE.values() for prov, _, _ in opts}
    check(CANDIDATES and all(c.provider not in preferred for c in CANDIDATES),
          "no candidate provider appears in the preference table -- that changes only "
          "after a bake-off win")
    EVERYONE = (ANTHROPIC, GEMINI, VOYAGE, SARVAM)
    check(route(Task("ocr", PAGE_IMAGE, HIGH), available=EVERYONE).provider == GEMINI,
          "with Sarvam's key present too, a scanned page still goes to the incumbent")
    try:
        route(Task("ocr", PAGE_IMAGE, HIGH), available=(SARVAM,))
        check(False, "a candidate alone is not a route")
    except NoRoute:
        check(True, "with ONLY Sarvam available, a PAGE_IMAGE task refuses rather than "
                    "routing to an unmeasured candidate")
    try:
        route(Task("ocr", PAGE_IMAGE, LOW), available=(SARVAM, VOYAGE))
        check(False, "a LOW task does not degrade onto a candidate either")
    except NoRoute:
        check(True, "...and a LOW task does not degrade onto a candidate either")
    check({c.role for c in CANDIDATES} == {PAGE_IMAGE, RETRIEVAL_RERANK, RETRIEVAL_DENSE},
          "candidates: Sarvam for PAGE_IMAGE, Voyage for rerank and for dense retrieval")
    from pathlib import Path as _P
    root = _P(__file__).resolve().parent.parent
    check(all((root / c.bakeoff).is_file() for c in CANDIDATES),
          "every candidate names a bake-off script that exists")
    check(all("non-overlapping" in c.adopt_when for c in CANDIDATES),
          "every candidate's adoption rule requires non-overlapping intervals")
    check(candidates(PAGE_IMAGE)[0].provider == SARVAM and not candidates("AUDIO"),
          "candidates(role) filters by role")
    check(set(providers_available()) <= {ANTHROPIC, GEMINI},
          "providers_available() still lists only routable providers, never candidates")

    # ── the free-model fallbacks (28-09-2026) ────────────────────────────────
    import os as _os
    from checker import ollama_runner as _ol

    def _with_ollama(model: str):
        """Temporarily name a local model, so these checks do not depend on a laptop."""
        return {_ol.BASE_URL_ENV: "http://127.0.0.1:11434", _ol.MODEL_ENV: model}

    def _env(d):
        held = {k: _os.environ.get(k) for k in d}
        _os.environ.update(d)
        return held

    def _restore(held):
        for k, v in held.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    # NARRATE was imported into this file and appeared in no table, so every narration
    # task raised "no route declared" -- for a row the header declares in prose.
    rn = route(Task("narrate", TEXT, LOW, purpose=NARRATION), available=BOTH)
    check(rn.model == NARRATE and not rn.degraded,
          f"NARRATION is routable at last, and Claude is still first ({rn.model})")
    rn2 = route(Task("narrate", TEXT, LOW, purpose=NARRATION), available=(GEMINI,))
    check(rn2.provider == GEMINI and rn2.degraded and not rn2.requires_review,
          f"...falling back to Gemini, marked degraded, and NOT flagged for review -- "
          f"it is LOW consequence and review() drops any sentence it invents ({rn2.provider})")
    check(route(Task("classify", TEXT, LOW), available=BOTH).model == CLASSIFY
          and route(Task("narrate", TEXT, LOW, purpose=NARRATION),
                    available=BOTH).model == NARRATE,
          "classification and narration are both (TEXT, LOW) and route differently -- "
          "which is why purpose had to become part of the key")

    # LOW classification prefers Flash-Lite over Flash, and both over nothing.
    rc = route(Task("classify", TEXT, LOW), available=(GEMINI,))
    check(rc.model == FLASH_LITE and rc.degraded,
          f"a LOW classification falls back to Flash-Lite first ({rc.model})")
    check("28-09-2026" in rc.why and "UNMEASURED" in rc.why,
          "...and the route says both when it was measured to answer and that it has "
          "not been measured on THIS task")

    # HIGH extraction: the policy change, and the thing that must survive it.
    held = _env(_with_ollama("llama3:latest"))
    try:
        rh = route(Task("extract", TEXT, HIGH), available=(OLLAMA,))
        check(rh.provider == OLLAMA and rh.model == "llama3:latest",
              f"HIGH extraction falls back to the operator's local model ({rh.model})")
        check(rh.degraded and rh.requires_review,
              "...marked degraded AND requires_review -- this file used to refuse a "
              "degraded HIGH task outright, and the flag is what carries forward the "
              "thing that refusal protected")
        check(rh.est_cost_inr == 0.0,
              "...at zero MARGINAL cost, which is the number a budget gate needs")
        check(not route(Task("extract", TEXT, HIGH), available=BOTH).requires_review,
              "...while a first-choice HIGH route needs no review")
        check(not route(Task("classify", TEXT, LOW), available=(GEMINI,)).requires_review,
              "...and a degraded LOW task is not flagged either -- degraded alone would "
              "have flagged it, which is why requires_review is its own field")
        check("[REQUIRES REVIEW]" in plan((Task("extract", TEXT, HIGH),), available=(OLLAMA,)),
              "the plan prints the review flag, so it is visible before anything is spent")
    finally:
        _restore(held)

    # A :cloud model is not local, and the whole reason for the row is that it is.
    held = _env(_with_ollama("kimi-k2.6:cloud"))
    try:
        route(Task("extract", TEXT, HIGH), available=(OLLAMA,))
        check(False, "a :cloud Ollama model is refused")
    except NoRoute as e:
        check("leaves this machine" in str(e),
              "an Ollama CLOUD model is refused: same localhost URL, same client, and "
              "the prompt still leaves the machine -- which voids the only reason a "
              "HIGH task may run there at all")
    finally:
        _restore(held)

    held = _env({_ol.BASE_URL_ENV: "http://127.0.0.1:11434", _ol.MODEL_ENV: ""})
    try:
        route(Task("extract", TEXT, HIGH), available=(OLLAMA,))
        check(False, "an unnamed local model is refused")
    except NoRoute as e:
        check("names no default model" in str(e),
              "...and with no OLLAMA_MODEL named it refuses rather than picking one -- "
              "the model is what the attestation records")
    finally:
        _restore(held)

    # Claude stays FIRST everywhere. Unreachable is not the same as beaten.
    firsts = {prof: opts[0][0] for prof, opts in _PREFERENCE.items()}
    check(all(p == ANTHROPIC for prof, p in firsts.items() if prof.modality == TEXT),
          f"every TEXT row still prefers Anthropic ({firsts})")
    check(all(len(opts) > 1 for prof, opts in _PREFERENCE.items() if prof.modality == TEXT),
          "...and every TEXT row now has somewhere to go when it cannot be called")

    # providers_available() must not report a provider that answers HTTP 400.
    check(ANTHROPIC not in providers_available(credit_exhausted=lambda: True),
          "a key with no credit is NOT an available provider -- `available()` means a "
          "key exists, and the founder's key exists and cannot be called")
    from checker import anthropic_model as _am
    check(((ANTHROPIC in providers_available(credit_exhausted=lambda: False))
           == _am.available()),
          "...while with credit it is reported exactly when a key exists, so the new "
          "check subtracts a provider and never adds one")

    # The profile is derived for every Task built before `purpose` existed.
    check(Task("x", TEXT, HIGH).profile.purpose == EXTRACTION
          and Task("x", TEXT, LOW).profile.purpose == CLASSIFICATION
          and Task("x", PAGE_IMAGE, HIGH).profile.purpose == TRANSCRIPTION,
          "a Task built without a purpose derives the one its old row meant")
    try:
        Task("x", TEXT, LOW, purpose="VIBES")
        check(False, "an unknown purpose is rejected")
    except ValueError:
        check(True, "an unknown purpose is rejected at construction")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
