# `/v1/ask` response contract — `placedon.ask/0`

Written 2026-09-15 (runbook task UX-C). **The route exists** as of 2026-09-18 (ASK-1):
`POST /v1/ask` in `checker/api.py`, answered by `checker/ask.py::answer()` from deterministic
engine calls alone — no model is called on any path and `uses_model` is always `false`. The
prototype is still static: it renders fixtures and sends nothing. Every fixture is now a REQUEST
put through the same `answer()`, so the prototype and the route cannot drift.
Validator and fixture builder: `scripts/assistant_contract.py`.
Plan: [`docs/PLAN_13_ASSISTANT_UX_PLAN.md`](../../docs/PLAN_13_ASSISTANT_UX_PLAN.md). Evidence:
[`docs/research/ux/INTERNAL_ASK_AUDIT.md`](../../docs/research/ux/INTERNAL_ASK_AUDIT.md) (§R2 is the
draft this corrects).

Every field below names the engine code that produces it, or is marked **NEW** (no module produces it
today).

---

## 1. Rendering rules the client must obey

1. **Render `state`; never infer it.** A response without one of the three states is not rendered
   as an answer (C3).
2. **No text the response did not supply.** Captions, headlines, figures, reviewers and scope lines come
   from fields, never from client copy that implies a result.
3. **Stages are shown only if `stages` is present** — and it is present only on the document path.
   No client-timed "thinking…" sequence (K9).
4. **Two as-of truths never look alike.** A `figures[]` item carries an instrument and an in-force date.
   Section text carries `law_version` — *current consolidation as ingested*, not point-in-time.
5. **No confidence, anywhere.** There is no field to render (C4).

## 2. Envelope (every state)

| Field | Type | Source |
|---|---|---|
| `schema` | `"placedon.ask/0"` | NEW |
| `state` | `answered` \| `partial` \| `out_of_scope` | `ask.answer` — server-side mapping (§6) |
| `turn_id` | string | `ask._turn_id` — sha256 of question, as_of, kind and document date, first 12 hex. No clock and no randomness, so a rebuilt fixture and a live turn share an id; there is still no conversation state (FEATURES.md:120) |
| `parent_turn_id` | string, follow-ups only | NEW |
| `question` | string — the user's words | request |
| `generated_at` | ISO timestamp | `checker/api.py` pattern |
| `as_of` | ISO date — the read date | `checker/api.py` pattern |
| `context` | `{kind: document \| general, document_date}` | `kind` NEW; `document_date` from the document path (`orchestrator.run`, `api.document_check`) |
| `uses_model` | bool | `bundles.dispatch` / `api.document_check` (`no_model`) |
| `scope` | `{held: [names], sentence}` | `scope.in_corpus()`, `scope.coverage()` |
| `stages` | `[{n, what, detail}]`, **document path only** | `orchestrator.Step`; `what` ∈ capability, date, model, review, correction, abstain |

## 3. `answered`

Truthful today **only from a deterministic path** — an obligation row or a servable prescribed
threshold. A model-composed statement cannot reach it: `claim_verifier` never returns `SUPPORTED`.

| Field | Source |
|---|---|
| `facts` `{name: {value, provenance: USER_FACT}}` | request (the facts the user supplied) |
| `rows[]` | `api._row_json` — obligation_id, duty, provision, state, basis, missing_facts, blocked_by, cited_spans |
| `figures[]` `{key, amount, rupees, instrument, effective_from, effective_to, evidence_state, source_url}` | `prescribed_thresholds.lookup` |
| `citations[]` `{ref, cite, title, evidence_state, usable_for_answering, unusable_reason, defects, retrieved_on[], source_url}` | `evidence_pack` provision `to_dict` (`sources[].retrieved_on` — K10) |
| `law_version` `{basis, point_in_time_verified, corpus_fetched, statement}` | `evidence_pack.AsOf.to_dict` |
| `evidence_pack` `{retrieval_query, route, usable_keys, unusable_keys, missing, insufficient_evidence}` | `retrieve.retrieve` + pack `to_dict` (`query` — K10) |
| `what_it_is_not[]` | `api.compliance_pack` |

