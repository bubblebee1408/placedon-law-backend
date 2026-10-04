# PLAN_15 — building the Themis terminal: feeds, model, and the non-digital moat

Written 2026-09-17, answering: *how do we actually develop the Bloomberg terminal
for lawyers, what live data pipeline feeds it, what must the model be good at, and
what do we do about the fact that most Indian legal data is not digital.*

**Read §0 first.** This is the fifteenth planning document in `docs/`. It is
written as a build spec — schemas, owners, done-when — precisely because
`FAILURE_MODES.md` warns that this repository's characteristic failure is producing
excellent prose instead of movement.

---

## 0. The finding that reframes the question

**You already have the terminal. You do not have the ticker.**

The defining feature of a terminal is not analytics — it is the alert that arrives
without being asked. Themis has the machinery that *computes* that alert and no way
to *deliver* it:

| Terminal organ | Themis module | State |
|---|---|---|
| Identity spine | `entity_graph.py` — CIN/DIN, statutory and universal | **BUILT** |
| Time axis | `as_of.py`, `amendment.py`, bitemporal `event_log.py` | **BUILT** |
| The reverse index — *instrument lands → which obligations move* | `currency.affected_by()`, `event_log.affected_by()` | **BUILT** |
| Staleness detection | `staleness.py`, `currency.py` | **BUILT** |
| Uncertainty done honestly | `mca_snapshot.py` blindness windows | **BUILT** |
| **Subscriptions and delivery** | — | **MISSING. This is F5's entire stated gap** |
| **A watcher on the Gazette** | — | **MISSING. This is D-1** |

`FEATURES.md` F5: *"Status: ENGINE BUILT — `affected_by()` is the reverse index.
Missing: subscriptions and delivery."*

So the question "how do we build the Bloomberg terminal for lawyers" has a much
smaller answer than it looks: **build the two missing organs, and it is a
terminal.** Everything else in this document is detail on those two.

---

## 1. Your list of data axes, triaged

You named eight axes. They are not one problem; they are three, and only one is
the product.

| Axis you named | Verdict | Why |
|---|---|---|
| **Documents signed by the government** (Gazette, GSR/SO instruments) | ✅ **BUILD. This is the product** | Free, public, permitted by `CLAUDE.md`. Acquisition path already exists (`register_gsr700e/880e.py`) |
| **New laws passed, amendments, commencements** | ✅ **BUILD. Same feed** | The reverse index already consumes exactly this |
| **Listed-company disclosures / financial reports** | ✅ **BUILD, second** | `CLAUDE.md` permits "public listed-company disclosures". BSE/NSE announcements carry board outcomes, RPT disclosures, Reg 30 events |
| **Which startups got funded** | ⚠️ **Only via its statutory trace** | Tracxn/Crunchbase are proprietary. But **PAS-3 (return of allotment)** and **SH-7** are the MCA filings a funding round *must* produce. Reach it through the registry, not the press |
| **MCA corporate data** (CIN, DIN, directors, charges) | ⚠️ **Contract, not code** | `corporate_data.py` + `mca_aggregator.py` are built and **refuse until a licensed provider is wired**. MCA21 has no public API |
| **Live financial market data** | ❌ Off-wedge | A compliance buyer is not paying for prices. Licensed benchmarks the physical trade contracts against are not available anyway |
| **Ship tracking (AIS)** | ❌ **Measured dead** | PLAN_08 §5: no source is simultaneously global, real-time and redistributable at startup cost. **India has no free terrestrial AIS at all** |
| **Oil production** | ❌ Off-wedge | EIA and World Bank Pink Sheet are free and clean, but this is a commodities product with a different buyer |

**The three ✅ rows are a genuine live data pipeline.** They are free or cheaply
licensed, legal under the source policy, and they land directly on the wedge. The
❌ rows have been measured three times and the answer has not changed.

### 1.1 What the ✅ feeds actually answer

This is the part that makes it a terminal rather than a database:

| Feed | The question it answers | The alert it fires |
|---|---|---|
| Gazette | *Did the law under this document change?* | "G.S.R. 880(E) landed. 4 of your obligations moved. 12 client documents are now stale." |
| MCA registry | *Did the company change?* | "A charge was registered against your counterparty on 3 March." |
| Listed disclosures | *Did the counterparty change?* | "Board approved an RPT under s.188 that your matter depends on." |

Cross those three against the obligation register and you have
**obligation × entity × date** — which is the whole terminal.

---

## 2. The feed architecture

Ports the `server/providers/` shape from God's Eye into Python (PLAN_14 §4), with
two fields that repo would not have taught us.

```
checker/feeds/
    __init__.py          the Feed protocol
    common/
        fetch.py         one HTTP path, through checker/robots.py -- fails closed
        cache.py         on-disk, hashed, dated: an observation is an artifact
        rate.py          per-source governor
    gazette.py           FEED 1 -- egazette / India Code DSpace
    listed_disclosures.py FEED 2 -- BSE/NSE announcements
    mca.py               FEED 3 -- wraps the existing mca_aggregator seam
```

