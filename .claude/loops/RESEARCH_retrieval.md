# RESEARCH — document excerpt retrieval (L1)

Agent R, 2026-10-28. Branch `claude/retrieval-loop-20261028`. No code edited.
Every source below was opened in this session; the "Opened" line says what was actually read
(full PDF text, or abstract page only). Anything not opened is marked **UNVERIFIED**.

## Question

`gateway/document_evidence.collect()` ranks passages by `overlap / sqrt(len(passage_terms))`
and keeps every passage sharing one query word, up to `MAX_PASSAGES = 8`. Measured (EVAL_retrieval.md,
CUAD dev, long query): R@1 0.193, R@8 0.546, MRR 0.306, precision 0.109, 6.50 shown. What does the
literature and proven engineering practice say about fixing (a) term weighting, (b) morphology,
(c) cut-off, (d) semantic gap, (e) follow-ups — **under our constraints**: phase 1 deterministic,
model-free, stdlib-only, exact offsets, no score shown to a reader, honest NO_MATCH?

## Code analysis (what is already in the repository)

| Item | Finding | Reuse? |
|---|---|---|
| `gateway/document_evidence.py` | `_terms()` returns a **set** (tf lost), casefolds, keeps combining marks (category `M*`) so Indian-script words survive; drops 1-char tokens and a 40-word stoplist that already contains `agreement contract clause section document`. One streaming pass over `_spans()`, keeps only the best 8 in a `bisect.insort` list (memory test: < 8 MiB on 166k tiny paragraphs, overview path). Score = overlap / √(passage terms). No IDF, no stemming, no cut-off. | Keep `_spans`, offsets, streaming top-K, tie-break `(-score, ordinal, position)`. Replace the score. |
| `checker/lexical_rank.py` | Okapi BM25, k1 = 1.5, b = 0.75, Lucene-style non-negative IDF `log(1 + (N−n+0.5)/(n+0.5))`. Tokenizer is `[a-z]+`, len ≥ 3. | **Formula yes, class no.** The tokenizer drops every Indian-script word and every number ("30 days"), the class materialises all docs and re-tokenises the query per doc. Copy the ~10 lines of arithmetic, not the class. |
| `checker/vault_search.py` | Stdlib BM25 over vault chunks with a deterministic **context prefix** (document name, class, nearest heading) used for indexing only; shown text stays the chunk's own. | Idea reusable later (deterministic "contextual BM25", see §h). Not phase 1 core. |
| `checker/fusion.py`, `checker/chunk_fusion.py` | RRF with k = 60 (Cormack 2009), measured on statutes: BM25 0.71 → fusion 0.80 cross-section; chunk_fusion warns that fusion only helps when error sets are disjoint. | Phase 2 reuses `RRF_K = 60` and the refusal-not-silent-fallback pattern. |
| `checker/voyage_model.py`, `checker/dense_index.py` | Dense retrievers exist for statutes. PLAN_22 D4: dense enters only if a bake-off wins; client text reaches Voyage only after its processing location is confirmed. | Phase 2 only, behind `gateway/models.serve`. |
| `checker/reranker.py` | Deliberately a linear, explainable reranker over named features — the repository has already argued against an opaque cross-encoder in the statute path. | Phase 3 must answer that argument, not ignore it. |
| `gateway/verbs.py` `_dispatch_conversation` | `de.collect(text, ctx.documents, enabled=…)` with the current user text only. `store.read_messages(cid)` returns ordered messages with `role`, so the previous **user** question is available deterministically. Line 2820 already refuses ambiguous follow-ups *without* attachments; with attachments nothing carries the topic. | The follow-up hook goes here. |
| `scripts/conversation_regression_checks.py` | Discovers `tests/test_document_evidence.py` by pattern. | New unit tests go into that file (or a new pattern must be registered). |

## Sources checked

### (a) Term weighting — BM25

