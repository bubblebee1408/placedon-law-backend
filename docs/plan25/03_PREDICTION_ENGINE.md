# 03: The prediction engine — six algorithms, their maths, and what was measured

**Status: BUILT and TESTED as a prototype.** It lives in `checker/forecast/`, uses only the
standard library, and is registered as Ring 3 in `checker/rings.py`. Every module proves
itself with seeded simulation in its `_test()`.

**No real legal data has been run through it.** Every rate, interval and score on this page
comes from a simulation where the truth is known. The ₹10 cr / ₹100 cr limits are served by
the engine (G.S.R. 880(E), CORROBORATED), and 9/19/99 is arithmetic. That is how you check that an algorithm works. It is
not how you check that Themis is accurate. That needs human labels, which is file 05.

**Why this is not the Bayesian engine `LESSONS.md` L-15 deleted.** L-15's engine ran correct
arithmetic over *stipulated* weights (a prior of 0.6, a likelihood ratio of 12.0). Here:

- no prior is stipulated;
- `rates` and `events` estimate theirs from the strata themselves (empirical Bayes), and say
  "mostly prior" when a stratum is thin;
- `POOL_CAP` is a numerical ceiling, not a belief;
- a FORECAST number still cannot render without the track record L-15's module never had.

## 1. What "think beyond the data and predict" can honestly mean

The research (file 01 and appendix C) gives four kinds of "beyond the data". Three are
buildable now, and one is not.

| Kind | Example question | Honest method | Module |
|---|---|---|---|
| **What-if over uncertain facts** | "Will we still be a small company next year if turnover lands between ₹80 and ₹105 crore?" | Run the exact legal rule over the stated range of facts | `propagate` |
| **Base rates from records** | "How often does NCLT allow compounding under this section? How long does a scheme take?" | Partial pooling; survival with censoring | `rates`, `survival` |
| **Forecast of a future event** | "Will SEBI amend this regulation in the next 12 months?" | Pooled event rates, scored against what then happens | `events`, `scoring` |
| ~~Forecast of a case outcome~~ | "Will we win?" | **Not built.** Needs labelled resolved matters and counsel. The method exists (`conformal`: a set with guaranteed coverage, abstaining when it cannot separate the outcomes), and is tested on simulations only | — |
| ~~Simulated judge or court~~ | "Simulate how the bench will reason" | **Not built.** Agent courts are unvalidated. LLMs are near random on formal counterfactuals (CounterBench [S]) and flatten identity groups (Wang et al., NMI 2025 [S]) | — |

**The rule that holds across all of them:** the law is never probabilistic. The rule is
applied exactly. Only facts, rates and future events carry probability. That is why
`propagate` calls the Ring 0 decider and never approximates it.

## 2. The algorithms

### 2.1 `rates`: partial pooling across benches, sections and statutes

The problem it solves: a bench with 3 cases cannot support a rate of its own, and a forum
with 300 can.

```
y_j ~ Binomial(n_j, p_j),   p_j ~ Beta(a, b)       (a, b fitted from all strata)
rho = ( s² / (m(1-m)) - mean(1/n_j) ) / (1 - mean(1/n_j))       a + b = 1/rho - 1
estimate_j = (y_j + a) / (n_j + a + b),  exact Beta 95% interval
```

**Measured (seeded simulation, 60 forums × 40 strata, true prior Beta(4, 12)):**

| Check | Result |
|---|---|
| Pooling beats the raw rates | **57 of 60** forums |
| Mean squared error vs raw | **0.56×** (a 44% reduction) |
| Recovered prior mean | 0.260 against a true 0.25 |
| A 3-case stratum at 2/3 | reported as 0.316 and flagged "mostly prior" |
| A 300-case stratum at 0.667 | reported as 0.646, barely moved |
| Strata differing only by noise | pooled completely, with no false difference shown |
| Complete pooling: interval covers the truth | **168/183 runs (91.8%)**. The first version covered **~4%**: its prior was "worth 1e6 cases". An independent QA review found it; the fix is that a prior is never worth more cases than the data it was fitted from |

### 2.2 `survival`: how long things take, counting the pending cases

