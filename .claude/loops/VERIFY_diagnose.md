# Verify: diagnose API and result page

2026-08-08 · Phase 4 of 5

## Verdict: **GO**

## Checks

| Check | Result |
|---|---|
| `scripts/verify.py` (22 checks incl. 8 suites + tsc) | **GO** |
| `npx tsc --noEmit` | 0 errors |
| Secrets scan | 0 |
| Rate limiting on `/api/diagnose` | present — `checker/ratelimit.py`, 5/min per IP |
| CORS allows `localhost:3000` | yes, plus exposed headers |
| E2E in Chromium | pass, 0 JS errors |
| LLM cost | **₹0.00** — no call on this path |

## E2E — the spec's own scenario (14 employees, Karnataka, IT/SaaS, nothing in place)

```
Fix first                          1
We couldn't answer this honestly   1
Worth attention                    1
Looks fine                         0   (empty state renders)
```

## Test cases from DECISION

| # | Case | Result |
|---|---|---|
| 1 | grouped sections with counts | pass |
| 2 | empty state renders, not an absent section | pass |
| 3 | **two findings with identical titles** | **pass — both render**; was the `key={f.title}` bug |
| 4 | `severity: "unknown"` survives | pass — its own section, the abstention intact |
| 5 | counts equal cards rendered | pass |
| 6 | `verify.py` stays GO | pass |

## The claims the spec asked for, measured on the live page

| Claim | On the page |
|---|---|
| risk score `NN/100` | **no** — no derivation exists |
| "Verified against India Code & Gazette" | **no** — fails the build |
| "Section 4(1) … 10 or more employees" | **no** — s.4 contains no number |
| a stated annual-return deadline | **no** — abstains |

"31 January" **does** appear — inside the abstention, explaining why we refuse to state it:
*"Gurugram notified 28 February, while most districts use 31 January… Most tools will
confidently say 31 January. That is a generalisation, not a rule."* That is the differentiating
text on the page, not a leak.

## Bugs found and fixed

**1. `key={f.title}` collision — fixed.** `assess.py` does not guarantee unique titles; two
colliding findings made React reuse the wrong node, putting the wrong citation under the wrong
heading on a compliance report. Now keyed by `section-index`. Same for `next_steps`.

**2. A gap in `verify.py` itself — found and closed during this phase.** The spec's IC
description is the L-1 fabrication: *"Section 4(1) of the PoSH Act, 2013 requires an Internal
Committee at workplaces with 10 or more employees."* Tested against the ratchet, it **PASSED** —
the check required the literal word "threshold", which that phrasing avoids.

The check now matches the *claim* (a headcount within 60 characters of an employee/worker noun,
cited to s.4 without "inferred") rather than one phrasing of it, and additionally scans
`assess.py` and `rules.py` source, because `assess()` only exercises the branches one profile
reaches. Re-tested:

```
FAIL  s.4 is never cited as the source of the ten-employee threshold
      checker/assess.py: a headcount and an s.4 reference share a line …
      Section 4 states no number.
```

This is the second time in one session that the ratchet needed an adversary to find its own
blind spot. See LESSONS L-11.
