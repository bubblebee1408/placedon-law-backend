# Product build plan

Written 2026-09-01 against the repository as it stands at commit `72f4391`.
**No code was written for this document. No web search was available.**

This is the sequencing document. It does not re-argue strategy, and it does not restate designs
that already exist. It sits on top of four documents and adds only the thing none of them
provides — an ordered, gated, costed path from what is in this repo today to something a lawyer
can use:

| Document | What it already decided | What this plan does with it |
|---|---|---|
| `CLAUDE.md` | The constraints. Non-negotiable. | Treated as boundary conditions, never revisited. |
| `docs/AGENT_ARCHITECTURE_PLAN.md` | Planner / retriever / extractor / analyst / verifier / narrator / reviewer; the routing table; the measured cost arithmetic; Stages 0–5 of the *engine*. | Engine stages are consumed, not redesigned. Every cost figure here is copied from its §5, never re-estimated. |
| `docs/FEATURE_PLAN_INDIA.md` | F1–F14, the compliance-matrix column spec, the s.52 posture, the build order for *features*. | Features are consumed as the payload each product surface carries. |
| `docs/COMPETITOR_PATTERN_ANALYSIS.md` / `docs/COMPETITOR_FEATURE_MATRIX.md` | Claim classification; the vendor-sourced matrix; the HELD/PARTIAL/NONE split. | The six surfaces below are named after the matrix rows, so progress is measurable against it. |
| `research/TASKS.md` | The open ledger, including who is blocked on whom. | The dependency graph in §4 is that ledger, re-drawn as a build order. |

**The strategy is settled and is not relitigated here:** rent existing models, keep the
legal-correctness core deterministic, sell a workflow system rather than a model.

> Legora-style workflow orchestration and Harvey-style workspaces, but the legal correctness core
> is Indian, deterministic, and audit-first.

Every assumption in this document is flagged **ASSUMPTION**, **UNVERIFIED**, or **GUESS** inline
and collected in §9.

---

## 1. Honest inventory

### 1.1 The one-sentence version

**We have built a verification apparatus of unusual quality and we have not built a product.**
78 self-testing modules in `checker/` (25,902 lines) all pass. A lawyer cannot use one of them,
because there is no way to put a document in and get an answer out.

### 1.2 What EXISTS and works today

"Works" means: the module is in `scripts/run_tests.sh`, its self-test passes, and it does what its
docstring says. Verified 2026-09-01 — **all 78 suites green** (`bash scripts/run_tests.sh`).

**The verifier and its release gate — the genuine asset.**

| File | What it actually does |
|---|---|
| `checker/cascade.py` | The E6→E5→E4→E3 composition, importable. `verdict(premise, claim)` is the runtime primitive; `judge_row(row)` is the benchmark adapter. Both reach the same code. Lifted out of `metric_policy._test()` at `d6e8476` — before that, every number this project reported about the cascade was a property of a closure inside a test. |
| `checker/metric_policy.py` | Four-axis release gate: false-accept ceiling 10, F1 floor 0.40, abstention cap 0.25, per-bucket reporting. Measured today: **PASS at FA 2, F1 0.58, abstention 0.00.** |
| `checker/entail_baseline.py` (E3), `entail_binding.py` (E4), `entail_role.py` (E5), `entail_qualifier.py` (E6) | Regex, sentence segmentation, type reasoning. Readable, explainable, ₹0 to run. |
| `checker/claim_verifier.py` | Necessary-condition triage. Tops out at `LEXICAL_CANDIDATE`; `establishes_support()` is False for it. |
| `checker/grounding_policy.py` | The state ceiling. `CLAIM_ENTAILED` is reserved and nothing in this repo can produce it. |
| `checker/attribution.py` | Per-answer stage attribution — RETRIEVED / ADMITTED / SERVED / CITED / GROUNDED — carrying `system_behaved_correctly` so a correct refusal is not scored as a failure. |

**The evidence and provenance boundary.**

| File | What it actually does |
|---|---|
| `checker/evidence_pack.py` | The single boundary through which provision text reaches a model. Closed world, servability inherited from `provenance.py`, no repair of defective sources (raw text verbatim + separate `reading_text` with every transformation named). |
| `checker/admission.py` | `MODE_REVIEW` vs `MODE_MODEL`. Only `PRODUCTION_USABLE` material reaches a model-facing pack; a blocked item is reported as blocked, never silently dropped. |
| `checker/provenance.py`, `checker/commencement.py`, `checker/as_of.py`, `checker/witness_span.py`, `checker/timeline.py` | Instrument-qualified provenance; the notification that appointed a date rather than the footnote that asserts it; 434 amendment records, 431 dated. |
| `checker/legal_ref.py`, `checker/section_index.py`, `checker/mvp_freeze.py` | A provision number is never an identity. 474/517 mapped, 0 live sections unresolved, 12/12 MVP sections confirmed against India Code's own REST API. |

**Review governance — more complete than anything user-facing.**

| File | What it actually does |
|---|---|
| `checker/review_record.py` | Append-only JSONL. Pins the table by content hash, not commit. Nothing in it can reach a gold label. Refuses a second decision for a proposal unless it declares what it supersedes. |
| `checker/scoped_retraction.py` | Applies exactly the pairs a reviewer named; writes every other record back byte-identically; records the resulting knowing divergence in `deferred_drift.json`. Built because an authorisation to retract two pairs once executed as four removals. |
| `checker/benchmark_v2_freeze.py` | Freezes only `HUMAN_JUDGED` + `APPROVED` records. Raises rather than silently dropping. Identity-leak check (`identity_leaks()`) asserts no reviewer id contains an "@". |
| `checker/review_table.py`, `checker/reviews.py`, `checker/resubmission.py`, `checker/promotion_preview.py` | The reviewer's working surface as data. Decides nothing. |

**Two working vertical slices — the only end-to-end legal answers we can produce.**

- `checker/s96_slice.py` — AGM deadline. Source packet → amendment event → commencement instrument
  (`S.O. 2422(E)`, list item quoted) → dated reconstruction → deadline → evidence card. Refuses to
  render `COMPLETE` when any field is missing, and prints "must not be relied on" when it does.
