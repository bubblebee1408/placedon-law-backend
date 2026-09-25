# PLAN_16 — research programme, architecture, and what we can prove

Written 2026-09-24. Status vocabulary is [PLAN_00_INDEX](PLAN_00_INDEX.md)'s:
**BUILT · MEASURED · SOURCED · INFERRED · UNVERIFIED · BLOCKED**.

This answers one request: find the research that the Themis architecture should
rest on, decide what we can build and *prove*, plan the API / CLI / MCP / RAG work,
and lay out a publication programme in the way Harvey publishes BigLaw Bench.

**Read §0 before quoting anything.**

---

## 0. Evidence quality of this document

- Every paper in §2 was located by web search on 2026-09-24 and its title, authors,
  venue and main finding confirmed from the search index, the publisher page or the
  venue page. **arxiv.org and export.arxiv.org are blocked by this environment's
  egress policy**, so no paper was read in full here. Status for §2 as a whole:
  **PARTIALLY_VERIFIED — abstract-level.** Before any of it is cited in a paper,
  each one is read in full by a person.
- The four temporal-legal-RAG papers in §2.4 were found only through search
  snippets. Their numbers are quoted as the snippets gave them and are
  **UNVERIFIED** until read.
- No accuracy claim for Themis follows from anything here. No practising lawyer
  has reviewed any output, and there is no real-document benchmark (README).

---

## 1. Decisions this plan builds on (founder, 2026-09-24)

| # | Decision |
|---|---|
| 1 | First customer: **in-house legal teams** |
| 2 | **No general chat.** Nothing is answered from a model's memory about law we do not hold. Drafting and summarising the customer's own documents is allowed only when every sentence is traced to a span (`checker/lawyer_summary.py`) |
| 3 | **A Vault** (durable per-tenant document store). Customer data is never used for training unless an admin opts in, per matter, revocably. PLAN_07 §1's "never durable" rule is amended to: *nothing is kept as a side effect; only a deliberate Vault upload persists, under the customer's control.* The AI runtime stays zero-retention |
| 4 | **Providers:** Azure OpenAI in an Indian region as the default for client documents; Claude as a customer-enabled option on the most India-resident route; Gemini free tier and Sarvam (until opt-out is confirmed) **never** receive a client document |
| 5 | **Placedon** is the product and brand; **Themis** is the engine inside it |

Recommended over decision 3's "train on opted-in data": offer **"contribute to the
evaluation set"** instead. A reviewed document plus the lawyer's verdict is worth
more as a test case than as training text, and `annotation.to_sft()` (CLAUDE.md,
E6) must be fixed before any training path opens. DPDP consent for third parties'
personal data in those documents needs counsel's view first.

---

## 2. The literature the architecture rests on

### 2.1 The problem is real and measured

| Paper | Venue | What it establishes for us |
|---|---|---|
| Magesh, Surani, Dahl, Suzgun, Manning, Ho — *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools* | J. Empirical Legal Studies 22(2), 2025; arXiv 2405.20362 | Commercial legal RAG tools hallucinate **17–33%** of the time. First **preregistered** evaluation of legal AI. The method we copy: preregister before measuring |
| Joren, Zhang, Ferng, Juan, Taly, Rashtchian (Google) — *Sufficient Context: A New Lens on RAG Systems* | ICLR 2025; arXiv 2411.06037 | Large models answer wrongly **instead of abstaining** when retrieved context is insufficient. This is the "new RAG from Google" worth adopting: classify whether the context is *sufficient* before answering |

### 2.2 Retrieval-augmented generation — what exists

| Paper | Venue | Take | Do not take |
|---|---|---|---|
| Asai et al. — *Self-RAG* | ICLR 2024; 2310.11511 | The idea of retrieve → critique → decide | Its self-critique: a model grading its own claim is the circularity `eval/realrun/` refuses |
| Yan et al. — *Corrective RAG (CRAG)* | 2401.15884 | A retrieval evaluator that grades evidence quality before generation | Its web-search fallback: violates the source policy |
| Edge et al. (Microsoft) — *From Local to Global: A Graph RAG Approach* | 2404.16130 | Graph index for *global* questions ("what obligations does this group of companies carry?"). We already hold a provision graph | LLM-extracted entity graphs as authority: a model may propose, never decide |
| Google — *Speculative RAG* | 2407.08223 | Small drafter + large verifier, each draft from a distinct evidence subset. A cost pattern for the router | — |
| Google Cloud — *Check grounding* API | Vertex AI docs | A 0–1 support score with per-claim citations. **Use only as an external baseline** in evaluation | As a dependency on the serving path, or on client documents (decision 4) |

