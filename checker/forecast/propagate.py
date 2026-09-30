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


def _verdict(out: object) -> bool:
    """A decider's answer as True/False. INSUFFICIENT_DATA is an abstention, never False.

    Ring 0 deciders return `applicability.Result` (APPLIES / DOES_NOT_APPLY /
    INSUFFICIENT_DATA), sometimes with a Trace as `(Result, Trace)`. Mapping INSUFFICIENT_DATA
    to False would turn "we will not say" into probability mass for "does not apply" -- the
    silence-reads-as-no-obligation failure CLAUDE.md exists to prevent.
    """
    if isinstance(out, tuple) and out:
        out = out[0]
    if isinstance(out, bool):
        return out
    name = getattr(out, "name", None)
    if name == "APPLIES":
        return True
    if name == "DOES_NOT_APPLY":
        return False
    if name == "INSUFFICIENT_DATA":
        raise EstimateError("the rule answered INSUFFICIENT_DATA for some drawn facts, so no "
                            "probability exists: an abstention is not a 'does not apply'")
    raise EstimateError("a decider must answer True/False or APPLIES/DOES_NOT_APPLY, "
                        "not a score")


def probability_applies(decider: Callable[[dict], object], facts: dict[str, Fact], *,
                        rule_id: str, as_of: str, source: str,
                        n: int = 20000, seed: int = 20260930) -> Estimate:
    """P(the decider answers APPLIES) under the declared uncertainty in `facts`.

    `rule_id`, `as_of` and `source` are required: a probability about a rule that does not
    say which rule, on which date, from which instrument, is not one a lawyer can check.
    """
    if not (rule_id.strip() and as_of.strip() and source.strip()):
        raise EstimateError("rule_id, as_of and source are all required")
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
        k += _verdict(out)
    lo, hi = wilson(k, n)
    p = k / n
    return Estimate(p, min(lo, p), max(hi, p), n,
                    "Monte Carlo over declared fact uncertainty", HYPOTHETICAL,
                    "uncertainty about the law",
                    basis=f"{rule_id} as of {as_of} ({source})",
                    notes=(f"Rule {rule_id} as of {as_of} is applied exactly; only these facts "
                           f"vary: {', '.join(uncertain) or 'none'}",
                           f"The interval is simulation error over {n} draws, not a sample "
                           f"of {n} cases"))


