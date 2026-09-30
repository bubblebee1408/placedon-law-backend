# 03: The architecture — seven planes over the four rings

## 1. The shape in one picture

The rings are unchanged. `checker/rings.py` enforces them [R], and nothing in this plan
weakens it:

- **Ring 0** Law: what the law requires. Deterministic.
- **Ring 1** Company facts: the tenant's entities, documents and matters.
- **Ring 2** Live signals: feeds and news. Never authority.
- **Ring 3** Statistics and predictions. Never authority.

The **planes** are the new idea. A plane is a job the system does. A plane can span rings, but
its outputs stay in the ring they belong to.

```
                    ┌──────────────────────────────────────────────────────────────┐
  lawyer / agent ──►│ P7 GOVERN  tenancy · RLS · markings · audit · DPDP · hosts   │  gateway/ [R:H]
                    ├──────────────────────────────────────────────────────────────┤
                    │ P5 ORCHESTRATE  PLAN_23's 12 layers: gate → intent → plan    │
                    │   compiler → saga executor → router → L0 verify → critic →   │
                    │   synthesis → human gate → record → recall                   │  agents/ [R:H]
                    ├───────────────┬───────────────┬──────────────┬───────────────┤
                    │ P1 SENSE      │ P2 UNDERSTAND │ P3 DECIDE    │ P4 ANALYSE    │
                    │ documents     │ extract into  │ Ring 0       │ Ring 3        │
                    │ feeds         │ the ontology; │ deciders,    │ statistics,   │
                    │ audio (later) │ model PROPOSES│ currency,    │ survival,     │
                    │ papers        │ code ADMITS   │ citator      │ (forecast:    │
                    │               │               │              │  gated)       │
                    ├───────────────┴───────────────┴──────────────┴───────────────┤
                    │ ONTOLOGY + OBSERVATION STORE (bitemporal, append-only)       │  observation_store [R:H]
                    ├──────────────────────────────────────────────────────────────┤
                    │ P6 LEARN  decisions → labels → eval sets → candidate →       │
                    │   frozen-split test → human promotion → versioned behaviour  │  NEW (05)
                    └──────────────────────────────────────────────────────────────┘
```

**The rule that binds every plane** is PLAN_22's, unchanged: *a model may read, extract,
label and phrase. A model may never decide a legal status, choose an authority, or supply a
date.* This plan adds one clause: **a model may never promote its own change.**

## 2. The ontology: what Themis knows, as typed objects

This extends PLAN_19 03 §2 (G1.1, `checker/ontology.py`, not yet built). Every property is
stored as an `Observation` carrying:

- `value`;
- `source` (URL + sha256, or a tenant document id + span);
- `valid_at` (when it was true in the world);
- `known_at` (when we learned it);
- `evidence` (the G0.5 order);
- `marking` (tenant, matter, privilege).

| Object | Key | Ring | Example properties | Comes from |
|---|---|---|---|---|
| `Instrument` | instrument id (`legal_ref.py`) | 0 | title, number, gazette date, commencement | eGazette, India Code |
| `Provision` | (instrument, number) | 0 | text as of date, amendment chain | corpus |
| `Obligation` | rule id | 0 | applicability predicate, deadline rule, `blocked_by` | `obligations.py` |
| `Company` | CIN | 1 | class, paid-up capital, turnover, listed | tenant upload, MCA master data |
| `Person` | DIN / PAN (hashed) | 1 | roles, appointments | tenant, MCA master data |
| `Document` | tenant doc id | 1 | type, date, parties, clauses, signed? | vault upload |
| `Matter` | tenant matter id | 1 | members (ethical wall), documents, positions | tenant |
| `Position` | position id | 1 | question, answer, `as_of`, the law versions used, reviewer, decision | `runs.approve` [R:H] |
| `Judgment` | neutral citation / diary no. | 2 | court, bench (size only by default), date, statutes cited, citations | AWS SC/HC (after counsel) |
| `Citation` | (citing, cited) | 2 | treatment: followed / distinguished / overruled; label source | extraction + HUMAN label |
| `ForumCase` | forum + case no. | 2 | filing date, stage dates, disposal date or *pending*, case type, provisions | NCLT pages (access OPEN) |
| `Event` | event id | 2 | Gazette notification, IBBI order, SEBI order | feeds [R] |
| `Operation` | op id | — | tasks, evidence budget | `operations.py` [R] |
| `Estimate` | estimate id | 3 | statistic, n, interval, method, data cutoff, what it is **not** | P4 |
| `PaperCard` | DOI / arXiv id | — | claim, venue, n, metric, tag [V]/[S], the rule it forces | research registry |

