# Placedon build roadmap — the plan, synthesized

Written 2026-09-04 from a four-agent parallel decomposition (ingestion, retrieval,
deciders, product/validation). This is the single authoritative "what we build and
in what order." It is deliberately short on vision (see
`docs/BLOOMBERG_FOR_INDIA_ANALYSIS.md`) and long on sequence, dependencies, and the
gates that need a human or a contract.

## Thesis in one line

A deterministic, source-grounded engine that states a company's Companies Act
position — every line cited, dated, and refusing when unsure — fused with live
corporate-entity data through **licensed** feeds, not scrapers. The moat is the
verification discipline, not the diagram.

## Where we already are (do not rebuild)

Retrieval (BM25 within-section 0.62, cross-section 0.73/recall@5 0.93), the E3→E6
entailment gate, the entity graph, the licensed corporate-data seam
(`corporate_data.py`), 8 periodic obligations + the s.185/186/188 transaction
deciders, currency tracking, and the cited evidence pack — all built, tested, green.
The blueprint's "hard half" exists. What remains is (1) proving it with a
practitioner, (2) widening coverage without guessing, (3) making the data live
legally, (4) raising retrieval accuracy only where measured necessary.

---

## THE CRITICAL PATH (everything bends around this)

```
  P1  Shareable assurance memo   ─┐
  P2  Minimal demo surface        ├──►  P0  ONE CS REVIEWS A REAL PACK  ──►  everything downstream
  (both already ~90% built)      ─┘        (BLOCKING — the only gate that matters)
```

`P0` is the whole game. Until one practising Company Secretary reacts to a *real
generated pack* (not slides), every further track below is a guess about what
practitioners need. The product workstream is explicit: sequence is **P1 → P2 →
P0**, and P0 is the sole success criterion for this phase.

- **P1 — Shareable memo.** Render `diligence_pack.py` as a standalone, printable
  memo (HTML/PDF): company + date + scope, the five-state discipline legible, the
  currency-watch banner, sub-clause citations with hashes, and the explicit "a
  record, not an instrument; not legal advice; no lawyer has validated this"
  boundary. *Acceptance:* a reader who has never seen the tool understands what it
  asserts, what it does not, and where every claim comes from. Hold the line —
  assurance memo, never a signable resolution.
- **P2 — Demo surface.** Extend `serve_matrix.py`: one input (company + its
  transactions) → the P1 artifact, in under two minutes, no auth. Keep it ugly and
  working.
- **P0 — The review (human, founder).** Founder books and runs one CS session on a
  real pack; capture via `record_interview.py` on three axes: would you put your
  name near this as pre-diligence evidence? is any citation/currency claim wrong?
  what's the one thing that makes it untrustworthy? *Warm 3–4 leads in parallel;
  lead with the artifact, not a pitch.* This is the founder's step; no proxy.

**Nothing in the tracks below should be built ahead of P0 except what P0 needs.**

---

## POST-VALIDATION TRACKS (parallel, re-prioritised by what the CS says)

### Track D — Deciders (widen coverage, never guess)
Order chosen to close the open gap first, then reuse existing machinery before
anything needing new corpus.
- **D1. Close s.188's members'-approval threshold.** Acquire + *human-review* Rule
  15 (Board Meetings Rules — held but UNREVIEWED; a reviewer sets the operative
  boundary), wire into `s188.py` so `NEEDS_MEMBER_APPROVAL_UNDETERMINED` resolves.
  Regression-test both branches (withheld still refuses, names `S-188-RULES`).
- **D2. Disclosure & class-office duties.** `s184.py` (director interest — pure
  entity-graph, no threshold), then `s203.py` (KMP) and `s177.py` (audit committee),
  both gated on prescribed-class thresholds (the G.S.R. 700(E) pattern). Each must
  return `DOES_NOT_APPLY` below-class but `CANNOT_DETERMINE` when the threshold rule
  is unacquired — the two never collapse.
- **D3. `s180.py`** board-power restrictions (special-resolution gate; UNDETERMINED
  when the limit fact is absent).
