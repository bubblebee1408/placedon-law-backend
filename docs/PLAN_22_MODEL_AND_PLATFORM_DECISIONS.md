# PLAN_22 — model and platform decisions

Written 2026-09-29, from the founder's architecture review. Status vocabulary is
[PLAN_00_INDEX](PLAN_00_INDEX.md)'s: **BUILT · MEASURED · SOURCED · INFERRED ·
UNVERIFIED · BLOCKED**.

> **Provenance.** The competitor findings below were gathered in the founder's review and
> are recorded here as supplied. **This repository has not independently replicated any of
> them.** Where a number comes from the company selling the thing it measures, it is marked
> **UNVERIFIED (vendor-reported)** and must be cited that way everywhere — a vendor figure
> repeated without its label becomes, three documents later, a fact we appear to have
> measured. The decisions in §4 do not depend on any vendor number being true.

**Read this before any model, retrieval, OCR, API or MCP work.**

---

## 1. Goal

Placedon is a Harvey-style legal AI for Indian **in-house legal teams**, on Indian
corporate law, built on the verification engine that already exists here. Later: law
firms, then individual lawyers. **Themis** (graph / events / watch) is the premium tier.

This is the buyer already recorded in [PLAN_20_INHOUSE_CORPORATE](PLAN_20_INHOUSE_CORPORATE.md);
PLAN_22 adds only the model and platform layer beneath it.

## 2. What Harvey runs (verified September 2026)

| Layer | What it is | Evidence class |
|---|---|---|
| Retrieval | Voyage AI **custom** embedding `voyage-law-2-harvey`, fine-tuned on **20B+ tokens of US case law** | SOURCED (Voyage blog, 2024) |
| Retrieval gain | **~25% fewer irrelevant top results** | **UNVERIFIED (vendor-reported** — Voyage blog, 2024, measuring its own model) |
| Generation, historically | OpenAI + Anthropic hosted models | SOURCED |
| Generation, Aug 2026 | **"Harvey Tenet"** — Kimi K3 post-trained with Fireworks via RL, **~150 B300 GPUs, 2 months** | SOURCED |
| Tenet gain | **~2x tasks** on Harvey's **own** Legal Agent Benchmark | **UNVERIFIED (vendor-reported, not independent** — Harvey's benchmark, Harvey's model) |
| Surfaces | REST API (completion, Vault); **hosted MCP server at `api.harvey.ai/hosted_mcp/mcp` with OAuth**; DMS connectors | SOURCED |

**The lesson, and it is the reason this section exists:** Harvey's edge is **not the
model** — they switched models, twice. It is **retrieval, workflows, and expert-labelled
data**. A plan that answers Harvey by training a model is answering the wrong half.

### 2.1 Claims that are NOT verified and must never be repeated

Two figures circulated in earlier discussion and are **false or unsourced**. They are
recorded here so that finding them in an old note is enough to reject them:

- ~~"GPT-6 Astra"~~ — **no such model is verified.** Do not name it.
- ~~"fine-tuned GPT-4 on 10B tokens"~~ — **unverified.** The sourced figure is Voyage's
  *embedding* model on 20B+ tokens of case law, which is a different layer and a
  different company.

## 3. Constraints we actually build under

| Constraint | Detail | Class |
|---|---|---|
| No Anthropic credit | The founder is a student. The Anthropic key exists and cannot be called — `router.providers_available()` already treats a credit-less key as an unavailable provider | BUILT |
| Azure works now | Deployments `llama-3-3-70b` and `gpt-5-mini`; keys in `.env`; client in `eval/realrun/azure_model.py`, core in `checker/azure_model.py` | BUILT |
| Azure measured | **18 cases, 0 errors** on `llama-3-3-70b` (`eval/realrun/last_run_azure_llama-3-3-70b.json`); both deployments answered a live probe on 29-09-2026 | MEASURED |
| Gemini free tier | **20 requests / day / model** — `backend/budget.FREE_TIER_RPD_PER_MODEL`. **Backup only**; a demo's worth, not a working day | MEASURED |
| No large local models | The laptop holds 8.6 GB; a 12B model ran Ollama out of GPU memory on 14-09-2026. "Run it locally" means an 8B or nothing | MEASURED |

