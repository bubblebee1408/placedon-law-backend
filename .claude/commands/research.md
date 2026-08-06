---
description: Run a focused research cycle. Use this FIRST, before any building. Produces evidence, not opinions. Routes to the market or operations researcher by topic.
argument-hint: [topic, e.g. "what HR complains about" or "offer letter templates" or "greytHR pricing"]
---

You are running a research cycle for **placedon.com — AI for HR**.

Topic: `$ARGUMENTS`

If no topic is given, pick the highest-value open question from `RESEARCH_LOG.md`. If that file
doesn't exist, start with: **"What do Indian SME HR managers actually complain about — across all
of their work, not only compliance?"** That question is deliberately broad, because the product is
AI for HR and the founder has not yet validated which part of the job hurts most.

## Step 0 — Route the topic

Two researchers own different questions. Choose before you start; say which you chose and why.

| Topic is about… | Researcher | Track tag |
|---|---|---|
| Demand, pain, pricing, competitors, willingness to pay, regulatory timing | `market-researcher` | `[TRACK: market]` |
| Templates, benchmarks, playbooks, how HR actually does the work | `hr-ops-researcher` | `[TRACK: operations]` |
| A specific statute, rule, or notification | `market-researcher`, then route findings to `legal-verifier` | `[TRACK: compliance]` |

A topic can legitimately need both — e.g. *"what do offer letters at Bengaluru startups look
like, and do HR people find writing them painful?"* is one question for each. Run both and log two
entries. Do not merge them; they have different evidence standards.

**Track tags are load-bearing.** `/loop` refuses to build on a track that has no evidence tagged
for it. An untagged entry unlocks nothing.

## Procedure

1. **Gather.** Invoke the chosen researcher. Require:
   - every claim carries a source URL and a publication date
   - FACT vs INFERENCE labelled explicitly on each finding (market/compliance), or provenance and
     sample size recorded on each artifact (operations)
   - contradictions between sources reported, not silently resolved
   - findings appended to `RESEARCH_LOG.md` with the track tag in the heading

2. **Assess.** Invoke `business-strategist`:
   - Does this change any decision in `DECISIONS.md`?
   - Does it validate or invalidate the beachhead (Karnataka SMEs, 20–200 employees)?
   - Does it change pricing, sequencing, or which track leads?
   Record any change as a decision **with a reversal condition**. A decision without one is a
   belief, not a decision.

3. **Convert.** Invoke `product-planner`:
   - Does this evidence justify a new backlog item, on this track?
   - Does it invalidate anything currently in the backlog?
   Schedule only what the evidence supports, and only on the track the evidence came from.

4. **Report.** Print: what was learned, what changed, what is still unknown, and the single
   highest-value next question.

## Hard rules
- **Never end a research cycle in a feature decision without evidence.** If the research was
  inconclusive, say so and propose the next question rather than guessing.
- **Do not build anything in this command.** Research only. Building is `/loop`.
- If a finding contradicts a committed decision, surface it loudly at the top of the report.
- If the topic requires interpreting a law, route to `legal-verifier` and flag that a human
  employment lawyer is needed. Researchers do not interpret statutes.
- **Web search cannot replace customer conversations.** If the topic is really *"will they pay"* or
  *"does this hurt enough"*, say plainly that the answer requires talking to 10 people and that no
  amount of searching substitutes for it.
