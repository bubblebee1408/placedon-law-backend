# 02: The architecture — built on the orchestration code that exists, for every body of law

This document describes the system **as it is wired in the code today**. The orchestration
branch `claude/harvey-india-platform-analysis-d2mmqi` was read at `89370dc`. Each part says
whether it is BUILT, PARTIAL, NEW, or a FIX. Where it rests on a paper, the paper is in
file 01. Where it rests on a line of code, the line is in `.claude/loops/…_D_CODE_AUDIT.md`.

## 1. The whole system on one page

```
╔════════════════════════════════════════════════════════════════════════════════════╗
║ SURFACES      REST /v2/<verb>        MCP themis.<verb>          CLI placedon <verb>  ║
║ (BUILT)       web app, Word add-in   Claude/Harvey/any agent    engineers, cron, CI   ║
║               └──────────── generated from ONE verb table + parity test ──────────┘  ║
╠════════════════════════════════════════════════════════════════════════════════════╣
║ L0 GATE       API key → (tenant, actor) · RLS on Postgres · audit row · rate limit NEW║
╠════════════════════════════════════════════════════════════════════════════════════╣
║ L1 INTAKE     closed set of intents ─ one per verb ─ refused if not in the set        ║
║ L2 PLAN       code compiles a typed plan: steps · budget · timeout · as_of   (FIX)    ║
║ L3 EXECUTE    Postgres queue, FOR UPDATE SKIP LOCKED, step-level resume      (FIX)    ║
╠══════════════╤═════════════════╤══════════════════╤══════════════════╤═════════════╣
║ SCOPE        │ RETRIEVE        │ DECIDE           │ NARRATE          │ FORECAST     ║
║ which body   │ date-filtered   │ Ring 0 code      │ model phrases    │ Ring 3       ║
║ of law? held │ versioned text  │ per body of law  │ what code        │ rates · time ║
║ or declared? │ BEFORE model    │ (and, later, a   │ decided; every   │ what-if ·    ║
║ (BUILT)      │ (FIX: F5)       │ solver) (BUILT)  │ clause quoted    │ change ·     ║
║              │                 │                  │ (BUILT)          │ conformal NEW║
╠══════════════╧═════════════════╧══════════════════╧══════════════════╧═════════════╣
║ L6 VERIFY (code)  span byte-identical · sufficient context · value checks  (BUILT/NEW)║
║ L7 CRITIC         may remove or narrow, once; never add                     (NOT BUILT)║
║ L8 SYNTHESIS      law shown as law; statistics shown as statistics; kept apart         ║
║ L9 HUMAN GATE     lawyer sees the quote before approving; decision = a label  (PARTIAL)║
║ L10 RECORD        law versions · as_of · model · cost · MAST tag · behaviour version   ║
║ L11 RECALL        law changes → every past answer that relied on it           (NEW)    ║
╠════════════════════════════════════════════════════════════════════════════════════╣
║ MEMORY        observation_store (bitemporal) · ontology · derivation (evidence algebra)║
║               positions · decisions · labels · per-tenant playbook & precedent memory  ║
╠════════════════════════════════════════════════════════════════════════════════════╣
║ LIVE DATA     cron → feed adapters (eGazette, SEBI, RBI, IBBI, OFAC, MCA master data) ║
║ (daily)       → observation_store → operations → watch → recall      (God's Eye patterns)║
╠════════════════════════════════════════════════════════════════════════════════════╣
║ HUMANS        lawyer-engineer funnel ↔ Labelling Agent (sorts, pre-labels, never decides)║
║               body-of-law onboarding: acquire → attest → encode → test → HELD          ║
╚════════════════════════════════════════════════════════════════════════════════════╝
```

**Read it as three loops turning at different speeds:**

- **The request loop**, in seconds. A lawyer asks, code plans, the law is retrieved *as of
  the date*, code decides, a model phrases, code verifies, and the answer is recorded with
  the law versions it used.
- **The live-data loop**, daily. Feeds bring the Gazette and regulator orders into the
  store. A change finds the obligations it touches, then the past answers that relied on
  them (recall), and opens operations for a lawyer to review.
