"""Will this instrument change within h years? Gamma-Poisson, pooled across instruments.

The founder asked for Themis to "predict the next move". For a regulator, the honest form of
that question is a rate: how often has this kind of provision been amended, and what does
that imply for the next h years? One provision's own history is too thin (PLAN_08 records
about 6 amending events in the whole amendment corpus), so rates are pooled across
provisions exactly as `rates` pools across benches.

## The model

    k_i | lambda_i ~ Poisson(lambda_i * T_i),      lambda_i ~ Gamma(shape alpha, rate beta)

k_i amending events in T_i years of exposure. Empirical-Bayes moments: with mu = sum k / sum T
and s^2 the sample variance of k_i / T_i,

    Var(k_i / T_i) = mu / T_i + mu^2 / alpha   =>   mu^2 / alpha = s^2 - mu * mean(1 / T_i)

If the right side is <= 0 there is no spread beyond Poisson noise, and every provision gets
the pooled rate (complete pooling, capped as in `rates`).

Posterior: Gamma(alpha + k_i, beta + T_i). The probability of at least one amendment in the
next h years (negative-binomial predictive) is

    P(N >= 1) = 1 - ( beta' / (beta' + h) ) ** alpha'

It is a FORECAST, so it renders as a number only with a SERVABLE track record
(`calibration_contract`). Until then the module still computes and the page shows no number.

## Verified here

`_test()` draws true rates from a known Gamma, simulates histories and the following year,
and measures calibration and Brier score against the pooled constant rate.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from checker.forecast import FORECAST, Estimate, EstimateError

SHAPE_CAP = 1e6


def _gser(a: float, x: float) -> float:
    s = term = 1.0 / a
    ap = a
    for _ in range(1000):
        ap += 1.0
        term *= x / ap
        s += term
        if abs(term) < abs(s) * 3e-16:
            return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    raise EstimateError("incomplete gamma series did not converge")


def _gcf(a: float, x: float) -> float:
    fpmin = 1e-300
    b = x + 1.0 - a
    c, d = 1.0 / fpmin, 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = d if abs(d) > fpmin else fpmin
        c = b + an / c
        c = c if abs(c) > fpmin else fpmin
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-16:
            return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    raise EstimateError("incomplete gamma fraction did not converge")


def gamma_cdf(x: float, shape: float, rate: float) -> float:
    """P(X <= x) for X ~ Gamma(shape, rate), via the regularised lower incomplete gamma."""
    if shape <= 0 or rate <= 0:
        raise EstimateError("Gamma parameters must be positive")
    z = x * rate
    if z <= 0:
        return 0.0
    return _gser(shape, z) if z < shape + 1.0 else 1.0 - _gcf(shape, z)


def gamma_ppf(q: float, shape: float, rate: float) -> float:
    lo, hi = 0.0, max(1.0, 10.0 * shape) / rate
    while gamma_cdf(hi, shape, rate) < q:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if gamma_cdf(mid, shape, rate) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass(frozen=True)
class RatePrior:
    shape: float
    rate: float
    pooled_rate: float
    strata: int


def fit_rate_prior(histories: list[tuple[int, float]]) -> RatePrior:
    """(events, years of exposure) per provision -> a Gamma prior on the yearly rate."""
    use = [(k, t) for k, t in histories if t > 0]
    if len(use) < 2:
        raise EstimateError("at least two provisions with exposure are needed")
    if any(k < 0 for k, _ in use):
        raise EstimateError("a negative event count is a data error")
    mu = sum(k for k, _ in use) / sum(t for _, t in use)
    if mu == 0.0:
        raise EstimateError("no amending event in any provision: there is no rate to pool, "
                            "and 'never' is not a forecast")
    r = [k / t for k, t in use]
    mr = sum(r) / len(r)
    s2 = sum((x - mr) ** 2 for x in r) / (len(r) - 1)
    between = s2 - mu * sum(1.0 / t for _, t in use) / len(use)
    shape = SHAPE_CAP if between <= 0 else mu * mu / between
    return RatePrior(shape, shape / mu, mu, len(use))


def p_change(events: int, years: float, prior: RatePrior, horizon: float, *,
             basis: str = "") -> Estimate:
    """P(at least one amendment within `horizon` years), with a 95% posterior band."""
    if horizon <= 0 or years < 0 or events < 0:
        raise EstimateError("horizon must be positive; history cannot be negative")
    a, b = prior.shape + events, prior.rate + years
    p = 1.0 - (b / (b + horizon)) ** a
    lam_lo, lam_hi = gamma_ppf(0.025, a, b), gamma_ppf(0.975, a, b)
    lo = 1.0 - math.exp(-lam_lo * horizon)
    hi = 1.0 - math.exp(-lam_hi * horizon)
    return Estimate(p, min(lo, p), max(hi, p), events,
                    "Gamma-Poisson (empirical Bayes), negative-binomial predictive",
                    FORECAST, "a statement that the law will or will not change",
                    basis=basis,
                    notes=(f"{events} event(s) in {years:g} years for this provision; "
                           f"prior pooled from {prior.strata} provisions",))


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

    print("forecast.events")

    # ── the Gamma functions against closed forms ────────────────────────────
    # Gamma(1, r) is Exponential(r): cdf = 1 - exp(-r x)
    check(abs(gamma_cdf(2.0, 1.0, 0.5) - (1 - math.exp(-1.0))) < 1e-12,
          "Gamma(1, 0.5) is exponential: cdf(2) = 1 - e^-1")
    # Gamma(2, 1): cdf = 1 - e^-x (1 + x)
    check(abs(gamma_cdf(3.0, 2.0, 1.0) - (1 - math.exp(-3) * 4)) < 1e-12,
          "Gamma(2, 1): cdf(3) = 1 - 4e^-3")
    check(abs(gamma_cdf(gamma_ppf(0.975, 3.7, 2.2), 3.7, 2.2) - 0.975) < 1e-9,
          "the Gamma quantile inverts the cdf")

    # ── calibration by simulation from a known prior ────────────────────────
    rng = random.Random(20260930)
    true_shape, true_rate = 0.8, 4.0            # mean 0.2 amendments per provision-year

    def poisson(lam: float) -> int:
        k, p, L = 0, 1.0, math.exp(-lam)
        while True:
            p *= rng.random()
            if p <= L:
                return k
            k += 1

    preds, outcomes, pooled_preds = [], [], []
    for _ in range(5):
        hist, lams = [], []
        for _ in range(400):
            lam = rng.gammavariate(true_shape, 1.0 / true_rate)
            t = rng.uniform(5, 15)
            hist.append((poisson(lam * t), t))
            lams.append(lam)
        prior = fit_rate_prior(hist)
        for (k, t), lam in zip(hist, lams):
            preds.append(p_change(k, t, prior, 1.0).value)
            pooled_preds.append(1.0 - math.exp(-prior.pooled_rate))
            outcomes.append(1 if poisson(lam) >= 1 else 0)
    n = len(preds)
    mean_p, obs = sum(preds) / n, sum(outcomes) / n
    from checker.interval import wilson
    lo, hi = wilson(sum(outcomes), n)
    check(lo <= mean_p <= hi,
          f"mean forecast {mean_p:.4f} sits inside the observed rate's interval "
          f"[{lo:.4f}, {hi:.4f}] (observed {obs:.4f}, n={n})")
    # calibration in the tails, where a bad model shows first
    top = sorted(zip(preds, outcomes), reverse=True)[: n // 10]
    t_p, t_o = sum(p for p, _ in top) / len(top), sum(o for _, o in top)
    t_lo, t_hi = wilson(t_o, len(top))
    check(t_lo <= t_p <= t_hi,
          f"top decile: forecast {t_p:.3f}, observed {t_o / len(top):.3f} "
          f"(interval [{t_lo:.3f}, {t_hi:.3f}])")
    brier = sum((p - o) ** 2 for p, o in zip(preds, outcomes)) / n
    brier0 = sum((p - o) ** 2 for p, o in zip(pooled_preds, outcomes)) / n
    check(brier < brier0,
          f"pooled history beats one rate for everything: Brier {brier:.4f} vs {brier0:.4f}")

    # ── the corpus as it is: a forecast is computed, and NOT rendered ──────
    real = p_change(1, 12.0, fit_rate_prior([(1, 12.0), (0, 12.0), (2, 12.0), (0, 12.0),
                                             (3, 12.0)]), 1.0)
    txt = real.render(None)
    check(txt.startswith("No forecast shown") and f"{real.value:.3g}" not in txt,
          "with no track record, the forecast is computed but no number is shown")
    try:
        fit_rate_prior([(0, 10.0), (0, 12.0)])
        check(False, "refuses to pool when no provision has ever changed")
    except EstimateError:
        check(True, "refuses to pool when no provision has ever changed")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