- `checker/s173_slice.py` — board-meeting regime. Holds the s.173(1) **ceiling** vs s.173(5)
  **floor** distinction, names the direction on every finding, and surfaces s.174 quorum as an open
  dependency rather than certifying validity on count and gap.

**The new corporate stack (built in the last week, commits `a154ed6` → `852acdc`).**

- `checker/company_profile.py` — corporate `CompanyProfile`. Facts only, no thresholds. `Money` is
  whole rupees with `lakh()`/`crore()` constructors so mis-scaling cannot be silent. `Figure` binds
  an amount to its financial year so a comparison against the wrong year is refused. `None` means
  "not told", never zero — because for a "does not exceed X" test, zero is the strongest possible
  pass.
- `checker/classify.py` — s.2(85) small-company classification with the asymmetry stated:
  **NOT SMALL** needs one definitive failing condition; **SMALL** needs every condition known and
  satisfied.
- `checker/prescribed_thresholds.py` — dated thresholds with provenance state. **Refuses today**,
  because G.S.R. 700(E) has not been properly acquired (S-002). See §4.

**Other things that genuinely work:** `checker/matter.py` (typed, contradiction-refusing matter
with `missing_for_agm()` naming gaps *before* computation), `checker/drafting.py` +
`provenance_slots.py` (`approve()` raises on any `MODEL_SUGGESTION` or `UNKNOWN` slot),
`checker/pdf_signature.py` + `scripts/verify_document.py` (CCA India signature verification),
`checker/robots.py` (fails closed on 5xx), `checker/ss/defects.py` (SS-1/SS-2 scanner),
`backend/budget.py` (₹3,500/month, ₹116.67/day, persisted to disk so a serverless restart does not
reset it to zero).

### 1.3 What is HALF-BUILT

| Thing | What exists | What is missing |
|---|---|---|
| `checker/model_adapter.py` | The whole contract: four pre-call refusals (non-MODEL pack, no admissible evidence, **no budget tracker**, citation not in pack), rigid JSON parse, three post-parse downgrades, fail-closed on malformed output, `BUDGET_EXHAUSTED` deliberately absent from `DECISIONS` so a model can never emit it. 33 KB of tested contract. | **The model. It is a `StubModel`.** Not one real token has ever been sent. Every claim about how a real model behaves inside this contract is untested. |
| The benchmark | `corpus/benchmark/` frozen at v1.0.0, manifest hashed, `software_commit` pinned, `not_a_claim_of` field states its own limits. | **69 pairs, 5 sections, 54 CONSTRUCTED / 15 HUMAN_JUDGED, one reviewer** (`reviewer-01`). See §1.5 — it cannot measure what the gate claims. |
| Company classification | `classify.small_company()` answers definitively wherever arithmetic is not needed (a public company is not small whatever its turnover). | The arithmetic itself returns `INSUFFICIENT_DATA` because the prescribed amounts are unacquired. **Blocked on a human** (S-002). |
| The SS defect scanner | 68 ROC orders analysed, rules traced to real s.454 adjudications, `NEEDS_BOOK` scope notes for checks that are properties of the physical minutes book. | R-003: T1.4a/T1.6a/b/c/T1.7 **still over-fire**. R-008: false negatives **never measured** — every document in `corpus/testdocs/` is compliant. |
| Point-in-time reconstruction | Boundary behaviour proved on s.177, s.447, s.35 — 6/6 boundaries (`docs/TEMPORAL_PROOF.md`). 24 amended spans corroborated against the amending Acts on Indian Kanoon, 0 conflicts. | **Span-level, not section-level.** Whole-section reconstruction remains UNVERIFIED against any independent source. That distinction is exactly what the retracted claims missed (`docs/RETRACTIONS.md`). |
| The HTTP surface | `checker/app.py` + `api/index.py` + `vercel.json` — a working FastAPI app with nine routes, deployable. | **Every route serves the PoSH checker.** `/check`, `/api/ask`, `/register`, `/api/generate/*` are all HR-era. There is not one Companies Act route. R-010 (retire HR-era assets) is open. |

### 1.4 What is ONLY PLANNED — no code exists

- `checker/orchestrator.py` — the static task graph. Designed in `AGENT_ARCHITECTURE_PLAN.md` §2.2.
  Does not exist.
- `checker/step_log.py` — append-only step records. Does not exist.
- `checker/extract_adapter.py` — document → typed facts, span-verified. Does not exist.
- **The obligation register** — the authored, human-reviewed, versioned list of duties from which
  every matrix row is generated (`FEATURE_PLAN_INDIA.md` §1.2 Block A). Does not exist. **This is
  the single largest missing artefact in the product, and it is authoring work, not engineering.**
- **Any user interface for the Companies Act product.** No page, no upload, no grid, no card
  renderer. `checker/documents.py` emits print-ready HTML with correct `@page` rules, so the
  *rendering* primitive exists; nothing calls it for a corporate matter.
- F5 abolished-obligation suppression, F7 precedent drift, F12 carry-forward state, F14 corporate
  abstention register — all specified in `FEATURE_PLAN_INDIA.md`, none built.

### 1.5 The blunt part: how much of this is real

Three statements, each uncomfortable and each true.

**(a) The product is nearly nonexistent.** Of the six capability rows in
`COMPETITOR_FEATURE_MATRIX.md` that describe something a user touches, five are `NONE` and one is
`PARTIAL`. Of the six rows describing verification underneath, all six are `HELD`. That table is
the honest summary of the last four months: *behind on everything a user touches, ahead on
everything underneath it.*

**(b) `model_adapter.py` is stubbed, and the entire "rent a model" strategy is therefore
unexercised.** The contract is beautiful and untested against reality. Item 12 in
`AGENT_ARCHITECTURE_PLAN.md` §10 names the load-bearing assumption plainly: *whether a cheap
model's claims keep the release gate PASSing is UNMEASURED.* Everything from Stage 4 onward rests
on it.

**(c) The benchmark cannot measure what the gate claims.** The gate reports four axes across three
buckets. Run it today and look at what the buckets actually are:

