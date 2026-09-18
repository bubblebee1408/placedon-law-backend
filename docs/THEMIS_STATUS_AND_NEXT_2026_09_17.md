# Themis — where we are, and where to start

Written 2026-09-17. Status vocabulary is [PLAN_00_INDEX](PLAN_00_INDEX.md)'s:
**BUILT · MEASURED · SOURCED · INFERRED · UNVERIFIED · BLOCKED**.

This document answers four questions: what the engine actually is today, which
plan already covers what, exactly where work stopped, and what to do next. It
also answers a fifth asked on 16-09: what would have to change in the God's Eye
repository for it to serve this project.

**Nothing here is new engineering.** Every state below was read out of the
repository on 2026-09-17, and the gate was re-run rather than quoted.

---

## 0. The name

**Themis** is adopted as the project name, on the founder's decision of 16-09-2026.

The prior names in the record were `Bookmark` (the Bloomberg/entity layer) and
`God's Eye` (the telemetry layer), both from [PLAN_08](PLAN_08_BOOKMARK_AND_GODSEYE.md).
Θέμις means *"that which is laid down"* — established ordinance as distinct from
argument. The engine's admission gate (`checker/admission.py`) decides what is
laid down well enough to be served, which is the same idea.

**One decision is still open and it changes the blast radius** (§8, D-1): whether
Themis replaces `Placedon` as the product and company name across four repos and
the brand spec, or names *this engine* — the admissibility harness — inside
Placedon. Nothing is renamed in code until that is answered.

**Recorded objections, overruled by the founder, kept so they are not
re-discovered:** `Themis Solutions Inc.` is the registered name of Clio, the
largest legal practice-management vendor; `Themis Bar Review` and at least one
banking-compliance `Themis` also trade in this sector. Trademark clearance in the
software and legal-services classes is therefore **UNVERIFIED and likely
contested**. This is a cost to plan for, not a reason to reopen the decision.

---

## 1. The one-page answer: start here

The critical path is short, and it is not what the backlog suggests. Five links:

```
  D-002  the PDF page reader is broken            [BLOCKED on a dependency decision]
    │        agrees with an independent reader on 0 of 14 corpus files
    ▼
  re-extract the Board Rules 2014 cleanly          [BLOCKED on D-002]
    │        every one of 15 rules is currently damaged; R15 carries 578 split words
    ▼
  human review of the 30 queued items              ["a day of human work, not engineering"]
    │        reports/review_brief.md — all 30 HUMAN_REVIEW_PENDING, servable: False
    ▼
  s.177 stops refusing; matrix gains answerable rows
    │        Rules 6 and 7 of this very instrument are what s.177 needs
    ▼
  H-C — one practising Company Secretary reacts to the pack   [THE GATE. Open since 04-09]
```

**Start at the top of that chain, not the bottom.** The reason is in §5: today the
30 review items cannot be reviewed honestly, because the text a reviewer would be
adjudicating is mangled by the extractor. Sending a Company Secretary into that
spends the scarcest resource in the project on proofreading.

**The one-line version:** the measuring instrument is excellent and the material
it measures is damaged. Fix the material.

---

## 2. Where we are — measured 2026-09-17

### 2.1 The gate

```
$ ./scripts/run_tests.sh
all suites green
HARNESS_RESULT suites=163 failed=0 status=GREEN
```

**MEASURED today**, not quoted from the overnight report. 163 suites, 0 failed.
`checker/scope.py` passes 20/20 on its own.

### 2.2 Position

| | |
|---|---|
| Branch | `loop/bookmark-godseye-v0` — **not `main`** |
| Uncommitted | `web/assistant/tools/accept.mjs` (+150/−29) and the UX runbook |
| Last commit | `ea627b7` *fix: a document turn says what law it was checked against* |
| Scope | 9 bodies declared, **1 held** (CA2013); SEBI_LODR held as a consolidation, wired to no obligation |

### 2.3 What is built

Eight of eleven features have a built engine ([FEATURES](FEATURES.md)). The
deterministic core is real and tested: `obligations.py` (1,448 lines), the
s.185/186/188 deciders, `currency.py`, `as_of.py`, `entity_graph.py`,
`diligence_pack.py`, `staleness.py`, `drafting.py`, the E3→E6 entailment cascade,
and `POST /v1/document-check` behind a working Word add-in.

### 2.4 What is genuinely distinctive — say this part out loud

The strongest asset is **not** the checker. It is the apparatus that measures the
checker, and it is unusual enough to be the moat:

- `eval/realrun/run.py` — 18 adversarial cases through the real orchestrator,
  **scored without a model** (substring, set membership, date comparison), on the
  stated reasoning that *a judge sharing the weights that produced a claim cannot
  measure the claim*.
- `eval/realrun/text_field_probe.py` — declared **a measuring instrument, not a
  gate**. It exists because widening `field_binding` to text/date fields was
  *proposed and declined* for lack of observed evidence.
- `scripts/harness_regression.sh` — three full sweeps proving a failing suite
  really turns the harness RED, including the silent-failure shape that once hid
  four real failures behind "all suites green".
- Four checker holes in the 14-09 run were **found by real models, not by
  hand-written tests**, and every fix was replayed against stored runs to prove it
  refused nothing that previously served correctly.

**MEASURED leak rate:** gpt-5-mini **0/18**, Llama-3.3-70B **0/18**. The only
errors are over-refusals, and one of those was our own gate's bug, since fixed.

### 2.5 What is damaged — the other half of the truth

| Defect | Where | State |
|---|---|---|
| **D-002** · the repo's page reader agrees with an independent reader on **0 of 14** corpus PDFs (1 page returned for a 169-page file) | `checker/pdf_text.extract_pages` | BLOCKED on a dependency decision |
| **D-1** · the amendment corpus **stops in 2023** — 2024, 2025, 2026 absent, and nothing watches | `corpus/companies_act/` | OPEN |
| 17 corpus pages are **OCR over a scan**, with errors reaching the figures (`1.1124.31`, `7.(,4`, and a CIN) | `corpus/testdocs/` | Recorded, deliberately not repaired |
| All 15 Board Rules carry extraction damage, up to **578 split words**; one heading reads *"in its own na me"* | `reports/review_brief.md` | BLOCKED on D-002 |
| **F11** MCA Master Data Strip is served but **has no data** | `checker/mca_strip.py` | BLOCKED on an aggregator contract |
| **F8** Bulk Document Review | — | NOT BUILT, and named the riskiest item |

For a product whose entire moat is statutory currency, **D-1 is the most serious
defect in the repository**: the corpus that proves the law moved has itself
stopped moving, and no watcher exists. It is recorded. It is not fixed.

---

## 3. The technical plan that already exists

Thirteen numbered plans plus the feature list. This is the map, so no work gets
re-planned.

| Plan | Covers | State on 2026-09-17 |
|---|---|---|
| [PLAN_00_INDEX](PLAN_00_INDEX.md) | Index, status vocabulary, falsifiers | Current |
| [PLAN_01_ARCHITECTURE](PLAN_01_ARCHITECTURE.md) | 20 roles; only 9 touch a model | BUILT; roles 16–20 designed only |
| [PLAN_02_MODEL_TRAINING](PLAN_02_MODEL_TRAINING.md) | What to train and what not to | Hardware limit is arithmetic; label yield unmeasured |
| [PLAN_03_DATA_SOURCES](PLAN_03_DATA_SOURCES.md) | Every source, access mechanics | SOURCED; vendor authorisation unverifiable |
| [PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md) | The v1 surface | Add-in BUILT and loading |
| [PLAN_05_ROADMAP](PLAN_05_ROADMAP.md) | Sequence and gates | Gates falsifiable; demand n=1 |
| [PLAN_06_EVALUATION](PLAN_06_EVALUATION.md) | How to be believed | Static RAG = 0%, traced; no Indian benchmark exists |
| [PLAN_07_TENANCY_AND_PRICING](PLAN_07_TENANCY_AND_PRICING.md) | Isolation, zero retention, pricing | Retention rule quoted from a shipped system |
| [PLAN_08_BOOKMARK_AND_GODSEYE](PLAN_08_BOOKMARK_AND_GODSEYE.md) | The Bloomberg + telemetry layers, four rings, the firewall | Architecture written; **Rings 2–3 human-gated, not started** |
| [PLAN_09_MCA_MASTER_DATA_STRIP](PLAN_09_MCA_MASTER_DATA_STRIP.md) | F11 | Engine BUILT, data BLOCKED |
| [PLAN_10_ADOPTION_REVIEW](PLAN_10_ADOPTION_REVIEW.md) | Criminal-law pivot declined; 5 lessons kept | Closed 13-09 |
| [PLAN_11_NEXT_MOVE](PLAN_11_NEXT_MOVE.md) | Tracks L / R / A / D for the 14-09 loop | L and R complete; A complete |
| [PLAN_12_DOCUMENT_INTAKE](PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md) | F8 and role 13 end to end, ~16,600 words | **Complete.** 43 red-team findings, all fixed. G01 unchosen |
| [PLAN_13_ASSISTANT_UX](PLAN_13_ASSISTANT_UX.md) | The Ask section | Spec + prototype done; **red team in progress** |
| [BLOOMBERG_FOR_INDIA_ANALYSIS](BLOOMBERG_FOR_INDIA_ANALYSIS.md) | The four Bloomberg mechanics against India | Three declined, one already built |

