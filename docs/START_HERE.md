# Start here

The one page to read before anything else in this repository, for people and for coding
agents. It says what is being built, how a request travels through the code, which documents
are current, and where each kind of change belongs. Written 2026-10-01 against `main` at
2e0793c. Where this page and the code disagree, the code wins; fix this page.

**The full architecture — every product, feature, agent, model and source — is [ARCHITECTURE.md](architecture/ARCHITECTURE.md).** Features, integrations (government, publishers, MCP, CLI, API) and document verification: [PLATFORM_FEATURES_AND_INTEGRATIONS.md](architecture/PLATFORM_FEATURES_AND_INTEGRATIONS.md). How each feature is built, card by card: [FEATURE_ARCHITECTURE.md](architecture/FEATURE_ARCHITECTURE.md). The per-file index is [REPO_MAP.md](REPO_MAP.md), generated from each module's own docstring
(`python3 scripts/repo_map.py`). The rules every change must obey are in
[../CLAUDE.md](../CLAUDE.md), and they bind whatever this page says.

## 1. What this is, in five lines

**Placedon** is an evidence-backed legal intelligence layer for Indian in-house legal teams.
It answers questions about Indian corporate law, reviews documents and contracts, and says
which bodies of law a corporate event engages. Every answer cites the exact provision, its
amending instrument and the date it came into force, or it refuses and says why. **Code
decides legal status, authority and dates; a model may only read, extract, label and
phrase; a lawyer attests before anything is VERIFIED.**

## 2. What is held and what is not

`checker/scope.py` is the authority. Run `python3 checker/scope.py` for the live table.

