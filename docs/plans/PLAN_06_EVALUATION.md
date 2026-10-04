# Evaluation — how to be believed

The point of this document: an evaluation a sceptical Indian corporate lawyer, or
a competitor, cannot dismiss. Everything here is sourced.

## Do not use LegalBench as a headline number

LegalBench (162 tasks, CC BY 4.0 in aggregate but **per-task licences**) is built
almost entirely on **American law**. Its rule-recall and rule-application tasks
are jurisdiction-locked by construction — they test recall of a *specific*
jurisdiction's rule. None of the 162 tasks encode Indian corporate law.

It cannot be repurposed by substitution. It can only be used as a **template** for
building an Indian equivalent. Quoting a LegalBench score for a Companies Act
product invites the obvious and fatal objection: *you benchmarked against tasks
that do not apply to you.*

**LegalBench-RAG** measures retrieval — but over a static, single-snapshot corpus
of NDAs and M&A agreements. There is no versioned corpus, no as-of-date
conditioning, and no score for whether a retrieved clause was in force at the
relevant time. **It is silent on the only question we care about.**

## The benchmark to build instead

There is a published template, and it is the strongest evidence our thesis exists:

> **Temporal Misgrounding in Legal RAG** (arXiv:2608.09393). A 32,436
> article-version corpus of French tax law (1938–2031) with explicit validity
> dates, from the official Légifrance API. 209 all-model-hard questions. Scored
> with deterministic nugget matching — regex and numeric tolerance, explicitly
> **not** LLM-as-judge, to avoid circularity.
>
> **Static RAG retrieved the date-applicable version 0% of the time.** Not
> approximately zero — zero, across all 209 questions, at 2.7% strict accuracy,
> while confidently citing real but temporally inapplicable text. Parametric-only
> scored 3.0%. Date-conditioned retrieval over the same versioned corpus:
> **98.3–99.1%.**

The Indian equivalent does not exist, and building it would be a genuine
contribution rather than a reproduction. That is the eval to build: Companies Act
2013 provisions with in-force date ranges, queries anchored to past dates where
the applicable version differs from today's, scored on whether the version cited
was actually in force.

**Our ₹4 crore case is the first row of that benchmark.**

## The three scores that must never be merged

Routinely conflated, and they diverge sharply:

1. **Answer correctness** — is the conclusion right?
2. **Provenance correctness** — is the citation real and applicable?
3. **Temporal correctness** — was that the version in force on the relevant date?

A system can pass 1 and 2 and fail 3. That is the ₹4 crore failure exactly, and
it is invisible to every benchmark listed above except the versioned one.

## Hallucination: the numbers, verified

**Magesh, Surani, Dahl, Suzgun, Manning & Ho** (Stanford RegLab) — preregistered
22 March 2024, peer-reviewed in *Journal of Empirical Legal Studies* 2025.
202 hand-crafted queries across four categories including false-premise questions.

| Tool | Accurate | Hallucinated |
|---|---|---|
| Lexis+ AI | 65% | **17%** |
| Westlaw AI-Assisted Research | 41% | **33%** |
| Ask Practical Law AI | ~19% | 17% (62% incomplete) |
| GPT-4 (non-legal baseline) | — | **43%** |

Their definition is the one to adopt: **hallucinated = incorrect OR misgrounded**,
where misgrounded means a real citation that does not support the claim or is
inapplicable. Misgrounded errors are more dangerous *because they survive surface
citation-checking* — which is precisely what a citation-existence check like
Harvey's would pass.

Corroborating this: on a benchmark of injected hallucinated citations, the best
detector reached >80% recall on fabricated citations and verbatim misquotes but
only **52.8% on incorrect pincites** — detection is weakest exactly on the
misgrounded class. Note the preregistration: it is why that study is taken
seriously and most vendor self-assessments are not. **Preregister ours.**

## Evaluating abstention properly

A bare "abstains X% of the time" is meaningless. Report a **risk-coverage curve** —
accuracy-among-answered at multiple coverage levels — plus a confusion matrix on
the abstention decision itself:

| | Should have answered | Should have abstained |
|---|---|---|
| **Answered** | correct | **dangerous overconfidence** |
| **Abstained** | unhelpful caution | correct caution |

Two findings that should shape the target:

- **AbstentionBench** (Meta/FAIR): abstention is unsolved even in frontier models,
  scale does not help, and **reasoning fine-tuning actively hurts it** — models
  become more confidently wrong. Directly relevant: one of its six scenarios is
  stale/outdated information.
- **InsufficiencyBench** (legal-specific, attorney-annotated): the best model
  scored F2 ≤ 0.46 on identifying *which* facts are missing; GPT-5.2 over-flagged
  **72.4% of complete queries** while staying silent on **13.2% of genuinely
  deficient ones.** Abstention today is badly calibrated, not merely rare.

Its metrics are the right ones for us, because they distinguish useful refusal
from generic hedging: credit only for naming *which* fact or instrument is
missing, whether the stated reason is legally sound, and whether the model
smuggled in a conclusion anyway. Our pack already names the missing limb and the
instrument — so we should score well, and we should prove it rather than say it.

## The rules

1. **Preregister** the question set and metrics before running anything.
2. **Deterministic scoring only.** No LLM-as-judge — it inherits the recency bias
   under test.
3. **Human legal-expert ground truth**, stratified by jurisdiction, date-sensitivity
   and false-premise.
4. **n in the hundreds**, with confidence intervals. Anything smaller reads as
   anecdote.
5. **Mutation-test the eval.** Feed it a knowingly-wrong system. If the score does
   not fall, the eval is decoration — the same standard applied to every check in
   this repo.
6. **The metric that decides adoption is false-accept rate on legal rows**, not
   fluency.

## First measurement — `checker/pit_bench.py`

Built 2026-09-10, on the Indian equivalent of the French versioned-corpus design.
Nine dated cases, every date a boundary of an instrument on disk or a point
inside one. Deterministic scoring, no LLM judge.

| Arm | Accuracy | Wrong answer | Wrong refusal |
|---|---|---|---|
| **Placedon, holding both instruments** | **1.00** | **0** | **0** |
| Baseline: latest figure, ignoring the date | 0.33 | **6 of 9** | 0 |
| Placedon, holding neither (abstention arm) | 0.22 | **0** | 7 |

**Ground truth is the law on each date, decided by each instrument's own
commencement — not by what we hold.** That separation is the whole design, and the
first version of this benchmark got it wrong: the cases encoded *"we cannot serve
this"* as the law, so the moment G.S.R. 880(E) was attested the benchmark scored a
**correct** engine at 0.67. A benchmark whose expected answers move when you
acquire an instrument is measuring your holdings, not the law. Acquisition state
now lives in the harness, and a test asserts the expectations are identical under
both states.

The baseline's failure is symmetric, which is the point: it serves today's ₹10
crore for a 2024 date just as readily as it served ₹4 crore for today's. One
figure for every date across a four-year span.

The third arm is what stops this being a vanity metric. With neither instrument
held the engine invents nothing — **0 wrong answers** — but it scores **0.22**,
because seven correct answers were knowable and it could not give them. Refusing
is right and it is not free. A product whose pitch is "we refuse" needs a
benchmark that charges it for refusing.

Mutation-tested both ways: a system with no currency layer must score below 1.00,
and a system that abstains on everything must be penalised.

**Honest limit:** nine cases over one prescribed chain is a mechanism test, not a
coverage claim. The set grows with each acquisition; the scorer is frozen so a
later run is comparable.

## What we can claim today, and what we cannot

**Can:** the engine refuses where it cannot verify, the refusals name the
instrument, and we found three real staleness defects in our own shipped code.

**Can, as of 2026-09-10:** 1.00 on nine dated point-in-time cases while holding
both instruments, against a no-currency-layer baseline at 0.33 — with the
four-outcome breakdown, the case list, both acquisition arms, and the mutation
tests published alongside it.

**Cannot:** generalise that. Nine cases over one prescribed chain is a mechanism
test, not a coverage claim, and there is still no external Indian benchmark to be
scored against. Anyone quoting "1.00" without "on nine cases over one chain" is
overstating it, including us.
