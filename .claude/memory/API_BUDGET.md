# API Budget

> The spec's daily figure overspends the monthly cap by 29–114%. See `SPEC_ERRATA.md` E-3.

## The numbers
| | Value |
|---|---|
| Monthly cap | **₹3,500** (~$36.75 at ₹95.23/USD, 2026-08-06) |
| Daily, derived | **₹116** — not the spec's ₹150–250, which breaches the cap by day 14–23 |
| Per answer, Haiku 4.5 | **~₹0.97** (~6,700 in / ~700 out) |
| Per answer, Opus 5 | ~₹4.86 |
| Answers/month at Haiku | **~3,600** |
| Answers/day at Haiku | **~120** — not the spec's 50-call ceiling |

The spec's "₹3–5 per call, 50 calls/day" prices a mid-tier model at Opus rates. Both halves are
wrong in opposite directions.

## Routing
| Workload | Model | Cost |
|---|---|---|
| Company Health Scan | **none** | ₹0 — deterministic engine + templated obligations |
| Cited Q&A | `claude-haiku-4-5` | ~₹0.97 |
| Operations drafts | `claude-haiku-4-5` | ~₹0.97 |
| 100-question proof artifact | `claude-opus-5` **via Batch API** (50% off) | ~₹243 one-time |
| Gazette extraction | `claude-haiku-4-5`, structured output | ~₹1 for the whole PoSH corpus |

Escalate to a stronger model **only on a measured gate failure**, never on intuition.

## Levers, in order
1. **Don't call.** ₹0 for anything `applicability.py` can answer. This is the biggest lever by far.
2. **Prompt caching.** Server-side, ~0.1× on reads. Min prefix 4,096 tokens on Haiku 4.5, 512 on
   Opus 5. Verify with `usage.cache_read_input_tokens` — zero means something in the prefix varies.
   (`lru_cache` is per-process and caches nothing on serverless — errata E-5.)
3. **Batch API.** 50% off anything not user-facing.
4. **Measure, never estimate.** `count_tokens` against the actual model. Never `tiktoken`.

## Runtime enforcement
`backend/budget.py` → `BudgetTracker.can_make_call()` before every request. On exhaustion the
product degrades to template mode and says so; it does not fail silently.

## Current
Spend today: ₹0 · Spend this month: ₹0 · Remaining: ₹3,500
*(No LLM call has been made yet. The checker makes none.)*
