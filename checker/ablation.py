"""The ablation matrix: which part of the system actually produces the accuracy?

The program's central claim is that accuracy here is a *systems* property, not a model
property — that retrieval, schema constraint and the decision layer carry the number,
and the language model is the smallest contributor rather than the largest. That claim
is worth nothing until it is measured against the alternative, so this module runs the
same task through five configurations and prints what each one scores.

The task is the frozen cross-section eval's own: given a plain question a company
secretary would ask, name the section of the Companies Act 2013 that governs it. The
labels are structural (read off each section's title), not legal judgements, which is
what makes them safe to grade automatically.

## The five tiers

    V1  base model, prompting only, NO retrieval — the model answers from its weights
    V2  base model + dense retrieval (top-5 as context)
    V3  PEFT fine-tuned adapter, no retrieval            — NOT RUNNABLE, see below
    V4  base model + hybrid BM25 top-5 AND dense top-5 as context
    V5  V4 + schema-constrained output: the answer must parse under
        `extraction_schema.validate_section_ref`, with exactly one repair retry

V4 passes both ranked lists, labelled, rather than a fused list. Reciprocal Rank Fusion
is M3 and is not written yet; inventing a fusion here would make V4 measure something
the shipped system does not have.

## V3 is a hole in the matrix, and it stays a hole

There is no CUDA device on this machine (Apple M1, 8 GB unified memory), and the 70
eval cases are a bar rather than a training set — there is no annotated gold set and no
annotators. Both blockers are arithmetic, not judgement. So V3 is emitted as an explicit
NOT_RUNNABLE row carrying its reason. A matrix with an invented row is worse than a
matrix with a stated gap, because the gap is recoverable and the invention is not.

## Nothing is reported that was not measured

The model is probed before anything is graded. If Ollama does not answer, every
model-dependent tier is reported NOT_RUNNABLE with the transport's own reason, and no
number is printed for it. The same holds if the dense index cannot load: V2/V4/V5 go
NOT_RUNNABLE rather than quietly degrading to BM25 and reporting BM25 under a dense
label. If the model dies part-way through a tier, that tier is marked NOT_RUNNABLE with
the case count it reached — a partial run is not a result.

## The sample size is part of every number

gemma3:1b on an M1 is slow enough that all 70 cases across four tiers is a long wall
clock. The harness therefore runs a bounded prefix of the eval, defaults to 20 cases,
and prints the sample size on every line it emits. An unstated sample is a lie by
omission, so `render()` states it whether or not anyone asked.

Standard library only. No new dependency (CLAUDE.md).
"""
from __future__ import annotations

import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from checker.cross_section_eval import CASES, Case
from checker.extraction_schema import validate_section_ref
from checker.ollama_runner import ModelUnavailable, NotConfigured, OllamaRunner

# gemma3:1b is the only model on this box that leaves room for anything else to run.
# llama3 (4.7G), qwen3.5 (6.6G) and mistral-nemo (7.1G) each consume nearly all of the
# 8 GB of unified memory. This is measured, not a preference.
DEFAULT_MODEL = "gemma3:1b"

# `ollama_runner` refuses to invent a host, on purpose. The harness therefore names the
# endpoint explicitly: reaching out of this process is a decision, and this is where it
# is taken.
DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

DEFAULT_SAMPLE = 20
TOP_K = 5
PROBE_PROMPT = "Reply with the single word: ready"
PROBE_TIMEOUT_S = 60
CALL_TIMEOUT_S = 120

RUN = "RUN"
NOT_RUNNABLE = "NOT_RUNNABLE"

PEFT_BLOCKED = (
    "no CUDA device (Apple M1, 8 GB unified memory, Metal only) so no PEFT/QLoRA run is "
    "possible here; and there is no annotated gold set to fine-tune on — the 70 eval "
    "cases are the bar, not training data, and the project has no annotators. Both "
    "blockers are recorded rather than approximated."
)

Retriever = Callable[[str, int], list]
Runner = Callable[[str], str]


