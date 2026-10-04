---
description: Open a session — read memory, state the goal, confirm before building
---

# /start

Do these in order. Do not skip to building.

## 1. Read the brain

```bash
./scripts/verify_green.sh                # is the tree healthy? (no --fast mode; all or nothing)
cat .claude/today/TODAY.md                # where did we stop?
cat .claude/memory/BLOCKERS.md            # what is actually blocked?
```

Then skim `.claude/memory/LESSONS.md`. It is short and every line cost something.

## 2. Rebuild the index if the tree moved

```bash
git log --oneline -5
python3 scripts/index_codebase.py         # ~0.5s
```

## 3. State the goal in one sentence, then stop

Say what today's goal is, what it unblocks, and **what it costs**. Then wait.

Before proposing anything, check it is not already answered:

```bash
python3 scripts/search_memory.py --memory "<the thing you are about to build>"
```

Decisions with reversal conditions live in `docs/plans/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md`
and `.claude/DECISIONS.md`; withdrawn claims in `docs/evidence/RETRACTIONS.md`.
Rebuilding something already decided against is worse than building nothing.

## 4. The questions that outrank everything

Before proposing any build, check these:

```bash
grep -nE "\*\*founder\*\* \| \*\*(open|ready|blocked)" research/TASKS.md   # human-only blockers
PYTHONPATH=. python3 checker/scope.py | tail -5                                   # what is held
```

- **No practising lawyer or Company Secretary has reviewed any output** (H-001) → no accuracy
  claim is possible, whatever is built. If H-001 is still open, say so.
- **One body of law of eleven is held** → a feature that needs an unheld body will refuse
  until it is acquired. Say so before building it.

If a proposed build does not survive being compared to those, say that plainly rather than
building it anyway.
