# "Bloomberg Law for India" — deep analysis, grounded in what Placedon already is

Written 2026-09-04 in response to a vision: fuse a Harvey-style generative legal
AI with a "God's Eye" live-data engine to build an Indian Bloomberg-Law equivalent.
This is the honest analysis — what is genuinely valuable, what Placedon already
has, and the three lines the pasted blueprint crosses that this project must not.

## 0. The one-line verdict

The *kernel* is right and, remarkably, **Placedon has already built the hard,
defensible half of it**. But the pasted blueprint's ingestion strategy (scrape
SCC/Manupatra/e-Courts/MCA21), its labeling strategy (zero-human LLM auto-labeling
as ground truth), and its interface fantasy (a 3D vessel-tracking globe for
Companies Act work) each violate either the law, this project's discipline, or its
scope. Keep the kernel; reject those three; and the result is buildable and honest.

## 1. The real kernel, stated plainly

Strip the cinematics and "Bloomberg for Indian corporate law" means one thing:

> **Fuse live corporate-entity data with source-grounded legal analysis, so a
> lawyer sees a company's legal position and its real-world context in one view,
> with every claim traceable to a primary source.**

That is a real, valuable, under-served thing. It is also *exactly the axis Placedon
already competes on* — deterministic, source-grounded, entity-aware — which is why
so much of the "architecture" the blueprint describes is already in this repo.

## 2. What Placedon ALREADY has that IS this architecture

The blueprint presents a 4-phase pipeline as if it were greenfield. Map it to the
codebase and most of the load-bearing parts exist:

| Blueprint layer | Placedon component (already built) |
|---|---|
| "Corporate Entity Graph / Entity Resolution (Step 2)" | `checker/entity_graph.py` — typed, dated, directed relationships; tri-state (absence ≠ denial) |
| "Hybrid RAG: BM25 + dense with RRF" | `checker/chunk_retrieval.py` + `corpus_retrieval.py` — BM25 shipped (0.62 within-section, 0.73/0.93 cross-section); the dense half is the deferred, *measured-against-an-eval* embedding decision |
| "Parent-child chunking for statutory context" | `checker/structural_chunk.py` — chunks on the statute's OWN units (section→sub-section→proviso→limb), stronger than length-based parent-child |
| "Never hallucinate a citation; strict source-attribution" | the whole thesis: `checker/cascade.py` (E3→E6 entailment gate), `ground_span.py` — a claim must be *entailed by* a retrieved span or it is NOT_ESTABLISHED |
| "Regulatory/currency tracking" | `checker/currency.py` — obligation-level "is the law current" (the Legora-Monitors analogue) |
| "Declarative rules engine (s.185/186/188 limits & math)" | `checker/s185.py`, `s186.py`, `s188.py` — grounded, abstention-first deciders on the entity graph |
| "The verified memo output" | `checker/diligence_pack.py` — the dated, cited, gap-explicit evidence pack |

The point the blueprint misses: **the hard part isn't the pipeline diagram, it's
the verification discipline underneath it, and that is the part that already
exists.** A competitor can draw this diagram in an afternoon; they cannot cheaply
retrofit "the model may propose, the system must verify, the reviewer decides."

## 3. The three lines the blueprint crosses — and must not

### 3.1 Scraping prohibited sources (the fatal one)

The blueprint says, in its own words, "building this requires bypassing them
entirely," and proposes Playwright scrapers with proxy rotation against e-Courts,
and "target public endpoints and structured aggregators" for MCA21.

`CLAUDE.md` is unambiguous: *"Do not bypass the MCA WAF, robots restrictions,
access controls, or source terms. Permitted sources only: official legislation,
Gazette, public ICSI specimens, public listed-company disclosures, Indian Kanoon
under its attribution terms."* This session already proved the discipline is real:
G.S.R. 700(E) was acquired through a **browser a human directs**, not a crawler,
precisely because the compliant fetcher fails closed on a blocked robots file.

The legal path to the same data is **licensed access, not scraping**:
- **Corporate data** → the authorised MCA21 API aggregators the blueprint itself
  names (Surepass, FileSure, and peers) operate under MCA-sanctioned access. That
  is a commercial/contractual step, not a scraping pipeline.
- **Litigation** → **Indian Kanoon under its attribution terms** (already permitted
  here) and the official e-Courts services, not proxy-rotated scrapers.
- **Statute/Gazette** → India Code / the Gazette, the browser-download path already
  built (`scripts/register_gsr700e.py`).

This is not a limitation to route around; it is the moat. A platform that scrapes
prohibited sources is one cease-and-desist from zero, and cannot be sold to a CFO
who is buying *risk reduction*.

### 3.2 "Zero-human labeling with local LLMs" as ground truth

The blueprint proposes running local models to auto-label case treatment
("overruled / distinguished / followed") and entity links, and treating that as the
knowledge graph. This is the **exact hallucination trap Placedon exists to refuse**.
`checker/model_adapter.py`'s first rule: a model's own recollection is *not evidence*.
An auto-labeled "this case overruled that one," unverified, is a confident guess in
a domain where a wrong "still good law" gets a client sanctioned.

