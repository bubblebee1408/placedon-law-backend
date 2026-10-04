# 04: Analytics and prediction — how deep it can go, and the gate at each depth

The founder asked: *how deep can it go?* The honest answer is a ladder. Each rung needs more
data and carries more risk than the one below it. **A rung is built only when the rung below
it is measured**, and each rung has a data gate that can be checked mechanically.

## 1. The ladder

| Level | Question it answers | Method | Data it needs | Output class | Gate |
|---|---|---|---|---|---|
| **L0** | What does the law say, as of this date? | Deterministic retrieval + deciders | Held corpus | verified_fact | **Built** |
| **L1** | Is this judgment still good law? | Citation graph + human-labelled treatments | SC/HC judgments (AWS) | deterministic_conclusion | Counsel on CC-BY; citation extraction precision measured on a hand-checked sample |
| **L2** | How many / what share? ("s.241 petitions at NCLT Mumbai, 2023–25") | Counts, proportions, Wilson intervals | `ForumCase` records | predictive_signal (descriptive) | Lawful access to NCLT records; n ≥ 30 per shown stratum, else count only |
| **L3** | How long? ("time from filing to sanction of a scheme") | Kaplan–Meier with censoring; log-rank between strata | Filing date, disposal date **or pending** | predictive_signal | L2's gate + censoring handled + a recomputation test |
| **L4** | What usually happens, by type? ("share of compounding applications allowed") | Hierarchical Beta-Binomial, partially pooled | Outcome labels per case | predictive_signal | Outcome labels extracted **and** human-checked on a sample; n per stratum shown |
| **L5** | What is likely in *this* matter? | Forecast from pre-decision features only; time-split; conformal prediction sets | L4 + pre-decision features | predictive_signal, with prediction *set* | The pre-registered gate in §5. **May never pass** |
| **L6** | How does *this judge* decide? | Per-judge models (02 P6) | Judge identity | — | **OFF.** Counsel first (§6) |

L0 is where the product is today. L1–L3 are the realistic "Gotham depth" for corporate forums.
L4 is achievable for narrow, high-volume case types. L5 is a research programme. L6 is a legal
question before it is an engineering one.

## 2. On-wedge first: analytics over law we hold

Litigation analytics usually starts with courts. For this product it starts with **the
Companies Act forums**, because the statute there is held (`scope.py`), so a statistic can sit
beside the law it concerns.

| Matter type | Provision (held) | Forum | Why in-house counsel pay for it |
|---|---|---|---|
| Schemes of arrangement / amalgamation | ss.230–232 | NCLT | Deal timelines: "when can we close?" |
| Oppression and mismanagement | ss.241–242 | NCLT | Exposure: stage durations, interim relief rates |
| Compounding of offences | s.441 | NCLT / RD | Cost of a default: compounding fee distributions by section |
| Reduction of capital | s.66 | NCLT | Timeline |
| Adjudication of penalties | s.454 | ROC (adjudicating officer) | Penalty amounts by section. **Access: MCA site; the WAF rule in `CLAUDE.md` applies** [OPEN] |

IBC petitions (ss.7/9) are the highest-volume NCLT work. **IBC is not held** (`scope.py`), so
IBC statistics would sit beside law we do not hold. They are excluded until IBC is held. That
is the same invariant as the obligation register.

## 3. The maths, rung by rung

### 3.1 L2: a proportion with its interval

Show `k/n` and the Wilson 95% interval (S1). How many cases a stratum needs before a rate
means anything:

| Desired half-width of 95% interval (worst case p = 0.5) | n needed |
|---|---|
| ±0.10 | **97** |
| ±0.05 | **385** |
| ±0.03 | **1,068** |

Examples of what a lawyer would see:

| Observed | Wilson 95% |
|---|---|
| 7 of 10 | 0.40 – 0.89 |
| 35 of 50 | 0.56 – 0.81 |
| 140 of 200 | 0.63 – 0.76 |

*(Computed in this session with z = 1.95996.)* **Display rule:** below n = 30, show the count
and the interval and withhold the rate. That rule already exists in the gold set.

### 3.2 L3: time-to-event with censoring

For each case: `t = disposal_date − filing_date` if disposed, otherwise
`t = data_cutoff − filing_date` with `event = 0` (censored).

```
Ŝ(t) = ∏_{t_i ≤ t} (1 − d_i / n_i)        Kaplan–Meier
Var[Ŝ(t)] ≈ Ŝ(t)² Σ d_i / (n_i (n_i − d_i))   Greenwood
```

- The median is the first t where Ŝ(t) ≤ 0.5. Report it with its confidence interval, the n
  at risk, and the data cutoff.
- **The failure this prevents.** "Average time of disposed cases" ignores the cases still
  pending, which are the slow ones. Dropping them biases every duration downward (S2). DAKSH
  uses survival analysis on Indian pendency for exactly this reason (02 §3).
