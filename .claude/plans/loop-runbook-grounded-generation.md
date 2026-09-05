# Loop Runbook — grounded generation layer

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21
**Branch:** `ingest/board-meeting-rules-2014`

## What this layer is for

Retrieval decides *what law exists*. Admission decides *what may be shown*. This layer decides
*what may be said* — and, crucially, checks it afterwards. The model is the least trusted component
in the system and is treated that way: it receives a closed world, must cite into it, and every
sentence it produces is verified against the pack before anyone sees it.

## Build order (each green before the next starts)

1. `checker/claim_schema.py` — the atomic claim. Nothing downstream works if a "claim" can be a
   paragraph bundling three propositions and one citation.
2. `checker/model_adapter.py` — closed-world prompt + structured output. **Stub model first.**
   The entire contract is testable with no model call, and building against a stub keeps the
   contract honest rather than shaped around one model's habits.
3. `checker/claim_verifier.py` — per-claim support checking against the pack.
4. `scripts/baseline_eval.py` — frozen fixtures, claim-level metrics.

## Stop condition (hard)

All four modules green under `./scripts/run_tests.sh`, and `baseline_eval` reports decision
accuracy, unsupported-claim rate, and abstention correctness over frozen fixtures.

## Prohibited in this loop

- **No real LLM call.** Wiring a live model spends the user's money and needs their say-so. The
  stub proves the contract; the swap is one function.
- **No fine-tuning, no PEFT.** Nothing has been measured yet. Adaptation without an error taxonomy
  is guessing with a GPU.
- **No Rules-linked benchmark cases.** All 30 review items are open. A benchmark case built on
  unreviewed law would bake unreviewed law into the definition of correct.
- **No weakening of the admission gate to make a case pass.**

## The rule the layer exists to enforce

> A pack built in MODE_REVIEW must never reach the model.

An adapter that takes `mode` as an argument can be lied to by its caller. So **the pack carries its
own mode**, set at construction, and the adapter reads it from the pack rather than being told.

## Honesty constraint on the verifier

Without a model, the verifier cannot do entailment. It must not pretend to. What it can do is check
a **necessary condition** — that a claim's distinctive terms actually occur in the evidence it
cites — and say plainly that passing this is not proof of support. Calling a lexical check
"entailment" would be the exact overclaim this repo exists to prevent.

Contradiction detection is genuinely hard and is the known weak point in claim-level checkers. The
interface goes in now; the first implementation is conservative and says so.

## Monitor

```bash
cd ~/PlacedOn/placedon-law-backend
./scripts/run_tests.sh
python3 scripts/baseline_eval.py
```
