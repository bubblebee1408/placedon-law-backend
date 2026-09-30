# VERIFY: Themis deep architecture (PLAN_25) + checker/forecast

## Verdict: GO for merge into the PR (draft); NO-GO for any use on real matters

**GO for merge into the draft PR:**

- Every blocker and major finding from both independent reviews is fixed.
- Each fix has a test that was written first and seen red.
- The seven forecast suites pass under 20 seeds.

**NO-GO for use on real matters,** which was always the design:

- No real legal data has been run through the package.
- No FORECAST-kind estimate can render a number until a track record exists for its target.

## Independent reviews

| Reviewer | First verdict | Findings | State now |
|---|---|---|---|
| trust-boundary-reviewer | **VETO** | F1 a forecast could render against any SERVABLE record; F2 the Move 2 prompt returned raw numbers and used a Ring 3-written rule; F3 no output-class mapping; F4 render dropped notes and basis; F5–F9 doc overclaims and missing tags | Fixed in `1dbff0b` (code) and `d839e20` (docs) |
| qa-reviewer | **NO-GO** | 1 complete pooling: "95%" interval covered ~4%, and `pooled_rate(0,5)` crashed; 2 events complete pooling crashed in 176/176 homogeneous cases; 3 `kaplan_meier` hung on NaN; 4 seed-pinned 95% checks (propagate failed 4/12 seeds, events 5/40); 5–12 minor issues (binning doc, overflow, float ceil, validation, n semantics, test looseness, stale docstring, duck-typing) | All fixed in this commit. Tests for 1–3 were seen red first: rates crashed, events FAIL, survival timed out |

**Maths confirmed by QA independently:**

- Beta and Gamma CDFs match numeric integration (max error 7e-12 and 1.6e-12).
- The moment estimators are derived correctly.
- The KM tie convention and the Greenwood log-log band match hand calculation.
- The conformal quantile, the ACI sign and the Prop 4.1 bound are correct.
- The Murphy identity holds.

## Measured

| Check | Result |
|---|---|
| Forecast suites | `__init__` 13/13, rates 19/19, survival 8/8, conformal 9/9, events 9/9, propagate 12/12, scoring 12/12 |
| `checker/rings.py` | 38/38; `violations()` = [] |
| **Seed robustness** (each suite × 20 seeds, run on copies) | **0 failures** in every module |
| Full harness | see the HARNESS_RESULT line appended below |

## Not verified

- **Any accuracy on real matters.** There are no data and no human labels.
- **Literature and vendor claims.** Mostly [S]; publisher hosts were egress-blocked.
- **The orchestration-branch defects** (F1 and F2 in appendix D) were confirmed by reading the code. They were not fixed here, because this session cannot push to that branch; they are Move 1.
- **`DECISIONS.md` is listed in `.claude/INDEX.md` but does not exist in this repo,** so the loop's "mirror into DECISIONS.md" step could not be done without inventing seven missing decisions. It is recorded here instead.
- **`BACKLOG.md`,** where QA wanted to file its result, also does not exist.

## Full harness, after all fixes

`HARNESS_RESULT suites=205 failed=2 status=RED`

The two red suites are `checker/provenance.py` (113/115) and `checker/s96_slice.py` (33/36).
They were red before this work too: the baseline run was `suites=198 failed=2`, with the same
two suites. The causes are environmental:

- a file-permission fixture that root can read;
- the Act 1 of 2018 witness, which lives only in a network cache.

`t0/finish` (PR #22) addresses them on the orchestration branch. Nothing imports
`checker.forecast`, so it cannot affect them.
