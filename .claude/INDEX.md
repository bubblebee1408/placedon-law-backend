# Placedon agent system

Version 1.1 · 2026-08-08

## Quick start

```bash
./setup.sh                    # idempotent; installs deps, builds the index, runs verify
python3 scripts/verify.py     # GO / NO-GO, 21 checks
```

Then in Claude Code: `/start`, then `/build <feature>` or `/fix <bug>` or `/research <topic>`.

## Directory map

| Path | What |
|---|---|
| `.claude/today/TODAY.md` | Current session goal |
| `.claude/memory/*.md` | Persistent context — product, architecture, budget, lessons, debt, features, conventions |
| `.claude/loops/*.md` | Per-feature loop artifacts: RESEARCH / DECISION / VERIFY / LEARN |
| `.claude/commands/*.md` | The commands. `/start` `/build` `/fix` `/research` `/loop` `/today` |
| `.claude/agents/*.md` | **12 agents.** The loop delegates to these. |
| `scripts/` | The tools. `.claude/scripts/` holds wrappers so both paths work. |
| `RESEARCH_LOG.md` | 12 findings, each with *Contradictions found* |
| `DECISIONS.md` | 8 decisions, each with a **reversal condition** |
| `BACKLOG.md` | Work items and blockers, with IDs |

## The loop

**Research → Decision → Build → Verify → Learn.** `/build` runs it end to end and each phase
writes its file into `.claude/loops/`.

## Agents

Twelve, not five. The spec's Investigator / Architect / Engineer / QA / Strategist map onto
agents that already exist and are more specific:

| Spec role | Use |
|---|---|
| Investigator | `market-researcher`, `hr-ops-researcher`, `corpus-engineer` |
| Architect | `architect`, `product-planner` |
| Engineer | `developer` |
| QA | `qa-reviewer`, `trust-boundary-reviewer`, `legal-verifier` |
| Strategist | `business-strategist`, `cost-governor` |

`trust-boundary-reviewer` and `legal-verifier` have no counterpart in the five-agent model, and
they are the two that stop this product shipping a false legal claim.

## Escalation

**Auto-approve:** file layout, component structure, tests, styling, bug fixes, refactors.

**Human required:** a new paid dependency · anything raising the ₹3,500 serving cap · any change
to what the product claims legally · a schema migration · anything touching complaint data ·
price changes · public launch.

## Budget

Two budgets, and conflating them is a category error — see `memory/API_BUDGET.md`.

- **Serving** ₹3,500/month, `MONTHLY_CAP_INR/30 = ₹116.67/day` **derived**, enforced in
  `backend/budget.py` before the call. Spent to date: **₹0.00**.
- **Building** — Claude Code sessions. Not billed per call; nothing to meter.

## Departures from the v1.0 spec, and why

Recorded here rather than silently, because each is a fact the spec got wrong:

| Spec said | Reality |
|---|---|
| Claude 3.5 Sonnet | Retired. Product runs **Haiku 4.5**, measured **₹0.97/answer** (spec said ₹3–5). |
| Daily allowance ₹155 | ₹155 × 30 = ₹4,650, over the ₹3,500 cap. Derived value is ₹116.67. `verify.py` fails on any asserted daily cap above monthly/30. |
| chromadb + sentence-transformers | ~2 GB of dependencies. Replaced by BM25F: **0.05 ms mean, 449 KB, exact recall.** Revisit at the labour codes (~500 sections of prose). |
| weasyprint | Needs cairo/pango; does not run on Vercel serverless. Print-ready HTML + browser print instead. |
| pgvector / Supabase | Not in use. Corpus is sha256-pinned JSON on disk. |
| slowapi | `checker/ratelimit.py`, 33 lines, no dependency. |
| TECH_DEBT "None yet" | Eight real items, each with a payoff trigger. |
| LESSONS: 5 principles | Nine lessons, each with the incident that cost something. |

## What the system does not change

```
PoSH sections lawyer-verified : 0 / 30
customer conversations        : 0
LLM calls ever made           : 0
git remotes                   : 0
```

The Q&A product cannot answer anything until the first number moves. `/start` prints these every
session so no amount of tooling can quietly route around them.