**S1. Robertson, S. & Zaragoza, H. "The Probabilistic Relevance Framework: BM25 and Beyond."
*Foundations and Trends in Information Retrieval* 3(4):333–389, 2009. DOI 10.1561/1500000019.**
URL: https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf — *Opened: full PDF text (pdftotext).*
- Claims: BM25 = Σ_t idf(t)·tf·(k1+1)/(tf + k1·(1−b+b·dl/avgdl)); IDF approximated by
  `log((N−n+0.5)/(n+0.5))` (eq. 3.3); "the model provides no guidance on how these should be set …
  values such as 0.5 < b < 0.8 and 1.2 < k1 < 2 are reasonably good in many circumstances", optimal
  values "depend on … the type of documents or queries". Query-term saturation (k3) "was unimportant",
  so qtf is linear. On proximity: "It is sobering to see how hard it has been in the past to effectively
  use proximity … the improvements reported are small."
- Evidence quality: **high** — the authoritative survey by the model's author; decades of TREC evidence.
- Applies: directly. It is arithmetic, stdlib, deterministic, and it is exactly the missing IDF
  ("period" on every page ⇒ low weight). The eq. 3.3 IDF goes negative when a term is in more than
  half the passages; use the non-negative `log(1 + …)` variant already in `checker/lexical_rank.py`.
  The survey's own proximity verdict is the reason **not** to add a phrase/proximity bonus in phase 1.

### (b) Morphology — Porter / Snowball; Indian scripts

**S2. Porter, M.F. "An algorithm for suffix stripping." *Program* 14(3):130–137, July 1980.**
URL: https://tartarus.org/martin/PorterStemmer/def.txt — *Opened: the author's published definition text.*
- Claims: rule-based suffix stripping in 5 steps with a measure m. Step 1a: SSES→SS, IES→I, SS→SS,
  S→ ; Step 1b: (m>0) EED→EE, (*v*) ED→, (*v*) ING→, with follow-ups AT→ATE, BL→BLE, IZ→IZE,
  double-consonant undoubling, (m=1 and *o)→E; Step 1c: (*v*) Y→I.
- Evidence quality: **high** for "what the algorithm is"; it is the reference implementation.
- Applies: step 1 alone handles plurals and -ed/-ing (`parties`/`party` → `parti`, `terminated` →
  `terminate`) but **not** `termination` ↔ `terminate` — that needs step 2 (ATION→ATE) and step 4.
  Root cause 3 in the runbook names exactly that pair, so step 1 alone is insufficient.
  Original Porter also conflates `general`/`generate` (both → `gener`), a known over-stem.

**S3. Snowball "English (Porter2) stemming algorithm", snowballstem.org.**
URL: https://snowballstem.org/algorithms/english/stemmer.html — *Opened: algorithm page.*
- Claims: revised Porter. Step 1a: `sses`→`ss`; `ied`/`ies`→`i` if preceded by >1 letter else `ie`;
  `s` deleted if the preceding part contains a vowel not immediately before the s; `us`/`ss` unchanged.
  R1 = region after the first non-vowel following a vowel; **for words beginning `gener`, `commun`,
  `arsen`, `past`, `univers`, `later`, `emerg`, `organ`, `inter`, R1 is the remainder of the word**
  — the explicit fix that keeps `generate`→`generat` apart from `general`→`general`. Invariant and
  exceptional forms listed (`news`, `sky`, `atlas`, `bias`, …).
- Evidence quality: **high** as a specification (maintained by Porter's project, published test
  vocabulary); its retrieval benefit on contracts is **not** measured anywhere I opened.
- Applies: the deterministic, stdlib-implementable stemmer that fixes both the runbook pair
  (`termination`, `terminate`, `terminated` → `termin`) and the `general/generate` false merge.
  English only.

**S4. Unicode Standard Annex #15 "Unicode Normalization Forms", Unicode 18.0.0 rev. 58 (2026-08-12).**
URL: https://www.unicode.org/reports/tr15/ — *Opened.*
- Claims: canonically equivalent strings have the same normalized form; NFKC "erase[s] many formatting
  distinctions" and should not be applied blindly; normalization **changes string length** and
  offsets map only up to equivalence; several Devanagari/Bengali/Gurmukhi/Odia nukta precomposed
  characters are composition exclusions (NFC keeps them decomposed).
