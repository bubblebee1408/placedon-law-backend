# LEARN: Themis deep architecture (PLAN_25)

## What cost something, and was recorded

**LESSONS L-27. A protection named in a plan is not a protection until the call path shows it.**
- PLAN_23 and PLAN_24 both said "a date filter runs before the model". The code audit showed it does not.
- Two real defects (FAILED stored as ANSWERED; no `ask` answer carries its source) sat behind a green suite.

**The build's first versions were wrong in ways only independent review caught.**
- **Forecasts:** a forecast could render against anyone's track record.
- **Complete pooling:** its "95%" interval covered the truth ~4% of the time, and the same branch crashed the events module in 176/176 homogeneous cases, which is the likely shape of the real corpus.
- **Survival:** hung on NaN.
- **Tests:** two suites passed only on their chosen seed.

The self-tests were green throughout. **The review found what the author's tests could not, because the author chose both the code and the checks.**

This is recorded in `docs/plans/plan25/03` §2.7, not as a new lesson. L-13 and L-14 (vacuous checks, and guards tested only against the author's own strings) already say it. This loop is another instance, and the fix was the same: an independent pass, then failing tests first.

## Tech debt taken knowingly

**T-9.** The forecast package is stdlib-only: Monte Carlo and bisection quantiles.

## State of the ledger this loop touched

- **New open items for the founder** (docs/plans/plan25/08):
  - the D3 amendment;
  - the NCLT and SEBI terms;
  - the counsel questions;
  - the funnel start.
- **Move 1 in 08** carries the orchestration-branch defects: F1, F2, F5, F7, the migration collision, and the MCP billed call.
- **`.claude/INDEX.md` lists `DECISIONS.md` as holding 8 decisions, but the file does not exist.** Recorded; not invented.
