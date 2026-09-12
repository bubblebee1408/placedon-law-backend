# The features — the canonical list

**This document supersedes every earlier feature and roadmap document in this
repository.** Those were deleted rather than left to rot; the tombstone list is in
[PLAN_00_INDEX](PLAN_00_INDEX.md). If a feature is not here, it is not planned.

Eleven features, three phases. Each one names what it does, what exists today, and
what is missing — because "planned" and "built" are different words and this
repository does not blur them.

**Scope note.** These features operate across the whole of Indian corporate-law
compliance — Companies Act, LLP Act, SEBI, FEMA, IBC, competition, stamp duty,
DPDP — not the Companies Act alone. `checker/scope.py` is the register and the
authority. Today one of those nine bodies is held; the rest are DECLARED, which
means a question there is refused with the body named and the gap stated. Every
feature below inherits that: **F2's matrix has fifteen rows because that is what
the Companies Act corpus supports, not because fifteen is the whole of corporate
law.**

---

## Phase 1 — the wedge

### F1 · Document Currency Check *(the Word add-in)*
Audits the document open in front of the lawyer against the law in force **on that
document's date** — flags superseded figures, names the instrument that moved
them, and refuses what it cannot verify.

- **Status:** **BACKEND BUILT.** `POST /v1/document-check` is live and tested
  (`checker/api.py`), and `checker/document_extract.py` grounds an extractor's
  proposals against the document. Full spec in [PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md).
- **Reuses:** `obligations` · `as_of` · `currency` · `staleness` · `api.handle`
- **Missing:** the Office.js task pane. **Only the UI** — the route this file
  previously listed as missing had already shipped a day before the claim was
  written, which a review caught.
- **Why first:** it needs no MCA data, no Gazette feed, no OCR, and no citator —
  every blocker the research found applies to other products, not this one.

### F2 · Compliance Matrix
Company facts → 15 obligation rows, each saying whether the duty attaches, whether
it looks met, or what is missing. Rows come from the law, so a company that has
uploaded nothing still gets a full matrix.

- **Status:** BUILT. `obligations.py` (1,448 lines), live at `POST /v1/compliance-pack`,
  HTML via `matrix_view.py`.
- **Missing:** a facts-in form a non-engineer would use.
- **Caveat that matters:** **2 of 15 rows refuse** on an unheld rule — s.177
  (Rule 6, held but unread) and s.203 (chain traced, unconfirmed). s.2(85) now
  answers, because G.S.R. 880(E) was attested on 2026-09-10.

### F3 · Evidence Pack / Verified Report
The matrix as a dated, cited, hash-stamped document a CFO can hand to diligence
counsel, with an explicit "what could not be verified" list.

- **Status:** BUILT. `diligence_pack.py` renders it today.
- **Missing:** print/PDF output and a shareable link.

---

## Phase 2 — currency, which is the moat

### F4 · Company Event Log
One dated, sourced stream of what changed — the company's own events and the law
changes that move its obligations. Bitemporal: `at` (when it took effect) versus
`known_at` (when we learned it).

- **Status:** BUILT (v0). `event_log.py` + three read routes.
- **Missing:** the timeline UI; company-fact events, which need licensed registry
  data and are v1.

### F5 · Law-change Monitor
A Gazette instrument lands → these obligations move → these companies. Alerts that
are dated and sourced, never a bare reminder.

- **Status:** ENGINE BUILT — `affected_by()` is the reverse index.
- **Missing:** subscriptions and delivery.

### F6 · Point-in-Time Answer
"What did this provision say on 15 March 2019?" — the version in force on a past
date, for a transaction or filing under review.

- **Status:** MACHINERY BUILT. `as_of.py`, amendment lineage, versioned corpus.
- **Missing:** corpus depth. Each acquired instrument extends the answerable range.
- **Why it matters:** static RAG retrieves the date-applicable version **0% of the
  time** (arXiv:2608.09393). This is the capability nothing else on the Indian
  market sells.

### F7 · Staleness Audit
For every external instrument an answer depends on: what is its acquisition state,
and would a successor have anywhere to be recorded?

- **Status:** BUILT. `staleness.py`.
- **Missing:** nothing technical — it is currently internal, and is arguably a
  customer-facing feature in its own right.
- **Provenance:** written after this engine served a superseded threshold as
  CURRENT for nine months. It immediately found three more instances.

---

## Phase 3 — the platform

### F8 · Bulk Document Review
Many documents in → key terms extracted into a table. **Ours refuses the cell it
could not read** rather than guessing at it.

- **Status:** NOT BUILT, and the riskiest item here.
- **Gated on:** OCR, and the 20-document test. On real scans the best engines
  reach chrF++ 86.3 and the worst 40.5 — and a study of real scanned Indian legal
  documents with stamps and handwriting concluded current systems lack the
  precision for legal-grade work.
