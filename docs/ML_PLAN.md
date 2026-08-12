# The machine-learning plan

Written 2026-08-12, answering: *where do we build the neural network, where do we train it, and
where does the training data come from?*

The short answer is **nowhere, nowhere, and you don't have any** — and that is a finding worth
writing down properly rather than a failure to work around. This document says why, in enough
detail to defend to a technical co-founder, and names the exact conditions under which each answer
changes.

---

## 0. First, a correction to the status table

The plan lists ten components, seven marked "❌ Not built" at paths under `src/`. **`src/` does not
exist in this repository.** Every one of those seven is already built somewhere else:

| Plan says missing | Actually exists as | Size |
|---|---|---|
| `src/rag/embeddings.py`, `src/rag/vector_store.py` | `checker/retrieval.py` (keyword route + scan, no vectors — deliberately) | 4 KB |
| `src/llm/client.py` | `backend/services/llm.py` | 8.9 KB |
| `src/safety/pipeline.py` | `checker/verifier.py` | 17.7 KB |
| `src/rag/pipeline.py` | `checker/ask_engine.py` | 17.9 KB |
| `src/evaluation/evaluator.py` | `checker/test_unlock.py` + `scripts/verify.py` | 67 KB |
| `src/playbooks/posh_playbook.py` | `applicability.py` + `checker/assess.py` | 22 KB |

Pasting the six prompts would produce a parallel `src/` tree duplicating ~140 KB of tested code,
with two implementations of the safety layer disagreeing silently. **Do not paste them.**

---

## 1. You are already using neural networks. You are not training them, and that is correct.

Worth being precise, because "we don't do AI" would be wrong.

- **Llama-3.3-70B / Claude** — a transformer. Billions of parameters, trained by someone else.
  `backend/services/llm.py` is pinned and ready; the path is dark until a lawyer verifies.
- **`all-MiniLM-L6-v2`** — a 6-layer distilled BERT producing 384-dimensional embeddings. It is
  what the plan proposes for retrieval. We rejected it, and the reason is arithmetic, not taste.

A perceptron is a linear function fitted to data. A neural network stacks them with
non-linearities so the composite can approximate functions you cannot write down. **That last
clause is the whole test.** You train a network when you cannot state the rule.

For every decision this product makes, **you can state the rule, and the rule is the statute.**
`applicability.py` is not an approximation of s.4 — it *is* s.4, transcribed into control flow. A
network trained to predict its output would be a lossy approximation of a function we already
compute exactly, fitted on data we would have to generate from the exact function. That is not a
model. That is a slower, less reliable copy with a confidence score bolted on.

---

## 2. The three places a trained model could actually go

Assessed honestly, including the one that is real.

### 2.1 Retrieval ranking — **no, and the arithmetic is not close**

The proposal: embed 30 sections into ChromaDB, embed the query, take cosine top-3.

| | Vector search | What we do |
|---|---|---|
| Dependencies | torch + sentence-transformers, ~2 GB | stdlib |
| Cold start | seconds | none |
| Latency over 30 sections | ~10–40 ms | **0.05 ms** measured |
| Recall guarantee | approximate, tuned by threshold | **exact** — every section is examined |
| Failure mode | silently returns the wrong section, confidently | none available |

Over 30 documents a linear scan *is* the exhaustive search. Cosine similarity is an approximation
of an operation we perform exactly and faster. Embeddings become correct when the corpus is large
enough that exhaustive comparison is too slow — **around 500 sections**, i.e. when the four labour
codes land.