### 2.3 Attribution, factuality, abstention, and guarantees

| Paper | Venue | Role in Themis |
|---|---|---|
| Gao et al. — *Enabling LLMs to Generate Text with Citations (ALCE)* | EMNLP 2023; 2305.14627 | Citation-quality metrics. Best models lack full citation support ~50% of the time on ELI5 — the baseline our span tracing exists to beat |
| Min et al. — *FActScore* | EMNLP 2023; 2305.14251 | Split text into atomic facts; score the share supported by a knowledge source. `lawyer_summary.py`'s per-clause tracing is the same shape, with byte-identical spans instead of a model judge |
| Wen et al. — *Know Your Limits: A Survey of Abstention in LLMs* | TACL 2025; 2407.18418 | The taxonomy for positioning our abstention (query / model / human values) |
| Angelopoulos & Bates — *A Gentle Introduction to Conformal Prediction* | 2107.07511 | Distribution-free, finite-sample guarantees from a calibration set |
| Mohri & Hashimoto — *Language Models with Conformal Factuality Guarantees* | ICML 2024; 2402.10978 | Back off an output's claims until a conformal threshold holds: **80–90% correctness guarantees** with few labelled samples. The basis of contribution C1 |
| Cherian, Gibbs, Candès — *LLM validity via enhanced conformal prediction* | NeurIPS 2024; 2406.09714 | Fixes two defects of the above: the guarantee is not conditional on topic, and filtering removes too many true claims. Needed because our claims are heterogeneous (thresholds vs. dates vs. duties) |
| Goguen & Meseguer — *Security Policies and Security Models* | IEEE S&P 1982 | **Non-interference**: low outputs are unchanged by high inputs. The formal statement of what `checker/rings.py` enforces |
| Miller (Anthropic) — *Adding Error Bars to Evals* | 2411.00640 | Standard errors, paired comparisons and power analysis for evals. Governs every number we publish |

### 2.4 Legal benchmarks, and the closest prior work to ours

| Paper | Venue | Relevance |
|---|---|---|
| Guha et al. — *LegalBench* | NeurIPS 2023 D&B; 2308.11462 | 162 tasks built by legal professionals. The model for how a benchmark earns lawyers' trust |
| Joshi et al. — *IL-TUR* | ACL 2024; 2407.05399 | The Indian legal benchmark. GPT-4 below specialised models on most tasks |
| Malik et al. — *ILDC for CJPE* | ACL 2021; 2105.13562 | 35k Supreme Court cases; best model **78%** vs **94%** for experts on outcome prediction. The honest ceiling for "predict the case" |
| Harvey — *BigLaw Bench* (blog series: Research, Retrieval, Hallucinations, Sources, Global, Arena) | harvey.ai/blog | The publishing model the founder asked for: tasks derived from real billable work, released as a public subset, extended per practice area and jurisdiction |
| *Temporal Misgrounding in Legal RAG: A Versioned-Corpus Benchmark for French Tax Law* (FiscalQA Pro) | arXiv 2608.09393 | **Prior art for our flagship idea.** Snippet (UNVERIFIED): static RAG ~3% strict on version-dependent questions, version-aware ~98% |
| *Asking For An Old Friend: Temporal Failure Modes in LLM Statutory QA* | arXiv 2605.23497 | 312 German statutory QA pairs, pre-/post-amendment. Prior art |
| *LexKairos: Benchmarking Legal Temporal Capabilities in LLMs* | arXiv 2608.09106 | Effective-date and effective-version tasks. Prior art |
| *Time as Structure: Temporal Dependency Graphs for Verifiable Deadline Computation over Legal Documents* | arXiv 2608.15270 | Prior art for statutory deadline arithmetic |

