# Internal audit — what the Ask section can truthfully show today

Written 2026-09-15 for PLAN_13 Phase R. Read-only audit; no code changed.
This is the one research file allowed to cite local files instead of URLs. Paths are relative to
`placedon-law-backend/` unless prefixed `BP:` (= `Placedon-law-business-plan/`, a PUBLIC repo, read only).

Markers: **SOURCED** (file:line read) · **MEASURED** (ran the code on 2026-09-15, command stated) ·
**INFERRED** (my reasoning from sourced lines) · **UNVERIFIED**.

---

## Question

1. What can a `/v1/ask` response carry today, using only BUILT modules — states, citations, as-of,
   refusal reasons, evidence-pack ids, stages — and what is missing?
2. A draft JSON contract for `answered` / `partial` / `out_of_scope` using only those fields, with new
   fields marked.
3. Which design tokens are in use across `BP:docs/DESIGN_SYSTEM.md` and the Word task pane, and where
   they disagree.
4. Which capabilities the composer may truthfully suggest.
5. (Required by the brief) every place `BP:landing-page/ask.html` contradicts the two specs.

## Sources checked

`docs/PLAN_13_ASSISTANT_UX_PLAN.md` · `BP:docs/DESIGN_SYSTEM.md` · `BP:docs/UX_INTERACTION_SPEC.md` ·
`BP:landing-page/ask.html` · `addin/taskpane.html` · `addin/taskpane.js` · `checker/model_adapter.py` ·
`checker/cascade.py` · `checker/claim_verifier.py` · `checker/evidence_pack.py` ·
`checker/legal_retrieval.py` · `checker/scope.py` · `checker/bundles.py` · `checker/orchestrator.py` ·
`checker/session.py` · `checker/api.py`. Also read to settle field shapes: `checker/reasoning.py`
(Refusal/Review), `checker/retrieve.py` (routes), `checker/coverage.py` (frame JSON),
`checker/currency.py` (Finding), `checker/prescribed_thresholds.py` (Threshold), `checker/obligations.py`
(Row, states, duties), `checker/claim_schema.py`, `checker/ground_span.py`, `docs/FEATURES.md` F9.

Searches run: `grep -rn 'v1/ask'` over checker/ scripts/ addin/ web/ docs/ → only PLAN_13 and FEATURES.md
mention it; `grep` for `"answered"|"partial"|"out_of_scope"` in checker/ scripts/ → only scope-status
constants, no answer-state code; `grep` for importers of `checker.cascade` and `ground_span`.

MEASURED probe (read-only, `PYTHONPATH=. python3 -c …`): `prescribed_thresholds.held(...)` at
2026-09-15, `scope.coverage()`, `bundles.capabilities()`, `retrieve("s.2(85)")`, `retrieve("rule 2(1)(t)")`.

---

## Evidence found

