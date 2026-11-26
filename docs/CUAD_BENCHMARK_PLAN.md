# CUAD Benchmark Plan

## Purpose

Compare Mistral Large 4 (candidate) against existing incumbents on contract
clause extraction. Mistral is promoted from CANDIDATE to PREFERRED in
`checker/router.py` only after passing the benchmark (PLAN_22 D2).

---

## 1. Evaluation Datasets

### A. CUAD Test Split

**Source:** `theatticusproject/cuad` on HuggingFace, standard train/test split.
**Size:** ~100 contracts held out (20% of 510).
**Format:** SQuAD 2.0 JSON with gold spans per category.
**Purpose:** Direct comparison with published baselines (DeBERTa-xlarge AUPR 47.8).

### B. Indian Corporate Contract Set (curated)

**Source:** Manually curated from public Indian contract filings (MCA, BSE/NSE
EDIFAR, ROC public registers).
**Size target:** 50 contracts across 5 types:
- 10 service agreements
- 10 share purchase agreements
- 10 joint venture agreements
- 10 employment agreements
- 10 NDAs

**Annotation:** Each contract annotated for:
- All applicable CUAD categories
- India-specific categories: stamp duty, arbitration seat, Companies Act
  references, SEBI reporting obligations
- Party identification (for LexDeMod Stage 9)

**Contract-level separation:** No contract appears in both development and
evaluation sets. If a contract has amendments, all versions go in the same set.

---

## 2. Metrics

### Primary

| Metric | Definition | Threshold |
|--------|-----------|-----------|
| Exact Match (EM) | `gold_text == predicted_text` (after whitespace normalization) | ≥ 0.70 |
| Token F1 | Precision × Recall on word-level overlap between predicted and gold | ≥ 0.80 |
| Evidence Precision | Fraction of predicted spans that are VERIFIED against source | ≥ 0.90 |
| Evidence Recall | Fraction of gold spans where model found something (not NOT_FOUND) | ≥ 0.70 |

### Secondary

| Metric | Definition | Threshold |
|--------|-----------|-----------|
| Span Accuracy | Predicted offsets within ±50 chars of gold offsets | report only |
| Unsupported Answer Rate | Fraction of extractions that are UNVERIFIED | ≤ 0.10 |
| Abstention Quality | Precision of NOT_FOUND (when gold is also empty) | ≥ 0.80 |
| JSON/Schema Validity | Fraction of model responses that parse as valid JSON | ≥ 0.95 |
| Latency (p50) | Median time per window extraction | report only |
| Latency (p95) | 95th percentile time per window extraction | report only |
| Cost per contract | Total API cost for all windows of one contract | report only |

### Statistical Requirements (PLAN_22 D2)

- All comparisons use non-overlapping 95% confidence intervals
- Bootstrap CI with 1000 resamples, contract-level (not span-level)
- A model is promoted only when its CI does not overlap the incumbent's
- If CIs overlap: incumbent stays preferred, candidate stays candidate

---

## 3. Providers Under Test

| Provider | Model | Deployment | Role |
|----------|-------|------------|------|
| Mistral | Large 4 | `mistral-large-4` on Azure AI Foundry | Candidate |
| Azure | Llama 3.3 70B | `llama-3-3-70b` on Azure AI Foundry | Current EXTRACTION fallback |
| Azure | GPT-5 Mini | `gpt-5-mini` on Azure AI Foundry | Current EXTRACTION second fallback |

**Not tested (and why):**
- Anthropic Claude: no credit, API returns HTTP 400. Remains first preference
  when credit returns.
- Ollama local: operator-specific model, not benchmarkable in a reproducible way.
- Gemini: not wired for EXTRACTION purpose.

---

## 4. Test Protocol

### Input Construction

For each contract in the evaluation set:
1. Run `sanitize.normalize_text()` → normalized text
2. Run `pipeline.process()` → DocumentState with classification and tags
3. Run `cuad_extractor._windows()` → windows
4. For each window, run `cuad_extractor._build_prompt()` → identical prompt

**Critical:** Every provider receives the EXACT SAME prompt for the same window.
Prompts are generated once and stored in `data/benchmark/prompts/`.

### Execution

