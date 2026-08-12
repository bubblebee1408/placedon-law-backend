# Technical plan — the model, the AI, and what to actually build

Written 2026-08-12, after analysing `PLACEDON_TECHNICAL_EXECUTION_PLAYBOOK` and
`PLACEDON_AI_MODEL_ARCHITECTURE_BLUEPRINT`.

Read `docs/00_RELAUNCH_PLAN.html` in `placedon-law-research` first. That decides *what* to build.
This decides *how*, and mostly it decides what not to.

---

## 0. The finding

**Both documents are plans to build, from scratch, a worse version of what is already running.**

They are competent documents. The RAG explanation is clear, the embedding analogy is good, the
20-step checklist is sequenced sensibly. But they describe an architecture this project rejected
for a specific reason, and following them would undo that decision.

### The inversion

| | Blueprint | This repository |
|---|---|---|
| Who decides what the law requires | The LLM, from retrieved context | `applicability.py`, deterministically |
| What the LLM does | Generates the answer | Explains a decision already made |
| Hallucination control | Guards downstream — citation validator, "hallucination guard", confidence scorer | The model is never asked a question it could fabricate an answer to |
| Failure mode | A wrong obligation, stated fluently, with a plausible citation | Abstention |
| Target accuracy | ">85%" | The number of unsourced claims is zero, by construction |

The blueprint's Layer 3 is *"Retrieved Context + Question → Groq API"* and Layer 4 is a set of
filters trying to catch what Layer 3 produced. That is the standard design. It is also the design
that fails, and we now have the evidence.

---

## 1. What the research says about the blueprint's architecture

### The one study that settles it

