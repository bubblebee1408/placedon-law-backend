# `/v1/ask` response contract — `placedon.ask/0`

Written 2026-09-15 (runbook task UX-C). **The route exists** as of 2026-09-18 (ASK-1):
`POST /v1/ask` in `checker/api.py`, answered by `checker/ask.py::answer()` from deterministic
engine calls alone — no model is called on any path and `uses_model` is always `false`. The
prototype renders fixtures and sends nothing when it is opened from a file; served by
`scripts/serve_ask.py` on 127.0.0.1 it asks this route live (D2, `web/assistant/README.md`).
Every fixture is a REQUEST put through the same `answer()`, and a live turn is rendered by the
same renderer, so the prototype and the route cannot drift.
Validator: `checker/ask_contract.py` — the route runs it on every response and withholds a
violation as a `500` (§6 D18). Fixture builder and the validator's tests:
`scripts/assistant_contract.py`.
> **STATUS (2026-09-19) — the three blocking defects are fixed; the route is awaiting its next
> independent verification.** Do not wire a client to `/v1/ask` until that verification passes,
> with the single exception the founder approved for the demo (`research/TASKS.md` A-011):
> `scripts/serve_ask.py`, the local demo server, which binds 127.0.0.1 alone and serves this route
> only to `web/assistant/` on its own origin — every open item below still stands, and the page
> sends only `{question, context}`, so a live turn is answered by what the question itself names. Fixed in ASK-1 fix round 3 (§6 D19–D22):
> 1. **The NCLT and the IBBI no longer refuse anything on their own** (`88b6d8a`). The six cases
>    that were refused as the IBC are not refused now, with or without a section number — and
>    "not refused" is all that is claimed. Asked with no provision named, four of the six
>    (capital reduction, oppression, public-to-private conversion, IBBI-registered valuers) come
>    back `partial` with `confirmed: []` and one item, the evidence pack's own "No provision was
>    retrieved at all. This pack is empty."; the other two find a section by word match and show
>    its text, not applied to any company (scheme of amalgamation → s.232, just-and-equitable
>    winding up → s.242). Naming the provision (`provisions: ["s.66"]` and so on) is what makes
>    such a turn read the section the question is about. The IBC still refuses by title, by
>    acronym and by its own terms of art (CIRP, resolution professional, insolvency commencement).
> 2. **One citation grammar.** A provision is read by the retriever's own scanner everywhere, so
>    "s 2(85)", "u/s 2(85)", "S 2 (85)", "ss. 2(85)" and "§ 2(85)" all find the s.2(85) row; a
>    shape the scanner cannot read is a `400` (`137e74f`).
> 3. **The title the user names beats register order:** "s.62 and SEBI ICDR" and "SEBI approval for
>    a buyback" refuse as SEBI_OTHER, with that body's text (`b8498bc`).
> Also fixed: facts are typed on every path, applied or not; an answer's citations are checked by
> clause, not section (`d31ad71`, `137e74f`).
>
> **Round 4 (2026-09-19/21) narrowed the request rather than patching cases** (§6 D23–D25):
> - **A provision is exactly one Companies Act citation** (`8b32b84`). "s.2(85) and s.62",
>   "s.2(85), s.186 and s.188" and "sections 2(85) to 5" were answered with citations the row and
>   the figure did not rest on; "section 2(85) of the LLP Act, 2008" and "section 7 of the IBC"
>   were answered as the Companies Act's. All are now a `400` saying why.
> - **One evidence schema, typed strictly, on every route** (`11725d3`). `calendar_year: "2025"`
>   with four 2025 board meetings produced **a defect in a company that had complied** —
>   `APPLIES_NOT_SATISFIED` on s.173 — because the year was never typed; `resident_director_days:
>   "many"` was a `500`. Both were reachable through `/v1/compliance-pack` as well, and a false
>   defect there breaks CLAUDE.md. Now a `400`, never a coercion.
> - **A citation in the question's own words is no longer described as a word match**
>   (`ac6e6b7`), and the turn says it was read as a *Companies Act* section, which is not
>   necessarily the Act the question meant.
>
> **Still open, stated plainly:**
> - A clause the Act does not have (`s.2(85)(iii)`) still answers on the s.2(85) row. The
>   structural index cannot say a clause is absent (it splits s.180(1) into (i)/(ii), not the
>   Act's (a)–(e)), so using it would refuse real clauses.
> - A regulator named with no held law still refuses as the one body the register lists it under,
>   which can be the wrong body ("RBI" in an NBFC-director question refuses as FEMA).
> - A SEBI regulation the register does not declare at all (Delisting, Mutual Funds) refuses with
>   SEBI LODR's text — register order is the only thing left to decide it. The fix is a register
>   entry in `scope.py`.
> - The IBBI's place among the Companies Act's own forums rests on the Registered Valuers Rules
>   2017, which this engine does **not** hold: a founder decision (runbook DEMO PLAN D1), not a
>   corpus fact. The NCLT's rests on s.408 in our corpus.
> - Some empty-`confirmed` partials' only reader text is an evidence-pack string written for a
>   model ("not admitted for model use … Its text is unknown to you") — §9.4, ASK-2.
> - Homoglyphs from other scripts (a Cyrillic "Е" in "SЕBI") are not folded.
> - A bare section number next to an unheld body's title refuses the whole question ("Under s.230
>   … Insolvency and Bankruptcy Code …" → IBC): §6 D2 decides that the number is that body's, and
>   it is recorded as a design choice, not a bug.
> - An IBC question that uses none of its terms of art ("NCLT admitted our insolvency
>   application", "pre-packaged insolvency resolution process") is not refused; it comes back
>   `partial`. A missed refusal is the safe direction, and the terms of art are the register's to
>   extend.

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
| `evidence_pack` `{retrieval_query, route, usable_keys, unusable_keys, missing, insufficient_evidence, abstain_reason}` | `retrieve.retrieve` + pack `to_dict` (`query` — K10). **`abstain_reason` added 2026-09-26, additively** (PLAN_17 M7 rule 1): one of `HELD_NOT_ADMITTED` / `CITATION_UNRESOLVED` / `NOTHING_RETRIEVED`, and `""` whenever the route did not abstain — never `null`, so the type never varies. `route` itself could not carry it: `scripts/assistant_contract.py` pins `route == "abstain"` on a fixture, so its values are contract. **There is deliberately no code for "the question was not about law"** — an off-topic question and held law the retriever missed are the same fact about this engine, and separating them would need a model deciding scope, which `scope.py` alone decides. See `docs/plan19/decisions/M1_ABSTAIN_REASON.md`. |
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
| `body` `{key, name, regulator, covers, scope_status}` | `scope.body(key)`; detection: `checker/ask_scope.py` (§6 D2) |
| `reason` | `scope.refusal_for(key)` verbatim |
| `held[]` | `scope.in_corpus()` |

A body the register does not declare (e.g. the Income-tax Act) has no `refusal_for` text; its `reason`
would be NEW copy and needs its own decision. **Still open after ASK-1**: such a question is *not*
out_of_scope, and nothing is invented for it (PLAN_13 §7.12 calls `body.undeclared_reason` NEW and
blocking). It is decided by what the request names, like any other turn: naming nothing, it comes
back `partial` (lexical retrieval over its words, or nothing reached); with facts but no provision,
`partial` (the facts are not applied, D6). If the request names Companies Act provisions or figures,
those are answered **as named** — the engine does not know the question was about income tax, and
the capability row that sent them is responsible for having chosen them.

## 6. State mapping — DECIDED 2026-09-18 (ASK-1), revised the same day after the verifier

Implementation: `checker/ask.py` (mapping, request), `checker/ask_scope.py` (scope),
`checker/ask_read.py` (engine readers, citation grammar), `checker/ask_contract.py` (validator).
Every decision below is a choice this build made; the table it replaces was inferred. Where a case
was **not** decided it says so rather than guessing. Fix round 1 (verifier FAIL on `be078a6`)
revised D1, D2, D4, D6, D11, D14 and added D16–D18. Fix round 3 (2026-09-19, after the second
verifier FAIL and the founder's decision in the runbook's DEMO PLAN) added D19–D22 and revised the
D2 rows, D16 and D17 to match.

### The request

```jsonc
POST /v1/ask
{ "question": "Is this company a small company?",   // rendered verbatim, ≤ 2,000 characters;
                                                    // its meaning is never decided (D1)
  "as_of": "2026-09-15",                            // optional; defaults to the day in generated_at
  "context": { "kind": "general", "document_date": null },
  "facts": { … },                 // general: api.PROFILE_KEYS (+ "evidence": api.EVIDENCE_KEYS)
                                  // document: what /v1/document-check takes
  "provisions": ["s.2(85)"],      // citations to read: s.173, section 2(85), rule 3
  "figures": ["small_company.turnover.prescribed"],   // prescribed-threshold keys
  "parent_turn_id": "t_20ccadb72b4b" }
```

**D1 — only what the request names can be answered.** A deterministic engine cannot know which
provision a sentence is about, and guessing would put a citation under words nobody asked us to
interpret — the Act-versus-Rule collision `retrieve.py` exists to prevent. So the caller (the
capability row of PLAN_13 §4.1) names what it wants read: `provisions` must each be a citation read
by the retriever's own grammar (D21; a bare number, a year, a topic, or a shape that grammar cannot
read is a `400`), and `figures` must be keys the threshold table declares
(`400` otherwise). An unresolvable citation comes back as a pack miss, never as a near-miss.
**Where the request names no provision, `retrieve()` runs lexical retrieval over the question's
words** — a match of words against the corpus, with its own route (`search`, or `exact` where the
sentence itself carries a citation), not an understanding of the question. What that finds is
shown as the stamp line's "Looked up …", and it can **only ever feed a `partial` turn**, which says
so (`ask.LEXICAL`).

### The mapping

| Case | State | Decision |
|---|---|---|
| The question is about a body `scope.py` declares and does not hold | `out_of_scope` | **D2 (revised).** Decided first, by `checker/ask_scope.py`, from `scope.py`'s strings alone. **A wrong refusal of held law is the worse error** — it tells a user we do not cover what we do — so the detector is built around not making it. *Title signals* (strong): multi-word chunks of the body's `name`, capitalised 3+-letter acronyms in it (`FDI`, `SEBI`, `ICDR`), and the key's own acronym where the key is one token (`LLP`, `FEMA`, `IBC`); acronyms match case-sensitively. *Regulator signals* (weak): each regulator named. Any signal that is also a **held** body's declared string is dropped (`MCA` regulates the Companies Act, so it refuses nothing). **`covers` phrases are never a trigger** — "board composition", "annual filings", "issue of capital", "internal committee" are the held Act's vocabulary too — and serve only to choose between bodies already named ("SEBI … insider trading" → SEBI_OTHER). Which of several named bodies: D20. The Companies Act's own forums, the NCLT and the IBBI, never refuse on their own: D19. The text is NFKC-normalised, dotted acronyms collapsed (`R.B.I.`), whitespace collapsed; homoglyphs from other scripts are **not** folded (no confusables table is held). |
| A declared body's **title** named next to held law | `partial` (MIXED) | **D2.** Held law = the held body's title ("Companies Act") in the question, or `provisions` in the request. The held part is read; the unheld part is one `cannot_verify` item, `ref` = the body key, `detail` = `scope.refusal_for` verbatim; **no row is decided and the facts are not applied**, because a row would be Companies Act reasoning applied to a matter the unheld body may govern ("Is our LLP a small company?" is never answered as a company). A bare section number next to a title is that body's section ("section 6 of FEMA"), not held law. |
| A **regulator** named next to held law, including a bare citation | not refused | **D2.** A regulator named next to held law is the held Act's own procedure, not a refusal. A regulator named with **no** held law still refuses as the body the register lists it under ("report to RBI … foreign investor" → FEMA1999), which can be the wrong body ("RBI" in an NBFC-director question → FEMA) — open, recorded in the notice. (Until round 3 this row recorded "NCLT approval to reduce share capital" → IBC2016 as a known false positive; D19 closed it.) |
| Rows or figures, every one decided, nothing not confirmed, every citation rested on | `answered` | **D3.** "Decided" excludes any row carrying `missing_facts`, a `blocked_by`, or state `APPLIES_UNDETERMINED` / `CANNOT_DETERMINE`: those move to `not_confirmed` (kind `cannot_verify`, with the facts they needed) and are not served as rows. |
| Anything else on the general path | `partial` | **D4 (revised).** A `partial` is never empty-handed, and each statement it makes about itself is used **only where it is true**: `NOTHING_DECIDED` only when nothing at all was reached; `TEXT_NO_FACTS` when a provision was read and no facts were supplied; `TEXT_NO_ROW` when facts were supplied and no obligation this engine decides rests on the provision; `LEXICAL` when what is shown came from lexical retrieval; `FACTS_NOT_APPLIED` when facts came with no provision; `UNRESTED` for a named provision no served row or figure rests on. (Before the fix, a turn that had read s.173 said "no admitted provision was reached".) |
| A prescribed figure the table will not serve | `partial`, figure absent | **D5.** The `ThresholdUnavailable` message is carried verbatim as the item's `detail`. The statutory floor is never substituted (`prescribed_thresholds.operative_small_company_limits` says why: ₹50 lakh against ₹4 crore is a wrong answer in the costume of a cautious one). |
| Which rows a turn serves | — | **D6 (revised).** The rows whose `provision` falls under a named citation, compared as (section, subsection path) — s.173 covers s.173(1); s.16 never matches s.186, s.2(41) never s.2(85), and "section 2(85)" finds the s.2(85) row. **Where the request names no provision, no row is decided** and the facts are not applied, echoed or used; the turn says so (`FACTS_NOT_APPLIED`). Serving every row against a free-text question would claim a relevance nobody established. |
| What an `answered` turn cites | — | **D16 (new; by clause since round 3).** Only what its rows and figures **rest on**, compared by clause and not by section — a figure resting on s.2(85)(ii) does not rest on s.2(41): a row rests on its own provision; a figure rests on the Act limb its statutory bounds are keyed to in the threshold table (`small_company.turnover.*` → s.2(85)(ii)). A named provision nothing rests on makes the turn `partial` and is named (`UNRESTED`) — no small-company figure is ever cited under s.186. Figures named with **no** provision are answered on the figures alone, with no `citations`, `evidence_pack` or `law_version`: each figure carries its instrument, in-force date and source, which is its citation, and no word of the question is searched for another. |
| Document turn, `cannot_verify` non-empty | `partial` | **D7.** `confirmed` = the verified rows, `not_confirmed` = `cannot_verify`, `superseded` and `scope_frame` as in §4. |
| Document turn, nothing flagged, something verified | `answered` | **D8.** The verified rows ride as `rows[]`. Unreachable with the register as it stands, so it is exercised on the pure assembler `_document_turn`, not left undefined. |
| Document turn, nothing flagged, nothing verified, something superseded | `partial` | **D9.** One `cannot_verify` item per superseded row, from the row's own fields. |
| Document turn that reached no obligation | `partial` | **D10.** One item, `ask.NOTHING_REACHED`. |
| Any document turn | — | **D11 (corrected).** No `evidence_pack` is served: nothing on the document path is shown as retrieved evidence. `_law_version_at` **does** call `retrieve()` — over the sections the check's rows cite, only to read the corpus-fetched dates the `law_version` statement is built from, at the **document's own date** (red team L2). (The first version of this line said the document path runs no retrieval; that was wrong.) No `facts` block: the document's particulars are the check's own inputs and every row carries them. No `stages`: the orchestrator is the model path and this route never enters it. A document turn that also names an unheld body's title gets its refusal item and is never `answered`. |
| `BUDGET_EXHAUSTED`, a transport failure, an engine failure | **no state at all** | **D12.** `answer()` raises `BadRequest` for a malformed request (the route returns `400`) and lets **everything else propagate**. An engine failure must never reach a client wearing a legal state (CLAUDE.md; the frontend's `AGENTS.md:62`), so there is no `except Exception` on this path and a test asserts the route does not turn one into a `200`. |
| A malformed request | `400` | **D17 (new).** Refused, naming the field: an unknown request or context key; a fact name the engine does not declare (`api.PROFILE_KEYS`, `api.EVIDENCE_KEYS`; `_DOC_CHECK_KEYS` on a document turn) — so `facts.confidence` can never ride into a response; a list or object where one value belongs; any value `api._profile` or `api._evidence` would refuse — a `cin` or `financial_year` that is not a string, a `director_count` that is not a non-negative integer (these were a `TypeError`, i.e. a `500`, on all three fact routes), a money figure in words, an unknown company class, a date that is not a date — **on every path, whether or not the turn applies the facts** (round 3: they were skipped when no provision was named); an empty `facts` object is no facts; a question over **2,000 characters** (a pasted document is a document turn, not a question); a `provisions` item the retriever's grammar cannot read (D21); an empty `parent_turn_id`; a document turn with no date, or with two that disagree. |
| A response that breaks `placedon.ask/0` | `500`, no state | **D18 (new).** The route runs `validate()` on its own response before serving it. A violation is withheld as `{"error": "contract_violation", "violations": […]}` — a server fault a client renders as a service error, never a `200` it could render as a state. |
| Every state | `uses_model: false` | **D13.** No model is called on any path, and the suite asserts the modules import no model or network library. |

**D14 (revised) — which supplied facts the response names back.** Facts are echoed only on a turn
that **applied** them (a provision named, not a MIXED turn), verbatim, labelled `USER_FACT`, minus
`as_of`, `incorporation_date` and `financial_year` — the three fields `_profile()` needs to place
the company in time, which the envelope's `as_of` and each row's own financial year already carry.
Only declared fact names can arrive (D17), so nothing the engine does not know can be echoed.
Nothing is derived, defaulted or added; a fact that was not supplied leaves the row undecided rather
than being invented. *Partly open*: on an AGM-timing turn `incorporation_date` is substantive rather
than frame, and naming it there was not decided here.

**D15 — `demand_signal`.** Emitted (`{"action": "tell_us_blocking"}`) on a **general** `partial`
that both confirmed something and could not confirm something else (an engine gap — not one of the
D4 statements about what this system did not do). **Not decided:** whether it also belongs on the
empty-`confirmed` partial, on a document partial, or on `out_of_scope` — the UX spec shows the
button in all three (§7.12, §7.11) but conditions it on the server supplying the field, and widening
it changes a fixture the prototype is accepted against. Left to ASK-3/ASK-5 with the founder.

### Round 3 (2026-09-19)

**D19 — the Companies Act's own forums never refuse on their own.** `ask_scope.HELD_ACT_FORUMS`
holds the NCLT and the IBBI. The register lists both as IBC2016's regulators, but the NCLT is
constituted by the held Act itself (s.408; corpus section_id 49303, asserted by the test), and a
Companies Act question names it constantly — capital reduction (s.66), schemes (s.230), oppression
(s.241), winding up (s.271), conversion (s.14). Registered valuers under s.247 register with the
IBBI; that rests on the Registered Valuers Rules 2017, which we do **not** hold, and is recorded as
the founder's decision (runbook DEMO PLAN D1), not as a corpus fact. Decided in `ask_scope.py`;
`scope.py`, the authority, is untouched. The IBC still refuses by title ("Insolvency and Bankruptcy
Code"), by acronym ("IBC") and by `TERMS_OF_ART` — "CIRP", "corporate insolvency resolution
process", "resolution professional", "insolvency commencement" — each asserted absent from the
whole held Companies Act text, so none can be the Act's own vocabulary. "Liquidator" and "winding
up" are deliberately not terms of art: the Act uses both.

**D20 — the title the user named decides which refusal they get.** Among several named bodies:
first one named by a title signal no other body shares ("ICDR", "SEBI ICDR", "SAST", "PIT"); then
one whose declared `covers` the question names — single words count here ("buyback"), because this
only chooses between bodies already named and never refuses on its own; only then register order
("SEBI" alone → SEBI_LODR). The register has no separate key for ICDR, SAST, PIT or Buyback: they
share SEBI_OTHER, whose refusal text names all four, so that is the body used. A SEBI regulation the
register does not declare at all still falls to register order and LODR's text — open (notice).

**D21 — one citation grammar.** A provision is read by `legal_retrieval._scan`, the scanner
`retrieve()` itself uses, both to accept it and to match it against a row. `names_a_provision`'s
looser shape check is not used for acceptance: a shape it accepts and the scanner cannot read
("s.9999") is a `400`. (`ask_scope` still uses the looser check for one purpose only — deciding
that a question names held law, which can only suppress a refusal, never cause one.)

**D22 — facts are typed wherever they arrive.** See D17. A turn that does not apply the facts still
refuses malformed ones; an empty `facts` object is treated as none and no turn says facts were
supplied when they were not.

### Round 4 (2026-09-19/21) — narrow the input, and the cases fall out

Three rounds of verification each found a new shape the request accepted, so this round changed
the surface rather than the cases.

**D23 — a `provisions` item is exactly ONE Companies Act citation.** Read whole with the
retriever's own prefix and number grammar (`legal_retrieval._PREFIX`/`_ITEM`): one citation,
optionally qualified by the held Act ("of the Companies Act, 2013"), and nothing else. A second
citation, a range, another Act, a named Rules instrument, a Regulation or a Code is a `400`
saying why — never read as the Companies Act, and never resolved for another instrument (we hold
none of them). A bare rule number ("rule 2(1)(t)") is still read as a rule under the Companies
Act; it can abstain, never answer. This closes the joint-string and other-statute defects at
once: the scanner had kept only the numbers, so "section 2(85) of the LLP Act" became the
Companies Act's s.2(85).

**D24 — one evidence schema, declared once, typed strictly.** `api._EVIDENCE_FIELDS` is the
single table: `EVIDENCE_KEYS` is derived from it, `api._evidence()` builds from it, and
`checker/ask.py` refuses by it, so no field can be read by one route and ignored by another. An
undeclared field, a wrong type or an out-of-range value is a `400` — never a coercion, never a
`500`. Two ranges, and where they come from:
- `calendar_year`: an `int` from **2015** to the last calendar year **ended** by the read date.
  2015 because `checker/as_of.COMMENCEMENT` is 01-04-2014, so calendar 2014 straddles the 1956
  Act; the upper bound because `s173_slice` counts meetings without knowing the date it is read
  on, so a year still running would be reported short of four meetings in September.
- `resident_director_days`: an `int` 0–366 — a financial year runs to 31 March (s.2(41)), so a
  full one has 365 or 366 days; a longer first year is s.149(3)'s proportionate proviso, which
  this engine does not compute.
`/v1/compliance-pack` also refuses an undeclared top-level fact now, as `/v1/document-check`
already did. A false defect on that route would break CLAUDE.md's rule about calling a finding a
defect when it is not one, which is exactly what the untyped `calendar_year` produced.

**D25 — what a turn says about its own retrieval is true of that turn.** With no provision named,
a word-matched turn carries `LEXICAL`; a turn whose question carried its own citation carries
`QUESTION_CITED`, which says the citation was read **as a Companies Act section**, not
necessarily the Act the question meant.

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
obtain; after either, run `python3 scripts/assistant_contract.py --write`. (ASK-1 and its fix round
changed neither: all six fixtures rebuild byte-identically through `answer()`.)

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