**Consequence, stated plainly:** "version-aware legal RAG" is **not** a novel
contribution in September 2026. Four groups have published it. What §4 claims as
ours has to be narrower and must be checked against these papers, read in full,
before submission.

---

## 3. The architecture, component by component, with its evidence

```
 Lawyer (Next.js, Microsoft SSO, business email)
        │
 API gateway — tenant + matter scoping, policy, audit        [policy.py: BUILT]
        │
 ORCHESTRATOR — plans; decides nothing about the law
   │
   ├─ 1 SCOPE GATE        held / declared / out of scope     [scope.py: BUILT, 20/20]
   ├─ 2 RETRIEVE          structural BM25, as-of filtered    [BUILT; 70-case eval]
   ├─ 3 SUFFICIENCY GATE  is the context enough to answer?   [NEW — Joren et al.]
   ├─ 4 DECIDE            deterministic obligations/deciders [BUILT, Ring 0]
   ├─ 5 NARRATE           model writes prose (router.py)     [BUILT]
   ├─ 6 TRACE             each clause → byte-identical span  [lawyer_summary.py: BUILT, 89/89]
   ├─ 7 CERTIFY           conformal back-off over claims     [NEW — Mohri & Hashimoto; Cherian et al.]
   └─ 8 SERVE             only what survived 1–7; the rest is shown as refused
        │
 Live layer — Gazette / OFAC / IBBI feeds → operations       [BUILT, Ring 2]
 Firewall — no Ring 2/3 value reaches Ring 0                 [rings.py: BUILT, 36/36]
```

What each new stage adds, and why it is not already covered:

- **Stage 3 (sufficiency)** is the gap `scope.py` cannot close: a question can be
  inside held law and still have insufficient retrieved context. Today that case
  reaches the narrator. Joren et al. show frontier models then answer instead of
  abstaining. Implementation: a sufficiency classifier whose output can only
  *withhold*, never *permit* (it adds refusals, never answers).
- **Stage 7 (certify)** turns "every sentence is traced" into a statistical
  guarantee. In Mohri & Hashimoto's form: *with probability ≥ 1−α (over a fresh
  question exchangeable with the calibration set), every claim that survives the
  filter is true.* It is a per-answer guarantee, not a bound on the fraction of
  false claims. It needs labelled data we do not yet have (§4, C1) — which is why
  the pilot matters.
- **Stages 1, 4 and 6 stay deterministic.** Nothing in the literature above is a
  reason to put a model in a decision path.

---

## 4. The mathematics and algorithms: candidate contributions

"New math" here means **formalising and proving properties of mechanisms this
repository already runs**, then measuring them. Each item states its claim, what
can be proven, what data it needs, and what would falsify it.

### C1 — Certified abstention for statutory QA

- **Claim.** Composing a deterministic verifier (span tracing) with conformal
  back-off gives a distribution-free guarantee that a served answer contains no
  false claim with probability ≥ 1−α, and the deterministic stage shrinks the
  calibration set needed. (Two different guarantees are in play and must not be
  conflated: the conformal one is per answer; the PAC row below bounds an error
  *rate* from a clean audit sample.)
- **Provable.** Under exchangeability of calibration and test claims, the
  split-conformal guarantee holds (Angelopoulos & Bates; Mohri & Hashimoto).
- **Data it needs — computed 2026-09-24:**

  | Target | Smallest calibration set |
  |---|---|
  | Split conformal, α = 0.10 / 0.05 / 0.01 | n ≥ 9 / 19 / 99 |
  | PAC-style, zero observed errors, δ = 0.05, α = 0.10 / 0.05 / 0.02 / 0.01 | n ≥ 29 / 59 / 149 / 299 expert-labelled claims |

  (Second row: smallest n with (1−α)^n ≤ δ.)
- **Falsifier.** Coverage measured on a held-out, expert-labelled set falls below
  1−α. Also: exchangeability fails because pilot questions drift by topic — which
  is exactly Cherian et al.'s conditional-validity problem.

### C2 — How many labels before "calibrated" means anything

