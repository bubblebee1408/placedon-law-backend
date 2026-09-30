# 02: The evidence — papers, datasets, articles — and the rule each one forces

Every row ends in a **rule**. A source that forces no rule is not in this table.

**Evidence quality.** The sources new to this plan were located by web search on 2026-09-30.
Publisher pages (ACL Anthology, eCourts, Development Data Lab) were egress-blocked, so they are
**[S]**. Sources inherited from PLAN_19/21/23 keep the tag those plans gave them. Before any of
this is quoted to a customer or an investor, a person reads the source in full.

---

## 1. Can a judgment be predicted? What the literature actually shows

| Source | Tag | What it establishes | Rule it forces |
|---|---|---|---|
| Medvedeva & McBride, *Legal Judgment Prediction: If You Are Going to Do It, Do It Right*, NLLP 2023 (Best Presentation) | [S]; also [V] in PLAN_19 | Of **171** papers claiming LJP, only **12 (~7%)** forecast an undecided case. The rest predict what a judgment *was*, from text written after the decision | **P1.** Any forecast uses only information that existed *before* the decision, and the evaluation split is by date |
| Medvedeva, Wieling & Vols, *Rethinking the field of automatic prediction of court decisions*, AI & Law 31:195–212, 2023 | [S] | Separates **outcome identification**, **outcome-based categorisation** and **outcome forecasting** | **P2.** Every analytics output declares which of the three it is. Only the third may be called a prediction |
| Katz, Bommarito & Blackman, *A general approach for predicting the behavior of the Supreme Court of the United States*, PLOS ONE 12(4): e0174698, 2017 | [S] | A time-evolving random forest over 1816–2015. **70.2%** of case outcomes and **71.9%** of justice votes, forecasting each term only from earlier data | **P3.** Real forecasting is possible, is modest, and needs decades of structured data plus a baseline to beat. That is the reference design for how to evaluate, not a number to promise |
| Malik et al., *ILDC for CJPE*, ACL 2021 | [V] in PLAN_21 | ~35k Supreme Court of India cases. Best model **~78%**, experts **~94%**. Inputs are judgments with the decision removed | **P4.** ILDC-style scores are identification scores (P1/P2). Never quoted as forecasting accuracy |
| Nigam et al., *NyayaAnumana & INLegalLlama*, COLING 2025 | [S] | **702,945** preprocessed Indian cases (SC, HCs, tribunals, district, daily orders). The model is reported at **~90% F1** on binary prediction | **P5.** Useful as a *corpus* and a *baseline* only. Its task construction must be audited for leakage (P1) before any comparison. The ~90% is not a forecasting figure until that audit says so |
| *The Judge Variable: Challenging Judge-Agnostic Legal Judgment Prediction*, arXiv 2507.13732, JURIX 2025 submission | [S] | French custody appeals: per-judge models beat a generalist model (reported F1 up to 92.85% vs 82.63%). Judge identity carries signal | **P6.** Judge identity is *predictive*, which is exactly why it is *regulated* (§5). Excluded by default; counsel decides |
| *Legal Fact Prediction: The Missing Piece in LJP*, arXiv 2409.07055 | [S] | Before a hearing, the facts are contested and not yet found. Prediction from court-found facts assumes away the hard part | **P7.** A pre-decision forecast runs from *pleadings and filings*, not from the judgment's statement of facts |

**What follows [I].**

- "Predict the next judgment" is a real research field with a known failure mode: leakage.
  Most published numbers come from that failure mode.
- An honest forecaster for Indian corporate forums needs **pre-decision records**: filing
  date, forum, bench, case type, statute, stage, and dates of listing. It does not need
  judgment text.
- Those records exist for NCLT as order and cause-list pages. Their bulk-access terms are
  **[OPEN]** (§3).

## 2. Can the system learn a company's data? What the literature shows

