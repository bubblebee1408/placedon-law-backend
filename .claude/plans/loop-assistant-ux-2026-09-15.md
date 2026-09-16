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
| UX-R | Research workflow → `docs/research/ux/` (Harvey assistant UI, Claude.ai chat UI, legal-AI chat patterns + trust evidence, internal audit) + source checks + design brief critic | complete | research commit (see log) | 9/9 agents. Checks: Harvey 7/7 hold; Claude 6/6; legal-AI 1 downgraded (L-A2 Westlaw side panel); audit 1 downgraded (I-E13). Main-session spot-checks VERBATIM: claim_verifier.py "This module never returns [SUPPORTED]"; Ding et al. AAAI 2025 random citations raise trust, checking lowers it. Brief: borrow structure/restraint not interaction model; `answered` truthful only for deterministic results; two as-of truths; contract has 3 defects (K8–K10); history & General mode OPEN |
| UX-C | `/v1/ask` contract: `web/assistant/contract.md`, fixtures for answered / partial / out_of_scope (+ a follow-up turn, a document-context turn), validator `scripts/assistant_contract.py --test` (RED first); add to gate. Fix brief defects K8 (no top-level `coverage` key), K9 (stages only where the engine emits them; never client-timed), K10 (field names/lines) | **complete** | contract commit (see log) | RED (NameError) → GREEN 27/27; gate 163 GREEN. Rebuild check caught a builder bug before commit (api `what_it_is_not` tuple ≠ JSON list) — fixed in the builder, test not loosened. Decision: fixtures are BUILT from deterministic engine modules (retrieve, evidence_pack, prescribed_thresholds, scope.refusal_for, api.compliance_pack, api.document_check) — no hand-typed legal text; test requires on-disk fixtures == rebuild. Real data probed: answered = CA13-S2-85-SMALL DOES_NOT_APPLY + ₹10 cr / ₹100 cr G.S.R. 880(E) 2025-12-01; partial = s.173 usable + s.16 SUSPENDED; out_of_scope = FEMA1999; document = 2024-06-01 (700(E)→880(E), 3 cannot_verify); follow-up = turnover limit. No stages in fixtures (no deterministic path emits them); subsection verbatim NEW |
| UX-D | Design workflow: 3 directions (Harvey-leaning / Claude-leaning / evidence-first native) → 3 judges → synthesis → harsh critique round → `docs/PLAN_13_ASSISTANT_UX.md` answering PLAN_13_PLAN §2 questions each with a verdict | **complete** | `b83e734` + dispositions commit | Directions done (775/715/824 lines + mockups + 3 shots each). **Judges: harvey 124 · claude 113 · evidence 106 → Harvey-leaning base.** Spec written, 1,143 lines. Critics returned **43 findings (7 fatal, 27 major, 9 minor)**; the single fix agent stalled 6× on the full payload → re-run as 4 sequential batches (`assistant-ux-apply-critics`) + a dispositions pass. Findings saved to scratchpad `ux/critic_findings.json` with unique ids |
| UX-B | Static prototype `web/assistant/` (web + task-pane layouts) rendering every fixture; acceptance checks PLAN_13_PLAN §6; Playwright screenshots 320/768/1024/1440 + grayscale | waiting-on-UX-C,UX-D | | |
| UX-V | Red-team workflow (legal accuracy & abstention · accessibility · design quality · NON_GOAL guard) → fixes → dispositions | waiting-on-UX-B | | |
| UX-M | Report `docs/ASSISTANT_UX_REPORT_2026_09_15.md`; TASKS.md rows; push notification; stop | waiting-on-all | | |

## Log
- 15-09 11:30 IST main session: plan + runbook written; research workflow launched (`wf_a834a1e6-418`, task `wf1s6jdmj`). Plan committed `fe9b3a5`.
- iter 1: UX-R running; every other row depends on it → nothing ready; waiting on the workflow notification (fallback wakeup 1800 s).
- iter 2 (13:00–13:20 IST): research workflow done → spot-checked, committed `6c6e848`. Screenshot helper `scratchpad/shot/shot.mjs` built and smoke-tested (cached chromium-1208, playwright 1.63 via pnpm in scratch only, network blocked, overflow detected correctly). Design workflow `wf_ad3553f6-c44` (task `w9tob6lix`) launched. UX-C contract done inline → `7d1fb4e`.
- **UX-B prep:** acceptance checker `scratchpad/shot/accept.mjs` implements PLAN_13_PLAN §6 across 5 fixtures × 5 widths (320/360/768/1024/1440): one state from fixture, state named in words, no overflow, figures show amount+instrument+in-force date, law_version shown with citations, no on-screen number absent from the fixture, keyboard reaches composer/citations/source panel, motion ≤200 ms and none under reduced motion, network blocked. It defines the DOM hooks the prototype must expose (`data-state`, `data-state-heading`, `data-figure`, `data-citation`, `data-source-panel`, `data-composer`, `data-law-version`, `data-chrome`). **Constraint found:** Chromium blocks `fetch()` of local JSON on file:// — the prototype must embed fixtures; plan: `assistant_contract.py --write` also emits `web/assistant/fixtures.js`.
- **Checker proved before use:** run read-only against the old public `ask.html` → **62/185 pass, 123 fail**: no `[data-state]`, no state named in words, horizontal overflow at 320/360, no composer-first tab order, and on-screen numbers absent from every fixture (800000, 5000000, 4200000, 20000000 — the superseded ₹8L/₹50L/₹42L/₹2cr figures the research flagged). Public repo still 0 changed files. (Note: "passes" include vacuous ones — e.g. citation reachability when a page has no citations.)
- `fixtures.js` embedded fixtures (RED NameError → GREEN 28/28; gate 163 GREEN) → `b7ebc25`. UX-B's design-independent prep is done; UX-B waits only on UX-D's spec. Waiting on design workflow notification (fallback 1800 s).
- **Outage 3 (session limit, ~13:40 IST → 16-09 00:30 IST, account re-login):** design workflow finished all 3 directions (specs 775/715/824 lines, mockups, 3 screenshots each — all on disk) then lost all 3 judges. Resumed same run (`wf_ad3553f6-c44`, task `whhc8pjdg`): directions replay from cache, judges → synthesis → critics → fix run live. Public repo 0 changed.