```
S(t) = Π (1 - d_i/n_i)                      Kaplan–Meier
Var ≈ S² Σ d_i / (n_i(n_i - d_i))           Greenwood;  log-log 95% band
median = first t with S(t) ≤ 0.5; interval read from the band
```

**Measured (400 exponential cases, true median 6.93, random censoring):**

| Check | Result |
|---|---|
| **The naive method** (drop pending cases) | median **4.42**: wrong by a third, and too fast in this sample |
| Kaplan–Meier | median **7.41** |
| Coverage of the 95% interval over 200 samples | **188/200 = 94%** |
| Without censoring, KM equals 1 − ECDF | exact at every step |

A bug was caught while building this: the median's interval limits were swapped. The
`Estimate` type refuses a value outside its own interval, so it failed loudly on the first
run instead of shipping.

### 2.3 `conformal`: forecast as a set, abstain when the set holds both outcomes

```
s_i = 1 - p̂(y_i | x_i)     on n calibration cases
q̂ = the ⌈(n+1)(1-α)⌉-th smallest s_i  (∞ if that exceeds n, meaning always abstain)
C(x) = { y : 1 - p̂(y|x) ≤ q̂ }          P(y ∈ C(x)) ≥ 1 - α for ANY model
ACI:  α_{t+1} = α_t + γ(α - err_t)       |mean err - α| ≤ (max(α₁,1-α₁)+γ)/(γT)
```

**Measured (a deliberately miscalibrated model; α = 0.10; 200 repetitions):**

| Check | Result |
|---|---|
| Conformal coverage | **90.06%**, which meets the 90% promise despite the bad model |
| Abstention rate | 31.7%, with the rest forecast |
| The same model's bare point forecast | right only **77.6%** of the time, with no warning |
| After a simulated change in the law, static conformal | error drifts to **20.9%** |
| After the same change, ACI | error held at **10.2%**, inside the proven bound of ±2.3 pts |
| Minimum labelled cases before any singleton is possible | **9 / 19 / 99** for α = 0.10 / 0.05 / 0.01 |

This is the most important result on the page. **In this simulation, a miscalibrated model
wrapped in conformal kept its 90% marginal coverage (90.06%) under exchangeability. After a
simulated law change, only ACI held (10.2% error).** Barber et al. (Annals of Statistics
2023) [S] treat conformal prediction under drift. That an amendment is such a drift is our
inference [I]. ACI is built and tested.

### 2.4 `events`: will this rule change within h years?

```
k_i ~ Poisson(λ_i T_i),  λ_i ~ Gamma(α, β)   (fitted across provisions)
P(≥1 change in h years) = 1 - (β'/(β'+h))^α',   α' = α + k_i,  β' = β + T_i
```

**Measured (2,000 simulated provisions):**

| Check | Result |
|---|---|
| Mean forecast vs what happened | **0.170 vs 0.168** (99.9% Wilson interval 0.142–0.197) |
| Top decile | forecast 0.459, observed 0.475 (99.9% interval 0.363–0.589), so calibrated in the tail |
| Homogeneous rates, the likely shape of the real corpus | computes (0.180). The first version **crashed in 176/176 such cases** (QA review); the prior is now capped at the events observed |
| Brier: pooled history vs one rate for all | **0.1215 vs 0.1399** |
| On real data today | it computes, **and shows no number**, because `calibration_contract` has no track record. That is the rule working |

### 2.5 `propagate`: the what-if engine

```
P(rule applies) = P( decider(facts) = True ),   facts ~ declared ranges
Monte Carlo, seeded; the interval is simulation error only
swing(): pin each uncertain fact at its 5th / 95th percentile -> which unknown matters
```

**Measured, against exact answers:**

| Check | Exact | Simulated |
|---|---|---|
| Uniform(40, 60) > 50 | 0.5000 | 0.5056 |
| Triangular(30, 45, 70) > 50 | 0.4000 | 0.4025 |
| Compound OR rule over two facts | 0.5793 | 0.5811 |
| **Real Ring 0 decider `checker.classify.small_company`** (proviso included), limits served by the engine (₹10 cr / ₹100 cr, G.S.R. 880(E)), turnover ~ U(limit−20, limit+5) | 0.80 | **0.7925** (n = 800) |
| Same, holding company | 0 | **0.0**: the proviso is applied |