- Differences between strata (bench A vs bench B, or pre- and post-2024 rules) use a log-rank
  test. **Bench comparisons count as L6 territory if benches map to individual members. Aggregate
  to forum level by default.**

### 3.3 L4: partially pooled rates

For stratum j with `y_j` successes of `n_j`, in a parent group with a Beta(a, b) prior fitted
across its strata:

```
posterior mean_j = (y_j + a) / (n_j + a + b)
```

A stratum with 3 cases is pulled toward its parent. One with 300 is barely moved. **Every
displayed estimate shows its own n_j and whether it is mostly data or mostly prior.** The rule
is to flag an estimate when `n_j < a + b`.

### 3.4 L5: forecasting, only with a set, never a bare point

For a matter-level forecast, conformal prediction produces a **set** of outcomes with coverage
≥ 1 − α (S4).

- When the set is `{allowed, dismissed}`, the system has **abstained**, and it says so.
- Only a singleton set is a forecast.
- Under drift from new rules or benches, ACI (S5) adapts α online. A coverage breach on the
  rolling window stops L5 serving.

## 4. What "statistics and decisions for lawyers" becomes, concretely

| Lawyer's need | Rung | Screen shows |
|---|---|---|
| "Are we compliant, as of this date, on what basis?" | L0 | Law, quotes, dates |
| "Can I still cite this judgment?" | L1 | Treatment chain with the citing sentences |
| "What if we cross the threshold?" | L0 `scenario` | Obligations switching on, with dates |
| "How long will NCLT take on our scheme?" | L3 | Median, interval, n, cutoff, "not a prediction for your matter" |
| "What does compounding a s.XX default usually cost?" | L4 | Pooled distribution, n, interval |
| "Will we win?" | L5 | A prediction set or an abstention, only if §5 has passed. Until then: "Not available. Here is L3/L4." |

## 5. The pre-registered gate for any L5 forecast

This is written now, **before** any data is seen. Tuning after seeing results is the failure
02 P1 describes.

1. **Target.** One forum, one matter type, one binary outcome, defined in writing (for
   example: "NCLT, s.66 capital reduction petitions, sanctioned vs not").
2. **Features.** Only what existed on the filing date or at a declared stage. A *leakage audit*
   lists each feature with the document it comes from and its date. Any feature derived from
   the final order is disqualifying (02 P1, P7).
3. **Split.** Train on cases filed up to date T. Test on cases filed after T **and** decided
   by the data cutoff. Test on censoring-aware subsets. The test split's hash is committed
   before the first run (PLAN_19 G0.2's rule).
4. **Baselines to beat.** (a) Majority class. (b) The L4 pooled base rate for the stratum.
   The model must beat **(b)** in Brier score, with a paired bootstrap 95% interval excluding
   zero.
5. **Calibration.** A reliability diagram. The ECE floor for the test n comes from
   `calibration_contract.ece_floor` [R]. A claimed calibration below the floor is refused by
   construction.
6. **Size.** `calibration_contract.n_min(0.5, 0.05)` = **256** resolved test cases for one
   stratum [R, PLAN_19 04 §7]. Fewer means the gate cannot pass; it is not "close".
7. **Serving.** Conformal sets only (§3.4), in output class `predictive_signal`, and never on
   a matter a Ring 0 decision depends on. The ring firewall enforces the last part.
8. **Kill.** If after 12 months no stratum reaches (4)–(6), L5 is closed and recorded in
   `NON_GOALS.md`.

## 6. Judge-level analytics (L6)

- **Evidence that it works:** per-judge models outperform a judge-agnostic one in French
  custody appeals [S] (02 P6).
- **Evidence that it is dangerous:** France made it a crime, with up to five years (02 R1).
  India has no known equivalent [OPEN]. The Contempt of Courts Act's "scandalises" limb
  (02 R2) is a live risk for a published scorecard.
- **Decision in this plan.** L6 is **not designed** until counsel gives written advice.
  - Until then, no `Judgment` or `ForumCase` object stores a judge name as a property used
    by any Ring 3 computation.
  - A `rings.py`-style source scan (T6) fails the gate if an analytics module reads a judge
    field.
  - Bench *size* and forum are allowed.

## 7. What this plan refuses in analytics, and why

| Refused | Why |
|---|---|
| Any percentage quoted from a paper as "our accuracy" | 00: no figure from another system is a figure for this one |
| Training an LLM to "predict judgments" (INLegalLlama-style) | L1–L3 (02 §2); D1 (PLAN_22); and 02 P5, leakage unaudited |
| Scraping NCLT, eCourts or MCA past their terms | `CLAUDE.md` non-negotiable |
| District-court analytics from DDL data, commercially | CC BY-NC-SA (02 §3); off-wedge |
