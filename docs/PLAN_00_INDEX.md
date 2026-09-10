# The plan — index and claim status

Written 2026-09-09, against the engine at this commit. Seven documents, each one
scoped so a reader can tell what is **built**, what is **measured**, what is
**researched-and-sourced**, and what is **still a hypothesis**.

The rule for every document here: a claim carries its evidence or it carries a
status marker. Nothing is asserted because it sounds right.

| Document | Covers | Strongest claim | Weakest |
|---|---|---|---|
| [PLAN_01_ARCHITECTURE](PLAN_01_ARCHITECTURE.md) | The 20-role orchestration, why only 9 touch a model | Built and green | Roles 16-20 are designed, not built |
| [PLAN_02_MODEL_TRAINING](PLAN_02_MODEL_TRAINING.md) | What to train, what not to, on what hardware | The hardware limit is arithmetic | Label yield from the corpus is unmeasured |
| [PLAN_03_DATA_SOURCES](PLAN_03_DATA_SOURCES.md) | Every source, verified access mechanics | Six research passes, URL-cited | Vendor authorisation unverifiable |
| [PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md) | The v1 product surface | Distribution path verified | Effort estimate is inference |
| [PLAN_05_ROADMAP](PLAN_05_ROADMAP.md) | Sequence, gates, Bloomberg scoped | Gates are falsifiable | Demand is n=1 |
| [PLAN_06_EVALUATION](PLAN_06_EVALUATION.md) | How to be believed | Static RAG = 0%, traced | No Indian benchmark exists yet |
| [PLAN_07_TENANCY_AND_PRICING](PLAN_07_TENANCY_AND_PRICING.md) | Isolation, zero retention, what to charge for | The retention rule is quoted from a shipped system | Indian deal sizes not found |
| [FEATURES](FEATURES.md) | **The canonical feature list.** If it is not there, it is not planned | 7 of 10 have a built engine | F8 unbuilt and risky |

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