### 3.1 The strategic finding these plans converge on

Worth restating because it should govern every roadmap argument from here:

| Bloomberg mechanic | US substrate | Indian reality |
|---|---|---|
| Clause benchmarking | EDGAR full-text exhibit filing | SEBI requires significant terms **"(in brief)"** |
| Shipment tracking | Bills of Lading are public record | DGCI&S withholds by policy |
| Corporate data API | EDGAR free public API | MCA21 has **no** official public API, even V3 |

**Bloomberg-style products are downstream of US disclosure mandates that
manufacture public corpora. India runs summary-disclosure regimes, not
record-filing regimes.** The aggregation play cannot be won in India by anyone at
any funding level. The defensible play is verification and currency over the one
dense public corpus that does exist — the statute. Which is what is built.

---

## 4. Where we stopped — precisely

### 4.1 Mid-flight, uncommitted

The **UX-V red team** on the Ask section. First run `wf_b97b010b-b9d` lost all
four agents to a session limit on 16-09 ~15:00. The session restarted at 22:28,
the scratchpad was gone, the acceptance runner was moved into the repo to survive
that (`1e4c401`), and the red team was relaunched as `assistant-ux-redteam-2`.

`web/assistant/tools/accept.mjs` carries **+150/−29 uncommitted lines** — the
A11Y-4 fix making citation records reachable via `[data-marker]` buttons rather
than tab stops. **This is real work sitting unprotected.** Commit it first.

Still open behind it: **UX-M** — the report, the TASKS rows, and the stop.

### 4.2 Stopped and waiting on a decision, not on engineering

From the 14-09 report's own "waiting on you" list, still unanswered on 17-09:

1. **G01** — durable storage for bulk review? Both branches designed; choosing is a liability call.
2. **L7** — map document wording to company class? Interpretive; today an unmapped class refuses at `api.py:86`.
3. **D2** — which PDF reader for page anchors? *This one blocks the critical path.*
4. **MCP registration** — credentials and tool scope.
5. **Sarvam** — only with training opted out, and only if the 10-page cap is acceptable.
6. **The 20-document test** — needs real buyer documents.

### 4.3 Never started

Rings 2 and 3 of PLAN_08 — the telemetry and inference layers — are **human-gated
behind H-E/H-F/H-G and correctly untouched.** `checker/rings.py`, the AST-walking
firewall that would enforce "no Ring 0 decider may import from Ring 2 or 3", is
**specified but not built**. So is the release chokepoint (F-3): "only SERVABLE
reaches a user" is currently reimplemented in **six places under two
vocabularies**, with no shared base class or registry.

---

## 5. The blocking chain, and why the order matters

`FEATURES.md` summary: *"four obligations refuse because their delegated rules are
unheld. Clearing those takes the matrix from 11 answerable rows to 15, and it is a
day of human work, not engineering."*

> **Doc inconsistency, flagged not resolved:** the F2 entry says **2 of 15** rows
> refuse (s.177 Rule 6 held-but-unread, s.203 chain traced-unconfirmed), while the
> summary says four obligations. One of the two is stale. Reconcile before quoting
> either number externally.

**The link that makes today's report the unblocking work:** `reports/review_brief.md`
queues the *Companies (Meetings of Board and its Powers) Rules 2014*. Rule 6 of
that instrument is *Committees of the Board* and Rule 7 is *Establishment of vigil
mechanism* — which is exactly what **s.177** needs to stop refusing. The 30 queued
items are not housekeeping; they are the delegated legislation under the rows that
currently abstain. Rules 10, 11 and 15 sit under **s.185, s.186 and s.188** — the
three flagship deciders.

> **Worth verifying directly, not asserted here:** whether `s185.py`, `s186.py`
> and `s188.py` reason off Act text alone, or are structurally incomplete until
> these rules are admitted. I did not trace it.

**And the reason not to start the human review today:** every rule in the brief
carries extraction damage — 6, 33, **321**, 12, 7, 33, 66, 39, 39, 22, 66, 70, 60,
51 and **578** split words. R15 runs to end-of-document and swallows the Annexure
and forms (13,401 characters where the operative text ends earlier). A reviewer
handed that is doing OCR correction, not legal review, and the result would tell
us nothing about whether the engine is right.

