# PLAN_19: a Gotham-grade workbench for Indian corporate lawyers, on Themis

Written 2026-09-25 against `main` at `6cdb109`. Nine documents. This plan extends PLAN_16
(research), PLAN_17 (beta milestones M0–M12) and PLAN_18 (technical design). It does not
replace any of them. Where they already decide something, this set cites the decision and
does not restate it.

## The request, stated exactly

The founder asked for a "Palantir Gotham for lawyers" built on Themis, with seven parts:

1. an integration path from API through MCP to CLI;
2. algorithms from GitHub and Hugging Face;
3. research papers, neural-network development, and new maths and algorithms that can be proved;
4. how Gotham was built, from public material;
5. a terminal with the density of Bloomberg Law;
6. monitoring across shipments (Zauba), the stock market (NSE), international news, and case law;
7. judgment prediction.

The founder also set the standard. The plan must be accurate, every line must be understood,
it must be arranged in shells, and it must be readable by senior engineers and investors. It
must be buildable step by step by Claude Code subagents under `/loop`.

## The verdict, before the detail

| Part | Verdict | Why, in one line | Where |
|---|---|---|---|
| Gotham's architecture | **TAKE the mechanisms, not the product** | Its load-bearing ideas are a typed object model, provenance on every property, access markings that join upward, and replicated analysis. Each maps onto a module that already exists here | [01](01_GOTHAM_FROM_PUBLIC_SOURCES.md) |
| API → MCP → CLI | **BUILD**, as one verb table generating three surfaces | Three hand-written surfaces drift apart. One table with a parity test cannot | [03](03_ARCHITECTURE.md) §6 |
| Terminal | **BUILD**, after the verb table | A terminal is a grammar over the verb table plus a dense renderer. Bloomberg's density is a UI property, not a data property | [03](03_ARCHITECTURE.md) §7 |
| Case law | **BUILD a citator, not a predictor** | The question "is this judgment still good law?" is deterministic over a citation graph and on-wedge. Its free source is CC-BY-4.0 | [02](02_SOURCES_AND_FEASIBILITY.md) §5 |
| International news | **BUILD as Ring 2 context only** | GDELT permits commercial use with attribution. News is never legal authority | [02](02_SOURCES_AND_FEASIBILITY.md) §4 |
| NSE / stock market | **DO NOT BUILD on scraping.** Only a licensed feed | NSE's terms prohibit automated collection, and commercial use of market data is licensed | [02](02_SOURCES_AND_FEASIBILITY.md) §2 |
| Zauba shipments | **DO NOT BUILD** until provenance and terms are shown | DGCI&S does not release shipment-level data. Where Zauba's comes from is unknown, and its terms could not be read from here | [02](02_SOURCES_AND_FEASIBILITY.md) §3 |
| Judgment prediction | **DO NOT BUILD** | The data cannot support a calibrated number, the literature says most "prediction" is not prediction, and it is off-wedge | [04](04_MATHS_AND_ALGORITHMS.md) §7 |
| New maths | **Four results worth building**, none claimed as novel mathematics | Evidence states form a semiring, so revocation is re-evaluation rather than re-query. Also: tri-state soundness under time, a sample-size gate on every "it got better", and a bound on the false-alarm budget | [04](04_MATHS_AND_ALGORITHMS.md) |
| Neural networks | **Small, supervised, human-labelled, later** | No foundation model. A reranker and two classifiers, trained only when the maths in 04 says the labels exist | [04](04_MATHS_AND_ALGORITHMS.md) §8 |

The whole thesis in one sentence: **Gotham's value is not the globe. It is the rule that every
fact on screen carries where it came from, who may see it, and when it was true.** Themis already
enforces that rule for the statute. This plan extends it outward, one source at a time, and
refuses every source that cannot carry it.

## Reading order

| # | Document | Audience | Status of its claims |
|---|---|---|---|
| 00 | This index | everyone | — |
| 01 | [Gotham from public sources](01_GOTHAM_FROM_PUBLIC_SOURCES.md) | engineers, investors | Patents and vendor docs, located 2026-09-25; patents read at abstract/claim-summary level |
| 02 | [Sources and feasibility](02_SOURCES_AND_FEASIBILITY.md) | founder, counsel | Each source carries a tag; two were egress-blocked |
| 03 | [Architecture](03_ARCHITECTURE.md) | engineers | Built parts tagged [R] (read in the repo today); new parts are designs |
| 04 | [Maths and algorithms](04_MATHS_AND_ALGORITHMS.md) | engineers, reviewers | Proofs given in full where they are short; every number was recomputed here |
| 05 | [Roadmap](05_ROADMAP.md) | everyone | Phases G0–G7 with entry and exit gates, interleaved with PLAN_17 M-numbers |
| 06 | [Loop prompts](06_LOOP_PROMPTS.md) | Claude Code | One prompt per step, with a subagent, a definition of done, and stop conditions |
| 07 | [Investor brief](07_INVESTOR_BRIEF.md) | investors | Two pages. No metric that has not been measured |
| 08 | [Self-critique](08_SELF_CRITIQUE.md) | founder | What would make each part worthless, and the kill criterion for each |

## Tags used throughout

| Tag | Means |
|---|---|
| **[R]** | Read in this repository on 2026-09-25, file and line given |
| **[V]** | Located and confirmed from a primary or publisher page on 2026-09-24/25, at abstract or summary level. Not read in full unless it says so |
| **[S]** | Seen only in a search-engine summary. Treat as a lead, not a fact |
| **[I]** | Inference: my reasoning, not a source |
| **[OPEN]** | Not established. Do not build on it |
| **[BLOCKED]** | Needs a human act, a contract, or counsel |

## What this set does not claim

- **No accuracy figure.** The gold set holds 0 human labels (`eval/goldset/`, first run
  2026-09-25). No number here is a measure of Themis's correctness.
- **No claim about Palantir's internals** beyond what its patents and its own public
  documentation state. "Gotham does X" means "Palantir's public material says X".
- **No claim of novel mathematics.** Section 04 applies known results (Green–Karvounarakis–Tannen
  provenance semirings, Fellegi–Sunter, conformal inference) to a setting where we have not found
  them applied. That is an engineering contribution. Whether it is publishable depends on a
  literature search a person has not yet done.
- **arxiv.org was blocked from this environment** (as it was for PLAN_16). Every arXiv citation is
  therefore [V] at best, via a publisher or proceedings page.