### 2.1 The `Feed` protocol

Every adapter carries seven fields. The last three are the ones that make this
Themis rather than a scraper:

| Field | Purpose |
|---|---|
| `source_id` | Named source. An unnamed observation is not evidence |
| `fetch()` → bytes + `sha256` | Hash the artifact, as `acquisition_log` already does |
| `parse()` → `Observation` | **Never** a `VERIFIED_FACT`. Ring 2 output only |
| `observed_at` | Bitemporal `known_at`, feeding `event_log` |
| **`licence`** | **Axis D.** May this be shown to a paying customer? |
| **`source_behaviour`** | How the source behaved, *including a refusal*. A 404 is evidence of nothing |
| **`blindness`** | FLOOR / CEILING / EITHER, per `mca_snapshot.py`. See §2.3 |

### 2.2 Axis D per feed — settle this before writing code

| Feed | Licence position | Servable to a paying customer? |
|---|---|---|
| eGazette / India Code | Government of India official publication | **Yes** |
| BSE/NSE announcements | Public listed-company disclosure; permitted by `CLAUDE.md` | **Yes**, with attribution |
| Licensed MCA aggregator | Contractual; terms govern redistribution | **Per contract.** Never described as "MCA-authorized" — no vendor's claim could be verified against any published MCA list |
| OFAC SDN | US public domain | **Yes** |
| OpenSanctions | ~€0.10/call, explicit reseller tier | **Yes**, under that tier |
| Anything CC BY-NC | NonCommercial | **Never.** Ingestible for internal reasoning only |

### 2.3 The feature that makes live data honest — and it is already built

`mca_snapshot.py` is the most under-used module in the repository and it is the
answer to "how do we make live data accurate":

> *"The registry does not hold events; it holds filings, and the Act itself grants
> the company a window between the two. A fetch that is fourteen minutes old is
> still reporting a world that may be sixty days out of date."*

So instead of a freshness badge, every live value carries **blindness and
direction**:

```
FLOOR    the truth is at least this value   (an unfiled creation)
CEILING  the truth is at most this value    (an unfiled satisfaction)
EITHER   both failure modes are open
```

**`Active Charges: 0` is not "unencumbered."** Under s.77 a charge created up to
sixty days ago may lawfully be unregistered, so zero is a FLOOR.

That single distinction is the difference between a green chip and a correct one —
and it is what a competitor's "Synced 14m ago" badge gets wrong. **Every value in
the terminal UI must render its blindness. No exceptions.**

---

## 3. The model: what it must be good at

You named three capabilities. Two are built or prototyped. One is refused, and has
three honest substitutes.

### 3.1 Research — BUILT, needs surface

`model_adapter.py` is the safety spine (four refusals before any call). PLAN_13's
Ask section is specced, prototyped and passing **185/185 acceptance checks across
five widths**. The `/v1/ask` contract is validated and gated.

**Gap:** the red team (UX-V) is unfinished and `accept.mjs` is uncommitted.
Finishing it is measured in days, not months.

### 3.2 Legal conversion / drafting — BUILT, needs breadth

`drafting.py` + `provenance_slots.py`, **one template** (AGM notice). Every slot is
provenance-tracked. The architecture is right; the library is thin.

**This is the F1-adjacent commercial surface** — and note the wedge argument:
generation is commoditised (ComplyRelax is free to ICSI members until 2029), but a
customised template *stops receiving legal updates*. Drafting with live currency
attached is the differentiator; drafting alone is not.

### 3.3 Prediction — REFUSED, and here is what to build instead

**Do not build a legal outcome predictor.** This has been decided twice on
evidence, and PLAN_14 §5 records the arithmetic. The short version: the amendment
corpus holds **~6 amending events**, so "will Parliament amend this section" has
n_eff ≈ 6, where a *perfect* forecaster's error floor is 0.098. No data
acquisition fixes it.

**But "prediction" is three different products, and two of them are buildable:**

| What you probably mean | Honest form | Status |
|---|---|---|
| "When is this due?" | **Arithmetic on statutory deadlines.** s.77's 30-day charge window, AGM due dates under s.96, DIN KYC, s.139 auditor terms. A date the statute fixes is not a forecast — it is a calculation, and it is exact | **BUILD. Highest value per line of code in this document** |
| "How wrong could this be?" | **Blindness windows** (§2.3). Direction + magnitude, from the Act's own filing windows | **BUILT** (`mca_snapshot.py`), needs wiring into every surface |
| "Will this section change?" | **Conditional volatility** — not *"will Parliament amend this"* (n_eff ≈ 6, dead) but *"is this the kind of section that moves"*, which survives at **n_eff ≈ 261 section-years** | Buildable, but gate it behind `calibration_contract.py` |

