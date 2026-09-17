# PLAN_14 — the Terminal analysed, God's Eye integrated, and what the numbers may say

Written 2026-09-17. Answers three questions asked together on 16-09: what
Bloomberg Law's features actually are, how the God's Eye repository integrates
into the Themis backend, and how this can "make the probability and statistics
accurate."

**The third question has an answer the repository has already built, and it is
mostly "refuse."** §5 is the important section.

Status vocabulary per [PLAN_00_INDEX](PLAN_00_INDEX.md). This document supersedes
nothing; it extends [BLOOMBERG_FOR_INDIA_ANALYSIS](BLOOMBERG_FOR_INDIA_ANALYSIS.md)
Appendix A and [PLAN_08](PLAN_08_BOOKMARK_AND_GODSEYE.md) §5.

---

## 1. A distinction that changes the whole answer

**Bloomberg Terminal and Bloomberg Law are two different products.** Conflating
them is what produced the original "God's Eye" vision, and separating them is what
makes the buildable part visible.

| | Bloomberg Terminal | Bloomberg Law |
|---|---|---|
| Buyer | Traders, analysts, PMs | Litigators, transactional lawyers, in-house |
| Surface | Dedicated terminal / desktop app | Web platform |
| Indicative price | **$31,980/user/year** ($2,665/mo); $28,320/user/yr for 2+ seats | **$450/user/month** |
| Primitive | Real-time market and entity telemetry | Dated legal corpora + analytics over them |
| The "God's Eye" flavour | **This one** — commodity flows, vessel and supply-chain tracking, live everything | Not really present |

> **Pricing — SECONDARY-SOURCED, checked 2026-09-17 (§8).** Both figures were
> carried as recalled knowledge and have now been checked. Both held. **Neither is
> vendor-primary, and cannot become so: Bloomberg publishes no pricing page for
> either product** — itself a sourced finding. Terminal contracts are reported to
> require a 2-year minimum. Treat both as indicative, attribute to the aggregator
> if ever quoted, and never state them as Bloomberg's own published figures.

The fusion vision — a Harvey-style legal AI welded to a live telemetry globe — is
**Terminal aesthetics applied to a Law buyer.** PLAN_08 §5 already measured why
that fails in India, and §3 below restates it in one table. The part worth copying
is not the globe. It is something duller and more valuable, named in §2.4.

---

## 2. What Bloomberg Law actually ships

**Source-checked 2026-09-17** (§8 records the method and what was blocked). Rows
marked **SOURCED** carry Bloomberg's own wording; rows marked INFERRED are working
knowledge that the check did not reach and must not be quoted externally.