## 4. Decisions

Each carries its reason and the condition that would reverse it. A decision without a
reversal condition is a belief, not a decision.

### D1 — No training or post-training now

**Reason:** no GPUs, no expert-labelled data, and — the load-bearing one — **knowledge
baked into weights cannot be dated**, while our moat is point-in-time law. A model that
has learned the Companies Act cannot tell you which Companies Act it learned.

**Revisit when:** 1,000+ lawyer-reviewed traces exist **AND** a hosted model repeatedly
fails one specific workflow. Both, not either.

### D2 — Rent models behind `checker/router.py`, one callable signature

**Reason:** Harvey switched models twice; the interface is the asset, not the weights.

A model is promoted **only** by bake-off: a **non-overlapping 95% confidence interval
against the incumbent** *and* a person edits the table. **Never automate promotion before
real volume** — that is the revisit condition and it points at "not yet", not at a date.

### D3 — Every model call inside Azure

**Never call DeepSeek / Qwen / Kimi vendor APIs directly.** Kimi K3 and DeepSeek V4 are
reachable **only via Azure AI Foundry**. Client documents go only to endpoints whose
**hosting region is confirmed** — and the **Fireworks-on-Foundry region is OPEN**, so no
client document may go there until it is closed.

**The Gemini free tier never receives a Vault or matter document.** This is already
enforced rather than promised: `checker/public_only.py` admits only text that this
repository *publishes*, `checker/azure_model.narrate` and `checker/gemini_model.generate`
both require an `origin` with no default, and an AST sweep over the tree fails the gate if
any call site omits it. **BUILT.**

**Revisit when:** a buyer contract explicitly permits another host.

### D4 — Retrieval: BM25 for statutes

