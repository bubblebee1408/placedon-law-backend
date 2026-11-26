# CUAD Research Review

## 1. CUAD — Contract Understanding Atticus Dataset

**Citation:** Hendrycks, D., Burns, C., Chen, A., & Ball, S. (2021). "CUAD: An
Expert-Annotated NLP Dataset for Legal Contract Review." NeurIPS 2021 Datasets
and Benchmarks. [arXiv 2103.06268](https://arxiv.org/abs/2103.06268).

**Research problem:** Automated contract review requires identifying 41 types of
important clauses across diverse commercial agreements. Prior to CUAD, no
large-scale expert-annotated dataset existed for this task.

**Proposed method:** Frame clause identification as extractive QA in SQuAD 2.0
format. For each of 41 clause categories, a question is posed against the
contract text; the answer is the verbatim span, or the question is unanswerable.

**Mathematical formulation:**
- Input: (question q_i, context c) where q_i is one of 41 category questions
- Output: span (start, end) in c, or ∅ (no answer)
- Evaluation: AUPR (area under precision-recall curve) across categories
- Matching: Jaccard similarity ≥ 0.5 on lowercased word sets between predicted
  and gold spans

**Dataset:** 510 commercial contracts, 25 contract types, 13,000+ expert
annotations across 41 categories. SQuAD 2.0 JSON format (`CUADv1.json`).

**Preprocessing:** Sliding window over long contracts. Each contract is split
into overlapping chunks that fit within the model's max sequence length. >99% of
generated features contain no positive labels (extreme class imbalance due to
contracts being mostly boilerplate with sparse clause instances).

**Algorithm:**
1. Tokenize contract into overlapping windows (stride ~128 tokens)
2. For each window × question pair, predict start/end logit distributions
3. Aggregate across windows — take the highest-scoring span per category
4. Apply confidence threshold; below threshold → no answer
5. Negative (no-answer) features downweighted during training

**Evaluation metrics:**
- AUPR: primary metric (handles extreme class imbalance better than F1)
- Precision at 80% recall, precision at 90% recall
- Best model (DeBERTa-xlarge): 47.8 AUPR, 44.0 P@80%R, 17.8 P@90%R

**Limitations:**
- Low absolute performance even from the best model
- 33 of 41 categories have derived yes/no answers — overlap with classification
- LexGLUE excluded CUAD due to annotation quality concerns
- Dataset is US commercial contracts — no Indian law representation
- Some annotation inconsistencies noted by independent audits

**What Placedon adopts:**
- The 41 category taxonomy as the extraction target
- SQuAD-style question-per-category approach (adapted for generative LLM)
- Jaccard ≥ 0.5 as the matching threshold for fuzzy verification
- AUPR as the primary evaluation metric
- The sliding window approach (adapted for character-level windows)

**What must not be copied without modification:**
- The fine-tuned QA head approach (we use generative extraction through router)
- Token-level sliding windows (we use character-level to avoid tokenizer deps)
- The assumption that all 41 categories apply to all contract types
- US-centric category descriptions (must adapt for Indian conventions)

---

## 2. SQuAD 2.0 — Know What You Don't Know

**Citation:** Rajpurkar, P., Jia, R., & Liang, P. (2018). "Know What You Don't
Know: Unanswerable Questions for SQuAD." ACL 2018.
[arXiv 1806.03822](https://arxiv.org/abs/1806.03822).

**Research problem:** Extractive QA systems must distinguish answerable from
unanswerable questions rather than always extracting a span.

**Proposed method:** Extend SQuAD 1.1 with 50,000+ unanswerable questions.
Models must abstain when no answer exists in the passage.

**Mathematical formulation:**
- For each (question, passage), model outputs (start, end, p_has_answer)
- If p_has_answer < threshold → abstain (output ∅)
- No-answer score: s_null = s_start(CLS) + s_end(CLS) in BERT-based systems
- Best span score: s_span = max(s_start(i) + s_end(j)) for valid i ≤ j
- Predict no-answer when s_null - s_span > threshold τ (learned on dev set)

**Relevance to Placedon:**
- Our extractor must return NOT_FOUND when a clause category is absent
- For generative models, we instruct explicit NOT_FOUND response instead of
  threshold on logits
- Verification step (Part 5) catches cases where model extracts from nothing

**Limitations:**
- Designed for passages, not full documents — needs sliding window for contracts
- No notion of partial answers or approximate matches
- Abstention calibration is task-specific

---

## 3. LexDeMod — Agent-Specific Deontic Modality Detection

**Citation:** Sancheti, A., Garimella, A., Srinivasan, B. V., & Rudinger, R.
(2022). "Agent-Specific Deontic Modality Detection in Legal Language." EMNLP
2022, pp. 11563–11579. [arXiv 2211.12752](https://arxiv.org/abs/2211.12752).
GitHub: `abhilashasancheti/LexDeMod`.

**Research problem:** Contracts impose obligations, prohibitions, and permissions
on specific parties (agents). Existing work detects modality at the sentence
level but not which party bears it.

**Proposed method:** Annotate contracts for per-agent deontic modality and
trigger spans. Benchmark with Transformer models on two tasks:
1. Agent-specific multi-label deontic modality classification
2. Agent-specific deontic modality and trigger span detection

**Dataset:** English contracts (leases, employment, rental) annotated with:
- Agent: which contracting party
- Modality: obligation / prohibition / permission
- Trigger: the modal expression ("shall", "must not", "may")

**Preprocessing:** Sentence-level segmentation, agent identification via party
names from preamble, trigger span annotation.

**Evaluation:** Per-agent F1 for modality classification, token-level F1 for
trigger span extraction. Transfer experiments across agreement types.

**Limitations:**
- English-only, US-centric contract language
- Small corpus relative to CUAD
- Trigger span detection requires knowing party names in advance

**What Placedon adopts (Stage 9):**
- The obligation/prohibition/permission taxonomy per party
- Trigger span extraction approach (adapted for generative models)
- Party identification as a prerequisite step

**What must not be copied:**
- Fine-tuned BiLSTM/Transformer classifiers (we route through the existing router)
- Sentence-level classification without span evidence

---

## 4. ContractNLI — Document-Level NLI for Contracts

**Citation:** Koreeda, Y. & Manning, C. D. (2021). "ContractNLI: A Dataset for
Document-Level Natural Language Inference for Contracts." Findings of EMNLP 2021,
pp. 1907–1919. [arXiv 2110.01799](https://arxiv.org/abs/2110.01799).
GitHub: `stanfordnlp/contract-nli`.

**Research problem:** Determine whether a contract entails, contradicts, or does
not mention a given hypothesis, with evidence spans.

**Proposed method:** Frame contract analysis as document-level NLI with three
labels (entailed, contradicted, not-mentioned) and evidence identification.

**Dataset:** 607 contracts. Hypotheses are templated compliance requirements
(e.g., "Confidential information shall be returned or destroyed upon termination").

**Algorithm (Span NLI BERT):**
1. Segment long contract into passages that fit BERT's window
2. For each passage, predict evidence relevance (multi-label over spans)
3. Aggregate evidence across passages
4. Classify hypothesis against aggregated evidence

**Evaluation:** Accuracy on 3-class NLI, F1 on evidence span identification.
Existing models performed poorly — considerable room for improvement.

**Limitations:**
- Hypotheses are English-language compliance templates
- Not directly applicable to Indian statutory obligations
- Evidence identification is coarse-grained

**What Placedon adopts:**
- The concept of evidence-backed verification for extracted clauses
- Three-state output model (verified / contradicted / not-mentioned) adapted to
  our VERIFIED / FUZZY_MATCH / UNVERIFIED states
- Document-level aggregation strategy

---

## 5. LegalBench — Collaborative Legal Reasoning Benchmark

**Citation:** Guha, N. et al. (2023). "LegalBench: A Collaboratively Built
Benchmark for Measuring Legal Reasoning in Large Language Models." NeurIPS 2023
Datasets and Benchmarks. [arXiv 2308.11462](https://arxiv.org/abs/2308.11462).

**Research problem:** Measure legal reasoning capabilities of LLMs across
diverse task types.

**Dataset:** 162 tasks across 6 reasoning types, including CUAD-derived clause
extraction tasks. Each task has input-output pairs.

**Relevance to Placedon:**
- CUAD tasks in LegalBench provide additional evaluation data
- Task typology (IRAC framework) informs prompt design
- Benchmark methodology informs our bake-off design

**What Placedon adopts:**
- Evaluation methodology for LLM-based clause extraction
- Input-output pair format for our benchmark dataset

---

## 6. Chalkidis et al. — Obligation and Prohibition Extraction

**Citation:** Chalkidis, I., Androutsopoulos, I., & Michos, A. (2018).
"Obligation and Prohibition Extraction Using Hierarchical RNNs."
[arXiv 1805.03871](https://arxiv.org/abs/1805.03871).

**Research problem:** Identify sentences that express obligations or prohibitions
in contracts.

**Proposed method:** Hierarchical BiLSTM with attention for sentence-level
classification: obligation / prohibition / permission / none.

**Limitations:** Sentence-level only, no per-party resolution.

**What Placedon adopts:** The obligation/prohibition/permission taxonomy (feeding
into our existing `checker/obligations.py`).

---

## 7. Long-Document QA — Sliding Window Approaches

**Research findings (multiple sources):**

**Sliding window for BERT-class models:**
- Max sequence length ~384-512 tokens, stride ~128 tokens (50% overlap typical)
- Each window produces start/end distributions; aggregate across windows
- Answer spans crossing window boundaries handled by overlap
- 100-token window with 50-token stride reported as effective (SplaXBERT study)

**For generative LLMs (our approach):**
- Mistral Large 4 context: 32K tokens → ~6000 chars per window is conservative
- Stride of 2000 chars (1/3 overlap) ensures clause boundaries are covered
- ConReader insight: include definitions section in every window for long-range
  term resolution
- No start/end logit aggregation needed — model quotes verbatim text
- Deduplication across windows by Jaccard ≥ 0.8 on extracted text

**Engineering recommendation (not from papers):**
Our character-level windowing is simpler than token-level for three reasons:
1. No tokenizer dependency (no HuggingFace transformers install needed)
2. Character offsets map directly to the source document for verification
3. Mistral Large handles variable token-to-char ratios internally

---

## Verified Research Findings

1. CUAD defines 41 clause categories with SQuAD 2.0 extractive QA format
2. Best BERT model achieves only 47.8 AUPR — generative LLMs may match or exceed
3. Jaccard ≥ 0.5 is the established matching threshold for span verification
4. >99% of sliding window features are negative — class imbalance is extreme
5. Sliding window with 50% overlap is the standard approach for long documents
6. ContractNLI provides a 3-class verification framework (entailed/contradicted/not-mentioned)
7. LexDeMod provides per-party obligation/prohibition/permission extraction
8. Trigger span extraction enables obligation-to-party mapping
9. Existing models perform poorly on contract NLI — room for improvement
10. LegalBench includes CUAD-derived tasks for LLM evaluation

## Proposed Engineering Decisions

1. Use generative extraction (Mistral Large via router), not fine-tuned QA head
2. Character-level windows (6000 chars, stride 2000) instead of token-level
3. Include definitions section in every window (ConReader insight)
4. Three verification states: VERIFIED / FUZZY_MATCH / UNVERIFIED
5. NOT_FOUND as explicit instruction rather than threshold-based abstention
6. Jaccard ≥ 0.5 for fuzzy matching, ≥ 0.8 for cross-window dedup
7. Extend 13 regex categories to 41 CUAD categories, keeping regex as Stage 2
8. Per-party obligation extraction as Stage 9 (LexDeMod approach)
9. Indian-specific categories added alongside CUAD 41 (stamp duty, arbitration seat)

## Unresolved Questions

1. What is the right Indian contract evaluation set? No CUAD equivalent exists
2. Should we add India-specific categories beyond CUAD's 41? (stamp duty,
   Companies Act compliance, SEBI reporting, arbitration seat)
3. How does Mistral Large perform on Hindi/regional language contract clauses?
4. What is the right confidence threshold for FUZZY_MATCH vs UNVERIFIED?
5. Should cross-window merging prefer the longest or highest-confidence span?