| id | claim | marker | location |
|---|---|---|---|
| E1 | No `/v1/ask` route exists. Routes are health, compliance-pack, document-check, mca-strip, company events, instrument affected. | SOURCED | `checker/api.py:560-567`; `docs/FEATURES.md:120` |
| E2 | No module emits `answered`/`partial`/`out_of_scope`. The only `OUT_OF_SCOPE` constant is a *scope status of a body of law*, not an answer state. | SOURCED + grep | `checker/scope.py:38-41` |
| E3 | Orchestrator outcomes are `SERVED`, `SERVED_AFTER_CORRECTION`, `ABSTAINED`, `REFUSED_BEFORE_CALL`, plus the refusal code `DOCUMENT_DATE_CONFLICT`. | SOURCED | `checker/orchestrator.py:65-73` |
| E4 | `Outcome` carries `verdict`, `review`, `steps`, `corrections_used`, `abstained_on`; each `Step` is `{n, what, detail}`; `what` ∈ capability, date, model, review, correction, abstain. | SOURCED | `checker/orchestrator.py:80-101, 208-258` |
| E5 | The orchestrator refuses to run without a document date. | SOURCED | `checker/orchestrator.py:200-204` |
| E6 | Review refusals are `{violation, detail, offending}`; violations: INTENT_NOT_DECLARED, FACT_WITHOUT_SPAN, FACT_NOT_GROUNDED, FACT_VALUE_UNSUPPORTED, FACT_MISBOUND, DATE_INVENTED, FIGURE_INVENTED, CITATION_OUTSIDE_PACK, CONCLUSION_ASSERTED. | SOURCED | `checker/reasoning.py:54-82` |
| E7 | Model-adapter decisions: APPLIES, DOES_NOT_APPLY, INSUFFICIENT_FACTS, INSUFFICIENT_EVIDENCE. `BUDGET_EXHAUSTED` exists but is not a model decision. Warning codes: NO_ADMISSIBLE_EVIDENCE, MODEL_OUTPUT_PARSE_FAILURE, DECISION_DOWNGRADED, DECISION_WITHOUT_CLAIMS, DUPLICATE_CLAIM_ID. | SOURCED | `checker/model_adapter.py:54-71` |
| E8 | `ModelResult.to_dict()` = decision, claims, missing_facts, warnings, model_name, prompt_version, rejected_claims. | SOURCED | `checker/model_adapter.py:131-146` |
| E9 | The adapter refuses before any call: a REVIEW pack, an empty pack (→ INSUFFICIENT_EVIDENCE, no call), no budget, and a citation outside the pack. | SOURCED | `checker/model_adapter.py:8-19, 284-297, 304-324, 249-253` |
| E10 | `Claim` = claim_id, text, claim_type, evidence_ids, support, confidence (HIGH/MEDIUM/LOW). | SOURCED | `checker/claim_schema.py:25-35, 54-60` |
| E11 | The claim verifier's top verdict is `LEXICAL_CANDIDATE`. It never returns `SUPPORTED`, and `establishes_support()` is True only for SUPPORTED. | SOURCED | `checker/claim_verifier.py:22-31, 52-74` |
| E12 | `ClaimVerification` = claim_id, verdict, issues, supporting_evidence_ids, coverage (a float). | SOURCED | `checker/claim_verifier.py:88-99` |
| E13 | The cascade returns True/False/None with `decided_by` and steps. Its runtime importers are `ground_span.py` (ESTABLISHED/NOT_ESTABLISHED) and `retrieval_eval.py`. Neither `claim_verifier`, `model_adapter`, `reasoning` nor `orchestrator` imports it. (check 2026-09-15: cascade.py:54-106 and ground_span.py:27 `from checker.cascade import verdict` match; claim_verifier/model_adapter/reasoning/orchestrator contain no "cascade" at all; but `checker/retrieval_eval.py` never mentions cascade — the other importer is `checker/metric_policy.py:189,255`, inside its gate/test code, not a runtime path) | UNVERIFIED | `checker/cascade.py:54-106`; `checker/ground_span.py:1-14, 27`; `checker/claim_verifier.py:42-46` |
| E14 | Evidence-pack JSON: schema `placedon.evidence_pack/1`, query, as_of, identity_note, insufficient_evidence, provision_keys, usable_keys, unusable_keys, mode, provisions, missing. | SOURCED | `checker/evidence_pack.py:491-504` |
| E15 | Each provision carries: a qualified key (`ref`), cite, title, corpus_record_id, content sha256, raw_text, reading_text, derivations, evidence_state, sources[], defects[], usable_for_answering, unusable_reason. | SOURCED | `checker/evidence_pack.py:432-457` |
| E16 | Pack `as_of` has **no date field by design**: basis `CURRENT_CONSOLIDATION_AS_INGESTED`, point_in_time_verified=False, evidence_state UNRESOLVED, corpus_fetched, point_in_time_requested, statement. | SOURCED | `checker/evidence_pack.py:324-379` |
| E17 | A clean provision is at most `CORROBORATED`, never VERIFIED. SD-002 (s.16, 124, 76A, 329) and SD-002-OPEN (s.236, 465, 247, 74, 78) are unusable. | SOURCED | `checker/evidence_pack.py:160-168, 653-665, 793-797` |
| E18 | Retrieval routes are `exact`, `search`, `abstain`. A cited-but-unresolvable provision abstains without searching. | SOURCED | `checker/retrieve.py:42-44, 139-174` |
| E19 | Citation retrieval holds only COMPANIES_ACT_2013. A Rules citation or another Act returns no hit. Subsections resolve to the section, and the subsection is recorded. | SOURCED | `checker/legal_retrieval.py:52-54, 252-260, 97, 26-28` |
| E20 | `retrieve("rule 2(1)(t)")` → route `abstain`, with the notice "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R2 (Definitions) was cited and DOES exist…". Rule-number matching reads one Rules file (Board Meetings Rules), so rule 2(1)(t) of the Specification of Definition Details Rules is reported as the Board Meetings Rules r.2. | MEASURED; SOURCED | `checker/retrieve.py:48, 60, 63-76` |
| E21 | `retrieve("s.2(85)")` → route `exact`, usable key `ACT:COMPANIES_ACT_2013:S2`, as_of basis CURRENT_CONSOLIDATION_AS_INGESTED, corpus_fetched `2026-08-18`. | MEASURED | — |
| E22 | A dated figure: `Threshold` = key, amount, effective_from, effective_to, instrument, source_url, state, note; `lookup()` raises rather than guessing and never falls back to the statutory floor. | SOURCED | `checker/prescribed_thresholds.py:49-76, 262-279` |
| E23 | At 2026-09-15, the paid-up prescribed limit held is ₹10 crore, G.S.R. 880(E), effective 2025-12-01, CORROBORATED, servable=True. | MEASURED | `checker/prescribed_thresholds.py:243-249` |
| E24 | `currency.Finding` = obligation_id, status, detail, instrument. It carries **no in-force date**. | SOURCED | `checker/currency.py:41-45, 76-81` |
| E25 | `document_check` returns superseded[] (governed_then, governs_now, instrument, reference), cannot_verify[], verified[], a coverage frame, what_this_is / what_it_is_not, and `no_model: true`. | SOURCED | `checker/api.py:305-404` |
| E26 | Coverage frame JSON: checked, checked_count, unchecked[{what, why, acquire, state}], unchecked_count, corpus, as_of, sentence, establishes_compliance=false, dismissable=false. | SOURCED | `checker/coverage.py:108-135` |
| E27 | Scope register: 1 body IN_CORPUS (CA2013), 1 CURRENT_ONLY (SEBI LODR), 7 DECLARED (LLP, SEBI other, FEMA, IBC, Competition, Stamp, **DPDP**), 2 OUT_OF_SCOPE (PoSH, AI law). `scope.coverage()` = "1 of 9 in-scope bodies of law are held". | SOURCED + MEASURED | `checker/scope.py:76-153, 208-211` |
| E28 | `refusal_for(key)` returns distinct text for OUT_OF_SCOPE, CURRENT_ONLY and DECLARED, and raises for IN_CORPUS. An undeclared body (e.g. GST) raises `LookupError`, so it has no refusal text. | SOURCED | `checker/scope.py:172-176, 191-205, 320-326` |
| E29 | The DECLARED refusal says the body "is within scope … but no instrument has been acquired … This is a statement about what we hold, not a finding that no obligation applies." | SOURCED | `checker/scope.py:202-205` |
| E30 | There are 5 bundles, all `uses_model=False`. The router refuses near-misses and never substitutes. `dispatch` returns `{bundle, uses_model, result}`. | SOURCED + MEASURED | `checker/bundles.py:134-152, 176-199, 238-240` |
| E31 | The obligation register holds 15 obligation ids, all CA2013. Row states: APPLIES_SATISFIED, APPLIES_NOT_SATISFIED, APPLIES_UNDETERMINED, DOES_NOT_APPLY, CANNOT_DETERMINE. | SOURCED | `checker/scope.py:160-169`; `checker/obligations.py:47-57, 119-128` |
| E32 | Session: client text stays in memory. `releasable()` refuses a record that carries a verbatim ≥40-char fragment. It does not catch paraphrase, and "a narration layer will need its own control". | SOURCED | `checker/session.py:37-40, 50-53, 112-128` |
| E33 | Two model contracts exist and are not joined. The orchestrator drives `reasoning.Proposal` (document facts with spans); the model adapter drives `Claim`s with evidence_ids. | SOURCED | `checker/orchestrator.py:57-58, 186-189`; `checker/model_adapter.py:274-275` |
| E34 | No conversation state exists anywhere. | SOURCED | `docs/FEATURES.md:120` |

