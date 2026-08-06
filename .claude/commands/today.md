---
description: Day-one kickoff. Runs the full research-to-plan sequence and tells you exactly what to do today.
---

You are running the day-one sequence for the Indian HR compliance AI product. The founder is a
solo student in Bengaluru with near-zero capital. Be concrete and honest about effort.

## Sequence

1. **Read context**: `docs/03_MARKET_RESEARCH_BUSINESS_PLAN.md`,
   `docs/04_GTM_AND_PRODUCT_STRATEGY.md`.

2. **Invoke `market-researcher`** on these three questions, in order:
   a. What are Indian SME HR managers currently complaining about re: compliance? (forums,
      Reddit, LinkedIn, Quora — find actual quotes, not summaries)
   b. Which Karnataka labour code rules are notified vs pending, as of today?
   c. What do greytHR / Keka / Zoho actually charge and what do they explicitly NOT cover?

3. **Invoke `business-strategist`** to write or update `DECISIONS.md` with the committed
   positions: beachhead, pricing tiers, free tier, wedge. Each with a reversal condition.

4. **Invoke `product-planner`** to produce `BACKLOG.md` scoped strictly to V1 (PoSH only),
   ordered by dependency, every item citing its evidence.

5. **Produce `TODAY.md`** — the founder's actual next actions, split into:
   - **Do today** (≤3 items, each under 2 hours)
   - **Do this week**
   - **Blocked on a human** (finding the employment lawyer, booking customer interviews)

## Rules
- Be honest about what cannot be answered from research alone. Customer interviews are not
  replaceable by web search — say so.
- The first item in `TODAY.md` should almost always be a customer conversation or the
  100-question proof artifact, not writing code.
- If the research suggests the premise is weak, say that plainly at the top rather than producing
  a plan for a bad idea.
