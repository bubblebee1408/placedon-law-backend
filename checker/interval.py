"""Honest error bars, in the standard library.

Every proportion this repo reports -- p@1 0.71, recall@5 0.91, 78% accuracy --
is an estimate from a finite sample, and until now each was printed as though it
were a measurement. At n=70 the difference matters: two retrievers separated by
two percentage points are not distinguishable, and saying so requires an interval.

## Why Wilson and not the textbook formula

The Wald interval `p +- z*sqrt(p(1-p)/n)` is the one everyone remembers and it is
wrong in exactly the regime this repo lives in. At 19/20 it returns
[0.854, 1.046] -- an interval that (a) excludes the observed value's own
neighbourhood asymmetrically and (b) claims probability mass above 1.0, which is
not a thing. Wilson has no such failure, needs no continuity fudge, and behaves at
the boundary where small legal corpora actually sit.

## Why exact tests and not normal approximations

`math.comb` is in the standard library, so the exact binomial sum costs nothing
and cannot mislead. The approximations err in whichever direction the algebra
happens to take them -- and for the small n this project has, that direction is
sometimes optimistic. An instrument that flatters us at small n is worse than no
instrument, because small n is the only time we consult it.

No third-party dependency. No randomness that is not seeded.
"""
from __future__ import annotations

import random
from math import comb, sqrt
from typing import Callable, Sequence

# 1.959963985 is the two-sided 95% normal quantile. Named, not inlined, because a
# magic 1.96 in a statistics module is how a 90% interval gets labelled 95%.
Z95 = 1.959963985


class IntervalError(ValueError):
    """An input that cannot bear the statistic asked of it."""


def _check_kn(k: int, n: int) -> None:
    if isinstance(k, bool) or isinstance(n, bool):
        raise IntervalError("k and n must be ints, not bools")
    if n <= 0:
        raise IntervalError(f"n must be positive, got {n}")
    if not 0 <= k <= n:
        raise IntervalError(f"k must lie in [0, {n}], got {k}")


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials.

        centre = (k + z^2/2) / (n + z^2)
        half   = (z / (n + z^2)) * sqrt( k(n-k)/n + z^2/4 )

    Never leaves [0, 1], and needs no special case at k=0 or k=n -- which is why
    it is used here instead of the Wald form that returns 1.046 at 19/20.
    """
    _check_kn(k, n)
    z2 = z * z
    denom = n + z2
    centre = (k + z2 / 2) / denom
    half = (z / denom) * sqrt(k * (n - k) / n + z2 / 4)
    return (max(0.0, centre - half), min(1.0, centre + half))


def binom_test(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided binomial test: P(outcome at most as likely as observed).

    Summed over the exact pmf via math.comb, not approximated. The two-sided form
    is the "method of small p-values": add every outcome whose probability does
    not exceed the observed one, with a tolerance so that exact ties -- which are
    routine at p=0.5 -- are included rather than lost to float comparison.
    """
    _check_kn(k, n)
    if not 0.0 <= p <= 1.0:
        raise IntervalError(f"p must lie in [0, 1], got {p}")

    def pmf(i: int) -> float:
        return comb(n, i) * (p ** i) * ((1 - p) ** (n - i))

    observed = pmf(k)
    tol = 1e-12 * max(1.0, observed)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= observed + tol))


def mcnemar(b: int, c: int) -> float:
    """Exact McNemar test on the two DISCORDANT counts of a paired comparison.

    b = cases the first system got and the second did not; c = the reverse.
    Concordant cases carry no information about a difference and are excluded by
    construction -- which is the whole point of pairing.

    Conditional on b+c discordant pairs, b ~ Binomial(b+c, 1/2) under the null,
    so this is the exact binomial test at p=0.5. No continuity correction and no
    chi-square approximation: at the n this repo has, the approximation is the
    part that would be wrong.
    """
    if b < 0 or c < 0:
        raise IntervalError(f"discordant counts cannot be negative: b={b}, c={c}")
    if b + c == 0:
        return 1.0          # no disagreement is no evidence, not a divide-by-zero
    return binom_test(b, b + c, 0.5)