- **Held** (decided on any date): Companies Act, 2013 (`corpus/companies_act/`).
- **Current text only**: SEBI LODR Regulations (today's text, no earlier dates).
- **Declared** (in scope, not acquired, so an answer names the gap): LLP Act, SEBI
  ICDR/SAST/PIT/Buyback, FEMA and the FDI rules, IBC, Competition Act, Indian Contract Act,
  Arbitration Act, stamp duty, DPDP Act.
- A question about a declared body is **refused by name, never answered by silence**, and
  the invariant that no obligation exists for an unheld body is a test.

## 3. How a request travels through the code

```
client (web app, MCP, CLI)
  │
  ▼  gateway/          app.py (HTTP), verbs.py (one verb table → REST, MCP and CLI),
  │                    auth.py (hashed keys → tenant), audit.py (hash-chained metadata),
  │                    store.py and migrations/ (Postgres, FORCE RLS on every tenant table)
  │
  ▼  agents/           plans.py (intent → fixed step list), runtime.py (persisted steps,
  │                    bounded correction), one file per intent: research_question.py,
  │                    review_contract.py, review_document.py
  │
  ▼  gateway/jobs.py + worker.py    durable queue (SKIP LOCKED), idempotent steps, saga cancel
  │
  ▼  checker/          the engine:
  │    retrieval       text_search.py (the ranker), ask.py (the ask path), ask_scope.py
  │    law and dates   scope.py, as_of.py, amendment.py, applicability.py, obligations.py,
  │                    events.py (which bodies an event engages), claim_bodies.py
  │    verification    quoted_span.py, ground_span.py, entailment_gate.py, cascade.py
  │    models          model_cascade.py (deterministic → small → large, escalate only on a
  │                    verifier rejection), router.py, azure_model.py, public_only.py
  │    sources         sources/ (tiers: only HELD can verify; terms register in terms.py)
  │    contracts       clauses.py, playbook.py, playbooks/nda_v1.json
  │
  ▼  answer: ANSWERED / PARTIAL / NEEDS_LAWYER / ABSTAINED, with quotes and a trace.
     FAILED means a transport error only and is never shown as a refusal.
```

**The ring firewall** (`checker/rings.py`) is checked by an AST walk in the test gate:
Ring 0 (legal core) may never import Ring 2 (feeds, gateway, sources) or Ring 3 (agents,
forecast). A probability can never reach a legal decision.

## 4. The documents that are current

Read these; treat every other document as dated history unless one of these points to it.

| Document | Why it matters |
|---|---|
| [../CLAUDE.md](../CLAUDE.md) | The non-negotiable rules and the verification status |
| [PLAN_20_INHOUSE_CORPORATE.md](plans/PLAN_20_INHOUSE_CORPORATE.md) | Who the customer is (read [EVIDENCE_CORRECTIONS_PLAN_20.md](plans/EVIDENCE_CORRECTIONS_PLAN_20.md) with it) |
| [PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md](plans/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md) | Models, platform, database: decisions D1–D8, each with a reversal condition |
| [PLAN_23_ORCHESTRATION.md](plans/PLAN_23_ORCHESTRATION.md) | How work is planned and run: layers, research basis, steps O0–O9 |
| [PLAN_26_INDIAN_SOURCES.md](plans/PLAN_26_INDIAN_SOURCES.md) | Indian sources, their tiers and terms, build order S0–S5 |
| [../.claude/loops/DECISION_harvey_parity.md](../.claude/loops/DECISION_harvey_parity.md) | The feature sequence H0–H6 (refusals, sources, web, drafts, review tables, Word) |
| [RETRIEVAL_BAKEOFF_2026-09-30.md](evidence/RETRIEVAL_BAKEOFF_2026-09-30.md) | Why the ranker is what it is |
| [RETRACTIONS.md](evidence/RETRACTIONS.md) and [CLAIMS_LEDGER.md](evidence/CLAIMS_LEDGER.md) | What was claimed, what was withdrawn, and why |
| [PLAN_00_INDEX.md](plans/PLAN_00_INDEX.md) | The index of every numbered plan, with the status of each |

Two numbered folders are **Project Themis**, developed on its own branch:
[plan24/](plans/plan24/00_INDEX.md) and [plan25/](plans/plan25/00_INDEX.md), with `checker/forecast/`.
`docs/plans/plan24/` is unrelated to `PLAN_26_INDIAN_SOURCES.md`, which was renamed from
PLAN_24 to end that collision.

## 5. Where each kind of change belongs

| You want to… | Start in | And never forget |
|---|---|---|
| Add an API, MCP or CLI action | `gateway/verbs.py` | One entry generates all three surfaces; write verbs stay off MCP |
| Add a task the product can do | `agents/plans.py`, then a new `agents/<intent>.py` | Plans are fixed step lists; a model may pick, never invent |
| Add a body of law | `checker/scope.py`, then an `ingest_*`/`acquire_*` script | Promotion to held needs acquisition, hashing, cross-check and a lawyer spot-check |
| Add an outside source | `checker/sources/` plus a record in `terms.py` | No record, no fetch; never work around robots rules or a WAF |
| Add a table | `gateway/migrations/NNN_*.sql` | Tenant tables get FORCE RLS; run `scripts/rls_integration.py --run` |
| Change retrieval | `checker/text_search.py` | Measure on the dev split only (`scripts/retrieval_recall.py`); the held-out split is spent |
| Call a model | `checker/router.py`, `checker/model_cascade.py` | Client documents only to India-region endpoints; UNPRICED is never ₹0 |
| Work on review tables (H4) | `checker/review_grid.py` and `agents/review_grid.py` | See the naming note below — three names, one feature |

**Naming, because three names mean one feature here.** The review-table feature is
`review_grid` **in the code** (`checker/review_grid.py` holds the cells, the states and the
CSV export; `agents/review_grid.py` runs one queue job per cell) and `review_table.*` **in
the verbs** (`review_table.create`, `.status`, `.export`), which is the name a user sees.

**`checker/review_table.py` is a different, older module and is unrelated to any of it.**
It is the human-review accounting for the eleven benchmark fixture proposals: for each
proposed replacement claim it reports, per statutory qualifier, PRESERVED / MISSING /
NOT_APPLICABLE, so a reviewer can rule on the proposal. It decides nothing and writes no
gold label. It predates H4, and H4's plan row asked for its filename without that being
checked — which is how the new module briefly overwrote it (restored from git, intact).

## 6. Running and testing

```bash
bash scripts/run_tests.sh              # the gate: read the HARNESS_RESULT line, never prose
PYTHONPATH=. python3 eval/goldset/run.py   # gold set, dev split, two denominators
python3 checker/scope.py               # what is held
python3 scripts/repo_map.py            # regenerate docs/REPO_MAP.md
```

The gate cannot run twice at once (a server binds a fixed port). A suite that prints no
count, or fewer checks than its floor in `scripts/suite_floors.json`, fails.

## 7. What is honestly unknown

- No accuracy figure exists. The gold set has **no human labels**; its dev split is 13
  answer rows and 17 refusal rows, and the held-out split has been run once.
- The event table in `checker/events.py` has not been reviewed by a lawyer.
- Only one body of law of eleven is held.

## 8. Cleanup candidates, not yet removed

Found on 2026-10-01 by an import scan: these tracked Python files are neither imported by
other code nor run by the test gate. Most are command-line tools that the documents tell a
person to run, so **none is deleted without a check that nothing references it**.

- `backend/services/llm.py` and `checker/anthropic_model.py`: the Anthropic path. No
  Anthropic credit is in use (PLAN_22); kept until that decision is final.
- `scripts/build_section_index.py`, `scripts/cross_validate_corpus.py`,
  `scripts/verify_against_pdf.py`, `scripts/verify_reconstruction.py`,
  `scripts/scan_testdocs.py`, `scripts/seed_admission.py`, `scripts/preflight.py`,
  `scripts/render_review_html.py`, `scripts/render_review_table.py`: one-off tools with
  recorded results in `docs/` or `reports/`.
- `scripts/index_codebase.py` and `scripts/search_memory.py` exist twice, with different
  contents, also under `.claude/scripts/`.
