# Build plan — corrected against the measured state

**Written:** 27 Aug 2026. Supersedes the sequencing in `docs/MODEL_PLAN.md`
where the two differ.

## Working definition (adopted)

> Placedon is a verified legal-evidence operating system. It uses existing
> language models as reasoning components, but controls their inputs, tools,
> legal sources, temporal versions, outputs, citations, and review states. Its
> first product reconstructs and reviews Indian Companies Act compliance
> obligations with evidence a human professional can inspect and approve.

And the governing principle, unchanged:

> The model may propose. The system must verify. The reviewer decides.

## Three corrections to the proposed plan

### 1. The data model is already built

Every entity in the proposed schema exists in code today:

| Proposed | Exists as |
|---|---|
| Source / provenance | `checker/provenance.py`, `checker/admission.py` |
| Provision | `checker/provision_graph.py`, `checker/section_index.py` |
| Amendment event | `checker/amendment.py`, `checker/as_of.py` |
| Commencement | `checker/commencement.py` |
| Evidence item | `checker/evidence_pack.py` |
| Claim | `checker/claim_schema.py`, `checker/claim_verifier.py` |
| Review decision | `checker/review_queue.py`, `checker/reviews.py` |
| Permissions / matter | `checker/matter.py` |

Milestone A is therefore substantially complete. The work is not to build these
but to connect them into one path and measure it.

### 2. s.96 is the right slice, and it was blocked until today

The plan names s.96 for the first vertical slice and for Milestone B. Two days
ago that was not possible: s.96 carries one of the six genuinely unbalanced
spans, so its pre-13-June-2018 text could not be reconstructed.

It is possible now, and not by guessing. Act 1 of 2018 s.26 states the whole
substitution:

    In section 96, in sub-section (2), in the proviso, for the words
    "Provided that", the following shall be substituted, namely:—
    "Provided that annual general meeting of an unlisted company may be held at
    any place in India if consent is given in writing or by electronic mode by
    all the members in advance: Provided further that"

The replacement text ends at "Provided further that", which is where the span
ends — **stated by the instrument, not inferred from punctuation**. The
boundary is 178 characters, located in the India Code content, and S.O. 2422(E)
confirms section 26 commenced 13 June 2018.

So the witness method resolves the flagship section. That is the unblock for
Milestone B.

### 3. One claim vocabulary, not three

The plan proposes SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONTRADICTED
/ DERIVED / INDETERMINATE / PENDING_REVIEW. We already run two vocabularies:

- `checker/grounding_policy.py` — the state path
  CITATION_FOUND → SOURCE_ADMITTED → SOURCE_IN_FORCE → CLAIM_PARTIALLY_MATCHED
  → CLAIM_QUALIFIERS_CHECKED → CLAIM_ENTAILED → HUMAN_APPROVED
- benchmark labels — ENTAILED / NOT_ENTAILED / PENDING_REVIEW / INVALID_FIXTURE

Adding a third would mean three ways to say the same thing and no single
authority on what a status means. The states map: PARTIALLY_SUPPORTED is
CLAIM_PARTIALLY_MATCHED; DERIVED is the existing `DerivedDate` provenance slot;
CONTRADICTED and INDETERMINATE are genuinely missing and should be added to the
existing enum rather than a new one.

## Build order

### Step 1 — s.96 end to end (Milestone B)

    source → version → amendment → commencement → evidence → calculation → review

Concretely: given a company class, financial-year end, and (optionally) a prior
AGM date, return the AGM deadline **with** the provision as it stood on the
relevant date, the amendment history, the commencement instrument for each
change, the limb that binds, and the arithmetic — every element inspectable.

`checker/agm.py` already computes the three limbs. What is missing is binding
that computation to a *dated* reconstruction and emitting one evidence card.

**Done when:** a s.96 answer for a past date carries its reconstructed text, the
amending instrument, the commencement notification with its hash, and abstains
when any of those is missing.

### Step 2 — resolve the remaining unbalanced spans by witness

Five genuine unbalanced spans remain, plus five marker-absent. Apply the s.96
method: take the replacement text from the amending Act, locate its end in the
content, prove the boundary. Do not guess any that the instrument does not state.

**Done when:** each of the ten is EXACT with an instrument-stated boundary, or
recorded as unresolvable with the reason.

### Step 3 — the compliance pack

AGM · annual return · financial statements · board meetings · board report ·
auditor appointment · director interest · related-party transactions.

Each obligation is a deterministic rule over: company class, dates the company
chose, dates fixed by statute, and the provision as in force. The distinction
between company-chosen and statute-fixed dates is load-bearing — an engine that
treats an actual AGM date as if it were computable will be wrong for every
company that held its meeting late.

### Step 4 — model in shadow

The adapter exists (`checker/model_adapter.py`, shadow mode, fail-closed
parsing). Wire a live model to: extract facts from an uploaded document, spot
issues, and propose atomic claims. Every claim goes through the existing
verification path. Nothing the model produces is displayed as usable until the
evidence layer has passed it.

**Done when:** a model-proposed claim can reach CLAIM_ENTAILED, and an
unsupported one is refused, on a frozen fixture.

### Step 5 — the gold set

50-100 hand-labelled cases across: exact reconstruction, partial, conflicting
sources, missing facts, wrong date calculation, unsupported claim, prompt
injection, irrelevant retrieval. Human-labelled; a model may draft, never label.

## What we do not build

- No foundation-model training. Revisit only with a labelled set and a benchmark
  showing where existing models fail.
- No connectors (iManage, SharePoint, NetDocuments) before the evidence engine
  is measured. They are contracts and integrations, not differentiation.
- No second statute until the Companies Act pack is measured end to end.
- No proprietary-benchmark claim. We have 71 human-reviewed pairs from five
  provisions of one Act. That is a fixture, not a benchmark, and saying
  otherwise would be the exact overclaim this project exists to avoid.

## What must never be claimed

- "fiduciary-grade accuracy"
- "every output is grounded" — measured: E3 accepts 51% of unsupported claims
- that a citation existing proves the proposition
- that a valid signature proves a document was officially issued
