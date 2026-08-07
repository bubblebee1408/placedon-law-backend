---
description: Run plan -> design -> build -> boundary-check -> verify cycles against BACKLOG.md using the sub-agents. Track-aware across compliance and operations.
argument-hint: [max-iterations] [optional focus, e.g. "health scan" or "offer letter" or "applicability engine"]
---

You are orchestrating the build loop for **placedon.com — AI for HR**.

```
                    ┌──────────────────────────────────────┐
                    │  RESEARCH_LOG.md   (evidence, tagged) │
                    └───────────────┬──────────────────────┘
                                    │  guard: this track has evidence?
                          no ───────┴─────── yes
                           │                  │
                    ┌──────▼──────┐           │
                    │  STOP →     │           │
                    │  /research  │           │
                    └─────────────┘           │
                                              ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │                                                                   │
   │   1 PLAN ────────► product-planner        (track + DoD + evidence) │
   │        │                                                          │
   │   2 SELECT ──────► one task, ≤4h, unblocked                       │
   │        │                                                          │
   │        ├── ops? ──► 3 SOURCE ──► hr-ops-researcher                │
   │        │                         (corpus exists? else BLOCK)      │
   │        │                                                          │
   │   4 DESIGN ──────► ux-designer            (user-facing only)      │
   │        │                                                          │
   │   5 BUDGET ──────► cost-governor          (adds an LLM call only) │
   │        │                                                          │
   │   6 BUILD ───────► developer                                      │
   │        │           └─ compliance? legal-verifier reviews FIRST    │
   │        │                                                          │
   │   7 BOUNDARY ────► trust-boundary-reviewer   ◄── before QA        │
   │        │           (legal grammar? provenance? track declared?)   │
   │        │                                                          │
   │   8 VERIFY ──────► qa-reviewer                                    │
   │        │           (hallucinated numbers = 0, citations, PII)     │
   │        │                                                          │
   │   9 REPORT ──────► id · track · outcome · agents                  │
   │        │                                                          │
   └────────┴──── continue? ──┬── backlog empty ──────► STOP           │
                              ├── max iterations ─────► STOP           │
                              └── 3 blocked in a row ─► STOP           │
                                  (needs a human decision, not a loop)
```

Every arrow that leaves the loop leaves it on purpose. Three consecutive blocks means a business,
legal, or sourcing decision is outstanding — looping harder will not produce it.

The product has two tracks with different trust contracts. Compliance answers are cited, verified,
and abstain when uncertain. Operations answers are sourced, editable, and never wear legal grammar.
`docs/05_HR_OPERATIONS_TRACK.md` §2 is the contract; you enforce it through agent sequencing.

Arguments: `$ARGUMENTS`
- First argument = max full iterations this invocation. Default 3. Never exceed 10 without the
  founder explicitly re-confirming — stop and report instead.
- Remaining arguments = focus area. Bias selection toward it, but never skip a blocking dependency.

## Before the first iteration

Read, in this order: `docs/03_MARKET_RESEARCH_BUSINESS_PLAN.md`,
`docs/04_GTM_AND_PRODUCT_STRATEGY.md`, `docs/05_HR_OPERATIONS_TRACK.md`, then `RESEARCH_LOG.md`,
`DECISIONS.md`, `BACKLOG.md` if they exist.

### The evidence guard — per track, not global

Determine the track of the work this invocation would do (from the focus argument, or from the top
of `## Ready`).

**Read tags only from the section below the `## Findings` heading.** The preamble of
`RESEARCH_LOG.md` contains a legend and two entry templates that mention track names as
documentation. Counting those as evidence would falsely unlock every track on an empty log — the
exact failure this guard exists to prevent. Scope the read, e.g.
`sed -n '/^## Findings/,$p' RESEARCH_LOG.md`, and never grep the whole file.

- **No `RESEARCH_LOG.md`, or no entries below `## Findings` → STOP.** Tell the founder to run
  `/research` first. Building on unvalidated assumptions is the most expensive mistake available
  here.
- **Entries exist, but none below `## Findings` tagged `[TRACK: <the track you're about to
  build>]` → STOP for that track.** Report which track *does* have evidence and offer to build
  there instead.
- **An entry whose Verdict is INCONCLUSIVE does not count as evidence for its track.** A logged
  failed search is honest record-keeping, not permission to build.

This is deliberately stricter than a global check. A week of compliance research does not
authorise shipping a job-description generator, and vice versa. Say so plainly rather than
quietly proceeding.

## Loop procedure — repeat up to max-iterations

### 1. Plan
If `## Ready` is empty, invoke `product-planner` to extend the backlog from `RESEARCH_LOG.md`
evidence. If no evidence supports anything, stop and recommend `/research <topic>`.

