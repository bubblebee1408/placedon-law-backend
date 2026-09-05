# Ablation, corrected — the de-anchored re-run

Measured 2026-09-06 on **all 70** frozen `cross_section_eval` cases with de-anchored
prompts. This run **overturns the headline of the first run**, which was published on
20 cases with prompts that fed the model an example section number.

## What changed, and it is not small

| Tier | first run (anchored, n=20) | **corrected (de-anchored, n=70)** |
|---|---|---|
| V1 base model, no retrieval | 0.00 | **0.00** |
| V2 + dense top-5 | 0.00 | **0.24** |
| V3 PEFT, no retrieval | NOT_RUNNABLE | **NOT_RUNNABLE** |
| V4 + hybrid BM25⊕dense | 0.10 (confounded) | **0.63** |
| V5 V4 + schema-constrained | 0.45 | **0.61** |

Retrieval alone, no model: **RRF fusion p@1 0.80, recall@5 0.97.**

## Correction 1 — the earlier headline was wrong

The first run's sharpest claim was: *"V1 and V2 at exactly 0.00 are the sharpest data
point — handed the right section in its context 90% of the time, the model still could
not name it."*

**That was an artefact of our own prompt.** Both tiers ended with `"for example: 185"`,
and `gemma3:1b` echoed 185. With the example removed, V2 scores **0.24** and V4 scores
**0.63**. The model was not incapable of selecting from evidence; it was being told, in
effect, to answer 185.

The lesson is not about the model. A prompt defect produced a **confident, quotable,
wrong conclusion about a model's capability** — and it survived one round of publication
because the number was plausible in the direction we already believed. It was caught only
by re-inspecting raw outputs on a suspicious delta.

## Correction 2 — schema constraint can now be judged, and it does not help p@1

The first run could not separate schema constraint from example exposure, because V4 and
V5 differed in both. With exposure equalised:

    V4 (no schema constraint)  p@1 0.63
    V5 (schema constrained)    p@1 0.61

**A difference of one case — noise.** Schema constraint does **not** improve which
section the model names. What it does deliver is **schema validity 0.99** (69/70 valid
first try, 1 repair retry). That is the honest split: constrained decoding buys
*parseability*, not *accuracy*. Worth having for a machine-readable pipeline; worth
nothing for correctness.

## What survives unchanged

**V1 is still exactly 0.00 over 70 cases.** With no retrieval and no example, the model
names the correct governing section zero times out of seventy. Whatever `gemma3:1b`
knows, it is not the section numbering of the Companies Act 2013. Retrieval is not an
optimisation here; it is the entire source of the answer.

**Retrieval alone still beats every model tier.** Fusion 0.80 against the best model tier
0.63. So the operative conclusion holds — **no model belongs in the answer path today** —
but the margin is 0.17, not the 0.35 the first run implied, and it is a narrower and more
honest claim.

## llama3 is not usable on this hardware

`llama3` (4.7 GB) exceeded **600 seconds** to load and answer a single query on 8 GB
unified memory, against `gemma3:1b`'s 1.0-1.6 s/query. A 70-case run across four tiers is
not feasible. Recorded as measured infeasibility, not as a result: **whether a larger
model would beat fusion's 0.80 remains untested here**, and this hardware cannot settle
it.

## Caveats

- One model (`gemma3:1b`) at n=70; a second model is untested for the reason above.
- V3 was never run and is reported as *not measured*, never 0.00.
- The context ceiling was 0.96-0.97, so retrieval was rarely the limiting factor.