- **D4. `s62`/`s42`** share-issue procedures (scope to attachment + gross breach,
  not full workflow).
- **D5. `s90` SBO** — ship refuse-only until the BEN/SBO rules are acquired+reviewed.
- *Cross-cutting:* every new decider registers in `obligations.py`, threads the
  E-gate + `obligation_citations.py`, surfaces in the pack; the self-test that "no
  row asserts compliance without facts" extends per id.

### Track I — Ingestion & data (make it live, legally)
- **I1. Generalise acquisition** beyond 700(E): `scripts/acquire_instrument.py`
  (human browser download → hash → attest → `acquisition_log`), keyed by instrument
  id; store the instrument's *own* effective date (never "as consolidated today" —
  the retracted mistake).
- **I2. Wire acquired instruments into `currency.py`** (CURRENT / NOT-IN-FORCE /
  SUPERSEDED / UNACQUIRED); dated human review cadence per instrument (no
  auto-discovery).
- **I3. Licensed MCA21 adapter** — `checker/providers/mca_aggregator_adapter.py`
  implementing the existing `LicensedAggregatorProvider` against one contracted,
  MCA-sanctioned aggregator → `CorporateRecord` → entity graph. **BLOCKED on a
  signed licence.** No adapter ships live until it exists; no WAF/robots bypass ever.
- **I4. Case-law adjacency** — `checker/caselaw_ik.py` via Indian Kanoon under its
  attribution terms; stored as clearly-labelled *secondary* evidence that can only
  raise POTENTIAL_ISSUE/INFORMATIONAL, never an APPLICABLE_DEFECT. **BLOCKED on
  confirmed IK terms.**

### Track R — Retrieval accuracy (only where measured)
- **R1. Expand the eval** to 120–150 cross-section queries with a *frozen 70/30
  held-out split*; every label a structural anchor with provenance.
- **R2. Re-measure the BM25 ceiling** on the bigger set; bucket failures
  (lexical-mismatch / structural-ambiguity / tokenization). Expect the number to
  drop — honest signal.
- **R3. Embedding decision gate (Decision B).** Justified only if ≥15% of failures
  are lexical-mismatch a cheap fix can't recover AND an offline probe lifts recall@5
  on those by ≥8 absolute points on held-out. Else stay zero-dependency.
- **R4. Embeddings + RRF** (`k≈60`), BM25 as fallback, only if R3 passes; accept
  only on ≥+5 recall@5 held-out, non-regressing p@1, verified graceful degradation.
- **R5. Gate subordination test** — inject a plausible-but-wrong retrieved span;
  confirm the E-gate rejects it. Retrieval rank is never a citation. Never co-tune
  retrieval and the gate.

---

## Phasing

| Phase | Contains | Gate to exit |
|---|---|---|
| **Now** | P1, P2 | a real pack is shareable + producible live |
| **Validation (blocking)** | P0 | one CS review captured on the three axes |
| **Phase 2** (reordered by P0) | D1, D2; I1, I2; R1, R2 | s.188 determinate; instruments current; true BM25 baseline |
| **Phase 3** | I3 (on licence), I4 (on terms); D3–D5; R3–R5 | live corporate data in the graph; coverage widened; embeddings iff justified |

## The discipline lines (non-negotiable, every track)
- **Licensed access, never scraping** (MCA21 via contracted aggregator; case law via
  Indian Kanoon attribution; statute via human browser acquisition).
- **A model never decides or cites** — it proposes; the E-gate disposes; a human
  attests thresholds. No "zero-human LLM labeling as truth."
- **Refuse on unacquired rules; keep DOES_NOT_APPLY and CANNOT_DETERMINE distinct.**
- **Assurance memo, never an operative instrument.**
- **No new dependency without a measured reason** (the R-track gates the only
  candidate — embeddings).

## The immediate next move
Build **P1** (the shareable assurance memo) now — it needs no human, no contract,
no dependency, and it is the thing that makes **P0** possible. Everything else waits
on the CS the memo unlocks.