**So: fix the extractor, re-extract, then spend the human.**

---

## 6. What to do next — an ordered queue

Each item states what makes it done. TDD, one logical change per commit, per
`CLAUDE.md`.

### Now (this week)

| # | Task | Done when |
|---|---|---|
| **N1** | **Commit the uncommitted.** `accept.mjs` + the runbook row | Gate green; `git status` clean |
| **N2** | **Decide D2** (§8 D-2) — fix the stdlib page parser, or adopt a PDF library with a stated reason under the dependency policy | A decision written into PLAN_12 with its reason, and the status row updated |
| **N3** | **Fix the page reader** per N2 | The two-reader census agrees on ≥13 of 14 corpus PDFs, re-run and recorded |
| **N4** | **Re-extract the Board Rules** and regenerate `review_brief.md` | Split-word counts at or near zero; R15's operative/Annexure boundary set; headings clean |
| **N5** | **Reconcile the 2-vs-4 refusing-obligations inconsistency** (§5) | One number, traceable to `obligations.py` |
| **N6** | **Finish UX-V and UX-M** — the red team and the report | Findings dispositioned; report committed; loop stopped |

### Next (once N3–N4 land)

| # | Task | Done when |
|---|---|---|
| **N7** | **Human review of the 30 items** — a day of work, now honestly reviewable | Decisions recorded via `scripts/review.py`; instrument `production_usable` set on evidence |
| **N8** | **s.177 (and any others) stop refusing**; regenerate the matrix | Answerable rows rise; the gain is stated as a measured number |
| **N9** | **Then and only then, H-C** — one practising Company Secretary reacts to the pack | Written reactions captured in `docs/research/` |

### Structural, and overdue

| # | Task | Done when |
|---|---|---|
| **N10** | **The release chokepoint (F-3).** Collapse six SERVABLE reimplementations under two vocabularies into one registry | All six call one gate; a test proves no seventh path can serve |
| **N11** | **`checker/rings.py`** — the one-way firewall, enforced by an AST walk over every Ring 0 module | A Ring 0 module importing upward fails the gate |
| **N12** | **D-1 — a watcher on the corpus's own currency.** The corpus stops in 2023 and nothing notices | A test fails when the newest amendment is older than a stated threshold |

**N12 deserves promotion.** It is the G.S.R. 880(E) failure exactly one layer up:
the engine that watches whether the law moved does not watch whether its own
record of the law moved. That is the product's central claim, unguarded.

### Explicitly NOT next

Rings 2 and 3, any telemetry feed, any vessel or spatial work, and any MCA
aggregator build. All are gated, correctly, and all are downstream of H-C.

---

## 7. God's Eye → Themis: what to take and what to strip

`bilawalsidhu/gods-eye-view` — **SOURCED 2026-09-17 from the GitHub API**, not
from memory: 35,729 stars, 7,138 forks, 1,290 files (1,024 under `src/`),
JavaScript, last pushed 2026-09-16, homepage `maptheworld.ai`.

### 7.1 The licence — this settles PLAN_08 §A.5's open question

§A.5 said *"check the upstream licence first — it was not verified here."* It is
verified now, and the answer is sharper than either outcome anticipated:

- **The code is MIT.** Clean, permissive, safe to fork.
- **The data is not, and the LICENSE says so in capitals.** *"THE MIT LICENSE
  ABOVE COVERS THE SOURCE CODE ONLY."*
  - TeleGeography submarine cables — **CC BY-NC-SA 3.0**, NonCommercial + ShareAlike
  - Bhote Koshi imagery and derived centerline — **CC BY-NC 4.0**, NonCommercial
  - Datacenters and dams (OSM extracts) — **ODbL 1.0**, attribution + share-alike
  - Live sources (Google Maps, OpenSky, AISStream, adsb.lol, CelesTrak, USGS,
    Overpass) — each under its own terms; several restrict commercial use

**This repository is a worked example of Axis D**, the licence/redistribution axis
PLAN_08 §4 introduced as non-optional. Its author solved exactly the problem
Themis named: the code you may ship and the data you may not are different
grants, and the boundary has to be machine-visible. That is worth reading closely
even if not a line of it is forked.

### 7.2 What is worth taking — the pattern, not the globe

The reusable asset is `server/providers/`, and it is better than §A.5's
"rate-governor/cache proxy" summary suggested. It is **a uniform adapter
interface over ~20 heterogeneous live sources**, with the shared machinery
factored out:

```
server/providers/common/{http,request,rate-limit,query,geo,source-root}.js
server/providers/{aircraft,vessels,space,overpass,places,radio,regional,firms,gbfs,...}
```

