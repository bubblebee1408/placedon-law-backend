# Loop Runbook — Entailment / grounding engine

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-26
**Branch:** `engine/entailment` (base: `main`)

## Why this loop

`GROUNDED` cannot pass for any case. We verify that a citation exists, is
admitted, and is in force — never that our sentence *follows from* the served
text. Magesh et al. measured inapplicable authority contributing to 23-38% of
hallucinations in commercial legal tools; existence checks catch almost none of it.

## Hard stop condition

> A frozen benchmark of **≥120 claim/source pairs** (built from our own corpus,
> including prior-wording hard negatives) runs end to end; the entailment checker
> reports precision **and** recall on it with a stated decision threshold; at
> least one case reaches `GROUNDED` and at least one is correctly refused as
> `GROUNDING_FAILURE`; all existing suites stay green.

When that holds the loop stops and reports. It does not proceed to the next idea.

## Out of scope — do not build, even if it seems next

Neo4j · Pinecone · Elasticsearch · vector DB of any kind · UI · drafting
templates · a second statute · live LLM calls in the test path · LLM-as-judge
evaluation · fine-tuning a foundation model · scraping any blocked source.

## Tasks, in dependency order

Each ends with tests green and one commit.

### E1 — Mine labelled pairs from the corpus we already hold
Positives: `(section text, its amendment footnote claim)`.
Hard negatives: prior wording vs current text for the same span — semantically
near-identical, legally opposite. This is the pair that matters; a model that
cannot separate them serves repealed law as current.
Also: date negatives from `timeline.py`, instrument negatives from `legal_ref.py`.
- **Done when:** ≥120 pairs emitted with provenance, balanced, and a human has
  eyeballed 20 of them for label correctness.

### E2 — Freeze the benchmark
Write to `corpus/benchmark/entailment.jsonl`, hash-stamped, never regenerated
silently. A benchmark that moves when the code moves measures nothing.
- **Done when:** the file is committed with a manifest hash and a loader test.

### E3 — Deterministic baseline first
Lexical overlap + numeric/date agreement + citation match. No model.
This is the number every model must beat. If a model cannot beat it, we ship this.
- **Done when:** precision/recall reported on the frozen set.

### E4 — DECIDED 2026-08-26: build paraphrased pairs. Do not ship E3 as the gate.

Evidence. E3 scores **1.00** on the constructed set and **1/4** on the four
hand-written paraphrases in `corpus/benchmark/entailment_v1.json` — with all
three errors being false accepts, i.e. false statements of law declared
SUPPORTED.

The mechanism is structural, not a tuning problem:
- "first meeting within **ninety days**" — "ninety days" genuinely occurs in
  s.173, governing the gap between two meetings. The claim binds a real quantity
  to the wrong obligation.
- "file a return with the **Registrar**" — neither word occurs in s.173, yet
  coverage holds because they are 2 content words of ~10. The fixture's own
  acceptance note records that no threshold separates e01 from e02: both score
  0.667, because the borrowed vocabulary is the provision's.

Ship-as-is was the cheaper answer and it is the wrong one: it would attach a
citation to three false statements of law out of four.

**E3 is retained as a fail-closed pre-filter** — zero false accepts on the
matched subset, reliable on token-level substitution — but a claim it accepts is
*not obviously wrong*, which is not *supported by the cited text*.

**E4 tasks:**
1. Author paraphrased pairs where surface matching must fail: right vocabulary /
   wrong binding, quantity attached to the wrong obligation, negation, scope
   swap (every company vs listed company), conflated sub-sections.
2. Every pair human-verified. Model-generated paraphrase is permitted as a
   *drafting* aid; a model may never assign the gold label.
3. Target ≥120 pairs, ≥40 of them right-vocabulary/wrong-binding.
4. Then, and only then, evaluate a checker against them.
- **Done when:** the stop condition holds and E3's 1/4 ceiling is beaten on the
  paraphrase set without losing its 0.00 false-accept rate on the matched set.

### E5 — Wire into the ladder
`GROUNDED` becomes reachable in `checker/attribution.py`.
- **Done when:** the stop condition above holds.

## Binding constraints

- Never use ILDC, HLDC, IL-TUR, Pile of Law or any CC-BY-NC dataset. Commercial
  product; the licence forbids it and a third-party MIT re-upload does not cure it.
- Never evaluate with an LLM judge (Magesh et al.; Cymbler et al.).
- Never report an accuracy figure without n and the method.
- `s.52(1)(q)(ii)`: never emit bare statutory text without original matter.
- Do not bypass any WAF, robots rule, or access control. India Code lives at
  `indiacode.gov.in`; `.nic.in` is dead.
- If a step cannot be completed honestly, write UNVERIFIED and stop. Do not guess.

## Per-iteration gates

1. All existing suites green — a regression stops the loop, it is not worked around.
2. One task, one commit, conventional message.
3. New ideas go to `BACKLOG.md`, not into this loop.
4. Every claimed number carries n and method in the same sentence.

## Monitor

```bash
cd ~/PlacedOn/placedon-law-backend
git log --oneline engine/entailment ^main
bash scripts/run_tests.sh
```
