# CUAD Extractive QA Stage — Implementation Plan

## What this is

`checker/cuad_extractor.py` — the model-dependent stage that calls Mistral Large
via the router to extract clause values from contracts. This replaces (and extends)
the regex tagger's output with exact quoted spans containing obligation amounts,
dates, party names, and clause text.

## Research basis

| Paper | Key contribution | How we use it |
|-------|-----------------|---------------|
| CUAD (Hendrycks et al., NeurIPS 2021, arXiv 2103.06268) | 41 clause categories, SQuAD 2.0 extractive QA format, 510 contracts | Category list, question templates, evaluation methodology |
| ConReader (Xu et al., EMNLP 2022, arXiv 2210.08697) | Long-range context, term-definition, similar-clause relations | Informs our context window strategy (include definitions section) |
| SQuAD 2.0 (Rajpurkar et al., 2018) | Extractive QA with unanswerable questions | Input format, no-answer handling pattern |

## Architecture decision: generative extraction, not BERT QA head

The CUAD paper fine-tunes RoBERTa/DeBERTa with a QA head that outputs start/end
logits. We use Mistral Large (generative LLM) via the router because:

1. **We already have the router** — Mistral Large is wired as CANDIDATE for EXTRACTION
2. **Generative models quote verbatim** — measured 0.933 exact-span on CUAD test split
   (reports/bakeoff_2026-09-29.json, Azure llama-3-3-70b)
3. **41 categories in one prompt** — no per-category fine-tuning needed
4. **PLAN_23 verification** — every extracted span is verified against the source text
   by deterministic code, so a model error becomes UNVERIFIED, not a wrong fact

## The 41 CUAD categories and their questions

Each category gets a question template. The CUAD paper's format:
> "Highlight the parts (if any) of this clause related to '<Category>'.
>  Details: <Description>"

For a generative model, we adapt this to a structured extraction prompt.

### Category registry (all 41)

```
 #  Category                          Type       Question
 1  Document Name                     entity     What is the name of this agreement or document?
 2  Parties                           entity     Who are the parties to this agreement?
 3  Agreement Date                    date       What is the date of this agreement?
 4  Effective Date                    date       When does this agreement become effective?
 5  Expiration Date                   date       When does this agreement expire?
 6  Renewal Term                      span       What are the renewal terms?
 7  Notice to Terminate Renewal       span       How much notice is required to terminate renewal?
 8  Governing Law                     entity     Which jurisdiction's law governs this agreement?
 9  Most Favored Nation               boolean    Is there a most favored nation clause?
10  Non-Compete                       span       What are the non-compete restrictions?
11  Exclusivity                       span       What are the exclusivity provisions?
12  No-Solicit of Customers           span       Is there a no-solicitation of customers clause?
13  Competitive Restriction Exception span       Are there exceptions to competitive restrictions?
14  No-Solicit of Employees           span       Is there a no-solicitation of employees clause?
15  Non-Disparagement                 span       Is there a non-disparagement clause?
16  Termination for Convenience       span       Can either party terminate for convenience?
17  ROFR/ROFO/ROFN                    span       Is there a right of first refusal, offer, or negotiation?
18  Change of Control                 span       What happens on a change of control?
19  Anti-Assignment                   span       Are there anti-assignment provisions?
20  Revenue/Profit Sharing            span       Is there revenue or profit sharing?
21  Price Restriction                 span       Are there price restrictions?
22  Minimum Commitment                span       What are the minimum commitment requirements?
23  Volume Restriction                span       Are there volume restrictions?
24  IP Ownership Assignment           span       Is there an IP ownership assignment clause?
25  Joint IP Ownership                span       Is there joint IP ownership?
26  License Grant                     span       What license is granted?
27  Non-Transferable License          boolean    Is the license non-transferable?
28  Affiliate IP License-Licensor     span       Can the licensor's affiliates use the IP?
29  Affiliate IP License-Licensee     span       Can the licensee's affiliates use the IP?
30  Unlimited/All-You-Can-Eat License boolean    Is the license unlimited or all-you-can-eat?
31  Irrevocable or Perpetual License  boolean    Is the license irrevocable or perpetual?
32  Source Code Escrow                span       Is there a source code escrow provision?
33  Post-Termination Services         span       Are post-termination services required?
34  Audit Rights                      span       What audit rights exist?
35  Uncapped Liability                boolean    Is liability uncapped?
36  Cap on Liability                  span       What is the cap on liability?
37  Liquidated Damages                span       Are there liquidated damages provisions?
38  Warranty Duration                 span       What is the warranty duration?
39  Insurance                         span       What insurance is required?
40  Covenant Not to Sue               span       Is there a covenant not to sue?
41  Third Party Beneficiary           span       Are there third party beneficiaries?
```

