# ML program — autonomous loop runbook

Authorised 2026-09-05 with full decision authority. This file is the loop's durable
state: each iteration reads it, does the next unchecked task, tests, commits, ticks the
box. It stops only when the queue is empty or a task is blocked by physics.

## Hardware reality (measured, not assumed)

    Apple M1 · 8 GB unified memory · Metal 4 · no CUDA
    ollama: gemma3:1b (815M) · llama3 (4.7G) · qwen3.5 (6.6G) · mistral-nemo (7.1G)
    python: numpy ✓ torch ✓ transformers ✓ sentence_transformers ✓ sklearn ✓ mlx ✗

Two consequences decide the whole program:

1. **The 8B QLoRA fine-tune is cancelled.** Unsloth requires NVIDIA/CUDA; there is
   none. 8 GB is *total* unified memory, and qwen3.5 alone takes 6.6 GB. This is not a
   judgement call to revisit — it is arithmetic. Any tier of the ablation matrix that
   requires a trained adapter (V3, and the PEFT half of V5) is **NOT RUNNABLE** and is
   recorded as such rather than faked.
2. **Decision B is unblocked.** It was deferred on 2026-09-04 because adding an
   embedding dependency violated the no-new-dependency rule. `sentence_transformers` is
   already installed. The stated reason no longer holds, so the experiment runs — and
   it is measured against the frozen BM25 baseline, not adopted on faith.

## The ablation matrix, honestly scoped

| Tier | Configuration | Runnable here | Why |
|---|---|---|---|
| V1 | base model + prompting | **yes** | gemma3:1b fits in memory |
| V2 | + dense retrieval | **yes** | sentence_transformers present |
| V3 | PEFT, no retrieval | **NO** | needs CUDA + a gold set that has no annotators |
| V4 | + hybrid BM25⊕dense, RRF | **yes** | BM25 shipped; dense from V2 |
| V5 | + reranker + constrained JSON | **partial** | reranker and JSON constraint yes; PEFT half no |

Four of five tiers are real. The two that are not are marked NOT_RUNNABLE with the
reason, because a matrix with an invented row is worse than a matrix with a gap.

## Queue

- [ ] **M1 — Dense embedding index.** `checker/dense_index.py`: embed all ~474 section
      headings+text with a local sentence-transformers model, cache to disk, expose
      `search(query, k)`. Must degrade to a clear refusal if the model cannot load —
      never silently fall back to BM25 and report a dense number.
- [ ] **M2 — Measure dense vs BM25 on the frozen eval.** Run `cross_section_eval`'s 70
      cases through dense retrieval. Record p@1 and recall@5 beside BM25's 0.71/0.91.
      Report the honest delta whichever way it goes. Do NOT tune.
- [ ] **M3 — RRF fusion.** `checker/fusion.py`: Reciprocal Rank Fusion over BM25 and
      dense rank lists. Measure fused p@1/recall@5. RRF fuses ranks, never scores.
- [ ] **M4 — Learned reranker (the perceptron).** A from-scratch linear model trained on
      the eval's own labels over interpretable features (BM25 rank, dense rank, heading
      overlap, section-number literal match). Cross-validated so the reported number is
      not the training score. Every weight must be inspectable — a black-box reranker in
      a system whose thesis is auditability would be a contradiction.
- [ ] **M5 — Ablation harness.** `checker/ablation.py`: run V1/V2/V4/V5 end to end and
      emit the table, with V3 explicitly NOT_RUNNABLE and the reason attached.
- [ ] **M6 — Push.** Plan + results to the business-plan repo.

## Rules the loop may not break

- No new pip install. Everything used is already on disk.
- No model in a decision path. Retrieval ranks; deciders decide; the E-gate verifies.
- Measure before adopting. A component that does not beat the frozen baseline is
  reported as not beating it, and is not merged into the default path.
- Do not tune on the eval. The 70 cases are a bar, not a training set. M4 is the one
  exception and it is cross-validated precisely because of that.
- Human-gated items (H-B lawyer labels, H-C practitioner review) are untouched.

## Log

- 2026-09-05 — environment measured; fine-tune cancelled on hardware grounds; decision B
  unblocked because its stated blocker (new dependency) is already resolved.
