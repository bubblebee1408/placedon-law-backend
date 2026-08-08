---
description: Open a session — read memory, state the goal, confirm before building
---

# /start

Do these in order. Do not skip to building.

## 1. Read the brain

```bash
python3 scripts/verify.py --fast          # is the tree healthy?
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

`RESEARCH_LOG.md` has 12 findings and `DECISIONS.md` 8 decisions with reversal conditions.
Rebuilding something already decided against is worse than building nothing.

## 4. The two questions that outrank everything

Before proposing any build, check these:

```bash
python3 -c "import json;p=json.load(open('corpus/provisions/posh_act_2013.json'))['provisions'];print('verified:',sum(1 for x in p if x['verified_by']),'/',len(p))"
```

- **0 / 30 verified** → the Q&A product cannot answer anything. H-2 is one evening and outranks
  every feature. Say so.
- **0 customer conversations** → H-1 decides whether the buyer is HR or the company secretary,
  which changes the product. Say so.

If a proposed build does not survive being compared to those two, say that plainly rather than
building it anyway.