```
RELEASE GATE — PASS
  false accepts   :      2   ceiling 10
  F1              :   0.58   floor   0.40
  abstention      :   0.00   cap     0.25
  per bucket:
    dropped_qualifier     n=9    FA=0    F1=  n/a   [no positives: F1 undefined]
    paraphrase            n=15   FA=0    F1=0.64   [no negatives: cannot detect false accepts]
    wrong_binding         n=43   FA=2    F1=0.44
```

- `dropped_qualifier` has **no positive examples at all**. F1 is undefined, not 0.00. E6 refuses
  correctly and has never been observed to accept correctly, because there is nothing in the set
  for it to accept.
- `paraphrase` has **no negative examples at all**. It cannot detect a false accept. Its F1 of 0.64
  is a measurement of one direction only.
- **Only `wrong_binding` (n=43) carries both labels**, and there the numbers are FA 2, F1 0.44 —
  materially worse than the headline 0.58.

So: two of three buckets are structurally incapable of measuring the axis the gate exists to
protect. The headline "FA 2, F1 0.58, PASS" is arithmetically correct and is being carried by a
single 43-row bucket. To the gate's credit, `metric_policy` now says this itself — it prints `n/a`
rather than a false 0.00 and flags the single-label bucket. The honesty is in the code. The
measurement is still not there.

Add the rest of the benchmark's own limits, from its own manifest: **5 sections** of **one Act**,
**54 of 69 labels CONSTRUCTED** rather than human-judged, **one reviewer**. Its `not_a_claim_of`
field states it: *"This benchmark does not measure general legal grounding."*

**Therefore: nothing in this repository entitles us to an accuracy claim of any kind today.** See
§5.

---

## 2. The six surfaces, sequenced

Six stages, named after the rows in `COMPETITOR_FEATURE_MATRIX.md` so progress is measurable
against the thing that embarrassed us.

The engine stages in `AGENT_ARCHITECTURE_PLAN.md` §8 map onto these as follows, and are **not**
re-planned here:

| Product stage | Engine stages consumed |
|---|---|
| Stage 1 — compliance matrix | Engine Stage 0 (partly done: `cascade.py` lifted, budget wired) + Engine Stage 1 (orchestrator) |
| Stage 2 — matter workspace | — (deterministic; new `checker/store.py`) |
| Stage 3 — tabular review | — (deterministic; generalises `review_table.py`) |
| Stage 4 — workflow agents | Engine Stage 2 (extractor) + Engine Stage 3 (answer, shadow first) |
| Stage 5 — research with citations | Engine Stage 4 (narrator) |
| Stage 6 — review governance | — (surfaces machinery that already exists) |

### Stage 1 — Compliance matrix. **Zero LLM. A complete product on its own.**

This stage is load-bearing in a way the others are not. **It must require no API key, no model, no
network call to any provider, and it must be a correct and useful product with all of that
absent** — because it is what every later stage degrades to when the budget runs out. If the daily
cap trips at 11am, Stage 1 is what a user sees for the rest of the day, and they must not be able
to tell that anything is missing except the prose.

**What ships**

- `checker/orchestrator.py` — the static task graph. Matter type → ordered step list. The model
  never chooses a step; an unknown matter type is a refusal, not a fallback.
  (`AGENT_ARCHITECTURE_PLAN.md` §2.2.)
- `checker/step_log.py` — append-only JSONL step records. Every later stage depends on this
  existing first; it is also the cache (§6.3 of the architecture plan).
- **The obligation register**, v0: 10–15 obligations, hand-authored, each with `obligation_id`,
  provision as an instrument-qualified `legal_ref`, an `applicability` expression, and a named
  human author. Versioned. **This is the critical authoring task of the whole plan.**
- The matrix assembler: `CompanyProfile` + `as_of` date → rows, Blocks A–F per
  `FEATURE_PLAN_INDIA.md` §1.2. Rows generated from the profile, never from documents — **a company
  with zero documents still gets a full matrix, every evidence cell reading `NO_EVIDENCE_HELD`.**
  That output is correct and is the most valuable thing in the table.
- Features F1, F2 (s.96 card), F3 (s.173 card), F4 (class engine, degraded — see below), F11
  (source-defect disclosure inline), F14 (abstention register).
- The first Companies Act HTTP surface: one page, upload nothing, type facts, get a matrix, print
  it. Reuse `checker/documents.py`'s `@page` rules. Retire the PoSH routes in the same commit
  (R-010).
- `scripts/preflight.py` extended with the s.52 render-time ratio check
  (`FEATURE_PLAN_INDIA.md` §6): a view whose quoted-statute character count exceeds its
  original-matter character count fails to render.

**Smallest version that is genuinely useful**

Two matter types — `BOARD_MEETING_GAP` and `AGM_DEADLINE` — over one company, facts typed by hand,
printed to PDF. That alone answers the practitioner's real first-hour question on a new client
("what does this company owe, and by when"), with every figure carrying its source and every gap
named. Both slices already exist; the orchestrator is roughly 150 lines of state machine.

**What it does NOT claim**

- It does not read documents. Facts are typed.
- It does not cover any section beyond s.96 and s.173 at first, and the register's coverage is
  whatever a human wrote down.
- **It does not establish entailment.** Nothing in this repo can produce `CLAIM_ENTAILED`.
- **It does not claim accuracy.** B-001 does not exist; `CLAUDE.md` forbids the claim.
- **It cannot classify a small company on the arithmetic** — `prescribed_thresholds.lookup()`
  refuses until S-002 is resolved. It will answer NOT SMALL definitively where no threshold is
  needed, and `INSUFFICIENT_DATA` otherwise. Shipping this refusal visibly is *better* product
  than a confident ₹4 crore nobody sourced, and the UI must say so in words.
- It does not colour a row green, emit a score, a percentage or a "compliance health" figure
  (`checker/epistemic_status.py`), or hide a row it could not evaluate.

**Cost: ₹0.0000 per matter.** No API key required to run the product.

### Stage 2 — Matter workspace

Harvey's Vault is a bulk document store. Ours is not, and must not try to be — the Indian solo
practice has no document mass (`FEATURE_PLAN_INDIA.md` §0). A *matter workspace* is a per-company
register that carries state across years.

**What ships**

- `checker/store.py` — persistence for `CompanyProfile`, prior matrices, and per-year
  determinations. **ASSUMPTION:** flat JSON on disk is sufficient at this user count. The repo has
  zero third-party dependencies and `NON_GOALS.md` rejects Neo4j/Pinecone/Elasticsearch/Celery.
