# PLAN 24 — Architecture Compatibility Matrix and Model Evaluation Design

**Written 2026-11-22. Status: DESIGN — nothing is adopted until a bake-off wins.**

This plan answers two questions:

1. Where do the directive's candidate technologies (InLegalBERT, BGE-M3, BGE reranker,
   DeBERTa, Qwen3-14B, LangChain, LangGraph, Qdrant) fit — or not fit — into the
   architecture that already exists?
2. How do we evaluate each candidate against the incumbent, using the eval harness that
   already exists, so the decision is a measurement and not a preference?

PLAN_22 D2 is the governing rule: **a model is promoted only by bake-off — a
non-overlapping 95% confidence interval against the incumbent, plus a person editing the
table.** Nothing in this document bypasses that.

---

## 1. The Architecture As Built

### 1.1 Model Layer

| Slot | Incumbent | Module | Evidence |
|------|-----------|--------|----------|
| Generation HIGH | Claude Opus 5 (Bedrock ap-south-1) | `checker/bedrock_model.py` | PLAN_22 D3: client docs India-only |
| Generation LOW | Claude Haiku 4.5 (Bedrock) | `checker/bedrock_model.py` | Measured Rs 0.97/call |
| Generation fallback | Azure Llama 3.3 70B / gpt-5-mini | `checker/azure_model.py` | 18/18 cases, 0 errors |
| Narration | Claude Sonnet 5 → Gemini Flash | `checker/router.py` | Cannot introduce a fact |
| OCR | Gemini Flash (86.3% chrF++) | `checker/gemini_model.py` | PLAN_22 D5; Sarvam candidate |
| Local fallback | Ollama (8B max) | `checker/ollama_runner.py` | 8.6 GB GPU; 12B OOM |
| Public-only backup | Gemini free tier (20 RPD) | `checker/gemini_model.py` | Never sees client docs |

### 1.2 Retrieval Layer

| Slot | Incumbent | Module | Metric | Evidence |
|------|-----------|--------|--------|----------|
| Cross-section (which section?) | RRF fusion (BM25 + MiniLM dense) | `checker/fusion.py`, `checker/dense_index.py` | p@1 0.80, recall@5 0.97 | 70-case frozen eval |
| Within-section (which chunk?) | BM25 over structural chunks | `checker/chunk_retrieval.py` | p@1 0.62 | `checker/retrieval_eval.py` |
| Reranker | 7-feature linear perceptron | `checker/reranker.py` | Transparent, explainable | Cross-validated on 70 queries |
| Dense embeddings | all-MiniLM-L6-v2 (local, offline) | `checker/dense_index.py` | p@1 0.73 (solo) | Loses to fusion but contributes |
| Voyage (candidate) | voyage-law-2 | `checker/voyage_model.py` | NOT YET MEASURED | Enters only on bake-off win |

### 1.3 Verification Layer

| Component | Module | Role |
|-----------|--------|------|
| Model cascade | `checker/model_cascade.py` | deterministic → small → large, escalate on verifier rejection only |
| Model adapter | `checker/model_adapter.py` | Single entry point; 4 pre-call refusals; output parsed to rigid structure |
| Quoted span | `checker/quoted_span.py` | Every sentence traced to verbatim span or dropped |
| Entailment gate | `checker/entailment_gate.py` | Precision 0.83 |
| Prompt safety | `checker/prompt_safety.py` | UNTRUSTED_CLAUSE on all untrusted text |

### 1.4 Orchestration Layer

| Component | Module | Design |
|-----------|--------|--------|
| Router | `checker/router.py` | Deterministic function of (modality, consequence, volume, availability) |
| Verb table | `gateway/verbs/registry.py` | 71 verbs → REST + MCP + CLI, parity-tested |
| Audit trail | `gateway/audit.py` | Hash-chained, append-only |
| Budget | `backend/budget.py` | Per-tenant, reserve-before-spend |

---

## 2. Compatibility Matrix

Each candidate from the directive is evaluated against the architecture's constraints.

### 2.1 Embedding Models

