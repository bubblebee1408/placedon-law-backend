# M5 — ablation matrix, measured 2026-09-05

Model `gemma3:1b` via local Ollama. **Sample: the first 20 of the 70 frozen
cross_section_eval cases.** Every number below is over those 20 and no others.
Task: name the section of the Companies Act 2013 that governs a plain-English question.

## The matrix

| Tier | Configuration | p@1 | context ceiling | schema-valid | latency |
|---|---|---|---|---|---|
| V1 | base model, no retrieval | **0.00** | — | — | 0.62 s |
| V2 | + dense top-5 | **0.00** | 0.90 | — | 0.73 s |
| V3 | PEFT, no retrieval | **NOT_RUNNABLE** | — | — | — |
| V4 | + hybrid BM25⊕dense | **0.10 — CONFOUNDED** | 0.95 | — | 0.85 s |
| V5 | V4 + schema-constrained | **0.45** | 0.95 | 1.00 (20/20 first try) | 0.89 s |

**Retrieval alone, with no model in the loop at all: RRF fusion p@1 0.80, recall@5 0.97.**

## V3 is not a gap in the data — it is a gap in the hardware

No CUDA device (Apple M1, 8 GB unified, Metal only), so no QLoRA/Unsloth run is
possible. And there is no annotated gold set to train on: the 70 eval cases are the bar,
not training data, and there are no annotators. Both blockers recorded; `p@1` is
reported as *not measured*, never as 0.00. A row that was never run must not look like a
row that scored zero.

## V4 is confounded, and the cause is our prompt

The V4→V5 jump on **identical retrieved context** was implausible, so raw outputs were
inspected before publishing. Extraction is not at fault (`s.23`→23, `185`→185 both parse
correctly). The cause is prompt anchoring:

    V4 prompt: "...Answer with the section number only, for example: 185"

`gemma3:1b` then emits **185** for unrelated questions — the example, echoed. Observed
directly: "rules for a private placement offer" → `185` (gold 42); "how does a company
issue further shares" → `185` (gold 62). V5's prompt offers three varied examples
(185, 188(1)(a), 2(85)) and demands a bare reference, so no single number dominates.

So 0.10 measures a badly designed prompt, not hybrid retrieval. It is recorded
CONFOUNDED rather than published as a finding, and the honest conclusion is that **the
V4-vs-V5 comparison cannot be used to claim schema constraint improves accuracy.** What
V5 legitimately demonstrates is a 100% schema-validity rate with zero repair retries.

## The finding that survives every caveat

A 1B model **degrades** a retrieval system that already works:

    RRF fusion, no model      p@1 0.80
    best model tier (V5)      p@1 0.45
    model with retrieval only p@1 0.00 (V2)
    model alone               p@1 0.00 (V1)

V1 and V2 at exactly 0.00 are the sharpest data point. Even *handed the right section in
its context 90% of the time*, gemma3:1b could not name it. The bottleneck is not
knowledge and it is not retrieval — it is the model's ability to select from evidence
placed in front of it.

This is the plan's own central claim, confirmed against its own prediction and pointing
the opposite way. The plan expected V5 to be "state of the art" and retrieval to be the
enabling layer. Measured here, **retrieval IS the system, and this model subtracts from
it.** Accuracy is a systems property — and the corollary the plan did not draw is that
a weak model is not a neutral addition to a good pipeline. It is a regression.

## What this does and does not license

- It does **not** show fine-tuning is pointless. V3 was never run; a tuned model might
  clear 0.80. That remains untested and untestable on this hardware.
- It **does** show that shipping a small local model in front of this retrieval stack
  would halve accuracy, so no model belongs in the answer path today.
- It **does** justify fusion (M3) on its own merits: 0.80 with no model, no GPU, no
  fitted parameter, and no new dependency.

## Caveats stated plainly

- n=20, not 70. A single case moves p@1 by 0.05.
- One model only (`gemma3:1b`, the sole model that fits comfortably in 8 GB).
- Prompts were not tuned per tier, which is exactly what confounded V4. A tuned V4 would
  score higher; how much higher is unmeasured.
