# Which model provider, and why

Written 2026-08-12, answering the Groq-vs-alternatives analysis.

Its conclusion — *"Groq primary, Gemini fallback, don't pay for Anthropic until you have
revenue"* — rests on three claims. Two are wrong, and one is right in a way that changes the
recommendation rather than supporting it.

Every number below is measured or sourced. Reproduce the arithmetic with
`python3 -c` against `backend/budget.py`.

---

## 1. The Gemini recommendation targets a model that no longer exists

> *"Gemini 1.5 Flash — 1 million token context. Promote it to primary for long judgments."*

**Gemini 1.5 is shut down.** All Gemini 1.0 and 1.5 models return **404**
([Google deprecations](https://ai.google.dev/gemini-api/docs/deprecations)). The free tier as of
2026 is Flash and Flash-Lite only; **Pro-series lost its free tier in April 2026**.

This is the same error class as two earlier documents in this project naming
`claude-3-5-sonnet-20241022` (retired 2025-10-28) and `@anthropics/claude-code` (404, wrong scope).
Model and package identifiers rot faster than architecture advice, and a plan that names one
without checking it fails on first run.

The reason to promote Gemini was 1M context for **full judgments**. We hold **zero judgments**.
The argument is for a capability we have no corpus to exercise, using a model that is gone.

---

## 2. The Groq free tier does not have the headroom claimed

> *"14,400 requests/day = ~600 analyses per hour. Enough for 100 beta users."*

That is the requests-per-day limit. The binding limit is **tokens per minute**, and the free tier
is **6,000 TPM** ([Groq free tier, 2026](https://tokenmix.ai/blog/groq-free-tier-limits-2026)).

Measured on this workload — `backend/services/llm.py`, 6,700 input + 700 output:

```
tokens per answer               7,400
free-tier tokens per minute     6,000
-> ONE ANSWER DOES NOT FIT IN ONE MINUTE'S BUDGET

answers per minute              0.81
answers per day (TPM-bound)     1,168
advertised ceiling              14,400 req/day
-> RPD is unreachable. TPM binds first, by 12x.
```

A single legal answer here carries three whole statutory sections as context. That is not a
tunable — whole sections are the architecture, because chunking destroys the verbatim quotability
`verifier.py` depends on. **Our context size is a consequence of the correctness design, and it is
what makes the free tier's headline number unreachable.**

1,168/day is still a real number and more than enough for beta. But the plan's "600 analyses per
hour" is off by roughly 50×, and any capacity planning built on it is wrong.

---

## 3. The cost comparison is off by 10×

> *"With ₹5,000 you get maybe 500 calls on Claude vs 14,400/day free on Groq."*

Measured, `backend.budget.cost_inr("claude-haiku-4-5", 6700, 700)`:

```
Rs 0.9713 per answer
Rs 5,000 buys 5,147 answers      <- not 500
monthly cap Rs 3,500 -> 3,603 answers/month
```

The comparison also silently swaps model tiers. It prices **Claude Opus 4.8** ($1–$25/1M) against
**Llama on Groq**. We route to **Haiku 4.5**, and we can do that safely for a reason specific to
this architecture: `applicability.py` decides what the law requires and `verifier.py` rejects any
figure absent from source, so **model choice is a cost lever, not a correctness lever**. Comparing
a frontier model's price to a small model's free tier answers a question nobody asked.

---

## 4. What the analysis gets right, and it is the important part

> *"You don't need the smartest model. You need obedience, not creativity."*

Correct, and it is the same conclusion this repository reached from the other direction. The
context is pre-retrieved and pre-gated; the model's only job is to restate a decision already made,
in plainer words, without introducing a proposition. An 8B model at low temperature would do it.

Which is exactly why **cost is not the deciding factor** — at 3,603 answers/month inside an already
enforced cap, the spend is bounded and small. The deciding factor is something the analysis never
mentions.

---

## 5. The thing that decides it: Citations

`anthropic==0.89.0`, already pinned, exposes `CitationCharLocation`,
`CitationContentBlockLocation`, `CitationPageLocation`. Anthropic's Citations returns
**character-level provenance into the source documents you supply**.

That converts `verifier.py` from *"does this string appear in the source?"* to *"the API reports
the exact span this claim came from."* It is the sub-sentence-level attribution the research points
at ([Verifiable Generation with Subsentence-Level Fine-Grained Citations](https://arxiv.org/pdf/2406.06125)),
and it is the single most architecturally relevant feature available to a system whose entire
premise is that every claim traces to source text.

**Groq and Llama have no equivalent.** Neither does Gemini. Choosing Groq to save ₹0.97 per answer
costs the mechanism that makes the product defensible.

### Correction, 2026-08-15 — finer is not better

The paragraph above argues for Citations *because* the attribution is sub-sentence. **That part of
the reasoning is now contradicted by newer evidence and is withdrawn.**

[Are Finer Citations Always Better? Rethinking Granularity for Attributed Generation](https://arxiv.org/abs/2604.01432)
(Wang, Zhang, Van Durme, Khashabi, April 2026) measures the opposite: enforcing fine-grained
citations **degrades attribution quality by 16–276%** against the best granularity, and
**paragraph-level is the peak, not sentence-level**. Larger models are penalised *more*, because
fine constraints fracture the semantic dependencies they use to compose an answer. Humans prefer
finer citations; models attribute worse under them, which is a trap for anyone designing from
intuition.

**The decision does not change; the reason does.** Citations remains the right feature — it supplies
machine-checkable provenance rather than a claim about provenance, and that is the property
`verifier.py` needs. But we cite at **provision level**, which for this corpus is the natural unit
anyway, and the precision requirement is met by the **deterministic engine**, not by slicing
citations finer.

The general lesson is the one already in §7: this project keeps finding that a plausible design
instinct is wrong when someone measures it. That was true of the confidence float, of embeddings
against keyword retrieval, and now of citation granularity.

---

## 6. Decision

| | Choice | Why |
|---|---|---|
| Primary | **Anthropic Haiku 4.5**, as already wired | Citations; ₹0.97/answer; cap enforced pre-flight in `backend/budget.py` |
| Local / dev | **Ollama**, already implemented | ₹0, no network, no key. Used for every non-production run. |
| Groq / Gemini | **Not added** | No Citations. Two new dependencies and two accounts for a path that is dark until Gate 1. |
| Router by context length | **Not built** | It exists to route long judgments to a 1M-context model. We hold no judgments, and that model is retired. |

**Revisit when** either of these becomes true, and not before:

1. A judgment corpus exists and a single query genuinely exceeds Haiku's context.
2. Measured spend approaches the ₹3,500 cap with real users — at which point the comparison is
   Haiku against Groq *with* a Citations substitute built by hand, and that substitute's cost goes
   in the comparison.

---

## 7. The general lesson, which is worth more than this decision

Three provider recommendations have now been made to this project. Each named a specific model or
package. **Each named one that was retired or nonexistent**:

| Named | Reality |
|---|---|
| `claude-3-5-sonnet-20241022` | retired 2025-10-28, returns 404 |
| `@anthropics/claude-code` | 404 — the package is `@anthropic-ai/claude-code` |
| `gemini-1.5-flash` | shut down; all 1.0 and 1.5 models return 404 |

Architecture advice ages in years. Identifiers age in months. **Any plan naming a model, package
or endpoint should be checked against the registry before a line is written** — it costs one
command and it is the cheapest verification available anywhere in this project.
