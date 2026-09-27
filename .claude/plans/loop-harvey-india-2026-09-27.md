# Runbook — Harvey-for-India platform, Themis-ready core

Founder's plan, pasted 2026-09-27, to be executed under `/loop`. Branch:
`claude/harvey-india-platform-analysis-d2mmqi`. One logical change per commit, each with tests,
draft PR per milestone.

## The rule that holds everywhere
**Models read, extract and explain. Code decides legal status. A lawyer attests before anything is
served as VERIFIED.** Enforced by `checker/rings.py`: nothing from a model or a forecast may feed a
legal decision.

## Correction to the plan, measured before starting
The plan opens Day 1 with *"get the test harness green (198 suites, 5 failing today)"*.
**Measured on this branch at `4707404`: `HARNESS_RESULT suites=206 failed=0 status=GREEN`,
re-run independently in 212s.** 198 is the count on `claude/placedon-law-backend-analysis-zxwjjp`,
a different branch. **M0 is already met.** Day 1 therefore starts at the ingester.

## Milestones and done criteria (verbatim from the plan)
| # | Milestone | Done when |
|---|---|---|
| M0 | Green tests | `HARNESS_RESULT status=GREEN` — **MET at 4707404, 206/0** |
| M1 | Breadth | 5 Acts + 4 SEBI regulations ingested and hash-stamped; each CURRENT_ONLY in scope.py; the invariant test ("no obligation for a body that isn't held") passes |
| M2 | Retrieval across bodies | `/v1/ask` returns instrument-qualified citations per body; a question mixing held and unheld law is answered in part and refused for the rest |
| M3 | Gateway | Two tenants provably cannot see each other's rows (test); `/v1` passthrough unchanged |
| M4 | Runtime | A run killed mid-way resumes and produces an identical trace; missing budget or model leads to refusal |
| M5 | Documents | An ICSI specimen notice plus minutes gives span-traced facts; minutes checks never fire on a notice |
| M6 | First workflow | Every sentence served is cited or dropped; every refusal is named |
| M7 | Themis data layer | A Gazette item opens an operation on a watched entity; "as known on" and "as of" queries differ correctly |
| M8 | Entailment v0 | Scored on a frozen evaluation set; SUPPORTED reachable only through it |

## Bodies of law, in order
1. Companies Act 2013 (held) · 2. SEBI LODR (current text held, awaiting review) ·
3. SEBI ICDR/SAST/PIT/Buyback · 4. LLP Act 2008 · 5. FEMA 1999 + FDI rules · 6. IBC 2016 ·
7. Competition Act 2002 · 8. DPDP 2023 · 9. Stamp duty, State-by-State (last)

**Tier 1 Research:** ingested, hash-stamped, verbatim cited text labelled **CURRENT TEXT ONLY**;
questions about earlier dates **refused** until amendment history is held.
**Tier 2 Decided:** deterministic checks per body, each lawyer-attested before serving.

## Model routing
| Job | Model |
|---|---|
| High-consequence extraction | `claude-opus-5-5` |
| Explaining from retrieved sources, with citations | `claude-sonnet-5` + Citations API |
| Low-consequence classification | `claude-haiku-4-5` |
| Scanned pages | Gemini (wired) |
| Second opinion | OpenAI — **shadow only, never served** |
| Reranking | Voyage — candidate only |

Preferred model unavailable: **high-consequence task is REFUSED**; low-consequence may fall back
and the result must say it did.

## Status vocabularies (one set, used everywhere)
- **Run:** PLANNED · RUNNING · AWAITING_HUMAN · ANSWERED · PARTIAL · REFUSED · FAILED.
  **FAILED means a system or transport error and must never be shown as a refusal.**
- **Proposition:** VERIFIED · PARTIALLY_VERIFIED · UNVERIFIED · CONFLICTING · OUT_OF_SCOPE
- **Obligation:** the existing five states, unchanged.

## Allowed new dependencies, with reasons
`psycopg[binary]` (Postgres driver) · `openai` (shadow adapter only). Check what the existing
Anthropic/Gemini adapters already use before adding anything. **Nothing else** — no LangGraph,
LiteLLM, Redis, Celery, LangSmith, no model voting.

## Not in this plan
Case law · prediction layers · fine-tuning (collect consented traces first) · enterprise SSO ·
Word add-in polish.

## Standing constraints carried from this session
- Never deploy. Never push the frontend repo. Never edit or push `Placedon-law-business-plan`.
- Stage explicit paths; **never `git add -A`**. One logical change per commit.
- `./scripts/verify_green.sh` is the only oracle. **One gate at a time** — it binds 127.0.0.1:8021
  with `allow_reuse_port = False`, so concurrent runs produce a spurious RED.
- No unsupported product, market, legal or competitor claims. UNVERIFIED beats a guess.
- Never repair a defective government source; flag it verbatim.
- A new module is not BUILT until it has a `_test()` listed in `scripts/run_tests.sh`.
- `scripts/check_doc_refs.py` is in the gate: a present-tense doc may not cite a path that
  does not exist. Naming a dead path means not backticking it.

## Order of work
**Day 1** — branch; generalize `scripts/ingest_companies_act.py` into `scripts/ingest_act.py`.
**Days 2–3** — ingest LLP, IBC, Competition, FEMA, DPDP + the four SEBI consolidations;
scope register CURRENT_ONLY per body; section index keyed by (instrument, number).
**Days 3–4** — retrieval and `/v1/ask` across bodies; mixed held/unheld question answered in part.
**Day 5** — gateway, Postgres, `runs`/`run_steps`/`audit`, tenant isolation (RLS).
**Week 2** — agent runtime (resume, approvals, budgets, ≤1 correction), router, documents, first
workflow. **Week 3** — one decider per body + Themis data layer. **Week 4** — entailment v0,
per-body evaluation, cost per run, design-partner sessions.

## Risks the plan names
1. **Lawyer attestation time** sets how fast Tier 2 grows. 2. **Amendment history** per new body is
after week 4. 3. **Source terms** — RBI caching restriction OPEN; FDI caps move by press note;
stamp duty differs by State; India Code availability confirmed at ingest time.