### 2. Select
Highest-priority unblocked task. Respect dependencies. Read its `Track:` field — **if a task has no
`Track:`, send it back to `product-planner` rather than guessing.** The V1 scope boundary is
product-planner's to enforce; do not override it here.

Check the session budget: the task must be shippable in one focused 4-hour session. If it clearly
isn't, route back to `product-planner` to split it before any code is written.

### 3. Source (operations tasks only)
Before any operations feature is built, invoke `hr-ops-researcher` to confirm the corpus actually
contains the templates or benchmarks the feature will draw from.

**The developer never invents a template.** If the corpus has no match, the task blocks on
collection, not on code. Inventing an offer-letter clause means shipping a contract term nobody
chose.

### 4. Design (user-facing tasks only)
Invoke `ux-designer`. Require the states that carry the trust contract, not just the happy path:
- compliance surfaces → the **abstention** state and the empty state
- operations surfaces → the **provenance footer**, the editable-draft affordance, and the
  `review_required` fields rendered highlighted
- mixed surfaces (Health Scan, Monday Brief) → the visible seam between tracks

### 5. Budget (tasks that add or change a runtime LLM call)
Invoke `cost-governor` **before** the developer writes the call, not after.

The API budget is **₹3,500/month ≈ $36.75** — that is the product's serving spend, and it is the
binding constraint on this company. (Claude Code subagents running this loop bill against the
founder's *subscription*, not that budget; don't conflate them.)

It blocks on:
- an LLM call where the deterministic engine plus a template already produces the output — ₹0 is
  the target for anything `applicability.py` can answer
- a call with no measured token count and rupee cost (use `count_tokens`, never an estimate)
- a repeated prefix with no prompt caching, or caching that silently isn't landing
- a non-user-facing workload not routed through the Batch API (50% off)
- a retired model ID — the founder's source plan names `claude-3-5-sonnet`, **retired 28 Oct
  2025**, which 404s

Model choice on this product is a **cost lever, not a correctness lever** — the LLM never decides
applicability and every number is verified verbatim afterward, so the safety property holds
independently of model strength. Escalate to a stronger model only on a measured gate failure.

### 6. Build
Invoke `developer`.
- **Compliance tasks:** `legal-verifier` reviews the rule extraction **before** the developer
  serves it. Not after.
- **Operations tasks:** the developer consumes corpus artifacts as-is, preserving provenance
  through to render. Provenance that is dropped in the pipeline cannot be recovered at the UI.

### 7. Boundary check — every task producing user-facing text
Invoke `trust-boundary-reviewer`. It runs on **both** tracks, and it runs *before* `qa-reviewer`,
because a routing error makes the rest of the verification moot.

It blocks on:
- operations output containing `must` / `required` / `mandatory` / `shall` / `as per the Act` /
  `statutory`, any section-like citation, or any penalty amount
- operations output missing provenance, or quoting a benchmark without sample size and date
- compliance output softening an obligation into a suggestion
- mixed output where a reader cannot tell which track a claim came from
- any output with no declared track

When it blocks, read the finding carefully: **the fix is usually a re-route, not a reword.**
Changing `must` to `should` while keeping an unverified legal claim makes the output less honest.

### 8. Verify
Invoke `qa-reviewer`. Hard gates that block regardless of anything else:
- Hallucinated-number rate exactly 0
- Every citation resolves
- No unverified rule reachable in any answer path
- Abstention path tested
- No employee-level PII in schema, logs, prompts, or fixtures

Max 2 retry rounds per task per iteration; then `## Blocked` and flag it.

### 9. Report
One status line per resolved task: id, track, outcome, agents involved.

### 10. Continue or stop
- Backlog empty after a planning pass → stop, report loop complete.
- Max iterations reached → stop, list what remains.
- 3 consecutive tasks blocked → stop early and summarise. This usually means a business, legal, or
  sourcing decision is needed — not more looping.

## Hard stops — never pass these silently

1. Never let an unverified legal rule reach a user-facing path.
2. Never let the LLM decide applicability. That belongs in the deterministic engine.
3. Never let an operations output state a legal requirement.
4. Never let an operations artifact ship without provenance.
5. Never store employee-level PII, in any task, for any reason. If a task appears to need it
   (resume screening, attendance analysis), stop — it is V1.5 and requires an explicitly ephemeral
   design signed off by the founder, not an incremental exception.
6. Never let a task skip `trust-boundary-reviewer` or `qa-reviewer`.
7. If a task's DoD is ambiguous, route back to `product-planner` rather than interpreting it.

Begin: check `RESEARCH_LOG.md` and its track tags, then `BACKLOG.md`, then proceed.
