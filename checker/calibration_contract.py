"""No number reaches a reader without a track record that earns it.

## Why this module exists at all

`.claude/memory/LESSONS.md` L-15: a Bayesian belief engine was built here, built
properly, and deleted. The author fixed a real sign error in the source spec,
replaced an unsourced 0.6 prior with 0.5, kept the number away from users, and
added a build-failing check if a posterior reached a template. "All of that was
right, and the module still had to go." Their verdict on their own work: "I fixed
the arithmetic and kept the fabrication."

It went because calibration was unreachable at the available n. This module turns
that finding from an anecdote into an instrument, so the question can be asked
again -- of any proposed target -- and answered with arithmetic rather than
memory. It is expected to REFUSE most things. A refusal here is the module
working, not failing.

## The two floors, and why the exact sum matters

For a perfectly calibrated forecaster issuing probability p on n independent
items, the observed frequency k/n is Binomial(n, p)/n. Single-bin ECE is
E|k/n - p|, so even a PERFECT model shows apparent miscalibration:

    ece_floor(0.90, 20) = 0.0513    <- a target of ECE < 0.05 is failed by perfection
    ece_floor(0.10,  6) = 0.1063

The convenient closed form sqrt(2p(1-p)/(pi*n)) is used everywhere and is wrong in
the direction that matters. At n=20 it overstates the floor (0.0535); at n=6 it
UNDERSTATES it (0.0977 against the true 0.1063), making a hopeless target look
merely difficult. Small n is the only regime where this instrument is ever
consulted, so the exact binomial sum is the only acceptable form. `math.comb` is
in the standard library; it costs nothing.

Separately and sufficiently: with n outcomes the observable frequency lattice is
{0, 1/n, ..., 1}, spacing 1/n. At n=20 the spacing IS 0.05. You cannot observe a
miscalibration finer than the target you set. Two independent arguments, one
conclusion.

## The contract

A number may be rendered only if its estimator holds a live track record that is
SERVABLE: enough n for the target to sit above the floor, measured calibration
within that target, and skill over the naive baseline. Anything else DEGRADES to
an ordinal assessment rather than shrinking into a confident figure.

This is deliberately the same shape as the rule the rest of the engine already
follows: an unattested instrument is refused, not served. A number without a
track record is an unattested instrument.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import comb

from checker.interval import wilson
from checker.lattice import Lattice

# ── the contract states, best -> worst ────────────────────────────────────────
SERVABLE = "SERVABLE"              # the number may be rendered
NO_SKILL = "NO_SKILL"              # calibrated, but no better than the naive baseline
UNCALIBRATED = "UNCALIBRATED"      # measured error exceeds the target, above the floor
UNDERPOWERED = "UNDERPOWERED"      # n too small for the target to be observable at all
UNREGISTERED = "UNREGISTERED"      # no track record exists
STATES = (SERVABLE, NO_SKILL, UNCALIBRATED, UNDERPOWERED, UNREGISTERED)
_LATTICE = Lattice("calibration_contract", STATES)


class NotServable(ValueError):
    """A number was asked for that no track record supports."""


def ece_floor(p: float, n: int) -> float:
    """E|k/n - p| for k ~ Binomial(n, p). The apparent ECE of a PERFECT model.

    Exact. Never the normal approximation -- see the module docstring.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p must lie in [0, 1], got {p}")
    return sum(comb(n, k) * (p ** k) * ((1 - p) ** (n - k)) * abs(k / n - p)
               for k in range(n + 1))