That shape is exactly what Themis Ring 1 needs, because PLAN_08 §5 already named
the feeds: MCA Defaulter Companies, struck-off companies, disqualified directors,
SEBI debarred entities (NSE `.xls`), IBBI master data, RBI wilful defaulters,
OFAC SDN, OpenSanctions. Eight sources, eight formats, eight sets of terms, one
contract — which is the problem `server/providers/` solves.

**The second thing worth taking is smaller and sharper:**
`scripts/check-import-directions.mjs` and `scripts/check-package-boundaries.mjs`.
That is an executable import-direction check — the same idea as the unbuilt
`checker/rings.py` (N11), already working in another language. Read it before
building ours.

### 7.3 What must be stripped, and why a fork is still the wrong move

| Component | Verdict |
|---|---|
| Cesium / WebGL globe, `src/layers`, `src/scenes`, `src/director`, `src/voice` | **Strip.** ~1,024 files of 3D client for a compliance matrix |
| All of `src/data/local_data/` | **Strip.** NC and ODbL data; the licence tells you to remove it for commercial use |
| Every telemetry provider — ADS-B, AIS, CelesTrak, FIRMS, CCTV, military installations | **Strip.** PLAN_08 §5 measured these: no source is simultaneously global, real-time and redistributable at startup cost, and India has no free terrestrial AIS at all |
| `server/providers/openai/*` | **Strip.** A model with tool-calling and live instructions is precisely what the Ring 0 firewall exists to keep out of a decision path |
| 6 runtime deps (cesium, satellite.js, mgrs, pbf, …) | **Strip.** This repo's stated virtue is no dependency outside the standard library |

**So: do not fork it.** Forking imports a JavaScript frontend stack, 1,290 files,
a non-standard-library dependency set and a data-licensing minefield into a Python
repository whose discipline is the product. **Read `server/providers/common/` and
the two boundary checkers, port the *interface shape* into Python for Ring 1's
register adapters, and take nothing else.** §3.3 and §A.5 stand: the spatial
product is a separate bet with a separate buyer.

### 7.4 If the globe is wanted anyway

It is a **separate repository, a separate buyer and a separate licence posture** —
never a feature of the compliance engine. PLAN_08 §5 priced the legal data stack
at roughly **$300–600/month** excluding vessel tracking, and found Spire/Kpler/
Windward at $2,000–8,000+/month. Nothing about Themis changes those numbers.

---

## 8. Decisions only the founder can make

| # | Decision | Why it is blocking |
|---|---|---|
| **D-1** | **Themis: product-wide, or this engine?** | Determines whether four repos, the brand spec and the landing page get renamed, or one README does |
| **D-2** | **The PDF reader** — fix the stdlib parser (large job) or adopt a library (new dependency, needs a stated reason) | **Blocks N3 → N4 → N7 → H-C.** The top of the critical path |
| **D-3** | **G01** — durable storage for bulk review | PLAN_07 says client documents are never durable; a 500-page bundle needs per-page state |
| **D-4** | **L7** — map document wording to company class | Interpretive; today it refuses safely |
| **D-5** | **The two-number integer rule** — keep refusing a correct count in a two-number sentence, or accept it | Recall against never serving a wrong count |
| **D-6** | **H-C — find the Company Secretary.** Open since 04-09 | Nothing downstream is worth building until someone reacts |

---

## 9. The thing worth saying plainly

Since 4 September, the blocking item has not moved. It was restated on 11-09 in
PLAN_08 §7, restated in the 14-09 overnight report, and is restated here. In the
same period the repository shipped 16 commits in a single night, a 16,600-word
intake architecture, a red-teamed UX spec, and a 185-check acceptance runner —
all of it good, none of it past the gate.

`FAILURE_MODES.md` names this exactly: *"This is an unusually self-aware
repository, and that is itself a hazard."* A project that writes down its
weaknesses in high-quality prose gets most of the credit for fixing them.

The extractor fix (N2–N4) is the one piece of engineering that actually converts
into movement on H-C. That is why it is first.

---

## 10. What this document does not claim

- It does not claim the s.185/186/188 deciders are wrong without the Board Rules.
  That link is flagged in §5 as worth tracing and **was not traced**.
- It does not resolve the 2-vs-4 refusing-obligations inconsistency; it records it.
- It makes no trademark finding on Themis. The collisions in §0 are **UNVERIFIED**
  and need a real clearance search.
- It makes no accuracy claim for the engine. No practising lawyer has reviewed any
  output, and there is still no real-document benchmark. That is the point of H-C.
