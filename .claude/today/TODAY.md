# TODAY: 2026-08-08

## Goal

Agent system complete. Loop running its first real pass on **T-7** (report passed in the URL
query string; breaks at ~10 findings).

## The two numbers that outrank every feature

```
PoSH sections lawyer-verified : 0 / 30      → H-2, one evening, unlocks all 12 core questions
customer conversations        : 0           → H-1, ten calls, decides who the buyer is
```

Neither is a code problem. `/start` prints them every session so no amount of tooling can quietly
route around them.

## State

| | |
|---|---|
| `scripts/verify.py` | **GO — 22 checks** |
| Documents live | `ic_order`, `posh_policy`, `board_report` |
| Agent index | 89 files, 13,823 lines, 0.05 ms mean query |
| LLM spend, all time | **₹0.00** |
| Git remotes | **0** ← T-8 |

## Done this session

- [x] Verification ratchet — 22 checks, each carrying the incident that bought it
- [x] `LESSONS.md` — 10 lessons, each with its incident
- [x] Agent index + search (BM25F, measured against the specified embedding stack)
- [x] `CODING_CONVENTIONS`, `TECH_DEBT` (8 items with payoff triggers), `FEATURES`
- [x] `/start` `/build` `/fix` `/research` `/loop`, delegating to the 12 existing agents
- [x] `.claude/INDEX.md` — records the 8 departures from the v1.0 spec and why
- [x] `setup.sh` — idempotent, ends on a verify run

## In flight

- [ ] T-7 research (agent) — three options for getting the report out of the query string
- [ ] Independent review of the ratchet (agent) — hunting for checks that pass **vacuously**

## Next, in order

1. **T-8 — a git remote.** No trigger, no excuse. An `ln -sf` destroyed four command files today
   and git was the *entire* recovery path. It is one laptop deep. See LESSONS L-10.
2. **H-2 — the lawyer.** 12 sections, one evening, rehearsed end to end.
3. **H-1 — ten calls.** One question: *"Your Board's Report this year needs three numbers about
   sexual harassment complaints — do you know which three?"*
4. T-7, once the research lands.

## Constraints

One feature per session. No new paid dependency without asking. Nothing that raises the ₹3,500
serving cap. No claim of verification that has not happened.
