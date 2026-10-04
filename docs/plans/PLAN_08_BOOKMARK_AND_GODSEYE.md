# Bookmark and God's Eye — architecture, and what the evidence permits

Written 2026-09-11 on the founder's explicit instruction to build the Bloomberg
layer ("Bookmark") and the live-telemetry layer ("God's Eye"), and to design the
tag system accordingly.

**This document supersedes** `BLOOMBERG_FOR_INDIA_ANALYSIS.md` §3.3 and §A.5, and
`PLAN_05_ROADMAP.md` "Why God's Eye as originally conceived is the wrong shape" —
but **only in part, and not in the direction expected.** Those documents rejected a
*globe*. This one rejects the globe too, on stronger evidence, and proposes an
*evidence engine* in its place. Where they were right they are restated, not
overturned; the register of what changed is §7.

---

## 1. The thesis

Placedon is not a statute engine. It is an **evidential record engine** that
happens to be pointed at statute. Its primitives are: acquire from a named source
→ hash the artifact → record how the source behaved → grade the evidence → require
human attestation → serve only if SERVABLE → answer point-in-time, and name what
is unknown rather than interpolate across it.

Point those same primitives at a public register or a price series and the machine
does not change. Only the corpus changes.

A court has already stated the product. Delhi Commercial Court, 2026: **force
majeure must be proved by cogent evidence, not mere newspaper reports** — a claim
failed because the party relied on press reporting rather than contemporaneous
evidence. A dated, hashed, source-attributed record *is* the cogent evidence.

The same authority bounds it: **price risk is a commercial risk parties accept at
signing.** Volatility is not force majeure. So the value is in proving
retrospectively what a fact WAS, never in forecasting what it WILL BE. Evidence is
the wedge; prediction is a separate, degradable, tagged layer that mostly refuses.

---

## 2. Four rings and a one-way firewall

```
 RING 0  LEGAL CORE      [BUILT]  statute, obligations, deciders, currency, entailment
                                  emits VERIFIED_FACT | DETERMINISTIC_CONSEQUENCE
 ───────────────────────────── FIREWALL (one-way) ─────────────────────────────
 RING 1  BOOKMARK        [MOSTLY] entity graph (CIN/DIN), public registers, event log
 RING 2  GOD'S EYE       [NEW]    observations from named feeds -> OBSERVATION
 RING 3  INFERENCE       [NEW]    ordinal ASSESSMENT; numeric ESTIMATE only if calibrated
```

A module in Ring N may import from rings below it. **No Ring 0 decider may import,
read, or receive any value originating in Ring 2 or Ring 3.** A forecast may never
be an input to a deterministic legal decision.

Enforce it mechanically, the way `api.py:644-654` already asserts the API imports
no model library: `checker/rings.py` declares each module's ring and its `_test()`
walks every Ring 0 module's AST, failing on an upward import.

Why structural rather than conventional: the product's value claim is that **a
wrong model cannot make the product wrong** (`CODING_CONVENTIONS.md:14-15`). A
probability leaking into an applicability decision destroys that property
*silently*, because the output still looks deterministic.

---

## 3. The prerequisite: there is no release chokepoint, and there must be

"Only SERVABLE reaches a user" is currently reimplemented in **six** places under
**two** vocabularies:

| # | Location | Vocabulary |
|---|---|---|
| 1 | `evidence_pack.py:400-413` `usable_for_answering` | provenance.SERVABLE |
| 2 | `prescribed_thresholds.py:64-66,261` | provenance.SERVABLE |
| 3 | `assessment.py:411-423` `servable_conclusion` | CONCLUSIVE_STATUSES=(ADMITTED,) |
| 4 | `admission.py:55,114,142` | **separate** (PRODUCTION_USABLE, …) |
| 5 | `event_log.py:105-108` | verified_by invariant |
| 6 | `s188_threshold.py:51-52,118,130` | hand-rolled `state in SERVABLE` |

No shared base class, no registry, no adapter. The single bridge between the
evidence axis and the output-class axis is one property
(`prescribed_thresholds.py:64-66`) consumed at `event_log.py:152,163,166`.

**A new subsystem therefore inherits none of the discipline.** Telemetry would
bypass all six, and no test would notice, because every gate is tested per module
and there is no cross-cutting invariant suite.

So: `checker/release.py` — one `may_release(...) -> Release`, where `Release` is a
frozen `(allowed: bool, reason: str)`, never a bare bool, because the reason is
what must be shown when it refuses. Migrate one call site per commit, each proving
behaviour unchanged, then mutate to prove the gate is load-bearing.

**Nothing in Ring 2 or Ring 3 may be built before this lands.**

---

## 4. The tag system — a fourth axis

Three axes exist and are layered but not composed: **A** evidence state
(`provenance.py:28-36`), **B** accessibility (`:41-46`), **C** output class
(`event_log.py:49-52`).

### Axis D — LICENCE / REDISTRIBUTION (new, non-optional)

