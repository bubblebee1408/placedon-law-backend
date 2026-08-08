# Research: POST /api/diagnose and the /result page

2026-08-08 · Phase 1 of 5

## Verdict

**The feature is built, live, and answering the spec's own test case.** The research phase exists
precisely to catch this. Four of the spec's improvements are worth adopting; five of its
requirements would ship claims we have already refused, and two of those **fail our own build**.

## Confidence

High — every claim below was executed, not read.

## Existing code

Every path in the spec is absent; every capability exists at a different path.

| Spec path | Reality |
|---|---|
| `backend/routers/diagnose.py` | `checker/app.py:98` — `POST /api/diagnose`, live |
| `backend/engine/applicability.py` | `applicability.py` (root), 283 lines, 10/10 tests |
| `backend/models/schemas.py` | Pydantic models inline in `checker/app.py`; wire types in `frontend/shared/types.ts` |
| `backend/main.py` | does not exist — the app **is** `checker/app.py` |
| `shared/types.ts` | `frontend/shared/types.ts`, 116 lines |
| `backend/tests/test_applicability.py` | tests live in-module; `python3 applicability.py` → 10/10 |
| `frontend/components/risk-score.tsx` | absent **by decision** — see below |

Live response for the spec's exact scenario (14 employees, KA, no IC/policy/return):

```
headline : PoSH applies to you. 1 thing needs fixing now. 1 we could not answer honestly.
findings : 3
  [critical] No Internal Committee                            s.4(1) + s.26
  [unknown ] Annual return — we will not guess your deadline   s.21/22, fixed by the District Officer
  [warning ] No written PoSH policy on display                 s.19
```

## Contradictions found

Five, each tested:

**1. `citation-badge.tsx`: "Verified against India Code & Gazette" — FAILS THE BUILD.** Proven:

```
FAIL  no false verification badge anywhere in the source
      false verification claim in: ['frontend/components/citation-badge.tsx']
```

False twice over — nothing is lawyer-verified (0/30), and the corpus came from India Code, not
the Gazette. Refused ~7 times; `scripts/verify.py` makes it permanent.

**2. The IC description is the L-1 fabrication, in user-facing prose.** The spec's `description`
reads *"Section 4(1) of the PoSH Act, 2013 requires an Internal Committee at workplaces with 10
or more employees."* **Section 4 contains no number.** The ten-worker figure is in s.2 and
s.6(1). This exact sentence has now appeared in five generated documents.

**This one initially PASSED our ratchet** — the check required the word "threshold", which the
spec's phrasing avoids. That gap is now closed (match the claim, not the phrasing; plus a source
scan), and the sentence now fails the build.

**3. Risk score 0–100.** No derivation exists for critical=50 / warning=20. The spec's own worked
example gives 90/100 for a company missing three things — a number precise to two digits, built
from constants nobody can source. Refused three times. The product ships a plain headline.

**4. "Karnataka Rule 14 sets deadline as January 31" and `deadline: "2027-01-31"`.** Research
established the PoSH annual-return deadline is set **per District Officer** — Gurugram notified
28 February, overriding the widely-repeated 31 January. We hold no Bengaluru notification, which
is why the live response says *"we will not guess your deadline."* No source was found for "Rule
14". A wrong statutory deadline in front of a customer is the failure this company exists to
prevent.

**5. `state: "KA"` instead of ISO `IN-KA`.** Load-bearing, documented at `frontend/lib/api.ts:8`:
`jurisdiction.scope_for()` derives the national tier by splitting on the first hyphen, so a bare
`"KA"` yields `['KA-BLR','KA','KA']` — the national tier collapses into the state and every
national provision silently stops matching. The API returns 422 on non-ISO codes so it cannot
regress unnoticed.

## Worth adopting

1. **Group findings into Critical / Warning / Good sections with counts and empty states.** The
   result page renders a flat list.
2. **"No critical issues found"** as an explicit empty state rather than absence.
3. **`has_return_filed: "yes"` → a positive finding.** Compliant areas are currently invisible.
4. **Fix `key={f.title}`** at `result/page.tsx:127` — collides once findings multiply (found
   independently in `RESEARCH_T7.md`).

## Options

| | A. Build to spec at spec paths | B. Adopt the 4 UX improvements | C. Nothing |
|---|---|---|---|
| Outcome | duplicate stack, **build fails** on the badge | grouped sections, empty states, key fix | flat list stays |
| Cost | ₹0 + rewriting working code | ₹0, ~1 file | ₹0 |
| Risk | ships two refused false claims | none — no legal text changes | latent React key bug |

## Recommendation — B

Adopt the four presentation improvements. Reject the five claims, with the two hard failures
demonstrated above rather than argued.
