"""How long things take, counting the cases that have not finished yet.

PLAN_24 04 §3.2. "Average time of disposed cases" is the number everyone computes and it is
biased in the direction that matters: the cases still pending are the slow ones, and
dropping them makes every forum look faster than it is. Kaplan-Meier keeps them, as
CENSORED observations: known to have lasted at least this long.

## The estimator

With event times t_1 < t_2 < ..., d_i events at t_i and n_i cases still at risk:

    S(t)       = prod_{t_i <= t} (1 - d_i / n_i)                         Kaplan & Meier 1958
    Var S(t)   ~ S(t)^2 * sum_{t_i <= t} d_i / (n_i (n_i - d_i))          Greenwood
    95% band   : S(t) ** exp(+-1.96 * se_ll),  se_ll = sqrt(sum) / |log S(t)|   (log-log)

The log-log band stays inside [0, 1], which the plain Greenwood band does not.

The median is the first t with S(t) <= 0.5. Its interval is read off the band: the lower
limit is the first t where the LOWER band falls to 0.5, the upper limit the first t where
the UPPER band does. If the upper band never reaches 0.5, the upper limit is "not reached",
and it is reported that way, never replaced by the largest observed time.

## Verified here

`_test()` draws exponential durations with random censoring, where the true median is
ln 2 / lambda, and measures how often the interval covers the truth over 200 samples.
Without censoring, KM must equal one minus the empirical CDF exactly.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import exp, log, sqrt

from checker.forecast import DESCRIPTIVE, Estimate, EstimateError
from checker.interval import Z95


@dataclass(frozen=True)
class Step:
    t: float
    at_risk: int
    events: int
    survival: float
    low: float
    high: float


def kaplan_meier(durations: list[float], observed: list[bool]) -> list[Step]:
    """KM steps at each distinct event time. `observed[i]` is False for a censored case."""
    if len(durations) != len(observed):
        raise EstimateError("durations and observed flags differ in length")
    if not durations:
        raise EstimateError("no cases")
    if any(d < 0 for d in durations):
        raise EstimateError("a negative duration is a data error, not a case")
    pairs = sorted(zip(durations, observed))
    n = len(pairs)
    steps: list[Step] = []
    s, gw, i = 1.0, 0.0, 0
    while i < n:
        t = pairs[i][0]
        d = c = 0
        while i < n and pairs[i][0] == t:
            if pairs[i][1]:
                d += 1
            else:
                c += 1
            i += 1
        at_risk = n - (i - d - c)
        if d:
            s *= 1.0 - d / at_risk
            if at_risk > d:
                gw += d / (at_risk * (at_risk - d))
            if 0.0 < s < 1.0 and gw > 0:
                se = sqrt(gw) / abs(log(s))
                lo, hi = s ** exp(Z95 * se), s ** exp(-Z95 * se)
            else:
                lo = hi = s
            steps.append(Step(t, at_risk, d, s, lo, hi))
    return steps


def median(durations: list[float], observed: list[bool], *, basis: str = "",
           unit: str = "months") -> Estimate:
    """Median time to the event, with its 95% interval read from the log-log band."""
    steps = kaplan_meier(durations, observed)
    events = sum(observed)
    if events == 0:
        raise EstimateError("no case has reached the event; there is no median to estimate")
    med = next((st.t for st in steps if st.survival <= 0.5), None)
    if med is None:
        raise EstimateError("fewer than half the cases have reached the event: the median is "
                            "not reached, and no number is given")
    # The LOWER survival band is the pessimistic curve: it falls to 0.5 first, so it gives
    # the lower limit of the median. The upper band gives the upper limit.
    lo = next((st.t for st in steps if st.low <= 0.5), med)
    hi = next((st.t for st in steps if st.high <= 0.5), None)
    notes = [f"{len(durations) - events} of {len(durations)} cases censored (still pending)"]
    if hi is None:
        notes.append("upper limit not reached: longer than the longest observed event")
        hi = float("inf")
    return Estimate(med, min(lo, med), hi, len(durations),
                    "Kaplan-Meier median, log-log 95% band", DESCRIPTIVE,
                    "a prediction for your matter", basis=basis,
                    notes=tuple(notes) + (f"unit: {unit}",))


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

    print("forecast.survival")

    # ── no censoring: KM is exactly 1 - ECDF ───────────────────────────────
    d = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    steps = kaplan_meier(d, [True] * len(d))
    exact = all(abs(st.survival - (1 - sum(x <= st.t for x in d) / len(d))) < 1e-12
                for st in steps)
    check(exact, "with no censoring, KM equals one minus the empirical CDF at every step")

    # ── a hand-worked censored example (textbook shape) ─────────────────────
    #   times 1,2+,3,3,4+,5 : S(1)=5/6, S(3)=5/6*(1-2/4)=5/12, S(5)=0
    st = kaplan_meier([1, 2, 3, 3, 4, 5], [True, False, True, True, False, True])
    got = [(s.t, round(s.survival, 6)) for s in st]
    check(got == [(1, round(5 / 6, 6)), (3, round(5 / 12, 6)), (5, 0.0)],
          f"hand-worked censored example matches ({got})")

    # ── the bias this module exists to remove ──────────────────────────────
    rng = random.Random(20260930)
    lam = 0.1                                 # true median ln2/0.1 = 6.93
    true_med = log(2) / lam
    dur, obs = [], []
    for _ in range(400):
        t = rng.expovariate(lam)
        c = rng.uniform(0, 20)
        dur.append(min(t, c))
        obs.append(t <= c)
    naive = sorted(x for x, o in zip(dur, obs) if o)[sum(obs) // 2]
    km = median(dur, obs).value
    check(naive < km and abs(km - true_med) < abs(naive - true_med),
          f"dropping pending cases understates the median ({naive:.2f}); "
          f"KM ({km:.2f}) is closer to the truth ({true_med:.2f})")

    # ── interval coverage over repeated samples ───────────────────────────
    covered = reps = 0
    for _ in range(200):
        dur, obs = [], []
        for _ in range(150):
            t = rng.expovariate(lam)
            c = rng.uniform(0, 25)
            dur.append(min(t, c))
            obs.append(t <= c)
        e = median(dur, obs)
        reps += 1
        covered += e.low <= true_med <= e.high
    check(covered / reps >= 0.90,
          f"the 95% interval covers the true median in {covered}/{reps} samples")

    # ── refusals ─────────────────────────────────────────────────────────
    try:
        median([5, 6, 7, 8], [True, False, False, False])
        check(False, "refuses a median when fewer than half the cases have ended")
    except EstimateError as e:
        check("not reached" in str(e),
              "refuses a median when fewer than half the cases have ended")
    try:
        kaplan_meier([1, -2], [True, True])
        check(False, "refuses a negative duration")
    except EstimateError:
        check(True, "refuses a negative duration")
    e = median([1, 2, 3, 10, 11, 12], [True, True, True, False, False, False])
    check(e.high == float("inf") and any("not reached" in n for n in e.notes),
          "an upper limit beyond the data is reported as not reached, not invented")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
