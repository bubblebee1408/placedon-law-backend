# Research appendix B: Harvey, and the lawyer-engineer funnel (research agent, 2026-09-30)

## Evidence quality

Most claims are **[S]**. The egress proxy denied harvey.ai, arxiv, aclanthology, huggingface, barandbench, indiankanoon and job boards. Only claude.com and github.com could be fetched, and claims from those are **[V]**. Where the internal docs already hold a claim, they are cited (`docs/research/HARVEY_DIAGNOSIS_2026_09_25.md` and `CONNECTORS_AND_THE_WHITE_SPACE_2026_09_25.md`).

## Harvey

### Product

- **Surfaces:** Assistant, Vault (up to 100k files), Workflows, Knowledge (500+ sources, 90+ jurisdictions), Word add-in [S].
- **Indian content:** SCC Online became a Knowledge source in January 2026 [S].

### Funding and revenue

- **Latest round:** $550M at $15.5B, September 2026 [S]. Bloomberg reports $15.6B, so the sources contradict each other.
- **Earlier rounds:** $11B (March 2026) and $8B (December 2025) [S].
- **Annual recurring revenue:** estimates range from $300M to over $400M depending on the source [S]. None is disclosed.
- **Customers:** "142,000+ lawyers, 1,500+ customers, 60+ countries" [S].

### India

- **Customers:** AZB & Partners and Shardul Amarchand Mangaldas have firm-wide rollouts. S&A is reported as a customer. Cyril Amarchand Mangaldas is unconfirmed [S].
- **Office:** Bengaluru [S].

### Pricing

- **Seat price:** about $1,200 per seat per month, with 20–50 seat minimums [S]. Harvey does not publish prices.

### MCP

- **Harvey runs its own MCP server** [V, claude.com/connectors/harvey]:
  - five tools: Ask Harvey, Ask About Vault Project, Ask With Knowledge Source, List Vault Projects, List Knowledge Sources;
  - per-user OAuth;
  - endpoints under `api.harvey.ai/hosted_mcp/mcp`.
- **Harvey is also an MCP client ("BYOMCP")** [S, help.harvey.ai]:
  - A workspace administrator can connect a custom MCP server.
  - Every user must complete OAuth personally.
  - The internal doc records [V, 25 Sep] that partner servers need OAuth 2.1 with PKCE S256.

### Architecture

- **Retrieval:** Voyage custom embeddings (voyage-law-2-harvey), trained on 20B+ tokens of US case law plus annotations from Harvey's own experts. Reported result: about 25% fewer irrelevant top results [S, vendor-reported].
- **Models:** OpenAI, then Anthropic and Google from May 2025 [S].
- **Harvey Tenet** (August 2026): Kimi K3 post-trained with Fireworks using reinforcement learning on "publicly available legal data, synthetic data, and human expert data". Scored 19.7% vs 10.8% all-pass on Harvey's own benchmark [S, vendor-reported].
- **BigLaw Bench** [V, github]: rubric-scored work product. The full dataset is available only on request.

### Roles

- **Legal engineers** [S, Harvey careers]: "lawyers who left practice." They run discovery, demos, training, onboarding and pilots, and work with product managers and engineers. [I] At Harvey this is mainly a pre-sales and adoption role.
- **Applied Legal Researchers** own evaluation work: cross-reviewed tasks and Elo ratings from preference votes. The role requires a top US JD and 3–7 years of practice [S].
- **Thomson Reuters CoCounsel:** attorney editors create test standards, run the tests and grade the output [S].
- **Indian equivalents:** INCONCLUSIVE.

### Why Harvey matters to Placedon

1. **Incumbent at Indian Tier-1 firms.** Its public material does not claim point-in-time statutory answers; that is an unverified absence.
2. **A conditional distribution channel through BYOMCP.** This needs a hosted MCP server with OAuth 2.1, which is not built.
3. **The market's reference point for quality:** evaluations built by lawyers.

## Annotation evidence

| Dataset | Scale | How it was annotated | Agreement / quality |
|---|---|---|---|
| CUAD | 510 contracts, 13k+ labels | Law students trained 70–100 h against 100+ pages of guidelines; every label validated | Estimated value >$2M |
| MAUD | 47k+ labels, >10,000 h | Teams of 3 reaching consensus; every label reviewed by an M&A lawyer | Lawyers agreed with students about **80%** of the time. About 12.8 min per label [I] |
| LegalBench | 162 tasks | 40 contributors | — |
| ILDC | — | 5 experts on prediction | Fleiss κ = **0.820** [S] |
| PredEx | 15k+ expert annotations | Experts compared against the model | Humans 73% vs best model 78% |
| Kalamkar rhetorical roles (LREC 2022) | 265 judgments | Law students plus professionals | Fleiss κ = **0.59** |
| OpenNyAI InLegalNER | — | 100+ law students over a year; NLSIU partnership | Apache-2.0 data |
| JudgmentBench | — | Timed attorney judgments | Median 4.74 min per rubric score and 1.92 min per pairwise judgment. Pairwise recovered the quality ordering far better (Spearman 0.908 vs 0.150) |

## Pay rates in India

- **Law-student interns:** ₹2k–17.5k per month, roughly ₹85/h [I] [S].
- **Tier-1 first-year associates:** ₹12–22 LPA, roughly ₹600–1,000/h [I] [S].
- **Global freelance platforms:** $35/h median.

## Funnel stages

1. **Source:** NLU clinics, OpenNyAI-style cohorts, CS and LLB graduates.
2. **Screen:** statutory-reading test ≥ 70%, plus 10 gold items answered with citations.
3. **Calibration:** ≥ 80% agreement with gold and κ ≥ 0.6 on 30 items.
4. **Paid pilot:** 50 items, 10% of them hidden gold.
5. **Certified reviewer:** hidden-gold accuracy ≥ 85%, re-tested quarterly.
6. **Senior adjudicator:** 3+ years' practice and κ ≥ 0.8 with other seniors.

Prefer pairwise comparison over rubric scoring wherever the task allows.

## Cost of reaching n human-labelled items

The agent's arithmetic assumes:

- 2 independent reviewers × 15 min per item;
- 20% of items adjudicated at 10 min each;
- calibration of 10 h per reviewer;
- a gold set of 15 senior-hours.

| n | Scenario A (₹400/h reviewer, ₹1,500/h senior) | Scenario B (₹1,000/h, ₹2,000/h) |
|---|---|---|
| 59 | **₹45,250** | ₹83,433 |
| 300 | **₹113,500** | ₹240,000 |
| 1,000 | **₹324,500** | ₹726,667 |

## Law and ethics

- **BCI Rule 49** [S]: an advocate taking full-time salaried employment must inform the State Bar Council and cease to practise. Rule 47 bars an advocate from personally engaging in business. Whether part-time freelance review triggers Rule 49 is **OPEN**, and needs counsel.
- **Privilege:** *In re Summoning Advocates*, 2025 INSC 1275, gives in-house counsel no Section 132 BSA privilege, only Section 134 [S].
- **DPDP:**
  - s.8(2) requires a processor contract.
  - Substantive obligations apply from 13 May 2027. Some sources say 14 May, which is a contradiction.
  - s.3(c)(ii) exempts personal data published under a legal obligation, which may cover MCA filings [I]. This is **OPEN** and needs counsel.
