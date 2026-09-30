"""Ring 3 forecasting: the maths that lets Themis say something about what is LIKELY,
without ever letting a likelihood decide what the law IS.

PLAN_25 §5. Every function here is a known, published method. None is claimed as new
mathematics. What this package adds is the contract around them: every output is an
`Estimate` carrying its n, its interval, its method, what kind of claim it is, and the
sentence saying what it is NOT. A bare number cannot leave this package.

## Where it sits

`checker/rings.py` registers this package as RING 3 (INFERENCE). A Ring 0 decider may never
import it, and the firewall's AST scan enforces that. The dependency points the other way
only through `propagate`: a Ring 3 computation may *call* a Ring 0 decider, passed in as a
callable, over hypothetical facts. It never changes what the decider says.

## The kinds of claim, from PLAN_24 02 P2 (Medvedeva, Wieling & Vols 2023)

    DESCRIPTIVE   what the records show (counts, rates, durations)
    HYPOTHETICAL  the law applied to uncertain facts (propagate)
    FORECAST      a statement about an undecided future event

Only FORECAST is a prediction, and only FORECAST needs a live track record before it may
render (`calibration_contract`). The other two are arithmetic over stated inputs.

## Modules

    rates       Beta-Binomial partial pooling (empirical Bayes), exact Beta quantiles
    survival    Kaplan-Meier with Greenwood variance and log-log intervals, censoring-aware
    conformal   split-conformal prediction SETS for a binary outcome; adaptive conformal
                inference (ACI) for drift; a set of two outcomes is an abstention
    events      Gamma-Poisson for "will this instrument change within h years"
    propagate   probability that a deterministic rule applies when a fact is uncertain
    scoring     Brier score, the Murphy decomposition, log-odds pooling

Standard library only. Every random draw is seeded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DESCRIPTIVE = "DESCRIPTIVE"
HYPOTHETICAL = "HYPOTHETICAL"
FORECAST = "FORECAST"
KINDS = (DESCRIPTIVE, HYPOTHETICAL, FORECAST)


class EstimateError(ValueError):
    """An estimate that cannot honestly be formed from its inputs."""


@dataclass(frozen=True)
class Estimate:
    """One number, and everything a reader needs in order not to misread it."""
    value: float
    low: float
    high: float
    n: int
    method: str
    kind: str
    not_a: str                      # the sentence saying what this is NOT
    basis: str = ""                 # what data, as of when
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise EstimateError(f"unknown kind {self.kind!r}")
        if not self.not_a.strip():
            raise EstimateError("an estimate must say what it is not")
        if self.n < 0:
            raise EstimateError("n cannot be negative")
        if not (self.low <= self.value <= self.high):
            raise EstimateError(f"value {self.value} outside its own interval "
                                f"[{self.low}, {self.high}]")

    def render(self, track_record=None) -> str:
        """The only way an estimate becomes text.

        A FORECAST renders as a number only when `calibration_contract.assess` says its
        track record is SERVABLE; otherwise it degrades to a sentence with no number in it.
        That is the same rule the engine applies to an unattested instrument.
        """
        if self.kind == FORECAST:
            from checker.calibration_contract import SERVABLE, assess
            verdict = assess(track_record)
            if verdict.state != SERVABLE:
                return (f"No forecast shown ({verdict.state}): {verdict.reason} "
                        f"This is not {self.not_a}.")
        return (f"{self.value:.3g} (95% interval {self.low:.3g}–{self.high:.3g}; n={self.n}; "
                f"{self.method}; {self.kind.lower()}). Not {self.not_a}.")


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

    print("forecast (package contract)")
    e = Estimate(0.4, 0.3, 0.5, 120, "Wilson", DESCRIPTIVE, "a prediction for your matter")
    out = e.render()
    check("n=120" in out and "interval" in out and "Not a prediction" in out,
          f"a descriptive estimate renders with n, interval and its disclaimer ({out})")
    for bad, label in (
        (dict(value=0.6, low=0.3, high=0.5), "a value outside its own interval"),
        (dict(not_a="  "), "an estimate that does not say what it is not"),
        (dict(kind="PROPHECY"), "an unknown kind of claim"),
    ):
        kw = dict(value=0.4, low=0.3, high=0.5, n=10, method="m", kind=DESCRIPTIVE,
                  not_a="x")
        kw.update(bad)
        try:
            Estimate(**kw)
            check(False, f"refuses {label}")
        except EstimateError:
            check(True, f"refuses {label}")

    f = Estimate(0.7, 0.6, 0.8, 40, "conformal", FORECAST, "legal advice")
    txt = f.render(None)
    check(txt.startswith("No forecast shown (UNREGISTERED)") and "0.7" not in txt,
          "a FORECAST with no track record renders no number at all")
    from checker.calibration_contract import TrackRecord
    good = TrackRecord("t", n=500, mean_forecast=0.9, observed_rate=0.9, target_ece=0.05,
                       baseline_score=0.09, model_score=0.04)
    check(f.render(good).startswith("0.7 "),
          "...and renders only once calibration_contract says SERVABLE")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