@dataclass(frozen=True)
class TierSpec:
    tier: str
    config: str
    needs_model: bool
    needs_bm25: bool
    needs_dense: bool
    needs_peft: bool
    schema_constrained: bool


TIERS: tuple[TierSpec, ...] = (
    TierSpec("V1", "base model, prompting only, no retrieval",
             True, False, False, False, False),
    TierSpec("V2", "base model + dense retrieval (top-5 context)",
             True, False, True, False, False),
    TierSpec("V3", "PEFT fine-tuned adapter, no retrieval",
             True, False, False, True, False),
    TierSpec("V4", "base model + hybrid BM25 top-5 and dense top-5 (both lists as context)",
             True, True, True, False, False),
    TierSpec("V5", "V4 + schema-constrained output, one repair retry",
             True, True, True, False, True),
)


# ── grading ─────────────────────────────────────────────────────────────────
# Section numbers in the Companies Act 2013 run to three digits (up to s.470), so a
# 1-3 digit token cannot be the year "2013" and the grader stays lenient without
# being credulous. A reference introduced by "section"/"s." wins over a bare number.
_LABELLED = re.compile(r"(?:section|sec\.?|s\.)\s*(\d{1,3}[A-Z]{0,2})\b", re.I)
_BARE = re.compile(r"\b(\d{1,3}[A-Z]{0,2})\b")


def extract_section(text: str | None) -> str | None:
    """The section number a free-text answer proposes, or None if it proposes none.

    Deliberately lenient for the unconstrained tiers: those tiers are being measured on
    whether the model KNOWS the section, not on whether it can format. V5 is the tier
    that measures formatting, and it uses `validate_section_ref` instead.
    """
    if not text:
        return None
    m = _LABELLED.search(text)
    if m:
        return m.group(1).upper()
    m = _BARE.search(text)
    return m.group(1).upper() if m else None


# ── prompts ─────────────────────────────────────────────────────────────────
def _context_block(label: str, hits: Sequence) -> str:
    lines = [f"{label}:"]
    for num, title, _score in hits:
        lines.append(f"  s.{num} — {title}")
    return "\n".join(lines)


def build_context(spec: TierSpec, question: str,
                  bm25: Retriever | None, dense: Retriever | None,
                  top_k: int = TOP_K) -> tuple[str, list[str]]:
    """(context text, section numbers offered). Empty for a no-retrieval tier."""
    blocks: list[str] = []
    offered: list[str] = []
    if spec.needs_bm25 and bm25 is not None:
        hits = list(bm25(question, top_k))
        blocks.append(_context_block("Candidates ranked by keyword search (BM25)", hits))
        offered += [h[0] for h in hits]
    if spec.needs_dense and dense is not None:
        hits = list(dense(question, top_k))
        blocks.append(_context_block("Candidates ranked by dense embedding search", hits))
        offered += [h[0] for h in hits]
    return "\n\n".join(blocks), offered


def build_prompt(spec: TierSpec, question: str, context: str) -> str:
    head = ("You are answering about the Companies Act, 2013 (India).\n\n"
            f"Question: {question}\n\n")
    if context:
        head += (context + "\n\nThe correct section is very likely one of the "
                 "candidates above, but you may name another if none of them governs "
                 "the question.\n\n")
    if spec.schema_constrained:
        return head + (
            "Answer with a section reference and NOTHING else — no words, no full "
            "stop, no explanation. Valid examples: 185 or 188(1)(a) or 2(85).\n"
            "Answer:")
    return head + ("Which single section of the Companies Act, 2013 governs this "
                   "question? Answer with the section number only, for example: 185\n"
                   "Section number:")


def build_repair_prompt(question: str, bad: str) -> str:
    return ("Your previous answer was not a valid section reference.\n"
            f"Question: {question}\n"
            f"You answered: {bad.strip()[:120]!r}\n\n"
            "Reply with the section number alone. No words, no punctuation, no "
            "explanation. For example: 185\nAnswer:")


