# RESEARCH: Themis deep architecture (PLAN_25)

Loop run on 2026-09-30. Four independent agents ran in parallel. Their reports are appendices A–D in this folder.

## Verdict

**BUILDABLE, on the existing code, after two defect fixes.** Three things support this:

- The deeper architecture the founder asked for exists in the literature as proven, free-to-run techniques (appendix C, the ranked list of ten).
- Most of those techniques map onto seams that already exist in the orchestration branch (appendix D, §E).
- The prediction layer can be built with zero cost and zero data dependency. It **was** built in this loop: `checker/forecast/`, 6 modules, all tests passing.

What cannot be built honestly today:

- case-outcome prediction on real matters, which needs labels and lawful NCLT data;
- judge-level analytics, which needs counsel;
- any number rendered as a forecast without a track record.

## Confidence

| Part of the finding | Confidence | Why |
|---|---|---|
| Code seams and defects | **High** | file:line evidence, 14 self-tests run by the auditor, and the two top defects re-checked by the main session |
| Literature | **Medium** | Almost all [S]; research hosts were egress-blocked |
| Free-model limits | **Medium-low** | All [S], and they change monthly |
| Harvey facts | **Medium** | Mostly [S]; one [V] (the claude.com connector page) |

## Evidence

- **Code:** appendix D.
  - F1: `worker.py:146-147` maps anything but REFUSED to ANSWERED.
  - F2: `verbs.py:215-216` reads `s.citation`, but the field is `citations`. **Both re-checked by the main session.**
- **Maths:** `checker/forecast/*` tests, seeded. Measured numbers are in `docs/plans/plan25/03_PREDICTION_ENGINE.md`.
- **Literature:** appendix C, with 60+ sources.
- **Free models:** appendix A.
- **Harvey and the funnel:** appendix B.

## Contradictions found

1. **PLAN_23 §1.11 and PLAN_24 03 say "a date filter runs before the model". It does not** (appendix D F5). This is the most dangerous one, because the literature's strongest single result (FiscalQA Pro: static RAG finds the date-applicable version 0% of the time, versus 98.3% with the date given) says exactly this filter is what matters.
2. **PLAN_23 says the durable executor is resumable and cancellable.** It is unreachable from every surface and not step-level (D F3).
3. **PLAN_24 01/03 is stale against the newest branch.** `ontology.py` and `derivation.py` exist; migrations 001–006; no feed writes to `observation_store` (D F8).
4. **Migration number 006 is taken on two branches** (D F9).
5. **Literature, internally:**
   - The expert ceiling in Indian judgment prediction is 94% (ILDC) vs 73% (PredEx).
   - Multi-agent systems: +90.2% (Anthropic, vendor) vs 17.2× error amplification (Google/MIT).
   - LLM annotators beat crowd workers, but score 0.54 F1 on statutes.
6. **Free models:** several tiers cited in current guides are gone: GitHub Models (retired 2026-07-30), Groq Llama models (gone 2026-08-16), Cerebras' free tier (gone 2026-07-21), and the free Gemini CLI (discontinued).
7. **The founder's scope message ("not just the Companies Act") vs `checker/scope.py`.** One of nine bodies is held. The architecture must make adding a body a pipeline, not a rewrite, and the invariant stays: no obligation for a body not held.

## Three options

| Option | What | Complexity | Cost | Risk | User value |
|---|---|---|---|---|---|
| **A. Extend what exists** | Fix F1/F2/F5 first. Add the forecast plane (Ring 3, done), a body-of-law onboarding pipeline, a labelling funnel with its agent, and cron feeds with God's Eye's reliability patterns. Keep the router, amend D3 for no-train free hosts on public text only | M | ₹0 now; about ₹45k for the first 59 lawyer labels | Low. Every step is testable against existing suites | High, and each step ships alone |
| B. Re-platform on an agent framework plus a graph database | LangGraph orchestration, Neo4j GraphRAG, many agents | L | ₹0 in software, weeks of rewrite | **High.** Sequential legal pipelines amplify errors under multi-agent designs (17.2×); GraphRAG gains are marginal (±2 pts); it discards 229 suites of working guarantees | Low until the rewrite lands |
| C. Train an Indian legal LLM for prediction | INLegalLlama-style continual pretraining and SFT on free GPUs | L | Kaggle hours; label cost | **High.** Leakage: ~7% of LJP papers forecast, and 200 trigrams reach F1 56. Fine-tuning new facts raises hallucination (Gekhman). Weights cannot be dated (PLAN_22 D1) | A number that measures nothing |

## Recommendation

**Option A.**

## Open questions

These need a person or counsel:

- **PLAN_22 D3 amendment:** may a no-training free host (for example Groq) receive **public** text?
- Gemma 3's licence clause on "unlicensed practice of… legal". Counsel.
- BCI Rules 47/49 for part-time advocate reviewers. Counsel.
- DPDP s.3(c)(ii) as applied to MCA filings. Counsel.
- NCLT, SEBI-order and RBI-compounding bulk-access terms, each read and quoted.
- Which body of law is second after CA2013. **Recommendation: SEBI LODR,** already held as text and wired to no rule.