**Type key:**
- `entity` — answer is a name, date, or jurisdiction (8 of 41)
- `date` — answer is a date or date expression
- `boolean` — CUAD's "derived answer" categories (presence/absence, but we still extract the span)
- `span` — answer is the clause text itself

## Implementation: 6 parts, each independently verifiable

### Part 1: Category registry (`_CATEGORIES` dict)

A frozen dict mapping category name → `(question, answer_type, description)`.
The 41 entries above, as data. No logic.

**Verify:** assert len == 41, assert all 13 regex tagger categories map to a CUAD
category, assert no duplicate names.

### Part 2: Document windowing (`_windows()`)

Split a document into overlapping windows for the extraction prompt.

**Algorithm (from SQuAD 2.0 / CUAD):**
- `max_context_chars = 6000` — fits comfortably in Mistral Large's context with the
  prompt template and all 41 questions
- `stride_chars = 2000` — 1/3 overlap, so a clause at a window boundary appears in
  full in at least one window
- Each window carries its `(start_offset, end_offset)` in the original document

**ConReader insight:** include the definitions section (usually at the top) in every
window, because term-definition relations are long-range. If the first 2000 chars
contain "definitions" or "interpretation", prepend them to every window.

**Verify:** a 20,000-char document produces the right number of windows, overlap is
correct, offsets are correct, definitions section is prepended.

### Part 3: Prompt construction (`_build_prompt()`)

Build the extraction prompt for a single window.

**Format:**
```
You are a contract clause extractor. For each category below, extract the EXACT
text from the contract that answers the question. Rules:
- Quote the contract VERBATIM — do not paraphrase, summarize, or add words
- If the contract does not contain the answer, respond with "NOT_FOUND"
- Return ONLY a JSON object mapping category name to extracted text

Contract text:
---
{window_text}
---

Extract the following:
{for each relevant_category: "Category: Question"}

Respond with a JSON object. Keys are category names, values are the verbatim
extracted text or "NOT_FOUND".
```

**Optimization:** Only ask about categories the regex tagger flagged OR categories
the regex tagger cannot detect (the 28 categories not in `clause_tags.TAGS`). This
avoids asking about Non-Compete in a service agreement with no non-compete clause.

**Verify:** prompt is well-formed, relevant categories are selected correctly,
prompt fits in Mistral Large's context budget (4096 completion tokens).

### Part 4: Response parsing (`_parse_response()`)

Parse the model's JSON response into structured extractions.

**Algorithm:**
1. Strip markdown fences if present (`json ... `)
2. Parse as JSON
3. For each key-value pair:
   - Skip if value is "NOT_FOUND" or empty
   - Validate key is a known category name
   - Store as `Extraction(category, quoted_text, window_start, window_end)`

**Verify:** handles clean JSON, markdown-wrapped JSON, malformed JSON (returns
empty list, never crashes), NOT_FOUND filtering, unknown category rejection.

### Part 5: Span verification (`_verify_extractions()`)

**This is the PLAN_23 gate.** Every extraction is verified against the source text.

**Algorithm:**
1. For each `Extraction`, search for `quoted_text` in the original document
2. **Exact match:** `text.find(quoted_text)` — if found, record `(start, end)` and
   mark VERIFIED