# ── results ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CaseOutcome:
    question: str
    expected: str
    raw: str
    predicted: str | None
    correct: bool
    gold_in_context: bool | None
    schema_valid: bool | None
    schema_valid_first_try: bool | None
    retried: bool
    latency_s: float


@dataclass(frozen=True)
class TierResult:
    spec: TierSpec
    status: str
    reason: str = ""
    n: int = 0
    correct: int = 0
    unparseable: int = 0
    retries: int = 0
    schema_valid: int | None = None
    schema_valid_first_try: int | None = None
    gold_in_context: int | None = None
    latencies: tuple[float, ...] = ()
    outcomes: tuple[CaseOutcome, ...] = ()

    @property
    def ran(self) -> bool:
        return self.status == RUN

    @property
    def p_at_1(self) -> float | None:
        """None — not zero — when the tier did not run. A tier that was never measured
        did not score 0.00; conflating the two is how a gap becomes a claim."""
        if not self.ran or not self.n:
            return None
        return self.correct / self.n

    @property
    def schema_validity(self) -> float | None:
        if not self.ran or self.schema_valid is None or not self.n:
            return None
        return self.schema_valid / self.n

    @property
    def context_recall(self) -> float | None:
        if not self.ran or self.gold_in_context is None or not self.n:
            return None
        return self.gold_in_context / self.n

    @property
    def latency_mean_s(self) -> float | None:
        return statistics.fmean(self.latencies) if self.latencies else None


@dataclass(frozen=True)
class Matrix:
    results: tuple[TierResult, ...]
    sample_size: int
    total_cases: int
    model: str
    endpoint: str
    model_status: str
    dense_status: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_tier(self, tier: str) -> TierResult | None:
        return next((r for r in self.results if r.spec.tier == tier), None)


# ── the run ─────────────────────────────────────────────────────────────────
def run_tier(spec: TierSpec, cases: Sequence[Case], runner: Runner,
             bm25: Retriever | None = None, dense: Retriever | None = None,
             top_k: int = TOP_K) -> TierResult:
    """Grade one tier over `cases`. Assumes runnability was already decided."""
    outcomes: list[CaseOutcome] = []
    correct = unparseable = retries = 0
    schema_ok = schema_ok_first = 0
    in_ctx = 0
    lat: list[float] = []
    uses_context = spec.needs_bm25 or spec.needs_dense

    for i, c in enumerate(cases):
        context, offered = build_context(spec, c.question, bm25, dense, top_k)
        gold_here = (c.section in offered) if uses_context else None
        if gold_here:
            in_ctx += 1
        try:
            t0 = time.perf_counter()
            raw = runner(build_prompt(spec, c.question, context))
            elapsed = time.perf_counter() - t0
        except (ModelUnavailable, OSError) as e:
            # A partial tier is not a result. Report the gap, keep the case count.
            return TierResult(spec, NOT_RUNNABLE,
                              f"the model stopped answering after {i} of {len(cases)} "
                              f"cases: {e}")

        retried = False
        valid: bool | None = None
        valid_first: bool | None = None
        if spec.schema_constrained:
            _f, ref = validate_section_ref(raw.strip())
            valid_first = ref is not None
            if ref is None:
                retried = True
                retries += 1
                try:
                    t1 = time.perf_counter()
                    raw = runner(build_repair_prompt(c.question, raw))
                    elapsed += time.perf_counter() - t1
                except (ModelUnavailable, OSError) as e:
                    return TierResult(spec, NOT_RUNNABLE,
                                      f"the model stopped answering during the repair "
                                      f"retry on case {i} of {len(cases)}: {e}")
                _f, ref = validate_section_ref(raw.strip())
            valid = ref is not None
            schema_ok += int(valid)
            schema_ok_first += int(bool(valid_first))
            predicted = ref.section.upper() if ref else None
        else:
            predicted = extract_section(raw)

        if predicted is None:
            unparseable += 1
        hit = predicted == c.section
        correct += int(hit)
        lat.append(elapsed)
        outcomes.append(CaseOutcome(c.question, c.section, raw, predicted, hit,
                                    gold_here, valid, valid_first, retried, elapsed))

    return TierResult(
        spec, RUN, "", len(cases), correct, unparseable, retries,
        schema_ok if spec.schema_constrained else None,
        schema_ok_first if spec.schema_constrained else None,
        in_ctx if uses_context else None,
        tuple(lat), tuple(outcomes))