| # | Feature | What it really is | Status | Transfers to India? |
|---|---|---|---|---|
| 1 | **Points of Law** | "Identifies the most cited cases for those Points of Law as well as identifies related Points of Law." ML-extracted holdings from opinions | SOURCED | Buildable, but it is the model-authoritative labelling trap (§A.2) and off-wedge |
| 2 | **Draft Analyzer** | "Semantic analysis to compare documents with **more than 2.3 million EDGAR documents**… detailed, relevant comparisons at the **paragraph level** and market standards at the **clause level**" | **SOURCED** | **NO. No data substrate exists.** SEBI requires terms *"(in brief)"*, not filed documents |
| 3 | **Litigation Analytics** | AI over **judge, court, attorney, law firm and company** data — **five** dimensions, not four | SOURCED | Off-wedge and legally fraught in India |
| 4 | **Docket Key** | "AI-powered Docket Key search to find the exemplar brief, motion, or complaint you need among **millions of samples**" | **SOURCED — was missing from this table** | **NO. Downstream of PACER.** See §2.3 |
| 5 | **Smart Code** | Statute sections annotated with the cases citing them; listed as an AI primary-law research tool | SOURCED (name), INFERRED (mechanism) | Partly — needs Indian Kanoon under attribution terms; Stage 3 at earliest |
| 6 | **Brief Analyzer** | Upload a brief; it "identifies authorities cited… and suggests other content… including relevant cases **not** cited in the brief, similar briefs from other dockets, and Practical Guidance". Integrated with Points of Law, Docket Key and Smart Code | SOURCED | Needs a case corpus **and** a docket corpus; downstream of 3 and 4 |
| 7 | **Practical Guidance** | "Step-by-step guidance" — checklists, forms, templates; expert-drafted | SOURCED | Transfers, but it is content, not engineering. ICSI specimens are the Indian analogue |
| 8 | **Dashboard Legal** | "Project management and collaboration tool" | **SOURCED — was missing** | Transfers; adjacent to F8/matter workflow |
| 9 | **BNA content stack** | Treatises, News, Manuals, Portfolios — the Bloomberg Industry Group editorial estate | SOURCED | Content business, not engineering. Not a wedge |
| 10 | **Company & deal data** | Bloomberg's financial entity spine fused into the legal surface | INFERRED | **This is the one that transfers** — and CIN/DIN beat LEI |
| 11 | **Alerts and monitoring** | Standing watches on dockets, companies, topics, regulatory change | INFERRED | **Transfers completely. See §2.4** |
| 12 | **Chart Builder / In Focus** | Visual comparison across jurisdictions and topics | INFERRED | Transfers cheaply; presentation, not substrate |

### 2.3 The source check sharpened the thesis: it is now four for four

PLAN_08 §5 called the pattern "three for three." Adding Docket Key makes it
**four**, and the shape is now unmistakable. Every one of Bloomberg Law's flagship
AI features is downstream of a **US public-record mandate that manufactures a
corpus**:

| Feature | The US mandate underneath it | Indian equivalent |
|---|---|---|
| Draft Analyzer | Reg S-K 601(b)(10) — material contracts **filed as exhibits** to EDGAR | None. SEBI discloses terms "(in brief)" |
| Docket Key | PACER — filings are public record | **PARTIALLY_VERIFIED** — see the caveat below |
| Litigation Analytics | PACER — dockets and outcomes | Same gap, same caveat |
| Points of Law / Brief Analyzer | Published judicial opinions at scale | Partial — Indian Kanoon, under attribution terms |

> **Caveat on the e-Courts rows — a negative claim, held to the negative-claim
> rule.** `CLAUDE.md`: *"could not verify" is not "does not exist."* What was
> checked on 2026-09-17: e-Courts publicly serves **case status, daily orders and
> cause lists**, and the E-Filing Rules state that *"access to e-filings is
> restricted in the manner provided in regulations and as may be notified from
> time to time,"* with e-filed pleadings *"stored on exclusive servers maintained
> under court control… separately labeled and encrypted."*
>
> That supports **"no freely downloadable pleadings corpus comparable to PACER"**
> and it does **not** support "e-Courts publishes nothing." The restriction is
> also court-by-court and notifiable, so it can differ by High Court and can
> change. **Status: PARTIALLY_VERIFIED.** Before this appears in any external
> competitive claim, anchor it on a named High Court's e-filing regulations, not
> on a search summary.

**Bloomberg Law is not an AI company that happened to enter law. It is a corpus
company whose corpora were created by American disclosure law.** The AI is the
interface to substrate the US government compelled into existence.

This is the single most decision-useful sentence in the competitive analysis,
because it says precisely what cannot be copied here and what can: **India
compels no such corpora, so no entrant can build these — and the one dense,
public, authoritative Indian corpus that does exist is the statute.** Which is
the one this repository is built on.

### 2.4 The feature nobody names, and it is the product

Strip the analytics and a terminal is three things:

1. **One identity spine** — every object keyed to a stable identifier.
2. **Everything dated** — every fact carries a time, so history is answerable.
3. **A watch you leave running** — the user does not query; the system tells them
   when something they care about moved.