| Candidate | What It Does | Replaces | Fits? | Constraint Notes |
|-----------|-------------|----------|-------|------------------|
| **InLegalBERT** (law-ai/InLegalBERT) | 110M-param BERT, pre-trained on Indian legal corpus (Supreme Court, High Courts) | `all-MiniLM-L6-v2` in `dense_index.py` | **YES — as bake-off candidate** | 768-dim (vs MiniLM 384). ~440 MB. Runs offline. Indian legal vocabulary is the draw. Must beat fusion p@1 0.80. |
| **BGE-M3** (BAAI/bge-m3) | 568M-param, multilingual, multi-granularity (dense + sparse + ColBERT in one model) | `dense_index.py` + potentially `lexical_rank.py` | **YES — as bake-off candidate** | ~2.3 GB. Built-in sparse retrieval could replace BM25. Hindi/multilingual capability matters for Indian legal docs. Must beat fusion p@1 0.80. Heavier: 5x MiniLM memory. |
| **Voyage law-2** (already wired) | Legal-domain embedding, 1024-dim | `dense_index.py` | **YES — already a candidate** | API-based (not offline). Processing location unconfirmed for client data. `checker/voyage_model.py` exists. |

**Evaluation design:** See §3.1.

### 2.2 Rerankers

| Candidate | What It Does | Replaces | Fits? | Constraint Notes |
|-----------|-------------|----------|-------|------------------|
| **BGE reranker** (BAAI/bge-reranker-v2-m3) | Cross-encoder reranker, multilingual | `checker/reranker.py` (linear perceptron) | **CONDITIONAL** | The linear reranker is explainable by design (PLAN_23 §1; "unexplainable component in retrieval path is a contradiction"). A cross-encoder is a black box. Acceptable only if: (a) it beats the perceptron on the eval by a non-overlapping CI, AND (b) the `explain()` contract is preserved by wrapping the cross-encoder score as one additional feature in the linear model — not by replacing it. |
| **Voyage rerank-2.5** (already wired) | API reranker | Same | **CONDITIONAL** | Same explainability constraint. API-based; processing location unconfirmed. |

**Evaluation design:** See §3.2.

### 2.3 Classification / NLI Models

| Candidate | What It Does | Replaces | Fits? | Constraint Notes |
|-----------|-------------|----------|-------|------------------|
| **DeBERTa** (microsoft/deberta-v3-large or -base) | NLI / entailment classification | `checker/entailment_gate.py` (precision 0.83) | **YES — as bake-off candidate** | 304M (base) or 434M (large). The entailment gate is a measured component; DeBERTa-MNLI is a natural candidate to improve it. Must beat 0.83 precision without degrading recall. Runs locally. |

**Evaluation design:** See §3.3.

### 2.4 Generation Models