The disciplined version: a model may *propose* a label; it is not truth until it
passes a deterministic check or a human review. That is the `reviews.py` /
benchmark-freeze pattern already built. Labeling can be *model-assisted*, never
*model-authoritative*.

### 3.3 The "God's Eye" 3D globe / vessel tracking — scope creep in a costume

Live AIS ship-tracking and a photorealistic globe are genuinely useful for a
*specific* practice: maritime, sanctions (OFAC), and trade law. They are close to
irrelevant to the **Companies Act corporate-compliance** wedge Placedon chose.
Bolting a globe onto a compliance engine is the same mistake dropping DPDP/PoSH
avoided — breadth that dilutes the wedge. Live *telemetry* that matters for
Placedon is not ships and planes; it is **Gazette amendments, MCA filings, and
regulatory circulars**. If the spatial product is wanted, it is a *separate bet*
with a separate buyer, not a feature of this one.

## 4. The disciplined architecture: "Bloomberg for Indian corporate law, our way"

Same ambition, legal and verifiable. Five layers; three of them already exist.

```
 L1  SOURCED INGESTION  (legal only)
     • Statute + Gazette: India Code / eGazette, human-browser acquisition + hash + attest   [BUILT: register_gsr700e, acquisition_log]
     • Corporate registry: LICENSED MCA21 aggregator API (CIN, DIN, charges, filings)         [NEW: contractual, then an ingest adapter]
     • Case law: Indian Kanoon under attribution terms                                         [NEW: adapter, permitted]
                                   │
 L2  ENTITY RESOLUTION GRAPH
     • CIN/DIN as identity; company↔director↔subsidiary↔RPT edges; tri-state                   [BUILT: entity_graph.py — extend with CIN/DIN ids]
                                   │
 L3  HYBRID RETRIEVAL
     • BM25 (shipped) ⊕ dense embeddings (deferred, measured); RRF fusion                      [BUILT: chunk/corpus_retrieval; embed = decision B]
                                   │
 L4  DETERMINISTIC VERIFICATION + DECIDERS
     • E3→E6 entailment gate; obligation register; s.185/186/188; currency                     [BUILT]
                                   │
 L5  OUTPUT
     • The verified, cited, gap-explicit memo (NOT operative documents)                        [BUILT: diligence_pack — render as a shareable artifact]
```

Only **L1 (licensed corporate/case-law feeds)** and **the dense half of L3** are
genuinely new engineering, and the dense half is already a made, measured decision
(deferred until BM25's 0.62/0.93 is shown insufficient). The rest is hardening what
exists.

## 5. Model orchestration (the "agents"), mapped to discipline

The blueprint's "Harvey-style agents" become, in Placedon's terms, a pipeline where
**most stages consult no model**:

1. **Applicability (deterministic)** — which sections/obligations attach to this
   company, from facts. No model. `obligations.py` / `applicability.py`.
2. **Retrieve (deterministic)** — hybrid BM25(+dense) to the governing spans.
3. **Extract (model, cheap, verified)** — pull a fact from a filing/PDF; the
   deterministic layer verifies it. Model proposes, system checks.
4. **Verify (deterministic)** — E3→E6; a proposed claim must be entailed or it is
   NOT_ESTABLISHED.
5. **Decide (deterministic)** — the deciders + entity graph.
6. **Narrate (model, gated)** — user-facing prose, every sentence tied to a verified
   span; never the source of a legal conclusion.

This is the Harvey "dozens of subagents" shape with the crucial inversion the
blueprint omits: the model is the *narrator and extractor*, never the *decider or
the citation*. That inversion is the product.

## 6. The staged plan (with the validation gate first, not last)

- **Stage 0 — validate the existing slice (BLOCKING).** One practising CS reacts to
  the current evidence pack (the eight obligations + s.185/186/188 + currency). This
  outranks every layer above. Building L1 before a practitioner confirms L4/L5 are
  right is the "grand architecture on an unvalidated core" failure the strategy
  reviews warn about.
- **Stage 1 — corporate-data ingestion (legal).** Contract a licensed MCA21
  aggregator; build an ingest adapter that maps CIN/DIN into the entity graph. This
  is what turns the graph from hand-entered to *live* — the real "Bloomberg" fusion,
  minus scraping.
- **Stage 2 — dense retrieval, IF measured necessary.** Revisit decision B against
  the eval; add embeddings + RRF only if BM25's numbers prove insufficient in real
  use.
- **Stage 3 — case-law adjacency (Indian Kanoon, attribution).** Litigation-exposure
  as a *linked* signal on an entity, source-attributed — not predictive judicial
  analytics (legally fraught, and not the compliance wedge).
- **Stage 4 — (separate bet) spatial layer.** Only if a maritime/sanctions buyer is
  pursued. Not part of the Companies Act product.

## 7. The reality check the vision needs

Everything above is buildable and honest. But the single largest risk is not
technical — it is that this analysis becomes the thirteenth strategy document while
one practitioner has still not reacted to what exists. The blueprint's own authors
(the three-agent reviews) said it in plain words: *test with a working artifact,
not slides.* The most "Bloomberg" thing to do next is not to draw a bigger diagram;
it is to put the verified memo this engine *already produces* in front of one
Company Secretary and let them tell us where it is wrong. The architecture here is
the map for after that conversation, not instead of it.
