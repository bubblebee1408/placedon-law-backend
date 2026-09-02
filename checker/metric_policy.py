"""The release gate: what a verifier configuration must satisfy to ship.

Accuracy alone cannot gate a legal verifier. On a set that is 66% negative,
"always NOT_ENTAILED" scores 0.66 with F1 0.00 — it accepts nothing, ever, and
would pass any accuracy threshold below that while being useless. Afane et al.
(CSLAW 2026) measured exactly this: an all-affirmative baseline scoring F1 0.73
against Westlaw AI's 0.64 and Lexis+ AI's 0.41.

So the gate is four conditions, and a configuration must satisfy all of them:

    false-accept ceiling   an unsupported claim served as supported is the
                           legally dangerous error. It is capped in absolute
                           count, not as a rate, because a rate hides how many
                           wrong answers a reviewer actually sees.
    F1 floor               stops a refuse-everything configuration passing.
    abstention cap         stops a configuration passing by declining most
                           items. Abstention is safe; it is not free.
    per-bucket reporting   an aggregate can hide a bucket at zero. Every
                           bucket is reported and none may be worse than the
                           majority baseline on false accepts.

The majority-class baseline is printed with every result, always. A score
without it is not a result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Thresholds. Deliberately not aspirational — these are what the current
# cascade achieves plus a small margin, so the gate catches regression rather
# than blocking work. Raising them is a decision to record, not to drift into.
FALSE_ACCEPT_CEILING = 10        # cascade currently 2 with the E6 gate, 13 without
F1_FLOOR = 0.40                  # cascade currently 0.58; baseline is 0.00
ABSTENTION_CAP = 0.25            # cascade currently 0.00; E5 alone is 0.83
BUCKET_MIN_REPORTED = 3          # buckets below this size are named, not scored

# Roles a module may hold in the cascade.
SPECIALIST = "SPECIALIST"        # narrow competence, high abstention, never alone
GENERAL = "GENERAL"              # answers across the set
GATE = "GATE"                    # may only refuse, never accept

MODULE_ROLES = {
    "E3": GENERAL,
    "E4": SPECIALIST,
    "E5": SPECIALIST,
    "E6": GATE,
}


@dataclass
class GateResult:
    passed: bool
    false_accepts: int
    f1: float
    abstention: float
    failures: list[str] = field(default_factory=list)
    buckets: dict = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            "",
            f"RELEASE GATE — {'PASS' if self.passed else 'FAIL'}",
            f"  false accepts   : {self.false_accepts:>6}   ceiling {FALSE_ACCEPT_CEILING}",
            f"  F1              : {self.f1:>6.2f}   floor   {F1_FLOOR:.2f}",
            f"  abstention      : {self.abstention:>6.2f}   cap     {ABSTENTION_CAP:.2f}",
        ]
        if self.buckets:
            lines.append("  per bucket:")
            for k, v in sorted(self.buckets.items()):
                f1 = "  n/a" if v["f1"] is None else f"{v['f1']:.2f}"
                note = ""
                if v.get("single_label"):
                    kind = "no positives" if not v["pos"] else "no negatives"
                    note = (f"   [{kind}: F1 undefined]" if v["f1"] is None
                            else f"   [{kind}: cannot detect false accepts]")
                lines.append(f"    {k:<22}n={v['n']:<4} FA={v['fa']:<4} "
                             f"F1={f1}{note}")
        for f in self.failures:
            lines.append(f"  FAILED: {f}")
        if self.passed:
            lines.append("  Passing this gate is not evidence that grounding is solved.")
            lines.append("  It means the configuration did not regress on four axes.")
        return "\n".join(lines)


def evaluate_gate(predict, rows, bucket_of=None) -> GateResult:
    """Score a predictor against the gate. `predict(row) -> bool | None`."""
    from checker.grounding_policy import ENTAILED

    tp = fp = tn = fn = ab = 0
    buckets: dict[str, dict] = {}
    for r in rows:
        v = predict(r)
        g = (r.label == ENTAILED)
        key = bucket_of(r.kind) if bucket_of else None
        b = buckets.setdefault(key, {"n": 0, "tp": 0, "fp": 0, "tn": 0, "fn": 0,
                                     "ab": 0, "pos": 0, "neg": 0}) if key else None
        if b is not None:
            b["n"] += 1
            b["pos" if g else "neg"] += 1
        if v is None:
            ab += 1
            if b is not None:
                b["ab"] += 1
            continue
        slot = "tp" if (v and g) else "fp" if v else "fn" if g else "tn"
        if slot == "tp":
            tp += 1
        elif slot == "fp":
            fp += 1
        elif slot == "fn":
            fn += 1
        else:
            tn += 1
        if b is not None:
            b[slot] += 1

    n = len(rows)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    abst = ab / n if n else 0.0

    out = {}
    for k, b in buckets.items():
        bp = b["tp"] / (b["tp"] + b["fp"]) if b["tp"] + b["fp"] else 0.0
        br = b["tp"] / (b["tp"] + b["fn"]) if b["tp"] + b["fn"] else 0.0
        # F1 is defined over positives. A bucket holding no positive examples
        # has none to find, so its F1 is pinned at 0.00 by arithmetic and not by
        # performance — dropped_qualifier read 0.00 while sitting at zero false
        # accepts, which made a solved bucket look broken and invited someone to
        # "fix" a number that cannot move. Report it as undefined instead.
        single_label = b["pos"] == 0 or b["neg"] == 0
        out[k] = {"n": b["n"], "fa": b["fp"],
                  "f1": None if b["pos"] == 0
                        else (2 * bp * br / (bp + br) if bp + br else 0.0),
                  "pos": b["pos"], "neg": b["neg"],
                  "single_label": single_label}

    fails = []
    if fp > FALSE_ACCEPT_CEILING:
        fails.append(f"{fp} false accepts exceeds the ceiling of {FALSE_ACCEPT_CEILING}")
    if f1 < F1_FLOOR:
        fails.append(f"F1 {f1:.2f} is below the floor of {F1_FLOOR:.2f}")
    if abst > ABSTENTION_CAP:
        fails.append(f"abstention {abst:.2f} exceeds the cap of {ABSTENTION_CAP:.2f}")
    if not out:
        fails.append("no per-bucket reporting was supplied")

    return GateResult(not fails, fp, f1, abst, fails, out)


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

    print("metric_policy")

    check(MODULE_ROLES["E5"] == SPECIALIST,
          "E5 is registered as a specialist, not a standalone verifier")
    check(MODULE_ROLES["E4"] == SPECIALIST, "E4 is a specialist too")
    check(MODULE_ROLES["E3"] == GENERAL, "E3 is the general module")
    check(MODULE_ROLES["E6"] == GATE, "E6 is a gate — it may refuse, never accept")

    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED, NOT_ENTAILED
    from checker.eval_taxonomy import bucket_of
    # Imported, not redefined. While this was a closure the gate scored code no
    # runtime could reach, so a shipped verifier and a measured verifier were
    # only ever the same by coincidence.
    from checker.cascade import judge_row as cascade, e3, e4, e5, e6

    # Score the FROZEN benchmark, not the generator. The gate used to measure
    # entail_pairs_v2.all_pairs(), which rebuilds the pair set at import time —
    # so the manifest hash validated a file the gate never opened, and the two
    # had already diverged (69/22 attested, 67/20 measured). A gate that cannot
    # verify its own input must not report PASS.
    from checker.benchmark_v2_freeze import FrozenBenchmarkError, frozen_rows
    try:
        rows = [p for p in frozen_rows() if p.label in (ENTAILED, NOT_ENTAILED)]
        drift = ""
    except FrozenBenchmarkError as e:
        rows, drift = [], str(e)

    if drift:
        check(True, "the gate REFUSES to score a benchmark that has drifted")
        print(f"\n  BENCHMARK DRIFT — the gate cannot certify anything.\n"
              f"  {drift[:300]}\n"
              f"  Re-freeze under authorisation, or correct the spans. No "
              f"accuracy figure may be quoted until this clears.\n")
        check(MODULE_ROLES["E6"] == GATE,
              "module roles are still asserted while scoring is blocked")
        print(f"\n{ok}/{ok + fail} passed")
        if fail:
            raise SystemExit(1)
        return

    def E3(r):
        return e3(r.source_span, r.claim)

    def E4(r):
        return e4(r.source_span, r.claim)

    def E5(r):
        return e5(r.source_span, r.claim)

    def E6(r):
        return e6(r.source_span, r.claim)

    # The refuse-everything baseline must FAIL the gate. That is the whole point.
    g = evaluate_gate(lambda r: False, rows, bucket_of)
    check(not g.passed, "the refuse-everything baseline fails the gate")
    check(any("F1" in f for f in g.failures),
          f"...on the F1 floor ({g.failures})")

    # E5 alone must fail on abstention, however accurate it is where it speaks.
    g5 = evaluate_gate(E5, rows, bucket_of)
    check(not g5.passed, "E5 alone fails the gate")
    check(any("abstention" in f for f in g5.failures),
          f"...on the abstention cap ({g5.abstention:.2f})")

    # E3 alone must fail on false accepts.
    g3 = evaluate_gate(E3, rows, bucket_of)
    check(not g3.passed, "E3 alone fails the gate")
    check(any("false accepts" in f for f in g3.failures),
          f"...on the false-accept ceiling ({g3.false_accepts})")

    # The gate must never turn a rejection into an acceptance: for every row,
    # the gated cascade's verdict is either the ungated one or False.
    def ungated(r):
        for f in (E5, E4):
            v = f(r)
            if v is not None:
                return v
        return E3(r)

    from checker.cascade import verdict as _verdict
    check(all(cascade(r) is _verdict(r.source_span, r.claim).supported
              for r in rows),
          "the gate scores checker.cascade, on the (premise, claim) primitive "
          "a runtime would call")

    check(all(cascade(r) is ungated(r) or cascade(r) is False for r in rows),
          "the E6 gate only ever converts an accept into a refusal")

    gu = evaluate_gate(ungated, rows, bucket_of)
    check(gu.false_accepts > FALSE_ACCEPT_CEILING,
          f"the ungated cascade fails the false-accept ceiling ({gu.false_accepts})")

    gc = evaluate_gate(cascade, rows, bucket_of)
    check(gc.passed, f"the cascade passes the gate ({gc.failures})")
    check(gc.buckets, "per-bucket results are reported")
    # A bucket with no positives has no F1 to report, and printing 0.00 made a
    # solved bucket look like a failing one.
    dq = gc.buckets["dropped_qualifier"]
    check(dq["pos"] == 0, f"dropped_qualifier holds no positives ({dq['pos']})")
    check(dq["f1"] is None, "...so its F1 is reported as undefined, not 0.00")
    check(dq["fa"] == 0, f"...and its real signal, false accepts, is 0 ({dq['fa']})")

    pa = gc.buckets["paraphrase"]
    check(pa["neg"] == 0, f"paraphrase holds no negatives ({pa['neg']})")
    check(pa["single_label"], "...and is flagged single-label")
    check(pa["f1"] is not None,
          "...but keeps an F1, since it does have positives to find")

    wb = gc.buckets["wrong_binding"]
    check(not wb["single_label"] and wb["f1"] is not None,
          "a bucket carrying both labels reports a real F1")

    rr = gc.render()
    check("n/a" in rr, "the rendered gate prints n/a rather than a false 0.00")
    check("F1 undefined" in rr, "...and says why")
    check("cannot detect false accepts" in rr,
          "an all-positive bucket is marked as unable to detect false accepts")

    r = gc.render()
    check("not evidence that grounding is solved" in r,
          "a passing gate states what it does not mean")
    print(r)

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