def probe_model(model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL,
                timeout_s: int = PROBE_TIMEOUT_S) -> tuple[Runner | None, str]:
    """(runner, reason). Probes with a real generation so a missing model, a dead
    daemon and an unloadable weight file all surface here rather than mid-matrix.

    Temperature and seed are left at `OllamaRunner`'s defaults (0.0 / 0) on purpose:
    the tiers are only comparable if the only thing that changed between them is the
    tier.
    """
    try:
        runner = OllamaRunner(model, base_url=base_url, timeout_s=timeout_s)
    except NotConfigured as e:
        return None, f"not configured: {e}"
    try:
        runner(PROBE_PROMPT)
    except (ModelUnavailable, OSError) as e:
        return None, f"{model} at {base_url} did not answer the probe: {e}"
    return runner, f"{model} answered the probe at {base_url}"


def probe_dense() -> tuple[Retriever | None, str]:
    try:
        from checker.dense_index import available, search
    except ImportError as e:                       # pragma: no cover - import guard
        return None, f"dense_index is not importable: {e}"
    ok, why = available()
    return (search if ok else None), why


def probe_bm25() -> tuple[Retriever | None, str]:
    from checker.corpus_retrieval import search
    return search, "BM25 over the ingested corpus"


def run_matrix(*, cases: Sequence[Case] = CASES, sample_size: int = DEFAULT_SAMPLE,
               runner: Runner | None = None, model_reason: str = "",
               bm25: Retriever | None = None, dense: Retriever | None = None,
               dense_reason: str = "", model: str = DEFAULT_MODEL,
               endpoint: str = DEFAULT_BASE_URL, top_k: int = TOP_K) -> Matrix:
    """Run every tier over the first `sample_size` cases.

    Callers inject `runner`, `bm25` and `dense`; whatever is None is treated as
    unavailable and the tiers that need it are reported NOT_RUNNABLE with the reason
    given. Nothing is probed from in here — `run_live()` probes and passes the results
    down — so the decision logic is testable without a daemon.
    """
    sample = list(cases[:max(0, sample_size)])
    results: list[TierResult] = []
    for spec in TIERS:
        if spec.needs_peft:
            results.append(TierResult(spec, NOT_RUNNABLE, PEFT_BLOCKED))
            continue
        if spec.needs_model and runner is None:
            results.append(TierResult(
                spec, NOT_RUNNABLE,
                model_reason or "no model runner: the tier was not measured"))
            continue
        if spec.needs_dense and dense is None:
            results.append(TierResult(
                spec, NOT_RUNNABLE,
                dense_reason or "dense retrieval unavailable; BM25 is NOT substituted "
                                "under a dense label"))
            continue
        if spec.needs_bm25 and bm25 is None:
            results.append(TierResult(spec, NOT_RUNNABLE,
                                      "BM25 retrieval unavailable"))
            continue
        results.append(run_tier(spec, sample, runner, bm25, dense, top_k))

    return Matrix(tuple(results), len(sample), len(cases), model, endpoint,
                  model_reason or ("runner injected" if runner else "no runner"),
                  dense_reason or ("dense injected" if dense else "no dense"))