Analytics are what a terminal *sells*. The standing watch is what makes it a
terminal, and it is the reason the subscription renews.

**Themis already has all three**, which is not obvious from the feature list:

| Terminal primitive | Themis component | State |
|---|---|---|
| Identity spine | `entity_graph.py`, CIN/DIN — mandatory and universal by statute, where LEI is voluntary | BUILT |
| Everything dated | `as_of.py`, `amendment.py`, versioned corpus, point-in-time answers | BUILT |
| The standing watch | `currency.py`, `staleness.py`, `event_log.py`, `affected_by()` | BUILT |

**The terminal thesis for Themis, in one sentence:** *the watch is the product, the
statute is the corpus, and the alert is "the law under your document moved."* That
is F5, and its engine is already built.

**And there is a hole in it.** D-1: the amendment corpus stops in 2023 and nothing
watches *its* currency. A terminal whose own feed has been dead for three years is
not a terminal. This is why `N12` in
[THEMIS_STATUS_AND_NEXT](THEMIS_STATUS_AND_NEXT_2026_09_17.md) §6 should be
promoted: it is not maintenance, it is the flagship feature's integrity.

---

## 3. Why the data-fusion half cannot be bought in India, restated

Three mechanics, three substrates, three walls — and §2.3 now makes it four. Measured 2026-09-11, PLAN_08 §5:

| Bloomberg mechanic | US substrate | Indian reality |
|---|---|---|
| Clause benchmarking | EDGAR full-text exhibit filing | SEBI: significant terms **"(in brief)"** |
| Shipment tracking | Bills of Lading are public record | DGCI&S withholds shipment-level data **by policy, at any price** |
| Corporate data API | EDGAR free public API | MCA21 has **no** official public API, even V3 |

And for the telemetry specifically: **no source is simultaneously global,
real-time and redistributable at startup cost.** NOAA and Danish open AIS are
coastal only. Global Fishing Watch is CC BY-NC. VesselFinder bans resale.
Spire/Kpler/Windward are $2,000–8,000+/month. **India has no free terrestrial AIS
feed at all** — no Coast Guard or DG Shipping equivalent of NOAA.

**Conclusion, unchanged and now thrice-confirmed:** the aggregation play cannot be
won in India by anyone at any funding level. Bloomberg-style products are
downstream of US disclosure mandates that manufacture public corpora. India runs
summary-disclosure regimes. The defensible play is verification and currency over
the one dense public corpus that exists — the statute.

---

## 4. How God's Eye integrates — the concrete answer

**It does not get forked.** §7 of THEMIS_STATUS records why: 1,290 files, a Cesium
frontend, six runtime dependencies, and a data-licensing minefield, into a Python
repo whose stated virtue is no dependency outside the standard library.

**What integrates is one idea**, and it is the right one.

### 4.1 What to take

`server/providers/` is a uniform adapter interface over ~20 heterogeneous live
sources with the shared machinery factored out:

```
server/providers/common/{http,request,rate-limit,query,geo,source-root}.js
server/providers/{aircraft,vessels,space,overpass,places,radio,regional,...}
```

Themis needs exactly this shape, because PLAN_08 §5 already named the feeds:
**MCA Defaulter Companies, struck-off companies, disqualified directors, SEBI
debarred entities (NSE `.xls`), IBBI master data, RBI wilful defaulters, OFAC SDN,
OpenSanctions.** Eight sources, eight formats, eight sets of terms, one contract.

Second thing worth reading: `scripts/check-import-directions.mjs` and
`check-package-boundaries.mjs` — a working executable import-direction check, the
same idea as the unbuilt `checker/rings.py`.

### 4.2 The Python shape it becomes

```
checker/feeds/
    __init__.py         the Feed protocol -- every adapter implements it
    common/
        fetch.py        one HTTP path, reusing checker/robots.py (fail closed)
        cache.py        on-disk, hashed, dated -- an observation is an artifact
        rate.py         per-source governor; the one pattern worth porting
    mca_defaulters.py   SEBI_DEBARRED, IBBI, RBI_WILFUL, OFAC_SDN, OPENSANCTIONS ...
```