- Evidence quality: **high** (the standard).
- Applies: Indian-script text from PDFs arrives as either precomposed or decomposed nukta forms.
  Matching should compare **NFC-normalised tokens**, but normalisation must never touch the stored
  text or offsets — normalise the token string only, after `_spans` has fixed `[start, end)`.
  NFKC rejected (it changes meaning-bearing distinctions). No Indian-script stemmer is adopted: none was
  opened and verified in this session, and a wrong stemmer in a script we cannot test against CUAD is
  worse than none. **UNVERIFIED / not searched further**: published Hindi light stemmers.

### (c) Ranked-list truncation

**S5. Arampatzis, A., Kamps, J. & Robertson, S. "Where to stop reading a ranked list? Threshold
optimization using truncated score distributions." SIGIR 2009, pp. 524–531.**
URL (metadata/abstract): https://dare.uva.nl/id/a874f6a0-2d62-40de-b24f-6f0608f39fbe and dblp
`conf/sigir/ArampatzisKR09` — *Opened: search-result abstract only; the UvA PDF failed on a TLS
certificate error.* Method details below come from the abstract and from the BiCut paper (S6),
which describes it as "a competitive method for dynamic list truncation that relies on a parametric
view of the data". **Full text UNVERIFIED.**
- Claims (abstract): rank cut-off as score-distributional threshold optimisation; truncated
  normal(relevant)/exponential(non-relevant) models perform significantly better, on **TREC 2007/2008
  Legal Track**.