| Candidate | What It Does | Replaces | Fits? | Constraint Notes |
|-----------|-------------|----------|-------|------------------|
| **Qwen3-14B** | 14B-param generation model | Azure Llama 3.3 70B (fallback) or Ollama local | **NO for local** (12B OOM'd; 14B worse). **YES via Azure AI Foundry** if available there. | PLAN_22 D3: never call vendor APIs directly. Must go through Azure. 14B exceeds local GPU (8.6 GB measured). As an Azure deployment: viable fallback candidate, evaluated on the 18-case existing eval. |

**Evaluation design:** See §3.4.

### 2.5 Frameworks

| Candidate | What It Does | Replaces | Fits? | Constraint Notes |
|-----------|-------------|----------|-------|------------------|
| **LangChain** | LLM application framework | `checker/router.py`, `checker/model_adapter.py`, `checker/model_cascade.py` | **NO — the architecture already solves what LangChain solves, with stronger invariants.** | The router is a deterministic function (PLAN_23 rule). The cascade escalates on external verifier rejection only (Huang ICLR 2024). The adapter enforces 4 pre-call refusals. LangChain's abstractions (chains, agents, callbacks) would **loosen** these invariants — a LangChain agent decides what runs next, violating "code owns the plans and the hand-offs." LangChain adds ~50 transitive dependencies against the no-new-dependency rule. No measured deficiency in the current layer that LangChain addresses. |
| **LangGraph** | Stateful multi-agent orchestration | `checker/model_cascade.py`, `gateway/worker.py` | **NO — same objection, plus the cascade is structurally incapable of self-escalation by design.** | LangGraph's value is dynamic graph execution (cycles, conditional edges). PLAN_23 §1.2: "a workflow for every task whose shape is known — which is nearly all of them here." The cascade's stages are `Callable[[str], str]` with no confidence field — structurally cannot self-escalate (PLAN_23 §1.4). LangGraph would re-introduce the model-decides-what-runs-next pattern the architecture explicitly prohibits. |
| **Qdrant** | Vector database | `checker/dense_index.py` (pickle file) | **DEFERRED — not until volume demands it.** | The dense index is a pickle of numpy arrays over 527 sections. At this scale (527 vectors × 384 dims = ~800 KB), a vector database is infrastructure for a problem that fits in memory. Qdrant becomes relevant when: (a) the corpus grows past ~50K chunks, OR (b) multi-tenant vector isolation is needed in production. Neither is true today. When it is, Qdrant is a reasonable choice — but so is pgvector on the existing Azure PostgreSQL (D8), which adds zero new infrastructure. |

### 2.6 Summary

| Technology | Verdict | Action |
|------------|---------|--------|
| InLegalBERT | **EVALUATE** | Bake-off against MiniLM on cross-section and within-section retrieval |
| BGE-M3 | **EVALUATE** | Bake-off against fusion (BM25 + MiniLM) on both surfaces |
| BGE reranker | **EVALUATE with constraint** | As additional feature in linear model, not as replacement |
| DeBERTa | **EVALUATE** | Bake-off against entailment gate (precision 0.83) |
| Qwen3-14B | **EVALUATE if on Azure** | Bake-off against Llama 3.3 70B on existing 18-case eval |
| Voyage law-2 | **ALREADY WIRED** | Awaiting bake-off (processing location unconfirmed for client data) |
| LangChain | **REJECT** | Architecture already provides what it offers, with stronger invariants |
| LangGraph | **REJECT** | Contradicts "code owns the plans" and structurally-enforced cascade |
| Qdrant | **DEFER** | Not until corpus > 50K chunks or multi-tenant vectors needed |

---

## 3. Model Evaluation Design

Each evaluation follows the same protocol (PLAN_22 D2):

1. **Frozen eval set.** The candidate is measured on the SAME eval set as the incumbent.
   No new eval cases are added for the candidate — that changes the denominator.
2. **Bootstrap CI.** `checker/retrieval_metrics.py` already provides `bootstrap_ci`
   (10,000 resamples, seed 20261002). The candidate wins only if its 95% CI does not
   overlap the incumbent's.
3. **Person edits the table.** An automated script may REPORT; it may not ADOPT.
4. **One thing at a time.** Each candidate is evaluated independently. No compound
   changes (e.g., "BGE-M3 + BGE reranker together").

### 3.1 Embedding Bake-off: InLegalBERT / BGE-M3 vs Incumbent

**Incumbent:** RRF fusion (BM25 + all-MiniLM-L6-v2), p@1 0.80, recall@5 0.97.

**Eval set:** The frozen 70-case cross-section eval (`checker/cross_section_eval.py`).

**Protocol:**

```
For each candidate model M in [InLegalBERT, BGE-M3]:
  1. Build dense index with M (same corpus, same chunking)
  2. Run cross-section eval: p@1, recall@5, MRR, nDCG@5
  3. Run RRF fusion (BM25 + M) — same fusion parameters
  4. Bootstrap CI on p@1 for fusion(BM25 + M) vs fusion(BM25 + MiniLM)
  5. If CI non-overlapping AND p@1 improves: CANDIDATE WINS, report to human
  6. Also run within-section eval (chunk_retrieval surface, p@1 incumbent 0.62)
```

**Implementation:** New module `eval/embedding_bakeoff.py` that:
- Takes a model name, loads it via `sentence_transformers`
- Builds the dense cache (same as `dense_index.py` but parameterised on model)
- Runs `cross_section_eval` with the new index
- Reports: incumbent CI, candidate CI, overlap (yes/no), verdict

**Dependencies:** `sentence_transformers` (already installed locally, not in requirements).
`torch` (same). InLegalBERT and BGE-M3 are HuggingFace models loadable by
`SentenceTransformer(model_name)`. No new pip dependency.

**BGE-M3 sparse mode:** BGE-M3 produces sparse vectors natively. If dense BGE-M3 wins,
a follow-up eval tests BGE-M3 sparse vs BM25 to determine whether BM25 can be replaced
entirely. This is a SECOND bake-off, not part of the first.

### 3.2 Reranker Bake-off: BGE Reranker as Feature

**Incumbent:** Linear perceptron over 7 features, cross-validated on 70 queries.

**Constraint:** The reranker must remain explainable (`explain()` decomposes every
ranking decision into per-feature contributions). A cross-encoder score is one number;
it enters as an **8th feature** in the linear model, not as a replacement.

**Protocol:**

```
1. For each (query, candidates) in the 70-case eval:
   a. Score all candidates with BGE reranker cross-encoder
   b. Add cross-encoder score as feature 8 in the linear model
   c. Retrain linear model (8 features) with cross-validation
2. Compare 8-feature model p@1 CI vs 7-feature model p@1 CI
3. If non-overlapping and improved: the cross-encoder feature earns its place
4. Report the weight the linear model assigns to feature 8:
   if it dominates (>0.7 of total weight), the other features are dead weight
   and the explainability contract is hollow — flag this as a design concern
```

**Implementation:** Extend `checker/reranker.py` with an optional 8th feature slot.
The cross-encoder is loaded lazily; if unavailable, the 7-feature model runs unchanged.

### 3.3 Entailment Bake-off: DeBERTa vs Incumbent Gate

**Incumbent:** Entailment gate, precision 0.83.

**Eval set:** The entailment gate's own eval cases (in `checker/entailment_gate.py`).

**Protocol:**

```
1. Load DeBERTa-v3-base (or -large) with HuggingFace transformers
2. For each (premise, hypothesis, expected) in the entailment eval:
   a. Run DeBERTa NLI: entailment / neutral / contradiction
   b. Map to gate's vocabulary: entailment → SUPPORTED, contradiction → CONTRADICTED,
      neutral → INSUFFICIENT
3. Measure precision on SUPPORTED decisions (the gate's metric)
4. Bootstrap CI: DeBERTa precision vs incumbent 0.83
5. Also measure: recall (does DeBERTa find supported claims the gate misses?)
6. Measure latency: DeBERTa inference time vs current gate
```

**Dependencies:** `transformers` (not in requirements). `torch` (already installed
locally). DeBERTa-v3-base is ~350 MB. Runs locally, no API.

**Concern:** DeBERTa-MNLI is trained on English NLI. Indian legal language has specific
constructions ("notwithstanding anything contained in", "subject to the provisions of")
that may not be in MNLI's distribution. The eval will show whether this matters.

### 3.4 Generation Bake-off: Qwen3-14B (if on Azure)

**Incumbent:** Azure Llama 3.3 70B, 18/18 cases 0 errors.

**Prerequisite:** Qwen3-14B must be available as an Azure AI Foundry deployment. If not,
this evaluation is BLOCKED. Do not call Qwen vendor APIs directly (PLAN_22 D3).

**Protocol:**

```
1. Deploy Qwen3-14B on Azure AI Foundry (same region as Llama deployment)
2. Run the existing 18-case eval (eval/realrun/) against Qwen
3. Score: errors, refusals, claim accuracy, latency, cost per call
4. Bootstrap CI on accuracy: Qwen vs Llama 3.3 70B
5. If Qwen wins on accuracy AND costs less: candidate for the LOW-consequence slot
6. If Qwen wins on accuracy but costs more: not a clear win, report and defer
```

**Local evaluation is impossible:** 14B exceeds local GPU (8.6 GB; 12B OOM'd on
2026-09-14). This is an Azure-only evaluation.

---

## 4. Execution Order

| Step | What | Depends On | Estimated Effort |
|------|------|------------|-----------------|
| E1 | Embedding bake-off (InLegalBERT) | HF model download (~440 MB) | 1 day: build index, run eval, report |
| E2 | Embedding bake-off (BGE-M3) | HF model download (~2.3 GB) | 1 day: same protocol |
| E3 | Reranker feature eval (BGE reranker) | HF model download (~1.1 GB) | 1 day: extend reranker, retrain, report |
| E4 | Entailment bake-off (DeBERTa) | HF model download (~350 MB) | 1 day: adapter, run eval, report |
| E5 | Generation bake-off (Qwen3-14B) | Azure deployment (may be BLOCKED) | 1 day if available |

**E1 and E2 are independent and can run in parallel.**
**E3 depends on E1/E2 only if the winning embedding changes the reranker's input.**
**E4 is fully independent.**
**E5 is blocked on Azure availability.**

---

## 5. What This Plan Does NOT Do

- **Does not adopt anything.** Every evaluation produces a report. A person decides.
- **Does not add LangChain, LangGraph, or Qdrant.** Reasons in §2.5.
- **Does not modify the cascade, router, or adapter.** Those are verified designs
  (PLAN_22, PLAN_23). A candidate enters through the existing `dense_index.py` or
  `reranker.py` extension points, not by replacing infrastructure.
- **Does not fine-tune any model.** PLAN_22 D1: no training until 1,000+ lawyer-reviewed
  traces exist AND a hosted model repeatedly fails one specific workflow.
- **Does not change the retrieval default.** BM25 stays the incumbent for statutes
  (PLAN_22 D4). A candidate that beats fusion becomes the new fusion partner, not a
  replacement for BM25.

---

## 6. Decision Log

| Date | Decision | Basis |
|------|----------|-------|
| 2026-11-22 | LangChain REJECTED | Architecture provides what it offers with stronger invariants (§2.5) |
| 2026-11-22 | LangGraph REJECTED | Contradicts PLAN_23 "code owns plans and hand-offs" (§2.5) |
| 2026-11-22 | Qdrant DEFERRED | 527-vector index fits in memory; revisit at 50K+ chunks (§2.5) |
| 2026-11-22 | InLegalBERT, BGE-M3, BGE reranker, DeBERTa → EVALUATE | Bake-off protocol defined (§3) |
| 2026-11-22 | Qwen3-14B → EVALUATE if on Azure | Local impossible (14B > 8.6 GB GPU); PLAN_22 D3 (§3.4) |
| 2026-11-22 | InLegalBERT **MEASURED: LOSES** | Dense p@1=0.10, fusion p@1=0.41 vs incumbent 0.80. CIs non-overlapping — incumbent wins decisively. Pre-training-only BERT without contrastive sentence training produces poor retrieval embeddings. Indian legal vocabulary does not compensate for missing sentence-level training. |
| 2026-11-22 | BGE-M3 **MEASURED: NO WIN** | Dense p@1=0.771 (nearly matches incumbent fusion), but fusion p@1=0.743 — fusion *hurts* BGE-M3. CI [0.643, 0.843] overlaps incumbent CI [0.700, 0.886]. Per PLAN_22 D2, overlapping CIs = no promotion. BGE-M3's rankings disagree with BM25 enough that RRF averages them down. MiniLM and BM25 are more complementary. |
| 2026-11-22 | E3: BGE reranker as 8th feature **MEASURED: NO WIN** | 7-feature and 8-feature rerankers produce IDENTICAL held-out p@1=0.829 (CI [0.743, 0.914]). Cross-encoder score (BAAI/bge-reranker-base, 1138 pairs scored) adds zero signal beyond existing RRF rank features. Both beat RRF fusion (0.80) but the 8th feature is redundant. The existing 7 hand-named features already capture what the cross-encoder knows. |
| 2026-11-22 | E4: DeBERTa entailment **MEASURED: LOSES** | DeBERTa acc=0.672 (CI [0.552, 0.776]) vs cascade acc=0.806 (CI [0.701, 0.896]). CIs overlap but cascade is strictly better on every metric. DeBERTa P=0.438 R=0.350 F1=0.389 vs cascade P=0.818 R=0.450 F1=0.581 (tp=7/fp=9/fn=13 vs tp=9/fp=2/fn=11). DeBERTa has 4.5× worse false-positive rate on Indian statutory entailment. Generic English NLI (MNLI+FEVER+ANLI training) cannot match hand-built deterministic modules tuned for Indian legal constructions (negation mutations, qualifier drops, quantity changes). Prior entry used broken zero-shot-classification pipeline; this corrected run uses proper (premise, hypothesis) NLI. |
| 2026-11-22 | E5: Qwen3-14B generation **DESIGN ONLY** | Requires Azure AI Foundry (PLAN_22 D3). Eval design: (1) metrics — factual accuracy on 20 hand-verified claim-evidence pairs, hallucination rate on 10 prompts with no evidence, citation precision on 30 generated passages; (2) test set — reuse entail_pairs_v2 entailed subset + 10 new generation-specific cases; (3) promotion bar — non-overlapping 95% CI on factual accuracy vs incumbent (Claude Haiku 4.5 via Bedrock), AND 0 hallucinated citations on the no-evidence set; (4) constraint — every call via Azure AI Foundry ap-south-1, never vendor API directly. Cannot run until Azure subscription is active. |
