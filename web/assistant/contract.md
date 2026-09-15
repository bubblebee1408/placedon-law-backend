# `/v1/ask` response contract — `placedon.ask/0`

Written 2026-09-15 (runbook task UX-C). **The route does not exist yet** (`checker/api.py` has no
`/v1/ask`; FEATURES F9). This contract is what the Ask section prototype renders, and what the route
must return when it is built. Validator and fixture builder: `scripts/assistant_contract.py`.
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
| `state` | `answered` \| `partial` \| `out_of_scope` | NEW — server-side mapping (§6) |
| `turn_id` | string | NEW — no conversation state exists (FEATURES.md:120) |
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
| `law_version`, `evidence_pack` | as in §3 |
| `demand_signal` | NEW (UX spec §3.2) |

## 5. `out_of_scope`

| Field | Source |
|---|---|
| `body` `{key, name, regulator, covers, scope_status}` | `scope.body(key)`; **detecting the body from a question is NEW** |
| `reason` | `scope.refusal_for(key)` verbatim |
| `held[]` | `scope.in_corpus()` |

A body the register does not declare (e.g. the Income-tax Act) has no `refusal_for` text; its `reason`
would be NEW copy and needs its own decision.

## 6. State mapping — INFERRED, to be decided when `/v1/ask` is built

| Engine result | State |
|---|---|
| Question's body has status ≠ IN_CORPUS | `out_of_scope` |
| Deterministic row or servable threshold; pack has no unusable key the question named | `answered` |
| Usable **and** missing/unusable items; `SERVED*` with any claim below SUPPORTED; adapter `INSUFFICIENT_FACTS`; document check with `cannot_verify` | `partial` |
| `ABSTAINED`, `REFUSED_BEFORE_CALL`, `INSUFFICIENT_EVIDENCE`, route `abstain` inside CA2013 | `partial` with empty `confirmed` (audit U2 — open) |
| `BUDGET_EXHAUSTED` | not a legal state — a service error, never rendered as abstention |

## 7. What the validator refuses

A missing or fourth state · a figure without `amount`, `instrument` or `effective_from` · a citation
outside the evidence pack · `answered` citing an unusable provision · any `confidence` or `coverage`
key at any depth · `answered` with `uses_model` true · `partial` with empty `not_confirmed` ·
`out_of_scope` about a held body or without a reason · `stages` on a general turn, or a stage name the
orchestrator does not emit · a document turn without `document_date` · section text (citation or
confirmed item) carrying `effective_from` · a follow-up with an empty `parent_turn_id`.

## 8. Fixtures

`web/assistant/fixtures/*.json`, **built by calling the engine** at a fixed `as_of` (2026-09-15):

| Fixture | State | Built from |
|---|---|---|
| `answered_small_company` | answered | `api.compliance_pack` (paid-up ₹12 cr, turnover ₹80 cr) → `CA13-S2-85-SMALL`; `prescribed_thresholds.lookup`; `retrieve("s.2(85)")` |
| `partial_s173_s16` | partial | `retrieve("s.173 and s.16")` — s.173 usable, s.16 not admitted |
| `out_of_scope_fema` | out_of_scope | `scope.body("FEMA1999")`, `scope.refusal_for` |
| `document_context_2024` | partial | `api.document_check` for a document dated 2024-06-01 |
| `followup_turnover` | answered | `prescribed_thresholds.lookup` turnover; `retrieve("s.2(85)")`; parent = the answered turn |

The user's *questions* are illustrative. Everything legal in a fixture is engine output. The self-test
requires the files on disk to equal a fresh rebuild; after an engine change run
`python3 scripts/assistant_contract.py --write`.