- **The learning loop**, weekly. Every lawyer decision becomes a label. Labels become test
  sets. A proposed improvement is tested on a frozen split and promoted only by a person.
  The Ring 3 forecasters gain the track record that lets them show numbers.

## 2. Many bodies of law, not one Act

`checker/scope.py` is the authority. It declares **nine bodies of law**:

| Body | Status today |
|---|---|
| Companies Act 2013 | HELD |
| SEBI LODR | held as text, wired to no rule |
| LLP Act 2008 | DECLARED (refused) |
| SEBI ICDR/SAST/PIT/Buyback | DECLARED |
| FEMA 1999 + FDI rules | DECLARED |
| IBC 2016 | DECLARED |
| Competition Act 2002 | DECLARED |
| Stamp duty | DECLARED |
| DPDP 2023 | DECLARED |

The design makes adding a body a **pipeline**, not a rewrite. Every body passes through the
same six gates, and **only the last gate changes what is served**:

```
 ACQUIRE ──► ATTEST ──► STRUCTURE ──► ENCODE ──► TEST ──► PROMOTE
 official    a human    sections,     rules as   gold set  scope.py:
 text only   checks     provisos,     code, per  for this  DECLARED
 (Gazette,   source +   versions,     provision; body, ≥   → HELD
 regulator)  hash       as_of index   deadlines  30 items   (a person
 robots.txt  (admission (legal_ref:   as rules;  per rule  edits it)
 honoured    .py)       instrument-   solver     family
                        qualified)    tests
   corpus-    lawyer-    corpus-       lawyer-    lawyer-
   engineer   engineer   engineer      engineer + engineer +
   agent                 agent         developer  legal-verifier
```

- **The invariant holds at every step.** "No obligation may exist in the register for a
  body that is not held" (`CLAUDE.md`, tested). A body in the pipeline stays DECLARED, so
  its questions are still *refused, with the body named*, until PROMOTE.