def n_min(p: float, target: float) -> int:
    """The smallest n at which `target` sits at or above twice the noise floor.

    A floor merely EQUAL to the target means a perfect model fails about half the
    time, so the requirement is floor <= target/2. Solved by search rather than by
    inverting the approximation, because the approximation is what we distrust.
    """
    if target <= 0:
        raise ValueError(f"target must be positive, got {target}")
    need = target / 2
    # The floor falls monotonically in n, so bracket by doubling then bisect for
    # the exact minimum. Returning a power of two here would overstate the n a
    # person must go and find, which is the same kind of small dishonesty this
    # module exists to prevent.
    hi = 1
    while ece_floor(p, hi) > need:
        hi *= 2
        if hi > 1 << 24:
            raise ValueError(f"no feasible n for p={p}, target={target}")
    lo = hi // 2                      # floor(lo) > need >= floor(hi), or hi == 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if ece_floor(p, mid) <= need:
            hi = mid
        else:
            lo = mid
    return hi


@dataclass(frozen=True)
class TrackRecord:
    """What an estimator has actually done, not what it promises."""
    target_id: str
    n: int                      # resolved outcomes
    mean_forecast: float        # the p it issues (single-bin form)
    observed_rate: float        # the frequency that actually occurred
    target_ece: float           # the calibration target claimed
    baseline_score: float       # Brier of the naive/no-change baseline
    model_score: float          # Brier of the estimator

    @property
    def measured_ece(self) -> float:
        return abs(self.observed_rate - self.mean_forecast)

    @property
    def floor(self) -> float:
        return ece_floor(self.mean_forecast, self.n)

    @property
    def skill(self) -> float:
        """Brier skill score vs the baseline. <= 0 means the baseline is no worse."""
        if self.baseline_score <= 0:
            return 0.0
        return 1.0 - (self.model_score / self.baseline_score)


@dataclass(frozen=True)
class Verdict:
    state: str
    reason: str

    def __bool__(self) -> bool:
        return self.state == SERVABLE


def assess(record: TrackRecord | None) -> Verdict:
    """May this estimator's number be rendered? Usually not."""
    if record is None:
        return Verdict(UNREGISTERED,
                       "no track record exists; a number with no history is an "
                       "unattested instrument")
    r = record
    if r.floor > r.target_ece:
        need = n_min(r.mean_forecast, r.target_ece)
        return Verdict(UNDERPOWERED,
                       f"{r.target_id}: floor {r.floor:.4f} > target {r.target_ece:.4f} "
                       f"at n={r.n}. A PERFECTLY calibrated model fails this target, so "
                       f"the target sits below the instrument. n >= {need} would be "
                       f"needed for the target to be observable at all.")
    if r.measured_ece > r.target_ece:
        return Verdict(UNCALIBRATED,
                       f"{r.target_id}: measured ECE {r.measured_ece:.4f} exceeds target "
                       f"{r.target_ece:.4f} at n={r.n}, and the floor is only "
                       f"{r.floor:.4f}, so this is real miscalibration, not noise.")
    if r.skill <= 0:
        return Verdict(NO_SKILL,
                       f"{r.target_id}: Brier skill {r.skill:+.3f} over the naive "
                       f"baseline. Calibrated and useless is still useless; the "
                       f"baseline is the honest thing to report.")
    return Verdict(SERVABLE,
                   f"{r.target_id}: n={r.n}, ECE {r.measured_ece:.4f} within target "
                   f"{r.target_ece:.4f} (floor {r.floor:.4f}), skill {r.skill:+.3f}.")


