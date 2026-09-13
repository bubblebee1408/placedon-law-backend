# PLAN 10 — The pasted stack, checked against what exists

**Date:** 2026-09-13 · **Status:** analysis + one module built · **nothing committed pending approval**

The pasted plan proposes a stack (Sonnet + Haiku, voyage-law-2, pgvector, Indian Kanoon)
and a replacement `CLAUDE.md` for an **Indian criminal-law research and drafting**
product. This document checks every rule in it against the code that exists, flags what
cannot be verified, and names the one decision only you can make.

---

## 0. The Harvey citation — OPEN, and my earlier wording was too strong

The pasted research cites a Harvey engineering post (3 Nov 2025) on Tool Bundles and
leave-one-out eval gates.

**History.** On 10 Sep 2026, commit `ebc6f4c`, I retracted my own attribution of the
leave-one-out gate to Harvey: I had taken it from secondary write-ups and stated it as
fact, and an agent search did not find the post. `checker/bundles.py` now grades the
attribution SECONDARY.

**What I got wrong in the first draft of this document.** I escalated that to
"CONTRADICTED — we searched for it and found nothing." *Could not verify* and *does not
exist* are different claims and I wrote the stronger one. The repo rule is explicit:
**if evidence is incomplete, write OPEN or UNVERIFIED. Do not guess.**

**What this session actually established** (13 Sep 2026):

| Attempt | Result |
|---|---|
| `harvey.ai/blog`, fetched directly | Loads. Lists Sep 2026 back through Aug 2026 — **paginated, so a Nov 2025 post would not appear here anyway.** Not evidence either way |
| `harvey.ai/blog/tool-bundles` | 404 — but **I invented that slug**, so this proves nothing |
| A guessed ZenML LLMOps-database URL | 404 — same problem, same worthlessness |
| Web search | **Budget exhausted for this session** (200/200) |

**Status: OPEN.** A reader reports finding the post at harvey.ai dated 3 Nov 2025 with
named authors and independent corroboration in ZenML's LLMOps database. I could not
reach it, and I could not disprove it. Two explanations remain live: the post exists and
both my searches missed it, or the corroboration chain traces back to the same secondary
material. **Resolving it needs one person opening harvey.ai's Nov 2025 archive.**

**What does not change either way:** grading the attribution SECONDARY is correct, and
treating every claim in the pasted research as a claim is correct. The architecture does
not rest on it — `bundles.py` justifies the leave-one-out gate from ToolEmu (23.9%),
Gorilla, CAR-bench and Large Legal Fictions, none of which is Harvey.

## 1. What already exists

The machinery is largely built. The domain and the data are not.

### Golden rules (pasted §2)

| Rule | Status | Where |
|---|---|---|
| No uncited legal claim ships; abstain instead | **BUILT** | `reasoning.py` (7 violations incl. `CITATION_OUTSIDE_PACK`, `CONCLUSION_ASSERTED`), `ground_span.py`, `claim_verifier.py` |
| Grounded ≠ good law — in force, not superseded | **BUILT, and it is our strongest asset** | `currency.py`, `staleness.py`, `as_of.py`, `commencement.py`, `interval.py`, supersession chains |
| Retrieved text is DATA, never instructions | **PARTIAL** | `model_adapter.py` only. No `<source>` delimiter discipline in the prompt path |
| Pinpoint spans, never whole documents | **BUILT** | `structural_chunk.py`, `witness_span.py`, `span_inventory.py`, `chunk_retrieval.py` |
| Fail loud | **BUILT** | API 400s on typo'd keys, `session.py`, the silent-failure fixes |
| Attribution — "Powered by IKanoon" | **BUILT** | `attribution.py`, `licence.py`; CLAUDE.md already binds us to IK's terms |
| Never call output legal advice | **BUILT** | `docs/NON_GOALS.md` |

### Retrieval (pasted §4)

| Rule | Status | Where |
|---|---|---|
| Hybrid BM25 + dense, fused | **BUILT** | `lexical_rank.py`, `dense_index.py`, `fusion.py`, `chunk_fusion.py`, `reranker.py` |
| Contextual chunks with section-path metadata | **BUILT** | `structural_chunk.py`, `structural_index.py` |
| Scoped corpus, not bulk-embedded | **BUILT** | `scope.py` — nine bodies, one held, the rest actively refused |
| Statute-map expansion (`ipc_bns_map`) | **NOT BUILT — and the proposed shape is wrong.** See §3 | — |