| Source | Tag | What it establishes | Rule it forces |
|---|---|---|---|
| Ovadia, Brief, Mishaeli & Elisha, *Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs*, EMNLP 2024 | [S] | Across knowledge-intensive tasks, **RAG consistently outperforms unsupervised fine-tuning** for injecting knowledge | **L1.** A tenant's knowledge enters through retrieval and structured memory, not weights |
| Gekhman et al., *Does Fine-Tuning LLMs on New Knowledge Encourage Hallucinations?*, EMNLP 2024 | [S] | New facts are learned slowly through fine-tuning. As they are learned, hallucination on *existing* knowledge rises roughly linearly | **L2.** "Train it on the company's documents" makes the model *worse* at what it already knew. PLAN_22 D1 stands |
| Carlini et al., *Extracting Training Data from Large Language Models*, USENIX Security 2021 | [S] | Verbatim training sequences, including personal data, can be extracted by query alone | **L3.** No tenant's text enters any weights that another tenant can query. With DPDP, not even the same tenant's, without consent (§6) |
| Huang et al., ICLR 2024: LLMs cannot self-correct reasoning yet | from PLAN_23 §1.4 | No intrinsic self-correction without external feedback | **L4.** "Updates itself" means updates from *external* signal (a reviewer's decision, a law change), never from the model grading itself |
| PLAN_22 D1: knowledge in weights cannot be dated | [R:H] | The moat is point-in-time law; weights have no `as_of` | **L5.** Anything learned must carry `known_at` and `valid_at`, so it is stored as data |

## 3. Indian data: what exists, and whether we may use it

| Source | Tag | What it holds | Licence / access | Decision |
|---|---|---|---|---|
| Indian Supreme Court Judgments, AWS Open Data (Dattam Labs; `vanga/indian-supreme-court-judgments`) | [S] | Judgments 1950–2025 from eCourts, raw JSON + parquet metadata, bi-monthly updates | **CC-BY-4.0, applied by the maintainer** | Citator source (T5), **after counsel** confirms the grant covers court text (PLAN_19 02 §5) |
| Indian High Court Judgments, AWS Open Data | [S] | **17.8M** judgments, 25 High Courts, ~1.25 TiB | CC-BY-4.0, maintainer-applied | Same gate. Company-law appeals and writs in HCs matter for the citator |
| Vaquill `open-india-law` (GitHub) | [S] | **12.8M+** judgments (SC + 25 HCs), **1.1M+** legislation sections, **813k+** tribunal/regulator matters; scrapers Apache-2.0 | Data **CC BY 4.0** | **Candidate for G0.3's unheld-Act text and for tribunal metadata.** It is a derivative of India Code and the court sites, so its provenance must be checked item by item. **[R] Already used once:** `eval/temporal/external/open_india_law_s2_85.json` (retrieved 2026-09-14) holds the record used for s.2(85). That record carries `stored_under_section_number: "3"`, `section_title` equal to the Act's own title, and `amendment_count: 0` for a Companies Act amended by several Amendment Acts since 2015. Its metadata cannot be taken at face value, which is why item-by-item checking is required. Never held law without attestation |
| Development Data Lab, judicial data | [S] | **81.2M** district-court cases 2010–2018: case type, filing and decision dates, acts and sections | **CC BY-NC-SA 4.0; commercial use needs a separate DDL licence.** Judges and litigants anonymised | Research/benchmarking only, unless licensed. District courts are off-wedge for corporate law anyway |
| National Judicial Data Grid (NJDG) | [S] | Pendency and disposal statistics, updated daily | Portal statistics are public. **The Open API is provided to Central and State Governments with a departmental ID and key** | Not a private-sector feed. Aggregate pendency figures may be cited, with the date |
| eCourts services | [S] | Case status, orders | Reproduction permitted **with acknowledgement**, not in misleading or derogatory contexts. Terms page egress-blocked, not read in full | Per-case lookups by a user; no bulk crawl until terms are read [OPEN] |
| NCLT / NCLAT websites | [S] | Orders and judgments searchable by date, bench and case number | Bulk-access terms and robots **[OPEN]** | **The forum that matters most for the wedge.** T6 cannot start until access is lawful |
| DAKSH | [S] | Survival analysis of Indian case pendency; survey of 9,000+ litigants | Research publications | **Method precedent** for time-to-disposal estimates (04 §3) |
| eGazette, IBBI, OFAC, SEBI RSS, data.gov.in MCA master data | [R] PLAN_19 02 | Law changes, counterparty status, company facts | Recorded per source in PLAN_19 02 | Built or scheduled (G3) |

## 4. Statistics that make a number honest

| Source | Tag | Rule it forces |
|---|---|---|
| Wilson score interval (Wilson 1927); Miller, *Adding Error Bars to Evals* (2024) | textbook; [V] in PLAN_21 | **S1.** Every rate is shown as k/n with a 95% interval. No rate below n = 30 (existing gold-set rule) |
| Kaplan & Meier, JASA 1958; Cox, JRSS-B 1972 | textbook | **S2.** Durations ("how long until NCLT sanctions a scheme") are estimated with censoring. **Pending cases are censored observations. Dropping them biases every duration downward** |
| Gelman et al., *Bayesian Data Analysis* (hierarchical models) | textbook | **S3.** Small strata (one bench, one section) are partially pooled toward their parent (the forum, the chapter). Each shows its own n |
| Angelopoulos & Bates; Mohri & Hashimoto ICML 2024; Cherian, Gibbs & Candès NeurIPS 2024 | [V] in PLAN_21 | **S4.** Where a guarantee is claimed it is conformal, per answer, with its calibration n stated |
| Gibbs & Candès, *Adaptive Conformal Inference Under Distribution Shift*, NeurIPS 2021 | [S] | **S5.** Law changes the distribution. Online coverage is tracked with ACI, and a coverage breach blocks serving (05 §4) |
| McNemar's test with Connor's sample size (PLAN_19 04 §8) | [R] | **S6.** "It got better" requires a paired test on a frozen split. Below the required n the verdict is *undecided* |
| Fellegi & Sunter, JASA 1969 | [V] in PLAN_19 | **S7.** Entity resolution is a scored match with review thresholds, never a silent merge |

## 5. Regulation that bounds the design

| Source | Tag | Rule it forces |
|---|---|---|
| France, Loi n° 2019-222, art. 33 | [S]; [V] in PLAN_19 | Reusing judges' identity data "with the purpose or effect of evaluating, analysing, comparing or predicting their actual or alleged professional practices" is prohibited, with up to **five years' imprisonment**. **R1.** Judge-level analytics is a legal-risk feature, not a UI feature |
| Contempt of Courts Act 1971, s.2(c): publication that "scandalises or tends to scandalise" a court | [S] | **R2.** India has no known analytics ban [OPEN], but a published judge "scorecard" carries contempt risk. **Counsel before design** |
| DPDP Act 2023 and DPDP Rules 2025 (notified 13 Nov 2025; Board immediate; consent managers ~Nov 2026; core obligations by **13 May 2027**) | [S]; PLAN_21 | **R3.** Tenant documents hold third parties' personal data (directors, DIN, PAN). Using them for any learning needs a lawful basis and a purpose recorded per matter (05 §6) |

## 6. Palantir, from its own documentation

| Source | Tag | What it says | What we take |
|---|---|---|---|
| Palantir Foundry docs: Ontology overview, core concepts, object and link types, properties | [S] | Object types (entities/events), properties, link types, and **action types** (how an object may be changed). The ontology is the "semantic + kinetic" twin of the organisation | **O1.** Every change to an object is an *action* with a declared actor, reason and undo. PLAN_23's sagas are the same idea |
| Foundry: property provenance, object permissioning; Gotham integration (Entity / Event / Document parents) | [S] | Properties record their backing source; objects carry permissions | **O2.** Every property carries `source`, `known_at`, `valid_at` and `marking`. PLAN_19 01 already mapped this [R] |

## Sources

- Medvedeva & McBride 2023: https://aclanthology.org/2023.nllp-1.9/ · https://masha-medvedeva.github.io/papers/MedvedevaMcBride_LegalJudgmentPrediction.pdf
- Medvedeva, Wieling & Vols 2023: https://link.springer.com/article/10.1007/s10506-021-09306-3
- Katz, Bommarito & Blackman 2017: https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0174698
- NyayaAnumana: https://aclanthology.org/2025.coling-main.738/ · https://github.com/ShubhamKumarNigam/NyayaAnumana-and-INLegalLlama
- The Judge Variable: https://arxiv.org/abs/2507.13732
- Legal Fact Prediction: https://arxiv.org/html/2409.07055v2
- Ovadia et al.: https://aclanthology.org/2024.emnlp-main.15/
- Gekhman et al.: https://aclanthology.org/2024.emnlp-main.444/
- Carlini et al.: https://www.usenix.org/conference/usenixsecurity21/presentation/carlini-extracting
- ACI: https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html
- AWS SC judgments: https://registry.opendata.aws/indian-supreme-court-judgments/ · HC: https://registry.opendata.aws/indian-high-court-judgments/
- Vaquill open-india-law: https://github.com/Vaquill-AI/open-india-law
- Development Data Lab: https://www.devdatalab.org/judicial-data
- NJDG: https://www.nic.gov.in/project/national-judicial-data-grid/
- eCourts terms: https://ecourts.gov.in/ecourts_home/static/terms.php
- NCLT orders: https://nclt.gov.in/order-judgement-date-wise · NCLAT: https://nclat.nic.in/judgement-data
- DAKSH: https://www.dakshindia.org/Justice-Frustrated/forecasting-judicial-data-using-predictive-modelling
- France art. 33: https://www.jurist.org/news/2019/06/new-france-law-bans-use-of-analytics-to-determine-judge-behavior/
- DPDP Rules 2025 (PIB): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- Palantir ontology: https://www.palantir.com/docs/foundry/ontology/core-concepts · https://www.palantir.com/docs/foundry/object-link-types/properties-overview · https://www.palantir.com/docs/foundry/object-permissioning/overview
