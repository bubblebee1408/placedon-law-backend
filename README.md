# placedon-law-backend

The engine and API gateway behind Placedon, an evidence-first audit layer for Indian
corporate-law documents. Deterministic Python decides; a model may propose or explain, never
decide; a lawyer verifies.

> The model may propose. The system must verify. The reviewer decides.

**New here?** Read in this order, about an hour in total:

1. This file: setup, layout, the test gate.
2. [docs/START_HERE.md](docs/START_HERE.md): what is built, how a request flows, which documents are current.
3. [CLAUDE.md](CLAUDE.md): the non-negotiable rules and the verification status. They bind people as well as agents.
4. [CONTRIBUTING.md](CONTRIBUTING.md): how to make a change that the gate will accept.
5. [docs/README.md](docs/README.md): the map of every document folder.

---

## What it does today

- **Scope.** Eleven bodies of Indian corporate law are declared in `checker/scope.py`, and
  that file is the authority. **One, the Companies Act 2013, is held.** A question about a body
  that is declared but not held is *refused, naming what would be needed*. That is a different
  answer from "no obligation applies", and the difference is the product.
- **Compliance matrix.** Given what a company is (class, dates, directors, capital,
  turnover), it returns one row per obligation, each in one of five states:
  `APPLIES_SATISFIED · APPLIES_NOT_SATISFIED · APPLIES_UNDETERMINED · DOES_NOT_APPLY · CANNOT_DETERMINE`.
- **Ask, document check, contract review.** These are served through the gateway as verbs.
  Every answer is `ANSWERED / PARTIAL / NEEDS_LAWYER / ABSTAINED`, with quotes and a trace.
  `FAILED` means a transport error only, and is never shown as a refusal.
- **What it does not claim.** There is no accuracy figure. No practising lawyer has reviewed
  the output, and the gold set has no human labels. Read
  [docs/evidence/FAILURE_MODES.md](docs/evidence/FAILURE_MODES.md) before believing any of
  this works.

## Two API surfaces

| Surface | Where | Auth | Routes |
|---|---|---|---|
| `/v1`, the engine | `checker/api.py` (`handle`, pure function) | none | `GET /v1/health` · `POST /v1/compliance-pack` · `POST /v1/document-check` · `GET /v1/company/{cin}/events` · `GET /v1/company/{cin}/events/{event_id}` · `GET /v1/instruments/{fragment}/affected` |
| `/v2`, the gateway verbs | `gateway/verbs.py` → `gateway/app.py` | API key → tenant | generated from one verb table, which also produces the MCP tools (`checker/mcp/`) and the CLI (`gateway/cli.py`) |

The gateway forwards `/v1` **byte for byte**, and its suite asserts this. To list the live
`/v2` verbs, run `PYTHONPATH=. python3 gateway/cli.py --help`. Do not trust a list copied
into a document.

## Setup

