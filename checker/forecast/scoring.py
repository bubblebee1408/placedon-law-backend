"""Scoring forecasts, and combining several: Brier, the Murphy decomposition, log-odds pooling.

A forecaster is judged on outcomes, never on how confident it sounds. This module holds the
three tools the learning loop needs for that (PLAN_24 05):

## Brier score, and why the decomposition matters

    BS = (1/N) sum (f_i - o_i)^2

On its own the Brier score mixes two different virtues. Murphy (1973) splits it exactly,
when forecasts take K distinct values f_k with n_k cases and observed frequency o_k each:

    BS = REL - RES + UNC
    REL = (1/N) sum n_k (f_k - o_k)^2        calibration error: lower is better
    RES = (1/N) sum n_k (o_k - obar)^2       resolution, i.e. discrimination: higher is better
    UNC = obar (1 - obar)                     the difficulty of the question itself

A forecaster that always predicts the base rate has REL ~ 0 and RES = 0. It scores UNC and
knows nothing. `skill` is 1 - BS / UNC: above 0 is better than the base rate.

## Log-odds pooling

Combining forecasters (the pooled base rate, a model, an LLM asked for a probability):

    logit p = d * sum_i w_i logit p_i,     sum w_i = 1

d = 1 is plain weighted log-odds pooling. d > 1 "extremizes" it. Satopaa et al. (2014)
report that this helps when forecasters hold partly independent information. That is a
property of the data, so here d defaults to 1. It may be raised only by the promotion gate
(PLAN_24 05 §5) on a frozen split, never by assertion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from checker.forecast import EstimateError


def brier(forecasts: list[float], outcomes: list[int]) -> float:
    if len(forecasts) != len(outcomes) or not forecasts:
        raise EstimateError("forecasts and outcomes must be non-empty and the same length")
    return sum((f - o) ** 2 for f, o in zip(forecasts, outcomes)) / len(forecasts)


@dataclass(frozen=True)
class Murphy:
    brier: float
    reliability: float
    resolution: float
    uncertainty: float

    @property
    def skill(self) -> float:
        return 0.0 if self.uncertainty == 0 else 1.0 - self.brier / self.uncertainty


def murphy(forecasts: list[float], outcomes: list[int], *, decimals: int = 6) -> Murphy:
    """Exact decomposition, grouping forecasts by their (rounded) value."""
    if any(o not in (0, 1) for o in outcomes):
        raise EstimateError("outcomes must be 0 or 1")
    n = len(forecasts)
    bs = brier(forecasts, outcomes)
    obar = sum(outcomes) / n
    groups: dict[float, list[int]] = {}
    for f, o in zip(forecasts, outcomes):
        groups.setdefault(round(f, decimals), []).append(o)
    rel = sum(len(os) * (f - sum(os) / len(os)) ** 2 for f, os in groups.items()) / n
    res = sum(len(os) * (sum(os) / len(os) - obar) ** 2 for os in groups.values()) / n
    return Murphy(bs, rel, res, obar * (1.0 - obar))


def _logit(p: float) -> float:
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    return math.log(p / (1.0 - p))


def pool(probs: list[float], weights: list[float] | None = None, d: float = 1.0) -> float:
    """Weighted log-odds pooling with an optional extremizing factor d (default 1)."""
    if not probs:
        raise EstimateError("nothing to pool")
    if any(not 0.0 <= p <= 1.0 for p in probs):
        raise EstimateError("probabilities must lie in [0, 1]")
    w = weights or [1.0 / len(probs)] * len(probs)
    if len(w) != len(probs) or abs(sum(w) - 1.0) > 1e-9 or any(x < 0 for x in w):
        raise EstimateError("weights must be non-negative and sum to 1")
    if d <= 0:
        raise EstimateError("d must be positive")
    z = d * sum(wi * _logit(p) for wi, p in zip(w, probs))
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

    print("forecast.scoring")
    import random
    rng = random.Random(20260930)

    # ── the decomposition is an identity, not an approximation ─────────────
    fs = [rng.choice([0.1, 0.3, 0.5, 0.7, 0.9]) for _ in range(5000)]
    os_ = [1 if rng.random() < f * 0.8 + 0.05 else 0 for f in fs]   # a miscalibrated source
    m = murphy(fs, os_)
    check(abs(m.brier - (m.reliability - m.resolution + m.uncertainty)) < 1e-12,
          f"BS = REL - RES + UNC exactly ({m.brier:.5f} = {m.reliability:.5f} - "
          f"{m.resolution:.5f} + {m.uncertainty:.5f})")
    check(m.reliability > 0.001, f"...and the miscalibration shows up as REL {m.reliability:.4f}")

    # ── the base-rate forecaster knows nothing, and the score says so ──────
    base = sum(os_) / len(os_)
    mb = murphy([base] * len(os_), os_)
    check(mb.resolution == 0.0 and abs(mb.skill) < 1e-12,
          "always forecasting the base rate has zero resolution and zero skill")
    check(m.skill > mb.skill, f"the informative forecaster has positive skill ({m.skill:.3f})")

    # ── pooling: properties that must hold whatever the data ───────────────
    check(abs(pool([0.73]) - 0.73) < 1e-12, "pooling one forecaster returns it unchanged")
    check(abs(pool([0.2, 0.8]) - 0.5) < 1e-12, "symmetric opinions pool to 0.5")
    check(pool([0.7, 0.8], d=2.0) > pool([0.7, 0.8]),
          "d > 1 extremizes away from 0.5 (allowed only after the gate)")
    check(abs(pool([0.3, 0.9], [1.0, 0.0]) - 0.3) < 1e-12, "a zero weight silences a forecaster")
    for bad in (dict(probs=[1.2]), dict(probs=[0.5, 0.5], weights=[0.7, 0.7]),
                dict(probs=[0.5], d=0)):
        try:
            pool(**bad)
            check(False, f"refuses {bad}")
        except EstimateError:
            check(True, f"refuses {bad}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
