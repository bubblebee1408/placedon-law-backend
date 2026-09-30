# 01: What the research proves, and the rule each finding forces on the architecture

**Evidence quality:** 60+ sources, gathered by an independent research agent on 2026-09-30.
Full citations are in `.claude/loops/RESEARCH_THEMIS_DEEP_ARCH_C_LITERATURE.md`.

- Nearly every source is **[S]**, read in search results only. arxiv, ACL Anthology, Nature
  and OpenReview were blocked from this environment.
- Before any number here reaches an investor deck or a paper, a person reads the source.

## The findings that shape the design, strongest first

| # | Finding | Source | Rule it forces |
|---|---|---|---|
| 1 | Retrieval that ignores dates found the right version of a law **0%** of the time and scored 2.7%. Giving it the as-of date: **98.3%** (oracle 99.1%) | FiscalQA Pro (ICML 2026 listing); German statutory QA (2026) | **Filter by date before the model** (file 02 §3, fix F5). The orchestration code does not do this today, although two plans say it does |
| 2 | Only **~7%** of judgment-prediction papers forecast anything; the rest read the answer from the judgment. 200 outcome words alone reach F1 56 | Medvedeva & McBride (NLLP 2023); shortcut-learning study (2026) | Forecasts use only pre-decision inputs, split by date (file 03) |
| 3 | Chains of independent agents amplify errors **17.2×** on sequential tasks (centralised: 4.4×); parallel breadth-first research gains | Kim et al. (Google/MIT 2025); Anthropic (vendor) | One orchestrator, code-owned plans; fan-out only for independent documents (PLAN_23 kept) |
| 4 | Models answer straight through injected contradictions 63–76% of the time. LLM "formal reasoning" is unfaithful; a solver is not | "Solving vs Verifying" (2026); "Know Your Limits" (ICML 2026) | Encode the statute by hand; the model parses facts; a separate verify pass (file 02 §2) |
| 5 | With insufficient context, frontier models hallucinate **15–40%** instead of abstaining. A context-sufficiency rater reaches 0.93 accuracy | Joren et al. (ICLR 2025) | A sufficient-context gate that can only withhold (file 02 §3) |
| 6 | Conformal methods give a **coverage guarantee for any model**. Amendments break the assumption; adaptive conformal restores long-run coverage | Mohri & Hashimoto (ICML 2024); Barber et al. (Ann. Stat. 2023); Gibbs & Candès (NeurIPS 2021) | Forecast as a set, abstain on {0,1}, use ACI. **Built and measured** (file 03 §2.3) |
| 7 | An LLM's stated confidence clusters at 80–100% and is overconfident. Models cannot predict their own legal hallucinations | Xiong et al. (ICLR 2024); Dahl et al. (JLA 2024) | Never show a model's own confidence as a probability |
| 8 | Commercial legal AI hallucinated 17–33% (Lexis+ AI 17%, Westlaw 33%) | Magesh et al. (JELS 2025) | Every clause quoted byte-identically (built) |
| 9 | Retrieval beats fine-tuning for new knowledge; fine-tuning on new facts **raises** hallucination; trained models leak their training text | Ovadia et al., Gekhman et al. (EMNLP 2024); Carlini et al. (USENIX 2021) | Adapt to each company through memory and retrieval, not weights (PLAN_24 05, unchanged) |
| 10 | Small open models fine-tuned on "a few dozen to a few hundred" labels beat GPT-4 on 95% of 260 legal classification tasks | Lawma (ICLR 2025) | After funding, the right model upgrade for extraction is small and ours, not bigger and rented |
| 11 | LLM annotators score F1 **0.54** on statutes; lawyer–student agreement ~80% (MAUD); Indian κ 0.59–0.87 | Savelka & Ashley (2023); MAUD; Kalamkar; Malik | Lawyers label; the agent only proposes and sorts (file 05) |
| 12 | Judge identity carries signal (F1 92.85 vs 82.63). **But** 5M Indian criminal cases show a tight zero in-group bias | Judge Variable (JURIX 2025 submission); Ash et al. (ReStat) | Judge analytics stays off pending counsel; US "judge bias" stories are not imported |
| 13 | Credible causal claims from court data come from judge-assignment and reform natural experiments, not from LLM simulation. LLM counterfactuals are near random | Chyn, Frandsen & Leslie (JEL 2025); CounterBench (2025) | The "what-if" is the law applied to changed facts (`propagate`), never a simulated court |
| 14 | GraphRAG vs RAG differences are marginal (±2 pts); combining them gains up to 6.4 | Han et al. (KDD 2026) | No graph-database re-platform. The provision graph plus the bitemporal store is enough |
| 15 | LLM forecasters approach the crowd only with retrieval, several samples and abstention; backtests leak | Halawi et al. (NeurIPS 2024); Paleka et al. (ICLR 2026) | Forecast selectively; score only on outcomes that resolve after the cutoff |

## Contradictions the design has to live with

- **Expert ceiling in Indian judgment prediction:** 94% (ILDC) vs 73% (PredEx). Never claim
  "expert-level" without a matched protocol.
- **LLM forecasters vs superforecasters:** a gap (ICLR 2025), claimed parity (FRI blog 2026),
  and leakage warnings (ICLR 2026). Treat parity as unproven.
- **Legal-AI accuracy:** Magesh (peer-reviewed) vs Vals October 2025 (industry, opt-in). The
  tasks differ.

## What the research says NOT to build

1. A judgment predictor trained on judgment text.
2. Retrieval that ignores dates over law that changes.
3. A confidence percentage produced by the model.
4. An LLM acting as the reasoning engine for statute logic.
5. A simulated court presented as a prediction.