- **Claim.** Published calibration targets (e.g. ECE < 0.05) are unreachable at
  common evaluation sizes even for a *perfect* forecaster, and the usual normal
  approximation understates the floor.
- **MEASURED (`checker/calibration_contract.py`):** `ece_floor(0.90, 20) = 0.0513`
  (a perfect forecaster fails ECE < 0.05 at n = 20); `ece_floor(0.10, 6) = 0.1063`.
- **Provable.** Exact binomial expressions; a short note with closed forms and a
  table.
- **Falsifier.** A derivation error — every figure must be re-derived
  independently before submission.

### C3 — Knowledge-base currency as a monitored quantity

- **Claim.** A legal RAG system must monitor whether **its own corpus** has stopped
  moving, not only which version of a provision to retrieve. This is the
  difference from FiscalQA Pro / LexKairos, which assume a maintained versioned
  corpus.
- **Provable.** With a monotone publication counter (Gazette serials, measured on
  eGazette), a poll bounds the set of publications it may have missed: the
  unseen serials between two readable high-water marks. A poll that regresses is
  detected (RT-07). Stated as a lemma with assumptions.
- **Evidence we hold.** The engine's own incident: a superseded s.2(85) threshold
  served as CURRENT for nine months (FEATURES F7); the amendment ledger stopping
  at 2023-10-30 (`corpus_currency.py`).
- **Falsifier.** The counter is not monotone, or serials are reused.

### C4 — Registry observations as interval-censored data

- **Claim.** A statutory filing window makes a registry's current value a
  *bound*, not a value: under s.77's registration window, "Active charges: 0" is
  a floor. `mca_snapshot.py` implements this as blindness windows.
- **Provable.** Formalise each field as an interval [observed, observed +
  unreportable-within-window] and give composition rules. Standard censoring
  framing; the contribution is applying it to statutory lag.
- **Falsifier.** A counterexample where the window does not bound the unreported
  set (for example, a late filing lawfully condoned).

### C5 — Non-interference between forecasts and legal determinations

- **Claim.** `rings.py` is a sound static *approximation* of non-interference
  (Goguen & Meseguer, 1982) for Python modules, under stated conditions: no
  dynamic import in a decider, and a transitive closure through unregistered
  helpers.
- **Evidence.** Red-team findings RT-01 and RT-02 were exactly the two ways the
  first version was unsound; both now have negative controls.
- **Provable.** Soundness relative to the import graph; incompleteness named
  (data passed at runtime through a shared object is out of scope).
- **Falsifier.** A Ring 0 output that changes when only a Ring 2 input changes.

### C6 — The evidence budget as a lattice

- **Claim.** `lattice.worst_of()` composes states as a meet on a finite ordered
  set, so a roll-up is monotone and always names its witness. It never multiplies
  probabilities over dependent inputs (the L-15 lesson).
- **Provable.** Monotonicity and witness preservation. Small, clean, and useful as
  the formal core of the "ordinal, not probabilistic" position.

### What we will not claim

- **Case-outcome prediction.** ILDC's best model reached 78% against 94% for
  experts on Supreme Court cases. We hold **zero judgments**, and calibration at
  our sample sizes is not achievable (C2). Not in the programme.
- **Market prediction.** Off the in-house buyer's problem, licensed data, and a
  possible SEBI Research Analyst Regulations question (counsel to confirm).

---

## 5. Publication programme

Harvey publishes mainly as **blog series with public benchmark subsets**
(BigLaw Bench). We do both: a technical blog for speed, and peer review for
credibility — which matters more for an unknown entrant than for Harvey.