**Links** are typed and come from `entity_graph.Rel` [R]. They include:

- `Company —director→ Person`
- `Position —relied_on→ Provision@version`
- `Judgment —cites→ Judgment`
- `Event —amends→ Provision`
- `Obligation —applies_to→ Company`

**Actions.** Every change to an object is an action. Palantir's documentation calls these
"action types" (02 §6). Each action has an actor, a reason, a compensation (PLAN_23 §1.9),
and an audit row.

## 3. The planes, one by one

### 3.1 P1 Sense: hears and reads

| Input | Path | Status |
|---|---|---|
| Tenant documents | `documents.upload` → vault → OCR if scanned (D5: Sarvam vs Azure, decided by measurement) | upload verb exists [R:H]; OCR choice OPEN |
| Law changes | eGazette watcher → `Event` | built [R] |
| Counterparty status | IBBI, OFAC; next SEBI debarred, data.gov.in MCA master data | built / G3 |
| Case law | AWS SC/HC judgments → `Judgment` | T5, after counsel |
| Forum dockets | NCLT orders/cause lists → `ForumCase` | T6, after access is lawful |
| **Audio ("hears")** | Tenant-uploaded board-meeting recording → ASR (Azure Speech, per D3) → transcript with timestamps → the SS-1 minutes checker compares minutes with what was said | **T8, optional.** Word error rate is measured on 10 real Indian-English recordings first. Transcripts are untrusted text (`prompt_safety`) |
| Research papers | PDF / publisher page → `PaperCard` | T2 |

**The one rule of P1.** Everything sensed becomes an `Observation` with provenance, or it does
not enter. No sensor writes to a decision.

### 3.2 P2 Understand: extraction into the ontology

- **A model proposes** typed values with spans: clause boundaries, parties, dates, citation
  treatments, case types. `checker/clauses.py` splits contracts by code [R:H].
- **Code admits** a value only if its span is byte-identical in the source
  (`quoted_span.py` [R:H]). Types must check, and the value must fit its domain (a date parses;
  a CIN matches its pattern).
- Unadmitted proposals are kept with the label `PROPOSED`. They are shown greyed as
  `SIGNAL`, never as fact.
- Entity resolution follows Fellegi–Sunter (S7), with thresholds: auto-link only on an exact
  identifier (CIN/DIN), review between thresholds, reject below.

### 3.3 P3 Decide: Ring 0, deterministic

- Existing: obligations and the s.185/186/188 deciders, `as_of`, `currency`,
  `affected_by()`, the scope gate, admission.
- New, on the same pattern:
  - **Citator** (PLAN_19 G5). "Is this judgment still good law?" is answered over the
    citation graph, using human-labelled treatments only.
  - **Compliance calendar** (PLAN_20 row 6). Deadlines are computed from rules
    ("within 30 days of the AGM"), not stored.
- **Scenario simulation (the "what if").** Re-run the deciders on changed facts: "if turnover
  crosses ₹X on 31 March, which obligations switch on, and from when?" This is deterministic.
  It is Ring 0 applied to hypothetical Ring 1 facts, marked `HYPOTHETICAL` end to end.
  **This is the simulation a lawyer can rely on**, because it is the law applied, not a model
  guessing.

### 3.4 P4 Analyse: Ring 3 statistics

Detailed in [04](04_ANALYTICS_AND_PREDICTION.md). Its outputs are always `Estimate` objects in
output class `predictive_signal`:

- **Descriptive:** counts and proportions with Wilson intervals.
- **Time-to-event:** Kaplan–Meier with censoring.
- **Partially pooled rates:** hierarchical Beta-Binomial.
- **Forecasts:** only if the pre-registered gate in 04 §5 is passed.

`rings.py` already forbids any Ring 0 module from importing Ring 3. The analytics plane is
registered as Ring 3 on day one.

### 3.5 P5 Orchestrate: PLAN_23, extended

PLAN_23's rules stand: code owns plans and hand-offs, retries only narrow, and escalation
happens on verifier rejection only. This plan adds **intents**. Each intent has one reasoning
type and one eval set (PLAN_23 §1.10).

