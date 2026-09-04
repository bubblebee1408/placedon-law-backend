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

Harvey's build, now confirmed from primary sources (OpenAI's own Harvey page and
harvey.ai/blog): a **custom-trained case-law model** — OpenAI states they "added
the equivalent of 10 billion tokens" of US case law into it — plus a **custom legal
embedding model** (voyage-law-2-harvey, 20B+ legal tokens), hybrid RAG, and
multi-agent orchestration ("dozens" of subagents in parallel) with **structural
citation anchoring** (each document element gets a unique id so an agent cites it
unambiguously). Strip the marketing and the correctness guarantee is, precisely,
*"grounded, not guaranteed"*: the substantive answer is a probabilistic LLM output
made auditable by deterministic *references*, not a deterministic proof that the
answer is correct. **No primary source — Harvey's or Legora's — claims
deterministic correctness.**

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
| What helps most | Custom-train case-law content in + RAG + custom legal embeddings | A **deterministic decider** over the statute's own structure; RAG for the current text |

This is a **deliberate divergence** from Harvey, not agreement with it. Harvey did
train case-law content into its model (10B tokens, primary-verified) and accepts a
"grounded, not guaranteed" answer. We choose the opposite for three corpus-specific
reasons, none of which applied to Harvey: (a) the 10B-token corpus that makes
custom-training pay off **does not exist** for the Companies Act — it is one Act
plus rules; (b) a compliance obligation is a *decidable predicate* ("did this
company hold an AGM within nine months of its first financial year-end" is
arithmetic on a date and a limb), so a verifier can give a real guarantee where
Harvey's analogical case-law reasoning cannot; (c) memorising a *dated* threshold
that later changes by amendment is the single worst failure this system can have —
a model that has learned "₹4 crore" in its weights keeps reciting it after the
Gazette moves. Harvey could afford scale-and-ground because its problem is not
decidable; we can afford deterministic-verify because ours largely is.

---

## 2. The pasted research, classified (primary-source verification)

Two sub-agents checked your pasted claims against **primary** sources only
(openai.com/index/harvey via its verbatim archived copy — the live page 403s bots
— and live harvey.ai/blog and legora.com pages). Secondary sources could only make
a claim PLAUSIBLE, never VERIFIED.

### Harvey (verdicts)

| Claim | Verdict | Note (primary source) |
|---|---|---|
| Custom-trained case-law model, "10 billion tokens" added | **VERIFIED** | openai.com/index/harvey. Caveat: **case law**, not statutes/filings; a *custom-trained* model, not naive API fine-tune |
| Fine-tune teaches reasoning/format, NOT facts | **UNSUPPORTED / contradicted** | OpenAI page says they added case-law *content* precisely because retrieval alone was insufficient |
| Partnered with OpenAI on a custom-trained model | **VERIFIED** | openai.com/index/harvey |
| Hybrid fine-tune + RAG | **VERIFIED** | openai.com + harvey.ai voyage post |
| Voyage AI embeddings, 20B+ legal tokens (voyage-law-2-harvey) | **VERIFIED** | harvey.ai/blog/harvey-partners-with-voyage… |
| Multi-model routing (GPT/Claude/Gemini) + fallback | **VERIFIED** (rate-limiting internals unconfirmed) | harvey.ai/blog/why-harvey-is-multi-model-by-design |
| Zero-data-retention; no training on client data | **VERIFIED** ("secure enclaves" wording unconfirmed) | why-we-built-our-own-cloud-agent-infrastructure; security-by-design |
| OpenAI Agent SDK + "Tool Bundles" (LexisNexis, SEC EDGAR) | **UNSUPPORTED** | they built their **own** harness; LexisNexis exists as an integration, not a "tool bundle" |
| 100+ model calls per task | **PLAUSIBLE** | primary says "dozens" of subagents in parallel, not "100+" |
| Citations enforced by parsing for a hyperlink | **PLAUSIBLE** | real mechanism is structural: each document element gets a unique id, edits tracked on a versioned branch tagged to the rule |
| "Vault" + iManage/SharePoint/NetDocuments | **VERIFIED** (loose paraphrase) | iManage/NetDocuments integrations confirmed; Vault is a distinct feature |