**The `Feed` protocol must carry five things, and the last two are the ones the
upstream repo would not have taught us:**

| Field | Why |
|---|---|
| `source_id` | Named source. An unnamed observation is not evidence |
| `fetch()` → bytes + sha256 | Hash the artifact. Same primitive as `acquisition_log` |
| `parse()` → `Observation` | Never a `VERIFIED_FACT`. Ring 2 output only |
| **`licence`** | **Axis D.** Whether this may be shown to a paying customer |
| **`observed_at` + `source_behaviour`** | Record how the source behaved, including a refusal. A 404 is evidence of nothing |

### 4.3 The three rules the integration must not break

1. **`checker/rings.py` lands BEFORE the first feed.** The one-way firewall — no
   Ring 0 decider may import or receive a value originating in Ring 2 or 3,
   enforced by an AST walk, the way `api.py:644-654` already asserts the API
   imports no model library. A feed landing first means the firewall is retrofitted
   around live code, which is how it ends up with exceptions.
2. **Every feed is Ring 2, and emits `OBSERVATION`.** It attaches to an
   `entity_graph` node as an overlay. It never becomes an input to s.185/186/188.
   A director appearing on a disqualification list is an observation to show the
   reviewer, not a fact that decides an obligation.
3. **Axis D is checked at serve time, not at ingest.** OFAC SDN is public domain
   and servable. OpenSanctions has an explicit reseller tier at ~€0.10/call —
   they have already solved "may I show this to a paying customer." Anything
   CC BY-NC is ingestible for internal reasoning and **never servable
   commercially**. The upstream LICENSE is itself the worked example: *"THE MIT
   LICENSE ABOVE COVERS THE SOURCE CODE ONLY."*

### 4.4 What this buys, on-wedge

A **counterparty risk-and-status overlay on the entity graph** — which lands
exactly on s.185 loans to related parties, s.188 related-party transactions, and
beneficial ownership. It fuses with Ring 1 rather than bolting a second product to
the side. PLAN_08 §5 priced the legal stack at roughly **$300–600/month**,
excluding vessel tracking.

**One thing never to do:** no third-party MCA vendor's "MCA-authorized" claim could
be verified against any published MCA list. If one is used, disclose it as
*"aggregated from public MCA filings via a commercial data vendor"* — never
"MCA-authorized."

---

## 5. "How can it make the probability and statistics accurate"

**It cannot, and the repository has already proved that — twice — and built the
instrument that says so.**

This is the most important section in the document, because the request as phrased
is the exact thing L-15 was written to prevent.

### 5.1 What already happened here

A Bayesian belief engine was built in this repository. It was built *well*: a real
sign error in the source spec was found and fixed, an unsourced 0.6 prior was
replaced with 0.5, the number was kept away from users, and a build-failing check
was added if a posterior reached a template.

**It was deleted anyway.** An adversarial audit of the nine underlying papers
established that calibration was unreachable — no logits to scale, and at n=20 the
observable resolution *is* 0.05, so an ECE<0.05 target sits below the instrument.
The author's verdict on their own work:

> *"I fixed the arithmetic and kept the fabrication."*

`LR_LAWYER_VERIFIED = 12.0` had exactly as much grounding as the `prior = 0.6` that
had been rejected. **Rigour applied to the mechanism does not launder an ungrounded
input — it disguises it, because the working is now checkable and the premise still
is not.**

### 5.2 The arithmetic that decides it

`checker/calibration_contract.py` — **BUILT** — turns that finding from an anecdote
into an instrument:

```
ECE_floor(p, n) = E|k/n - p|,  k ~ Binomial(n, p)     <- exact sum, never the normal approx
n_min(p, eps)   = ceil( 8 p (1-p) / (pi eps^2) )

ECE_floor(0.90, 20) = 0.0513    <- a PERFECT model fails a target of 0.05
ECE_floor(0.10,  6) = 0.1063
n_min(0.50, 0.05)   = 255
```

