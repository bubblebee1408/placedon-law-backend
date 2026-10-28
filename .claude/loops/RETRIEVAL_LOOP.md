# Loop: document excerpt retrieval (follow-ups and over-broad matches)

2026-10-28 · pattern `sequential` · mode `safe` · branch `claude/retrieval-loop-20261028`
(worktree `~/PlacedOn/be-retrieval`, from origin/main 5fd28fe). Never merged by the loop.

## Problem (measured 2026-10-28 on the isolated harness, synthetic data)

`gateway/document_evidence.collect()` ranks passages by `overlap / sqrt(len(terms))`, where
overlap is the count of query words in the passage. On an 8-page synthetic contract the
question "What notice period does the termination clause require?" returned **8 of 8
pages** (page 6, the right one, ranked first). The fee question returned 1 of 8 (correct).
Root causes, read from the code:

1. No term weighting: "period" (every filler page) counts the same as "termination" (one page).
2. No cut-off: any passage sharing one word is kept, up to MAX_PASSAGES = 8.
3. No morphology: "terminate" ≠ "termination".
4. No semantic match: "end the agreement" never reaches a Termination clause.
5. Follow-ups without content words ("what about the other party?") have nothing to match;
   the frontend now carries the documents (fe-simfix, uncommitted) but not the topic.

## Roles