- F12 carry-forward state: `previous_agm_date`, class per year, s.92/s.137 default history, MSC-2
  date. Without it the fifteen-month AGM limb, the annual small-company re-test and the para 2A
  gate cannot be computed at all.
- **Correction propagation.** A correction to year N invalidates every downstream row and forces
  re-derivation. Silently leaving stale downstream rows is the failure mode this feature creates
  and must be tested against directly.
- F13 document authenticity check as an intake step (`checker/pdf_signature.py`) — with a UI that
  cannot let signature validity be confused with a compliance finding.

**Smallest useful version:** one company, three financial years, one correction that visibly
invalidates downstream rows.

**What it does NOT claim:** that user-entered history is verified. It is not. Nothing here reads a
filing. A carried-forward AGM date is a user fact with a `USER_FACT` provenance label
(`checker/matter.FACT_ORIGINS`), and it renders as one.

**Cost: ₹0.0000 per matter.**

### Stage 3 — Tabular review, transposed

`COMPETITOR_FEATURE_MATRIX.md` records our grid as `PARTIAL`: `review_table.py` builds a traceable
grid, but its axes are documents × rules, not documents × questions. `COMPETITOR_PATTERN_ANALYSIS.md`
§4.4 makes the deeper point — **the natural grid is transposed.** Legora's rows are documents you
have. Ours are obligations the law imposes.

**What ships**

- The matrix rendered as a real grid: obligations × (company, financial year), with row expansion
  showing Blocks D–F verbatim.
- Multi-company view: one grid across a practice's client list at one `as_of` date.
- Export with `export_hash` per row (sha256 of the rendered row), so a row quoted in a file note
  can be shown to be the row we produced.
- F5 abolished-obligation suppression as `INAPPLICABLE` rows that state the omitting instrument,
  its clause, its commencement, and the date range in which the duty existed. Auditor ratification
  under the first proviso to s.139(1), omitted by Act 1 of 2018 s.40 w.e.f. 7 May 2018, is the
  canonical row. A suppression is as much a legal assertion as a finding and carries the same
  evidence burden.

**Smallest useful version:** five companies × the v0 obligation register at one date, printable.

**What it does NOT claim:** completeness of the obligation set. **An obligation nobody authored
into the register cannot appear, and false negatives are structural and currently unmeasured**
(R-008). This is the single largest honesty risk in the product and the UI must carry it as a
standing statement, not a footnote.

**Cost: ₹0.0000 per matter.**

### Stage 4 — Workflow agents. **First real LLM call in the product's history.**

**What ships**

- `checker/extract_adapter.py` (Engine Stage 2): document → typed `Matter` slots. Every extracted
  value must be a **verbatim span present in the uploaded document**, checked by exact substring
  match at a stated offset after whitespace normalisation only. Failure → slot is `UNKNOWN`, never
  guessed.
- Its own fixture set including documents where the field is **genuinely absent**, and its own gate
  row set, before it ships (`AGENT_ARCHITECTURE_PLAN.md` §3.4 obligation 1).
- The answer step (Engine Stage 3) **in shadow mode first**: run it, log it, do not serve it.
- Serving gate: `evaluate_gate` still PASSes with the model's claims in the loop, **and no bucket
  regresses against Stage 1's deterministic numbers.**
- Haiku tier by default. Standard tier only if the gate measurably improves — which is the test of
  `PROVIDER_DECISION.md`'s claim that model choice is a cost lever and not a correctness one.

**Smallest useful version:** extractor only, on one document type (AGM notice), pre-filling a
`Matter` the user then confirms. The answer step stays in shadow indefinitely if the gate says so.

**What it does NOT claim**

- `GROUNDED`. Claims top out at `CLAIM_QUALIFIERS_CHECKED`.
- That extraction is exhaustive. An `UNKNOWN` slot means "we did not find it", never "it is not
  there."
- That the document is legally correct or complete.
- **OCR.** Every document in `corpus/testdocs/` is text-extractable, so OCR quality is entirely
  untested. **UNVERIFIED** whether real small-practice intake is scan-heavy; `FEATURE_PLAN_INDIA.md`
  §4 flags this as "not yet" rather than "never".

**Cost:** extractor ₹0.3809/document; extractor + answer ₹0.8856/matter. See §6.

### Stage 5 — Research with citations

**What ships**

- F9 dated provision reading — "what did s.96 say on 12 June 2018, and what changed the next day"
  — **as a card, never as a browser.** Fidelity `EXACT`/`PARTIAL`/`ABSTAIN` and the basis sentence
  on the same screen.
- F8 commencement provenance card, including the explicit `NOT SUPPORTED BY A NOTIFICATION WE HOLD`
  where absent. Gazette matter is clean under s.52(1)(q)(i), so prefer the gazetted instrument.
- F10 qualifier-preservation check on a sentence the user pastes.
- The narrator (Engine Stage 4): prose over an already-decided card, cheapest tier,
  `MODEL_SUGGESTION`-labelled so `drafting.approve()` blocks by construction, **skipped entirely
  when the budget is short.**

**Smallest useful version:** F8 alone. It is built (`checker/commencement.py`), it is structurally
unique to us, and it needs no model.

**What it does NOT claim:** anything legal from the prose. F9 is **the highest-risk feature in the
plan** on s.52(1)(q)(ii) and is buildable only as a card — never a statute browser, never a
side-by-side clean-text diff, never a download. It was blocked once already
(`docs/PLAN_REVIEW_KIMI_2026_08_22.md`). **Open and UNVERIFIED:** whether machine-generated
commentary satisfies (q)(ii) at all is a counsel question, human-gated, unanswered.

**Cost:** cumulative ₹1.4094/matter with the narrator on.

### Stage 6 — Review governance as a product surface

The machinery here is the most complete in the repo and is already load-bearing from Stage 1 —
`review_record.py` is how the obligation register gets reviewed at all. What Stage 6 adds is the
*multi-person* surface: a firm's reviewer approving rows, an attestation trail, a retraction path
when an obligation turns out to be wrong.

**What ships**