The module's own docstring: *"It is expected to REFUSE most things. A refusal here
is the module working, not failing."*

**Applied to this corpus, the verdict is already known:** the amendment corpus
holds **~6 amending events, not 431** — six amending Acts carry 307 of 348
instrument mentions. So *"will Parliament amend this section"* has n_eff ≈ 6, where
`ECE_floor(0.1, 6) = 0.098`. **Permanently dead. No data acquisition fixes it.**

The *conditional* question — *"is this the kind of section that moves"* — survives
at n_eff ≈ 261 section-years. That one is answerable.

### 5.3 So what does Themis serve instead

`checker/lattice.py` — **BUILT** — the ordinal algebra, "the worst thing wins":

- Ring 3's default output is an **`ASSESSMENT`**: ordinal, with the weakest link
  **named**. A rollup that returns only a state is unusable; every verdict names
  the input that produced it.
- `max` needs no joint distribution. **Multiplying probabilities across a section,
  its qualifying rule, and the reviewer who attested it asserts independence
  between maximally dependent things** — and produces a number that looks like a
  measurement of the world when it is an artefact of an assumption nobody checked.
- **`ESTIMATE` is the exception**, permitted only where the minimum n is stated,
  exists in reality, and measured skill beats the naive baseline.

### 5.4 The honest reframe of your question

> "How can it make the probability and statistics accurate?"

becomes

> **"How can it prove, before anyone computes a number, whether the data could
> support that number at all — and degrade honestly to an ordered judgement when
> it cannot?"**

That question already has a built, tested answer. **The accuracy is not in the
statistic. It is in the gate that decides whether the statistic is allowed to
exist.** For a compliance product sold on risk reduction, that is a stronger claim
than a confident percentage, because a confident percentage is exactly what
opposing counsel takes apart.

**What is left to build here is small and worth doing:** wire
`calibration_contract` as a hard precondition on any Ring 3 output, so a number
without a live SERVABLE track record cannot render. That is N11's sibling and
belongs in the same commit series.

---

## 6. Build order

Nothing here jumps the queue in THEMIS_STATUS §6. This is what happens **after**
H-C, and the sequence matters:

| Step | Work | Gate |
|---|---|---|
| **T0** | `checker/rings.py` — the firewall, AST-enforced | Before any feed exists |
| **T1** | The release chokepoint (F-3) — six SERVABLE paths → one registry | Before Ring 2 can serve anything |
| **T2** | `checker/feeds/` — the protocol + `common/`, **no live source yet** | Offline tests, fixtures only |
| **T3** | **One** feed end to end: **OFAC SDN** — public domain, cleanest Axis D | An observation attaches to an entity, renders as Ring 2, refuses to enter a decider |
| **T4** | The Indian registers: MCA defaulters, struck-off, disqualified directors, SEBI debarred, IBBI, RBI | Each with its own Axis D tag and licence test |
| **T5** | Wire `calibration_contract` as a precondition on Ring 3 | A number with no track record cannot render |

**T3 before T4 deliberately.** OFAC is public domain, so the first feed exercises
the machinery without also litigating a licence. If the pipeline cannot serve the
easiest possible source cleanly, it is not ready for the ones with terms.

---

## 7. What this document does not claim

- **Rows 10–12 of §2 remain INFERRED.** The source check did not reach the company
  /deal-data, alerting or Chart Builder pages. They must not be quoted externally.
  Rows 1–9 carry Bloomberg's own wording and may be.
- **Both price figures are SECONDARY-SOURCED and can never be vendor-primary**,
  because Bloomberg publishes no pricing page for either product. Attribute to the
  aggregator or do not quote.