def bootstrap_ci(sample: Sequence[float], statistic: Callable[[Sequence[float]], float],
                 *, reps: int = 2000, seed: int = 0, alpha: float = 0.05
                 ) -> tuple[float, float]:
    """Percentile bootstrap CI. Seeded, so a reported interval never moves.

    An unseeded bootstrap makes a number that changes between runs, which in a
    document a lawyer relies on is indistinguishable from a number that changed
    because the evidence did.
    """
    if not sample:
        raise IntervalError("cannot bootstrap an empty sample")
    if not 0.0 < alpha < 1.0:
        raise IntervalError(f"alpha must lie in (0, 1), got {alpha}")
    rng = random.Random(seed)
    n = len(sample)
    stats = sorted(statistic([sample[rng.randrange(n)] for _ in range(n)])
                   for _ in range(reps))
    lo_i = int((alpha / 2) * reps)
    hi_i = min(reps - 1, int((1 - alpha / 2) * reps))
    return (stats[lo_i], stats[hi_i])


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

    print("interval")

    # ── the L-15 audit's own number, reproduced. This test IS the audit. ──────
    lo, hi = wilson(19, 20)
    check(round(lo, 3) == 0.764 and round(hi, 3) == 0.991,
          f"wilson(19, 20) == (0.764, 0.991) — the audit's interval ({lo:.3f}, {hi:.3f})")

    # ── the failure mode that justifies choosing Wilson at all ───────────────
    wald_lo = 19 / 20 - Z95 * sqrt((19 / 20) * (1 / 20) / 20)
    wald_hi = 19 / 20 + Z95 * sqrt((19 / 20) * (1 / 20) / 20)
    check(wald_hi > 1.0 and hi <= 1.0,
          f"...where the Wald form claims mass above 1.0 ({wald_hi:.3f}) and Wilson does not ({hi:.3f})")
    check(round(wald_lo, 3) == 0.854,
          f"...and misses low too ({wald_lo:.3f} vs Wilson {lo:.3f})")

    # ── boundaries: 0/n and n/n must not explode or escape [0,1] ─────────────
    z0, z1 = wilson(0, 20)
    o0, o1 = wilson(20, 20)
    check(z0 == 0.0 and 0 < z1 < 1, f"wilson(0,20) sits on the floor ({z0:.3f},{z1:.3f})")
    check(o1 == 1.0 and 0 < o0 < 1, f"wilson(20,20) sits on the ceiling ({o0:.3f},{o1:.3f})")
    check(all(0.0 <= a <= 1.0 and 0.0 <= b <= 1.0
              for a, b in (wilson(k, 7) for k in range(8))),
          "no interval escapes [0,1] anywhere on a small n")

    # ── an impossible input is refused, not silently clamped ─────────────────
    for k, n, why in ((-1, 10, "negative k"), (11, 10, "k > n"), (1, 0, "n = 0")):
        try:
            wilson(k, n)
            check(False, f"{why} is refused")
        except IntervalError:
            check(True, f"{why} is refused")

    # ── exact binomial, against values that can be computed by hand ──────────
    check(abs(binom_test(10, 10) - 2 * 0.5 ** 10) < 1e-12,
          f"binom_test(10,10) is 2*(1/2)^10 exactly ({binom_test(10, 10):.6f})")
    check(abs(binom_test(5, 10) - 1.0) < 1e-12,
          f"a dead-even split cannot be evidence against fairness ({binom_test(5, 10):.3f})")

    # ── McNemar: fusion.py's OWN reported error sets ─────────────────────────
    # 11 cases only dense gets, 8 only BM25 gets. The docstring concludes dense
    # beats BM25; this is whether that conclusion is available at n=70.
    p = mcnemar(11, 8)
    check(round(p, 3) == 0.648,
          f"mcnemar(11, 8) == 0.648 — fusion.py's comparative is not established ({p:.3f})")
    check(mcnemar(0, 0) == 1.0, "no disagreement at all is no evidence of difference")
    check(mcnemar(20, 0) < 0.001, f"total disagreement is strong evidence ({mcnemar(20, 0):.2e})")

    # ── bootstrap: seeded, so a CI never moves between runs ──────────────────
    data = [float(i) for i in range(100)]
    a1 = bootstrap_ci(data, lambda s: sum(s) / len(s))
    a2 = bootstrap_ci(data, lambda s: sum(s) / len(s))
    check(a1 == a2, f"the bootstrap is seeded, so the interval is reproducible ({a1[0]:.3f})")
    check(a1[0] < 49.5 < a1[1], f"...and brackets the true mean ({a1[0]:.2f}, {a1[1]:.2f})")
    check(bootstrap_ci(data, lambda s: sum(s) / len(s), seed=1) != a1,
          "...and a different seed gives a different interval, as it must")
    try:
        bootstrap_ci([], lambda s: 0.0)
        check(False, "an empty sample is refused")
    except IntervalError:
        check(True, "an empty sample is refused")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