- Reviewer queue over live matrix rows (generalising `review_queue.py` + `review_table.py`).
- Firm-level attestation: who signed off which row, against which version of the register, pinned
  by content hash.
- Scoped retraction of a published row, using `scoped_retraction.py`'s discipline: apply exactly
  what was named, write everything else back byte-identically, record the knowing divergence.
- A public "what we got wrong" surface. `docs/RETRACTIONS.md` already exists as the internal
  version and is, honestly, a marketing asset nobody else in this market has.

**Smallest useful version:** one reviewer, one attestation, one retraction, all visible in the
export.

**What it does NOT claim:** that review makes a row correct. It records who believed what, when,
against which version. Nothing more.

**Cost: ₹0.0000.**

---

## 3. Why Stage 1 must be the whole product first

Three reasons, stated once so they are not argued again.

1. **It is the degradation target.** `backend/budget.py` degrades to template mode on exhaustion
   and says so. If Stage 1 is not independently complete and correct, then "budget exhausted"
   means "broken product" rather than "less prose".
2. **The moat is in it.** Point-in-time reconstruction, commencement provenance, refusal on
   unacquired subordinate legislation, source-defect preservation — all four `HELD` rows that
   neither competitor's marketing mentions — are deterministic and land entirely in Stage 1. **The
   differentiated product needs no model at all.**
3. **It is the only stage we can build without measuring anything first.** Stages 4 and 5 are
   gated on measurements that do not exist. Stage 1 is gated on authoring work and a state
   machine.

---

## 4. Dependency graph, and which stages are blocked on a person

### 4.1 The graph

```
                    [obligation register v0]  ← AUTHORING, human, not code
                              |
  [cascade.py ✓]              |             [step_log.py]
  [budget wired ✓]            |                  |
        \                     |                  /
         +----------> STAGE 1: compliance matrix <----- [orchestrator.py]
                              |
                              |  (F4 arithmetic degraded)........ S-002 ⛔ HUMAN
                              |
                              v
                    STAGE 2: matter workspace
                              |
                              v
                    STAGE 3: tabular review
                              |          \
                              |           \...... R-003 (over-firing) blocks F6/SS scan
                              v
                    STAGE 4: workflow agents ........ needs extractor fixtures (new work)
                              |                      needs gate to PASS with model claims (UNMEASURED)
                              v
                    STAGE 5: research + narrator .... F9 gated on counsel (s.52 q(ii), UNVERIFIED)
                              |
                              v
                    STAGE 6: review governance

  ACROSS ALL STAGES, gating CLAIMS and not development:
      B-001 ⛔  no real-document benchmark          → no accuracy claim, any stage
      H-001 ⛔  zero practising-lawyer review       → no legal-quality claim, any stage
      S-001 ⛔  SD-004 s.174(1) has no witness      → s.174 quorum rules cannot be promoted
      R-008 ⛔  false negatives never measured      → no coverage claim, any stage
```

### 4.2 Blocked on a person, not on code

This is the part that gets quietly skipped, so it is stated flatly.

| ID | What is blocked | Who must act | What the block actually is |
|---|---|---|---|
| **S-002** | **Small-company arithmetic. Therefore F4, therefore every matrix row whose applicability depends on small-company status.** | **Founder.** | G.S.R. 700(E) is located — India Code handle `123456789/508916`, text bitstream uuid `6d5e9902-…`, 5,153 bytes — and **both official acquisition routes are closed to automation**: `indiacode.gov.in/robots.txt` returns HTTP 502 and `checker/robots.py` fails closed by RFC 9309 (a 5xx means we cannot know the rules), and eGazette chains to a root absent from this machine's trust store. The fix is a **human downloading a file** and running `python3 scripts/register_gsr700e.py <file>`. No amount of engineering removes this. Until then `prescribed_thresholds.lookup()` refuses, correctly. |
| **S-001** | Promotion of `v2-174-1-rule-pos`; any s.174 quorum rule. | Researcher, but needs an authoritative witness we do not hold. | India Code serves "of a company **hall** be one-third" — a transcription defect (SD-004). `CLAUDE.md` forbids repairing a defective government source, so the text stays verbatim and the rule stays unpromoted until an independent authoritative rendering exists. Note the second-order damage: SD-004 also proves phrase-matching misses real qualifiers — `as may be prescribed` does not match s.101(1) because India Code serves `maybe`. |
| **B-001** | **Every accuracy claim, at every stage.** Marked *CRITICAL PATH* in `research/TASKS.md`. | Founder + benchmark-engineer. | 30–50 corporate-law documents **including deliberately defective ones**. We hold 29 documents (18 real, 11 ICSI specimens) and **all of them are compliant** — so false negatives have never been measured (R-008) and cannot be. We hold **zero minutes books**; none is public and none was sought. |
| **H-001** | Every claim about legal quality. Explicitly recorded as gating *claims, not development*. | **Founder.** | Zero practising corporate lawyers have reviewed anything in this repository. The one reviewer in the benchmark manifest is `reviewer-01` — a pseudonymous id, one person, not recorded as a practising lawyer. |
| **H-002** | Indian Kanoon corroboration at scale. | Founder. | ₹10,000/month exceeds the entire ₹3,500 budget. Free non-commercial tier application unfiled. |
| **H-004** | Any live practitioner voice; therefore all of `FEATURE_PLAN_INDIA.md` §5 (distribution). | Founder. | Reddit OAuth credentials. Described in the ledger as *the only route to a live practitioner voice*. |
| **R-011** | Any market figure used externally. | Founder/main. | The market model is CS-segment-based; the segment changed to lawyers on 20 Aug. No figure in it may be quoted. |

**The honest summary of this table:** Stage 1 can be built today, at reduced coverage, with F4
visibly refusing. **Nothing at any stage can be claimed** until B-001 and H-001 are resolved, and
both are founder tasks with zero progress recorded. Development is not blocked. Assertion is
entirely blocked.

---

## 5. What must be TRUE before any accuracy claim is made publicly

`CLAUDE.md`: *"Never claim legal accuracy without an independent benchmark."* Concretely, **all**
of the following, and the word is *all*:

1. **B-001 exists.** 30–50 real corporate documents, from real practice, **including deliberately
   defective ones**, labelled by someone who is not the author of the checker.
