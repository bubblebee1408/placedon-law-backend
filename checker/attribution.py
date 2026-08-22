"""
Attribute a failure to the stage that caused it.

`scripts/baseline_eval.py` reports decision accuracy, abstention correctness, evidence recall. Every
one is a whole-pipeline number, and when a case fails none of them says WHICH STAGE failed -- while
the remedies are opposite. A provision that was never retrieved is a retrieval problem that no
prompt change will fix. A provision retrieved, admitted and served but never cited is a generation
problem that no retrieval work will fix. "Accuracy 0.8" destroys exactly the information needed to
act on either.

The ladder:

    RETRIEVED   retrieval found the provision at all
    ADMITTED    a reviewer admitted it for model use
    SERVED      it reached the evidence pack as usable
    CITED       a surviving claim cited it
    GROUNDED    the verifier established that a claim is carried by it

**A blocked admission is not a failure of this system.** When s.16 is withheld because it carries
pre-amendment text, or a Rule is withheld pending review, the pipeline did the right thing by not
serving it. A metric that scores those as failures punishes precisely the behaviour this repo exists
to have, so the verdict carries `system_behaved_correctly` and the two cases are never summed.

**GROUNDED cannot pass today**, for any case. `claim_verifier.establishes_support()` is False for
LEXICAL_CANDIDATE, and the lexical path cannot return anything stronger. That is recorded plainly
rather than smoothed over: treating triage as grounding would make this ladder report a capability
the system does not have.

Run: python3 checker/attribution.py
"""
from __future__ import annotations

from dataclasses import dataclass

from checker.claim_verifier import ClaimVerification, establishes_support
from checker.evidence_pack import EvidencePack
from checker.model_adapter import ModelResult

__all__ = ["StageResult", "Attribution", "attribute", "STAGES", "CLASSES",
           "RETRIEVED", "ADMITTED", "SERVED", "CITED", "GROUNDED", "VERDICTS",
           "PIPELINE_DEFECT", "MODEL_FAILURE_CAUGHT", "CORRECT_REFUSAL", "COMPLETE"]

RETRIEVED = "RETRIEVED"
ADMITTED = "ADMITTED"
SERVED = "SERVED"
CITED = "CITED"
GROUNDED = "GROUNDED"
STAGES = (RETRIEVED, ADMITTED, SERVED, CITED, GROUNDED)

# Verdicts. The split that matters is not pass/fail -- it is whether a human should go fix
# something, or whether the system correctly declined.
COMPLETE = "COMPLETE"                          # every stage passed
RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"        # never found; retrieval work
ADMISSION_BLOCK = "ADMISSION_BLOCK"            # correctly withheld; NOT a defect
SERVING_FAILURE = "SERVING_FAILURE"            # admitted but absent from the pack; a real bug
GENERATION_FAILURE = "GENERATION_FAILURE"      # served but the model did not cite it
GROUNDING_FAILURE = "GROUNDING_FAILURE"        # cited, and the verifier refuted it
GROUNDING_UNAVAILABLE = "GROUNDING_UNAVAILABLE"  # cited, but nothing here can establish entailment
VERDICTS = (COMPLETE, RETRIEVAL_FAILURE, ADMISSION_BLOCK, SERVING_FAILURE, GENERATION_FAILURE,
            GROUNDING_FAILURE, GROUNDING_UNAVAILABLE)

# Three different questions, deliberately not collapsed into one boolean. An earlier version had a
# single `system_behaved_correctly`, and it reported GROUNDING_UNAVAILABLE as False -- implying a
# defect, when the system had correctly declined to claim grounding it cannot establish. Conflating
# "go fix this" with "produced no answer" makes the metric useless in both directions: it panics
# about working safety behaviour and it congratulates a system that answers nothing.
#
#   PIPELINE_DEFECT      our code is wrong; someone must fix it
#   MODEL_FAILURE_CAUGHT the model misbehaved and a guard stopped it -- working as designed
#   CORRECT_REFUSAL      we declined deliberately; no answer, and that is right
#   COMPLETE             an answer came out
PIPELINE_DEFECT = "PIPELINE_DEFECT"
MODEL_FAILURE_CAUGHT = "MODEL_FAILURE_CAUGHT"
CORRECT_REFUSAL = "CORRECT_REFUSAL"
CLASSES = (PIPELINE_DEFECT, MODEL_FAILURE_CAUGHT, CORRECT_REFUSAL, COMPLETE)