Subsection text (e.g. the words of s.2(85)(i)) is **NEW**: retrieval resolves a subsection to its
section and records the subsection without extracting it.

## 4. `partial`

| Field | Source |
|---|---|
| `confirmed[]` | usable provisions (citation fields + `verbatim` = `reading_text`), or verified document-check rows |
| `not_confirmed[]` `{kind, …}` — `pack_missing` · `unusable` · `cannot_verify` · (future) `refusal`, `model_decision` | pack `missing[]`, `unusable_reason()`, `api.document_check` `cannot_verify[]`, `reasoning.Refusal`, `model_adapter` decisions |
| `superseded[]` (document path) | `api.document_check` |
| `scope_frame` (document path) | `coverage.Report.to_json()` — renamed from `coverage` (K8) |
| `law_version`, `evidence_pack` | as in §3. **On a document turn `law_version` is required** and carries `point_in_time_requested` = the document date, built by `evidence_pack._build_as_of`: `document_check` reports Act-only rows CURRENT by construction against the current consolidation, and this is what stops that reading as the law at the document's date (red team L2) |
| `demand_signal` | NEW (UX spec §3.2) |

## 5. `out_of_scope`

| Field | Source |
|---|---|
| `body` `{key, name, regulator, covers, scope_status}` | `scope.body(key)`; detection: `ask._body_named` (§6 D2) |
| `reason` | `scope.refusal_for(key)` verbatim |
| `held[]` | `scope.in_corpus()` |

A body the register does not declare (e.g. the Income-tax Act) has no `refusal_for` text; its `reason`
would be NEW copy and needs its own decision. **Still open after ASK-1**: such a question is *not*
out_of_scope. It falls to the general path and comes back `partial` — nothing is invented, and
nothing useful is said either (PLAN_13 §7.12 calls `body.undeclared_reason` NEW and blocking).

## 6. State mapping — DECIDED 2026-09-18 when `/v1/ask` was built (ASK-1)

Implementation: `checker/ask.py`. Every decision below is a choice this build made; the table it
replaces was inferred. Where a case was **not** decided it says so rather than guessing.

### The request

```jsonc
POST /v1/ask
{ "question": "Is this company a small company?",   // rendered verbatim; NEVER parsed for meaning
  "as_of": "2026-09-15",                            // optional; defaults to the day in generated_at
  "context": { "kind": "general", "document_date": null },
  "facts": { … },                 // general: what /v1/compliance-pack takes
                                  // document: what /v1/document-check takes
  "provisions": ["s.2(85)"],      // citations to read
  "figures": ["small_company.turnover.prescribed"],   // prescribed-threshold keys
  "parent_turn_id": "t_20ccadb72b4b" }
```

**D1 — `provisions` and `figures` exist because the engine does not read the question.** A
deterministic engine cannot know which provision a sentence means, and guessing would put a
citation under words nobody asked us to interpret — the Act-versus-Rule collision `retrieve.py`
exists to prevent. So the caller (the capability row of PLAN_13 §4.1) names what it wants read, and
each name is checked against what the engine declares: an undeclared figure key is a `400`, and an
unresolvable citation comes back as a pack miss, never as a near-miss. **Where the request names no
provision, the retrieval query is the user's own words** and `retrieve()` decides the route — which
is what the stamp line renders as "Looked up …", the only record of what was tried (PLAN_13 §7.12).
Anything the request does not name is not looked up; nothing is inferred from the sentence.

### The mapping