**BM25 is the incumbent for statutes and stays the incumbent.** The review calls it the
measured winner; **the head-to-head measurement is not in this repository** — what is here
is [PLAN_21](PLAN_21_RESEARCH_PROGRAMME.md) §"Hybrid dense retrieval", which admits dense
retrieval *only* if it beats BM25 on the enlarged eval with non-overlapping intervals
(`router.py`'s `adopt_when` rule). The decision is the same either way, so nothing turns on
closing this gap — but "incumbent by rule" and "winner by measurement" are not the same
sentence and E3 is what would make the second one true. **INFERRED**, pending E3.

Dense retrieval — `voyage-law-2` via `checker/voyage_model.py`, or Azure embeddings —
enters **only if a bake-off wins**, and the likeliest place it wins is **contracts**, not
statutes.

Client text reaches Voyage **only after its processing location is confirmed**.

### D5 — OCR: decided by measurement, not by brochure

Sarvam Vision (`checker/sarvam_model.py`; Indian, 22 languages) against **Azure Document
Intelligence**, decided on **scanned public Indian filings**.

Sarvam's own figure is **87.39% vs 79.35% for Gemini 3.6 Flash** —
**UNVERIFIED (vendor-reported)**, and not measured on our documents.

**Sarvam's training opt-out must be confirmed before any client document is sent.**

### D6 — One verb table generates REST API, MCP tools and a CLI

With a **parity test**, so the three surfaces cannot drift into three products.

### D7 — Hosted MCP server with OAuth, as a distribution channel

The same channel Harvey uses. Extends the **13 existing read-only tools in
`checker/mcp/`** rather than starting a new surface — count verified 29-09-2026:
`len(checker.mcp.tools.TOOLS) == 13` and `checker/mcp/policy.py` asserts
`READ_ONLY_TOOLS == KNOWN_TOOLS`, so "read-only" is enforced rather than described.
**BUILT.**

### The rule that binds every model, in every decision above

> A model **may** read, extract, label and phrase.
> A model may **never** decide a legal status, choose an authority, or supply a date.

This is not new policy — it is what `checker/entailment_gate.py`,
`agents/research_question.py` and the `L0` verifiers already enforce. It is restated here
because every decision on this page is an instance of it.

## 5. Architecture

Recorded **verbatim as supplied** in the founder's review. Two forms were given and both
are kept: the drawn diagram and the written-out form. They are not edited — including
where the box rules do not align — because a diagram retyped is a diagram changed, and
§5.4 carries the corrections instead.

### 5.1 As given — drawn

```
                 ┌──────────── SURFACES (one verb table → three) ─────────────┐
                 │  REST API /v2        MCP server (hosted, OAuth)     CLI     │
                 │  Word add-in · Web                                          │
                 └───────────────────────────────┬─────────────────────────────┘
                                                 │ auth → tenant, actor · audit row
 ┌───────────────────────────── L3 AGENT RUNTIME (agents/) ──────────────────────────────┐
 │ intent (fixed list) → plan (code) → steps saved → budget → at most 1 correction         │
 │ intents: research_question · review_contract · review_board_doc · law_changes           │
 └──────┬────────────────────┬─────────────────────┬──────────────────────────────┬────────┘
        │                    │                     │                              │
 ┌──────▼──────┐   ┌─────────▼────────┐   ┌────────▼─────────┐        ┌───────────▼─────────┐
 │ MODEL ROUTER│   │ RETRIEVAL        │   │ DOCUMENT PIPE    │        │ VERIFY (L0, no model)│
 │ router.py   │   │ BM25 (statutes)  │   │ text / OCR       │        │ scope · as_of ·      │
 │ Azure Llama │   │ + dense candidate│   │ Sarvam | Azure DI│        │ currency · quoted_   │
 │ gpt-5-mini  │   │ (Voyage / Azure) │   │ clause segmenter │        │ span · entailment ·  │
 │ Kimi/DS cand│   │ date-conditioned │   │ playbook engine  │        │ obligations          │
 │ Gemini: pub │   └──────────────────┘   └──────────────────┘        └─────────────────────┘
 │ only        │
 └─────────────┘
 ┌──────────────────────── L1 DATA (Postgres, row-level security per tenant) ─────────────┐
 │ corpus (hashed, versioned) · Vault docs · runs/steps/propositions · events with two     │
 │ dates (took effect / we learned it) · entity graph · audit chain                        │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 As given — written out

```
SURFACES (one verb table -> REST API /v2, MCP server with OAuth, CLI; plus Word
add-in and web) -> GATEWAY (auth -> tenant, actor; audit row) -> L3 AGENT RUNTIME
(agents/: fixed intent -> plan in code -> steps saved -> budget -> max 1
correction; intents research_question, review_contract, review_board_doc,
law_changes) -> four parts:
  MODEL ROUTER (router.py: Azure Llama, gpt-5-mini, Kimi/DeepSeek candidates,
    Gemini public-only)
  RETRIEVAL (BM25 for statutes, dense candidate Voyage/Azure, date-conditioned)
  DOCUMENT PIPE (text/OCR Sarvam|Azure DI, clause segmenter, playbook engine)
  VERIFY L0, no model (scope, as_of, currency, quoted_span, entailment,
    obligations)
-> L1 DATA (Postgres, row-level security per tenant: hashed versioned corpus,
Vault docs, runs/steps/propositions, events with two dates, entity graph, audit
chain).
Status today: runtime, retrieval (BM25), verify = built; router needs Azure rows;
document pipe, gateway, surfaces, Postgres tables = to build.
Themis later plugs into L1 (watch feeds -> events, entity graph, recall of past
answers that relied on changed law) without rebuilding.
```

### 5.3 Why the shape matters

Intents are a **fixed list in code** — `agents/plans.py` — and a model may only choose
among *declared optional steps*. That is what makes a run replayable.

**VERIFY is L0 and takes no model.** That is the same rule as §4's, drawn: the four boxes
above it may read, extract, label and phrase; only the box with no model in it decides.

**Themis plugs into L1, not into a new stack.** Watch feeds become events, events land on
the entity graph, and a past answer that relied on law which later changed is recalled —
all off the two-date events already in L1. This is what the bitemporal model in L1 is *for*,
and it is why the premium tier needs no rebuild.

### 5.4 Checked against the tree, 29-09-2026

The status line in §5.2 is preserved as written. Four refinements, each verified in this
checkout rather than passed through — the record stands and the correction is dated, which
is this repository's rule for its own history:

| §5.2 says | Verified today | |
|---|---|---|
| "router needs Azure rows" | **Already landed.** `checker/router.py` now carries an AZURE row for TEXT/LOW/NARRATION and `providers_available()` reports it (commits `d9a65c7`, `0ff9a4d`). Ten fixtures ran live on `azure:llama-3-3-70b` | **BUILT** |
| "gateway = to build" | True for auth, tenant and the app — `gateway/` holds only `__init__.py` and `audit.py`. The **audit chain is built** (19 checks) and the psycopg/Postgres decision is recorded in `requirements-gateway.txt` | **PART BUILT** |
| "document pipe = to build" | True for the F12 parts: `checker/clause_segmenter.py` and `checker/playbook.py` **do not exist**. Text/OCR does — `checker/pdf_pages.py`, `checker/sarvam_model.py`, `checker/classify.py` | **PART BUILT** |
| "Postgres tables = to build" | Stronger than "to build": **no migration file exists anywhere in the tree.** `001_core.sql` and `002_runs.sql` were specified and never written; R-016 (`runs` vs `turns`) is the open question blocking the second | **BLOCKED** |

All six L0 verifiers named in the diagram exist and are gated: `scope`, `as_of`,
`currency`, `quoted_span`, `entailment_gate`, `obligations`. **BUILT**, as claimed.

One box is drawn but not yet real anywhere: **retrieval is not date-conditioned yet.**
`as_of` and `currency` exist as verifiers that refuse a stale answer *after* retrieval; the
diagram puts the date inside retrieval, which is a different thing and is not built.


## 6. F12 — contract review (new feature)

```
upload
  -> text / OCR
  -> segment clauses                      (CODE, not a model)
  -> model extracts {type, verbatim span, values}
  -> quoted_span verifies BYTE FOR BYTE; values re-derived FROM the span
  -> company playbook rules evaluated by CODE:
         MATCHES · DEVIATES · MISSING · NEEDS_LAWYER
     reported as POTENTIAL_ISSUE — never as a legal defect
  -> law links only to HELD law; otherwise a named refusal
```

The Contract Act, the Arbitration Act and the Stamp Act are **not held yet**, so a
contract question reaching them gets the named refusal, not a quiet silence — the same
rule `checker/scope.py` already applies to the eight declared-but-unheld bodies.

**Measured on:** **CUAD** (510 contracts, 41 clause types, CC BY 4.0) **plus Indian
contracts**. CUAD alone measures American drafting.

## 7. Experiments

Deterministic scoring, **no LLM as judge**, 95% confidence intervals throughout.

| # | What | Set | Metric |
|---|---|---|---|
| E1 | Research answers | 60 Companies Act questions | traced-sentence rate · refusal rate · **rupees per answer**; across Llama 3.3, gpt-5-mini, Kimi K3, DeepSeek V4 |
| E2 | Clause extraction | CUAD test + 20 Indian contracts | per-clause F1 · **exact span** |
| E3 | Retrieval | frozen 70-case statute eval + CUAD | recall@k; BM25 vs Voyage vs Azure |
| E4 | OCR | 30 scanned public filings | Sarvam vs Azure DI |
| E5 | Lawyer usefulness | 2–3 in-house counsel, 20 real tasks | the only one that is not a number |

## 8. Build order

1. **Azure routing**
2. **Bake-off harness**
3. **Contract review v1**
4. **Gateway + verb table** → API / MCP / CLI
5. **SEBI acquisition**
6. **Frontend app**

**Prototype targets (INFERRED, not commitments):** demo ~day 3–4 · usable ~day 10–14 ·
pilot-ready ~week 4.

## 9. What this document does not establish

- **Every Harvey figure here is second-hand**, and the two gain figures are
  vendor-reported by the vendor that benefits. Nothing in §4 relies on them.
- **Sarvam's OCR advantage is unmeasured on our documents.** D5 is a plan to measure, not
  a choice already made.
- **The Fireworks-on-Foundry hosting region is OPEN** — an unresolved blocker on any
  client document reaching a Fireworks-served model. **BLOCKED.**
- **Voyage's and Sarvam's data-handling terms are unconfirmed.** D4 and D5 both gate on
  confirmation that has not happened.
- **Prototype dates are inference.** No velocity measurement supports them.
- **"BM25 is the measured winner" is not evidenced here** (see D4). It is the incumbent by
  rule; E3 is what would make it the winner by measurement.
