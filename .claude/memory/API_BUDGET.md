# API Budget

**Two budgets, not one.** The agent-system spec merged them and that is a category error worth
naming, because it would have you rationing the wrong resource.

| | What it pays for | Cap | Enforced by |
|---|---|---|---|
| **Serving** | LLM calls made *by the product, for a customer* | **₹3,500 / month** | `backend/budget.py`, in code, before the call |
| **Building** | Claude Code sessions that write the product | your subscription | not per-call; there is nothing to meter |

The spec proposed spending ₹3,000/month of the ₹3,500 on build agents (24 sessions × ₹125). That
leaves ₹500 to serve customers — about **515 answers** — while the thing being metered isn't
billed per-call anyway. Keep them separate. The ₹3,500 exists so a runaway loop cannot bankrupt a
student; it was never a development allowance.

---

## Serving budget — the live one

```
Monthly cap    ₹3,500.00     MONTHLY_CAP_INR
Daily cap      ₹  116.67     MONTHLY_CAP_INR / 30   ← derived, never asserted
Spent to date  ₹    0.00     no LLM call has ever been made
```

**The daily figure is derived, and that is load-bearing.** Two specs asserted "₹150–250/day"
against a ₹3,500 cap; ₹150 × 30 = ₹4,500 and ₹250 × 30 = ₹7,500 both breach it, so every daily
check would pass while the month blew out. The autonomous-agent-system document reintroduced the
identical bug as "₹155/day" (× 30 = ₹4,650). `scripts/verify.py` now fails if anyone asserts a
daily cap above `monthly / 30`.

### Measured cost per answer

| Model | In / out | ₹ per answer | Answers within ₹3,500 |
|---|---|---|---|
| **Haiku 4.5** ← in use | ~6,700 / ~700 | **₹0.97** | ~3,600 |
| Sonnet 5 | same | ~₹2.9 | ~1,200 |
| Opus 5 | same | ~₹4.86 | ~720 |

The spec's "₹3–5 per call" priced a mid-tier model at Opus rates. Measured, not assumed;
USD/INR 95.23 as at 2026-08-06.

**Model choice is a cost lever, not a correctness lever.** `applicability.py` decides whether a
law applies; the LLM only explains, and `verifier.py` rejects any number absent from the source.
A cheaper model cannot make the product wrong — it can only make it read worse.

### Why spend is ₹0

Every path currently abstains **before** the call. `verifier.should_abstain()` runs pre-flight,
and 0 of 30 sections carry `verified_by`, so no evidence packet has ever been clear to spend.
The Health Scan, all three document generators, and every validation are pure code — they cost
₹0 by construction, not by throttling.

The first rupee gets spent the day a lawyer signs off (BACKLOG H-2).

---

## Ledger

`backend/.budget.json`, written by `FileStore`. Not in git. A corrupt ledger **refuses to spend**
rather than assuming zero — the spec's in-memory version reset on every serverless invocation,
which meant the cap silently did not exist in production.

| Month | Calls | Spend | Notes |
|---|---|---|---|
| Aug 2026 | 0 | ₹0.00 | corpus unverified; every call gated pre-flight |

---

## Cost controls in force

- **Pre-flight abstention** — the decision not to answer costs nothing.
- **Keyword routing first** — `retrieval.keyword_route()` resolves most questions with no model.
- **Prompt caching on the system prompt** — ~0.1× on cached reads.
- **Top-k = 3 provisions** — context is the cost driver, so it is bounded.
- **Hard gate before the request** — `can_make_call()` runs *before* the HTTP call, not after.
- **Unknown or retired model IDs raise** rather than defaulting to a price.

## Review triggers

Raise the cap only when serving revenue exists. Until then, if spend exceeds ₹500/month with
fewer than 10 real users, something is looping — check the ledger before raising anything.
