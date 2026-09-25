# 07: Investor brief: what Placedon is building, and what it refuses to build

*Two pages. Every figure below is either measured in the repository or marked as not measured.*

## The problem

Indian corporate law changes by notification, and the change is not reflected where lawyers
read the law.

- **Our own engine did this.** It served a superseded small-company threshold as current for
  nine months (PLAN_00).
- **So do the sites lawyers read.** Four of the most-read Indian compliance sites checked still
  published the 2022 figure; one published a figure that never existed.
- **Legal AI tools hallucinate.** A preregistered study (Magesh et al., *Journal of Empirical
  Legal Studies*, 2025) measured commercial legal AI research tools hallucinating 17–33% of the
  time.

## The product

Placedon is **an evidence layer for Indian corporate law.** Given a question or a document, it
answers only with:

- the exact provision;
- the instrument that last changed it;
- the date it took effect;
- the evidence state of each of those.

**It abstains when it cannot verify.** For law it does not hold, it says which body of law
governs and that it has not been acquired. It never gives an empty answer that reads as "no
obligation".

PLAN_19 extends it from **answering** to **watching**:

- **Replay.** Every answer can be reproduced exactly as given on its date.
- **Recall.** Every answer that rested on a source since withdrawn can be listed.
- **Alerts.** Gazette changes are watched against a client's companies, and each alert states the
  chain of reasons it fired.

## Why "Gotham for lawyers" is the right analogy, and where it stops

Palantir's public patents and documentation describe four ideas worth copying:

- a typed object model every source maps into;
- provenance and access marking on every property;
- composites that inherit their most restrictive input;
- graph and timeline views over one object set.

Placedon already enforces the equivalent for the statute. This plan extends it outward.

**Where the analogy stops:** Gotham's moat is integrating many sources its customers may lawfully
access. In India, the sources a market-wide legal Gotham would need are closed, or forbid machine
reuse:

- MCA21 has no API;
- NSE's terms prohibit automated collection;
- shipment-level trade data is not released by the government;
- the national court-data API is open only to government.

**No company can build that integration moat here at startup cost.** The moat that *can* be
built is discipline: every fact typed, dated, sourced, licensed, and refused when any of those is
missing. It is harder to copy than a data feed, because it lives in every line of the engine
rather than in a contract.

## What exists today (measured, 2026-09-25)

| Component | Status |
|---|---|
| Companies Act 2013 corpus | 529 sections, hash-stamped; section index verified against India Code's own API, 12/12 MVP sections, 0 mismatches |
| Deterministic engine | 8 HTTP routes; a pre-commit gate running every self-testing module (195 suites per `CLAUDE.md`, 2026-09-25) |
| MCP server | 13 read-only tools, usable from Claude and other MCP clients |
| Live feeds | eGazette, OFAC SDN, IBBI |
| Gold set | 73 questions; **0 human-labelled**. So **there is no accuracy figure, and we do not publish one** |

## What we will not build, and why that is a strength

| Asked for | Decision | Reason |
|---|---|---|
| Live stock-market data (NSE) | Not without a licence | The exchange's terms prohibit scraping; market data for commercial use is licensed |
| Import/export shipment data | No | The provenance of the data and the terms of the site offering it could not be established |
| Judgment prediction | No | Most published "prediction" research does not predict (Medvedeva and McBride, 2023). The data cannot support a calibrated number. It is off-wedge |
| A confidence percentage on answers | No | It would be a number with no measured basis. Abstention is shown instead |

## The next eighteen months, as claims we will be able to make

| After | Claim |
|---|---|
| G0 | Refuses unheld law even when the Act is not named, measured on a held-out set |
| G1–G2 | Replay and recall, as above |
| G3 | Gazette watch against a client's companies, every alert with its reasons |
| G4 | One engine: CLI, API, and inside Claude, Copilot or Harvey via MCP |
| G5 | Supreme Court citator: has this authority been overruled, within the corpus held |

## Risks we state before you ask

1. **No practising lawyer has yet reviewed an output** (H-001 is open). This outranks every
   technical item.
2. **Copyright Act s.52(1)(q)(ii).** Whether an AI product's analysis is "commentary or other
   original matter" is a question for counsel, and the corpus rests on it.
3. **An incumbent could ship dated-instrument tracking as a feature.** PLAN_00 lists this as a
   thesis-falsifier.
4. **Demand is unproven.** The wedge (in-house legal teams) is a founder decision, not a measured
   market.

*Sources: PLAN_00, PLAN_08 §5, PLAN_14 §3, PLAN_16 §2,
`docs/research/DATA_ACCESS_AND_CONNECTORS_2026_09_25.md`,
`docs/research/GOLDSET_FIRST_RUN_2026_09_25.md`, and docs/plan19/01–04.*
