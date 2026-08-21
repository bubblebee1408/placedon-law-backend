# Loop Runbook — automation, CLI hardening, wider attacks

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-22 · Baseline: `1c6bb2d`

## What the analysis found

Six questions were raised about this system. Five describe behaviour that already works, verified by
running the code rather than recalling it:

| Question | Verified answer |
|---|---|
| Duplicate claim IDs in mixed packs | First survives, duplicate rejected and REPORTED in `rejected_claims`. Order decides which wins — arbitrary, but nothing is silent. |
| INVALID_CITATION vs UNSUPPORTED | Distinct verdicts. `S999` (absent) → INVALID_CITATION; a real citation that fails grounding → UNSUPPORTED with the missing terms named. |
| Boilerplate filters | `_RULE_MATCH_STOP` drops `section`, `rule`, `company`… so `"section 11"` yields 0 false notices where it once flagged r.10 and r.11. |
| Type-confusion fixes | `claims` as a string and `evidence_ids` as an int, both now failing closed. |
| Reviewer CLI edge cases | **Unaudited.** |

The sixth is a genuine hole: **nothing runs the 26 suites automatically.** No git hook, no CI. Every
safety property in this repo is enforced only by someone remembering to type a command.

## A measurement that changed the plan

The full suite runs in **4 seconds**. I had specified a fast changed-files mode so a pre-commit hook
would be tolerable. It is not needed, and building it would be complexity bought for nothing. The
hook runs everything.

## Tracks

**1 — Automation.** Pre-commit hook + CI workflow. The hook must block a commit when any suite is
red, be installable and removable by an obvious command, and never be the only copy of the logic
(CI runs the same script).

**2 — Reviewer CLI hardening.** A human is about to use this on 30 items. Edge cases: empty queue,
already-resolved item, missing or unreadable PDF, page range beyond the document, interrupted
decision, resuming a partly-reviewed queue, and a queue file that is corrupt.

**3 — Wider attacks.** The red-team covers 2 type-confusion shapes; I reproduced 5. Cover all of
them, since each took a different route through the parser.

## Deliberately NOT built

**The entailment layer.** RED-07 proves a real blind spot — a fabricated obligation graded SUPPORTED
because it borrows the provision's vocabulary. Closing it needs an entailment model, and there is
none here. The FIXTURE is frozen now, because ground truth for that question is cheap and permanent
and will be needed first. The layer waits. Building a pluggable adjudication stage around a stub
would be scaffolding pretending to be progress.

## Stop condition (hard)

The hook blocks a deliberately-red commit and passes a green one; every CLI edge case has a test;
all 5 type shapes are covered; all suites green.

## Prohibited

No live LLM. No PEFT. No Rules-linked gold cases while the 30 items are open. No new dependencies.