**Magesh et al., *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research
Tools*** — Stanford RegLab / HAI, preregistered, 202 queries, expert-scored, peer-reviewed in the
*Journal of Empirical Legal Studies* (2025). [arXiv:2405.20362](https://arxiv.org/pdf/2405.20362) ·
[RegLab](https://reglab.stanford.edu/publications/hallucination-free-assessing-the-reliability-of-leading-ai-legal-research-tools/)

| System | Hallucination rate |
|---|---|
| Lexis+ AI | **>17%** |
| Westlaw AI-Assisted Research | **~33%** |
| GPT-4 (baseline) | 43% |

Read that table against the blueprint. Lexis and Westlaw are *exactly* the blueprint's
architecture — retrieval over a proprietary legal corpus, an LLM generating the answer, guardrails
and citations bolted on — built by companies with thousands of engineers and decades of licensed
content. **They land at 17–33%.**

The blueprint's target is ">85% accuracy". That is a **15% error rate on statements of law**,
and it is stated as a success condition. On a compliance product, one in seven wrong is not a
passing grade; it is the product's core failure mode shipped as a KPI.

### The rest of the literature agrees

- Citation hallucination in deployed systems runs **11–57%**, and agent-produced citations
  frequently cannot be verified at all —
  [*Cited but Not Verified*](https://arxiv.org/html/2605.06635v1).
- [*Attribution, Citation, and Quotation: A Survey of Evidence-based Text Generation*](https://arxiv.org/pdf/2508.15396)
  (AAAI'25) separates three things the blueprint conflates: **attribution** (a pointer),
  **citation** (a formatted reference), and **quotation** (verbatim text). Only the third is
  checkable by machine. This repository already chose quotation — `verifier.py` rejects any figure
  or citation absent from the retrieved source text.
- [*Verifiable Generation with Subsentence-Level Fine-Grained Citations*](https://arxiv.org/pdf/2406.06125)
  is the direction to move toward when the LLM path is switched on: bind claims to spans, not
  documents.
- The abstention literature — e.g. [*Aspect-Based Causal Abstention*](https://arxiv.org/pdf/2511.17170),
  [TIAR](https://arxiv.org/pdf/2605.25850) — treats refusal as a **calibrated capability to be
  measured**, not an error state. Our epistemic lattice is a crude, deterministic version of the
  same idea, and crude-and-deterministic is the correct starting point.

**Conclusion: the architecture in this repository is the one the evidence supports. Do not
replace it. The plan below extends it.**

---

## 2. Concrete errors in the two documents

Verified, not asserted:

| Where | Claim | Reality |
|---|---|---|
| Setup, step 2 | `npm install -g @anthropics/claude-code` | **404, package does not exist.** It is `@anthropic-ai/claude-code` (current 2.1.228). The playbook fails on its second command. |
| Setup, step 3 | `claude auth login` | Not a command. Auth is `/login` inside the CLI, or `claude setup-token`. |
| Setup, step 9 | `/claude set model claude-3-7-sonnet-20250219` | Not a Claude Code command, and that model is two generations stale. |
| Prompt **P5** | "ICC External Member (**Rule 5**)" | Rule 5 is *Fees or allowances for Chairperson and Members of **Local** Committee*. The requirement is **s.4(2)(c)**; the Internal Committee member's allowance is **Rule 3**. Running P5 bakes a wrong citation into generated source. |
| Prompt **P5** | "Policy Display (Section 19a)" | Display is **s.19(b)**. 19(a) is providing a safe working environment. |
| Prompt **P5** | 10 checks incl. "Annual Report" | Rule 14 lists **five** items and prescribes **no date**. |
| Blueprint, Week 1 | Install `chromadb` + `sentence-transformers`, index the Act | `checker/retrieval.py` documents why this was rejected: **30 sections**. Loading torch to rank thirty paragraphs costs ~2 GB of dependencies and seconds of cold start to beat a scan measured at 0.05 ms. Revisit at ~500 sections, i.e. when the labour codes land. |
| Budget | "Claude Code Pro ₹2,400/month… Groq API buffer ₹500" | Introduces two paid API dependencies. Current inference spend, all time: **₹0.00**. `requirements.txt` has no `groq` and no `google-generativeai`, deliberately. |
| Blueprint | "Harvey uses OpenAI GPT-4 + proprietary RAG + human-in-the-loop" | Unverified. Do not repeat it to an investor. |
| Blueprint | "Self-RAG reduces hallucination by 40%" | Unverified as stated; the paper's gains are task- and metric-specific. |

**The P5 problem is the serious one.** These prompts are designed to be pasted into a code
generator. A wrong citation inside a prompt becomes a wrong citation inside `posh_playbook.py`,
which becomes a wrong citation on a document a company signs. That is the exact chain this
repository's `verifier.py` exists to break — and it would be broken by the tooling, upstream of
the verifier, where nothing is watching.

---

## 3. What we keep

Nothing in this plan changes these. They are load-bearing.

```
applicability.py        deterministic. The LLM is never in the decision path.
checker/verifier.py     rejects any citation or figure absent from source text.
checker/epistemic_status.py   ordinal lattice, weakest-link composition, no floats.
checker/retrieval.py    keyword route then scan. No vector search until ~500 sections.
corpus/                 30 PoSH sections, primary, byte-verified against India Code.
scripts/verify.py       31 checks across two repos, each with because=.
verified_by             null on all 30. The product abstains. This is the designed state.
```

---

## 4. The plan

Four phases. Phase 1 is the product decision from the relaunch plan; phases 2–4 are conditional on
gates that are not ours to open.

### Phase 1 — The register (this week, no LLM, no new dependencies)

The relaunch research found the one asset nobody has: **every competitor tells the customer to go
and ask their own District Officer for the notified annual-return date, and nobody has asked.** We
hold all 31 Karnataka District Officers by name and email, from MWCD's own SHe-Box directory.

Build:

```
corpus/reference/notified_dates.json     district → {date | "none notified" | "no reply"},
                                          asked_on, replied_on, verbatim reply, source
scripts/ask_district_officers.py         renders 31 letters from one template. Does NOT send.
scripts/ingest_reply.py                  records a reply, refuses to record a date without
                                          the text it came from
checker/jurisdiction.py                  already resolves district → state → national; wire
                                          notified_dates in as the district layer
```

Three rules, each enforced by a check in `verify.py`:

1. **A date without an attached reply is not recordable.** Same rule as `verified_by`.
2. **"No reply after N days" is a publishable value**, not a gap. The register's credibility comes
   from publishing non-answers.
3. **The national layer stays empty.** There is no national date. If someone adds one, verify
   fails.

Deliverable: `ask_engine` stops returning bare `UNCHECKED` for Bengaluru Urban and starts returning
a date with the District Officer's own words attached — or `UNCHECKED, asked on <date>, no reply`.
Both are better than every competitor, and the second one is the more differentiating.

### Phase 2 — Switch on the LLM path (only after a lawyer verifies)

`backend/services/llm.py` exists, `anthropic==0.89.0` is pinned, and the path has never executed
against a real model. It stays dark until `verified_by` is non-null, because a fluent explanation
of an unverified reading is the worst output this product could produce.

When it opens:

- **Use the Citations API, not free-text citations.** Anthropic's Citations returns structured
  references with **character-level provenance** into the source document. That converts our
  post-hoc `verifier.py` check from "does this string appear?" into "the API tells us the span."
  It is the closest available thing to the sub-sentence-level attribution the research points at.
- **Keep `verifier.py` anyway.** Belt and braces: the API's provenance is checked against our own
  corpus, not trusted.
- **Model choice is a cost lever, not a correctness lever** — because applicability already
  decided. Measured: ₹0.97/answer. Cap already enforced in `backend/budget.py`.
- **The explanation may not introduce a proposition.** It may only restate, in plainer words, a
  decision `applicability.py` made and a provision the corpus holds. Add a verify check for this.

### Phase 3 — Measure, with a real evaluation set

The blueprint says "golden test set, 20 Q&A pairs, target >85%". Both numbers are wrong. Twenty
pairs cannot distinguish 85% from 95%, and 85% is not a target on legal claims.

Build instead:

```
tests/golden/                 questions with a lawyer-verified expected disposition
                              — ANSWER (with the governing provision) or ABSTAIN (with why)
scripts/evaluate.py           reports three numbers, not one accuracy figure
```

The three numbers:

| Metric | Target | Why |
|---|---|---|
| **Fabrication rate** — claims not present in source | **0.** Not "low". | This is the one that ends the company. Stanford measured 17–33% for systems built to do exactly this. |
| **Coverage** — questions answered rather than abstained | rises as `verified_by` fills | Today it is 0% by design. It is a *gate*, not a bug. |
| **Wrong abstention** — abstained when the corpus did support an answer | should fall | This is the real cost of our design, and nobody currently measures it. |

Report all three. A single "accuracy" number hides the trade-off that *is* the product.

### Phase 4 — Corpus, not models (months, not weeks)

The blueprint's Month 3–6 is LoRA fine-tuning. Skip it. There is no training set, no labelled data,
and no problem it solves that the corpus does not solve better and for nothing.

What actually compounds:

1. Gazette text for the four MCA provisions, replacing the `ibclaw.in` reproduction.
2. Companies Act s.96 — we do not hold it, so we cannot state the Board's Report timing.
3. Gazette text for the PoSH Rules — currently `secondary_reproduction_cross_verified`, which is
   why the "no date is prescribed" finding is only as strong as that reproduction.
4. The other 30 states' District Officers, once Karnataka proves the register works.

Vector search becomes correct somewhere in here — around 500 sections. Not before.

---

## 5. Where sub-agents fit, and where they do not

Sub-agents are useful for **bounded, verifiable, parallel** work. They are dangerous for anything
that writes a legal claim, because a sub-agent's output arrives as fluent prose with no provenance —
the same failure mode as the LLM path, one level up.

**Use them for:**

| Agent | Job | Verification |
|---|---|---|
| `python-reviewer` | Review the register ingestion for the "date without a reply" hole | `verify.py` check must fail on a hand-crafted bad record |
| `security-reviewer` | The register accepts external email content — injection and PII review | Adversarial cases in `tests/` |
| `code-explorer` | Map every call site of `jurisdiction.py` before the district layer is wired in | A list of files, checkable by grep |
| `tdd-guide` | Golden-set harness, tests first | Tests must fail before implementation exists |
| `docs-lookup` | Anthropic Citations API exact bindings for Phase 2 | Code must compile and run |

**Never use them for:** reading a provision, deciding what a section requires, writing a citation,
or filling a field in `notified_dates.json`. Those come from primary text or from a named human,
and from nowhere else. This is the same rule as `verified_by`, applied to our own tooling.

---

## 6. The loop

Per iteration, in order. Stop at the first failure.

```
1. PICK      one task from Phase 1. One file.
2. TEST      write the failing test, or the verify.py check, first.
3. BUILD     implement the smallest thing that passes.
4. VERIFY    python3 scripts/verify.py     ->  must be GO
5. PROVE     for anything touching the corpus:
             python3 scripts/check_transcription.py   ->  30/30
6. RATCHET   if a bug escaped, add a check with because= naming the incident.
7. COMMIT    the message explains why, not what.
```

The ratchet is the part that matters. Every check in `verify.py` exists because something got
through once. Adding one costs a few lines; removing one costs the bug coming back.

---

## 7. What to say when someone asks about the AI

Not "we use RAG with Groq and ChromaDB." That describes the architecture that hallucinates 17–33%
of the time in the hands of Thomson Reuters.

> "The model never decides what the law requires — a deterministic engine does, from the employer's
> own answers. The model's only job is to explain a decision that has already been made, and a
> verifier rejects any number or citation that isn't in the source text. When we can't source an
> answer, the product says so and names what's missing. That's why our inference spend is zero and
> our fabrication rate is zero: we didn't filter the hallucinations out, we removed the step that
> produces them."

That is checkable in front of the person asking, which is the only kind of technical claim worth
making about this product.

---

## Appendix — reading list, in order of usefulness to us

| # | Paper | Why |
|---|---|---|
| 1 | [Magesh et al., *Hallucination-Free?*](https://arxiv.org/pdf/2405.20362) (Stanford RegLab, JELS 2025) | The empirical case for our architecture. Read it first, twice. |
| 2 | [*Attribution, Citation, and Quotation*](https://arxiv.org/pdf/2508.15396) (AAAI'25 survey) | Names the distinction our verifier already implements. |
| 3 | [*Verifiable Generation with Subsentence-Level Fine-Grained Citations*](https://arxiv.org/pdf/2406.06125) | The Phase 2 target. |
| 4 | [*Cited but Not Verified*](https://arxiv.org/html/2605.06635v1) | Why "it produced a citation" proves nothing. |
| 5 | [*Aspect-Based Causal Abstention*](https://arxiv.org/pdf/2511.17170) | Abstention as a measurable capability. |
| 6 | Lewis et al., *RAG* (2020) | Foundational. Read to know what we are *not* doing and why. |

### Added 2026-08-12 — the convergence

Searching for Indian legal NLP work turned up something worth recording carefully.

**[Falkor-IRAC: Graph-Constrained Generation for Verified Legal Reasoning in Indian Judicial AI](https://arxiv.org/abs/2605.14665)**
(arXiv 2605.14665, May 2026) independently arrives at this repository's architecture. Its claims,
against ours:

| Falkor-IRAC | Here |
|---|---|
| Answers accepted only if a valid supporting path traces through a knowledge graph | `provision_graph.py` — `blocked_by()` over the statute's own cross-references |
| A *"falsifiability oracle"* Verifier Agent that rejects fabricated citations | `verifier.py` — rejects any citation or figure absent from source |
| Graph-native metrics: citation grounding accuracy, **path validity rate**, hallucinated precedent rate | the three numbers in Phase 3 |
| Explicitly positions **against vector RAG for law** | `retrieval.py` — keyword route then scan, no vectors |

We did not read this paper before building. That is worth more than agreement would be: two
independent attempts at grounded Indian legal AI converged on graph-constrained generation with an
external falsifiability check, and both rejected the vector-RAG pipeline every planning document in
this project has proposed.

**What to actually take from it**, since agreement is not a reason to change anything:

1. **Path validity rate** as a metric. We measure whether a claim is *sourced*; they measure
   whether a *reasoning path* is traceable end to end. Ours is the weaker check. Add it to Phase 3.
2. **Conflict detection rate.** They detect provisions that contradict each other. Our lattice
   composes weakest-link but does not flag conflict. A real gap.
3. The companion note, *Why Vector RAG Fails in Law*, is the citable answer to "why not ChromaDB?"

Also worth reading:

| Paper | Why |
|---|---|
| [Citation Grounding via Legal Citation Graphs](https://arxiv.org/pdf/2606.00898) | Detecting and reducing citation hallucination using the citation graph. Directly extends `provision_graph.py`. |
| [IL-TUR](https://aclanthology.org/2024.acl-long.618/) (ACL 2024) | Indian Legal Text Understanding and Reasoning benchmark — English, Hindi, 9 Indian languages. **The evaluation set we do not have.** Phase 3 should measure against it before inventing our own. |
| [Domain-Partitioned Hybrid RAG for Legal Reasoning in India](https://arxiv.org/pdf/2602.23371) | Modular, explainable, India-specific. Read before any retrieval change. |

**The correction this makes to our own plan:** Phase 3 says build a golden set from scratch with a
lawyer. IL-TUR exists, is peer-reviewed, and is Indian. Measure against it first — a lawyer's
evening is the scarcest resource here and should be spent on the six load-bearing clauses, not on
re-deriving a benchmark that a research group already published.

Not on this list: LoRA, Self-RAG, fine-tuning of any kind. They solve problems we do not have with
resources we do not have, and the corpus solves the problem we do have for nothing.