| Intent | Reasoning type | Plane | Output class | Eval set |
|---|---|---|---|---|
| `ask` (exists) | statutory QA | P3 | verified_fact / abstained | gold set |
| `review_document`, `review_contract` (exist) | document vs rule / playbook | P2+P3 | deterministic_conclusion | NDA fixtures, SS specimens |
| **`authority_check`** | citator lookup | P3 | deterministic_conclusion | human-labelled treatments |
| **`scenario`** | deciders on hypothetical facts | P3 | deterministic_conclusion, `HYPOTHETICAL` | differential test vs the compliance pack |
| **`forum_statistics`** | descriptive / survival estimate | P4 | predictive_signal | recomputation test + interval coverage on held-out periods |
| **`recall`** | reverse provenance: positions that relied on X | P3 over P6 memory | deterministic_conclusion | replay of G.S.R. 880(E) |
| **`watch.subscribe` / `watch.alerts`** | event → affected positions | P1+P3 | operation (not a finding) | incremental = full recompute |
| **`paper_card`** | extract a paper's claims | P2 | SIGNAL until a person admits it | human check of 20 cards |

All new intents enter through the **verb table** (PLAN_22 D6). The REST, MCP and CLI surfaces
are generated from it, and a parity test fails if one drifts. MCP stays read-only
(`checker/mcp/policy.py` [R]). `scenario` and `forum_statistics` are reads; `watch.subscribe`
is a write, exposed only through the gateway with token identity.

**How one request flows.** An in-house counsel asks: *"We plan a scheme of amalgamation of two
subsidiaries. What do we have to do, and how long does NCLT usually take?"*

1. **Gate + intent.** The compiler splits the question into two intents at most (PLAN_23 mode
   c, ≤ 4 sub-questions): `ask` (ss.230–232) and `forum_statistics` (scheme sanction time).
2. **`ask`** runs the existing path. It checks scope (the Companies Act is held), retrieves
   as of today, decides, narrates with a quote per clause, and verifies with L0.
3. **`forum_statistics`** runs P4. It finds the stratum *(NCLT, bench, s.230–232 schemes)*,
   pulls the Kaplan–Meier estimate with n and interval, and states its data cutoff.
4. **Synthesis** keeps the two apart on screen. The law is shown as law, with quotes. The
   statistic is shown as a statistic ("median 7.2 months, n = 143, 95% CI 6.1–8.5, data to
   31-08-2026; this is not a prediction for your scheme"). *The numbers are illustrative of
   the format only; none has been measured.*
5. **Record.** The run is stored with the law versions used and the dataset version of the
   estimate. When either changes, `recall` finds this position.
6. **Human gate.** Counsel approves or rejects. That decision becomes a label (05 §2).

### 3.6 P6 Learn: the research registry and the learning loop

- **Research registry** (closes master-plan §105 criterion 18). A `PaperCard` holds:
  - the claim, venue and year;
  - the dataset and its n, and the metric;
  - the evidence tag;
  - the task type per 02 P2 (identification / categorisation / forecasting);
  - the rule it forces in this repo.

  A model drafts the card from the paper. A person admits it. `docs/plan24/02_EVIDENCE.md`
  is its first manual instance.
- **Learning loop.** See [05](05_LEARNING_AND_ADAPTATION.md). This is the "adapts, updates"
  the founder asked for.

### 3.7 P7 Govern

This exists on the newest branch [R:H]:

- tenants, with FORCE row-level security proved on Postgres;
- hashed API keys;
- a metadata-only audit row per call;
- host policy (`public_only.py`: nothing unpublished reaches a free tier).

It adds:

- **markings** on every observation (tenant, matter, privilege), joined upward. A derived
  object carries the most restrictive marking of its inputs (PLAN_19 01);
- **the audit anchor** (R-015);
- **DPDP purpose records** (05 §6).

## 4. What is Placedon's, and what is the tenant's

| Layer | Owner | Shared across tenants? | Learns from |
|---|---|---|---|
| Law corpus, citator, currency, calendar rules | Placedon | Yes (public law) | Law changes; human legal verification |
| Public forum statistics | Placedon | Yes (public records) | New public records |
| Global eval sets and promotion gates | Placedon | Yes | Placedon's own reviewers; tenant cases only if **opted in** per matter (PLAN_21 decision 3) |
| Tenant vault, ontology instance, playbook, positions, precedent memory | Tenant | **Never** | That tenant's uploads and decisions |
| Tenant-specific ranking / thresholds (05 §3) | Tenant | **Never** | That tenant's labels |

"Trained on the company's data plus Placedon's data", precisely:

- **The company's layer adapts to its own decisions.**
- **Placedon's layer adapts to the law and to Placedon's reviewers.**
- The two meet at query time, through retrieval and the orchestrator.
- They never meet inside a set of weights.
