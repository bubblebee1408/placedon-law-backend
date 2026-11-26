# Research Register — Document Processing Pipeline

Citations, models, and repos backing the document pipeline implementation.
Every model call goes through `checker/router.py` → Azure AI Foundry (PLAN_22 D3).
Code owns the pipeline; models propose; reviewers decide (PLAN_23).

## Document Classification

- **LEGAL-BERT** — Chalkidis, Fergadiotis, Malakasiotis, Aletras, Androutsopoulos (2020).
  "LEGAL-BERT: The Muppets straight out of Law School."
  Findings of EMNLP, pp. 2898–2904. [arXiv 2010.02559](https://arxiv.org/abs/2010.02559).
  HuggingFace: `nlpaueb/legal-bert-base-uncased` (110M params, CC BY-SA 4.0).

- **InLegalBERT** — Paul, Mandal, Goyal, Ghosh (2023).
  "Pre-trained Language Models for the Legal Domain: A Case Study on Indian Law."
  ICAIL 2023. [arXiv 2209.06049](https://arxiv.org/abs/2209.06049).
  HuggingFace: `law-ai/InLegalBERT` (MIT). Indian SC+HC corpus, outperforms LegalBERT
  on all three Indian legal tasks.

## Clause Extraction (CUAD)

- **CUAD** — Hendrycks, Burns, Chen, Ball (2021).
  "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review."
  NeurIPS 2021. [arXiv 2103.06268](https://arxiv.org/abs/2103.06268).
  510 contracts, 13,000+ annotations, 41 clause categories.
  HuggingFace dataset: `theatticusproject/cuad`. Model: `Rakib/roberta-base-on-cuad`.
  GitHub: `TheAtticusProject/cuad`.

## Obligation Extraction

- **Deontic modality** — Chalkidis, Androutsopoulos, Michos (2018).
  "Obligation and Prohibition Extraction Using Hierarchical RNNs."
  [arXiv 1805.03871](https://arxiv.org/abs/1805.03871).
  Hierarchical BiLSTM + attention for obligation/prohibition/permission classification.

- **LexDeMod** — Sancheti et al. (2022).
  "Agent-Specific Deontic Modality Detection in Legal Language."
  EMNLP 2022. GitHub: `adobe-research/LexDeMod`.
  Per-party obligation/prohibition/permission with trigger span extraction.

- **Contract classification survey** (2025).
  "A Survey of Classification Tasks and Approaches for Legal Contracts."
  [arXiv 2507.21108](https://arxiv.org/abs/2507.21108).
  7 contract tasks. Legal-RoBERTa-Large ROUGE F1 0.95 on NDA clause classification.

## Obligation Verification

- **ContractNLI** — Koreeda, Manning (2021).
  "ContractNLI: A Dataset for Document-Level Natural Language Inference for Contracts."
  EMNLP Findings. [arXiv 2110.01799](https://arxiv.org/abs/2110.01799).
  607 contracts. Entailed / contradicted / not-mentioned against hypotheses.

## Legal NER

- **OpenNyAI** — IIT Kharagpur + EkStep.
  HuggingFace: `opennyaiorg/en_legal_ner_trf` (spaCy transformer, F1 91.08).
  Labels: PETITIONER, RESPONDENT, JUDGE, COURT, STATUTE, PROVISION, PRECEDENT, DATE.
  GitHub: `OpenNyAI/Opennyai`, `Legal-NLP-EkStep/legal_NER`. MIT license.

- **Contract NER** — `agilelab-org/Contractner` (GLiNER-based, 18 entity types, 72.49%).

## Extractive Summarization

- **TextRank** — Mihalcea, Tarau (2004).
  "TextRank: Bringing Order into Texts." EMNLP, pp. 404–411.
  Graph-based unsupervised sentence ranking. No model needed.
  Implemented in `checker/textrank.py`.

- **Multi-LexSum** — Shen et al. (2022).
  "Multi-LexSum: Real-World Summaries of Civil Rights Lawsuits at Multiple Granularities."
  NeurIPS Datasets & Benchmarks. [arXiv 2206.10883](https://arxiv.org/abs/2206.10883).
  HuggingFace: `allenai/multi_lexsum`.

## Near-Duplicate Detection

- **MinHash** — Broder (1997).
  "On the Resemblance and Containment of Documents."
  Compression and Complexity of Sequences, IEEE, pp. 21–29.
  Implemented in `checker/dedup.py`.

- **datasketch** — `ekzhu/datasketch` (MIT). Canonical Python MinHash/LSH library.
- **text-dedup** — `ChenghaoMou/text-dedup`. Built on datasketch.

## LangChain Reference Architectures

- `Naresh1401/legal-contract-analyzer` — clause extraction + risk + compliance pipeline.
- `tomasonjo-labs/legal-tech-chat` — CUAD extraction → Neo4j graph → LangGraph agent.
- `crisar0790/legalmove-contract-analyzer` — LangChain agents + Pydantic output.

Adapted to our architecture: LangChain orchestrates, Azure AI Foundry serves models,
deterministic code validates every model output before anything downstream sees it.

## Model Provider Stack (user-specified, 2026-11-26)

| Provider | Role | Models |
|----------|------|--------|
| Mistral AI | Core LLM, reasoning, OCR | Large 4 (extraction), Small 4 (classification), OCR 4.1 (scans) |
| Google Gemini | General document intelligence | Flash (OCR incumbent), Flash-Lite (classification fallback) |
| Sarvam AI | Indian-language AI and speech | Document AI (candidate, awaiting bake-off) |

All Mistral models deployed on Azure AI Foundry (`checker/mistral_model.py`).
Wired as CANDIDATES in `checker/router.py` — promoted to preferred after bake-off
per PLAN_22 D2.