def render(m: Matrix) -> str:
    """Every line states what was measured and over how many cases."""
    L = [f"ablation matrix — task: name the governing section of the Companies Act 2013",
         f"model: {m.model}   endpoint: {m.endpoint}",
         f"model probe: {m.model_status}",
         f"dense probe: {m.dense_status}",
         f"SAMPLE: the first {m.sample_size} of {m.total_cases} frozen "
         f"cross_section_eval cases. Every number below is over those "
         f"{m.sample_size} cases and no others.",
         ""]
    for r in m.results:
        L.append(f"{r.spec.tier}  {r.spec.config}")
        if not r.ran:
            L.append(f"    STATUS: {NOT_RUNNABLE}")
            L.append(f"    REASON: {r.reason}")
            L.append("    p@1: not measured (not reported as 0.00 — it was never run)")
            L.append("")
            continue
        L.append(f"    p@1 (top-1 section exactly correct): {r.correct}/{r.n} = "
                 f"{r.p_at_1:.2f}  over {r.n} cases")
        if r.context_recall is not None:
            L.append(f"    gold section present in the retrieved context: "
                     f"{r.gold_in_context}/{r.n} = {r.context_recall:.2f}  "
                     "(the ceiling the model was working under)")
        if r.schema_validity is not None:
            L.append(f"    schema-valid output (validate_section_ref accepts it): "
                     f"{r.schema_valid}/{r.n} = {r.schema_validity:.2f}  "
                     f"[first try {r.schema_valid_first_try}/{r.n}, "
                     f"{r.retries} repair retries]")
        L.append(f"    unparseable answers (no section proposed at all): "
                 f"{r.unparseable}/{r.n}")
        L.append(f"    latency: mean {r.latency_mean_s:.2f} s/query over {r.n} queries "
                 f"(total {sum(r.latencies):.1f} s)")
        L.append("")
    return "\n".join(L)


def run_live(sample_size: int = DEFAULT_SAMPLE, model: str = DEFAULT_MODEL,
             base_url: str = DEFAULT_BASE_URL) -> Matrix:
    """The real run. Probes first, then measures whatever is actually available."""
    runner, model_reason = probe_model(model, base_url)
    dense, dense_reason = probe_dense()
    bm25, _ = probe_bm25()
    return run_matrix(sample_size=sample_size, runner=runner, model_reason=model_reason,
                      bm25=bm25, dense=dense, dense_reason=dense_reason,
                      model=model, endpoint=base_url)


# ── self-test: passes with no daemon, no network, no model ──────────────────
def _fake(answers, log=None) -> Runner:
    """A Callable[[str], str] standing in for the model. `answers` is a list consumed
    in order, or a single string, or a callable of the prompt."""
    if callable(answers):
        fn = answers
    elif isinstance(answers, str):
        def fn(_p, _a=answers):
            return _a
    else:
        box = list(answers)

        def fn(_p):
            return box.pop(0) if box else ""
    def run(prompt: str) -> str:
        if log is not None:
            log.append(prompt)
        return fn(prompt)
    return run


