# Research appendix C: literature grounding (research agent, 2026-09-30)

## Evidence quality

- **[S]:** search-snippet level. This covers almost everything below.
- **[R]:** the authors' own GitHub repo was fetched.
- **[V]:** nothing reached this level. arxiv, aclanthology, openreview, nature and PMLR were all egress-blocked.

## 1. Judgment prediction

- **Medvedeva & McBride (NLLP 2023):** only about 7% of prediction papers actually forecast. Medvedeva, Wieling & Vols (AI & Law 2023) define three tasks: identification, categorisation and forecasting [S].
- **ILDC** (ACL 2021): the best model scores 77.79 F1; experts average 94%. Model explanations diverge from the experts' [R+S].
- **PredEx** (Findings ACL 2024): RoBERTa 78%, Llama-2-7B 38%, **human experts 73%**. This contradicts ILDC's 94%, so expert ceilings depend on how they were measured [R+S].
- **NyayaAnumana** (COLING 2025): 702,945 cases; about 90% F1 after continual pretraining and SFT [S]. This is not forecasting.
- **IL-TUR** (ACL 2024): Indian NLU benchmark in English, Hindi and 9 other Indian languages [S].
- **Nigam et al.** "Rethinking LJP" and NyayaRAG (2024/25): statutes and precedents help, but models remain below experts [S].
- **Shortcut learning in LJP** (2026 preprint): 200 outcome-revealing trigrams alone reach Macro-F1 56.07. Leakage audits are essential [S].
- **Judge Variable** (JURIX 2025 submission): judge-specific models F1 92.85 vs 82.63 for a generalist [S].
- **Katz et al.** (PLOS ONE 2017): a time-evolving model, 70.2% on outcomes and 71.9% on justice votes [S].

## 2. Probabilistic forecasting with LLMs

- **Halawi et al.** (NeurIPS 2024): Brier 0.179 vs the human crowd's 0.149 on 914 questions. When the system abstains on some questions, 0.238 vs 0.240 on the rest [S].
- **ForecastBench** (ICLR 2025): superforecasters 0.096, public 0.121, best LLM 0.122. An FRI blog claims parity was likely reached by July 2026; that claim is not peer-reviewed [S].
- **Paleka et al.** (ICLR 2026): temporal leakage makes LLM backtests untrustworthy [S].
- **Schoenegger et al.** (Science Advances 2024): a 12-LLM ensemble matched 925 humans on 31 questions [S].
- **Satopää et al.** (IJF 2014) and **Baron et al.** (2014): log-odds pooling with extremizing works best when the extremizing factor is fitted on held-out data [S].
- **Xiong et al.** (ICLR 2024): the confidence LLMs state in words clusters at 80–100% and is overconfident [S].

## 3. Uncertainty and guarantees

- **Mohri & Hashimoto** (ICML 2024): conformal factuality gives 80–90% correctness guarantees [S].
- **Cherian, Gibbs & Candès** (NeurIPS 2024): conditional validity across topics [S].
- **Quach et al.** (ICLR 2024): conformal language modelling [S].
- **Abbasi-Yadkori et al.** (2024): conformal abstention [S].
- **Barber et al.** (Annals of Statistics 2023): conformal prediction beyond exchangeability; weighted quantiles under drift [S].
- **Farquhar et al.** (Nature 2024): semantic entropy AUROC 0.790 vs 0.691. Costs 5–10× compute and misses consistent errors [S].
- **Joren et al.** (ICLR 2025): an autorater judges whether retrieved context is sufficient, with accuracy 0.93. When context is insufficient, models hallucinate 15–40% of the time instead of abstaining [R].
- **Geifman & El-Yaniv** (NeurIPS 2017): selective classification with a risk guarantee [S].

## 4. Neuro-symbolic legal reasoning

- **Catala** (ICFP 2021): formalising French family benefits found a bug in the official implementation [S].
- **Lawsky** (2017): statutes read as default logic [S].
- **Blawx / s(CASP)** (2022): explanations that cite the provision [S].
- **LegalRuleML** (OASIS): a standard for legal rules, including temporal metadata [S].
- **Blair-Stanek et al.** (ICAIL 2023): GPT-3 does poorly on synthetic statutes [S].
- **Jurayj et al.** (AAAI 2026): the LLM turns facts into Prolog, and a solver runs them over gold statute encodings. The figure "86/100 on SARA" is UNVERIFIED [S].
- **"Know Your Limits"** (ICML 2026): LLM formal reasoning is unfaithful ("scope laundering"); Z3 is stricter [S].
- **"Solving versus Verifying"** (2026): models answer straight through injected contradictions 63–76% of the time. Prolog finds statute inconsistencies deterministically [S].

## 5. Causal inference and "what-if"

- **Chyn, Frandsen & Leslie** (JEL 2025): judge-leniency instruments; at least 71 studies [S].
- **Ash et al.** (ReStat): 5M+ Indian criminal cases show a **tight zero** in-group bias on gender and religion [S].
- **Chemin** (JLEO 2012): the 2002 CPC amendment made Indian courts faster, with economic effects [S].
- **Chen, Moskowitz & Shue** (QJE 2016): gambler's-fallacy sequence effects in asylum judges [S].
- **Hewitt et al.** (Nature 2026): LLM-simulated treatment effects correlate r=0.85 with real ones but overstate magnitudes. **Wang et al.** (NMI 2025): simulation flattens identity groups. The two findings conflict [S].
- **AgentCourt** (Findings ACL 2025): not validated against real outcomes. **CounterBench**: LLMs are close to random on formal counterfactuals [S].

