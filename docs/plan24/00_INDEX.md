# PLAN_24: Themis Intelligence — the orchestration model that learns, watches and measures

Written 2026-09-30 on branch `claude/kind-mayer-rt20h0` (based on `main` at `d966e4f`).
Nine documents. **A design, not a status.** Naming a module here is not a claim that it exists.

> **Two documents carry the number 24.** The orchestration branch independently wrote
> `docs/PLAN_24_INDIAN_SOURCES.md` (Indian sources: tiers, a terms register, build order S0–S5).
> When they met in `main` on 2026-09-30, both were kept. Here, **"PLAN_24" means this folder,
> `docs/plan24/`**, and the other is cited by its file name. Renumbering either one is a
> founder decision, as PLAN_16→PLAN_21 was.

> **Where the newest work lives.** PLAN_20–23, the gateway, `agents/`, the router and the
> playbook are on `claude/harvey-india-platform-analysis-d2mmqi` (135 commits ahead of `main`,
> head `22b8205`, unmerged on 2026-09-30). This plan was read against that branch with
> `git show`, not checked out. File references marked **[R:H]** were read there;
> **[R]** means read on `main`.

## The request, stated exactly

The founder asked for Themis to become a "Palantir Gotham for lawyers". It is for in-house
teams, top-tier firms and senior lawyers, Indian data first. It should:

- hear, read and understand;
- give judgments and predict the next one from judges' past decisions;
- use statistics and probability;
- read research papers;
- adapt to each company's data and learn from it, including Placedon's data;
- update itself frequently, and serve live, precise data;
- be integrated into the orchestration model.

The founder also asked for three more things:

- finish the incomplete work first;
- ground everything in proven papers, datasets and articles;
- give the first prompt for Claude Code.

## The verdict, before the detail

| Asked for | Verdict | The reason in one line | Where |
|---|---|---|---|
| Finish the incomplete work | **BUILD FIRST (T0)** | 31 open ledger rows plus PLAN_23's O1–O9. Seven T0 items are code-closable now; the rest need a person, a decision or a source | [01](01_STATE_AND_UNFINISHED.md) |
| "Palantir for lawyers" | **TAKE the mechanism** | Typed objects, provenance on every property, markings, actions — PLAN_19 01 already mapped it; this plan adds the *learning* and *analysis* planes | [03](03_ARCHITECTURE.md) |
| Orchestration integration | **EXTEND PLAN_23**, do not replace it | Its 12 layers stay. This plan adds 6 intents, a learning loop and an analytics plane *behind* them | [03](03_ARCHITECTURE.md) §4 |
| Adapt to each company's data | **BUILD — as memory, retrieval and small per-tenant models, not LLM weights** | Retrieval beats fine-tuning for new knowledge (Ovadia et al., EMNLP 2024). Fine-tuning on new facts raises hallucination (Gekhman et al., EMNLP 2024). Models memorise and leak training text (Carlini et al., USENIX Sec 2021) | [05](05_LEARNING_AND_ADAPTATION.md) |
| Update itself frequently | **BUILD — data updates automatically; behaviour changes only through a gate** | A change to what is served is promoted on a frozen test split, with a person signing. This is PLAN_22 D2, made into a loop | [05](05_LEARNING_AND_ADAPTATION.md) §3 |
| Statistics and probability | **BUILD, on held law first** | Forum statistics for Companies Act matters at NCLT (schemes, s.241/242, compounding) are on-wedge. Every number carries n and an interval | [04](04_ANALYTICS_AND_PREDICTION.md) |
| Predict the next judgment | **RESEARCH TRACK ONLY, pre-registered, may never ship** | Only 12 of 171 LJP papers forecast an undecided case (Medvedeva & McBride, NLLP 2023). Indian benchmarks are mostly outcome *identification*. The lawful NCLT data route is OPEN | [04](04_ANALYTICS_AND_PREDICTION.md) §5 |
| Judge-level analytics | **OFF by default; counsel decides** | France criminalised it (Loi 2019-222 art. 33). India's position is OPEN. Evidence says judge identity does predict outcomes (JURIX 2025), which is why it is sensitive | [04](04_ANALYTICS_AND_PREDICTION.md) §6 |
| Read research papers | **BUILD a research registry** | It closes the master plan's §105 criterion 18, which is unmet. Papers are engineering evidence, never legal authority | [03](03_ARCHITECTURE.md) §3.6 |
| Hear | **LATER, one use only** | ASR of a tenant's own board-meeting audio, checked against its minutes (SS-1 scanner exists). Word error rate is measured before use | [03](03_ARCHITECTURE.md) §3.1 |
| Live data | **BUILD, from permitted sources only** | eGazette, IBBI, OFAC are built; SEBI RSS, data.gov.in MCA master data next. NSE and Zauba stay refused (PLAN_19 02) | [02](02_EVIDENCE.md) §4 |
| International data | **NOT NOW**, per the founder | — | — |