_CLASS_OF = {
    COMPLETE: COMPLETE,
    # Retrieval finding nothing is our problem: the corpus, the index, or the query route.
    RETRIEVAL_FAILURE: PIPELINE_DEFECT,
    # Admitted but absent from the pack means admission and packing disagree -- a bug between two
    # of our own components, and the only verdict here that indicates broken code with no excuse.
    SERVING_FAILURE: PIPELINE_DEFECT,
    # The model cited the wrong thing, or cited something we refuted. The guard did its job.
    GENERATION_FAILURE: MODEL_FAILURE_CAUGHT,
    GROUNDING_FAILURE: MODEL_FAILURE_CAUGHT,
    # We declined on purpose. Not defects.
    ADMISSION_BLOCK: CORRECT_REFUSAL,
    GROUNDING_UNAVAILABLE: CORRECT_REFUSAL,
}

_UNREACHED = "not reached: an earlier stage failed, so this was never tested"


@dataclass(frozen=True)
class StageResult:
    stage: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return dict(stage=self.stage, passed=self.passed, detail=self.detail)


@dataclass(frozen=True)
class Attribution:
    expected_key: str
    stages: tuple[StageResult, ...]
    failed_at: str | None
    verdict: str

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"{self.verdict!r} is not a verdict")
        # Monotonicity. A ladder reporting CITED while SERVED failed describes something impossible,
        # and nothing it says can be relied on. Enforced here rather than trusted.
        seen_failure = False
        for s in self.stages:
            if seen_failure and s.passed:
                raise ValueError(
                    f"{self.expected_key}: {s.stage} passed after an earlier stage failed -- "
                    "the ladder is not monotonic and its output is meaningless")
            seen_failure = seen_failure or not s.passed

    @property
    def outcome_class(self) -> str:
        """Which of the four kinds of outcome this is. See _CLASS_OF."""
        return _CLASS_OF[self.verdict]

    @property
    def is_defect(self) -> bool:
        """Whether someone must go fix our code. NOT the same as 'no answer came out'."""
        return self.outcome_class == PIPELINE_DEFECT

    @property
    def produced_result(self) -> bool:
        """Whether a usable conclusion came out. Only COMPLETE does."""
        return self.verdict == COMPLETE

    def to_dict(self) -> dict:
        return dict(expected_key=self.expected_key, failed_at=self.failed_at,
                    verdict=self.verdict, outcome_class=self.outcome_class,
                    is_defect=self.is_defect, produced_result=self.produced_result,
                    stages=[s.to_dict() for s in self.stages])


def _mentions(notices: tuple[str, ...], key: str) -> str:
    """The notice naming this key, if any.

    Boundary-aware: a plain substring test makes ':S1' match ':S188' and attributes s.188's
    withholding to s.1.
    """
    def boundary(ch: str) -> bool:
        # Empty means start/end of string, which IS a boundary. Testing `ch not in ":_"` instead
        # silently rejects every match at position 0 -- because `"" in ":_"` is True in Python --
        # and position 0 is exactly where these notices put the key.
        return ch == "" or (not ch.isalnum() and ch not in ":_")

    for n in notices:
        i = n.find(key)
        while i != -1:
            before = n[i - 1] if i else ""
            after = n[i + len(key)] if i + len(key) < len(n) else ""
            if boundary(before) and boundary(after):
                return n
            i = n.find(key, i + 1)
    return ""


