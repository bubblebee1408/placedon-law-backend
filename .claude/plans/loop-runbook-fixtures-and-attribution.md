# Loop Runbook — frozen duplicate fixture, and failure attribution

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-22 · Baseline: `255e37b`

## What I cannot do, stated once

Three of the six questions concern external material — Isaacus Kanon 2 Embedder retrieval gains,
Legal RAG Bench judge prompts, its multi-document handling. **The web-search budget is exhausted
(200/200).** Describing that benchmark's judge prompts from memory would be inventing plausible
specifics about a real artefact, which is the confabulation this entire repo is built to prevent.
Not doing it. Raising `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` reopens the question.

What those questions point AT is buildable without any citation, and is track 2.

## Track 1 — RED-08, frozen

Duplicate-claim rejection is tested inside `model_adapter._test()`. That is a unit test, not a
frozen adversarial fixture. The difference is not bookkeeping: the frozen attacks declare WHICH
LAYER must catch them and assert it against a run-time ledger, so a defence quietly migrating
between layers fails the suite. A unit test asserts the outcome and is blind to where it came from.

Promote it. Include the order-independence pair (the same two claims in both emission orders must
produce byte-identical results) and a same-id/different-evidence variant.

## Track 2 — the attribution ladder

Today a benchmark case yields one verdict. When it fails, the failure could belong to any stage, and
one number cannot say which. Separate them:

```
RETRIEVED   was the provision found at all?
ADMITTED    was it admitted for model use?
SERVED      did it reach the pack?
CITED       did the model cite it?
GROUNDED    did the verifier find the claim carried by it?
```

The point is attribution, not more metrics. "Accuracy 0.8" tells you nothing to act on; "the
provision was retrieved and admitted but never served" names the broken stage. A case that fails at
RETRIEVED is a retrieval problem no model change will fix, and one that fails at GROUNDED is not
retrieval's fault.

The ladder is monotonic: a stage cannot pass if the one before it failed. That property is worth
asserting, because a ladder that reports CITED while SERVED failed is describing something
impossible and its output cannot be trusted.

## Stop condition (hard)

RED-08 frozen, its expected layer asserted against the ledger; the ladder attributes every frozen
benchmark case to a stage, monotonicity asserted; all suites green under the pre-commit hook.

## Prohibited

No external citations. No document ingestion, review tables, drafting, Word export. No live LLM.
No PEFT. No entailment stub. No new dependencies. The 30 review items stay untouched — they are a
human's work and the tool must keep refusing to do it.