**The reframe worth internalising:** a compliance buyer does not want a
probability. They want a **date they will be liable on** and an honest statement of
what you cannot see. Deadline arithmetic plus directional blindness beats a
confident percentage, because a percentage is what opposing counsel takes apart and
a statutory deadline is not arguable.

Anything numeric beyond those three passes `calibration_contract.py` or does not
render. That module exists and is expected to refuse most things.

---

## 4. "Most of the data is not digital" — this is the moat, not the obstacle

This is the sharpest thing in your question and it deserves the direct answer:
**you have the causality backwards, and in your favour.**

If Indian corporate legal data *were* clean and digital, the aggregation play would
work — and the best-funded entrant would win it. Harvey has SCC Online (signed Jan
2026) and far more capital. In a digital-corpus world, you lose.

Because the data is **not** digital, the winner is whoever builds the
acquisition-and-attestation pipeline. And that is the thing this repository already
is:

| The non-digital problem | The asset that answers it | State |
|---|---|---|
| Instruments are PDFs, some scanned | `acquisition_log`, hash + `--attest`, `register_*.py` | **BUILT — 6 instruments registered** |
| Scans carry OCR errors into figures | 17 pages found and **preserved verbatim, never repaired** | **MEASURED** |
| Bulk documents are 500-page mixed bundles | PLAN_12 intake architecture, 43 red-team findings fixed | **DESIGNED** |
| Page-anchored citation | **BLOCKED on D-002** — the page reader agrees with an independent reader on 0 of 14 files | **THE BOTTLENECK** |

**The strategic claim, stated plainly:** *Themis's moat is not its model. It is a
verified acquisition pipeline over a corpus nobody else has bothered to digitise
correctly — and the discipline to refuse when the digitisation failed.*

That claim is only true while the pipeline works. **D-002 is therefore not a bug,
it is the moat's load-bearing wall**, and it is currently broken.

---

## 5. Build order

Nothing here jumps H-C. Phase 0 is the existing critical path and is unchanged.

### Phase 0 — unblock (no new features)

| # | Task | Done when |
|---|---|---|
| 0.1 | Commit `accept.mjs`; finish UX-V / UX-M | Gate green, tree clean |
| 0.2 | **Decide D-2** — fix the stdlib page parser or adopt a library | Decision + reason recorded |
| 0.3 | Fix the page reader | Two-reader census agrees on ≥13 of 14 |
| 0.4 | Re-extract the Board Rules; regenerate `review_brief.md` | Split-word counts ≈ 0 |
| 0.5 | Human review of the 30 items | Decisions recorded; s.177 stops refusing |
| 0.6 | **H-C** — one Company Secretary reacts | Written reactions captured |

### Phase 1 — the ticker (this is the terminal)

| # | Task | Done when |
|---|---|---|
| 1.1 | **`checker/rings.py`** — the one-way firewall, AST-enforced | A Ring 0 module importing upward fails the gate |
| 1.2 | **The release chokepoint** — six SERVABLE paths → one registry | A seventh path cannot serve |
| 1.3 | **`checker/feeds/`** — protocol + `common/`, no live source | Offline fixtures only |
| 1.4 | **Gazette watcher** — closes **D-1** | A test fails when the newest amendment is older than a stated threshold |
| 1.5 | **Subscriptions + delivery** — F5's stated gap | An instrument lands → `affected_by()` → a dated, sourced alert naming the obligations and documents |
| 1.6 | **Deadline arithmetic** (§3.3 row 1) | s.77 / s.96 / DIN KYC dates computed and shown with their statutory basis |

**1.4 + 1.5 together are the product.** Everything before them is plumbing and
everything after is expansion.

### Phase 2 — the other two feeds

| # | Task | Gate |
|---|---|---|
| 2.1 | Listed-company disclosures feed | Axis D: attribution recorded |
| 2.2 | OFAC SDN — the easiest possible Axis D, as the pipeline shakeout | Observation attaches to an entity, refuses to enter a decider |
| 2.3 | Licensed MCA aggregator | **Contract first.** `mca_aggregator.py` already refuses without it |
| 2.4 | Blindness rendered on every live value | No value renders without FLOOR/CEILING/EITHER |

### Never

Ships, oil, market prices, outcome prediction, any model-authoritative labelling.

---

## 6. What this document does not claim

- **It authorises nothing ahead of H-C.** Phase 1 is written so the day after that
  conversation the work is a configuration rather than a design exercise.
- The PAS-3 / SH-7 funding-trace idea (§1) is **INFERRED**. That these forms are the
  statutory residue of a funding round is reasoning, not a sourced finding, and the
  filing-window blindness would be substantial.
- No cost estimate is given for the licensed MCA feed. PLAN_08 §5's $300–600/month
  covered the *register* stack, not an MCA21 aggregator contract.
- The claim that finishing UX-V is "days, not months" is **INFERRED** from the work
  remaining, not from a measured estimate.