def _stub_retriever(mapping):
    """Returns (number, title, score) triples, like corpus_retrieval/dense_index do."""
    def search(query: str, top_k: int = TOP_K):
        return [(n, f"title {n}", 1.0 - i * 0.1)
                for i, n in enumerate(mapping.get(query, [])[:top_k])]
    return search


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

    print("ablation")
    cases = (Case("q one", "185"), Case("q two", "188"), Case("q three", "96"))
    hits = {"q one": ["185", "42"], "q two": ["7", "188"], "q three": ["1", "2"]}
    bm25 = _stub_retriever(hits)
    dense = _stub_retriever(hits)

    # ── the honesty rules, first ──
    m = run_matrix(cases=cases, sample_size=3, runner=None,
                   model_reason="connection refused at http://localhost:11434",
                   bm25=bm25, dense=dense, dense_reason="loaded")
    check(all(not r.ran for r in m.results),
          "no runner: every model-dependent tier is NOT_RUNNABLE, none is graded")
    check(all("connection refused" in r.reason for r in m.results
              if not r.spec.needs_peft),
          "...and each carries the transport's own reason, not a generic one")
    check(all(r.p_at_1 is None for r in m.results),
          "a tier that did not run reports p@1 None, never 0.00")
    check("not measured" in render(m) and "never run" in render(m),
          "the rendered table says not-measured rather than printing a number")

    ok_runner = _fake(lambda p: "185" if "q one" in p else ("188" if "q two" in p else "96"))

    # ── V3 is NOT_RUNNABLE even when everything else is up ──
    m = run_matrix(cases=cases, sample_size=3, runner=ok_runner, bm25=bm25, dense=dense)
    v3 = m.by_tier("V3")
    check(v3 is not None and not v3.ran, "V3 is NOT_RUNNABLE even with model and dense up")
    check("no CUDA" in v3.reason and "no annotated gold set" in v3.reason,
          "...and states both blockers: no CUDA device and no annotated gold set")
    check(v3.p_at_1 is None and "V3" in render(m),
          "V3 still appears as a row — the gap is emitted, not skipped")

    # ── grading is real ──
    v1 = m.by_tier("V1")
    check(v1.ran and v1.n == 3 and v1.correct == 3 and v1.p_at_1 == 1.0,
          "a model that answers correctly scores p@1 3/3 over the 3 sampled cases")
    check(v1.gold_in_context is None,
          "V1 reports no context recall — it was given no context to recall from")
    wrong = run_matrix(cases=cases, sample_size=3, runner=_fake("999"),
                       bm25=bm25, dense=dense).by_tier("V1")
    check(wrong.p_at_1 == 0.0 and wrong.correct == 0,
          "a model that answers wrongly scores 0.00 — measured, not assumed")
    silent = run_matrix(cases=cases, sample_size=3, runner=_fake("I do not know."),
                        bm25=bm25, dense=dense).by_tier("V1")
    check(silent.unparseable == 3 and silent.correct == 0,
          "an answer proposing no section is counted unparseable and scored wrong")

    # ── sample size is bounded and stated ──
    m2 = run_matrix(cases=cases, sample_size=2, runner=ok_runner, bm25=bm25, dense=dense)
    check(m2.by_tier("V1").n == 2 and m2.sample_size == 2,
          "the sample size bounds the run and is carried on the matrix")
    txt = render(m2)
    check(f"first 2 of {len(cases)}" in txt and "over 2 cases" in txt,
          "render states the sample size and repeats the case count on the p@1 line")

    # ── retrieval wiring ──
    log: list[str] = []
    run_matrix(cases=cases, sample_size=1, runner=_fake("185", log), bm25=bm25, dense=dense)
    v1p = log[0]
    check("s.42" not in v1p and "Candidates" not in v1p,
          "the V1 prompt contains no retrieved candidates — that is the tier's point")
    v2p = next(p for p in log if "dense embedding" in p)
    check("s.185" in v2p and "BM25" not in v2p, "V2 passes the dense list only")
    v4p = next(p for p in log if "BM25" in p and "dense embedding" in p)
    check(v4p.count("s.185") == 2,
          "V4 passes BOTH ranked lists, labelled — no fusion is invented here")
    # The stub offers the gold section for two of the three cases, which is the point:
    # context recall is the ceiling the model was working under, and it is below 1.
    ctx = m.by_tier("V4")
    check(ctx.gold_in_context == 2 and abs(ctx.context_recall - 2 / 3) < 1e-9,
          "context recall records whether the gold section was even offered (2/3 here)")
    check(ctx.correct == 3 and ctx.p_at_1 == 1.0,
          "...and is reported separately from accuracy, so the two never merge")
    partial = run_matrix(cases=cases, sample_size=3, runner=ok_runner, bm25=bm25,
                         dense=_stub_retriever({"q one": ["185"]})).by_tier("V4")
    check(partial.gold_in_context == 2,
          "...and BM25 alone can supply the gold when dense does not")

    # ── dense down: V2/V4/V5 refuse rather than degrade to BM25 ──
    nd = run_matrix(cases=cases, sample_size=3, runner=ok_runner, bm25=bm25, dense=None,
                    dense_reason="MiniLM could not be loaded offline")
    check(nd.by_tier("V1").ran, "with dense down, V1 still runs — it needs no retrieval")
    check(all(not nd.by_tier(t).ran for t in ("V2", "V4", "V5")),
          "with dense down, V2/V4/V5 are NOT_RUNNABLE")
    check("MiniLM" in nd.by_tier("V2").reason,
          "...with the loader's own reason, not a substituted BM25 number")

    # ── V5: schema validity is measured separately from accuracy ──
    clean = run_matrix(cases=cases, sample_size=3, runner=ok_runner,
                       bm25=bm25, dense=dense).by_tier("V5")
    check(clean.schema_valid == 3 and clean.schema_validity == 1.0 and clean.retries == 0,
          "clean output: schema validity 3/3 over 3 cases, no retries")
    check(clean.correct == 3, "...and accuracy is still graded on top of validity")

    seq = _fake(["Section 185, I think.", "185",
                 "Section 188, I think.", "188",
                 "Section 96, I think.", "96"])
    retried = run_tier(TIERS[4], cases, seq, bm25, dense)
    check(retried.retries == 3 and retried.schema_valid == 3,
          "prose output is rejected, retried once, and the repaired answer counts valid")
    check(retried.schema_valid_first_try == 0,
          "...and first-try validity is reported separately, so the retry is visible")

    bad = run_tier(TIERS[4], cases, _fake("I cannot say."), bm25, dense)
    check(bad.schema_valid == 0 and bad.correct == 0 and bad.retries == 3,
          "output still malformed after one retry is invalid AND wrong — never repaired")
    check("schema-valid output" in render(
        Matrix((bad,), 3, len(cases), "m", "e", "s", "d")),
          "the schema-validity rate is rendered as its own metric")

    # ── latency is recorded ──
    check(len(clean.latencies) == 3 and clean.latency_mean_s is not None
          and clean.latency_mean_s >= 0.0,
          "one latency is recorded per query and the mean is reported over 3 queries")
    check("s/query over 3 queries" in render(
        Matrix((clean,), 3, len(cases), "m", "e", "s", "d")),
          "...and the rendered latency line states how many queries it averaged")

    # ── mid-run death is a gap, not a partial score ──
    def dies(prompt: str) -> str:
        if "q two" in prompt:
            raise ModelUnavailable("daemon went away")
        return "185"
    died = run_tier(TIERS[0], cases, dies)
    check(not died.ran and "after 1 of 3" in died.reason,
          "a model that dies mid-tier yields NOT_RUNNABLE with the case count reached")
    check(died.p_at_1 is None, "...and no partial p@1 is published from it")

    # ── the answer extractor ──
    check(extract_section("Section 185.") == "185", "'Section 185.' -> 185")
    check(extract_section("185") == "185", "a bare number is taken as the section")
    check(extract_section("The Companies Act, 2013 s.188(1)") == "188",
          "a labelled reference beats the year 2013 sitting next to it")
    check(extract_section("s.378A applies") == "378A", "a lettered section survives")
    check(extract_section("no idea") is None and extract_section("") is None,
          "an answer naming no section extracts to None, not to a guess")

    # ── determinism: the runner is constructed at defaults ──
    seen: list[dict] = []
    r = OllamaRunner(DEFAULT_MODEL, base_url="http://local",
                     transport=lambda p: (seen.append(p), {"response": "185"})[1])
    r("x")
    check(seen[0]["options"]["temperature"] == 0.0 and seen[0]["options"]["seed"] == 0,
          "the harness overrides no sampling option: temperature 0, fixed seed")
    check(r.deterministic, "...so tiers differ only by tier, and every call is repeatable")

    # ── probe failure is reported, not swallowed ──
    bad_probe, why = probe_model("nope", base_url="http://127.0.0.1:9")
    check(bad_probe is None and "did not answer the probe" in why,
          "an unreachable endpoint yields no runner and a stated reason")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--live" in sys.argv:
        n = DEFAULT_SAMPLE
        for a in sys.argv[1:]:
            if a.startswith("--sample="):
                n = int(a.split("=", 1)[1])
        print(render(run_live(sample_size=n)))
    else:
        _test()