---

## Evidence quality

High for (1)–(4). Every row is a direct read of the current tree (HEAD `ab377b7`) or a run of it. Limits:

- The MEASURED values (E20, E21, E23, E27) depend on on-disk registration and corpus state today; they
  can change when an instrument is attested or withdrawn.
- I did not run the full test suites (`scripts/run_tests.sh`).
- The "not imported" statements (E13, E33) rest on grep over `checker/ scripts/ backend/`. A dynamic
  import would not show up.

---

## Result

### R1 — What a `/v1/ask` response can carry today, from BUILT modules

| Field family | Available today from | Caveat |
|---|---|---|
| **Engine outcome** (not a UI state) | Orchestrator verdict (E3); adapter decision (E7); retrieve route (E18) | Three vocabularies, none of them `answered/partial/out_of_scope` (E2) |
| **Refusal reasons** | Review violations + DOCUMENT_DATE_CONFLICT (E3, E6); adapter warnings (E7); pack `missing[]` and `unusable_reason` (E14, E15); `refusal_for()` text (E28); `NoSuchCapability` message (E30) | Free-text details; codes are stable strings |
| **Citations** | Qualified keys, title, evidence_state, defects, sha256, sources (E15) | Section-level only; subsection is recorded, not resolved (E19) |
| **Evidence-pack ids** | `provision_keys`, `usable_keys`, `unusable_keys` (E14) | A pack has no id or hash of its own. **Pack id = NEW** |
| **As-of (law)** | Pack: an explicit "no point-in-time" statement plus corpus_fetched (E16). Figures: `effective_from`, `instrument`, `state` per Threshold (E22, E23) | Only prescribed thresholds carry a dated instrument. Section text carries an ingestion date, not an in-force date |
| **As-of (read date)** | `as_of` request field, the pattern in document_check (E25) | — |
| **Currency** | superseded / cannot_verify / verified with governed_then / governs_now (E25) | Needs a document date; Finding has no date (E24) |
| **Scope frame** | coverage frame (E26); `scope.coverage()` (E27) | The frame is built only in document_check |
| **Stages** | Orchestrator `steps[]` (E4) | A post-hoc trace, not a stream. Stage names are internal (capability, model, review…) |
| **Model disclosure** | `uses_model` / `no_model` (E25, E30); `model_name`, `prompt_version` (E8) | — |
| **Claims** | claim text, type, evidence_ids, verifier verdict, issues (E10, E12) | Nothing reaches SUPPORTED (E11) |

