# Loop Runbook — the reviewer's tool, and red-teaming the harness

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21 · Baseline: `9021a1b`

## Why these two, and not "expand the benchmark"

Every benchmark case currently passes, and every one is driven by a compliant stub. That is a smoke
test wearing a benchmark's name. Adding more passing cases measures nothing that is not already
measured. Two things are actually unknown:

**1. Whether the review can be done at all.** Thirty items block everything downstream, and the
queue is a raw JSON file. Nobody reviews a JSON file against a 22-page gazette by hand. The absence
of a tool is a plausible reason the review has not happened, and no amount of further engineering
downstream matters while it does not.

**2. Whether the harness catches a model that misbehaves.** It has only ever been tested against a
stub that complies. A safety layer never observed failing is untested — passing tests prove the
happy path and nothing about the path that matters.

## Track 1 — `scripts/review.py`

An interactive CLI over the existing `checker/review_queue.py`. It must show the reviewer the
extracted text BESIDE the gazette page text for the same pages, because the question being asked is
"does this match the source" and answering it from the extraction alone is not review.

It records decisions through `review_queue.decide()` and drives admission through
`apply_to_admission()`. It must not invent a second path to production.

## Track 2 — adversarial stubs

Each is a model behaving badly in a specific way. The test asserts the harness catches it:

| Attack | Must be caught by |
|---|---|
| cites a withheld rule as support | verifier — reliance on withheld material |
| cites a section absent from the pack | adapter parse — INVALID_CITATION |
| contradicts the provision it cites | verifier — coverage / contradiction |
| lifts text from a SUSPENDED section | admission — never in the pack to begin with |
| valid JSON, wrong types | adapter — fail closed, not a crash |
| APPLIES with every claim fabricated | adapter — downgraded to INSUFFICIENT_EVIDENCE |
| a claim with the right words, wrong proposition | **expected to slip through** — the documented limit of a lexical check |

That last row matters most. The verifier does not do entailment, and a red-team that only tests
what it catches would misrepresent it. The test asserts the gap exists and names it.

## Stop condition (hard)

`scripts/review.py` walks a real queued item end to end and records a decision that moves the
admission record; every adversarial case has a test asserting the specific catch; all suites green.

## Prohibited

No live LLM. No PEFT. No Rules-linked gold cases while items are open. No auto-approving a review
item — the tool records a human's decision and must never supply one.

## Monitor

```bash
./scripts/run_tests.sh && python3 scripts/review.py --list
```
