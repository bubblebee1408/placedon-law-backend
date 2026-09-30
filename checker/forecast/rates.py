"""Rates for small strata: Beta-Binomial partial pooling, and exact Beta intervals.

PLAN_24 04 §3.3. A bench with 3 decided compounding applications cannot support a rate of
its own; a forum with 300 can. Complete pooling (one rate for everyone) hides real
differences, and no pooling (each stratum alone) prints noise as a finding. Partial pooling
sits between them by an amount the data chooses.

## The model

    y_j | p_j ~ Binomial(n_j, p_j),     p_j ~ Beta(a, b)

The prior is estimated from the strata themselves (empirical Bayes, method of moments).
With m the pooled rate and rho = 1/(a+b+1) the intra-class correlation,

    Var(y_j / n_j) = m(1-m) [ rho + (1 - rho) / n_j ]

so, with s^2 the sample variance of the raw rates and h = mean(1/n_j),

    rho_hat = ( s^2 / (m(1-m)) - h ) / (1 - h),      a + b = 1/rho_hat - 1.

If rho_hat <= 0 the strata show no more spread than binomial noise alone would give, and
the honest answer is complete pooling. It is capped at a+b = POOL_CAP rather than infinity
so the posterior stays a proper Beta.

The posterior for stratum j is Beta(a + y_j, b + n_j - y_j), with mean (y_j + a)/(n_j + a + b).
**A stratum with n_j < a + b is mostly prior**, and every estimate says so.

## Verified here, not asserted

`_test()` simulates strata from a known Beta, fits the prior, and measures that the pooled
estimates have lower squared error than the raw rates. It also checks the Beta quantile
function against closed forms. Numbers are printed, not quoted from a paper.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import exp, lgamma, log

from checker.forecast import DESCRIPTIVE, Estimate, EstimateError

POOL_CAP = 1e6          # a + b when the data show no between-stratum spread
_EPS = 3e-14
_FPMIN = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularised incomplete beta (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _FPMIN else _FPMIN)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _FPMIN else _FPMIN)
        c = 1.0 + aa / c
        c = c if abs(c) > _FPMIN else _FPMIN
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _FPMIN else _FPMIN)
        c = 1.0 + aa / c
        c = c if abs(c) > _FPMIN else _FPMIN
        de = d * c
        h *= de
        if abs(de - 1.0) < _EPS:
            return h
    raise EstimateError(f"incomplete beta did not converge (a={a}, b={b}, x={x})")


def beta_cdf(x: float, a: float, b: float) -> float:
    """P(X <= x) for X ~ Beta(a, b). Exact to ~1e-12, standard library only."""
    if a <= 0 or b <= 0:
        raise EstimateError("Beta parameters must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def beta_ppf(q: float, a: float, b: float) -> float:
    """The q-quantile of Beta(a, b), by bisection on the exact CDF."""
    if not 0.0 <= q <= 1.0:
        raise EstimateError("quantile level must be in [0, 1]")
    lo, hi = 0.0, 1.0
    for _ in range(60):             # 2^-60 < 1e-18: past double precision
        mid = (lo + hi) / 2.0
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@dataclass(frozen=True)
class Prior:
    a: float
    b: float
    rho: float              # intra-class correlation; 0 means complete pooling
    strata: int

    @property
    def strength(self) -> float:
        """a + b: how many cases' worth of evidence the prior is worth."""
        return self.a + self.b


def fit_prior(strata: list[tuple[int, int]]) -> Prior:
    """Method-of-moments Beta prior from (successes, trials) per stratum."""
    usable = [(y, n) for y, n in strata if n > 0]
    if len(usable) < 2:
        raise EstimateError("at least two strata with cases are needed to fit a prior")
    for y, n in usable:
        if not 0 <= y <= n:
            raise EstimateError(f"successes {y} outside 0..{n}")
    total_y = sum(y for y, _ in usable)
    total_n = sum(n for _, n in usable)
    m = total_y / total_n
    if m in (0.0, 1.0):
        # every stratum all-success or all-failure: nothing to shrink between
        return Prior(max(m, 1e-9) * POOL_CAP, max(1 - m, 1e-9) * POOL_CAP, 0.0, len(usable))
    rates = [y / n for y, n in usable]
    mean_r = sum(rates) / len(rates)
    s2 = sum((r - mean_r) ** 2 for r in rates) / (len(rates) - 1)
    h = sum(1.0 / n for _, n in usable) / len(usable)
    rho = (s2 / (m * (1.0 - m)) - h) / (1.0 - h) if h < 1.0 else 0.0
    if rho <= 0.0:
        return Prior(m * POOL_CAP, (1.0 - m) * POOL_CAP, 0.0, len(usable))
    rho = min(rho, 1.0 - 1e-9)
    ab = 1.0 / rho - 1.0
    return Prior(m * ab, (1.0 - m) * ab, rho, len(usable))