| # | Paper | Contribution | Blocked on | Venue (deadline, as found 2026-09-24) |
|---|---|---|---|---|
| P1 | *How many labels before "calibrated"?* | C2 | Nothing — independent re-derivation only | arXiv preprint now; then a workshop or TMLR |
| P2 | *Non-interference between forecasts and legal determinations* | C5 + C6 | Nothing | ACM CS&Law 2027 (deadline UNVERIFIED — check computersciencelaw.org) or ICAIL 2027 (**28 Jan 2027**) |
| P3 | *Is the law in the answer still the law? Corpus currency in Indian corporate-law RAG* | C3 + C4, with the s.2(85) incident and competitor staleness | Read the four §2.4 papers in full; re-check the competitor sites with dated captures; independent corroboration (the RETRACTIONS lesson) | ICAIL 2027 (**28 Jan 2027**) |
| P4 | *Certified abstention for statutory QA* | C1 + the sufficiency gate | ≥ 59 (target 299) expert-labelled claims — **the in-house pilot** | NLLP 2027 (the 2026 deadline, 27 Aug, has passed) or ACL/EMNLP Findings |
| P5 | *An Indian in-house compliance benchmark* | Tasks from real in-house work, BigLaw-Bench style, public subset | Pilot data rights, annotators, consent (decision 3) | NeurIPS Datasets & Benchmarks |

Rules for every paper, inherited from this repository:

1. **Preregister** hypotheses and the analysis plan before measuring (Magesh et al.).
2. **Error bars on every number** (Miller); McNemar/Wilson for paired comparisons,
   as `fusion.py` already does.
3. **Non-circular evaluation.** No model grades its own family's output. No
   current consolidation used as pre-amendment ground truth (RETRACTIONS).
4. Every figure carries MEASURED / SOURCED / INFERRED and its commit.
5. A claims ledger entry per paper (`docs/CLAIMS_LEDGER.md`).

---

## 6. Development plan: API, CLI, MCP, RAG

Each item names what "done" means. **Bugs and privacy first, then foundations, then
research features.**

### 6.1 Fix before anything is shown to a customer

| Item | Done when |
|---|---|
| The lawyer sentence "Nobody has read the instrument yet" is false for attested instruments (`checker/mcp/tools.py:188`, `checker/operations.py:279-294`) | Both consult attestation; tests assert both the attested and the unattested wording |
| Provider privacy rule: Gemini free tier and Sarvam without opt-out never receive a Vault document | `router.py` refuses; a test proves it |
| Fresh-clone gate: 5 suites fail outside the founder's laptop (pypdf missing, root-readable `chmod 000`, uncommitted Indian Kanoon cache) | `run_tests.sh` GREEN from a clean checkout; CI enabled from `ci/tests.yml.pending` |

### 6.2 API

- OpenAPI description of the eight live routes (`checker/api.py`), versioned `/v1`.
- Identity in front of the engine: tenant, matter, actor from SSO — the engine
  stays unauthenticated and loopback-only behind the gateway.
- Operation store (G5): `create_operation` persists; `get_operation` stops
  returning 501; `submit_evidence` exists, and closing a BLOCKING requirement
  needs a human.
- Update the website's `AGENTS.md`: it says six routes and that `/v1/ask` does not
  exist; the engine serves eight.

### 6.3 CLI

- `themis` command, standard library `argparse` over `api.handle()` (same function
  the HTTP server and MCP call, so the three surfaces cannot drift):
  `themis ask`, `themis check <pdf>`, `themis pack`, `themis impact <instrument>`,
  `themis watch gazette|ofac|ibbi`, `themis scope`.

### 6.4 MCP

- The server exists (13 read-only tools, policy-decided). It answers protocol
  version **2024-11-05**; the current specification is **2026-07-28** (stateless
  core, authorisation hardening). Upgrade and test against a current client.
- Keep the rule: no write, submit or attest tool is exposed to an agent.

### 6.5 RAG v2