2. **False negatives are measured** (R-008). Until a known-defective document has been shown to the
   scanner, "it found nothing" and "there was nothing" are indistinguishable.
3. **R-003 is closed.** T1.4a/T1.6a/b/c/T1.7 no longer over-fire. The measured 80–93% false
   positives when minutes checks ran on notices is a disqualifying number and must be re-measured
   after the fix, not assumed fixed.
4. **The benchmark has both labels in every scored bucket.** Today `dropped_qualifier` has no
   positives and `paraphrase` has no negatives, so **two of three buckets cannot measure the axis
   the gate exists to protect.** A gate passing on one 43-row bucket is not a measurement of a
   system.
5. **The benchmark is not 54/69 CONSTRUCTED, not five sections, and not one reviewer.** Its own
   manifest says it does not measure general legal grounding. Quoting its numbers as accuracy would
   contradict the file itself.
6. **H-001 is done.** One or two practising corporate lawyers have reviewed the obligation register
   and a sample of output, and their role and PQE are recorded. Never present student feedback as
   lawyer validation (`docs/EVIDENCE_PROTOCOL.md`).
7. **Independent-publisher corpus verification exists.** Corpus status is `NOT_FULLY_VERIFIED`, and
   both renderings we compared are India Code — a defect in their own source is invisible to that
   check.
8. **Section-level reconstruction is corroborated, or the claim is stated at span level only.**
   24 spans, 0 conflicts, is a span-level result. `docs/RETRACTIONS.md` exists because that
   distinction was missed once already.
9. **The claim names its scope in the same sentence.** "n sections of the Companies Act 2013, on
   documents of type X, measured against benchmark version V." Anything broader is unsupported.

**Until every one of these holds, the permissible public statements are process claims, not
accuracy claims:** what the system refuses to do, what it discloses, what it carries as provenance,
and what it will not say. Those are true today and are, per `COMPETITOR_FEATURE_MATRIX.md`, things
neither competitor's marketing leads with.

**Also permanently forbidden regardless of benchmark:** any claim about what a competitor *cannot*
do. Absence from a marketing page is not absence from a product.

---

## 6. Cost per stage against the ₹3,500/month cap

Every figure below is **copied** from `AGENT_ARCHITECTURE_PLAN.md` §5, which derived them from
`backend/budget.py`. **No new estimates appear in this section.** Reproduce with
`PYTHONPATH=. python3 backend/budget.py`.

Ground truth: monthly cap **₹3,500**, derived daily cap **₹116.67**, USD/INR **95.23** (dated
2026-08-06, stale by ~4 weeks). Anthropic list pricing per million tokens: haiku-4-5 (1.00/5.00),
sonnet-5 (3.00/15.00), opus-5 (5.00/25.00). List prices are deliberate — *a budget guard must only
ever be wrong in the expensive direction.*

### Per stage

| Product stage | LLM calls per matter | Cost per matter | Matters/month at the cap | Matters/day at ₹116.67 |
|---|---|---|---|---|
| **Stage 1 — compliance matrix** | **0** | **₹0.0000** | **unbounded** | **unbounded** |
| **Stage 2 — matter workspace** | 0 | ₹0.0000 | unbounded | unbounded |
| **Stage 3 — tabular review** | 0 | ₹0.0000 | unbounded | unbounded |
| **Stage 4 — workflow agents** (extractor only) | 1 | ₹0.3809 | ~9,188 | ~306 |
| **Stage 4 — workflow agents** (extractor + answer) | 2 | ₹0.8856 | ~3,952 | ~131 |
| **Stage 5 — + narrator** | 3 | ₹1.4094 | ~2,483 | ~82 |
| Stage 5, all sonnet instead of haiku | 3 | ₹4.2283 | ~827 | ~27 |
| Stage 5, batched (50% off) | 3 | ₹0.7047 | ~4,966 | ~165 |
| **Stage 6 — review governance** | 0 | ₹0.0000 | unbounded | unbounded |

Per-call components, measured on real packs (`build_prompt()` on a one-provision MODE_MODEL pack —
s.173 7,238 chars ≈ 1,809 tokens, s.96 6,285 chars ≈ 1,571 tokens; token counts are `chars/4`,
**APPROX**):

| Step | in / out | haiku-4-5 | sonnet-5 | opus-5 |
|---|---|---|---|---|
| extractor | 2000 / 400 | **₹0.3809** | ₹1.1428 | ₹1.9046 |
| answer (1-provision pack) | 1800 / 700 | **₹0.5047** | ₹1.5142 | ₹2.5236 |
| answer (3-provision pack) | 6700 / 700 | ₹0.9713 | ₹2.9140 | ₹4.8567 |
| narrator | 2500 / 600 | **₹0.5238** | ₹1.5713 | ₹2.6188 |

### What the arithmetic decides

- **Stages 1–3 and 6 cost ₹0 and are four of the six surfaces.** The differentiated product is the
  free one to run. Idle cost is ₹0 — no vector index to host, no embedding service, no queue
  worker.
- **The routing table is a constant, not a router.** Everything goes to the cheap tier, because
  `applicability.py` decides and the cascade rejects. Nothing is routed to opus at any stage:
  `docs/MODEL_PLAN.md` finding 2 records that stronger-reasoning models are *worse* at temporal
  applicability — they collapse onto "apply the current law", which is the exact failure this
  product exists to catch. Spending 5× for a documented regression is not a trade-off.
- The spread is the point: **6,934 one-provision haiku answers vs 720 three-provision opus answers**
  from the same ₹3,500 — a **9.6×** difference in how many users the budget serves.
- **Deliberately not in the arithmetic:** prompt caching (**UNVERIFIED**, treat as upside only),
  retries (budget must be charged on the *attempt*), introductory pricing (list prices used).
- **GUESS, flagged in the source and repeated here as a guess:** iteration of 2–4× per matter in
  real use, which would put the effective Stage 5 figure nearer ₹1.4–₹2.0 than N × ₹1.4094. **No
  user data exists behind this. It must be measured before it appears in any pitch.**

---

## 7. What we are NOT building