def pooled_rate(y: int, n: int, prior: Prior, *, basis: str = "") -> Estimate:
    """The partially pooled rate for one stratum, with an exact 95% Beta interval."""
    if not 0 <= y <= n:
        raise EstimateError(f"successes {y} outside 0..{n}")
    a, b = prior.a + y, prior.b + (n - y)
    mean = a / (a + b)
    lo, hi = beta_ppf(0.025, a, b), beta_ppf(0.975, a, b)
    lo, hi = min(lo, mean), max(hi, mean)
    notes = ()
    if n < prior.strength:
        notes = (f"mostly prior: this stratum has {n} cases against a prior worth "
                 f"{prior.strength:.1f}",)
    return Estimate(mean, lo, hi, n, "Beta-Binomial partial pooling (empirical Bayes)",
                    DESCRIPTIVE, "a prediction for any particular matter",
                    basis=basis, notes=notes)


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

    print("forecast.rates")

    # ── the Beta functions against closed forms ────────────────────────────
    check(abs(beta_cdf(0.3, 1, 1) - 0.3) < 1e-12, "Beta(1,1) is uniform: cdf(0.3)=0.3")
    check(abs(beta_cdf(0.5, 2, 2) - 0.5) < 1e-12, "Beta(2,2) is symmetric: cdf(0.5)=0.5")
    # Beta(2,1) has cdf x^2; Beta(1,3) has cdf 1-(1-x)^3
    check(abs(beta_cdf(0.7, 2, 1) - 0.49) < 1e-12, "Beta(2,1): cdf(0.7) = 0.7^2")
    check(abs(beta_cdf(0.2, 1, 3) - (1 - 0.8 ** 3)) < 1e-12, "Beta(1,3): cdf(0.2) = 1-0.8^3")
    check(abs(beta_ppf(0.49, 2, 1) - 0.7) < 1e-9, "the quantile inverts the cdf")
    check(abs(beta_cdf(beta_ppf(0.025, 7.5, 31.2), 7.5, 31.2) - 0.025) < 1e-9,
          "...at non-integer parameters too")

    # ── recovery and shrinkage, by simulation from a KNOWN prior ────────────
    rng = random.Random(20260930)
    true_a, true_b = 4.0, 12.0          # mean 0.25, strength 16
    wins = 0
    ratios = []
    for _ in range(60):
        strata, truth = [], []
        for _ in range(40):
            p = rng.betavariate(true_a, true_b)
            n = rng.randint(3, 60)
            y = sum(rng.random() < p for _ in range(n))
            strata.append((y, n))
            truth.append(p)
        prior = fit_prior(strata)
        raw = sum((y / n - p) ** 2 for (y, n), p in zip(strata, truth))
        pooled = sum(((y + prior.a) / (n + prior.strength) - p) ** 2
                     for (y, n), p in zip(strata, truth))
        ratios.append(pooled / raw)
        wins += pooled < raw
    mean_ratio = sum(ratios) / len(ratios)
    check(wins >= 54, f"pooling beats raw rates in {wins}/60 simulated forums")
    check(mean_ratio < 0.8,
          f"...mean squared error falls to {mean_ratio:.2f} of the raw rates' on average")

    # a single run's fitted prior should be in the neighbourhood of the truth
    prior = fit_prior(strata)
    check(0.15 < prior.a / prior.strength < 0.35,
          f"fitted prior mean {prior.a / prior.strength:.3f} is near the true 0.25")

    # ── no spread beyond noise -> complete pooling, not a false difference ──
    flat = [(10, 40), (11, 40), (9, 40), (10, 40), (10, 40)]
    fp = fit_prior(flat)
    check(fp.rho == 0.0 and fp.strength == POOL_CAP,
          "strata that differ only by binomial noise are pooled completely")

    # ── the 'mostly prior' flag, and the interval ──────────────────────────
    small = pooled_rate(2, 3, Prior(4.0, 12.0, 1 / 17, 40))
    check(small.notes and small.notes[0].startswith("mostly prior"),
          f"a 3-case stratum is flagged as mostly prior ({small.value:.3f})")
    check(small.value < 2 / 3, "...and pulled well below its raw 2/3 toward the forum rate")
    big = pooled_rate(200, 300, Prior(4.0, 12.0, 1 / 17, 40))
    check(not big.notes and abs(big.value - 200 / 300) < 0.03,
          f"a 300-case stratum barely moves ({big.value:.3f} vs raw 0.667)")
    check(big.high - big.low < small.high - small.low,
          "...and its interval is narrower than the small stratum's")

    for bad in ([(1, 5)], [(6, 5), (1, 5)]):
        try:
            fit_prior(bad)
            check(False, f"refuses {bad}")
        except EstimateError:
            check(True, f"refuses {bad}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
