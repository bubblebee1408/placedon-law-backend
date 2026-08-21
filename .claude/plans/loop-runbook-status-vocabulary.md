# Loop Runbook — status vocabulary and duplicate determinism

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-22 · Baseline: `aed8794`

## What is NOT being built, and why

A large product design arrived: review tables, document upload, fact extraction, drafting, Word
export — a Harvey-class surface. It is good thinking and it is not what to build now.

**The 30 review items are still unreviewed.** Building a document-review product on a corpus nobody
has verified is the pattern this project has spent days refusing. Most of that design needs document
ingestion, which is a large new surface resting on unadmitted law.

Two pieces of it are unblocked and load-bearing. Those are in scope. Nothing else is.

## A finding that sharpens track 2

`applicability.py` at the repo root is HR-era debris — PoSH, ESI, `has_women_employees`,
`employees_below_wage_ceiling` — left from the abandoned labour-law pivot (R-010). Its philosophy is
right ("decides whether a provision applies — NEVER the LLM") and its vocabulary is the exact problem:

```python
class Result: APPLIES | DOES_NOT_APPLY | INSUFFICIENT_DATA
```

There is no way to say **"I could not assess this."** So a withheld Rule collapses into either
DOES_NOT_APPLY or INSUFFICIENT_DATA, and the first is a false statement of law while the second
blames the document for a gap that is actually ours.

## Track 1 — duplicate claim_id determinism

Today the first claim wins and the duplicate is rejected. The rejection is visible, so nothing is
silent, but WHICH claim survives depends on the order the model happened to emit them. For a legal
output that is indefensible: two claims sharing an id means claim identity is unreliable, and
picking one is choosing an answer by accident.

Reject **all** claims sharing a duplicated id, warn `DUPLICATE_CLAIM_ID`, and downgrade the decision
if no material claim survives.

## Track 2 — separate the axes

One status cannot carry provision availability, legal applicability, and obligation. Split them, and
make the conservative transitions explicit:

```
provision retrieved but not admitted  -> NOT_ASSESSABLE   (never DOES_NOT_APPLY)
provision admitted, predicate unknown -> INSUFFICIENT_FACTS
required Rule withheld                -> NOT_ASSESSABLE, and say which Rule
```

The rule the track exists to enforce: **the system may never say a provision does not apply when the
truth is that it could not be assessed.** Those are opposite answers to a lawyer — one closes the
question, the other says the question is still open and why.

## Stop condition (hard)

Duplicate ids are order-independent; a withheld Rule yields NOT_ASSESSABLE naming the Rule, never
DOES_NOT_APPLY; both tested against real evidence packs; all suites green under the pre-commit hook.

## Prohibited

No document ingestion. No review-table UI. No drafting. No live LLM. No PEFT. No deletion of
`applicability.py` in this loop — retiring HR-era debris is its own change with its own care.
