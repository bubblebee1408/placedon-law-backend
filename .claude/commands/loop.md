---
description: Run the full R-D-B-V-L loop autonomously, delegating to subagents
argument-hint: [feature or bug]
---

# /loop $ARGUMENTS

Runs Research → Decision → Build → Verify → Learn end to end, spawning agents for the phases
that benefit from an independent pass. Every phase writes its artifact to `.claude/loops/`.

## Before anything

```bash
python3 scripts/verify.py --fast
python3 scripts/search_memory.py "$ARGUMENTS"
python3 scripts/search_memory.py --memory "$ARGUMENTS"
```

**Then check the two numbers that outrank every feature:**

```bash
python3 -c "import json;p=json.load(open('corpus/provisions/posh_act_2013.json'))['provisions'];print('verified:',sum(1 for x in p if x['verified_by']),'/',len(p))"
```

If the task is Q&A-related and verification is 0/30, say so and stop. Building on a gate that is
closed produces code nobody can use.

## Track-scoped evidence guard

`/loop` refuses to build on a track with no `[TRACK: x]`-tagged evidence below `## Findings` in
`RESEARCH_LOG.md`. Compliance, operations and market are separate trust contracts; evidence for
one does not license a claim in another.

## R — Research

Spawn in parallel, since the answers are independent:

- `market-researcher` or `hr-ops-researcher` — is this wanted? Sources or it did not happen.
- `corpus-engineer` — do we hold the statutory text? If not, this is blocked, not hard.
- `architect` — does the pattern already exist here?

Write `.claude/loops/RESEARCH_<SLUG>.md`: **Verdict / Confidence / Evidence (with file:line and
measured numbers) / Contradictions found / Three options with complexity, cost, risk, user value
/ Recommendation / Open questions.**

*Contradictions found* is mandatory. It is the section that caught the s.4 threshold error.
A failed search is a finding — record INCONCLUSIVE rather than padding with vendor blogs.

## D — Decision

Pick one option. **Reject the others in writing.** Write `.claude/loops/DECISION_<SLUG>.md` with
the file list, the test cases **written before the code**, a rollback plan, and a **reversal
condition** — the observation that would make you change your mind. A decision without one is a
preference. Mirror it into `DECISIONS.md`.

Escalate, do not decide: new paid dependency · raising the ₹3,500 serving cap · any change to a
legal claim · schema migration · anything touching complaint data.

## B — Build

`developer`, following `.claude/memory/CODING_CONVENTIONS.md`. The rule that matters: **code
decides, the LLM explains, a lawyer verifies.** Tests live in the module and assert against the
**ingested corpus**, not constants.

## V — Verify

```bash
python3 scripts/verify.py
```

**If it touches a UI flow, drive it in a real browser.** Three bugs shipped past a green suite
(LESSONS L-2). Then spawn `qa-reviewer` on the diff, and `trust-boundary-reviewer` on anything
making a legal claim.

**If a bug escaped, add a check to `scripts/verify.py` with its story in `because=` BEFORE
fixing it.** Write the check, watch it fail, then fix. A check written after the fix tests the
fix; a check written before tests the bug.

Write `.claude/loops/VERIFY_<SLUG>.md` — GO or NO-GO.

## L — Learn

Update `LESSONS.md` (**only if it cost something** — predicted lessons are slogans),
`TECH_DEBT.md` (every row needs a payoff trigger), `FEATURES.md`, `TODAY.md`. Rebuild the index
if files moved. Write `.claude/loops/LEARN_<SLUG>.md`, then commit — the message explains **why**;
the diff already says what.

## Honesty rules that override everything above

1. Never claim verification that has not happened.
2. Never invent a number. If it cannot be derived, say so and say why.
3. Quote statute **verbatim**. "Not exceeding three years" is not "up to three years".
4. Report what actually happened, including the parts that failed.
