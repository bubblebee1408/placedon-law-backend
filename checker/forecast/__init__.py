"""Ring 3 forecasting: the maths that lets Themis say something about what is LIKELY,
without ever letting a likelihood decide what the law IS.

PLAN_25 §5. Every function here is a known, published method. None is claimed as new
mathematics. What this package adds is the contract around them: every output is an
`Estimate` carrying its n, its interval, its method, what kind of claim it is, and the
sentence saying what it is NOT. `render()` is the only sanctioned text path. `.value` is a
public field for computation, and a caller must never serialise it without the rendered
sentence beside it.

## Mapping onto the product's output classes (web/assistant/contract.md)

    DESCRIPTIVE   -> predictive_signal   never verified_fact, even when every record is verified
    HYPOTHETICAL  -> predictive_signal   never deterministic_conclusion: a probability over facts
    FORECAST      -> predictive_signal   only when SERVABLE for its OWN target; else abstained

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
    basis: str = ""                 # what data / which rule, as of when, from which source
    notes: tuple[str, ...] = field(default_factory=tuple)
    target_id: str = ""             # FORECAST only: the track record this may render against

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
        if self.kind == FORECAST and not self.target_id.strip():
            raise EstimateError("a FORECAST must name the target its track record is kept for")
        if self.kind == HYPOTHETICAL and not self.basis.strip():
            raise EstimateError("a HYPOTHETICAL must state the rule, date and source it applied")

    def servable(self, track_record=None) -> bool:
        """A FORECAST is servable only against a SERVABLE record kept for ITS target."""
        if self.kind != FORECAST:
            return True
        if track_record is None or getattr(track_record, "target_id", None) != self.target_id:
            return False
        from checker.calibration_contract import SERVABLE, assess
        return assess(track_record).state == SERVABLE

    def output_class(self, track_record=None) -> str:
        return "predictive_signal" if self.servable(track_record) else "abstained"

    def render(self, track_record=None) -> str:
        """The only way an estimate becomes text.

        A FORECAST renders as a number only when `calibration_contract.assess` says its
        track record is SERVABLE; otherwise it degrades to a sentence with no number in it.
        That is the same rule the engine applies to an unattested instrument.
        """
        tail = "".join(f" {n}." for n in self.notes) + (f" Basis: {self.basis}." if self.basis else "")
        if self.kind == FORECAST and not self.servable(track_record):
            from checker.calibration_contract import UNREGISTERED, assess
            if track_record is None or track_record.target_id != self.target_id:
                why = (f"{UNREGISTERED}: no track record is kept for '{self.target_id}'"
                       + ("" if track_record is None else
                          f" (a record for '{track_record.target_id}' does not count)"))
            else:
                v = assess(track_record)
                why = f"{v.state}: {v.reason}"
            return f"No forecast shown ({why}). This is not {self.not_a}.{tail}"
        hi = "not reached" if self.high == float("inf") else f"{self.high:.3g}"
        return (f"{self.value:.3g} (95% interval {self.low:.3g}–{hi}; n={self.n}; "
                f"{self.method}; {self.kind.lower()}). Not {self.not_a}.{tail}")


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

    f = Estimate(0.7, 0.6, 0.8, 40, "conformal", FORECAST, "legal advice",
                 target_id="change:SEBI_LODR:reg30")
    txt = f.render(None)
    check(txt.startswith("No forecast shown (UNREGISTERED") and "0.7" not in txt,
          "a FORECAST with no track record renders no number at all")
    from checker.calibration_contract import TrackRecord
    good = TrackRecord("change:SEBI_LODR:reg30", n=500, mean_forecast=0.9, observed_rate=0.9,
                       target_ece=0.05, baseline_score=0.09, model_score=0.04)
    other = TrackRecord("filed-late-given-history", n=500, mean_forecast=0.9,
                        observed_rate=0.9, target_ece=0.05, baseline_score=0.09,
                        model_score=0.04)
    # the trust-boundary review's finding: ANY servable record used to unlock the number
    t_other = f.render(other)
    check("0.7" not in t_other and "does not count" in t_other,
          "a SERVABLE record kept for a DIFFERENT target does not unlock the number")
    check(f.render(good).startswith("0.7 "),
          "...it renders only against a SERVABLE record for its own target")
    check(f.output_class(other) == "abstained" and f.output_class(good) == "predictive_signal",
          "output class: abstained without its own record, predictive_signal with it")
    check(e.output_class() == "predictive_signal",
          "a DESCRIPTIVE statistic is a predictive_signal, never a verified_fact")
    try:
        Estimate(0.5, 0.4, 0.6, 10, "m", FORECAST, "x")
        check(False, "a FORECAST with no target is refused")
    except EstimateError:
        check(True, "a FORECAST with no target is refused")
    try:
        Estimate(0.5, 0.4, 0.6, 10, "m", HYPOTHETICAL, "x")
        check(False, "a HYPOTHETICAL with no stated rule/date/source is refused")
    except EstimateError:
        check(True, "a HYPOTHETICAL with no stated rule/date/source is refused")
    noted = Estimate(0.3, 0.2, 0.4, 3, "m", DESCRIPTIVE, "a prediction",
                     basis="NCLT Mumbai, to 2026-08-31", notes=("mostly prior: 3 cases",))
    r = noted.render()
    check("mostly prior: 3 cases" in r and "Basis: NCLT Mumbai" in r,
          "notes and basis survive rendering -- uncertainty is never dropped on the way out")
    inf = Estimate(5.0, 4.0, float("inf"), 6, "KM", DESCRIPTIVE, "a prediction")
    check("not reached" in inf.render() and "inf" not in inf.render(),
          "an unbounded upper limit renders as 'not reached', never 'inf'")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
