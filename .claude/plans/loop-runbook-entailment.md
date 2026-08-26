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

### E4 — Entailment checker
Only now introduce a model. Report precision, recall, and the threshold.
Abstain by default: an unresolved pair is `UNRESOLVED`, never `GROUNDED`.
- **Done when:** it beats E3 on the frozen set, or E3 is kept and this is recorded.

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
