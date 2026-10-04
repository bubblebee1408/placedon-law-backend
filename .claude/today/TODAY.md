# TODAY: 2026-10-04

**This note is a pointer, not a status report.** The last version described the retired PoSH
product as live for seven weeks after it was retired. A status copied here goes stale the same
way, so this file names where status lives and stops.

## Where the state lives

| Question | Authority |
|---|---|
| Is the tree healthy? | `./scripts/verify_green.sh`: read the `HARNESS_RESULT` line |
| What is open, and who is it blocked on? | `research/TASKS.md` |
| What is held, declared, out of scope? | `PYTHONPATH=. python3 checker/scope.py` |
| What is verified, and against what? | `CLAUDE.md` § Verification status |
| What was claimed and withdrawn? | `docs/evidence/RETRACTIONS.md`, `docs/evidence/CLAIMS_LEDGER.md` |
| Which documents are current? | `docs/START_HERE.md` §4, `docs/README.md` |

## Goal

(one sentence: run /start to set it)