| Case | State | Decision |
|---|---|---|
| The question names a body `scope.py` declares and does not hold | `out_of_scope` | **D2.** Decided first, before any retrieval, and it wins even when the question also names law we hold — answering the LLP limb from Companies Act reasoning is the error `scope.py`'s own LLP note names. Detection (`ask._body_named`) uses **only the register's own strings**: multi-word phrases from `name` and `covers`, plus each named regulator, matched whole-phrase and case-insensitively. Single common words are excluded by construction — STAMP `covers` "debentures" and "agreements", and matching either would refuse a Companies Act question as a stamp-duty one. Several matches → the first in register order (so a SEBI question refuses as LODR, the held-as-consolidation body, before SEBI_OTHER). **No match → not `out_of_scope`** (see §5). |
| A decided obligation row, or a servable prescribed figure, **and** nothing not confirmed | `answered` | **D3.** "Decided" excludes any row carrying `missing_facts`, a `blocked_by`, or state `APPLIES_UNDETERMINED` / `CANNOT_DETERMINE`: those move to `not_confirmed` (kind `cannot_verify`) and are not served as rows. An `answered` turn renders `citations[]`; a `partial` renders the same provisions as `confirmed[]` with their `verbatim`. |
| Anything else on the general path | `partial` | **D4.** Including a pack miss, an unusable provision, an unservable figure, and an undecided row. A `partial` is **never empty-handed**: where a turn reached nothing at all, one `cannot_verify` item says so in the engine's words (`ask.NOTHING_DECIDED`) — "we decided nothing" is not "nothing applies". |
| A prescribed figure the table will not serve | `partial`, figure absent | **D5.** The `ThresholdUnavailable` message is carried verbatim as the item's `detail`. The statutory floor is never substituted (`prescribed_thresholds.operative_small_company_limits` says why: ₹50 lakh against ₹4 crore is a wrong answer in the costume of a cautious one). |
| Which rows a turn serves | — | **D6.** The rows whose `provision` names one of the request's `provisions`; where the request names none, every row the pack returned. A provision number is never a prefix (s.16 does not match s.186). |
| Document turn, `cannot_verify` non-empty | `partial` | **D7.** `confirmed` = the verified rows, `not_confirmed` = `cannot_verify`, `superseded` and `scope_frame` as in §4. |
| Document turn, nothing flagged, something verified | `answered` | **D8.** The verified rows ride as `rows[]`. Unreachable with the register as it stands (every document check so far leaves something unverifiable), so it is exercised on the pure assembler `_document_turn`, not left undefined. |
| Document turn, nothing flagged, nothing verified, something superseded | `partial` | **D9.** One `cannot_verify` item per superseded row, from the row's own fields. |
| Document turn that reached no obligation | `partial` | **D10.** One item, `ask.NOTHING_REACHED`. |
| Any document turn | — | **D11.** No `evidence_pack`: the document path runs no retrieval. `law_version` is built at the **document's own date** (`_law_version_at`, red team L2). No `facts` block: the document's particulars are the check's own inputs and every row carries them. No `stages`: the orchestrator is the model path and this route never enters it, so no turn this route serves carries stages. |
| `BUDGET_EXHAUSTED`, a transport failure, an engine failure | **no state at all** | **D12.** `answer()` raises `BadRequest` for a malformed request (the route returns `400`) and lets **everything else propagate**. An engine failure must never reach a client wearing a legal state (CLAUDE.md; the frontend's `AGENTS.md:62`), so there is no `except Exception` on this path and a test asserts the route does not turn one into a `200`. |
| Every state | `uses_model: false` | **D13.** No model is called on any path, and the suite asserts the module imports no model or network library. |

**D14 — which supplied facts the response names back.** `facts` echoes the request's facts
**verbatim**, labelled `USER_FACT`, minus `as_of`, `incorporation_date` and `financial_year` — the
three fields `_profile()` needs to place the company in time, which the envelope's `as_of` and each
row's own financial year already carry. Nothing is derived, defaulted or added; a fact that was not
supplied leaves the row undecided rather than being invented. *Partly open*: on an AGM-timing turn
`incorporation_date` is substantive rather than frame, and naming it there was not decided here.

**D15 — `demand_signal`.** Emitted (`{"action": "tell_us_blocking"}`) on a **general** `partial`
that both confirmed something and could not confirm something else. **Not decided:** whether it
also belongs on the empty-`confirmed` partial, on a document partial, or on `out_of_scope` — the
UX spec shows the button in all three (§7.12, §7.11) but conditions it on the server supplying the
field, and widening it changes a fixture the prototype is accepted against. Left to ASK-3/ASK-5 with
the founder rather than guessed here.

**Still `NEW` after ASK-1, unchanged:** the `located` sentence for the empty-`confirmed` partial;
`body.undeclared_reason` for a body the register does not declare (§5); the provenance stamp and
`not_confirmed[].ref` (§9, ASK-2); `uses_model` vs `no_model` (§9.2 — a founder/frontend decision,
deliberately not renamed here); subsection text (§3).

## 7. What the validator refuses

A missing or fourth state · a figure without `amount`, `instrument` or `effective_from` · a citation
outside the evidence pack · `answered` citing an unusable provision · any `confidence` or `coverage`
key at any depth · `answered` with `uses_model` true · `partial` with empty `not_confirmed` ·
`out_of_scope` about a held body or without a reason · a turn that renders rows, confirmed items, superseded items or citations without `law_version` · `stages` on a general turn, or a stage name the
orchestrator does not emit · a document turn without `document_date` · section text (citation or
confirmed item) carrying `effective_from` · a follow-up with an empty `parent_turn_id`.

## 8. Fixtures

`web/assistant/fixtures/*.json`, **built by putting a request through `checker.ask.answer()`** — the
function the route calls — at a fixed `as_of` (2026-09-15). The requests are in
`scripts/assistant_contract.py::REQUESTS`; the engine calls behind each are:

| Fixture | State | Built from |
|---|---|---|
| `answered_small_company` | answered | `api.compliance_pack` (paid-up ₹12 cr, turnover ₹80 cr) → `CA13-S2-85-SMALL`; `prescribed_thresholds.lookup`; `retrieve("s.2(85)")` |
| `partial_s173_s16` | partial | `retrieve("s.173 and s.16")` — s.173 usable, s.16 not admitted |
| `out_of_scope_fema` | out_of_scope | `scope.body("FEMA1999")`, `scope.refusal_for` |
| `document_context_2024` | partial | `api.document_check` for a document dated 2024-06-01 |
| `followup_turnover` | answered | `prescribed_thresholds.lookup` turnover; `retrieve("s.2(85)")`; parent = the answered turn |
| `partial_nothing_confirmed` | partial, empty `confirmed` | `retrieve("rule 2(1)(t)")` — route `abstain`, empty pack; the state the design says will dominate (red team L3) |

The user's *questions* are illustrative; what each turn reads is named by its request (§6 D1).
Everything legal in a fixture is engine output, and nothing is assembled in the builder. The
self-test requires the files on disk to equal a fresh rebuild, so a change to the engine **or to the
mapping** surfaces as a fixture diff rather than as a prototype rendering a shape no caller can
obtain; after either, run `python3 scripts/assistant_contract.py --write`. (ASK-1 changed neither:
all six fixtures rebuilt byte-identically through `answer()`.)

## 9. Open questions from the finalized frontend (2026-09-17)

`placedon-claude-legal-3300` renders engine output through a typed client (`src/lib/engine/types.ts`).
Before `/v1/ask` is built, these need an answer so that the site can render `placedon.ask/0` without
inventing anything. Source: `docs/research/ux/FRONTEND_ALIGNMENT_2026_09_17.md` §F6.

1. **Provenance stamp.** The site shows `corpus_version`, `benchmark_version` and `checker_commit`
   (`types.ts:183-192`); this envelope carries none of them.
2. **`uses_model` or `no_model`.** The site's types use `no_model`; this contract uses `uses_model`. One name.
3. **Class mapping.** The site's classes are `verified_fact | deterministic_conclusion | predictive_signal`
   plus `abstained`. `CORROBORATED` must not render as "Verified fact": its own docs say nothing reaches
   VERIFIED without human review. `out_of_scope` has no class there and needs one ("Not held").
4. **`not_confirmed[]` identifiers.** `pack_missing` items carry only `kind` and `detail`. The key the
   detail names should be its own `ref` field, so the site's citation chip can render without parsing
   prose (the prototype parses it today, `app.js readerDetail`).
5. **Not the claims schema.** The site's `RAG-INTEGRATION.md:327` expects `/v1/ask` to follow the
   model-adapter `claims[]` schema. It will not; this contract is the shape. That document is stale.