## 6. Temporal legal retrieval

- **FiscalQA Pro** (ICML 2026 listing): 32,436 article versions. Static RAG retrieved the date-applicable version **0%** of the time and scored 2.7%. Conditioning on the as-of date reached **98.3%** against a 99.1% oracle [S].
- **"Asking for an Old Friend"** (2026): 312 German QA items; version-filtered retrieval fixes post-cutoff decay [S].
- **SAT-Graph RAG** (JURIX 2025): Work and Expression versions, with the amending event as a node [S].
- **Han et al.** (KDD 2026): RAG vs GraphRAG differences are marginal (64.78 vs 63.01; 60.04 vs 61.66); integrating both gains up to 6.4 [S].
- **Zep/Graphiti** (vendor): a bitemporal knowledge graph [S].

## 7. Labelling

- **CUAD:** 510 contracts, 13,000+ labels, 70–100 h of training, value estimated at over $2M [S].
- **LegalBench:** 162 tasks from 40 contributors [S].
- **Lawma** (ICLR 2025): fine-tuned Llama 3 beats GPT-4 on 95% of 260 legal classification tasks. "A few dozen to a few hundred" labels suffice [S].
- **LLMs as annotators:**
  - **Gilardi** (PNAS 2023): LLMs about 25 pp better than crowd workers [S].
  - **Savelka & Ashley** (2023): zero-shot F1 on statutes and regulations only **0.54** [S].
  - **Schepers** (AI & Law 2025): weak recall on citations [S].
- **Alternative Annotator Test** (ACL 2025): the n needed before replacing humans with LLMs is OPEN [S].
- **Snorkel** (PVLDB 2017) and **CAL** (Cormack & Grossman, SIGIR 2014): weak supervision and continuous active learning for high-recall review [S].
- **Agreement on Indian legal annotation:** κ 0.65 (Income Tax) and 0.87 (Competition) [S].

## 8. Multi-agent systems

- **MAST** (NeurIPS 2025 D&B): 14 failure modes in 3 groups, κ = 0.88 [S].
- **Kim et al.** (Google/MIT, Dec 2025): independent multi-agent systems amplify errors **17.2×**, centralised ones **4.4×**. Sequential tasks degrade [S].
- **Anthropic** (vendor): +90.2% on breadth-first research at about 15× tokens [S].
- **Magesh et al.** (JELS 2025): Lexis+ AI 65% accurate / 17% hallucination; Westlaw 42% / 33% [S].
- **Dahl et al.** (JLA 2024): raw LLMs hallucinate 58–88% [S].
- **Vendor and industry benchmarks:** Vals (industry, opt-in), LegalBench-RAG (character-span scoring) and BigLaw Bench (vendor) [S].
- **Durable execution:** no peer-reviewed comparison; INCONCLUSIVE.

## Contradictions

1. Expert ceiling for Indian judgment prediction: ILDC 94% vs PredEx 73%.
2. LLMs vs superforecasters: a gap (ICLR 2025) vs claimed parity (FRI blog 2026) vs leakage warnings (ICLR 2026).
3. LLM simulation: r=0.85 (Nature 2026) vs group flattening (NMI 2025).
4. Legal AI accuracy: Magesh et al. vs Vals October 2025.
5. Multi-agent: +90.2% (Anthropic) vs 17.2× error amplification (Google/MIT). Parallel breadth-first work gains; sequential chains lose.
6. LLM formalisation raises accuracy but is unfaithful.
7. LLM annotators beat crowd workers but lose to small fine-tuned models, and score only 0.54 F1 on statutes.

## Ten proven techniques a small team can implement for free (ranked)

1. **Retrieval filtered by the as-of date,** over a bitemporal store. Needs about 200–300 temporal QA items for evaluation.
2. **Solver-executed statute encodings,** with the LLM parsing facts only. Needs about 10–30 scenario tests per provision.
3. **A separate verification pass** that checks for contradictions.
4. **A sufficient-context gate** before generation.
5. **Conformal abstention,** recalibrated after each amendment. Needs a calibration set of at least 1/α.
6. **Selective prediction** with risk–coverage curves.
7. **Semantic entropy** as an extra abstention signal.
8. **Small fine-tuned open extractors** (Lawma): a few dozen to a few hundred labels.
9. **LLM pre-labelling,** then the Alternative Annotator Test, then expert adjudication, plus Snorkel and CAL. Report κ per label family.
10. **Forecasting only through time-evolving base-rate or logistic models,** pooled in log-odds and scored with Brier and the Murphy decomposition. Use only pre-decision inputs and test on outcomes that resolve after the cutoff; needs hundreds of resolved outcomes.
    - For NCLT, an FRG hand-collected insolvency dataset exists (https://ifrogs.org/dms/IBC/nclt_data.html). No NLP prediction benchmark on it was found (OPEN).

## Five things not to do

1. Do not train or test prediction on judgment text or random splits.
2. Do not use static retrieval over law that changes with time.
3. Do not show an LLM's stated confidence as a probability.
4. Do not let an LLM imitate a solver.
5. Do not present agent-simulated courts as predictions, or assume a conformal guarantee survives an amendment. Do not use many agents for sequential reasoning, and never claim "hallucination-free".
