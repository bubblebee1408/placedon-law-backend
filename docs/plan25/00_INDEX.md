# PLAN_25: Themis, the deep architecture — research-grounded, built on the real orchestration code

Written 2026-09-30 by a `/loop` run:

- **Research:** four independent agents, in parallel.
- **Decision:** `.claude/loops/DECISION_THEMIS_DEEP_ARCH.md`.
- **Build:** `checker/forecast/`, 6 modules.
- **Verify:** the harness plus independent review.

It **extends** PLAN_19–24 and replaces none of them.

## The request

The founder asked for five things:

- An architecture deeper than PLAN_24's, able to "think beyond the data and predict".
- Grounding in research papers, articles and datasheets.
- Integration with the orchestration model being built.
- Use of God's Eye, free models via API/MCP/CLI with a post-funding upgrade, daily live
  data, and a hiring funnel for lawyer-engineers who work with their own agent.
- **Many bodies of law, not only the Companies Act.** The founder also asked what Harvey is
  for.

## What was actually done

1. **Research.** Four agents covered, in parallel:
   - the orchestration and God's Eye code (file:line evidence, 14 self-tests run);
   - 60+ papers;
   - free-model datasheets;
   - Harvey and the lawyer funnel.

   Reports: `.claude/loops/RESEARCH_THEMIS_DEEP_ARCH_{A,B,C,D}_*.md`.
2. **Two real defects confirmed** in the orchestration branch:
   - failed runs are stored as answered (`worker.py:146-147`);
   - no `ask` answer carries its source, so none can be approved or recalled
     (`verbs.py:215-216`).
3. **A false claim found in two plans:** "a date filter runs before the model". It does not,
   and the research's strongest result says that filter is what matters most.
4. **The prediction engine was built and tested:** `checker/forecast/`, six algorithms,
   standard library only, Ring 3 enforced. Measured on simulations with known truth
   (file 03).

## Reading order

| # | Document | What it answers |
|---|---|---|
| 01 | [What the research proves](01_WHAT_THE_RESEARCH_PROVES.md) | 15 findings, each forcing one design rule; the contradictions; what not to build |
| 02 | [Architecture](02_ARCHITECTURE.md) | The system on one page; three loops; the multi-statute pipeline; how each layer maps to real code |
| 03 | [Prediction engine](03_PREDICTION_ENGINE.md) | Six algorithms, their maths, and the numbers measured |
| 04 | [Models, API, MCP, CLI](04_MODELS_API_MCP_CLI.md) | The zero-cost stack, the post-funding upgrade, who may see client text |
| 05 | [Lawyer-engineer funnel](05_LAWYER_ENGINEER_FUNNEL.md) | Six stages with measurable gates; the Labelling Agent; the cost of 59 / 300 / 1,000 labels |
| 06 | [Live data sources](06_LIVE_DATA_SOURCES.md) | Every source per body of law, its access status, the daily schedule, the God's Eye patterns |
| 07 | [Harvey explained](07_HARVEY_EXPLAINED.md) | What it is, and the three reasons it matters |
| 08 | [Next moves and prompts](08_NEXT_MOVES_AND_PROMPTS.md) | Six moves in order, a Claude Code prompt each, founder actions, a study order |

## What this plan does not claim

- **No accuracy figure for Themis.** The gold set holds 0 human labels. Every number in
  file 03 is from a simulation where the truth is known. That proves the maths, not the
  product.
- **No figure from another system is Themis's figure.**
- **Evidence is mostly [S]**, read in search results only. Research and vendor hosts were
  egress-blocked. A person reads a source before it is quoted outside this repository.
- **Estimates of effort (for example one lawyer-engineer-month per body of law) are [I].**