def swing(decider: Callable[[dict], object], facts: dict[str, Fact], *,
          rule_id: str, as_of: str, source: str,
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
            pinned.append(probability_applies(decider, f, rule_id=rule_id, as_of=as_of,
                                              source=source, n=n, seed=seed).value)
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
    ctx = dict(rule_id="test.threshold", as_of="2026-09-30", source="synthetic")
    over50 = lambda f: f["turnover_cr"] > 50
    e = probability_applies(over50, {"turnover_cr": Uniform(40, 60)}, **ctx)
    check(e.low <= 0.5 <= e.high, f"Uniform(40,60) > 50: exact 0.5, simulated {e.value:.4f}")
    tri = Triangular(30, 45, 70)
    e = probability_applies(over50, {"turnover_cr": tri}, **ctx)
    exact = 1 - tri.cdf(50)
    check(e.low <= exact <= e.high,
          f"Triangular(30,45,70) > 50: exact {exact:.4f}, simulated {e.value:.4f}")
    check(abs(tri.cdf(tri.ppf(0.3)) - 0.3) < 1e-12, "triangular ppf inverts its cdf")

    either = lambda f: f["turnover_cr"] > 50 or f["paid_up_cr"] > 10
    facts = {"turnover_cr": Uniform(40, 60), "paid_up_cr": Normal(8, 2)}
    e = probability_applies(either, facts, **ctx)
    exact = 1 - (1 - 0.5) * NormalDist(8, 2).cdf(10)
    check(e.low <= exact <= e.high,
          f"compound OR rule: exact {exact:.4f}, simulated {e.value:.4f}")
    check(any("applied exactly" in n for n in e.notes) and "test.threshold" in e.basis,
          "the estimate names the rule, date and source, and says only the facts vary")

    # ── the REAL Ring 0 decider: checker.classify.small_company, proviso and all ──
    # The limits are the engine's own (prescribed_thresholds); nothing is typed here.
    from datetime import date
    from checker import prescribed_thresholds as pt
    from checker.classify import small_company
    from checker.company_profile import CompanyProfile, Figure, Money
    as_of = date(2026, 9, 30)
    try:
        cap, turn = pt.operative_small_company_limits(as_of)
    except pt.ThresholdUnavailable:
        cap = turn = None
    if cap is None:
        check(True, "the engine does not serve the limits today, so no probability is formed")
    else:
        turn_cr = turn.rupees / 1e7

        def small(f: dict):
            prof = CompanyProfile(
                company_class="private", incorporation_date=date(2019, 6, 1), as_of=as_of,
                latest_financial_year="2025-26", is_holding_company=f["holding"],
                is_subsidiary_company=False, is_section_8=False,
                governed_by_special_act=False,
                paid_up_capital=Figure(Money(int(5e7)), "2025-26"),
                turnover=Figure(Money(int(round(f["turnover_rupees"]))), "2025-26"))
            return small_company(prof)

        real = dict(rule_id="CA13-S2-85-SMALL (checker.classify.small_company)",
                    as_of=str(as_of), source="G.S.R. 880(E) limits via prescribed_thresholds")
        facts = {"holding": False,
                 "turnover_rupees": Uniform((turn_cr - 20) * 1e7, (turn_cr + 5) * 1e7)}
        e = probability_applies(small, facts, n=800, **real)
        check(e.low <= 0.80 <= e.high,
              f"real s.2(85) decider, engine limits (₹{cap.rupees / 1e7:g} cr / ₹{turn_cr:g} cr), "
              f"turnover ~ U(limit-20, limit+5) cr: exact 0.80, simulated {e.value:.4f}")
        sw = swing(small, facts, n=300, **real)
        check(sw["turnover_rupees"] == (1.0, 0.0),
              "swing names turnover as the fact that decides it (1.0 at p5, 0.0 at p95)")
        facts_h = dict(facts, holding=True)
        eh = probability_applies(small, facts_h, n=200, **real)
        check(eh.value == 0.0,
              "the s.2(85) proviso is applied: a holding company is never small, whatever turnover")
        # the trust-boundary finding: an unknown proviso fact is an ABSTENTION, not a 'no'
        try:
            probability_applies(small, dict(facts, holding=None), n=200, **real)
            check(False, "an unknown proviso fact yields no probability")
        except EstimateError as exc:
            check("INSUFFICIENT_DATA" in str(exc),
                  "an unknown proviso fact (INSUFFICIENT_DATA) yields no probability, "
                  "never probability mass for 'not small'")

    # ── a Ring 0 refusal is not a probability ──────────────────────────────
    def refuses(_f: dict) -> bool:
        raise LookupError("threshold not attested")
    try:
        probability_applies(refuses, {"x": Uniform(0, 1)}, **ctx)
        check(False, "a refusing decider yields no probability")
    except EstimateError as exc:
        check("no probability exists" in str(exc), "a refusing decider yields no probability")
    try:
        probability_applies(lambda f: 0.7, {"x": Uniform(0, 1)}, **ctx)
        check(False, "a decider returning a score is refused")
    except EstimateError:
        check(True, "a decider returning a score is refused: rules are True or False")
    try:
        probability_applies(over50, {"turnover_cr": Uniform(0, 1)}, rule_id="", as_of="x",
                            source="y")
        check(False, "a probability that does not name its rule is refused")
    except EstimateError:
        check(True, "a probability that does not name its rule, date and source is refused")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