def render_number(record: TrackRecord | None, value: float) -> str:
    """The number, with everything a reader needs to discount it. Or a refusal."""
    v = assess(record)
    if not v:
        raise NotServable(v.reason)
    r = record                                       # narrowed by assess
    lo, hi = wilson(round(r.observed_rate * r.n), r.n)
    return (f"{value:.2f} (95% CI {lo:.2f}–{hi:.2f}; n={r.n}; "
            f"base rate {r.observed_rate:.2f}; skill {r.skill:+.3f} vs baseline)")


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

    print("calibration_contract")

    # ── THE TEST THIS MODULE EXISTS FOR ─────────────────────────────────────
    # A PERFECTLY calibrated forecaster: it says 0.9 and 0.9 happens, exactly.
    perfect = TrackRecord("will-parliament-amend", n=20, mean_forecast=0.9,
                          observed_rate=0.9, target_ece=0.05,
                          baseline_score=0.09, model_score=0.05)
    v = assess(perfect)
    check(v.state == UNDERPOWERED,
          f"a PERFECTLY calibrated forecaster at p=0.9, n=20 is REFUSED ({v.state})")
    check("floor 0.0513 > target 0.0500" in v.reason,
          f"...and the refusal quotes the arithmetic ({v.reason[:56]}…)")
    check("n >= " in v.reason, "...and states the n that would be needed instead")
    try:
        render_number(perfect, 0.9)
        check(False, "rendering it raises rather than printing a number")
    except NotServable:
        check(True, "rendering it raises rather than printing a number")

    # ── the exact floor, against hand-computable values ─────────────────────
    check(round(ece_floor(0.9, 20), 4) == 0.0513, f"ece_floor(0.9,20)={ece_floor(0.9, 20):.4f}")
    check(round(ece_floor(0.1, 6), 4) == 0.1063, f"ece_floor(0.1,6)={ece_floor(0.1, 6):.4f}")
    # the approximation everyone uses, and why it is not used here
    from math import pi, sqrt as _sqrt
    approx6 = _sqrt(2 * 0.1 * 0.9 / (pi * 6))
    check(approx6 < ece_floor(0.1, 6),
          f"...the normal approximation UNDERSTATES at n=6 ({approx6:.4f} < {ece_floor(0.1, 6):.4f})")
    check(ece_floor(0.5, 20) > ece_floor(0.5, 200),
          "the floor falls as n rises, as it must")

    # ── the amendment corpus's real n, from PLAN_08 ─────────────────────────
    # n_eff is about 6 amending events. This is the target the founder asked for.
    amend = TrackRecord("will-parliament-amend-this-section", n=6, mean_forecast=0.1,
                        observed_rate=0.1, target_ece=0.05,
                        baseline_score=0.09, model_score=0.04)
    check(assess(amend).state == UNDERPOWERED,
          "at the corpus's real n_eff of 6, the amendment forecast is refused")

    # ── the other refusals ──────────────────────────────────────────────────
    check(assess(None).state == UNREGISTERED, "no record at all is UNREGISTERED")
    miscal = TrackRecord("t", n=500, mean_forecast=0.9, observed_rate=0.70,
                         target_ece=0.05, baseline_score=0.09, model_score=0.05)
    check(assess(miscal).state == UNCALIBRATED,
          "with enough n, real miscalibration is named as such, not as noise")
    check("real miscalibration, not noise" in assess(miscal).reason,
          "...and says so, because the distinction is the whole point")
    noskill = TrackRecord("t", n=500, mean_forecast=0.9, observed_rate=0.9,
                          target_ece=0.05, baseline_score=0.09, model_score=0.09)
    check(assess(noskill).state == NO_SKILL,
          "calibrated but no better than the baseline is refused")

    # ── and the one case that passes ────────────────────────────────────────
    good = TrackRecord("filed-late-given-history", n=500, mean_forecast=0.9,
                       observed_rate=0.9, target_ece=0.05,
                       baseline_score=0.09, model_score=0.04)
    check(assess(good).state == SERVABLE, f"a well-evidenced estimator passes ({assess(good).state})")
    out = render_number(good, 0.9)
    check(all(s in out for s in ("CI", "n=500", "base rate", "skill")),
          f"...and renders with interval, n, base rate and skill ({out})")
    check("0.90 (" in out, "...never as a bare number")

    # ── the states compose on the shared lattice, worst wins ────────────────
    worst = _LATTICE.worst_of([assess(good), assess(amend)], lambda v: v.state)
    check(worst.state == UNDERPOWERED,
          f"composing a good and a refused estimator yields the refusal ({worst.state})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