**The whole plan in one sentence.** Themis learns the way a good firm learns. Each reviewed
decision becomes a precedent and a test case. The weights of a language model do not. Every
number Themis shows carries its sample size, its interval, and the law version it was
computed against.

## Reading order

| # | Document | For | What it contains |
|---|---|---|---|
| 00 | This index | everyone | Verdicts, tags |
| 01 | [State and unfinished work](01_STATE_AND_UNFINISHED.md) | founder, engineers | Measured state; every open task, who can close it, in what order |
| 02 | [Evidence](02_EVIDENCE.md) | engineers, reviewers | Papers, datasets and articles, each tagged, each with the rule it forces |
| 03 | [Architecture](03_ARCHITECTURE.md) | engineers, investors | Seven planes over the four rings; the ontology; how a request flows |
| 04 | [Analytics and prediction](04_ANALYTICS_AND_PREDICTION.md) | engineers, founder | How deep it can go, level by level, with the maths and the data gates |
| 05 | [Learning and adaptation](05_LEARNING_AND_ADAPTATION.md) | engineers, counsel | Per-tenant memory, the promotion gate, drift, DPDP |
| 06 | [Roadmap](06_ROADMAP.md) | everyone | Phases T0–T8, entry and exit gates, interleaved with PLAN_19 G and PLAN_23 O steps |
| 07 | [Claude Code prompts](07_CLAUDE_CODE_PROMPTS.md) | Claude Code | **The first prompt**, and one per phase after it |
| 08 | [Self-critique](08_SELF_CRITIQUE.md) | founder | What would make each part worthless, and the kill criteria |

## Tags used throughout

| Tag | Means |
|---|---|
| **[R]** / **[R:H]** | Read in this repository on 2026-09-30 (`main` / the harvey branch) |
| **[V]** | Confirmed on 2026-09-30 from a publisher, venue or official page, at abstract or summary level. Not read in full unless it says so |
| **[S]** | Seen only in a search-engine summary. A lead, not a fact |
| **[I]** | Inference: this plan's reasoning, not a source |
| **[OPEN]** | Not established. Do not build on it |
| **[BLOCKED]** | Needs a person, a contract, or counsel |

## What this plan does not claim

- **No accuracy figure for Themis.** The gold set holds 0 human labels ([R:H]
  `eval/goldset/questions.jsonl`: 47 MECHANICAL, 40 SYNTHETIC). No practising lawyer has
  reviewed output (H-001, open since 2026-09-04).
- **No figure from another system is a figure for this one.** For example, INLegalLlama's
  reported ~90% F1 [S] is a measurement of a different task on different data (see 04 §5).
- **No claim about Palantir's internals** beyond its own public documentation.
- **aclanthology.org, ecourts.gov.in and devdatalab.org were egress-blocked from this
  environment, and no publisher page was fetched successfully.** Every source new to this plan
  is therefore **[S]**: located by web search, with title, authors and venue agreeing across
  several results. Sources an earlier plan already recorded as [V] keep that tag. Anything
  headed for a publication, a pitch deck or a customer is read in full by a person first.
