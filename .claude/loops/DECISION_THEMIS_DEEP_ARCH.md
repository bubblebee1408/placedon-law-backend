# DECISION: Themis deep architecture (PLAN_25)

## Chosen

**Option A: extend what exists.** Fix before extending.

## Rejected, in writing

- **B, re-platform on an agent framework and a graph database.**
  - The evidence says sequential pipelines lose under multi-agent designs (17.2× error amplification, Kim et al. 2025).
  - GraphRAG gains are marginal (Han et al., KDD 2026).
  - The current system's guarantees (rings, span verification, parity, RLS) are tested; a rewrite discards them.
- **C, train a legal LLM for prediction.**
  - The leakage findings mean the resulting score would not measure forecasting (Medvedeva & McBride; the shortcut-learning study).
  - Fine-tuning on new facts raises hallucination (Gekhman et al.).
  - PLAN_22 D1 already rejects it on dating grounds, and its revisit condition (1,000+ reviewed traces) is unmet.

## What this loop builds (the prototype), and the file list

| File | What |
|---|---|
| `checker/forecast/__init__.py` | `Estimate` contract. Kinds: DESCRIPTIVE / HYPOTHETICAL / FORECAST. Rendering is gated by `calibration_contract` |
| `checker/forecast/rates.py` | Beta-Binomial partial pooling; exact Beta CDF and quantile |
| `checker/forecast/survival.py` | Kaplan–Meier, Greenwood, log-log band, median with interval |
| `checker/forecast/conformal.py` | Split conformal sets; abstention; ACI with its bound |
| `checker/forecast/events.py` | Gamma-Poisson change forecast; exact Gamma CDF and quantile |
| `checker/forecast/propagate.py` | P(rule applies) over uncertain facts; swing sensitivity; Ring 0 refusals propagate |
| `checker/forecast/scoring.py` | Brier; Murphy decomposition; log-odds pooling |
| `checker/rings.py` | `checker.forecast` registered as RING_3 by package. Test written first and seen red (3 FAIL), then green |
| `scripts/run_tests.sh` | 7 new suites |
| `docs/plan25/*` | The architecture, for the founder to study |

## Tests written before the code

Each module's `_test()` states its claim as a simulation with a known truth, before the implementation was trusted:

- **Pooling:** beats raw rates in ≥ 54/60 forums, and MSE ratio < 0.8.
- **Kaplan–Meier:** equals 1−ECDF with no censoring; median CI covers the truth in ≥ 90% of samples; the naive median is further from the truth.
- **Conformal:** coverage ≥ 1−α on a miscalibrated model; ACI error within its proven bound after a shift, and closer to α than static.
- **Events:** mean forecast inside the Wilson interval of the observed rate; top decile calibrated; beats the pooled constant rate on Brier.
- **Propagate:** Monte Carlo interval contains the exact answer for uniform, triangular and compound rules, and for the real s.2(85) limits read from Ring 0.
- **Scoring:** the Murphy identity holds exactly; the base-rate forecaster has zero skill.
- **Rings:** Ring 3 contains only `checker.forecast`, and a decider importing it is caught.

## Rollback

Delete `checker/forecast/`. Revert the two edits (`rings.py` registry plus its test, and 7 lines in `run_tests.sh`). Nothing imports the package; the rings guard proves no decider can.

## Reversal condition

Abandon the forecast plane, or narrow it to `propagate` alone, if **either** of these happens:

1. After 6 months of pilot use, no FORECAST-kind estimate has reached SERVABLE on any stratum, **and** no user has used a DESCRIPTIVE statistic twice.
2. A practitioner in H-001 says base rates and durations would not change a decision they make.

## Escalated, not decided

- the PLAN_22 D3 amendment (new free model host);
- migration numbering (007);
- anything changing what `/v1/ask` serves (A-012);
- all counsel questions.