### Legora (verdicts)

| Claim | Verdict | Note (primary source) |
|---|---|---|
| aOS = 7-layer stack | **VERIFIED** | legora.com/product/aos |
| Multi-phase plan → parallel specialist sub-agents | **VERIFIED** | legora.com/blog/introducing-the-agent |
| Sub-agents pause for human oversight | **VERIFIED** | introducing-the-agent |
| Model-agnostic hot-swap Claude/GPT per task | **PLAUSIBLE** | "model selection" in harness; specific Claude/GPT swap not named |
| MCP to DMS as system of record | **VERIFIED** (MCP + NetDocuments); iManage/SharePoint not named | legora.com/product/agent |
| RAG over firm playbooks/precedents | **VERIFIED** | legora.com/product/aos |
| Per-clause enforced source-anchoring | **PLAUSIBLE / over-read** | primary says output-level *traceability* + "structured citations", **not** a described per-claim deterministic check |
| Zero training on client data; SOC2/ISO/GDPR/HIPAA | **VERIFIED** | legora.com/security |
| Tens of thousands of simultaneous calls | **UNSUPPORTED** | no quantitative figure in any primary source |
| Locked-box containers, wiped, regional residency | **UNSUPPORTED** | not stated in primary sources |

### The one finding that anchors the plan

From the Harvey verification, verbatim: Harvey's correctness guarantee is
*"probabilistic generation wrapped in deterministic grounding and anchoring — not
a deterministic correctness proof… the answer's substantive correctness remains a
probabilistic LLM output that is grounded, not formally guaranteed — no primary
source claims deterministic correctness."* Legora's own materials describe grounding
as **traceability + structured citations**, verification method unstated — the
strong "enforced per-clause verification" reading is not supported by their pages.

**So neither funded leader has a deterministic entailment verifier.** Both make the
answer *auditable*; neither makes it *guaranteed*. Placedon's E3→E6 cascade — the
claim must be entailed by the cited span or it is NOT_ESTABLISHED — is the guarantee
that sits precisely in that gap. This is now confirmed from their own primary
sources, not inferred.

## 3. How we develop the model — six decisions

**3.1 No knowledge fine-tune. Ever.**
We will not fine-tune statute or case text into model weights. The corpus is small
enough that the model would memorise and then mis-recite, and a confidently wrong
threshold is the worst output this system can produce. This aligns with
`CLAUDE.md` ("do not train a foundation model"). Note it is a *divergence* from
Harvey, which did train case law in — see §1 for why the corpus forces the
different choice.

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

> **Update 2026-09-04 — measured before adding any dependency.** The disciplined
> first step ran before embeddings: a zero-dependency BM25 ranker
> (`checker/lexical_rank.py`). It moved retrieval precision@1 from **0.20 (naive
> term-overlap) to 0.60** on the eval set, with no package and no network. The two
> residual misses are genuinely semantic — a question about the small-company
> *capital limit* retrieves the *definition* of paid-up capital (2(68)) over the
> 2(85)(i) limb; "first AGM" is indistinguishable from the other s.96 provisos by
> words alone. So the embedding dependency is now justified by a **specific,
> measured gap**, not a vague one — but it remains gated on TWO things and neither
> is mine to decide alone: (a) a dependency governance decision (torch/sentence-
> transformers or a paid embedding API, against "no new dependency without a
> stated reason"), and (b) enough eval cases to measure honestly — 0.60 on five
> cases is a weak signal, and the semantically-hard cases need the H-B lawyer
> labels to expand the set without overfitting. Tuning further against five cases
> would be fooling ourselves, so autonomous retrieval work correctly stops here.
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