- **Instrument-qualified references are already built** (`checker/legal_ref.py`: "a
  provision number is never an identity"). Section 7 of IBC and section 7 of the Companies
  Act can never be confused.
- **ENCODE follows the literature's strongest reasoning result** (file 01 §4). The statute
  is encoded once, by hand, as code or rules; the model only parses the facts. Themis's
  deciders (`s185.py`, `s188.py` and others) are already this pattern. A logic engine
  (s(CASP)/Blawx or Prolog, free) becomes worth adding when a body's rules are mostly
  exceptions ("notwithstanding", "subject to"), for example IBC timelines or FEMA
  permitted-route rules.
- **Order of bodies** (recommended, file 08):
  1. **SEBI LODR**: the text is already held; only ENCODE and TEST remain.
  2. **IBC**: the same forum as the Companies Act (NCLT), so forum analytics share data.
  3. **FEMA/FDI**: the highest in-house demand after corporate law [I].
  4. **DPDP**: core obligations bind from 13 May 2027.

  Each body is about **one lawyer-engineer-month** [I, estimate].

The Ring 3 forum analytics follow the same per-body rule. A statistic about a forum is
shown only beside law that is held. For each body, the forums and their public records:

| Body | Forum / regulator | Public records the analytics need | Access |
|---|---|---|---|
| Companies Act | NCLT, NCLAT, RD, ROC | orders; adjudication orders (s.454) | OPEN (terms unread) |
| IBC | NCLT, NCLAT, IBBI | orders; IBBI orders (feed **built**) | IBBI built; rest OPEN |
| SEBI | SEBI, SAT | adjudication and settlement orders | OPEN (SEBI RSS permitted per PLAN_19) |
| FEMA | RBI, ED | RBI compounding orders | OPEN |
| Competition | CCI, NCLAT | orders | OPEN |

## 3. The request loop in detail (L0–L11), with the fixes that come first

| Layer | Today | What changes | Why (evidence) |
|---|---|---|---|
| L0 Gate | hashed keys, RLS, audit | add a per-tenant rate limit | God's Eye `rate-limit.js` pattern |
| L1 Intake | 5 intents in `plans.py`; 10 verbs | one intent per verb; the verb table is the intake | PLAN_23 §1.10: one reasoning type per intent |
| L2 Plan | linear tuple of steps; no budget; **nothing calls it** | a typed plan with `budget_tokens`, `timeout_s`, `as_of`, `bodies_of_law`; the gateway calls `plans.template` | Anthropic vendor data: tokens explain 80% of variance, so budgets must be declared (PLAN_23 §1.3) |
| L3 Execute | queue exists but is **unreachable**; resume re-runs model calls | give surfaces a queue in `Context`; make handlers generators so each step persists before the next; renew leases | appendix D F3 |
| Scope | 9 bodies; practitioner phrasing leaks (5/14) | per-body lexicon from each body's own acquired text (ACQUIRE gives G0.3 its source) | gold-set run 2026-09-25 |
| Retrieve | BM25 over structure; **no as_of filter** (F5) | **filter by as_of before ranking**, over the bitemporal store | FiscalQA Pro: static RAG finds the right version 0% of the time; date-conditioned retrieval gets 98.3% |
| Decide | Ring 0 deciders per provision | per-body encodings; a solver for exception-heavy bodies | Catala found a bug in official code; LLM formalisation is unfaithful |
| Narrate | router → Azure llama-70b (gpt-5-mini fallback) | free no-train hosts for **public** text only (file 04) | appendix A |
| Forecast | — | `checker/forecast/` **(BUILT in this loop)** | file 03 |
| L6 Verify | span tracing, byte-identical | add the **sufficient-context gate** before narration (it may only withhold) | Joren et al., ICLR 2025: models hallucinate 15–40% on insufficient context |
| L7 Critic | not built | removes or narrows once, on the verifier's reason | Huang et al., ICLR 2024: no intrinsic self-correction |
| L9 Human gate | approve/reject after serving; **ask runs cannot be approved** (F2) | **fix F2**; `quote_viewed` (from T0) as migration **007**; `reviews.next` verb | automation bias (PLAN_23 §1.8) |
| L10 Record | provider, region, cost | + law_versions, as_of, behaviour_version, MAST tag, dataset_version | recall and the learning loop need them |
| L11 Recall | not built | join `runs ⋈ law_versions` with `currency.affected_by()` | PLAN_20: "the recall is why a GC pays" |

**Fixes that come before any new layer**, because every new layer inherits them:

| # | Defect | Where | Consequence today |
|---|---|---|---|
| F1 | worker maps FAILED/PARTIAL → ANSWERED | `gateway/worker.py:146-147` | failed runs look like answers |
| F2 | `s.citation` vs `Sentence.citations` | `gateway/verbs.py:215-216` | no `ask` answer has a source; approve returns NOT_FOUND; recall has nothing to join |
| F5 | no as_of filter before the model | `agents/research_question.py` | the docs claim the most important protection and the code does not have it |
| F7 | `public_only` shells out to git | `checker/public_only.py:156-195` | any container deploy refuses every `ask`, with a false reason |
| — | migration 006 used on two branches | `t0/finish` vs the orchestration branch | the next merge breaks `schema.py`'s pinned list |

## 4. Where the prediction plane plugs in

```
 verb forecast.whatif  ─► forecast.propagate ─► calls Ring 0 decider (per body) ─► Estimate(HYPOTHETICAL)
 verb forecast.rate    ─► forecast.rates     ◄─ observation_store (ForumCase rows)  ─► Estimate(DESCRIPTIVE)
 verb forecast.duration─► forecast.survival  ◄─ observation_store                    ─► Estimate(DESCRIPTIVE)
 verb forecast.change  ─► forecast.events    ◄─ corpus amendment chains + eGazette   ─► Estimate(FORECAST)
 (matter outcome)      ─► forecast.conformal ◄─ labelled resolved matters            ─► set or ABSTAIN
                               │
                               └─► Estimate.render(track_record) ─► calibration_contract.assess
                                    FORECAST without SERVABLE record → no number, a sentence
```

- **All five are read-only verbs**, so they appear on REST, MCP and CLI together (parity
  test).
- **Ring 3 is enforced by `rings.py`.** No decider can import a forecast, and the test
  proving that was written first and seen red.
- **`forecast.whatif` works on held law today.** The other four wait for data (file 03 §4).

## 5. The live-data loop (daily), with God's Eye's reliability patterns

The feed adapters exist (`checker/feeds/`: eGazette, OFAC, IBBI). **Nothing runs them on a
schedule, and nothing writes them into `observation_store`** (appendix D F8, E3). The loop:

```
 cron (GitHub Actions on a private repo, or the laptop) ─ daily 06:15 IST
   └► scripts/watch_gazette.py · watch_ofac.py · watch_ibbi · watch_sebi (NEW) · watch_rbi (NEW)
        └► checker/feeds/common/fetch.py   robots.txt honoured; 5xx fails closed
             + NEW (ported from God's Eye, MIT code, no data):
               1. staleness: cache.latest() → age → STALENESS_WARNING if older than its TTL
               2. partial success: per-source ok/fail; a dead source opens a HUMAN_REVIEW operation
               3. atomic admission: all-invalid batch = unavailable; high-water mark not advanced
               4. error taxonomy: 429 → wait Retry-After; 401/403 → denied, stop, tell a human
               5. liveness: a feed is "live" only if it admitted ≥1 recognised record
        └► observation_store.append (bitemporal: valid_at, known_at)
        └► operations.operation_for_gazette_item → tasks → lawyer-engineer queue
        └► recall: currency.affected_by() → runs that used the changed provision → notice
```

God's Eye's value to Themis is **its reliability engineering, not its globe.**

- Its providers solve "many flaky live sources, one honest status page". That is exactly
  what a daily legal feed needs.
- Its code is MIT. Its data licences (NC, SA, ODbL) mean **no data is taken**.
- The five patterns above are the port list, with file paths in appendix D §D.
- The 3-D globe, aircraft, vessels and satellites stay out. They answer no question about
  Indian law (PLAN_08, PLAN_19 02).

## 6. The human loop: lawyer-engineers and their agent

Detailed in file 05. Its place in the architecture:

```
 operations + reviews.next ─► LABELLING AGENT ─► queue sorted by value ─► lawyer-engineer
   (Ring 2/3; READ-ONLY)        pre-labels (a model PROPOSES,            reviews with the quote
                                shown greyed), picks what to              shown, decides, gives
                                label next (uncertainty sampling),        a reason
                                checks agreement, flags drift                   │
                                                                                ▼
                                             decisions (+quote_viewed, law_versions) = LABELS
                                                     │
                     ┌───────────────────────────────┼────────────────────────────┐
                     ▼                               ▼                            ▼
             gold sets per body            conformal calibration          body onboarding
             (eval, frozen splits)         (track records for Ring 3)     (ATTEST, ENCODE, TEST)
```

**The agent never decides.** It cannot write a decision: MCP has no write verbs, and
`runs.approve` needs an authenticated human key. The literature is why:

- LLM annotators score F1 0.54 on statutes (Savelka & Ashley).
- An LLM labeller must pass the Alternative Annotator Test before its labels count
  (ACL 2025).

## 7. What makes it "deep", in one table

| Capability the founder asked for | Where it lives | Honest depth today |
|---|---|---|
| Hears | ASR of the tenant's own recordings → SS-1 minutes check (PLAN_24 T8) | later |
| Reads | vault upload, OCR (measured choice), structural chunking | built for text; OCR choice open |
| Understands | extraction proposed by a model, admitted by code (spans, types, domains) | built for contracts and SS documents |
| Gives judgments | Ring 0 deciders per body; later a solver | built for CA2013 provisions; the pipeline for the rest |
| Understands research papers | research registry: `PaperCard`, model drafts, a person admits (PLAN_24 T2) | design |
| Adapts | per-tenant playbook, precedent memory, per-tenant scorers | playbook built; the rest design |
| Updates | daily feeds + recall + learning loop with a promotion gate | feeds built; loop design |
| Live data | cron feeds with staleness and liveness | adapters built; scheduler new |
| Statistics and prediction | `checker/forecast/` | **built and tested**; waits on real data |
| Simulation | `forecast.propagate`: the law applied exactly to uncertain facts | **built**; usable on held law now |
| Across many laws | the body-of-law pipeline, 9 bodies declared | 1 held; the pipeline is the plan |