- **The difference from Harvey's Vault:** Vault extracts and flags statistical
  outliers. Ours abstains on the cell it could not read, and says which page.

### F9 · Grounded Research Assistant
Ask a question → a cited answer, or an honest refusal. Never composes advice,
never invents a citation.

- **Status:** SAFETY SPINE BUILT — `model_adapter.py` (four refusals before any
  call), `cascade.py`, `claim_verifier.py`.
- **Missing:** `POST /v1/ask`, conversation state, and a model actually wired.
- **NON_GOAL boundary:** a *general* legal chatbot is barred. This is the
  constrained form — grounded or abstaining — and the constraint is the defence.

### F10 · Controlled Drafting
Every value in a draft is typed by where it came from: `TEMPLATE_TEXT` ·
`USER_FACT` · `SOURCE_QUOTE` · `DERIVED_FACT` · `MODEL_SUGGESTION` · `UNKNOWN`.
`approve()` **raises** on the last two — an unsourced draft cannot be approved.

- **Status:** BUILT. `drafting.py` + `provenance_slots.py`. One template (AGM
  notice), no model wired.
- **Missing:** more templates, the model wired into `MODEL_SUGGESTION` slots
  (still approval-blocked), and the provenance panel.
- **Sequencing:** add the second template only after a lawyer uses the first.
- **NON_GOAL boundary:** a free-text document generator is barred. We win on
  provenance, not prose.


### F11 · MCA Master Data Strip
Reconciles the document being drafted against the company's registry record —
capital headroom per class, encumbrance warranties against the index of charges,
and the status of a signatory's DIN — and states, for every figure, how far back a
lawful unfiled event could reach and in which direction.

- **Status:** **ENGINE BUILT, DATA NOT WIRED.** `checker/mca_snapshot.py` (blindness,
  8 windows quoted from the corpus), `checker/mca_reconcile.py` (three rules, and a
  constructor that refuses legal conclusions), `checker/buyer_sim.py` (ten buyer
  questions, `OVERCLAIMED: 0`). Analysis and simulation results:
  [PLAN_09](PLAN_09_MCA_MASTER_DATA_STRIP.md).
- **This does not reverse the retirement of the Verified Company Card below.** That
  row said the *data* sits behind a contract, and it still does —
  `corporate_data.LicensedAggregatorProvider` refuses, and there is no scraping path.
  What changed is that the engine, the refusals and the buyer simulation cost nothing
  to build and are now green, so the day a contract exists the feature is a wiring job.
- **Missing:** a contracted aggregator; the two delegated rules that would bound
  paid-up capital and DIN status. The simulation's one `GAP` — which company on a
  four-party SPA the bar is about — was closed by `checker/party_resolution.py`:
  a CIN is never a party, a role is, and each rule declares the role it needs.

---

## Cut, and why

| Cut | Reason |
|---|---|
| **Verified Company Card** | Was Phase 1. Cannot be built on free data — no director/DIN field, no s.77 charges, no s.164 join, and no vendor verifiable as an authorised MCA reseller. Moves behind a data contract |
| **Docket analytics** | NJDG bulk API is government-only, not licensable by a private company |
| **Clause benchmarking** | Impossible in India. No filing mandate creates the corpus — SEBI LODR requires "significant terms **(in brief)**", never the instrument |
| **Five-agent orchestration plane** | Deferred until real query volume exists. See [PLAN_01](PLAN_01_ARCHITECTURE.md) for what replaced it |
| **Spatial / "God's Eye" engine** | A WebGL client and a proxy. Touches no statute text, no entity resolution, no provenance. The telemetry that matters here is Gazette amendments — which is F4 |
| **General chatbot · free-text generator** | `NON_GOALS.md`. F9 and F10 are the permitted forms |

---

## The honest summary

**Eight of eleven have a built engine.** What is missing is mostly *surface* — UI,
endpoints, model wiring — not core logic.

**F1 has shipped its surface**: the Word add-in exists, loads, and answers through
a real check (`addin/`, commit `a04a60d`). This summary said "specced but not
started" for a day after it was built — the second time this file has lagged the
code, which is why the status line of every feature above now names a file or a
commit rather than a mood.

Two real exceptions remain: **F8 is genuinely unbuilt and genuinely risky**, and
**F11's engine is green but has no data behind it** and will not until an
aggregator contract exists.

And one thing gates the demo quality of F1, F2 and F3 at once: **four obligations
refuse** because their delegated rules are unheld. Clearing those takes the matrix
from 11 answerable rows to 15, and it is a day of human work, not engineering.
