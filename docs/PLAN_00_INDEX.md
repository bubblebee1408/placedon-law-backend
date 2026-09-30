# The plan — index and claim status

Written 2026-09-09 and **re-indexed 2026-09-27**, when it was found to list seven
documents out of twenty-two. Each is scoped so a reader can tell what is **built**,
what is **measured**, what is **researched-and-sourced**, and what is **still a
hypothesis**.

The rule for every document here: a claim carries its evidence or it carries a
status marker. Nothing is asserted because it sounds right.

**One number, one document.** Three numbers carried two files each until 2026-09-27:
PLAN_16 across two branches, and PLAN_13 and PLAN_20 within this one. All resolved —
see *Renames* at the foot of this page. If a number below is missing, it is because
PLAN_19 is a directory, `docs/plan19/`, not a single file.

| Document | Covers | Strongest claim | Weakest |
|---|---|---|---|
| [PLAN_01_ARCHITECTURE](PLAN_01_ARCHITECTURE.md) | The 20-role orchestration, why only 9 touch a model | Built and green | Roles 16-20 are designed, not built |
| [PLAN_02_MODEL_TRAINING](PLAN_02_MODEL_TRAINING.md) | What to train, what not to, on what hardware | The hardware limit is arithmetic | Label yield from the corpus is unmeasured |
| [PLAN_03_DATA_SOURCES](PLAN_03_DATA_SOURCES.md) | Every source, verified access mechanics | Six research passes, URL-cited | Vendor authorisation unverifiable |
| [PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md) | The v1 product surface — a Word task-pane add-in | Distribution path verified | Effort estimate is inference |
| [PLAN_05_ROADMAP](PLAN_05_ROADMAP.md) | Sequence, gates, Bloomberg scoped | Gates are falsifiable | Demand is n=1 |
| [PLAN_06_EVALUATION](PLAN_06_EVALUATION.md) | How to be believed | Static RAG = 0%, traced | No Indian benchmark exists yet |
| [PLAN_07_TENANCY_AND_PRICING](PLAN_07_TENANCY_AND_PRICING.md) | Isolation, zero retention, what to charge for | The retention rule is quoted from a shipped system | Indian deal sizes not found |
| [PLAN_08_BOOKMARK_AND_GODSEYE](PLAN_08_BOOKMARK_AND_GODSEYE.md) | The entity graph and the live-feed layer | A source audit, done before building | Most market-wide Indian data cannot lawfully be reused |
| [PLAN_09_MCA_MASTER_DATA_STRIP](PLAN_09_MCA_MASTER_DATA_STRIP.md) | The MCA master-data strip: analysis and simulation | Simulated before built | MCA access is the unsolved part |
| [PLAN_10_ADOPTION_REVIEW](PLAN_10_ADOPTION_REVIEW.md) | A pasted stack checked against what exists here | Declines a criminal-law pivot, with reasons | Review of a proposal, not a build plan |
| [PLAN_11_NEXT_MOVE](PLAN_11_NEXT_MOVE.md) | Large-document intake and provider choice | Driven by measured defects | Superseded in part by PLAN_16 |
| [PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE](PLAN_12_DOCUMENT_INTAKE_ARCHITECTURE.md) | F8 bulk document review, OCR and layout | Names role 13 concretely | Cites modules built under other names |
| [PLAN_13_ASSISTANT_UX](PLAN_13_ASSISTANT_UX.md) | **The Ask section design spec.** What `web/assistant/` is built from | Three judges scored the direction | A spec, not a measurement |
| [PLAN_14_TERMINAL_AND_FEEDS](PLAN_14_TERMINAL_AND_FEEDS.md) | The terminal, God's Eye integrated | Feeds exist and run | "What the numbers may say" is untested |
| [PLAN_15_TERMINAL_BUILD](PLAN_15_TERMINAL_BUILD.md) | Building the terminal: feeds, model, the non-digital moat | Builds on shipped feeds | Moat argument is reasoning, not measurement |
| [PLAN_16_BACKEND_ARCHITECTURE](PLAN_16_BACKEND_ARCHITECTURE.md) | **The backend a user actually meets.** Token economics, the vault, compliance | `backend/budget.py` implements §5.2–5.5 and is gated | Written 25-09; the pricing in §5 is superseded by PLAN_20 |
| [PLAN_17_BETA_BUILD](PLAN_17_BETA_BUILD.md) | The beta in shells, with a prompt per milestone | Milestones are ordered and checkable | Names artifacts not yet built |
| [PLAN_18_TECHNICAL_DESIGN](PLAN_18_TECHNICAL_DESIGN.md) | The beta's technical design, on interfaces that exist | Built on real interfaces | Specifies ten modules that do not exist yet |
| [plan19/](plan19/00_INDEX.md) | **PLAN_19, nine documents.** A Gotham-grade workbench on Themis | Part 04 proves recall without re-running | arxiv.org was blocked; citations are second-hand |
| [PLAN_20_INHOUSE_CORPORATE](PLAN_20_INHOUSE_CORPORATE.md) | **The current customer decision.** In-house legal teams, corporate law | Supersedes the CS-primary buyer | Four of its claims are corrected — read the next row first |
| [EVIDENCE_CORRECTIONS_PLAN_20](EVIDENCE_CORRECTIONS_PLAN_20.md) | What the 27-09 evidence review contradicts in PLAN_20 | Every figure carries a source class | A single commissioned review, not a replication |
| [PLAN_21_RESEARCH_PROGRAMME](PLAN_21_RESEARCH_PROGRAMME.md) | The research programme and the conformal guarantee | C1 states the guarantee per answer | Was PLAN_16 until 27-09; n=0 human labels |
| [PLAN_22_MODEL_AND_PLATFORM_DECISIONS](PLAN_22_MODEL_AND_PLATFORM_DECISIONS.md) | **The model and platform layer.** Rent-not-train, Azure-only calls, retrieval, OCR, API/MCP/CLI, contract review F12 | Seven decisions, each with a reversal condition; the Gemini/Vault firewall is BUILT and gate-enforced | Every Harvey figure is second-hand and two are vendor-reported; Fireworks-on-Foundry region is OPEN |
| [PLAN_23_ORCHESTRATION](PLAN_23_ORCHESTRATION.md) | **How work is planned and run.** Twelve layers, the workflow-before-agent rule, the verified cascade, sagas, and O1–O9 | Every rule is derived from a cited finding, MAST's 1,642 traces included | A design: layers 2–11 name work not built, and two of eleven findings are vendor material |
| [FEATURES](FEATURES.md) | **The canonical feature list.** If it is not there, it is not planned | 7 of 10 have a built engine | F8 unbuilt and risky |

