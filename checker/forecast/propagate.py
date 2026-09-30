"""What-if under uncertainty: the probability that a DETERMINISTIC rule applies when a
FACT is uncertain. The law stays exact; only the facts are uncertain.

This is the "think beyond the data" the founder asked for, in the one form that cannot
turn into a guess about the law. In-house counsel rarely know next year's turnover. They
know a range. The question "will we be a small company on 1 April?" then has an honest
probabilistic answer:

    P(rule applies) = P( decider(facts) is True ),  facts ~ the stated distributions

The decider is the Ring 0 code itself, passed in as a callable. Ring 3 calls Ring 0 and
never the other way round (`checker/rings.py`). The rule is never softened, sampled or
approximated. If the decider refuses, for example because a threshold is not attested,
the refusal propagates. **A refusal is not a probability.**

## Method

Monte Carlo with a seeded generator, n draws. The estimate is k/n, and its interval is the
Wilson interval, which here measures Monte Carlo error ONLY. The uncertainty the user
declared is already inside the probability. Single-threshold rules also have an exact
answer (the distribution's CDF), and `_test()` checks the simulation against it.

`swing()` is one-at-a-time sensitivity. For each uncertain fact, the probability is
recomputed with that fact pinned at its 5th and 95th percentiles. That tells counsel which
unknown actually matters, which is often the more useful answer.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist
from typing import Callable, Union

from checker.forecast import HYPOTHETICAL, Estimate, EstimateError
from checker.interval import wilson


@dataclass(frozen=True)
class Uniform:
    lo: float
    hi: float

    def sample(self, rng: random.Random) -> float:
        return rng.uniform(self.lo, self.hi)

    def cdf(self, x: float) -> float:
        return min(1.0, max(0.0, (x - self.lo) / (self.hi - self.lo)))

    def ppf(self, q: float) -> float:
        return self.lo + q * (self.hi - self.lo)


@dataclass(frozen=True)
class Triangular:
    lo: float
    mode: float
    hi: float

    def sample(self, rng: random.Random) -> float:
        return rng.triangular(self.lo, self.hi, self.mode)

    def cdf(self, x: float) -> float:
        a, c, b = self.lo, self.mode, self.hi
        if x <= a:
            return 0.0
        if x >= b:
            return 1.0
        if x <= c:
            return (x - a) ** 2 / ((b - a) * (c - a))
        return 1.0 - (b - x) ** 2 / ((b - a) * (b - c))

    def ppf(self, q: float) -> float:
        a, c, b = self.lo, self.mode, self.hi
        fc = (c - a) / (b - a)
        if q <= fc:
            return a + math.sqrt(q * (b - a) * (c - a))
        return b - math.sqrt((1 - q) * (b - a) * (b - c))


@dataclass(frozen=True)
class Normal:
    mu: float
    sd: float

    def sample(self, rng: random.Random) -> float:
        return rng.gauss(self.mu, self.sd)

    def cdf(self, x: float) -> float:
        return NormalDist(self.mu, self.sd).cdf(x)

    def ppf(self, q: float) -> float:
        return NormalDist(self.mu, self.sd).inv_cdf(q)


Dist = Union[Uniform, Triangular, Normal]
Fact = Union[Dist, float, int, bool, str]


def _is_dist(v: object) -> bool:
    return isinstance(v, (Uniform, Triangular, Normal))


def probability_applies(decider: Callable[[dict], bool], facts: dict[str, Fact], *,
                        n: int = 20000, seed: int = 20260930,
                        basis: str = "") -> Estimate:
    """P(decider(facts) is True) under the declared uncertainty in `facts`."""
    if n < 100:
        raise EstimateError("fewer than 100 draws cannot bound Monte Carlo error usefully")
    uncertain = sorted(k for k, v in facts.items() if _is_dist(v))
    rng = random.Random(seed)
    k = 0
    for _ in range(n):
        draw = {name: (v.sample(rng) if _is_dist(v) else v) for name, v in facts.items()}
        try:
            out = decider(draw)
        except EstimateError:
            raise
        except Exception as exc:  # a Ring 0 refusal, e.g. ThresholdUnavailable
            raise EstimateError(f"the rule could not be decided, so no probability exists: "
                                f"{type(exc).__name__}: {exc}") from exc
        if not isinstance(out, bool):
            raise EstimateError("a decider must return True or False, not a score")
        k += out
    lo, hi = wilson(k, n)
    p = k / n
    return Estimate(p, min(lo, p), max(hi, p), n,
                    "Monte Carlo over declared fact uncertainty; interval is simulation error",
                    HYPOTHETICAL,
                    "uncertainty about the law, which is applied exactly; only the facts "
                    "listed as uncertain vary",
                    basis=basis,
                    notes=(f"uncertain facts: {', '.join(uncertain) or 'none'}",))


def swing(decider: Callable[[dict], bool], facts: dict[str, Fact], *,
          n: int = 5000, seed: int = 20260930) -> dict[str, tuple[float, float]]:
    """For each uncertain fact: P(applies) with it pinned at its 5th and 95th percentile."""
    out = {}
    for name, v in facts.items():
        if not _is_dist(v):
            continue
        pinned = []
        for q in (0.05, 0.95):
            f = dict(facts)
            f[name] = v.ppf(q)
            pinned.append(probability_applies(decider, f, n=n, seed=seed).value)
        out[name] = (pinned[0], pinned[1])
    return out


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

    print("forecast.propagate")

    # ── simulation against exact answers ───────────────────────────────────
    over50 = lambda f: f["turnover_cr"] > 50
    e = probability_applies(over50, {"turnover_cr": Uniform(40, 60)})
    check(e.low <= 0.5 <= e.high, f"Uniform(40,60) > 50: exact 0.5, simulated {e.value:.4f}")
    tri = Triangular(30, 45, 70)
    e = probability_applies(over50, {"turnover_cr": tri})
    exact = 1 - tri.cdf(50)
    check(e.low <= exact <= e.high,
          f"Triangular(30,45,70) > 50: exact {exact:.4f}, simulated {e.value:.4f}")
    check(abs(tri.cdf(tri.ppf(0.3)) - 0.3) < 1e-12, "triangular ppf inverts its cdf")

    either = lambda f: f["turnover_cr"] > 50 or f["paid_up_cr"] > 10
    facts = {"turnover_cr": Uniform(40, 60), "paid_up_cr": Normal(8, 2)}
    e = probability_applies(either, facts)
    exact = 1 - (1 - 0.5) * NormalDist(8, 2).cdf(10)
    check(e.low <= exact <= e.high,
          f"compound OR rule: exact {exact:.4f}, simulated {e.value:.4f}")

    # ── a REAL Ring 0 threshold, read from the engine, never typed here ─────
    from datetime import date
    from checker import prescribed_thresholds as pt
    as_of = date(2026, 9, 30)
    try:
        cap, turn = pt.operative_small_company_limits(as_of)
        cap_cr, turn_cr = cap.rupees / 1e7, turn.rupees / 1e7

        from functools import lru_cache
        limits = lru_cache(maxsize=8)(pt.operative_small_company_limits)

        def small_limbs(f: dict) -> bool:
            # only the two monetary limbs of s.2(85); the exclusions (holding,
            # subsidiary, s.8, special Act) are separate facts and are not modelled here.
            # The limits are the engine's, looked up per as_of date (cached: the lookup
            # re-verifies artifacts on disk and is not meant to run 20,000 times).
            lim_cap, lim_turn = limits(f["as_of"])
            return (f["paid_up_rupees"] <= lim_cap.rupees
                    and f["turnover_rupees"] <= lim_turn.rupees)

        facts = {"as_of": as_of, "paid_up_rupees": 5e7,
                 "turnover_rupees": Uniform((turn_cr - 20) * 1e7, (turn_cr + 5) * 1e7)}
        e = probability_applies(small_limbs, facts, n=4000)
        exact = 20 / 25
        check(e.low <= exact <= e.high,
              f"s.2(85) monetary limbs with the engine's limits (₹{cap_cr:g} cr / ₹{turn_cr:g} cr): "
              f"turnover ~ U(limit-20, limit+5) cr -> exact {exact:.2f}, simulated {e.value:.4f}")
        sw = swing(small_limbs, facts, n=2000)
        lo_p, hi_p = sw["turnover_rupees"]
        check(lo_p == 1.0 and hi_p == 0.0,
              "swing names turnover as the fact that decides it (1.0 at p5, 0.0 at p95)")
    except pt.ThresholdUnavailable:
        check(True, "the engine does not serve the limits today, so no probability is formed")

    # ── a Ring 0 refusal is not a probability ──────────────────────────────
    def refuses(_f: dict) -> bool:
        raise LookupError("threshold not attested")
    try:
        probability_applies(refuses, {"x": Uniform(0, 1)})
        check(False, "a refusing decider yields no probability")
    except EstimateError as exc:
        check("no probability exists" in str(exc), "a refusing decider yields no probability")
    try:
        probability_applies(lambda f: 0.7, {"x": Uniform(0, 1)})
        check(False, "a decider returning a score is refused")
    except EstimateError:
        check(True, "a decider returning a score is refused: rules are True or False")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
