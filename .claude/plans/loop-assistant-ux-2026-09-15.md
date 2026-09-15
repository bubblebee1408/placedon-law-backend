# Loop runbook — Ask section (grounded assistant) UX, 2026-09-15

Plan and reasons: `docs/PLAN_13_ASSISTANT_UX_PLAN.md`. **Every iteration: read this file first, update it last.**

## Iteration protocol
1. Read this file; `git log --oneline -5`; `git status --short`.
2. If a background Workflow is running and nothing else is ready, schedule a 1800 s fallback wakeup and end.
3. Take the first `ready` row top to bottom; set `in-progress`.
4. Do it under CLAUDE.md: inspect first; tests RED → GREEN; `bash scripts/run_tests.sh` GREEN; one logical
   change per commit (repo convention incl. `Gate:` line); push `loop/bookmark-godseye-v0` only.
5. Workflow rows: when done, read outputs, spot-check 2 claims yourself against their URLs/files, commit.
6. Record status, commit, evidence below; append to Log.
7. Wakeup 60 s if ready work remains; 1800 s if only a Workflow is pending. When every row is complete or
   blocked: write the report row, push notification, stop.

## Stop rules
- A task fails twice → `blocked`, reason recorded.
- Never edit `~/PlacedOn/Placedon-law-business-plan` (PUBLIC). Never deploy. No model calls (fixtures only).
- No new runtime dependency. Playwright only via the cached chromium (`~/Library/Caches/ms-playwright/chromium-1208`), invoked from the scratchpad, never added to the repo.
- Memory is 8.6 GB: at most one workflow at a time; never run the gate while a workflow's agents are mid-flight if memory free < 20%.
- Usage limits: if a workflow dies on a limit, check disk for partial outputs before re-running anything.

## Tasks
| ID | Task | Status | Commit | Evidence |
|---|---|---|---|---|
| UX-R | Research workflow → `docs/research/ux/` (Harvey assistant UI, Claude.ai chat UI, legal-AI chat patterns + trust evidence, internal audit) + source checks + design brief critic | in-progress | | launched with this runbook |
| UX-C | `/v1/ask` contract: `web/assistant/contract.md`, fixtures for answered / partial / out_of_scope (+ a follow-up turn, a document-context turn), validator `scripts/assistant_contract.py --test` (RED first); add to gate | waiting-on-UX-R (internal audit) | | |
| UX-D | Design workflow: 3 directions (Harvey-leaning / Claude-leaning / evidence-first native) → 3 judges → synthesis → harsh critique round → `docs/PLAN_13_ASSISTANT_UX.md` answering PLAN_13_PLAN §2 questions each with a verdict | waiting-on-UX-R | | |
| UX-B | Static prototype `web/assistant/` (web + task-pane layouts) rendering every fixture; acceptance checks PLAN_13_PLAN §6; Playwright screenshots 320/768/1024/1440 + grayscale | waiting-on-UX-C,UX-D | | |
| UX-V | Red-team workflow (legal accuracy & abstention · accessibility · design quality · NON_GOAL guard) → fixes → dispositions | waiting-on-UX-B | | |
| UX-M | Report `docs/ASSISTANT_UX_REPORT_2026_09_15.md`; TASKS.md rows; push notification; stop | waiting-on-all | | |

## Log
- 15-09 11:30 IST main session: plan + runbook written; research workflow launched.