- **Smart Code's mechanism is INFERRED.** Only its name and its billing as an AI
  primary-law research tool are sourced; "statute annotated with citing cases" is
  recalled, not confirmed.
- No God's Eye code has been read line by line. §4 rests on the repository tree,
  the LICENSE, and `package.json`, all fetched from the GitHub API on 2026-09-17.
- Nothing here is authorised to build. H-C — one practising Company Secretary
  reacting to the evidence pack — still gates everything downstream, and this
  document is ahead of that gate by design, not by permission.

---

## 8. The source check — method, and what was blocked

Run 2026-09-17, per the rule that every research claim carries a URL or a marker.

**What was reached:**

| Source | Host | Used for |
|---|---|---|
| `bna.content.cirrus.bloomberg.com/blaw2023/products/legal-research-and-software/` | **Bloomberg-owned** | The product enumeration in §2 — Points of Law, Smart Code, Docket Key, Litigation Analytics, Brief Analyzer, Draft Analyzer, Dashboard Legal, Practical Guidance, BNA stack |
| Search-surfaced vendor copy for Draft Analyzer and Brief Analyzer | pro.bloomberglaw.com (via index) | The 2.3M EDGAR figure, the paragraph/clause levels, Brief Analyzer's behaviour |
| costbench / godeldiscount / LawNext / vaquill | Third-party aggregators | Both price figures |

**What was blocked, and not bypassed:**

- **`pro.bloomberglaw.com` returns HTTP 403 to automated fetch.** Recorded as
  blocked. Not routed around, per `CLAUDE.md`'s source policy — the same handling
  ecfr.gov received when it returned a bot wall during the SEBI check.
- **`bloomberglaw.com/help/...` 302-redirects to a client-support portal**
  (`bloombergindustry-clientsupport.com`), which requires authentication. Not
  pursued.

**Evidence-quality caveat, stated before any of this is used externally.** The
enumeration comes from a Bloomberg-owned content host rather than the canonical
`pro.bloomberglaw.com` product pages, and the vendor wording for Draft Analyzer
and Brief Analyzer arrived through a search index rather than a page opened
directly. Both are Bloomberg's own words, reproduced verbatim rather than
paraphrased, but neither is the canonical host. **Status: PARTIALLY_VERIFIED.**
Re-anchor against the primary product pages — which needs a human browser, since
the host refuses automated fetch — before any of it supports a competitive claim.

**What the check changed:**

1. Added two features the table had missed entirely — **Docket Key** and
   **Dashboard Legal**.
2. Corrected Litigation Analytics from four dimensions to **five** (attorney was
   missing).
3. Upgraded the **2.3M EDGAR** figure from a carried claim to Bloomberg's own
   published wording, which strengthens `BLOOMBERG_FOR_INDIA_ANALYSIS` §A.1.
4. **Produced a new finding**: the pattern is four for four, not three for three
   (§2.3). Docket Key is a second PACER-derived corpus, and it reframes Bloomberg
   Law as a corpus business rather than an AI business.
5. Confirmed both price figures, and established that neither can ever be
   vendor-primary.

### 8.1 Blocked and unresolved after this check

| Item | State | What would resolve it |
|---|---|---|
| §2 rows 10–12 (company/deal data, alerting, Chart Builder) | **INFERRED** | The canonical product pages — needs a human browser; the host 403s automated fetch |
| Re-anchoring rows 1–9 to `pro.bloomberglaw.com` | **PARTIALLY_VERIFIED** | Same. A human opening the pages and saving them |
| Smart Code's mechanism | **INFERRED** | Same |
| e-Courts pleadings access (§2.3) | **PARTIALLY_VERIFIED** | A named High Court's e-filing regulations, read directly |
| Both price figures | **SECONDARY-SOURCED, permanently** | Nothing. Bloomberg publishes no pricing page |

**The autonomous ceiling has been reached on this question.** Everything still
open needs either a human browser against a host that refuses robots, or a primary
regulation read directly. No further unattended iteration improves this document.