- Evidence quality: medium (peer-reviewed, legal e-discovery data; I did not read the numbers).
- Applies: supports the principle that **where to cut is a function of the score distribution of this
  query**, not a fixed k. Fitting a mixture per query on 8–300 passages is fragile and adds parameters;
  phase 1 takes the principle (cut relative to this query's own scores), not the estimator.

**S6. Lien, Y.-C., Cohen, D. & Croft, W.B. "An Assumption-Free Approach to the Dynamic Truncation of
Ranked Lists." ICTIR 2019, pp. 79–82. DOI 10.1145/3341981.3344234.**
URL: https://ciir-publications.cs.umass.edu/pub/web/getpdf.php?id=1326 — *Opened: full PDF text.*
- Claims: BiCut, a Bi-LSTM (two 128-dim layers) over the ranked list's scores and document statistics,
  makes continue/stop decisions; trained against a user metric (F1); beats fixed-k (5/10/50), greedy-k
  chosen on training data, and Arampatzis et al. on Robust04 over BM25 and DRMM top-300.
- Evidence quality: medium-high (peer-reviewed short paper, one collection).
- Applies: **not in phase 1** — it is a trained model and needs labelled truncation data. Its useful
  lesson: **fixed k is the weakest baseline**; the current code is fixed k = 8.

**S7. Bahri, D., Tay, Y., Zheng, C., Metzler, D. & Tomkins, A. "Choppy: Cut Transformer for Ranked
List Truncation." SIGIR 2020. arXiv:2004.13012.**
URL: https://arxiv.org/abs/2004.13012 — *Opened: abstract page.*
- Claims: a Transformer over relevance scores only, optimising a user-defined IR metric, "improves upon
  recent state-of-the-art methods". Baselines and numbers not on the abstract page (**UNVERIFIED**).
- Evidence quality: medium (peer-reviewed; numbers not read).
- Applies: not in phase 1 (trained model). It confirms that **scores alone carry enough signal to cut** —
  which is what a relative-to-top rule uses, crudely.

### (d) Hybrid, dense, rerank — LATER phases only

**S8. Cormack, G.V., Clarke, C.L.A. & Büttcher, S. "Reciprocal Rank Fusion outperforms Condorcet and
individual Rank Learning Methods." SIGIR 2009 (short).**
URL: http://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf — *Opened: full PDF text.*
- Claims: RRF(d) = Σ_r 1/(k + r(d)), **k = 60 "fixed during a pilot investigation and not altered"**;
  beats Condorcet 7/7 (sign test p≈0.008), CombMNZ 6/7 (p≈0.04), best individual run 6–7/7; ~4–5% MAP.
- Evidence quality: high (widely replicated; already measured in this repo on statutes, 0.71 → 0.80).
- Applies: phase 2 fuses BM25 and dense **ranks** (never scores) with k = 60, as `checker/fusion.py` does.

**S9. Karpukhin, V. et al. "Dense Passage Retrieval for Open-Domain Question Answering." EMNLP 2020.
arXiv:2004.04906.** — *Opened: abstract page.* Dense dual encoder beats Lucene BM25 by 9–19 points
absolute top-20 accuracy on open-domain QA. Quality high for open-domain Wikipedia QA; transfer to
contracts **unmeasured here**. Applies: phase 2 rationale for the semantic gap ("end the agreement" →
"terminate"), which no lexical method closes.

**S10. Khattab, O. & Zaharia, M. "ColBERT: Efficient and Effective Passage Search via Contextualized Late
Interaction over BERT." SIGIR 2020. arXiv:2004.12832.** — *Opened: abstract page.* Late interaction,
"two orders-of-magnitude faster" than BERT pair rerankers with competitive effectiveness. Applies: noted
only; a per-token index is heavy for per-turn attached documents and no ColBERT model is among the declared
providers. Not planned.

**S11. Nogueira, R. & Cho, K. "Passage Re-ranking with BERT." arXiv:1901.04085, 2019.** — *Opened: abstract
page.* BERT re-ranking topped MS MARCO, +27% relative MRR@10 over prior state of the art. Quality high on
MS MARCO. Applies: phase 3 candidate only; conflicts with `checker/reranker.py`'s explainability argument and
LegalBench-RAG's result below.

### (e) Conversational follow-ups

**S12. Elgohary, A., Peskov, D. & Boyd-Graber, J. "Can You Unpack That? Learning to Rewrite Questions-in-Context."
EMNLP-IJCNLP 2019, pp. 5918–5924.** URL: https://aclanthology.org/D19-1605/ — *Opened: anthology page/abstract.*
- Claims: defines rewriting a context-dependent question into a self-contained one with the same answer;
  CANARD, 40,527 rewrites over QuAC; Seq2Seq rewriters.
- Applies: names the task precisely; the rewriter is a trained model → not phase 1.

**S13. Dalton, J., Xiong, C. & Callan, J. "TREC CAsT 2019: The Conversational Assistance Track Overview."
arXiv:2003.13624, 2020.** — *Opened: abstract page.* 80 dialogues, 9–10 turns each, 21 groups / 65 runs;
manually resolved utterances beat the best automatic run by **35% relative**. Applies: the follow-up gap is
real and large in a benchmark built for it.

**S14. Lin, S.-C., Yang, J.-H., Nogueira, R., Tsai, M.-F., Wang, C.-J. & Lin, J. "Query Reformulation using
Query History for Passage Retrieval in Conversational Search." arXiv:2005.02230v1, May 2020** (v2 retitled
"Multi-Stage Conversational Passage Retrieval…", ACM TOIS). URL: https://arxiv.org/pdf/2005.02230v1 —
*Opened: full PDF text.*
- Claims: **Historical Query Expansion (HQE)** — non-parametric, BM25-based: (1) keyword extractor scores
  each token by its best BM25 score against the collection; tokens above R_topic join topic keywords,
  above R_sub (from the last M turns) join subtopic keywords; (2) **query-performance predictor**
  A_i = max_p BM25(u_i, p) judges whether the utterance is ambiguous (A_i < η); (3) every non-first
  utterance is concatenated with topic keywords, and ambiguous ones also with subtopic keywords. First
  utterance assumed clear. Best automatic run at TREC CAsT 2019. Grid-searched (η, R_topic, R_sub) =
  (10, 4.5, 3.5) for R@1000 and (12, 4.0, 3.0) for MAP; **M = 1 best for MAP**, M = 5 for R@1000. BM25
  R@1000 on CAsT eval, as I read Table 3 from the extracted text: raw 0.404, HQE ≈ 0.70, manual 0.788.
  Concatenation is unweighted; no down-weight is used.
- Evidence quality: high for TREC CAsT (top automatic system, peer-reviewed journal version); thresholds are
  absolute BM25 values tied to MS MARCO/CAR, **not transferable** to our per-turn collections.
