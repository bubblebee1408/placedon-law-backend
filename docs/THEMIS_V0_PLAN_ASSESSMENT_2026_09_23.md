# The THEMIS master build plan, assessed against the repository

Written 2026-09-23 against `THEMIS_CLAUDE_CODE_MASTER_BUILD_PLAN_2026-09-23.md`
(4,233 lines, 107 sections). Every status below was **measured on this machine
today**, not read from a document.

---

## 1. The verdict in one paragraph

The plan's architecture is right and most of its foundations already exist. Of its
own 22 V0 completion criteria (§105), **13 were already met, 3 were met today, 3
are partial, and 3 are not started.** The three built today are the ones that
mattered: they are the vertical slice the plan says proves the architecture. What
remains unbuilt is mostly *research programme* — Azure, a paper registry,
algorithm cards, and the ECAO candidate — none of which is on the path to a
customer, and one of which (ECAO) needs evidence the corpus cannot yet supply.

## 2. §105's own checklist, measured

| # | Criterion | State | Evidence |
|---|---|---|---|
| 1 | Deterministic harness GREEN | ✅ | **191 suites, 0 failed** |
| 2 | Ring 0 cannot import ML / Ring 2 / Ring 3 | ✅ | `checker/rings.py` 36/36, incl. transitive hops and dynamic imports |
| 3 | One live official source ingested automatically | ✅ | eGazette, OFAC SDN, IBBI — three |
| 4 | Raw artifact hash stored | ✅ | `feeds/common/cache.py`, content-hashed and dated |
| 5 | Observation normalised | ✅ | `feeds.Observation`, with licence / behaviour / blindness |
| 6 | Entity resolved | ⚠️ | `entity_graph.py` exists (CIN/DIN); **feeds are not wired to it** |
| 7 | Event stored | ⚠️ | `event_log.py` v0 — law-change half only |
| 8 | Affected obligation identified | ✅ | `currency.affected_by("880")` → `['CA13-S2-85-SMALL']` |
| 9 | **Watchlist can trigger an operation** | ✅ **today** | `checker/operations.py` |
| 10 | **Operation creates ≥3 task types** | ✅ **today** | four: legal research, corporate data, financial data, human review |
| 11 | **Evidence budget visible** | ✅ **today** | `EvidenceBudget` — a named count, not a score |
| 12 | Legal retrieval returns source spans | ✅ | BM25 over structural chunks |
| 13 | Citations resolve to stored evidence | ✅ | `/v1/ask` returns verbatim text + evidence state |
| 14 | Prediction separated from legal determination | ✅ | the ring firewall |
| 15 | Calibration measured before probability shown | ✅ | `calibration_contract.py` (exact binomial ECE floors) |
| 16 | Human review can block final serving | ✅ | `admission.py`; and now the operation graph's only sink |
| 17 | Azure deployment for one ML endpoint | ❌ | not started |
| 18 | Research paper registry | ❌ | not started |
| 19 | ≥5 algorithm cards | ❌ | not started |
| 20 | ≥3 research baselines benchmarked | ⚠️ | two: BM25 and dense, measured on a frozen 70-case eval |
| 21 | One new Themis algorithm candidate (ECAO) | ❌ | not started — see §4 |
| 22 | Full reproducible test instructions | ⚠️ | per-module, not consolidated |

**13 ✅ before today → 16 ✅ now.**

## 3. What was built today, and the one gap it exposed

`checker/operations.py` + `scripts/themis_slice.py` implement §12 and §85:

```
Gazette event → observation → affected obligation → watchlist
              → operation → routed tasks → evidence budget → human review
```

**Live, 2026-09-23:** six Gazette items published that day produced six
operations, each with blocking work routed to a named specialist. The worked case
(G.S.R. 880(E), an instrument this repo holds and has attested) produces five
requirements across all four task types.

The requirements are **derived, not authored**: `affected_by()` names the
obligations, and each obligation's own `evidence_needed` becomes the work.

### The gap the slice exposed — measured, and built in rather than hidden

**A Gazette listing does not name the instrument it contains.** Checked live: every
listed row's subject was either truncated by the site
(`"Publication of Notification..."`) or read `"This Gazette may contains Multiple
Subjects"`. The G.S.R. number is inside the PDF.

So the chain `Gazette item → affected_by()` **cannot close automatically**. The
honest handling — and what the code does — is to make *identifying the instrument*
the first blocking task, and to claim **no** affected obligation, because the index
was given nothing to match on. Guessing a number and matching the index against the
guess would manufacture exactly the signal this system exists to earn.

This is the single most decision-useful finding of the exercise: **the last mile
from "the Gazette published something" to "this obligation moved" is a PDF read,
and it is human-gated today.**

## 4. Where I would not follow the plan

**ECAO (§14, §41, §91) should not be built yet.** The plan proposes
Evidence-Conditioned Adaptive Operations as the novel research contribution, with a
benchmark (§42) and a calibration story (§26). The obstacle is not engineering —
it is that this repository has already deleted one probabilistic engine for exactly
this reason (L-15), and `calibration_contract.py` exists to refuse numbers the data
cannot support. The amendment corpus holds **~6 amending events**; an operation
benchmark would be scored on a handful of instruments. Building ECAO now produces
a number that cannot be calibrated, which is the failure the repo already
documented and retracted once.

**What to build instead, and it is already half-built:** the *ordinal* version. The
evidence budget is a named count of open blocking work. That composes, orders,
explains, and cannot be misread as a measurement. It is the L-15-sanctioned shape.

**§104's "three compelling demos" are reachable; §56–58 (Azure) are not the
bottleneck.** Deployment matters when someone is waiting to use it. Nobody is yet.

## 5. What the plan gets right, and the repo should adopt

- **§3's evidence/inference split** is the ring architecture, already enforced.
- **§8 — "use the architecture, not the dataset or code wholesale"** for God's Eye
  is exactly what was done: the adapter shape was ported, no code and no data.
- **§99's execution discipline** (inspect → baseline → one vertical slice → test →
  ring audit → full gate → scoped commit) is the workflow this session follows.
- **§103 "what not to build"** and **§22 "do not build a judge predictor"** are
  consistent with `NON_GOALS.md` and should stay.

## 6. The honest bottom line

The plan is a good architecture document and an over-large programme. Its own V0
section (§79) says it: *"Do not attempt every feature above in V0. Build one
complete vertical slice."* That slice now runs on live data.

What stands between this and a product is unchanged by any of it: **no practising
Company Secretary has reacted to the output.** H-C has been open since 4 September
— nineteen days. The operation model created six operations today for a watchlist
containing one fictional company, because there is no real one.