Consolidated from `docs/NON_GOALS.md`, `AGENT_ARCHITECTURE_PLAN.md` §9 and
`FEATURE_PLAN_INDIA.md` §4. Reasons are given so each can be revisited on evidence rather than on
enthusiasm.

**Refused on evidence**

| Not building | Why |
|---|---|
| Vector database / embedding retrieval | Not the 768 KB of vectors — the 2 GB dependency, a second inference surface, a standing fee against ₹3,500, and **a retriever that cannot abstain.** Decisive: the repo's known Act-vs-Rule collision (`retrieve.py`, `"rule 4"` → s.398, s.469) is a bug embeddings make *worse*, because `s.173` and `rule 173` are near neighbours in exactly the space a dense retriever ranks in. **Revisit when** a Companies Act retrieval benchmark shows recall@3 < ~0.90 on practitioner phrasings naming no provision. Build the benchmark first; it is cheaper than the thing it would justify. |
| LLM-as-judge, self-critique, self-consistency voting | An LLM judge inherits the same recency bias it is meant to detect (Magesh et al.; Cymbler et al. used deterministic regex nuggets instead). All variants multiply cost by N and measure agreement among samples from one distribution, which is not evidence about the law. |
| Autonomous tool-calling / ReAct loops | A model that chooses its next action chooses which provision to look at, and applicability is the one thing that must never be the model's call. Also makes per-matter cost unbounded against a ₹116.67 daily cap. |
| Fine-tuning / a trained NLI head / a foundation model | No data rights, no budget, not the moat. **One tension recorded honestly:** `docs/MODEL_PLAN.md` proposes a fine-tuned NLI head as "the one place a trained model earns its place". This plan does not authorise it, because the deterministic cascade is at FA 2 / F1 0.58 with zero training, and the largest remaining deterministic gap (`dropped_qualifier`, no positives at n=9) costs a day of reading nine claims and extending `entail_qualifier.qualifiers_in()`. Fix that first; revisit only if the cascade then plateaus below what the product needs, with the measurement in hand. |
| Parallel fan-out over large document sets | 100 documents × ₹0.38 = ₹38 for one matter — a third of the entire *daily* cap on one user. We hold one Act; `CLAUDE.md` forbids obtaining private minutes. And each branch needs its own admitted pack and citation-id namespace, so it is not parallelism, it is volume. |
| Firm playbook diff | Needs the firm's private precedent library, which the source policy forbids and a solo practice does not have. Worse: it inverts the failure — a document matching the house standard and three amendments out of date reads as *clean*. |
| Vault / data-room / document-mass features | Building for an asset the customer does not own is the whole mistake this plan exists to avoid. |

**Refused on law or policy**

| Not building | Why |
|---|---|
| Clean-statute browser, Act download, side-by-side clean-text diff | s.52(1)(q)(ii). Act text is servable only together with original matter. Blocked once already; enforced by `scripts/preflight.py` and the render-time ratio check. |
| Case-law citations | We hold **zero** judgments. A fabricated citation carried into a filing ends the customer's credibility with a judge and ours with the profession. "We hold statute only" is itself the differentiator. |
| Penalty-backed findings with no enforcement precedent | Route map in an AGM notice, leave of absence, dissent, numeric day-count shortfall — **zero** orders across 1,609 tagged. Advisory only, labelled. Also refuse "high enforcement risk": SS orders are ~4% of published adjudication orders; filing defaults dominate at 16.2%. |
| Automatic MCA filing | Transfers liability to us and depends on a portal we do not control. |
| Scraping MCA / paid publishers / user-agent rotation | Source policy. Rejected once already. |
| Repairing a defective government source | `CLAUDE.md`. `hall` stays `hall`. A harmless instance is not an exception. |

**Refused on epistemics**

| Not building | Why |
|---|---|
| Compliance score / risk percentage / "compliance health" | `checker/epistemic_status.py`: no aleatoric uncertainty to model, calibration unreachable at zero labels, and the arithmetic launders invention into something that reads as measurement. |
| "Legally compliant" certification | A legal conclusion. We do not make it. |
| Green rows | `VERIFIED` means *the evidence chain is complete*, not *the company is compliant*. |
| Generic deadline calendar with push alerts | Only where the date is statute-fixed **and** evidenced. A confidently wrong reminder is worse than none, and is exactly where auditor-ratification-style false positives get generated. |
| General legal chatbot / "chat with the Act" | Abandons the wedge, and is the fastest route to serving bare statutory text. |
| A document generator | ComplyRelax is free to ICSI members until 31 Mar 2029 with 201 unbroken updates. Generation is commoditised; the audit layer is not. |

**Not yet, rather than never — flagged as a risk**

- **OCR intake.** Every document in `corpus/testdocs/` is text-extractable, so OCR quality is
  entirely untested. Real small-practice intake is plausibly scan-heavy. **UNVERIFIED.** Settled by
  collecting 20 documents in the format they actually arrive in — one week of work that also
  settles the file-format question.
- **Word add-in, email-in, API integration.** Whether Indian small practices use Word desktop,
  Google Docs or LibreOffice is **completely unverified**. Browser app first, because it is the only
  surface whose enabling work is already done. WhatsApp is **probably a trap** — no audit trail, and
  a terrible surface for a dense evidence card.

---

## 8. Kill criteria

Each stage gets evidence that would say it is wrong. These are written now, before the data, so
they cannot be renegotiated afterwards.

### Stage 1 — compliance matrix

**Kill or redesign if:**
- Five practitioners are shown a matrix for a company they know and **fewer than three can name an
  obligation the register missed** — that would mean it looks complete and is not, which is worse
  than obviously thin. (Inverse also kills it: if all five name five or more misses each, the
  register is not a product, it is a stub.)
- The `NO_EVIDENCE_HELD` row — the thesis of the whole feature — is read by practitioners as noise
  rather than as the useful part. This is the central bet of `FEATURE_PLAN_INDIA.md` §0 and it is
  **UNVERIFIED**.
- With F4 refusing on small-company arithmetic (S-002), practitioners find the matrix unusable
  rather than admirably cautious. **This is the highest-probability kill in the list** and it is
  measurable in a week with five conversations.
- Row generation from a profile turns out to require facts practitioners do not have to hand at the
  start of a matter, so the input cost exceeds the output value.