Nothing records whether we are *allowed* to show a value to a paying customer. For
statute that was safe; the Gazette is public. For God's Eye it is fatal — the
source audit confirms Platts, Argus, ICE/CME settlement and MCX are licensed IP
(Argus's terms: *"you may not conduct text or data mining or web scraping … for
any purpose"*), and `SOURCE_POLICY.md:29` already records that RBI prohibits
commercial use **and caching**.

```
INTERNAL_ONLY   may compute with it; may never render it
MAY_SHOW        may render the value to an entitled customer
MAY_STORE       may persist beyond the session
MAY_DERIVE      may publish a figure derived from it
EMBARGOED       held, not releasable until a stated datetime
```

These are **capabilities, not a ladder.** A feed may be MAY_SHOW but not MAY_STORE
(a display-only quote), or MAY_STORE but not MAY_SHOW (a licensed input usable
only to compute a derived figure). So Axis D is a frozenset per feed, not an
ordinal state — treating it as a ladder would repeat exactly the error
`provenance.py:38-40` documents about conflating evidence with accessibility.

Licence is **attested like statute is attested**: a human records, once per feed,
what the contract permits, with its reference and date. The default for an
unregistered feed is the **empty** frozenset — it may not even be computed with.
Fail closed, as `robots.py:11-13` does.

### Axis C extended — each new class arrives WITH its invariant

The existing invariant (`event_log.py:105-108`) guards only `VERIFIED_FACT`. A new
class ships with no invariant unless one is written, which is precisely how a
discipline erodes. So:

**OBSERVATION** — a measured value from a named feed at a named time. Requires a
registered `feed_id`; **both** `observed_at` and `ingested_at` (the two clocks are
never merged); a `chain_hash`; a non-empty licence set. **May never be
VERIFIED_FACT** — feed-level attestation is not per-datum attestation and must not
be allowed to impersonate it.

**ESTIMATE** — a number. Requires a live calibration record (§6) or the
constructor degrades it to an ordinal ASSESSMENT. Never bare.

Note `event_log.py:109-113` treats `known_at < at` as `pass`. For a forecast that
is the *normal* case; for an observation it is a clock error. The rule must be per
output class from the start.

---

## 5. What the source audit permits — and forbids

Audited 2026-09-11 against actual terms and published pricing.

### God's Eye as literally conceived is not legally buildable at startup cost

No source is simultaneously global, real-time and redistributable to customers.
NOAA and Danish Maritime open AIS are free and clean but **coastal only** (~40–70nm
from shore). Global Fishing Watch is **CC BY-NC**. VesselFinder's terms ban resale,
redistribution and building substitute analytics. AISStream.io has an open,
unanswered question about commercial licensing, so no documented permission exists.
Spire/Kpler/Windward are enterprise-only, indicatively $2,000–8,000+/month.

Three findings make India the **hardest** market for this, not the easiest:

1. **India has no free or open terrestrial AIS feed** — no Coast Guard or DG
   Shipping equivalent of NOAA. Even the coastal fallback has no Indian version.
2. **DGCI&S does not disseminate shipment-level Indian trade data at any price.**
   A stated policy wall, not a pricing gap. The US publishes ocean Bills of Lading
   as public record; India does not.
3. Terrestrial AIS is worst exactly where a dark-fleet narrative needs it most —
   vessels go dark in open water, beyond terrestrial range.

### The pattern, now three for three

| Bloomberg mechanic | US substrate | Indian reality |
|---|---|---|
| Clause benchmarking | EDGAR full-text exhibit filing | SEBI: "significant terms **(in brief)**" |
| Shipment tracking | Bills of Lading are public record | DGCI&S withholds by policy |
| Corporate data API | EDGAR free public API | MCA21 has **no** official public API, even V3 |

**Bloomberg-style products are downstream of US disclosure mandates that
manufacture public corpora. India runs summary-disclosure regimes, not
record-filing regimes.** The data-aggregation play cannot be won in India by
anyone, at any funding level. The defensible play is verification and currency over
the one dense public corpus that does exist — the statute. Which is what is built.

### What IS buildable, cheap, legal, and on-wedge

A **counterparty risk-and-status overlay on the entity graph**, from official
Indian public registers plus international sanctions lists:

- MCA's own **Defaulter Companies** list; struck-off companies; disqualified directors
- **SEBI debarred entities** — published by NSE as downloadable `.xls`
- **IBBI** corporate-debtor master data and public announcements
- **RBI suit-filed wilful defaulters**, published annually as at 31 March
  (caveat: RBI runs no searchable public database; it is a classification banks apply)
- **OFAC SDN** free and public domain; **OpenSanctions** at €0.10/call with an
  explicit **reseller tier** — they have already solved "may I show this to a
  paying customer", which is Axis D priced

This lands on the existing wedge: s.185 loans to related parties, s.188 related-party
transactions, beneficial ownership. It fuses with Ring 1 instead of bolting a second
product to the side. Total legal stack roughly **$300–600/month**, excluding vessel
tracking.

Price evidence survives narrowly: **EIA** and **World Bank Pink Sheet** are free and
clean; PPAC gives the Indian crude basket. The licensed benchmarks the physical
trade actually contracts against are not available, and a sophisticated buyer will
see the gap.

### One thing never to do

No third-party MCA vendor's "MCA-authorized" claim could be verified against any
published MCA list. If one is used, disclose it as *"aggregated from public MCA
filings via a commercial data vendor"* — **never "MCA-authorized"**. Making an
unverifiable claim to compliance buyers is the one reputational hit this product
cannot take.

---

## 6. Ring 3 — mostly a lattice, rarely a number

**L-15 governs** (`.claude/memory/LESSONS.md:290-314`). A Bayesian engine was built
here, audited and deleted: calibration was unreachable at the available n. The
verdict on its author's own work — *"I fixed the arithmetic and kept the
fabrication"* — is the standard any new proposal must meet.

The audit's arithmetic is now reproducible as an instrument rather than an anecdote:

```
    ECE_floor(p, n) = E|k/n - p|,  k ~ Binomial(n, p)      <- compute EXACTLY
    n_min(p, eps)   = ceil( 8 p (1-p) / (pi eps^2) )

    ECE_floor(0.90, 20) = 0.0513    <- a PERFECT model fails a target of 0.05
    ECE_floor(0.10,  6) = 0.1063
    n_min(0.50, 0.05)   = 255
    Wilson(19, 20)      = [0.764, 0.991]
```

**Use the exact binomial sum, not the normal approximation.** The closed form
`sqrt(2p(1-p)/(pi n))` is convenient and wrong in the direction that matters:

| n, p | exact | normal approx | error |
|---|---|---|---|
| 20, 0.90 | 0.0513 | 0.0535 | +0.0022 (overstates) |
| **6, 0.10** | **0.1063** | **0.0977** | **-0.0086 (UNDERSTATES)** |
| 20, 0.50 | 0.0881 | 0.0892 | +0.0011 |
| 49, 0.90 | 0.0340 | 0.0342 | +0.0002 |

At n=6 the approximation understates the floor by 9%, making a hopeless target
look merely difficult — and small n is the only regime where this instrument is
ever consulted. `comb()` is in `math`; the exact sum costs nothing and cannot
mislead in the unsafe direction.

Applied to this corpus, two findings decide the layer:

- **The amendment corpus holds ~6 amending events, not 431.** Six amending Acts
  carry 307 of 348 instrument mentions. So "will Parliament amend this" has
  n_eff ≈ 6, where `ECE_floor(0.1, 6) = 0.098` — **permanently dead; no data
  acquisition fixes it.** The *conditional* question ("is this the kind of section
  that moves") survives at n_eff ≈ 261 section-years.
- Therefore Ring 3's **default output is ordinal**: an `ASSESSMENT` with the
  weakest link named. `max` needs no joint distribution; multiplying probabilities
  across a section, its qualifying rule and the reviewer who attested it asserts
  independence between maximally dependent things.

`ESTIMATE` is the exception, permitted only where the minimum n is stated, exists
in reality, and measured skill beats the naive baseline.

`metric_policy.py:96-160` cannot score a forecast — `predict(row) -> bool | None`,
four binary axes, no continuous path. Do not quietly widen it; that gate's whole
argument is that those four axes are what stop a useless configuration passing.

---

## 7. Register of what changed, and what did not

| Prior position | Status |
|---|---|
| §3.3 "God's Eye is scope creep in a costume" | **UPHELD on stronger evidence.** The globe is refused; the licensing audit independently reaches the same place |
| §A.5 "forking gods-eye-view is near-zero value" | **UPHELD** |
| §A.2 "case law never as prediction" | **UPHELD**; extended — most prediction is refused, per L-15 |
| PLAN_05 "the telemetry that matters is Gazette and filings, not moving objects" | **UPHELD, and sharpened**: the buildable telemetry is public *registers* |
| "God's Eye is a separate bet with a separate buyer" | **SUPERSEDED IN PART.** A risk-register overlay is the same buyer and the same wedge. Vessel tracking remains a separate bet, now with a price attached |
| Bookmark / entity graph | **UPHELD as the transferable pillar** |

**Unchanged and still blocking:** H-C — one practising Company Secretary reacting
to the evidence pack that already exists. Everything in this document is ahead of
that gate. That is the founder's decision, recorded here rather than obscured.

---

## 8. Two live defects found while writing this

**D-1 — the amendment corpus stops in 2023.** Amendment years present run
2014–2023 (2022: 2 records, 2023: 1); **2024, 2025 and 2026 are entirely absent.**
Either the Act has not moved in three years or the footnote ledger is stale, and
**nothing is watching**. This is the G.S.R. 880(E) failure exactly one layer up:
the corpus's own currency is unmonitored, so `as_of.py` may reconstruct a recent
date from an incomplete amendment record and report EXACT. It must be measured
before any backtest, and arguably before anything else in this document.

**D-2 — `fusion.py`'s docstring overclaims by one sentence.** McNemar on the
module's own reported error sets (b=11, c=8) gives exact two-sided p = 0.648, and
the Wilson intervals on p@1 overlap ([0.61,0.82] vs [0.60,0.81]). "Dense 0.73 beats
BM25 0.71" is not established at n=70. The module's actual argument — near-disjoint
error sets — is structural and survives untouched.