### Validation (pasted §5)

| Step | Status | Where |
|---|---|---|
| 1. Deterministic — quoted span literally appears | **BUILT** | `ground_span.py`, `witness_span.py`, `document_extract.py` |
| 2a. Currency — **statute** in force | **BUILT** | the whole currency stack |
| 2b. Currency — **judgment** not overruled | **NOT BUILT** | no citation-treatment model exists |
| 3. LLM — on point, and *ratio* not *obiter* | **PARTIAL** | `entail_binding.py` does quantity→obligation binding, which is the same shape but not the same question |
| Bounded correction, then abstain | **PARTIAL** | abstention exists across ~10 modules; no bounded redraft loop |

### Orchestration and eval

| Item | Status |
|---|---|
| Single tool-calling loop, `MAX_ITERS`, 3 tools | **NOT BUILT** — we have `router.py` (facts, not a manager agent) and `bundles.py` (5 capabilities, leave-one-out) |
| Citation precision / hallucination rate measured | **HARNESS BUILT, metrics not these two** — `pit_bench.py` scores four outcomes incl. `WRONG_REFUSAL`; `shadow.py` gates on `LEAKED == 0` |
| IL-TUR wired | **NOT BUILT** |
| Gold fact-situation set | **NOT BUILT** |
| Indian Kanoon API client | **NOT BUILT** — IK used only for amending-Act corroboration (`docs/CORROBORATION.md`) |
| voyage-law-2 / pgvector | **NOT BUILT** — `dense_index.py` is in-process |

**Score: 12 built, 4 partial, 8 not built.** Everything in the "not built" column is
either data or criminal-law domain.

---

## 2. Claims I could not verify — check these before spending on them

Repo rule: *no unsupported product, market, legal, or competitor claims.* Applying it to
the pasted material.

| Claim | Status | Why it matters |
|---|---|---|
| **Indian Kanoon: ₹10,000/month free for non-commercial, after use-case verification** | **UNVERIFIED — verify first** | The plan says *"It's likely your entire data budget, free."* The whole data strategy rests on this one line. If it is wrong or if approval is slow, Phase 1 has no corpus |
| IK ₹500 free dev credit on signup | UNVERIFIED | Smaller, same class |
| `indian-kanoon-mcp` pip package (FastMCP) | UNVERIFIED | Described as "close to a cheat code" — worth 10 minutes to confirm it exists and is maintained |
| voyage-law-2 "84.4 vs 68.4 NDCG@10" vs OpenAI | **VENDOR-REPORTED** | Voyage's own benchmark on its own model. Directionally plausible, not independent |
| voyage-law-2 "~1 trillion legal tokens", "explicitly covers Indian jurisdiction" | UNVERIFIED | Vendor copy |
| `voyage-context-3`, `rerank-2.5-lite` | UNVERIFIED (plausible) | Pin exact model IDs before writing them into config |
| Harvey Nov 2025 Tool Bundles post | **OPEN — see §0** | Reported found with corroboration; I could not reach it and could not disprove it. Nothing rests on it |
| 2026 arXiv: "Domain-Partitioned Hybrid RAG", "Falkor-IRAC" | UNVERIFIED | Cited as the hallucination-control design source |
| IL-TUR (ACL 2024), ILDC (2021), InLegalBERT (2023), Saptarshi Ghosh / IIT KGP | **Consistent with what I know** | These I would expect to hold up |

Nine of thirteen sourcing claims are unverified and one is open. That is not a reason to
reject the plan. It is a reason to treat each as a claim — and the IK line below turned
out to need exactly that treatment.

**Update, same day.** The Indian Kanoon ₹10,000/month non-commercial tier **is real** —
it is on IK's own pricing page. What is not confirmable by any search is **approval**,
which IK grants case by case. So: real tier, unconfirmed approval. The original framing
("likely your entire data budget, free") was a notch too confident, and the correction
came from the reader, not from me.

---

## 3. The one place the plan is technically wrong

> `/data/ipc_bns_map/` — "expand the query through the `ipc_bns_map` table so new-code
> queries also reach old-code precedent."