| Step | Done when |
|---|---|
| Grow the retrieval eval from 70 to ≥ 300 questions drawn from pilot users, frozen and preregistered | Power analysis per Miller shows it can detect the effect we care about; at n = 70, BM25 vs MiniLM is indistinguishable (McNemar p = 0.648) |
| As-of retrieval everywhere: every retrieved span carries the version and effective dates it is valid for | A question dated before an amendment never retrieves post-amendment text (tests on s.177, s.447, s.35 from TEMPORAL_PROOF) |
| Sufficiency gate (stage 3) | Adds refusals only; measured on the frozen eval: refusals added vs. wrong answers prevented |
| Conformal certification (stage 7) | Coverage reported with its calibration n; not served to customers until n ≥ 59 |
| Hybrid dense retrieval | Only if it beats BM25 on the enlarged eval, non-overlapping intervals (`router.py`'s `adopt_when` rule) |
| GraphRAG over the provision graph | Only for global, multi-company questions; the graph is ours, never model-extracted |

### 6.6 Vault and privacy (decision 3)

- Per-tenant encrypted storage, per-tenant keys; deletion by key destruction.
- Consent records for any evaluation or training use: who, when, which matters,
  revocable.
- Customer-visible retention policy; export on request.
- **Before any training use:** fix E6 (`annotation.to_sft()`), counsel's DPDP
  opinion on third-party personal data in customer documents.

---

## 7. Order of work

1. **§6.1** — the three fixes. Nothing reaches a customer before these.
2. **P1 and P2** — publishable from what exists; no customer data needed.
3. **Vault, SSO, operation store, CLI, MCP upgrade** — the product an in-house
   team can pilot.
4. **The pilot** — one in-house legal team. It is also H-C, and it produces the
   labelled claims P4 needs and the questions RAG v2's eval needs.
5. **P3 and P4** — after the §2.4 papers are read in full and the labelled data
   exists.
6. **P5** — only with data rights settled.

---

## 8. What this document does not claim

- That any §4 contribution is novel. Each needs a full literature check against
  papers read in full; §2.4 already removed one candidate.
- That any venue will accept any paper, or that the deadlines above are final.
- That Themis is accurate. That claim waits for P4's measured coverage on
  expert-labelled data.
- That the provider facts in decision 4 are confirmed: which Azure OpenAI models
  run in Indian regions, the zero-retention approval process, and India-resident
  routes for Claude are **UNVERIFIED** and must be confirmed with the vendors.

---

## Sources (checked 2026-09-24, abstract level)

- Magesh et al. — https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413 · https://arxiv.org/abs/2405.20362
- Joren et al. — https://arxiv.org/abs/2411.06037
- Self-RAG — https://arxiv.org/abs/2310.11511 · CRAG — https://arxiv.org/abs/2401.15884
- GraphRAG — https://arxiv.org/abs/2404.16130 · https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- Speculative RAG — https://arxiv.org/abs/2407.08223
- Vertex AI check grounding — https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding
- ALCE — https://aclanthology.org/2023.emnlp-main.398/ · FActScore — https://aclanthology.org/2023.emnlp-main.741/
- Abstention survey — https://aclanthology.org/2025.tacl-1.26/
- Conformal intro — https://arxiv.org/abs/2107.07511
- Conformal factuality — https://proceedings.mlr.press/v235/mohri24a.html
- Enhanced conformal — https://proceedings.neurips.cc/paper_files/paper/2024/hash/d02ff1aeaa5c268dc34790dd1ad21526-Abstract-Conference.html
- Goguen & Meseguer — https://www.semanticscholar.org/paper/Security-Policies-and-Security-Models-Goguen-Meseguer/4458b0a2247c658a9476b6b3774f3836c2c11e94
- Error bars — https://arxiv.org/abs/2411.00640
- LegalBench — https://proceedings.neurips.cc/paper_files/paper/2023/hash/89e44582fd28ddfea1ea4dcb0ebbf4b0-Abstract-Datasets_and_Benchmarks.html
- IL-TUR — https://aclanthology.org/2024.acl-long.618/ · ILDC — https://aclanthology.org/2021.acl-long.313/
- Harvey BigLaw Bench — https://www.harvey.ai/blog/introducing-biglaw-bench · https://www.harvey.ai/blog/biglaw-bench-hallucinations
- Temporal legal RAG prior art — https://arxiv.org/abs/2608.09393 · https://arxiv.org/html/2605.23497 · https://arxiv.org/pdf/2608.09106 · https://arxiv.org/pdf/2608.15270
- MCP specification 2026-07-28 — https://modelcontextprotocol.io/specification/2026-07-28
- NLLP 2026 — https://nllpw.org/workshop/call/ · ICAIL 2027 — https://icail-vienna-2027.org/call-for-papers/ · ACM CS&Law — https://computersciencelaw.org/