There is a second reason, specific to law. Embeddings encode *topical* similarity. Legal retrieval
frequently needs *structural* relation: s.4 matters to a question about s.26 because s.26(1)(a)
names it, not because they read alike. `provision_graph.py` traverses the statute's own
cross-references, which is exact and free. [Falkor-IRAC](https://arxiv.org/abs/2605.14665) reaches
the same conclusion from the other direction, and there is a companion note titled *Why Vector RAG
Fails in Law*.

### 2.2 Clause extraction from an uploaded policy — **genuinely real, and blocked on data**

This is the one honest ML task in the product, and the plan does not identify it.

A company uploads its own PoSH policy — prose written by their HR team or a law firm, not statute.
The system must find *"the clause that constitutes the Internal Committee"* and decide whether it
satisfies s.4(2). Today that is regex and keyword matching, which fails the moment a policy says
*"a redressal panel shall be convened"* instead of *"Internal Complaints Committee"*.

That is **span extraction / sequence labelling** — a genuine supervised learning problem:

```
input   : the policy text
output  : character spans, each labelled with the s.4(2) requirement it satisfies
model   : token classification head on a legal encoder (InLegalBERT for Indian legal English)
compute : fine-tunes on CPU in under an hour for a few hundred examples; a rented GPU is ~₹500
```

**The blocker is not compute. It is labels.** You need on the order of 200–500 policies with spans
marked by someone who knows s.4(2). You currently have **zero**, and there is exactly one
legitimate source: policies real customers upload, labelled during review.

Which places this ML work **downstream of the business gates, not parallel to them**. It is not
something to start on Monday. It is something that becomes possible after roughly fifty customers,
and pretending otherwise is how a founder spends three months building a labelling pipeline for a
dataset that never arrives.

Interim, and free: keep regex, and **abstain loudly when it finds nothing**. An extractor that says
*"we could not locate an IC constitution clause — check manually"* is correct. One that guesses is
the failure this whole repository is built against.

### 2.3 Multilingual query understanding — **no, buy it**

Kannada and Hindi query handling is real product value. A fine-tuned multilingual encoder would
help. So would the API, immediately, for ₹0 more than we already plan to spend, without a training
set in a language nobody here can label. Revisit only if a specific measured failure appears.

---

## 3. So what is the ML roadmap?

| Phase | Work | Model trained | Blocked on |
|---|---|---|---|
| Now | Exact methods. Corpus, register, graph traversal. | none | nothing |
| After Gate 1 (lawyer) | LLM path on, **Citations API** for character-level provenance | none | one evening of a lawyer's time |
| ~50 customers | Label uploaded policies during review; build the span dataset | none yet | customers |
| ~200–500 labelled policies | Fine-tune a token classifier for clause extraction | **first real training run** — CPU or ~₹500 GPU | the dataset above |
| ~500 corpus sections | Re-evaluate vector retrieval against the scan, with numbers | none | labour-code ingestion |

**Nothing before row three involves training anything.** That is the plan. It is short because the
honest version is short.

---

## 4. What to build instead, and it is not nothing

Three items with real technical content, all available today, none requiring a training set. Two
come from [Falkor-IRAC](https://arxiv.org/abs/2605.14665), which independently built this
architecture and measures two things we do not.

### 4.1 Path validity rate

We verify that a *claim* is sourced. They verify that a *reasoning path* is traceable end to end
through the graph. Ours is the weaker test: a claim can cite a real provision while the chain of
provisions supporting it is broken.

```
for each answer:
    reconstruct the path: question -> retrieved sections -> their dependencies -> the cited claim
    valid if every edge exists in provision_graph AND every node's status is answerable
report: fraction of answers with a fully valid path
```

### 4.2 Conflict detection

`epistemic_status.py` composes weakest-link, so a chain is only as strong as its worst ground. It
has no notion of two provisions that *contradict* each other — it will happily return the stronger
one. Real statutes conflict, and provisos exist precisely to carve exceptions.

```
for each pair of retrieved provisions:
    if one is a proviso to the other, or they impose incompatible obligations
    -> flag CONFLICT and abstain, naming both
```

### 4.3 Evaluate against IL-TUR before building our own set

[IL-TUR](https://aclanthology.org/2024.acl-long.618/) (ACL 2024) is a peer-reviewed Indian legal
understanding benchmark — English, Hindi, nine Indian languages. Our Phase 3 says "build a golden
set with the teacher". Measure against IL-TUR **first**. A lawyer's evening is the scarcest
resource in this project and belongs on the six load-bearing clauses, not on re-deriving a
benchmark a research group already published and validated.

Report three numbers, never one:

| Metric | Target | Why |
|---|---|---|
| Fabrication rate | **0** | Stanford RegLab measured 17–33% for Lexis and Westlaw on the architecture the plan proposes |
| Coverage | rises as `verified_by` fills | today it is 0% *by design* |
| Wrong abstention | falls | the real cost of this design, currently unmeasured |

---

## 5. What to say when someone asks "so where's your AI?"

> "The model is not the product and we do not train one. The rule engine is the statute in control
> flow, so there is nothing to approximate. A model explains a decision it did not make, and an
> external verifier rejects any figure or citation absent from the source text. The one place a
> trained model would genuinely earn its keep is extracting clauses from a customer's own policy
> prose — that needs a few hundred labelled policies, we have none, and the only honest way to get
> them is from customers. So it is on the roadmap after fifty of them, not before."

Every sentence there is checkable, which is the only kind of technical claim worth making about
this product.

---

## 6. The two errors in the plan's own safety design

Worth recording, because they are subtle and both were flagged in its Layer 4.

**The HallucinationGuard uses embedding similarity to detect fabrication.** It encodes each answer
sentence, encodes the context, and flags similarity below 0.6. This does not detect fabrication —
it detects *topical drift*. A sentence saying *"the deadline is 31 January"* is highly similar to a
context about annual reporting deadlines and sails through at ~0.8. A correct sentence phrased
unusually gets flagged. It is a paraphrase detector wearing a fact-checker's badge. `verifier.py`
does the checkable thing instead: **exact substring and numeric comparison against source.**

**The ConfidenceScorer converts retrieval distance into a percentage shown to the user.** Cosine
similarity between a query and a retrieved chunk is not a probability that the answer is correct;
it measures whether we found related text, not whether the claim is true. Displaying "94%
confidence" is the calibrated-confidence claim this project has refused six times, arrived at
through a back door. It requires a labelled validation set to mean anything, and we have none.