The retrieval goal is right. **A flat table is the wrong structure**, and the bug it
produces is this repository's founding bug in reverse.

A table says `IPC 302 → BNS 103`. Ask about a killing in **2023** and it hands you
BNS 103. The Bharatiya Nyaya Sanhita came into force **1 July 2024**; an offence before
that date is prosecuted under the IPC. That is serving law that did not exist when the
act was done — the same class of error as serving ₹4 crore after G.S.R. 880(E) moved it.

And a single table cannot express the distinction that actually decides these matters:

| Code | Anchored on |
|---|---|
| **BNS** (substantive offences) | the **date of the offence** |
| **BNSS** (procedure) | the **date proceedings commenced** |

A 2023 offence charged in 2025 is **an IPC offence tried under BNSS procedure**. One
matter, two codes, two anchors. Any interface showing one code per matter shows half the
answer, and a litigator spots it immediately.

**Built: `checker/code_transition.py`** — 20 checks, green. It models the transition as a
dated supersession, refuses without the anchor date rather than substituting today,
escalates conduct that straddles commencement instead of rounding it, and returns
`INSTRUMENT_NOT_HELD` for every row because we hold none of these codes. The date
arithmetic is real and tested; the legal anchors are `DECLARED` and each names the
provision that would settle it.

```
[ok] a 2023 killing is an IPC matter, not BNS 103 — which is what a flat map would return
[ok] one matter, two codes: a 2023 offence charged in 2025 is IPC substance under BNSS procedure
[ok] with no offence date it refuses rather than assuming today
[ok] conduct spanning commencement is escalated, not resolved by rounding
[ok] Bharatiya Nyaya Sanhita: not servable — 4 instrument(s) to acquire
```

This is also the honest answer to *"how do we beat generic ChatGPT on one workflow"*:
ChatGPT will cheerfully give you BNS 103 for a 2019 offence. Refusing to, and saying
why, is a demonstrable difference in the first sixty seconds of a demo.

---

## 4. Where the plan and the existing product diverge

This is the decision, and it is yours.

|  | What exists | What the pasted plan builds |
|---|---|---|
| Body of law | Companies Act 2013 (527 sections, hash-stamped) | BNS / BNSS / BSA |
| Task | audit an existing document | research + draft a new note |
| User | corporate lawyer, in-house | litigator, HC/SC |
| Buyer named | Lafarge ACS legal | law-college clinic / advocates |
| Evidence asset | supersession chains, temporal proof, corroboration | judgments with pinpoint paragraphs |

**~70% of the machinery transfers. ~0% of the domain does.** The corpus, the obligations
register, the 15-row matrix, the MCA strip, prescribed thresholds — none of it serves a
BNS research tool.

And there is an asymmetry worth naming: **the plan treats "statute in force, judgment not
overruled" as one bullet (§5.2). That bullet is the entire product built here so far** —
and on BNS it is nearly free, because BNS is fourteen months old and has almost no
amendment history. Our hardest-won asset contributes least exactly where the plan puts it.

The exception is §3: the IPC→BNS transition *is* a supersession problem, and it is the
one place the existing machinery is directly, unusually valuable.

---

## 5. What I would adopt regardless of the decision

Five things in the plan are right and cost nothing to take:

1. **Single vendor for reasoning.** Sonnet + Haiku. Already our tiering.
   **One amendment:** keep Gemini Flash for page images only. It is free, it wins on
   Devanagari, and at ₹2,000 the free OCR tier is not bloat — it is the budget.
   `router.py` already routes `PAGE_IMAGE → Gemini`, everything else Anthropic.
2. **No LangGraph, no CrewAI, no fine-tuning.** Agreed, and already how this is built.
3. **Measurement is the exit bar, not good numbers.** Exactly right, and already the
   discipline (`shadow.py` gates on `LEAKED == 0`; `pit_bench` scores refusals as costs).
4. **Wrap retrieved text in `<source>` and treat it as data.** A real gap here —
   `model_adapter.py` is the only place that touches it.
5. **A bounded correction loop, then abstain.** We abstain; we do not bound-and-retry.

---

## 6. The decision, recorded

**Taken 13 Sep 2026. This section is the authority; §7 is the reasoning that produced it.**