**Missing (must be built or decided before `/v1/ask`):**

1. **The state mapping itself.** No module turns engine outcomes into the three UI states (E2). It has to
   be a server function, per C3.
2. **An "answered" path for model-composed text.** The claim verifier cannot authorise a legal statement
   (E11). The cascade can say "supported" (E13), but it is wired only through `ground_span`, not into the
   adapter or orchestrator path. *INFERRED:* today, `answered` is truthful **only** for deterministic
   results — a bundle row, or a servable Threshold. Every model-path answer is `partial` at best.
3. **Question → body-of-law detection.** No module maps free text to a `scope.Body` key. `out_of_scope`
   therefore cannot be decided from a question today. `refusal_for` needs a key (E28). An undeclared body
   such as the Income-tax Act (the UX spec's own §3.3 example) has no refusal text at all.
4. **Free-text Q&A with no document.** The orchestrator requires a document date (E5); `retrieve()` does
   not (E18). The "general" context has no driver.
5. **Joining the two model contracts** (E33).
6. **Conversation state** (E34) and per-turn re-grounding.
7. **A narration leak control.** The session guard is verbatim-only (E32).
8. **An in-force date on currency findings** (E24) and on section text (E16).
9. **Streamed stage captions.** Today only the post-hoc trace exists (E4).
10. **A correct Rules-instrument resolver.** Rule numbers match against the Board Meetings Rules file only
    (E20), so a citation to another Rules instrument is misnamed in the refusal.

### R2 — Draft contract (fields from built modules; `NEW` = no module produces it)

Envelope, common to all states:

```jsonc
{
  "schema": "placedon.ask/0",                      // NEW
  "state": "answered | partial | out_of_scope",    // NEW — server-decided mapping (C3)
  "question": "…",                                 // evidence_pack.query  (evidence_pack.py:469,497)
  "generated_at": "2026-09-15T00:00:00Z",          // api.py:393 pattern
  "as_of": "2026-09-15",                           // read date; api.py:286 pattern
  "context": { "kind": "document | general",       // kind: NEW
               "document_date": "2024-06-01|null" },// orchestrator.py:186; api.py:285
  "uses_model": false,                             // bundles.py:199 / api.py:403
  "scope": { "held": ["CA2013"],                   // scope.in_corpus() (scope.py:179)
             "sentence": "1 of 9 in-scope bodies of law are held" }, // scope.coverage() (scope.py:208)
  "stages": [ { "n": 1, "what": "capability", "detail": "…" } ],     // orchestrator.Step (orchestrator.py:80-85)
  "turn_id": "…"                                   // NEW (no conversation state, FEATURES.md:120)
}
```

**Forbidden in every state (C4):** `claim.confidence` (claim_schema.py:60) and
`ClaimVerification.coverage` (claim_verifier.py:94) exist in the built modules and **must be dropped**
from the contract, not renamed.

**`answered`** — only a deterministic source may produce it today (R1 item 2):

```jsonc
{ "state": "answered",
  "headline": "Not a small company.",                          // NEW (server-composed)
  "figures": [ {                                               // prescribed_thresholds.Threshold (:50-63)
      "label": "Paid-up capital limit",                        // NEW (label)
      "amount": "₹10 crore",                                   // Threshold.amount — MEASURED E23
      "instrument": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
      "effective_from": "2025-12-01", "effective_to": null,
      "evidence_state": "CORROBORATED",
      "source_url": "…" } ],                                   // Threshold.source_url
  "rows": [ { "obligation_id": "CA13-S2-85-SMALL",             // api._row_json (api.py:122-134)
              "provision": "Companies Act 2013, s.2(85)",
              "state": "DOES_NOT_APPLY", "basis": "…" } ],
  "citations": [ { "ref": "ACT:COMPANIES_ACT_2013:S2",          // evidence_pack.py:432-457
                   "title": "…", "evidence_state": "CORROBORATED",
                   "defects": [], "usable_for_answering": true,
                   "subsection": "(85)" } ],                   // legal_retrieval.Hit.subsection (:97)
  "law_version": { "basis": "CURRENT_CONSOLIDATION_AS_INGESTED", // evidence_pack.AsOf (:342-346)
                   "point_in_time_verified": false,
                   "corpus_fetched": ["2026-08-18"] },
  "evidence_pack": { "id": "…",                                // id: NEW
                     "usable_keys": ["ACT:COMPANIES_ACT_2013:S2"], "unusable_keys": [], "missing": [] },
  "what_it_is_not": ["…"] }                                    // api.py:257-261 pattern
```

**`partial`** — something held and usable, something not:

```jsonc
{ "state": "partial",
  "confirmed": [ { "ref": "ACT:COMPANIES_ACT_2013:S173", "…": "…" } ],      // grouping: NEW; items = usable provisions / verified rows
  "not_confirmed": [                                                         // grouping: NEW; items below are built
     { "kind": "pack_missing", "detail": "<evidence_pack.missing[] string>" },          // evidence_pack.py:710-729
     { "kind": "unusable", "ref": "ACT:COMPANIES_ACT_2013:S16",
       "reason": "<unusable_reason()>", "defects": ["SD-002"] },                          // evidence_pack.py:419-430
     { "kind": "refusal", "code": "FIGURE_INVENTED", "detail": "…", "offending": "…" },  // reasoning.Refusal (:79-82)
     { "kind": "model_decision", "code": "INSUFFICIENT_EVIDENCE", "warnings": ["…"] } ], // model_adapter.py:54-71
  "verbatim": [ { "ref": "…", "reading_text": "…", "corpus_fetched": "2026-08-18",
                  "corpus_content_sha256": "…" } ],                                      // evidence_pack.py:442-443, 441
  "coverage": { "…": "coverage.Report.to_json()" },                                        // coverage.py:123-135 (document context only)
  "route": "exact | search | abstain",                                                     // retrieve.py:42-44
  "demand_signal": { "action": "tell_us_blocking" } }                                      // NEW (UX spec §3.2)
```

**`out_of_scope`**:

```jsonc
{ "state": "out_of_scope",
  "body": { "key": "FEMA1999",                                     // body DETECTION: NEW
            "name": "Foreign Exchange Management Act, 1999 and the FDI rules",
            "regulator": "RBI / DPIIT",
            "scope_status": "DECLARED" },                          // scope.Body (scope.py:44-53)
  "reason": "Foreign Exchange Management Act, 1999 and the FDI rules (RBI / DPIIT) is within scope — it covers foreign investment, sectoral caps, reporting (FC-GPR, FC-TRS), downstream investment — but no instrument has been acquired, so nothing here can be decided. Nothing acquired. Sectoral caps change by press note, which is a different acquisition problem from a Gazette rule. This is a statement about what we hold, not a finding that no obligation applies.",
                                                                  // scope.refusal_for("FEMA1999") composed from scope.py:110-116, 202-205
  "held": ["Companies Act, 2013"] }                                // scope.in_corpus()
```

A body the register does not declare (e.g. Income-tax) has no `refusal_for` text (E28), so its `reason`
would be NEW copy.

**Proposed mapping (NEW; INFERRED — for Phase C to test, not decided here):**

| Engine result | → state |
|---|---|
| A question detected as belonging to a body with status ≠ IN_CORPUS | `out_of_scope` |
| A deterministic bundle row or servable Threshold, with pack `insufficient_evidence=false` and no unusable key the question named | `answered` |
| Pack has usable **and** unusable/missing items; or orchestrator `SERVED*` with any claim below SUPPORTED; or adapter `INSUFFICIENT_FACTS` | `partial` |
| `ABSTAINED`, `REFUSED_BEFORE_CALL`, adapter `INSUFFICIENT_EVIDENCE`, route `abstain` for CA2013 | `partial` with empty `confirmed` — see U2 |
| `BUDGET_EXHAUSTED` (model_adapter.py:62) | **not a legal state** — a service error, never rendered as abstention |

### R3 — Design tokens: DESIGN_SYSTEM.md vs task pane

| Token / rule | DESIGN_SYSTEM.md | Task pane | Agree? |
|---|---|---|---|
| Ink | `#0A0A0A` (BP:DS:33) | `--ink:#0A0A0A` (taskpane.html:9) | yes |
| Parchment | `#F5F3EF` (DS:34) | `--parch:#F5F3EF` (:9) | yes, name differs |
| Slate | `#475569`, CTAs/active/verified, 1 per view (DS:35) | `--slate` used for **secondary text**: .sub, .meta, h2, .prov, .empty, summary, .k (:15,20,23,29,32,34,38) | **no** — the DS gives secondary text to Ink-80 `#4A4A4A` (DS:36) |
| Caution | `#8B4513`, abstention (DS:41) | Used for superseded rows (:25), refs (:31), a bad CIN (:42), the blocking head (:47), the coverage frame (:48) **and the `.err` backend-failure box (:33)** | **no** — styles an error the same as abstention (C5) |
| Abstention card | Caution left border (DS:87) | "Could not verify" rows use a **Slate** border (:26) | **no** — inverted |
| Verified | Slate-20 left border (DS:87) | `.row.ok` green `#7a9a7a` (:27) | **no** — an undeclared hue |
| Borders | Ink-10 `#E8E6E2` (DS:38) | `--rule:#D8D4CC` (:9) | **no** — undeclared |
| White | Cards "White bg" (DS:86), but no token in §2; UX spec asks to add `#FFFFFF` (BP:UX:241) | `#fff` literals (:18,24,33,36,48) | partial |
| Colours per screen | Max 3 (DS:15) | ink, parch, slate, caution, rule, white, green | **no** |
| Radius | 4px always (DS:85) | 3px (:18) | **no** |
| Body size | 14px (DS:67) | 13px (:11) | **no** |
| Minimum size | none below 12px (DS:71) | 11px in ≥10 rules (:15,20,22,29,31,34,38,41,44,50) | **no** |
| Sans stack | `-apple-system,"Helvetica Neue",Helvetica,Arial` (DS:57) | adds `"Segoe UI"` (:11) | minor — INFERRED reasonable for Word on Windows |
| Mono | JetBrains Mono 13px (DS:58,69) | `ui-monospace,Menlo` 11px (:29,31,41) | **no** |
| Headings | Playfair Display for Display/H1 (DS:56) | system sans, h1 14px (:14) | **no** — defensible at 320px, but undecided |
| Labels | H3 14px/600 (DS:66) | uppercase, letter-spaced 11px h2 (:22) | **no** |
| Italics | never, except placeholders (DS:73-74) | `.empty` italic (:32) | **no** |
| Primary button | Slate bg (DS:84) | Ink bg, white text (:17-18) | **no** |
| Focus | 2px Slate outline (DS:128) | none defined (:8-54) | **no** — falls back to the browser default |
| Spacing | 4px base (DS:78) | 14/10/9/6/3px paddings (:13,17,24,36) | **no** |
| Shadows / motion | none; ≤200ms (DS:10,19) | none | yes |
| Stack | Next.js + Tailwind + shadcn (DS:134) | vanilla HTML/JS; office.js from Microsoft CDN (:7) | **no** — PLAN_13 Phase B is also "no framework, no CDN" (PLAN_13:53) |

**The two specs also disagree with each other.** DS §6 keeps Dashboard, Corpus/Client Manager,
Deadlines, ROC lookup and Settings (DS:97-103). UX §5 cuts all of them (UX:211-216). UX:4-5 says UX wins
on flows, so UX governs. DS:3 and UX:248 call DPDP out of scope, while the backend register says DECLARED
(scope.py:136-142).

### R4 — Capabilities the composer may truthfully suggest

A suggestion may name only a declared bundle (E30) or a held provision (E19, E27), and must satisfy the
bundle's required inputs.

| Suggest? | Capability | Truthful example wording | Basis |
|---|---|---|---|
| **Yes** (document context) | `document.currency_check` | "Has the law this document rests on moved since it was made?" | bundles.py:135-138; needs document_date, company_class, incorporation_date |
| **Yes** | `company.compliance_matrix` on one of the 15 obligations | "Is this a small company on [as-of]?" (s.2(85)); "Is the AGM within the statutory gap?" (s.96(1)); "Are enough board meetings held, correctly spaced?" (s.173(1)); "Does a CSR committee have to be constituted?" (s.135(1)) | bundles.py:139-142; obligations.py:620-622, 635-637, 695-697, 710-712. It must also say that 15 obligations are not the whole Act (api.py:257-261) |
| **Yes** | `law.changes` | "What changed in the law since [date], dated and sourced?" | bundles.py:143-145; law-change events only, not company facts (api.py:197-199) |
| **Yes, as a source lookup, not an answer** | citation retrieval | "Show s.173 of the Companies Act 2013" | legal_retrieval.py:302-308; retrieve.py:153-158. Not s.16/124/76A/329 or s.236/465/247/74/78 (evidence_pack.py:160-168). No Rules (legal_retrieval.py:52-54) |
| No | `law.acquisition_exposure` | — | Operator-facing (bundles.py:146-148); INFERRED not a practitioner question |
| No | `document.ground_extraction` | — | A pipeline step, not a question (bundles.py:149-151) |
| **Never** | any DECLARED / CURRENT_ONLY / OUT_OF_SCOPE body: SDF/DPDP, LLP, dated LODR, FEMA, IBC, Competition, stamp duty, PoSH | — | scope.py:84-152 — a suggestion the engine can only refuse |
| **Never** | attach PDF, voice, export, follow-up/history | — | not in any bundle (bundles.py:134-152); no conversation state (FEATURES.md:120) |

### R5 — `ask.html` against the two specs (BP:landing-page/ask.html)

| # | ask.html | Contradicts |
|---|---|---|
| A1 | "✓ Paid-up capital … (below ₹50,00,000 limit)" and "Turnover … (below ₹2,00,00,000 limit)" (ask:276-277), under "Answered — verified" (ask:262) | UX:26-31 — superseded 2013 figures. Operative today: ₹10cr / ₹100cr, G.S.R. 880(E), in force 01-Dec-2025 (also E23). The backend refuses to fall back to the floor (prescribed_thresholds.py:273-279) |
| A2 | No instrument and no as-of beside any figure (ask:270-278) | UX:42-44, 92-94 (C2) |
| A3 | "✓ Verified — Adv. R. Sharma" (ask:271) | Invented reviewer. No module records a named legal verifier. Corpus maximum is CORROBORATED (E17); the verifier never returns SUPPORTED (E11) |
| A4 | Chip "Is this client a Significant Data Fiduciary?" (ask:259) | DPDP is out of scope (DS:3; UX:248); DECLARED in scope.py:136-142, so refusal only |
| A5 | Two states, "Answered — verified" / "Answered — abstained" (ask:262, 287) | UX:66 (exactly three); no out_of_scope; an abstention labelled "Answered" |
| A6 | "The system cannot answer this question." (ask:290) | UX:139-143 (degrade, never stop); no CONFIRMED / NOT CONFIRMED split (UX:144); no verbatim text (UX:145-147) |
| A7 | The abstention reason merges two texts: "…we have not dated is not a computable threshold — it requires a Central Government gazette notification naming this entity. No such notification is on file for DEF Ltd." (ask:292-294) | Grafts the DPDP SDF gazette-naming logic (BP:CLAUDE.md "SDF lookup problem") onto s.2(85). The s.2(85) limit is prescribed by rule, not by notification naming the entity (UX:22-31). Garbled and wrong |
| A8 | `<em>` inside the reason (ask:292) | DS:73-74 (no italics) |
| A9 | "📎 Attach PDF", "🎙 Voice" (ask:248-249) | UX:213 (document upload cut); PLAN_13:42-43 |
| A10 | Nav: Dashboard, Corpus Manager, Clients, Deadlines, District / ROC Lookup, Settings, Billing (ask:224-232) | UX:211-216 (all cut). "District / ROC Lookup" would "print the wrong official's email" (UX:215) |
| A11 | Header search "Search clients, provisions, deadlines…" and avatar "PS" (ask:217-218) | UX:213-214 (clients, deadlines cut) |
| A12 | Client select "ABC Pvt Ltd / XYZ Ltd / DEF Ltd" (ask:241) | UX:213 (client manager cut); invented entities |
| A13 | "Export PDF", "Ask Follow-up" (ask:282-283) | No export bundle (bundles.py:134-152); no conversation state (FEATURES.md:120) |
| A14 | "Request Verification", "Check Gazette Register" (ask:297-298) | UX:133, 150-152 — the second action is the demand signal "Tell us this is blocking you"; no gazette-register capability exists |
| A15 | Citation badge "s.2(85), Companies Act 2013" (ask:270) | UX:77-79 wants clause + rule + instrument + as-at |
| A16 | Composer states no scope (ask:244-253) | UX:168-170 (G1: name the covered Act) |
| A17 | Accents: primary button (ask:142), active nav Slate border + Slate-20 bg (ask:82), verified badge (ask:185) | DS:21 (more than one accent element = failed) |
| A18 | Generic `monospace` (ask:101,184,196,210); 11px label (ask:161); h1 28px/600 (ask:91); radius 50% (ask:61) and 3px (ask:210) | DS:58, 71, 63-64, 10 |

---

## Unresolved issues

- **U1 — Can a model-path answer ever be `answered`?** It needs either SUPPORTED from an entailment
  checker wired into `claim_verifier`, or `ground_span` ESTABLISHED wired into the adapter or orchestrator.
  Neither exists (E11, E13). This is a policy decision, not a UI one.
- **U2 — Refusal inside the held Act.** When nothing is usable for a CA2013 question (route `abstain`,
  `ABSTAINED`), the three-state contract has no clean slot. `partial` with an empty `confirmed` risks the
  "blank refusal" UX §3.2 warns against; `out_of_scope` would be false. OPEN.
- **U3 — The out_of_scope heading is false for DECLARED bodies.** UX §3.3's heading "Outside what
  Placedon covers" (UX:158) contradicts `refusal_for`, which says the body "is within scope" (E29). The
  heading word must change or the state must split. OPEN.
- **U4 — DPDP status conflicts:** BP specs say OUT_OF_SCOPE; scope.py says DECLARED. The backend CLAUDE.md
  names scope.py the authority. I did not reconcile the BP docs (public repo, read-only).
- **U5 — Rules resolver misnames instruments (E20).** Not verified beyond this one probe.
- **U6 — Section text carries no in-force date.** For a quoted provision (not a threshold), C2's "as-of next
  to the number" can truthfully show only "current consolidation, ingested 2026-08-18, not point-in-time"
  (E16).
- **U7 — The measured threshold state is volatile (E23).** Fixtures must not hard-code it as permanently
  servable.

## Recommended next action

1. Phase C: write `web/assistant/contract.md` from R2, with the mapping table as tests that fail first. The
   validator should reject `confidence`/`coverage` fields, a state not produced by the mapping, a figure
   without `instrument` + `effective_from`, and a citation key absent from `evidence_pack.usable_keys`
   (PLAN_13 §6.5).
2. Record U1–U3 as decisions in the design spec before any fixture uses `answered` for a model-composed
   sentence.
3. Open a task for R1 item 3 (body detection) and item 10 (Rules resolver). Both are backend work, outside
   this loop.

---

## What this means for the Ask section design

| Verdict | Element | Reason (tied to C1–C10) |
|---|---|---|
| **Keep** | The coverage frame, never collapsible, leading the result (taskpane.js:125-156; coverage.py:108-135) | C2/C3: an answer carries its own scope. Already built and practitioner-derived |
| **Keep** | `what_it_is_not` beside every answer (api.py:257-261, 401-402) | C1: bounds the claim |
| **Keep** | Figures rendered from `Threshold` with instrument + effective_from inline | C2: the only built source of a dated figure (E22) |
| **Keep** | Citation chips as qualified keys + evidence_state + defect codes | C2/C5: CORROBORATED is the honest ceiling (E17); a defect stays visible |
| **Keep** | `refusal_for()` text verbatim as out_of_scope copy | C3/C5: server-authored, distinguishes "not held" from "nothing applies" (E29) |
| **Keep** | Task pane's "Nothing was changed in your document" on failure (taskpane.js:71-72) | C7: document-context trust |
| **Adapt** | Stages: map orchestrator/retrieve step names to plain captions ("finding the provision", "checking the source", "checking dates") and show only captions before the state | C4 + harsh Q3: the trace exists (E4) but is post-hoc and internal |
| **Adapt** | Out-of-scope heading: use a word that is true for DECLARED bodies (e.g. "Not held") | C3/C5 + U3 |
| **Adapt** | Task-pane tokens: move secondary text Slate → Ink-80, borders `#D8D4CC` → Ink-10, radius 3 → 4px, minimum 12px, add a 2px Slate focus ring, drop the green `#7a9a7a`, give `.err` a neutral Ink treatment distinct from Caution | C5/C6 (R3) |
| **Adapt** | Composer suggestions generated from `bundles.registry()[*].answers` and the obligation duties, never hand-typed | C1 + PLAN_13 §4 (R4) |
| **Adapt** | Context toggle (document / general): "document" is the only fully-driven path today (E5) — "general" must say it returns source lookups, not decisions | C7/C8 + harsh Q7 |
| **Reject** | Any confidence %, `claim.confidence`, `coverage` float in UI | C4 (E10, E12) |
| **Reject** | A "Verified" badge or a reviewer name on an answer | C5/C10: nothing reaches VERIFIED or SUPPORTED (E11, E17) |
| **Reject** | ask.html as a base, including its nav, client picker, attach/voice/export/follow-up, and the SDF chip | C9/C10 (R5 A1–A18) |
| **Reject** | Token streaming of prose | C3/C4: no module decides a state before the whole review completes (orchestrator.py:215-259) |
| **Reject** | Rendering `BUDGET_EXHAUSTED` as an abstention | C5: it is a wallet statement, not a legal one (model_adapter.py:21-25) |
| **Reject** (for now) | Follow-up threads | C8: no conversation state (E34); each turn would need its own pack and as-of, and none exists |
