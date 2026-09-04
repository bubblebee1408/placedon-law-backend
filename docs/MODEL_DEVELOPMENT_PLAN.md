# How Placedon develops its "model" — the technical approach

Written 2026-09-04, in answer to "how did Harvey build its model on top of OpenAI,
and how will we develop ours." It takes the Harvey and Legora architectures
seriously, keeps the parts that fit, and rejects the one part that would trade
away our only advantage. Competitor claims here are classified, not repeated:
per docs/COMPETITOR_PATTERN_ANALYSIS.md, LinkedIn / YouTube / Medium / Reddit are
**not citations** — they can make a claim PLAUSIBLE, never VERIFIED. Two sub-agents
are verifying the pasted claims against primary sources; §2's table is folded in
from that pass.

---

## 0. The decision this document exists to make

Harvey's reported build is: fine-tune an OpenAI base model on ~10B tokens of US
case law, wrap it in hybrid RAG, run 100+ agent calls per task, and enforce
citations by **programmatically parsing the output for a hyperlink**. Strip the
marketing and that is a *probabilistic* system with a *post-hoc* citation check:
the model generates, then a parser checks that a link is present.

Copying it would be a mistake for us, and not a small one. Our entire moat is that
**the model is not trusted — a deterministic verifier is.** "The model may propose.
The system must verify. The reviewer decides." A programmatic "is there a link?"
check is far weaker than "is this claim *entailed by* the cited span?", which is
what our E3→E6 cascade already computes. If we adopt Harvey's fine-tune-and-parse
core, we become a worse-funded Harvey for a smaller market, and we throw away the
one thing we do that they do not.

So the answer to "how do we develop the model" is: **we adopt their orchestration
and retrieval, and we replace their probabilistic guardrail with our deterministic
one.** The rest of this document is that sentence, made concrete.

---

## 1. Why the difference is forced, not a matter of taste

Harvey's approach is *correct for Harvey's problem* and wrong for ours, because the
two bodies of law are shaped differently:

| | US case law (Harvey) | Indian Companies Act (Placedon) |
|---|---|---|
| Size | Millions of judgments, ~10B+ tokens | One Act + rules + a few thousand judgments — orders of magnitude smaller |
| Shape | Reasoning-heavy, analogical, unstructured prose | A structured statute: sections, sub-sections, provisos, numbered limbs, dated thresholds |
| What "correct" means | A persuasive argument grounded in precedent | A decidable predicate: does this duty attach, is it met, on this date |
| What helps most | Fine-tune to imitate legal reasoning; RAG for facts | A **deterministic decider** over the statute's own structure; RAG for the current text |