## Scope

**Compliance across Indian corporate law**, declared in `checker/scope.py`: nine
bodies in scope, one held. The register exists because widening a claimed scope
without widening the refusals is how an engine starts appearing to cover law it
has never read — and a silence that used to mean "outside our scope" would start
meaning "no obligation found", which is the opposite answer.

## The one-paragraph version

Indian corporate law changes underneath correct answers, and nothing watches. We
proved this on our own codebase: the engine served a superseded small-company
threshold as CURRENT for nine months, and three further obligations reported
current law they had never read. Every competitor checked shows the same class of
error today — four of the most-read Indian compliance sites still publish the
2022 figure, and one publishes a figure that never existed. The product is the
watching, not the answering.

## Status vocabulary

| Marker | Means |
|---|---|
| **BUILT** | In the repo, covered by a self-test in `scripts/run_tests.sh` |
| **MEASURED** | A number produced on this machine against a frozen eval |
| **SOURCED** | Verified against a primary source, URL recorded |
| **INFERRED** | My reasoning, not a source. Treat as a hypothesis |
| **UNVERIFIED** | Believed but not checked. Do not build on it |
| **BLOCKED** | Needs a human act or a contract |

## What would falsify the whole thesis

Stated first, because a plan that cannot be wrong is not a plan.

1. A practitioner reads the pack and calls the refusals useless — "just answer."
2. Nobody is ever actually caught out by a stale figure; the ₹4 crore case is a
   curiosity rather than a cost.
3. An incumbent (SCC Online, Manupatra) ships dated-instrument tracking as one
   feature and commoditises the wedge.
4. The as-of date reads to lawyers as hedging rather than rigour.
5. The declared-but-unheld bodies stay unheld long enough that "in scope" becomes
   a marketing word. One held body out of nine is a starting position, not a
   resting one.