| Agent | Writes | Never |
|---|---|---|
| **R — researcher/planner** | `.claude/loops/RESEARCH_retrieval.md`, then `DECISION_retrieval.md` (architecture + algorithm, each choice tied to a cited paper or article) | edits code |
| **T — tester** | `scripts/eval_document_retrieval.py`, `.claude/loops/EVAL_retrieval.md` (baseline + every iteration's numbers) | edits `gateway/` |
| **Orchestrator (main session)** | implements DECISION phases in `gateway/document_evidence.py` with tests, one phase per iteration | merges, pushes to main, changes residency/provider rules |

## Hard constraints (from CLAUDE.md and PLAN_22)

- Excerpts stay **deterministic and model-free** in phase 1 ("excerpts are found without a
  model"). Any model or embedding step is a later, separately approved phase, and only
  through `gateway/models.serve` and the declared providers.
- Exact offsets are sacred: `text[start:end]` is the quote; no passage spans a page break.
- Ranking orders excerpts; it is never a confidence number shown to a reader.
- No new dependency without a stated reason. Stdlib first.
- NO_MATCH must stay honest: "no match does not establish absence".
- Non-circular evaluation: tune on CUAD contracts 0–50 (dev), report the final verdict on
  contracts 51–101 (held-out) **once**, after the algorithm is frozen.

## Metrics (T computes; per query, then averaged)

On CUAD (1,244 answerable clause questions over 102 contracts) and the synthetic follow-up set:
- **Recall@k** (k = 1, 3, 8): a gold answer span overlaps a returned passage.
- **MRR**: reciprocal rank of the first passage that overlaps gold.
- **Precision of what is shown**: share of returned passages that overlap any gold span.
- **Passages shown** (mean): fewer is better at equal recall.
- **Empty rate**: share of answerable queries returning NO_MATCH (must not rise silently).
Queries: CUAD category name plus its "Details:" text, the way a lawyer would ask.

## Iterations

| # | Task | Owner | Depends | Status | Evidence |
|---|---|---|---|---|---|
| L0 | Baseline gate GREEN on this branch | orch | – | done | HARNESS_RESULT suites=341 failed=0 status=GREEN |
| L1 | Literature + code analysis → RESEARCH_retrieval.md | R | – | done | 19 sources opened; RESEARCH_retrieval.md |
| L2 | Eval harness + baseline numbers (dev split) → EVAL_retrieval.md | T | – | done | dev long: MRR 0.306, R@8 0.546, prec 0.109, shown 6.50; reproduced independently by orch |
| L3 | Architecture + algorithm + phased plan → DECISION_retrieval.md | R | L1, L2 | done | BM25 + Porter2 + relative cut/guard + HQE; accepted by orch |
| L4 | Implement phase 1 (deterministic) with unit tests | orch | L3 | done | english_stem.py (9001/9002 CUAD-dev words = NLTK; 'realization' open); BM25+cut+guard+history in document_evidence.py; verbs passes previous user question; tests/test_document_evidence.py 36 OK; gate GREEN 342/0 |
| L5 | Evaluate phase 1 on dev; regressions; adversarial cases | T | L4 | done | sweep in EVAL_retrieval.md 'Phase 1'; strict rule (B 0.4, α 0.5) fails shown 4.89>4.0; semantic-gap-2 FAIL at every setting |
| L6 | Tune or fix from L5 (max 2 rounds), re-evaluate | orch+T | L5 | done | 1 round. Frozen K1 1.2, B 0.4, ALPHA 0.6, W_HISTORY 0.5, stemming on; guard removed (no measurable effect). Dev long: MRR 0.440, prec 0.254, R@8 0.587, shown 3.94 (all §9 CUAD thresholds pass); verified by orch |
| L7 | Freeze; held-out evaluation once; gate; harness browser check | T+orch | L6 | done | held-out (run once): MRR 0.334→0.459, prec 0.108→0.268, R@8 0.576→0.598, shown 6.38→3.88; browser: 8-page contract termination 8/8→1/8 pages, follow-up → page 6 with visible disclosure |
| L8 | Report + PR draft (not merged) | orch | L7 | done | .claude/loops/PR_retrieval.md; not committed or pushed (owner instruction) |

## Stop conditions

Stop and report when any holds:
- L8 done; or
- phase 1 cannot beat baseline on dev MRR **and** precision without lowering Recall@8 by
  more than 2 points after 2 tuning rounds (report the negative result, do not ship); or
- any step would need a model call, a new dependency or a residency change (stop, ask); or
- the gate goes RED and one fix attempt does not restore it; or
- 10 loop iterations have run.

## Log
- 2026-10-28: loop started. Runbook written.
- 2026-10-28 tick 1: L0 gate, L1 agent R and L2 agent T started in parallel.
- 2026-10-28: L2 baseline recorded (T): scripts/eval_document_retrieval.py + EVAL_retrieval.md. CUAD dev (0–50, 612 q) long query MRR 0.306 / R@8 0.546 / prec 0.109 / shown 6.50; short query MRR 0.282 / R@8 0.492; 6.2% of dev questions unsearched (2 contracts > 200k chars). Held-out not run.
- tick 2: L2 verified by orch (identical numbers on re-run). Findings forwarded to R for L3.
- tick 3: L0 GREEN (341 suites, 0 failed). Waiting on R for L1/L3.
- 2026-10-28: R — L1 and L3 drafts written: .claude/loops/RESEARCH_retrieval.md (19 sources, opened) and .claude/loops/DECISION_retrieval.md (phase 1 = BM25 + Porter2 + relative cut-off/common-term guard + HQE follow-ups; 1b metadata switch; acronyms and size limit scoped out).
- tick 4: L1/L3 accepted. intake.classify routes elliptical follow-ups with files to RESEARCH_QUESTION (checked). L4 started.
- tick 5: L4 done. Orch quick dev check (long): MRR 0.306→0.428, R@8 0.546→0.596, prec 0.109→0.202, shown 6.50→4.87 (target ≤4.0 not met), wall 15.85 s. L5 handed to T.
- 2026-10-29: L5 phase-1 eval recorded (T) in EVAL_retrieval.md. Dev long MRR 0.306→0.440, prec 0.109→0.254, R@8 0.546→0.587, shown 6.50→3.94 at recommended K1 1.2 / B 0.4 / ALPHA 0.6 (needs orchestrator OK: strict §9 rule gives ALPHA 0.5, which fails shown ≤ 4.0 at 4.89). semantic-gap-2 FAIL [6,8]; guard inert on CUAD and synthetic; wall 15.75 s vs 16.4 s ceiling. Held-out not run.
- tick 6: L6 decision (orch): ALPHA 0.6, not the strict-rule 0.5. α 0.6 is 0.009 dev MRR below 0.5 (inside the >0.01 noise band), wins both §9 tie-breaks (precision, fewer shown) and is the only setting passing every CUAD threshold; cost R@8 0.623→0.587. A judgment, recorded as one. semantic-gap-2 stays FAIL: a filler page that really contains "end" is lexically indistinguishable; phase-2 motivation, not fixed here. Guard deleted.
- tick 6: L7 held-out run ONCE on frozen code; both baseline and phase 1 on the same split. Frontend fe-simfix now shows history_query visibly (was only in collapsed limitations).
- tick 7: L7 gate GREEN 342/0 on frozen code. L8 PR draft written. Loop STOPPED (stop condition: L8 done).