1. **Stay on corporate compliance.** No pivot. No criminal law as a second practice area.
   `checker/scope.py` remains the register and is unchanged.
2. **Keep `code_transition.py`.** It is machinery, it is correct, and it is the bridge if
   criminal law is ever added. It serves no obligation today and is wired to nothing —
   which is why keeping it costs nothing.
3. **Do not execute the Phase 1 criminal build.** No Indian Kanoon ingestion spine, no
   voyage-law-2, no pgvector, no IL-TUR harness.
4. **Apply for the IK non-commercial tier anyway.** The tier is real; approval is
   case-by-case and unconfirmable by search. It is no longer a single point of failure,
   because a compliance product is statute-, rule- and MCA-driven rather than case-law
   driven — the IK dependency shrinks to what it already is: corroborating amending Acts.
5. **The next move is the Lafarge/ACS conversation, not a commit.**

### The argument that decided it

The currency engine is worth **most** on compliance and **least** on criminal law. BNS is
fourteen months old with almost no amendment or overruling history, so the hardest-built
asset in this repository would do nothing there. Meanwhile "3–5 on-point judgments with
pinpoint cites" is already sold by Indian Kanoon, Manupatra and SCC Online to a market
that already pays for it.

Pivoting would mean discarding the edge in order to enter a commodity market.

*"Your board resolution rests on a threshold that moved in December 2025"* is a sentence
nobody else sells. It is the only place the currency engine is worth money, and it is
where we already are.

And the Lafarge conversation is not a fourth consideration — it is the deciding one. It
is the **only asset touching market risk**, which the three-role panel identified as now
being the entire risk. A pivot resets it to zero. Its existence alone is sufficient
reason not to pivot.

---

## 7. The five lessons, adopted

Taken from the pasted plan regardless of the scope decision, and now binding:

| # | Lesson | Status here |
|---|---|---|
| 1 | Single vendor for reasoning — Sonnet + Haiku | Already `router.py`. **One amendment: keep Gemini Flash for `PAGE_IMAGE` only.** It is free, it wins on Devanagari, and at ₹2,000 a free OCR tier is the budget, not bloat |
| 2 | No LangGraph, no CrewAI, no fine-tuning | Already how this is built. `docs/NON_GOALS.md` |
| 3 | Measurement is the exit bar — not good numbers | Already the discipline: `shadow.py` gates on `LEAKED == 0`, `pit_bench.py` scores refusals as costs |
| 4 | Wrap retrieved text in `<source>`; treat it as data, never instructions | **DONE 13-09-2026**, and the baseline stated here was wrong — see below |
| 5 | Bounded correction loop, then abstain | **PARTIAL.** We abstain across ~10 modules; we do not bound-and-retry |

Lesson 5 is the only one still needing code, and it does not block the meeting.

### Correction to lesson 4's baseline

This table originally said `model_adapter.py` was "the only place that honours this".
**That was false and I wrote it.** A grep for `injection|untrusted` matched a comment in
that file about *model output* being untrusted — a different thing — and I reported the
hit without reading the match. The real baseline was **zero of five** entry points
hardened, not one. Same error shape as the Harvey overstatement in §0: *a hit is not a
reading*.

Closed in `d700328` and `2f14d49`. The design principle that came out of it is not the
one the brief proposed:

> **The clause is universal; the delimiter is only for raw-string entry.**

Wrapping the Anthropic extract path would have shifted the `char_location` offsets that
span grounding rests on — no crash, just drift in the layer that makes "one ungrounded
field poisons the record" true. `checker/anthropic_model.py` now demonstrates that
exemption rather than asserting it: a real offset applied to a wrapped copy lands on
`'nt\nThe C'` instead of `'1,00,000'`.

Two things are logged rather than fixed, both in CLAUDE.md: **image-borne injection**
(uncloseable by any string guard — Gemini reads pixels) and **E6 training-data
poisoning** (`annotation.to_sft()`, dormant under the no-fine-tuning decision).

---

## 8. What this document is not

It is not a plan to build anything new. The engineering is ahead of the market evidence,
and the correct next action is a conversation. This file exists so that when the pivot
question is asked again — and it will be — the reasoning is on the record rather than
being re-derived from memory.
