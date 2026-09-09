# The plan — index and claim status

Written 2026-09-09, against the engine at this commit. Six documents, each one
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