def attribute(expected_key: str, pack: EvidencePack, result: ModelResult,
              verifications: tuple[ClaimVerification, ...] = ()) -> Attribution:
    """Which stage first failed to carry `expected_key` through the pipeline."""
    served = {p.key for p in pack.usable}
    present = {p.key for p in pack.provisions}
    withheld_notice = _mentions(tuple(pack.missing), expected_key)

    stages: list[StageResult] = []
    verdict = COMPLETE
    failed_at: str | None = None

    def stop(stage: str, detail: str, v: str) -> Attribution:
        stages.append(StageResult(stage, False, detail))
        for later in STAGES[STAGES.index(stage) + 1:]:
            stages.append(StageResult(later, False, _UNREACHED))
        return Attribution(expected_key, tuple(stages), stage, v)

    # RETRIEVED -- found anywhere: served, present-but-unusable, or named in a withheld notice.
    # A withheld notice counts as retrieval SUCCESS: we found the law and declined to serve it,
    # which is a different event from never finding it.
    if expected_key not in present and not withheld_notice:
        return stop(RETRIEVED, f"{expected_key} was not found by retrieval, and no notice names it",
                    RETRIEVAL_FAILURE)
    stages.append(StageResult(RETRIEVED, True,
                              "served" if expected_key in served else
                              "found, then withheld" if withheld_notice else "present in the pack"))

    # ADMITTED
    if expected_key not in served:
        detail = (withheld_notice[:160] if withheld_notice
                  else f"{expected_key} is in the pack but not admitted for model use")
        return stop(ADMITTED, detail, ADMISSION_BLOCK)
    stages.append(StageResult(ADMITTED, True, "admitted for model use"))

    # SERVED -- admitted and usable is what SERVED means, so reaching here means it passed. The
    # stage exists as a distinct rung because admission and packing are separate code paths and a
    # bug between them would otherwise be attributed to generation.
    stages.append(StageResult(SERVED, True, "present in the pack as usable evidence"))

    # CITED
    cited = {e for c in result.claims for e in c.evidence_ids}
    if expected_key not in cited:
        got = ", ".join(sorted(cited)) or "nothing"
        return stop(CITED, f"the model cited {got}, not {expected_key}", GENERATION_FAILURE)
    stages.append(StageResult(CITED, True, f"cited by {len(result.claims)} surviving claim(s)"))

    # GROUNDED
    supporting = [v for v in verifications
                  if expected_key in v.supporting_evidence_ids and establishes_support(v.verdict)]
    if not supporting:
        seen = sorted({v.verdict for v in verifications}) or ["no verifications supplied"]
        refuted = any(v.verdict in ("UNSUPPORTED", "CONTRADICTED", "INVALID_CITATION")
                      for v in verifications)
        return stop(
            GROUNDED,
            f"no verdict establishes support (saw: {', '.join(seen)}); the lexical path tops out "
            "at LEXICAL_CANDIDATE and no entailment checker exists",
            GROUNDING_FAILURE if refuted else GROUNDING_UNAVAILABLE)
    stages.append(StageResult(GROUNDED, True, "entailment established"))

    return Attribution(expected_key, tuple(stages), None, COMPLETE)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    import json
    from pathlib import Path

    from checker import claim_verifier as cv
    from checker.model_adapter import ModelTask, run
    from checker.retrieve import MODE_MODEL, retrieve

    def pipeline(query: str, model=None):
        pack, _ = retrieve(query, mode=MODE_MODEL)
        res = run(ModelTask("APPLICABILITY_CHECK", query, pack), model=model)
        return pack, res, cv.verify_all(res.claims, pack)

    # A clean provision goes all the way to GROUNDED and stops there -- the honest current ceiling.
    a = attribute("ACT:COMPANIES_ACT_2013:S173", *pipeline("s.173"))
    check(a.failed_at == GROUNDED, f"s.173 reaches GROUNDED and stops ({a.failed_at})")
    check(a.verdict == GROUNDING_UNAVAILABLE, f"...verdict {a.verdict}")
    check([s.stage for s in a.stages if s.passed] == [RETRIEVED, ADMITTED, SERVED, CITED],
          "the four stages before it all passed")
    check("no entailment checker exists" in a.stages[-1].detail,
          "...and the detail says why, rather than implying the claim was refuted")

    # A suspended provision: the system REFUSED correctly. This must not read as a defect.
    b = attribute("ACT:COMPANIES_ACT_2013:S16", *pipeline("s.16"))
    check(b.failed_at == ADMITTED, f"s.16 fails at ADMITTED ({b.failed_at})")
    check(b.verdict == ADMISSION_BLOCK, "...as an ADMISSION_BLOCK")
    check(b.outcome_class == CORRECT_REFUSAL and not b.is_defect,
          "...classed as a CORRECT_REFUSAL, not a defect")
    check(b.stages[0].passed, "retrieval still succeeded -- finding it and declining differ")

    # An unreviewed Rule: found, named in a notice, correctly not served.
    c = attribute("RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R15",
                  *pipeline("related party transactions"))
    check(c.failed_at == ADMITTED and c.verdict == ADMISSION_BLOCK,
          f"an unreviewed Rule is an ADMISSION_BLOCK ({c.failed_at}/{c.verdict})")
    check(c.outcome_class == CORRECT_REFUSAL and not c.is_defect, "...also a correct refusal")
    check("not admitted" in c.stages[1].detail.lower() or "R15" in c.stages[1].detail,
          "...and the detail names the withheld rule")

    # Never retrieved at all.
    d = attribute("ACT:COMPANIES_ACT_2013:S999", *pipeline("what colour is the sky"))
    check(d.failed_at == RETRIEVED and d.verdict == RETRIEVAL_FAILURE,
          f"an absent provision is a RETRIEVAL_FAILURE ({d.verdict})")
    check(d.is_defect and d.outcome_class == PIPELINE_DEFECT,
          "...and that IS something to go fix")
    check(all(s.detail == _UNREACHED for s in d.stages[1:]),
          "later stages report as unreached, not as independently failed")

    # Served but the model cited something else.
    other = json.dumps({"decision": "APPLIES", "claims": [
        {"claim_id": "c1", "claim_type": "LEGAL_TRIGGER",
         "text": "The audit committee shall act.",
         "evidence_ids": ["ACT:COMPANIES_ACT_2013:S177"]}]})
    e = attribute("ACT:COMPANIES_ACT_2013:S188",
                  *pipeline("related party transactions", model=lambda p: other))
    check(e.failed_at == CITED and e.verdict == GENERATION_FAILURE,
          f"served-but-not-cited is a GENERATION_FAILURE ({e.failed_at}/{e.verdict})")
    check("S177" in e.stages[3].detail, "...and the detail names what was cited instead")
    check(e.outcome_class == MODEL_FAILURE_CAUGHT and not e.is_defect,
          "a model citing the wrong provision is MODEL_FAILURE_CAUGHT -- the guard worked")

    # The distinction the single boolean destroyed: no answer, but nothing to fix.
    check(a.outcome_class == CORRECT_REFUSAL,
          "GROUNDING_UNAVAILABLE is a CORRECT_REFUSAL -- declining to claim unestablished grounding")
    check(not a.is_defect, "...so it is NOT a defect")
    check(not a.produced_result, "...but it produced no usable result either")
    check(sorted({_CLASS_OF[v] for v in VERDICTS}) == sorted(set(CLASSES)),
          "every verdict maps to a class, and every class is reachable")

    # Monotonicity, asserted rather than assumed.
    for att in (a, b, c, d, e):
        seen_fail = False
        good = True
        for s in att.stages:
            if seen_fail and s.passed:
                good = False
            seen_fail = seen_fail or not s.passed
        check(good, f"{att.expected_key.split(':')[-1]}: ladder is monotonic")
    try:
        Attribution("k", (StageResult(RETRIEVED, False, "x"), StageResult(ADMITTED, True, "y")),
                    RETRIEVED, RETRIEVAL_FAILURE)
        check(False, "a non-monotonic ladder must be refused at construction")
    except ValueError as exc:
        check("not monotonic" in str(exc), "a non-monotonic ladder is refused at construction")

    # Every frozen benchmark case attributes to exactly one stage.
    bench = json.loads((Path(__file__).resolve().parent.parent /
                        "corpus/benchmark/baseline_v1.json").read_text())
    attributed, stages_hit = 0, {}
    for case in bench["cases"]:
        for key in case.get("expect_evidence") or []:
            att = attribute(key, *pipeline(case["query"]))
            attributed += 1
            stages_hit[att.verdict] = stages_hit.get(att.verdict, 0) + 1
            fails = [s for s in att.stages if not s.passed]
            check(len(fails) == 0 or fails[0].stage == att.failed_at,
                  f"{case['id']}/{key.split(':')[-1]}: failed_at matches the first failed stage")
    check(attributed > 0, f"attributed {attributed} expected provisions across the benchmark")
    print(f"       verdict spread: {stages_hit}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
