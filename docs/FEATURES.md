# The features — the canonical list

**This document supersedes every earlier feature and roadmap document in this
repository.** Those were deleted rather than left to rot; the tombstone list is in
[PLAN_00_INDEX](PLAN_00_INDEX.md). If a feature is not here, it is not planned.

Ten features, three phases. Each one names what it does, what exists today, and
what is missing — because "planned" and "built" are different words and this
repository does not blur them.

---

## Phase 1 — the wedge

### F1 · Document Currency Check *(the Word add-in)*
Audits the document open in front of the lawyer against the law in force **on that
document's date** — flags superseded figures, names the instrument that moved
them, and refuses what it cannot verify.

- **Status:** SPECCED, not built. Full spec in [PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md).
- **Reuses:** `obligations` · `as_of` · `currency` · `staleness` · `api.handle`
- **Missing:** the Office.js task pane, one API route.
- **Why first:** it needs no MCA data, no Gazette feed, no OCR, and no citator —
  every blocker the research found applies to other products, not this one.

### F2 · Compliance Matrix
Company facts → 15 obligation rows, each saying whether the duty attaches, whether
it looks met, or what is missing. Rows come from the law, so a company that has
uploaded nothing still gets a full matrix.

- **Status:** BUILT. `obligations.py` (1,448 lines), live at `POST /v1/compliance-pack`,
  HTML via `matrix_view.py`.
- **Missing:** a facts-in form a non-engineer would use.
- **Caveat that matters:** 4 of 15 rows currently refuse — s.2(85), s.177, s.188,
  s.203 — because the delegated rules behind them are unheld or unreviewed.

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

**Seven of ten have a built engine.** What is missing is mostly *surface* — UI,
endpoints, model wiring — not core logic.

Two real exceptions: **F8 is genuinely unbuilt and genuinely risky**, and **F1 —
the one to ship first — is specced but not started.**

And one thing gates the demo quality of F1, F2 and F3 at once: **four obligations
refuse** because their delegated rules are unheld. Clearing those takes the matrix
from 11 answerable rows to 15, and it is a day of human work, not engineering.
