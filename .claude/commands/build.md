---
description: Full R-D-B-V-L loop for one feature, with subagents
argument-hint: [feature]
---

# /build $ARGUMENTS

One feature. No scope creep. If it splits, build the first half and say so.

## R — Research (before any code)

```bash
python3 scripts/search_memory.py "$ARGUMENTS"
python3 scripts/search_memory.py --memory "$ARGUMENTS"
```

Spawn in parallel where the answers are independent:

- **`market-researcher`** — is this wanted? Sources or it did not happen. A failed search is a
  finding; record it as INCONCLUSIVE rather than padding with vendor blogs (`RESEARCH_LOG.md`
  has a worked example).
- **`corpus-engineer`** — do we hold the statutory text this needs? If not, the feature is
  blocked, not hard.
- **`architect`** — does this pattern already exist here?

Write the finding into `RESEARCH_LOG.md` in the existing shape: **Verdict / Confidence /
Evidence / Contradictions found / What this means / Open questions**. *Contradictions found* is
not optional — it is the section that caught the s.4 threshold error.

## D — Decision

Three options, scored on complexity, cost, risk, user value. Pick one, **reject the others in
writing**. Record in `DECISIONS.md` with a **reversal condition** — the observation that would
make you change your mind. A decision without one is a preference.

Escalate to the human, do not decide: a new paid dependency, anything that raises the ₹3,500
serving cap, any change to what the product claims legally, anything touching complaint data.

## B — Build

Use **`developer`**. Conventions in `.claude/memory/CODING_CONVENTIONS.md`; the one that matters
is *code decides, the LLM explains, a lawyer verifies*.

Tests go in the module, and assert against the **ingested corpus** rather than constants.

## V — Verify

```bash
python3 scripts/verify.py
```

GO or NO-GO. If it touches a UI flow, **drive it in a real browser** — three bugs shipped past a
green suite (LESSONS L-2).

Then spawn **`trust-boundary-reviewer`** on anything that makes a legal claim, and
**`qa-reviewer`** on the diff.

**If a bug escaped, add a check to `scripts/verify.py` with its story in `because=` before
fixing anything else.** That is the ratchet — the bug gets paid for once.

## L — Learn

Update `.claude/memory/`: `LESSONS.md` (only if it cost something — predicted lessons are
slogans), `TECH_DEBT.md` (with the trigger to pay it off), `FEATURES.md`, `TODAY.md`.

Then commit. The message explains **why**, not what — the diff already says what.
