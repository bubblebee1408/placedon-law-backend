# Why the lattice, and not RAG

Every planning document written for this product proposes the same four layers: parse, embed and
retrieve, generate, then check the output. It is the standard design, it is what Lexis+ AI and
Westlaw are, and it is what this repository does not do.

This file explains why, using the measurements rather than the argument. Reproduce any of them:

```
python3 scripts/bench_architectures.py    # naive RAG vs the lattice, five questions
python3 scripts/bench_safety.py           # both safety designs vs real fabrications
python3 scripts/bench_retrieval.py        # keyword+scan vs embeddings
python3 scripts/bench_answers.py          # fabrication, coverage, wrong abstention
```

---

## 1. The measurement that decides it

Same corpus, same five questions, same model stub — a stub that **copies source text and therefore
cannot fabricate**. Every difference below is the architecture, not the model.

| Question | Naive RAG | Lattice |
|---|---|---|
| Penalty for non-compliance? | **answered**, 69.4% conf., no flags | abstained — 3 paths, 1 conflict |
| Time limit to complain? | **answered**, 70.7% conf., no flags | abstained — 5 paths, 2 conflicts |
| When is the annual return due? | **answered**, 37.2% conf., no flags | abstained (UNCHECKED) |
| IC needed with 8 employees? | **answered**, 51.5% conf., no flags | abstained (UNSUPPORTED) |
| **GST rate on legal services?** | **answered**, 29.4% conf., no flags | abstained |

**Naive answered 5 of 5. The lattice answered 0 of 5.**

Neither produced a false sentence, because the stub cannot. The entire difference is in what each
refuses — and on a compliance product that is the only difference that matters.

### The last row is the whole argument

*"What is the GST rate on legal services?"* has no answer anywhere in the PoSH Act. Naive RAG
answered it, citing **ss.18, 17 and 29 of the PoSH Act**, with **zero flags raised**, and attached
a confidence figure.

Every safety layer worked exactly as specified:

- **CitationValidator** passed — ss.18, 17, 29 *were* in the retrieved context.
- **HallucinationGuard** passed — the answer quoted that context.
- **ConfidenceScorer** returned 29.4% and the pipeline answered anyway.

The failure is not in the guards. It is that **guards check the output against the retrieval, and
the retrieval was wrong.** Nothing downstream of a bad retrieval can detect a bad retrieval. A
cosine search always returns its top-3; asked about GST it returns the three least-unrelated
sections of a sexual-harassment statute and reports how similar they are.

The lattice never reaches that point, because it does not ask "what is closest?" It asks "is there
a provision that governs this, and has anyone verified our reading of it?" For GST the answer to
the first is no.

---

## 2. What replaces each layer, and what it cost

| Proposed | Here | Measured |
|---|---|---|
| Embeddings + ChromaDB | keyword route weighted by corpus IDF, then exhaustive scan | **recall@3 1.00 vs 0.75**, 0.007 ms, no dependencies |
| LLM generates the answer | `applicability.py` decides; the model only explains | model choice becomes a cost lever, not a correctness lever |
| HallucinationGuard by cosine | `verifier.py`: exact citation + number + consequence checks | **6/8 caught, 0/4 false alarms** vs 6/8 caught, **2/4 false alarms** |
| ConfidenceScorer | the epistemic lattice — an ordinal status, never a percentage | see §4 |
| One accuracy score, target >85% | three numbers, always together | fabrication 0%, coverage 0%→**85%** after verification |

Not a rejection of RAG in general. Retrieval-augmented generation is the right shape for
open-domain question answering over a large corpus. It is the wrong shape for **stating what the
law requires**, for the reasons below.

---

## 3. Three properties statutes have that similarity search does not model

### Structure, not topic

s.4 matters to a question about s.26 because **s.26(1)(a) names it** — the penalty attaches to
failing the s.4 duty. Nothing about the two texts is topically similar; one is about committee
composition and the other about fines. An embedding cannot see the link. `provision_graph.py`
reads it off the statute's own cross-references, and `trace()` reports the route with the Act's
words attached:

```
[PATH s.4] rests on s.4, reached from s.26 via the Act's own words:
           "…where the employer fails to— (a) constitute an Internal Committee
            under sub-section (1) of section 4…"
```

That is a chain of authority — how a lawyer would justify the same refusal — and it is checkable
by the reader.

### Contradiction

Statutes disagree with themselves constantly; that is what a proviso is for. s.9 grants three
months to complain and its proviso extends it to six. An answer quoting one without the other is
wrong **in the direction that costs a complainant her remedy**.

Weakest-link composition cannot represent this: it is monotone, so adding a ground only lowers the
status. Two provisions that disagree resolve silently to the weaker one and the disagreement — the
thing a reader most needs — disappears. `conflicts()` surfaces it as a separate signal, reported
even when the answer would otherwise be given.

### Verification is a fact about a provision, not about a match

`verified_by` records that a named human with a bar number checked *our reading* of a section. No
retrieval score approximates it, and no amount of similarity substitutes for it. It is the gate
that makes the whole system honest, and it is the reason coverage is 0% today.

---

## 4. Why there is no confidence percentage

Refused seven times over this project, latterly with evidence rather than principle.

A retrieval similarity score measures whether related text was found. It does not measure whether
a claim is true. `bench_safety.py` demonstrates the gap directly: the embedding guard's own
similarity rated **two verbatim quotations of the statute** as more suspect than four fabrications.
A number that scores an exact quote as doubtful cannot be shown to a user as confidence.

Calibrated confidence requires a labelled validation set. There isn't one. Until there is, the
product reports an **ordinal status** — `SILENT < UNSUPPORTED < UNCHECKED < SECONDARY < INFERRED <
VERIFIED < QUOTED` — which is a fact about the corpus, composed by weakest link, with no floats
anywhere.

---

## 5. What this costs, stated plainly

**Coverage.** 0% today; 85% after a lawyer verifies, measured against the same twenty questions
(`bench_answers.py`). The three that still abstain are named in that output. Abstention is not
free and this file does not pretend otherwise.

**Corpus size.** The keyword-and-scan design is correct at 30 sections and wrong somewhere around
500. `bench_retrieval.py` exists so that transition is decided by re-running it, not by argument.

**Effort.** Every provision must be ingested from a primary source and byte-verified. There is no
path where a model summarises the statute into the corpus, because the corpus is what the verifier
checks against — a paraphrased source means the verifier certifies paraphrases.

---

## 6. The independent check

[Falkor-IRAC](https://arxiv.org/abs/2605.14665) (arXiv 2605.14665, May 2026) reached this
architecture separately: graph-constrained generation, answers accepted only if a valid path traces
through the graph, a *"falsifiability oracle"* rejecting fabricated citations, and graph-native
metrics rather than a single accuracy score. It positions explicitly against vector RAG for law.

We had not read it when this was built. Two independent attempts at grounded Indian legal AI
converged on the same shape, and both rejected the pipeline every planning document proposes.

The empirical case is [Magesh et al., *Hallucination-Free?*](https://arxiv.org/pdf/2405.20362)
(Stanford RegLab, *JELS* 2025): Lexis+ AI >17%, Westlaw ~33%, GPT-4 43% — measured on precisely the
retrieve-then-generate design, built by companies with licensed corpora and thousands of engineers.

---

## 7. The one-paragraph version

> The model never decides what the law requires. A deterministic engine does, from the employer's
> own answers, and a verifier rejects any figure or citation absent from the source text. When we
> cannot source an answer the product says so and names what is missing — with the route to it,
> quoted from the Act. That is why the fabrication rate is zero and the inference spend is ₹0.00:
> we did not filter the hallucinations out, we removed the step that produces them.

Every clause there is reproducible from a script in this repository, which is the only kind of
technical claim worth making about a compliance product.