3. **Fuzzy match:** if exact match fails, compute word-level Jaccard similarity
   (CUAD's own metric) between the extraction and every sentence in the document.
   If Jaccard ≥ 0.5, mark FUZZY_MATCH with the best-matching sentence
4. **No match:** mark UNVERIFIED — the model hallucinated or paraphrased

A VERIFIED extraction has an exact span in the document.
A FUZZY_MATCH extraction has a likely source sentence but the model rephrased it.
An UNVERIFIED extraction is dropped from the output — it is not a clause value.

**Verify:** exact matches are found at correct offsets, fuzzy matches work for
minor whitespace/punctuation differences, hallucinated text is caught.

### Part 6: Pipeline integration (`extract()`)

The public function that the pipeline calls.

```python
def extract(state: DocumentState, *, route_fn) -> DocumentState:
    """CUAD extractive QA on a document that has been classified and tagged.

    Calls the model through route_fn (which calls router.route() → Mistral Large
    → Azure AI Foundry). Every extraction is verified against the source text.
    Code owns the pipeline; the model proposes; deterministic code verifies.
    """
```

**Flow:**
1. `_windows(state.text)` → list of windows
2. For each window: `_build_prompt(window, state.tags)` → prompt
3. `route_fn(prompt)` → model response (through router → Mistral Large)
4. `_parse_response(response)` → list of raw extractions
5. `_verify_extractions(raw, state.text)` → verified extractions only
6. Merge across windows (deduplicate by Jaccard ≥ 0.8 on the extracted text)
7. Return updated `DocumentState` with `extractions` and `extraction_route`

**Verify:** end-to-end with a mock route_fn that returns canned JSON, correct
deduplication across windows, correct pipeline state update.

## What this does NOT do

- **Fine-tune a model.** We use the generative model as-is, through the router.
- **Replace the regex tagger.** The tagger runs first (Stage 2) and its output
  guides which categories the extractor asks about. The extractor EXTENDS, not
  replaces.
- **Make legal judgements.** An extracted span is a pointer, not a finding (same
  principle as `clause_tags.py`). Whether the clause is valid, standard, or
  acceptable is the playbook's job.
- **Bypass the router.** All model calls go through `router.route()` → Azure AI
  Foundry (PLAN_22 D3).

## Mapping: regex tagger → CUAD categories

| clause_tags.py (13)        | CUAD category (41)              |
|----------------------------|---------------------------------|
| Governing Law              | Governing Law (#8)              |
| Term                       | Renewal Term (#6), Expiration Date (#5) |
| Termination for Convenience| Termination for Convenience (#16) |
| Confidentiality            | (no direct CUAD match — NDA-specific) |
| Indemnity                  | (no direct CUAD match — but related to liability) |
| Limitation of Liability    | Cap on Liability (#36), Uncapped Liability (#35) |
| Non-Compete                | Non-Compete (#10)               |
| Assignment                 | Anti-Assignment (#19)           |
| Notice Period              | Notice to Terminate Renewal (#7)|
| Renewal                    | Renewal Term (#6)               |
| Audit Rights               | Audit Rights (#34)              |
| Insurance                  | Insurance (#39)                 |
| Dispute Resolution         | (no direct CUAD match — but related to Governing Law) |

The 28 CUAD categories not in the regex tagger are NEW extraction targets.

## Execution order

1. Part 1 (category registry) — code and verify
2. Part 2 (windowing) — code and verify
3. Part 3 (prompt construction) — code and verify
4. Part 4 (response parsing) — code and verify
5. Part 5 (span verification) — code and verify
6. Part 6 (pipeline integration) — code and verify

Each part has its own self-test block. No part depends on a live model — all tests
use deterministic inputs and canned responses.

## Sources

- [CUAD paper (NeurIPS 2021)](https://arxiv.org/abs/2103.06268)
- [CUAD GitHub](https://github.com/The-Atticus-Project/cuad)
- [CUAD HuggingFace dataset](https://huggingface.co/datasets/theatticusproject/cuad)
- [Rakib/roberta-base-on-cuad](https://huggingface.co/Rakib/roberta-base-on-cuad)
- [ConReader (EMNLP 2022)](https://arxiv.org/abs/2210.08697)
- [SQuAD 2.0 sliding window details](https://arxiv.org/pdf/2008.12804)
- [Norm extraction with ChatGPT](https://arxiv.org/abs/2404.02269)
- [Cost-benefit analysis (AI & Law, 2025)](https://link.springer.com/article/10.1007/s10506-025-09484-4)