Fine-tuning "how a litigator thinks" pays off when the task is open-ended
reasoning over a vast corpus. A compliance obligation is not that: "did this
private company hold an AGM within nine months of its first financial year-end" is
arithmetic on a date and a statutory limb, not a question of legal style. For
that, a fine-tune adds risk (a model that has *memorised* a threshold will recite
last year's number with confidence) where a verifier adds a guarantee. Even
Harvey's own account says fine-tuning must **not** teach case facts, because that
hallucinates — which is exactly the failure a small, precise statutory corpus
would invite if we fine-tuned knowledge into it.

---

## 2. The pasted research, classified (verification pass)

_Two sub-agents checked the claims you pasted against primary sources
(openai.com/index/harvey, harvey.ai/blog, legora.com/blog). Verdicts fold in here
on their return. Until then these are provisional, from primary pages fetched
2026-09-04 plus your pasted secondary sources._

**What is safe to treat as real (primary-sourced last turn):** model-agnostic
routing behind an abstraction layer; zero-data-retention as architecture; cost
routing to cheaper models where "good enough"; a multi-agent Playbook Review;
Legora's aOS layering, parallel sub-agents, source-anchored verification, and MCP
integrations.

**What stays PLAUSIBLE at best (secondary only — do not build a plan that depends
on the exact figure):** the "10B token" fine-tune size; "Voyage AI 20B token"
embeddings; "100+ model calls"; "Redis token-bucket" internals; "tens of thousands
of simultaneous calls." These are engineering *patterns* worth learning from, not
facts to cite to an investor.

**The load-bearing point survives either verdict:** whether Harvey fine-tuned on
10B tokens or 3B, its correctness guarantee is a probabilistic generate-then-check.
Ours is a deterministic verify-or-refuse. That contrast is the plan.

---

## 3. How we develop the model — six decisions

**3.1 No knowledge fine-tune. Ever.**
We will not fine-tune statute or case text into model weights. The corpus is small
enough that the model would memorise and then mis-recite, and a confidently wrong
threshold is the worst output this system can produce. This also aligns with
`CLAUDE.md` ("do not train a foundation model") and with Harvey's own caution that
fine-tuning must not carry facts.

**3.2 RAG over the statutory corpus is how current law enters — retrieval, not
weights.**
The current text of a section or a Gazette threshold lives in the corpus and is
*retrieved*, never baked in. This is also why RAG — not fine-tuning — is the
**currency mechanism**: when the law changes, we re-index, we do not re-train.
`checker/currency.py` already tracks which retrieved instrument each obligation
rests on.

**3.3 Structural chunking, not token-window chunking.**
Generic RAG splits text into 512-token blocks. The Companies Act has its own index
— section → sub-section → proviso → numbered limb — and we chunk on *that*. A
retrieval that returns "s.2(85)(i), the paid-up-capital limb, with its proviso"
beats one that returns "tokens 4096–4608." The law's structure is the embedding's
best feature and it is free. This is a concrete edge over a firm that chunks US
prose by length.

**3.4 Embeddings: off-the-shelf first; a narrow legal-embedding fine-tune is the
ONE defensible training, and it is optional.**
Start with a general embedding model. Later — only after a retrieval eval set
exists (3.6) — a narrow embedding fine-tune on Indian corporate-law language is
the single training we would consider (the honest analogue of Harvey's Voyage AI
legal embeddings), so that "default is a breach unless satisfied" retrieves the
right limb. Weeks, not months; optional; never on the critical path.

**3.5 The model proposes; the deterministic cascade disposes.**
Any model output that asserts a legal position must be **entailed by a retrieved
span** or it is marked NOT_ESTABLISHED. This is `checker/cascade.py` (E3→E6) and it
is categorically stronger than Harvey's "parse for a hyperlink": a link proves a
source was cited; entailment proves the claim *follows from* it. This is the moat,
and it is already built.

**3.6 Agentic decomposition = the obligation register.**
Legora spawns specialist sub-agents in parallel and stitches their output; we do
the same shape, but our specialists are mostly **deterministic deciders (₹0)**, not
LLM agents. The register already decomposes a company into per-obligation
sub-tasks; each runs its decider first and calls a model only for genuinely
ambiguous language. Same parallel-specialist pattern, a fraction of the cost, and
verifiable where theirs is not.

---

## 4. The pipeline, concretely (RAG + verify + agentic)

```
intake (company facts)
   │
   ├─ obligation register decomposes into per-duty sub-tasks   [obligations.py]
   │
   ▼  for each obligation:
   1. RETRIEVE  structural chunks for the governing provision   [retrieve.py + structural chunker]
   2. DECIDE    run the deterministic decider on the facts       [obligations deciders]  ← most rows end here, no model
   3. PROPOSE   model called ONLY for residual ambiguous language (Tier 1/2)
   4. VERIFY    the proposal must be entailed by the retrieved span, or NOT_ESTABLISHED  [cascade.py]
   5. GROUND    attach the span + Gazette instrument
   │
   ▼
   STITCH into the pre-diligence pack, breaches first            [diligence_pack.py]
   CURRENCY flag any obligation resting on unacquired/stale law  [currency.py]
```

Steps 1 and 4 are where we differ from Harvey/Legora: retrieval indexes the
statute's *structure*, and verification is *entailment*, not a link-presence check.

---

## 5. What training we will and will not do

| Kind of "training" | Verdict | Why |
|---|---|---|
| Foundation model from scratch | **Never** | `CLAUDE.md`; none of Harvey/Legora/Spellbook do it either |
| Knowledge fine-tune (statute/cases → weights) | **Never** | small corpus → memorise-and-misrecite; the worst failure mode |
| Format/style fine-tune | **Maybe, far later** | only with a lawyer-validated eval harness and a real reason; low priority |
| Embedding fine-tune (retrieval quality) | **The one defensible narrow train** | optional; only after a retrieval eval set; the Voyage analogue |
| RAG index build + refresh | **Yes — this is the real "model work"** | how current law enters; the currency mechanism |
| Deterministic verifier + deciders | **Yes — the moat** | already built and green |

The honest headline: **most of our "model development" is not model training at
all.** It is corpus curation, structural retrieval, and deterministic verification.
That is cheaper, more defensible, and it is the axis the market's own currency
features (Legora Monitors, Harvey Horizon Scanning) validate.

---

## 6. Build order

1. **Retrieval eval set** — a set of (question → correct statutory span) pairs. You
   cannot improve retrieval you cannot measure. This needs a lawyer to confirm
   "correct span" — the same H-001 dependency, and a good reason for that review.
2. **Structural chunker** over the corpus (section/sub-section/proviso/limb).
3. **Wire retrieve → decider → E-gate** on the extraction tier so a model proposal
   is verified against the retrieved span before it can appear.
4. **Measure retrieval**; only then consider an embedding fine-tune (3.4).
5. **Never** open a knowledge fine-tune.

---

## 7. Honest risks

- **Retrieval on a small corpus** can be brittle; the structural chunker mitigates
  it but the eval set is what proves it.
- **The eval set's "correct span" needs a practitioner** — we cannot self-certify
  it, which is the same reason H-001 matters and is not a detour around it.
- **Model-proposer scope creep**: the deterministic floor must keep carrying most
  rows. Every time we let the model decide where a decider could, we import the
  probabilistic risk we are trying to avoid.

---

## 8. Sources and classification

Primary (fetched 2026-09-04): harvey.ai/blog, legora.com, spellbook.com — see
docs/TECHNICAL_PLAN_EVIDENCED_2026_09.md §1. Secondary (your pasted material):
LinkedIn, YouTube, Medium, Reddit, newsletter and third-party blogs — classified
PLAUSIBLE at best and never load-bearing. The two verification sub-agents' verdicts
are folded into §2 on their return; where a claim cannot be raised above PLAUSIBLE,
this plan does not depend on it.