For each provider:
1. Send each prompt through that provider's API
2. Record raw response, latency, HTTP status
3. Parse response with `cuad_extractor._parse_response()`
4. Verify with `cuad_extractor._verify_extractions()`
5. Deduplicate with `cuad_extractor._deduplicate()`
6. Compare against gold annotations

### Evaluation

```python
# Per category, per contract:
for contract in eval_set:
    for category in CUAD_CATEGORIES:
        gold = gold_annotations[contract][category]
        predicted = model_output[contract][category]

        em = exact_match(gold, predicted)
        f1 = token_f1(gold, predicted)
        evidence_ok = predicted.status in ("VERIFIED", "FUZZY_MATCH")
        abstained_correctly = (gold is None and predicted is None)
```

### Output

`reports/bakeoff_cuad_{date}.json`:
```json
{
    "date": "2026-12-01",
    "eval_set": "cuad_test",
    "n_contracts": 100,
    "providers": {
        "mistral-large-4": {
            "exact_match": {"mean": 0.75, "ci_lower": 0.70, "ci_upper": 0.80},
            "token_f1": {"mean": 0.85, "ci_lower": 0.81, "ci_upper": 0.89},
            "evidence_precision": 0.93,
            "evidence_recall": 0.78,
            "unsupported_rate": 0.07,
            "abstention_precision": 0.85,
            "json_validity": 0.98,
            "latency_p50_ms": 2300,
            "latency_p95_ms": 5100,
            "cost_per_contract_inr": 12.50
        },
        "llama-3-3-70b": { ... },
        "gpt-5-mini": { ... }
    },
    "promotion_decision": "HOLD — CIs overlap on token_f1",
    "decided_by": "pending human review"
}
```

---

## 5. Acceptance Criteria for Promotion

Mistral Large 4 is promoted from CANDIDATE to PREFERRED when ALL of:

1. Token F1 ≥ 0.80 on CUAD test split (mean, not lower CI bound)
2. Evidence Precision ≥ 0.90 (VERIFIED + FUZZY_MATCH extractions)
3. Unsupported Answer Rate ≤ 0.10
4. JSON/Schema Validity ≥ 0.95
5. 95% CI on Token F1 does not overlap incumbent's CI
6. No category has Token F1 < 0.50 (no catastrophic failure on any type)
7. A person reviews the report and edits the router table

**Criteria 7 is non-negotiable.** The script produces the report; a person makes
the edit. This is PLAN_22 D2: "a person edits table."

---

## 6. Script Design: `scripts/bakeoff_models.py`

```python
"""Bake-off: compare model providers on CUAD extraction.

Produces reports/bakeoff_cuad_{date}.json. The script measures; a person decides.

Usage:
    PYTHONPATH=. python3 scripts/bakeoff_models.py \
        --eval-set data/benchmark/cuad_test.json \
        --providers mistral-large-4,llama-3-3-70b,gpt-5-mini \
        --output reports/

The script CANNOT modify router.py. PLAN_22 D2 requires a human edit.
"""
```

**Functions:**
- `load_eval_set(path)` → list of (contract_text, gold_annotations)
- `generate_prompts(contract, gold)` → list of (window, prompt, gold_per_window)
- `run_provider(provider, prompts)` → list of (response, latency)
- `evaluate(responses, gold)` → metrics dict
- `bootstrap_ci(scores, n=1000, alpha=0.05)` → (lower, upper)
- `compare_providers(metrics_a, metrics_b)` → promotion_decision
- `write_report(all_metrics, path)` → JSON file

---

## 7. Indian Contract Annotation Guidelines

For the Indian evaluation set, annotators follow these guidelines:

1. Use the same 41 CUAD categories
2. Add India-specific annotations:
   - **Stamp Duty:** "What stamp duty provisions apply?"
   - **Arbitration Seat:** "What is the seat of arbitration?"
   - **Companies Act Reference:** "Which sections of the Companies Act are referenced?"
   - **SEBI Compliance:** "What SEBI reporting requirements are mentioned?"
3. Mark clauses that differ from US conventions (e.g., "governed by Indian law"
   rather than state-specific)
4. Include Hindi/regional language clauses if present (bilingual contracts)
5. Annotate party names as they appear (Indian naming conventions)

**Annotation format:** Same SQuAD 2.0 JSON as CUAD, with India-specific categories
added as categories 42–45.
