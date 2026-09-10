# Architecture — 20 roles, 9 models, 0 model decisions

## The premise

Harvey's public description of its safety mechanism is a prompt: *"Answer the
user's question using ONLY the text provided below."* This repo's
`model_adapter.py` says, in its own docstring, why that is not enough:

> Four refusals happen BEFORE any model call, **because a prompt is not a safety
> mechanism.**

That is the whole architectural difference, and everything below follows from it.
Harvey verifies that a citation exists. We verify that the claim follows from it
**and that the cited law is still in force.** The second half is what no amount
of model improvement buys, because it is a property of the corpus.

## Why a lattice and not a RAG pipeline

The standard design — `parse → embed → retrieve → generate → check` — fails
because **nothing downstream of a bad retrieval can detect a bad retrieval.** A
cosine search returns its top-k for a question the corpus cannot answer.

Two findings make this concrete for statutory work:

- **SOURCED, and the number is literal.** On a 32,436-article-version corpus of
  French tax law with explicit validity dates, static RAG retrieved the
  date-applicable version **0% of the time** across 209 questions — 2.7% strict
  accuracy — while confidently citing real but temporally inapplicable text.
  Date-conditioned retrieval over the same versioned corpus scored 98.3–99.1%.
  (arXiv:2608.09393. French tax law, not Indian company law — cite it as evidence
  of the *pattern*, not of India.)
- **SOURCED.** Stronger-reasoning models are *worse* at temporal applicability.
  On 26,000 Chinese civil judgments, accuracy on the old statute version fell
  below 0.25 against 0.70–0.84 on the current version, and stronger reasoning
  models did worse — reduced exploration across temporal alternatives.
  (arXiv:2608.14610.) **A better model does not close this gap; it widens it.**

So a perfect retriever over a stale corpus produces a confident wrong answer —
exactly the ₹4 crore failure. Currency is the load-bearing layer, not retrieval.

## The 20 roles

Model count is a cost and a risk surface, not a feature. Harvey's Vault
"5,000 mini-agents" is a MapReduce over extraction calls — parallelism, not
intelligence. Here is the honest inventory.

### Tier 0 — deterministic, no model (11 roles). This is the product.

| # | Role | Module | State |
|---|---|---|---|
| 1 | Corpus admission | `admission.py` | BUILT |
| 2 | Point-in-time resolver | `as_of.py` | BUILT |
| 3 | Derived-date computer | `derived_date.py` | BUILT |
| 4 | Applicability decider | `obligations.py` (1,448 ln) | BUILT |
| 5 | Transaction deciders | `s185/186/188/180/184.py` | BUILT |
| 6 | Entity graph | `entity_graph.py` | BUILT |
| 7 | Currency engine | `currency.py` | BUILT |
| 8 | Staleness auditor | `staleness.py` | BUILT |
| 9 | Event log | `event_log.py` | BUILT |
| 10 | Provenance slots | `provenance_slots.py` | BUILT |
| 11 | Lexical retrieval | BM25 + RRF | BUILT, MEASURED 0.80 p@1 |

### Tier 1 — small, local, cheap (4 roles)

| # | Role | Choice | State |
|---|---|---|---|
| 12 | Document classifier | small encoder | DESIGNED |
| 13 | OCR + layout | tiered: cheap OCR → VLM fallback | DESIGNED |
| 14 | Reranker | InLegalBERT (MIT) | DEFERRED — fusion already at 0.80 |
| 15 | **Entailment head** | fine-tuned NLI, E3→E6 cascade | **The one model worth training** |

### Tier 2 — frontier model, each downstream of a gate that can reject it (5 roles)

| # | Role | Constraint | State |
|---|---|---|---|
| 16 | Extractor | proposes typed facts; every span verified | `extraction_schema.py` BUILT, unwired |
| 17 | Narrator | phrases verified results only | `model_adapter.py` BUILT, stub model |
| 18 | Slot-filler | emits `MODEL_SUGGESTION`; blocks approval | `drafting.py` BUILT, unwired |
| 19 | Query planner | decomposes retrievals; never decides law | DESIGNED |
| 20 | Critic | checks the others against the pack | `cascade.py` partially BUILT |

**Nine of twenty use a model. Five use a frontier model. Zero decide whether a law
applies.** A 20-model swarm where models decide things fails this repo's own rules
on the first row.

## The gate that makes it safe

Everything a model emits passes through, in order:

```
model output
  → schema validation      (extraction_schema: could this even exist?)
  → citation check         (model_adapter: is this id in the pack? if not, REJECT — not repair)
  → entailment             (cascade E6→E3: does the claim follow from the span?)
  → currency               (currency + staleness: is the cited law still in force?)
  → provenance typing      (provenance_slots: what kind of value is this?)
  → human                  (approve() raises on MODEL_SUGGESTION or UNKNOWN)
```

Steps 4 and 6 are the ones no competitor found in this research performs.

## Failure modes, and what each costs

| Failure | Caught by | If it escapes |
|---|---|---|
| Invented citation | `model_adapter` id check | A fabricated authority in a filed document |
| Right section, wrong reading | `cascade` entailment | Plausible, unsupported legal advice |
| **Right section, superseded figure** | **`currency` + `staleness`** | **The ₹4 crore error — a wrong classification for a year** |
| A rule we never read | `staleness` invariant | Confident answers on law we do not hold |
| Unreadable document page | OCR confidence gate (role 13) | A half-read date entered as fact |

## What the orchestration evidence actually supports

Researched 2026-09-10. Three findings, and two of them argue *against* the
fashionable answer.

**1. Routing between models is a cost play, not an accuracy play.** Every router
with hard numbers targets *retaining* 90–95% of the strongest model's quality
more cheaply — RouteLLM (arXiv 2406.18665, ICLR 2025) gets >2x cost reduction at
90–95% of GPT-4 quality; Hybrid LLM (arXiv 2404.14618) cuts large-model calls up
to 40% with no quality drop. **Neither beats the best model on accuracy, by
design.** The one method that does exceed GPT-4 accuracy, FrugalGPT (arXiv
2305.05176, ~4% at equal cost), does it with a multi-call cascade and a scoring
function — a compound system, not a router.

So a multi-model router earns its place here only if cost becomes a constraint.
It is not a quality mechanism, and proposing one as though it were would be
building the wrong thing.

**2. Multi-agent decomposition has a serious negative literature.** This is not
folklore:

- **MAST** (arXiv 2503.13657) — 1,600+ annotated traces across 7 open-source
  multi-agent frameworks, 14 failure modes, inter-annotator κ=0.88. Its motivating
  finding: performance gains on popular benchmarks are **"often minimal"** against
  the complexity and cost added.
- **Beyond Consensus** (arXiv 2608.30373) — a **single judge beat multi-agent
  debate** on human alignment across six LLM judges; ablation isolates asymmetric
  role prompting introducing a downward bias that debate fails to correct.
- **More Capable, Less Cooperative** (arXiv 2604.07821) — capability does not
  predict cooperation: o3 reached **17%** of optimal collective performance where
  the weaker o3-mini reached **50%**.

The widely-circulated industry essay against multi-agent systems (Cognition,
"Don't Build Multi-Agents") is, by its own framing, **anecdotal with no
benchmarks** — the papers above are the real evidence, and they point the same way.

**3. Capability honesty is measurably bad, which is what justifies the gate.**
ToolEmu (arXiv 2309.15817): the safest agent tested still failed **23.9%** of the
time. Large Legal Fictions (arXiv 2401.01301): **58%** hallucination for GPT-4 and
**88%** for Llama 2 on verifiable questions, and models "cannot always predict when
they are producing legal hallucinations." Training for abstention helps but does
not solve it — +10.3pp precision (arXiv 2607.10738).

### What this means for the 20 roles above

It supports them, and it sharpens why only nine touch a model. The evidence points
to **a single strong model behind retrieval, verification and abstention**, over an
orchestrated swarm — unless decomposition is *measured* to help on our task, which
it has not been. Tier 0 is not a limitation we are working around; it is the
configuration the literature supports.

DSPy (arXiv 2310.03714) reports large gains (>25% and >65% over few-shot on the
authors' pipelines) but they are **self-reported on their own tasks and metrics**,
with no independent replication found. Promising; not something to build a
correctness-critical path on before validating against our own eval.

## Open architectural questions

- **Role 19 (query planner) is the riskiest addition.** A planner that decomposes
  a legal question is one step from a planner that decides which law applies.
  The boundary must be enforced in code, not convention.
- **Role 13's confidence gate has no threshold yet.** It cannot be set without the
  document corpus (see PLAN_05, the 20-document test).
- **The cascade is partially built.** E3→E6 exists; the trained head does not.
