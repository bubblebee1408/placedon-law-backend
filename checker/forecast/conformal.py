"""Forecast as a SET, and abstain when the set holds both outcomes.

PLAN_24 04 §3.4 and §5 step 7. A point probability from a model is only as good as the
model's calibration, which at our volumes cannot be demonstrated (`calibration_contract`).
Split conformal prediction needs no such trust. Given any scoring model and n held-out
labelled cases, it returns a set C(x) of outcomes with

    P( y_new in C(x_new) ) >= 1 - alpha          (Vovk et al.; Angelopoulos & Bates)

for any model and any data distribution, provided calibration and new cases are
exchangeable. For a binary outcome the set is {}, {0}, {1} or {0, 1}:

    a singleton  -> a CANDIDATE forecast. It reaches a reader only as an `Estimate` of kind
                    FORECAST, through `Estimate.render`, with a SERVABLE record for its target
    {0, 1}       -> ABSTAIN: the evidence does not separate the outcomes at this alpha
    {}           -> ABSTAIN as well: never shown as "neither will happen"

## Split conformal, exactly

Score s_i = 1 - phat(y_i | x_i) on the calibration set. With k = ceil((n + 1)(1 - alpha)),
qhat is the k-th smallest score. If k > n there are too few cases for this alpha, and
every set is {0, 1}: the method abstains rather than pretending. C(x) = { y : 1 - phat(y|x) <= qhat }.

## Drift: adaptive conformal inference (Gibbs & Candes, NeurIPS 2021)

Law changes, so exchangeability fails over time. ACI tracks the realised error and moves
its working level:

    alpha_{t+1} = alpha_t + gamma * (alpha - err_t)

Whatever the drift, the long-run error rate satisfies

    | (1/T) sum err_t - alpha |  <=  (max(alpha_1, 1 - alpha_1) + gamma) / (gamma * T)

`_test()` checks that bound on a simulated shift, and checks marginal coverage of the
static method over repeated samples.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from checker.forecast import EstimateError

FORECAST_SET = "FORECAST"
ABSTAIN = "ABSTAIN"


def conformal_quantile(scores: list[float], alpha: float) -> float:
    """qhat for split conformal. `math.inf` means: too few cases, always abstain."""
    if not 0.0 < alpha < 1.0:
        raise EstimateError("alpha must be in (0, 1)")
    if not scores:
        return math.inf
    n = len(scores)
    k = math.ceil(round((n + 1) * (1.0 - alpha), 9))   # round: 0.3*10 is 3.0000000000000004
    if k > n:
        return math.inf
    return sorted(scores)[k - 1]


def min_calibration_n(alpha: float) -> int:
    """Smallest calibration set for which the method can ever return a singleton."""
    n = 1
    while math.ceil(round((n + 1) * (1.0 - alpha), 9)) > n:
        n += 1
    return n


def prediction_set(p1: float, qhat: float) -> frozenset[int]:
    """Outcomes whose nonconformity 1 - phat(y) is within qhat. p1 = phat(y = 1)."""
    if not 0.0 <= p1 <= 1.0:
        raise EstimateError("a probability must lie in [0, 1]")
    return frozenset(y for y, p in ((0, 1.0 - p1), (1, p1)) if 1.0 - p <= qhat)


def decision(pset: frozenset[int]) -> str:
    return FORECAST_SET if len(pset) == 1 else ABSTAIN


@dataclass
class SplitConformal:
    alpha: float
    qhat: float = math.inf
    n: int = 0

    def calibrate(self, probs: list[float], labels: list[int]) -> "SplitConformal":
        if len(probs) != len(labels):
            raise EstimateError("probabilities and labels differ in length")
        if any(y not in (0, 1) for y in labels):
            raise EstimateError("labels must be 0 or 1")
        if any(not (0.0 <= p <= 1.0) for p in probs):     # also rejects NaN
            raise EstimateError("calibration probabilities must lie in [0, 1]")
        scores = [1.0 - (p if y == 1 else 1.0 - p) for p, y in zip(probs, labels)]
        self.qhat = conformal_quantile(scores, self.alpha)
        self.n = len(scores)
        return self

    def predict(self, p1: float) -> frozenset[int]:
        return prediction_set(p1, self.qhat)


@dataclass
class AdaptiveConformal:
    """ACI over a fixed calibration pool; `alpha_t` moves with realised errors."""
    alpha: float
    gamma: float
    scores: list[float]
    alpha_t: float = -1.0

    def __post_init__(self) -> None:
        if self.alpha_t < 0:
            self.alpha_t = self.alpha

    def predict(self, p1: float) -> frozenset[int]:
        if self.alpha_t <= 0.0:
            return frozenset({0, 1})
        if self.alpha_t >= 1.0:
            return frozenset()
        return prediction_set(p1, conformal_quantile(self.scores, self.alpha_t))

    def update(self, pset: frozenset[int], y: int) -> int:
        err = 0 if y in pset else 1
        self.alpha_t += self.gamma * (self.alpha - err)
        return err

    @staticmethod
    def bound(alpha1: float, gamma: float, horizon: int) -> float:
        if gamma <= 0 or horizon <= 0:
            raise EstimateError("gamma and horizon must be positive")
        return (max(alpha1, 1.0 - alpha1) + gamma) / (gamma * horizon)


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("forecast.conformal")
    rng = random.Random(20260930)

    # ── how many labelled cases before a singleton is even possible ────────
    check(min_calibration_n(0.10) == 9 and min_calibration_n(0.05) == 19
          and min_calibration_n(0.01) == 99,
          "minimum calibration n: 9 / 19 / 99 for alpha 0.10 / 0.05 / 0.01 (PLAN_21 C1)")
    check(conformal_quantile([0.1] * 18, 0.05) == math.inf,
          "with 18 cases at alpha 0.05 every set is {0,1}: abstain, not guess")

    # ── marginal coverage of a deliberately MISCALIBRATED model ─────────────
    # truth: P(y=1|x) = sigmoid(2x); the model believes sigmoid(4x + 0.5).
    def draw(n: int, shift: float = 0.0):
        xs = [rng.gauss(0, 1) for _ in range(n)]
        ys = [1 if rng.random() < _sigmoid(2 * x - shift) else 0 for x in xs]
        ps = [_sigmoid(4 * x + 0.5) for x in xs]
        return ps, ys

    alpha = 0.10
    covs, abstain_rates = [], []
    for _ in range(200):
        cp, cy = draw(200)
        sc = SplitConformal(alpha).calibrate(cp, cy)
        tp, ty = draw(300)
        sets = [sc.predict(p) for p in tp]
        covs.append(sum(y in s for s, y in zip(sets, ty)) / len(ty))
        abstain_rates.append(sum(decision(s) == ABSTAIN for s in sets) / len(sets))
    mean_cov = sum(covs) / len(covs)
    check(0.895 <= mean_cov <= 0.905 + 1 / 201,
          f"mean coverage {mean_cov:.4f} meets 1 - alpha = 0.90 despite a miscalibrated model")
    mean_abs = sum(abstain_rates) / len(abstain_rates)
    check(0.0 < mean_abs < 1.0,
          f"...and it abstains on {mean_abs:.1%} of cases, forecasting the rest")
    naive_cov = []
    for _ in range(200):
        tp, ty = draw(300)
        naive_cov.append(sum((p >= 0.5) == (y == 1) for p, y in zip(tp, ty)) / len(ty))
    check(sum(naive_cov) / len(naive_cov) < 0.85,
          f"the same model's bare point forecast is right only "
          f"{sum(naive_cov) / len(naive_cov):.1%} of the time, with no warning")

    # ── drift: ACI keeps its long-run error at alpha; static conformal does not ──
    horizon, gamma = 4000, 0.01
    cp, cy = draw(500)
    cal_scores = [1.0 - (p if y == 1 else 1.0 - p) for p, y in zip(cp, cy)]
    static = SplitConformal(alpha).calibrate(cp, cy)
    aci = AdaptiveConformal(alpha, gamma, cal_scores)
    s_err = a_err = 0
    for t in range(horizon):
        shift = 0.0 if t < horizon // 4 else 2.5          # the law changed
        (p,), (y,) = draw(1, shift)
        s_err += y not in static.predict(p)
        a_err += aci.update(aci.predict(p), y)
    s_rate, a_rate = s_err / horizon, a_err / horizon
    b = AdaptiveConformal.bound(alpha, gamma, horizon)
    check(abs(a_rate - alpha) <= b,
          f"ACI long-run error {a_rate:.4f} is within {b:.4f} of alpha after the shift")
    check(abs(s_rate - alpha) > abs(a_rate - alpha),
          f"...while static conformal drifts to {s_rate:.4f}")

    try:
        prediction_set(1.2, 0.5)
        check(False, "refuses a probability above 1")
    except EstimateError:
        check(True, "refuses a probability above 1")
    check(decision(frozenset()) == ABSTAIN, "an empty set is an abstention, never 'neither'")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