- `swing()` correctly names turnover as the fact that decides the answer.
- If the decider answers **INSUFFICIENT_DATA** for any draw (for example, an unknown proviso
  fact), **no probability is formed**. An abstention is never counted as "does not apply".
- A decider that raises (for example, an unattested threshold) produces no probability.
- A decider returning a score is refused.
- Every estimate states the rule id, the as-of date and the source.

### 2.6 `scoring`: grading forecasters, and combining them

```
Brier = REL - RES + UNC     (Murphy 1973; exact for discrete forecasts)
skill = 1 - Brier / UNC
pool:  logit p = d · Σ w_i logit p_i    (d = 1 until the promotion gate says otherwise)
```

**Measured:**

| Check | Result |
|---|---|
| The identity | holds to 1e-12 (0.20165 = 0.00589 − 0.05198 + 0.24773) |
| The base-rate forecaster | skill **0**, as it must be |
| An informative forecaster | skill **0.186** |

## 2.7 How the tests were made trustworthy

Two independent reviewers ran after the build:

- **The trust-boundary review (VETO)** found that a forecast could borrow any track record,
  that notes were dropped on rendering, and that the what-if test used a rule written inside
  Ring 3.
- **The QA review (NO-GO)** re-derived every formula independently. The Beta/Gamma CDFs
  matched numeric integration to ~1e-12, and the KM ties and Greenwood band matched hand
  calculation. It then found:
  - the complete-pooling failures above;
  - a hang on NaN durations;
  - tests that passed only on the chosen seed: a "95% interval contains the truth" check
    fails 1 run in 20 by design.

**All of these are fixed, and each fix has its test.** The failing tests were written first
and seen red. Simulation checks now use 4-standard-error or 99.9% tolerances. **Every test
now passes under 20 different seeds** (measured).

## 3. How it connects to the rest of Themis

- **Ring 3, enforced.** `rings.py` now asserts that Ring 3 holds `checker.forecast` and
  nothing else. It also asserts that a Ring 0 decider importing any forecast module,
  including one not yet written, is caught.
- **Rendering is gated.** `Estimate.render()` prints a FORECAST number only when
  `calibration_contract.assess()` says SERVABLE **for a record kept for that forecast's own
  `target_id`**. An independent review showed that the first version accepted *any* SERVABLE
  record; that is fixed and tested. Every render carries n, the interval, the method, the
  "not a …" sentence, the notes ("mostly prior", "censored", "not reached") and the basis. A
  HYPOTHETICAL without a stated rule, date and source is refused at construction.
- **Orchestration.** Each algorithm becomes a verb (file 02 §4): `forecast.rate`,
  `forecast.duration`, `forecast.change`, `forecast.whatif`. **None exists yet.** When
  built, all four are read-only, so all four are also MCP tools. They return the rendered
  sentence, never a bare value. Output classes are mapped in file 02 §4.

## 4. What it needs before any of this touches a real matter

| Algorithm | Real data it needs | Where that comes from | Blocked by |
|---|---|---|---|
| rates, survival | case records with filing date, disposal date or *pending*, type, outcome | NCLT/NCLAT orders, SEBI adjudication orders, RBI compounding orders, CCI orders | access terms read and quoted per source (file 06) |
| events | the amendment history of each instrument | eGazette plus the corpus's own amendment chains | the corpus stops in 2023 (D-1); the eGazette watcher closes that gap going forward |
| conformal | ≥ 19 labelled cases per stratum for α = 0.05; a few hundred for a useful abstention rate | the lawyer-engineer funnel (file 05) | people, not code |
| propagate | nothing new: the Ring 0 deciders already exist | — | **usable now** for held law |
| scoring | resolved forecasts | the learning loop (PLAN_24 05) | time |

**The one module usable on real matters today is `propagate`**, because it adds no
statistics about the law, only about the user's own uncertain facts.