- Applies: **directly, as the phase 1 follow-up method** — it is deterministic and model-free. Transferable
  parts: expand from the previous turn(s); expand more when the current utterance retrieves poorly; M = 1.
  Non-transferable: the absolute η and R values. A down-weight on history terms is **our** choice (so the
  current turn's own words dominate when it has any), not HQE's — labelled INFERRED in the decision.

### (f) Legal / contract benchmarks

**S15. Hendrycks, D., Burns, C., Chen, A. & Ball, S. "CUAD: An Expert-Annotated NLP Dataset for Legal Contract
Review." NeurIPS 2021 (Datasets & Benchmarks). arXiv:2103.06268.** — *Opened: abstract + HTML full text.*
510 EDGAR contracts, 25 types, 41 label categories, 13,101 annotations by law students checked by attorneys;
SQuAD-style question per category ("Highlight the parts (if any) of this clause related to …" + description);
labelled clauses ≈10% of a contract, each label ≈0.25%. "General information" labels (Document Name, Parties,
Agreement Date) ask for the contract's name, signatories and date; Parties was evaluated leniently because
segments are tiny. Licence not stated on the pages opened (EVAL_retrieval.md records CC BY 4.0 from the
local copy; not re-verified here). Applies: our dev/held-out eval. Caveat: US SEC contracts in English.

**S16. Pipitone, N. & Houir Alami, G. "LegalBench-RAG: A Benchmark for Retrieval-Augmented Generation in the Legal
Domain." arXiv:2408.10343, 2024.** — *Opened: abstract + HTML full text.*
6,858 query–answer pairs over 79M+ characters from PrivacyQA, CUAD, MAUD, ContractNLI; snippet-level
retrieval. CUAD, naive 500-char chunks, no reranker: **precision@1 9.27%, recall@1 12.60%, recall@8 40.70%,
recall@64 75.71%**. Authors claim the Cohere reranker was "inferior to not using a reranker"; on CUAD their
own tables show the reranker raising precision at every k while recall was mixed, and two tables duplicate
rows — **the reranker conclusion is internally inconsistent**. Evidence quality: medium (preprint).
Applies: (1) a realistic ceiling: even an embedding pipeline over whole-corpus CUAD gets R@8 ≈ 0.41 at
snippet level — our per-contract R@8 0.546 is not comparable (one contract searched, overlap relevance),
but it says dense retrieval is not a free win on contracts; (2) a reranker's benefit on contracts is not
established.

**S17. Koreeda, Y. & Manning, C.D. "ContractNLI: A Dataset for Document-level Natural Language Inference for
Contracts." Findings of EMNLP 2021. arXiv:2110.01799.** — *Opened: abstract page.* 607 NDAs; NLI plus evidence
span identification, modelled as multi-label classification over spans; existing models "fail badly". Applies:
supports treating a passage (span) as the unit of evidence, as we do; a candidate later eval set (NDAs), not used now.

### (g) Knowing when retrieval failed

**S18. Yan, S.-Q., Gu, J.-C., Zhu, Y. & Ling, Z.-H. "Corrective Retrieval Augmented Generation." arXiv:2401.15884, 2024.**
— *Opened: abstract + HTML full text.* A fine-tuned T5-large (~0.77B) evaluator scores each query–document pair
in [−1, 1]; Correct if any doc above an upper threshold (PopQA 0.59), Incorrect if all below a lower threshold
(−0.99), else Ambiguous; Incorrect discards retrieval and runs web search. PopQA accuracy 52.8 → 59.8.
Evidence quality: medium (preprint; Wikipedia QA). Applies: **the architecture of gating, not the model.**
Our gate must be model-free, and our "Incorrect" action can never be "search the web" (only selected
documents are searched, a stated limitation). Phase 1 analogue: NO_MATCH when no passage matches; a narrow
deterministic "weak match" signal is the HQE trigger, never a confidence shown to a reader.

### (h) Industry evidence

**S19. Anthropic, "Introducing Contextual Retrieval", 19 Sep 2024.** URL: https://www.anthropic.com/news/contextual-retrieval
— *Opened.* Top-20 retrieval failure rate 5.7% baseline → 3.7% contextual embeddings (−35%) → 2.9% plus contextual
BM25 (−49%) → 1.9% with reranking (−67%); rerank 150 → 20; BM25 is kept because embeddings "can miss exact matches"
(e.g. "Error code TS-999"). Fusion method not named. Evidence quality: **vendor-reported**, own datasets, not
contracts specifically. Applies: (1) supports keeping BM25 as a permanent leg in any hybrid; (2) the "context
prefix" idea has a **model-free** variant already in `checker/vault_search.py` (heading/name prefix) that could be a
phase 1c experiment; the LLM-written context is a model call → phase 2+ under residency rules.

## Evidence found (synthesis)

1. **IDF + tf saturation (BM25)** is the standard, evidence-backed fix for root cause 1 and is model-free (S1).
2. **Fixed-k is the weakest truncation baseline** (S6); score-distribution-aware cut-offs beat it (S5, S6, S7).
   No phase-1-compatible paper method exists — all good ones are trained. A **relative-to-top** cut is our
   model-free approximation of the principle; it is INFERRED, to be tuned on dev and judged on held-out.
3. **Porter2** handles `termination/terminate`, `parties/party`, `exclusivity/exclusive` and explicitly avoids
   `general/generate` (S2, S3). Porter step 1 alone does not fix the runbook's own example.
4. **Follow-ups**: a deterministic, BM25-based history expansion (HQE) was the best automatic system at TREC CAsT
   2019 (S14); the gap to manual rewriting is large (S13). Our synthetic suite independently shows prepending the
   prior question turns both NO_MATCH follow-ups into exact-page hits.
5. **Semantic gap** (root cause 4) is closed only by dense retrieval (S9) or a model rewrite (S12); hybrid fusion via
   RRF k = 60 (S8) and BM25 kept as a leg (S19). Not phase 1.
6. **Reranking on contracts is unproven**: LegalBench-RAG's own data are inconsistent (S16); the repo already argues
   for explainable reranking (`checker/reranker.py`).
7. **Proximity/phrase bonuses** give small gains even where they work (S1) — not justified for phase 1.

## Evidence quality

High: S1, S2, S3, S4, S8, S14 (method), S15. Medium: S5 (abstract only), S6, S7 (abstract only), S16, S17, S18.
Vendor-reported: S19. No source measures any of these techniques on **Indian** corporate documents or on
Indian-script text; every transfer to our setting is INFERRED until the dev/held-out numbers say otherwise.

## Result

Phase 1 = BM25 (k1 1.2, b 0.75, non-negative IDF) over the passages of the selected documents, Porter2 English
stemming on ASCII-Latin tokens only, NFC-normalised tokens for Indian scripts (unstemmed), a relative-to-top score
cut-off with a common-term guard, and HQE-style expansion from the previous user question when the current one is
elliptical or retrieves nothing. Phase 2 = dense leg via `gateway/models.serve` fused by RRF k = 60, only after a
bake-off and residency confirmation. Phase 3 = reranker, only if an explainable one fails and a measured gain
exists. Full specification: DECISION_retrieval.md.

## Unresolved issues

- Arampatzis 2009 and Choppy full texts not read (TLS failure; abstract only) — their numbers are UNVERIFIED here.
- No verified Indian-language stemmer; Indian-script queries stay unstemmed (recall loss on inflected Hindi forms is
  accepted and documented, not measured).
- CUAD licence not re-verified from the dataset page in this session.
- HQE thresholds are absolute BM25 values on a different collection; our trigger is a structural/zero-score rule
  instead, and its weight (0.5) is ours, not the paper's.
- Metadata questions (Document Name / Parties / Agreement Date, 151/612 dev) have **no lexical handle**; no source
  opened addresses position priors for contract preambles — any rule there is engineering, not literature.
- Acronym expansion (ROFR/MFN): no authoritative public acronym table was opened; and the CUAD ROFR gold text
  ("negotiate exclusively … in good faith") would not match an expansion anyway.

## Recommended next action

L3: write DECISION_retrieval.md against T's baseline (done in the same session), then L4 orchestrator implements
phase 1 in `gateway/document_evidence.py` + a stdlib Porter2 module, with the unit tests listed there.