### Stage 2 — matter workspace

**Kill if:** practitioners do not carry state between years in a form they would type into us —
i.e. the fifteen-month AGM limb is answered from a file they already have, and a second system to
maintain is a cost rather than a saving.

### Stage 3 — tabular review

**Kill if:** the transposed grid (obligations × companies) is consistently misread as the
conventional one (documents × questions), or practitioners with fewer than ~10 client companies
find no value in a multi-company view — which would make it a feature for a segment we have not
identified.

### Stage 4 — workflow agents

**Kill the answer step if:**
- `evaluate_gate` does not PASS with a cheap model's claims in the loop. **The honest response is
  to ship Stages 1–3 and the extractor only — not to buy a bigger model.** Buying up-tier converts
  a correctness failure into a cost failure and hides it.
- Any bucket regresses against Stage 1's deterministic numbers.
- Extraction span-verification fails often enough that most slots come back `UNKNOWN`, making the
  extractor slower than typing.
- Real intake turns out to be scan-heavy and OCR error rates break exact substring matching — in
  which case the extractor's entire safety property is unavailable and the step must not ship.

### Stage 5 — research with citations

**Kill F9 if:** counsel answers that machine-generated commentary does not satisfy s.52(1)(q)(ii).
This is a binary legal answer, not a product judgement, and it kills the feature outright rather
than shrinking it.
**Kill the narrator if:** users cannot tell `MODEL_SUGGESTION` prose from decided output in
testing. The label existing in the data model is not the same as the distinction surviving in a UI.

### Stage 6 — review governance

**Kill if:** solo practitioners — the primary segment — have nobody to review anything, making the
whole surface a feature for firms we have not sold to. **ASSUMPTION, UNVERIFIED:** that a
reviewable trail matters to a buyer at all. It matters to us for correctness regardless, so the
internals stay either way; only the *surface* is killable.

### Kill criteria for the strategy itself

Written because a plan with no strategy-level kill criterion is a plan that cannot be wrong.

- **If B-001 shows the deterministic core is not more accurate than a frontier model answering
  directly on the same questions**, the "deterministic core is the moat" thesis is dead and the
  correct response is to stop building and re-plan. This is the single most important measurement
  in the project and it does not exist.
- **If H-001 reviewers find the obligation register materially wrong**, the register — not the
  engine — is the product risk, and effort should move from code to legal authoring.
- **If S-002 stays blocked for another quarter**, small-company status is unanswerable, and a large
  fraction of the private-company obligation set cannot be evaluated. At that point the honest move
  is to narrow the product to obligations that do not depend on class, and say so publicly.

---

## 9. Assumptions, collected

| # | Assumption | Status |
|---|---|---|
| 1 | Model IDs and per-million pricing in `backend/budget.py` | **UNVERIFIED.** No web access. `PROVIDER_DECISION.md` §7 records three prior plans that each named a retired identifier. Check the registry before writing code. |
| 2 | Token counts (`chars/4`) | **APPROX.** Char counts are measured; the divisor is a convention. |
| 3 | USD/INR 95.23 | Dated 2026-08-06. Stale by ~4 weeks. |
| 4 | Prompt caching economics | **UNVERIFIED.** Not modelled. Upside only. |
| 5 | Batch API 50% discount | Modelled in `budget.py`; not re-verified. Batch is latency-asynchronous and may not suit an interactive path. |
| 6 | 2–4× iteration per matter | **GUESS.** No user data. Must be measured before it appears anywhere else. |
| 7 | A cheap model's claims keep the gate PASSing | **UNMEASURED.** Load-bearing for Stage 4. |
| 8 | Extractor accuracy on real Indian corporate documents | **UNMEASURED.** No extraction fixtures exist. |
| 9 | Flat JSON persistence is sufficient for Stage 2 | **ASSUMPTION.** Consistent with zero-dependency policy; untested above trivial volumes. |
| 10 | The browser app is the right first surface | **Reasoned, not evidenced.** `FEATURE_PLAN_INDIA.md` §5.1: nothing in this repository records where an Indian corporate practitioner does this work. Four interviews, all lawyers, none a CS. Four is not a sample. |
| 11 | `NO_EVIDENCE_HELD` rows are the valuable output | **UNVERIFIED and central.** The whole matrix thesis rests on it. Testable with five conversations. |
| 12 | Real intake is text-extractable | **UNVERIFIED and probably false.** All 29 corpus documents are text-extractable by selection, not by sampling how documents arrive. |
| 13 | Practitioners prefer a visible refusal to a confident unsourced number | **ASSUMPTION**, and it is the personality of the entire product. If false, Stage 1 fails its kill criterion. |
| 14 | Machine-generated commentary satisfies s.52(1)(q)(ii) | **UNVERIFIED, counsel question, human-gated.** Operating assumption is the conservative one. |
| 15 | Competitor capabilities | Vendor marketing pages only, fetched 2026-09-01. **Absence from a page is not absence from a product.** No claim about what a competitor cannot do is permitted anywhere. |

---

## 10. One-paragraph summary

We have a verification apparatus that is genuinely unusual — a deterministic cascade that cannot
hallucinate its own critique, gated on four axes, plus point-in-time reconstruction, commencement
provenance, source-defect preservation and immutable review governance — and we have no product:
no user interface for the Companies Act at all, a stubbed model adapter that has never sent a
token, and a benchmark of 69 constructed pairs across five sections in which two of three scored
buckets are structurally incapable of measuring the axis the gate exists to protect. The plan is
therefore to build the four ₹0-cost surfaces first — compliance matrix, matter workspace, tabular
review, review governance — because they carry the entire differentiation and require no model,
and to treat the two model-bearing surfaces as extensions that must degrade cleanly back to them.
Stage 1 is the whole product: a company profile and a date in, an obligation matrix out, every
figure carrying its source, every gap named, every refusal visible, at ₹0.00 per matter and no API
key. The gating work is not engineering: a human must download G.S.R. 700(E) before small-company
arithmetic can answer at all, a human must assemble thirty defective documents before any accuracy
claim is permissible, and a practising lawyer must read the obligation register before we may say
anything about legal quality. Development is not blocked. Assertion is entirely blocked, and this
document exists partly so that stays true.
