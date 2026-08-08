# Decision: diagnose API and result page

2026-08-08 · Phase 2 of 5 · reads `RESEARCH_diagnose.md`

## Selected: Option B — adopt the presentation improvements, reject the claims

## Rejected, with reasons

**Option A (build to spec at spec paths).** Rejected on three grounds, in order of severity:
it would ship a false verification badge and a fabricated statutory claim — both demonstrated
failing the build; it would state an invented annual-return deadline for a district whose
notification we do not hold; and it would duplicate a working, tested stack at new paths, leaving
two implementations of the same endpoint to drift apart.

**Option C (nothing).** Rejected: the four improvements are real, cost nothing, and one of them
is a latent React bug that grows with the finding count.

## Files

| File | Change |
|---|---|
| `frontend/app/result/page.tsx` | group findings into Critical / Warning / Unknown / Good with counts and empty states; fix `key={f.title}` → index-qualified key |

One file. Everything else in the spec either exists or is refused.

## Not building, and why

| | Reason |
|---|---|
| `risk-score.tsx` | No derivation for critical=50 / warning=20. A two-digit number nobody can source is worse than no number. |
| `citation-badge` "Verified against India Code & Gazette" | False twice over. `verify.py` fails the build on it. |
| `deadline: "2027-01-31"` | The deadline is District-Officer-set. We do not hold Bengaluru's. |
| `backend/routers/`, `backend/main.py`, `shared/types.ts` | Duplicate paths for code that exists. |
| slowapi | `checker/ratelimit.py`, 33 lines, no dependency. |

## Test cases, written before the code

1. 3 critical + 0 warning → "Critical Issues (3)"; the Warnings section shows its empty state.
2. 0 critical → "No critical issues found" renders, not an absent section.
3. Two findings with **identical titles** → both render (this is the `key` bug).
4. A `severity: "unknown"` finding → appears under its own heading, **not** silently dropped.
   The abstention is the product; losing it in a UI refactor would be the worst outcome here.
5. Section counts equal the number of cards rendered beneath each.
6. `scripts/verify.py` stays GO — in particular the badge and s.4 checks.

## Rollback

Single file, single commit. `git revert` restores the flat list. No API, schema, corpus or
citation change, so nothing downstream depends on this.

## Cost

**₹0.** No LLM call. `assess.py` is deterministic Python and the diagnose path has never made
one — total spend across the project remains ₹0.00.

## Reversal condition

If a customer conversation (H-1) shows people want a single comparable number more than they
want to know which specific obligation is unmet, revisit the risk score — but derive it from
something, and show the derivation.
