# Research findings — August 2026

Two parallel reviews: legal datasets (licence-verified) and legal-AI literature.
A third, on Indian government document-verification APIs, died on a session
limit before reporting and is still OPEN.

---

## 1. The thesis is externally validated, and the number is brutal

> **Static RAG over current statutory text retrieves the date-applicable version
> 0% of the time.**

Cymbler, Guez & Fabre, *Temporal Misgrounding in Legal RAG: A Versioned-Corpus
Benchmark for French Tax Law*, arXiv 2608.09393 (Aug 2026). 32,436 article-versions
of the French tax code spanning 1938-2031; 209 expert-reviewed questions.

| Approach | Strict accuracy |
|---|---|
| Model parametric knowledge | 3.0% |
| Static RAG over current text | 2.7% |
| **Correct-version retrieval by static RAG** | **0%** |
| Their multi-version retriever | 98.3% |

Corroborated independently: Huang et al. (arXiv 2608.14610) find LLMs are biased
toward applying the most recently enacted law regardless of when the facts
occurred — and that **stronger-reasoning models are worse at this**.

**What this means for us.** Point-in-time correctness is not a model problem or a
prompt problem. It is won or lost in corpus construction. That is unglamorous data
engineering, which is exactly why frontier-model progress will not erode it.

**Method to steal:** Cymbler et al. scored with deterministic regex nuggets and
explicitly refused LLM judges, because an LLM judge inherits the same recency bias
it is meant to detect. Do not evaluate our temporal accuracy with a model.

**And:** there is no versioned Indian statutory corpus in the published
literature. Not for the Companies Act 2013, not for anything.

---

## 2. "17-33%" is real, is someone else's measurement, and must be re-cited

The figure in the Kimi plan traces to Magesh, Surani, Dahl, Suzgun, Manning & Ho,
*Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools*,
arXiv 2405.20362 (Stanford RegLab/HAI + Yale, 2024).

| System | Accurate | Incomplete | Hallucinated |
|---|---|---|---|
| Lexis+ AI | 65% | 18% | 17% |
| Westlaw AI-Assisted Research | 42% | 25% | 33% |
| Ask Practical Law AI | 20% | 63% | 17% |
| GPT-4 baseline | 49% | 8% | 43% |

Method: **n=202** hand-built queries, **preregistered 22 Mar 2024**, submitted by
hand through vendor UIs, manually coded on two axes, **Cohen's κ = 0.77**.

**It is US case law, four US commercial tools, mid-2024.** It is not a general LLM
rate, not a statutory rate, and not transferable to India. We cannot "beat" it —
that would be measuring a different thing on a different corpus. Cite it as
attributed context, never as a baseline we exceed.

**The portable part is the methodology**, and it is the most valuable thing in the
paper: correctness and groundedness coded as **separate axes**, where
`hallucinated = incorrect OR misgrounded`. A response can be factually correct and
still count as a hallucination if it cites authority that does not support it.

**Inapplicable authority** — wrong jurisdiction, wrong statute, wrong court, *or
overruled/superseded* — contributes to **23-38%** of hallucinations across all
three commercial tools. A verifier that only asks "does this citation exist"
catches almost none of it. Ours must check applicability: right Act, right
section, right version, in force on the relevant date. That is what
`checker/admission.py` and `as_of` already attempt.

Related: Dahl et al. (arXiv 2401.01301, *Journal of Legal Analysis*) find pooled
hallucination of **58% (GPT-4) to 88% (Llama 2)** on 14 tasks, ground truth taken
from *metadata* rather than case text. Models are systematically overconfident
(GPT-4 pooled ECE 0.190), so **suppressing low-confidence answers cannot fix
this** — the models do not know what they don't know. Magesh et al. refused
LLM-as-judge outright for the same reason.

---

## 3. Indian corporate-law NLP does not exist — and we can prove it

IL-TUR (ACL 2024) is the field's flagship Indian benchmark. Its eight tasks are
NER, rhetorical roles, judgment prediction, **bail**, statute identification,
prior-case retrieval, summarisation, translation. **Zero corporate, company or
securities law.** Full-index arXiv searches on Companies Act / SEBI / NCLT return
no NLP work on Indian corporate law.

This cuts both ways and the plan should say so:
- **Upside:** the gap is demonstrable to an investor with a citation, not a hand-wave.
- **Cost:** no dataset to reuse and no external yardstick. Corpus construction is a
  first-class workstream, not an assumption.

---

## 4. Licensing: most Indian legal datasets are closed to a commercial product

**Cannot use — non-commercial licences:** ILDC (CC-BY-NC), HLDC (CC-BY-NC),
IL-TUR (CC-BY-NC-SA **and** gated), Pile of Law, MultiLegalPile, LexFiles
(all CC-BY-NC-SA), OpenNyAI AIBE (CC-BY-ND — NoDerivatives forbids the
transformations any ML pipeline performs).

Third-party re-uploads of ILDC tagged MIT do **not** cure this. An uploader cannot
relicense CC-BY-NC data.

**Commercially safe, verified:** InLegalBERT / InCaseLawBERT (MIT) — the best
commercially-clean Indian legal encoders that exist; `opennyaiorg/en_legal_ner_trf`
(Apache-2.0); `labofsahil/Indian-Supreme-Court-Judgments` (CC-BY-4.0, 42,846 rows);
CUAD and ContractNLI original (CC-BY-4.0); BillSum (CC0); SEC EDGAR (US government
work, free, **mandatory User-Agent header**, 10 req/s).

**Indian Kanoon has a paid commercial API** whose terms *explicitly permit* RAG
context-building and LLM fine-tuning, conditional on displaying their logo.
₹0.50/search, ₹0.20/document. This is the legitimate route to case law at scale and
it removes the licensing risk entirely.

**Unverified — do not cite:** SUPACE and SUVAS. Three authoritative sources
returned 403 and no academic literature on either could be located.

---

## 5. Actions taken

- India Code domain migration found and acted on — see `CLAUDE.md`. The 403 that
  blocked corpus re-verification since 21 Aug was a dead domain.
- Section index confirmed against source: 12/12 MVP, 0 mismatches.

## Still open

- Government document-verification APIs (CCA India root certs, DigiLocker, MCA):
  agent died on a session limit. `chains_to_cca` in `checker/pdf_signature.py` is
  still a **string match**, not chain validation, and the code says so.
- SSRN and Indian law-review scholarship: not covered by either review.