Requirements: Python 3.10+. Postgres is optional (the gateway falls back to an in-memory
store and says so on `/v1/health`).

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m pip install -r requirements-gateway.txt      # Postgres driver, only for the gateway store
python3 scripts/check_deps.py                           # exit 0 = ready
```

`./setup.sh` does the first and third of these in one step and is safe to re-run.

| Requirements file | For |
|---|---|
| `requirements.txt` | the runtime: FastAPI, pydantic, jinja2, the Anthropic SDK |
| `requirements-dev.txt` | the test gate (adds uvicorn, httpx, pdfplumber, pypdf, jsonschema, so every suite can import) |
| `requirements-gateway.txt` | the gateway's Postgres store |

Environment variables are read where they are used. The main ones are
`PLACEDON_DATABASE_URL` (`gateway/store.py`; unset means in-memory) and the model-provider
settings read by `checker/azure_model.py` (e.g. `PLACEDON_ACCEPT_REGION`). **Never commit a key.**

## Run it

```bash
python3 scripts/serve_api.py              # /v1 engine, http://127.0.0.1:8020
python3 scripts/serve_matrix.py           # compliance-matrix HTML view, :8014
PYTHONPATH=. python3 gateway/cli.py --help    # the CLI surface
PYTHONPATH=. python3 -m gateway.worker --serve    # the job worker, see docs/guides/RUN_WORKER.md
PYTHONPATH=. python3 checker/scope.py     # what is held, declared and out of scope
```

The gateway is built with `gateway.app.create_app(keys=...)`. The frontend repository
(placedon-claude-legal-3300, its scripts/local-gateway.py) starts it with a fresh key and writes that key into the frontend's
`.env.local` without printing it. That is the supported local path.

## The test gate

```bash
./scripts/run_tests.sh       # every self-testing module; read the HARNESS_RESULT line
./scripts/verify_green.sh    # the same, plus an environment check first
```

- There is **no pytest**. Each module carries `_test()`, runs with `--test`, and prints
  `N/N passed`. The harness fails a suite that prints no count, or fewer checks than its
  floor in `scripts/suite_floors.json`.
- Read `HARNESS_RESULT suites=N failed=N status=...` and nothing else. Suite counts written
  in prose go stale.
- `status=BLOCKED` means dependencies are missing: nothing ran. That is *unmeasured*, not red.
- **One gate at a time.** `scripts/serve_ask.py --test` binds a fixed port, so a second
  concurrent run fails spuriously.

## Repository layout

```
.
├── checker/            the engine: Ring 0 legal core + retrieval, verification, sources
│   ├── api.py            /v1 handler (pure: request in, (status, dict) out)
│   ├── scope.py          which bodies of law are held / declared / out of scope (authority)
│   ├── obligations.py    the obligation register: matrix rows
│   ├── text_search.py    the ranker;  ask.py: the ask path
│   ├── rings.py          import firewall: Ring 0 may never import Ring 2/3 (AST-checked)
│   ├── sources/          outside sources, tiered; terms register in terms.py
│   ├── mcp/              MCP server (generated tools)
│   ├── forecast/         Project Themis prediction work (Ring 3)
│   └── ss/               Secretarial Standards defect scanner
├── gateway/            /v2: FastAPI app, verb table, auth, audit, jobs, worker, Postgres store
│   └── migrations/       NNN_*.sql; every tenant table has FORCE row-level security
├── agents/             agent runtime: plans.py (intent → fixed step list), one file per intent
├── backend/            budget, Azure pricing, and services/llm.py (the single paid-call chokepoint)
├── applicability.py    root-level applicability evaluator (imported by checker/)
├── corpus/             hash-stamped legal text, benchmarks, test documents (see below)
├── eval/               gold set, temporal harness, pre-label and real-run evaluations
├── playbooks/          contract-review playbooks (nda_v1.json, DRAFT until a lawyer approves)
├── scripts/            ingestion, verification, servers, and the test harness
├── research/TASKS.md   the task ledger: the single source of truth for what is open
├── reports/            generated measurement outputs
├── web/assistant/      static prototype of the Ask screen + its JSON fixtures
├── addin/              Word task-pane add-in prototype (dev HTTPS proxy)
├── ci/                 the CI workflow, held as tests.yml.pending (see ci/README.md)
├── ops/                launchd plist for the worker
├── docs/               every document, by kind (see docs/README.md)
└── .claude/            agent configuration: agents/, commands/ (/start, /build, /fix, ...), memory/, plans/
```

For a per-module index, see [docs/REPO_MAP.md](docs/REPO_MAP.md). It is generated by
`python3 scripts/repo_map.py` from each module's docstring, and the gate fails when it is stale.

### About `corpus/`

`corpus/companies_act/` holds 527 sections, plus `_index.json` and `_manifest.json` (529 files).
Every file is hash-stamped. **Never edit a corpus file by hand**, and never "repair" a defective
government source: defects are recorded in
[docs/evidence/SOURCE_DEFECTS.md](docs/evidence/SOURCE_DEFECTS.md) and preserved verbatim.

## Where to go next

| You want to… | Read |
|---|---|
| understand the whole system | [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) |
| see every feature and how it is built | [docs/architecture/FEATURES.md](docs/architecture/FEATURES.md), [docs/architecture/FEATURE_ARCHITECTURE.md](docs/architecture/FEATURE_ARCHITECTURE.md) |
| touch models, retrieval, OCR, API or MCP | [docs/plans/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md](docs/plans/PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md) |
| touch `agents/` or `gateway/` | [docs/plans/PLAN_23_ORCHESTRATION.md](docs/plans/PLAN_23_ORCHESTRATION.md) |
| know who the customer is | [docs/plans/PLAN_20_INHOUSE_CORPORATE.md](docs/plans/PLAN_20_INHOUSE_CORPORATE.md) |
| know what was claimed and withdrawn | [docs/evidence/RETRACTIONS.md](docs/evidence/RETRACTIONS.md), [docs/evidence/CLAIMS_LEDGER.md](docs/evidence/CLAIMS_LEDGER.md) |
| pick up work | [research/TASKS.md](research/TASKS.md) |

Security reports: [SECURITY.md](SECURITY.md).
