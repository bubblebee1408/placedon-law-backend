# Overnight loop runbook — 2026-09-14

The plan and its reasons: `docs/PLAN_11_NEXT_MOVE.md`. This file is the loop's working state.
**Every iteration: read this file first, update it last.**

## Iteration protocol

1. Read this file. Read `git log --oneline -5` and `git status --short`.
2. If a background Workflow is running and its task is the only ready work, schedule a 1800 s
   fallback wakeup and end the iteration.
3. Pick the **first** row below whose status is `ready` (top to bottom). Set it `in-progress`.
4. Do it inline, following CLAUDE.md: inspect and name affected files first; test RED → GREEN;
   `bash scripts/run_tests.sh` must end `status=GREEN`; one logical change per commit;
   `git push origin HEAD` (this branch only).
5. Record: status, commit hash, one-line evidence, in the table. Append to the Log.
6. Research/architecture rows are launched with the Workflow tool and run in the background.
   When one completes: read its outputs, adversarially spot-check two claims yourself, commit
   the docs, mark the row.
7. Schedule the next wakeup: 60 s if more ready work exists, 1800 s if only a Workflow is
   pending. Stop (ScheduleWakeup stop) when every row is `complete` or `blocked`, after writing
   the morning report.

## Commit convention (this repo)
Subject `type: description`; a body saying what was observed and why; then a line
`Gate: HARNESS_RESULT suites=N failed=0 status=GREEN` copied from the run, then
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. The pre-commit hook re-runs the
gate (~81 s per commit) — run `git commit` with a 300 s timeout.

## Stop rules
- A task fails twice → `blocked`, reason recorded, move on. Never leave the gate red: revert
  your own uncommitted change instead.
- Azure model calls counter reaches 300 → no more Azure calls; mark dependent rows `blocked`.
- Ollama: never load a model over 8B, and unload before running the gate (GPU memory makes 3
  suites fail otherwise — observed today).
- Anything needing a credential, a purchase, a new cloud resource, or buyer documents → `blocked`.

## Counters
| Counter | Value | Cap |
|---|---|---|
| Azure model calls | 12 (probe runs + smoke tests, 14-09 daytime) | 300 |
| Iterations | 0 | — |

## Tasks

| ID | Task | Status | Commit | Evidence |
|---|---|---|---|---|
| R | Research workflow R1–R5 + source checks + gaps (background Workflow task `wmcndrraz`, run `wf_cf6b0319-a8b`). On completion: read the 6 docs under `docs/research/`, spot-check 2 claims, commit as one docs commit | in-progress | | launched by main session |
| L1 | Refuse empty/whitespace text value — `checker/document_extract.py:227`; replay stored T05 proposal → abstains; gpt-5-mini & 70B served facts unchanged | ready | | |
| L2 | `cin` value must be CIN-shaped; reuse `checker/party_resolution.py` pattern; report, never repair | ready | | |
| L5 | `text_field_probe`: score served values vs case ground truth (`WRONG_SERVED`); re-score stored runs, no new calls | ready | | |
| L3 | Widen `checker/field_binding.py` to text/date fields; replay all four stored runs; commit ONLY if 0 new refusals on correct facts, else record and mark blocked-for-founder | ready | | |
| L4 | `eval/realrun/run.py --azure <deployment>`; run gpt-5-mini and llama-3-3-70b (≤ 80 calls); record leak rates | ready | | |
| D1 | Text-layer census of `corpus/testdocs/` per page (text / needs OCR / mixed); MEASURED, public docs, labelled not-the-20-document-test | ready | | |
| D2 | Page-anchored spans in `checker/document_extract.py` for multi-page PDFs (uses `checker/pdf_text.py`) | ready | | |
| D3 | Provider registry module listing extract adapters + capabilities; serving routes untouched | ready | | |
| E1 | Install AWS CLI (`brew install awscli`), OCI CLI (`brew install oci-cli`), Kaggle CLI (`pipx install kaggle` or `pip3 install --user kaggle`); record versions; no credentials | in-progress | | install launched by main session (background task `b3u1xoaq4`); verify versions with `aws --version; oci --version; kaggle --version` |
| E2 | `docs/TOOLING.md`: CLIs present + MCP servers to add once credentials exist (exact commands, not registered) | ready | | |
| A | Architecture workflow → `docs/PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md` (needs R complete) | waiting-on-R | | |
| M | Morning report `docs/OVERNIGHT_REPORT_2026_09_14.md`; update `research/TASKS.md`, `docs/FEATURES.md` status lines, `docs/PLAN_00_INDEX.md` | waiting-on-all | | |

## Log
- 14-09 main session: committed and pushed today's work (4 commits). Plan and runbook written. Loop armed.