None of these is answerable by building more. All four are answerable in ten
conversations.

## What was deleted, and where it went

38 superseded documents were removed rather than left to rot: 19 planning and
roadmap documents in `docs/`, and 19 completed loop runbooks in `.claude/plans/`.
Git history keeps all of them — `git log --diff-filter=D --name-only` finds any
of it — but a repository where five documents each claim to be the roadmap has no
roadmap.

| Deleted | Superseded by |
|---|---|
| `FEATURE_PLAN_INDIA`, `WORKFLOW_BACKLOG_INDIA` | [FEATURES](FEATURES.md) |
| `ROADMAP`, `BUILD_ROADMAP`, `BUILD_PLAN_PRODUCT`, `BUILD_PLAN_2026_08`, `PLAN_TWO_MONTH`, `NEXT_PHASE_PLAN` | [PLAN_05_ROADMAP](PLAN_05_ROADMAP.md) |
| `TECHNICAL_PLAN`, `TECHNICAL_PLAN_CORPORATE`, `ARCHITECTURE`, `AGENT_ARCHITECTURE_PLAN` | [PLAN_01_ARCHITECTURE](PLAN_01_ARCHITECTURE.md) |
| `ML_PLAN`, `MODEL_DEVELOPMENT_PLAN` | [PLAN_02_MODEL_TRAINING](PLAN_02_MODEL_TRAINING.md) |
| `WEEK2_RULE_INGESTION_PLAN` | [PLAN_03_DATA_SOURCES](PLAN_03_DATA_SOURCES.md) |
| `LOOP`, `NEXT_MOVE_PLAN_2026_09_04` | [LOOP_EVENT_LOG](LOOP_EVENT_LOG.md) |
| `SONNET_ERA_REVIEW`, `PLAN_REVIEW_KIMI_2026_08_22` | reviews of external PDFs; nothing depended on them |
| 19 × `.claude/plans/loop-*.md` | completed loops, Aug 12 – Sep 5 |

Every reference to a deleted document — **including seven code docstrings** — was
repointed to its successor rather than left dangling. Full suite green after.

**Deliberately kept**, because they are evidence or policy rather than plans:
`RETRACTIONS` (known-invalid results), `SOURCE_DEFECTS`, `SOURCE_POLICY`,
`SOURCE_PROVENANCE_POLICY`, `ACQUISITION_POLICY`, `CLAIMS_LEDGER`,
`TEMPORAL_PROOF`, `CORROBORATION`, `BENCHMARK_GOVERNANCE`, `METRIC_POLICY`,
`H001_OUTREACH`, `SESSION_BUILD_LOG_2026_09`, `RETIRED_POSH` (a decision record —
deleting those is how a team re-litigates settled questions), and the measured
results under `.claude/plans/`.

## Renames, 2026-09-27

One number had come to mean two documents in three places. Resolved on the founder's
decision; the old names are recorded here because dated records still use them.

| Was | Is now | Why |
|---|---|---|
| `PLAN_16_RESEARCH_PROGRAMME.md` (on `main`, 24-09) | `PLAN_21_RESEARCH_PROGRAMME.md` | `PLAN_16_BACKEND_ARCHITECTURE.md` (25-09) keeps the number. 25 live references renumbered; `backend/budget.py`'s eight "PLAN_16 §5.x" comments are untouched and still correct, because they cite the backend document |
| `PLAN_13_ASSISTANT_UX_PLAN.md` | `ASSISTANT_UX_PLAN.md` | The number stays with the **spec**, because that is what everything cites: `web/assistant/contract.md` references "PLAN_13 §4.1", "§7.12", "§11", "§13", and those sections exist only in the spec |
| `PLAN_20_EVIDENCE_CORRECTIONS.md` | `EVIDENCE_CORRECTIONS_PLAN_20.md` | It is a correction to a plan, not a plan |

**Dated records were deliberately not updated.** `docs/research/*`, `.claude/plans/*` and the
2026-09 reports still use the old names, and their reference was correct on the day it was
written. Editing a dated record to match a later rename is how a repository loses its own
history — the same rule that kept `docs/CLAIMS_LEDGER.md`'s 2026-08-21 denominator intact. Each
renamed file carries a header note mapping the old name to the new one.
