"""
Run the frozen baseline and report claim-level metrics.

**What is being measured.** This scores the HARNESS -- retrieval, admission, the adapter's
refusals, and the verifier -- against labels frozen before any run. The default model is a stub, so
nothing here is a measurement of model quality, and reporting it as one would be the circular
benchmarking this repo has already had to retract once. When a real model is wired in, the same
fixtures measure the model against the same frozen labels, and the difference is attributable.

Answer-level accuracy is reported but is the least informative number. The ones that matter:

  unsupported-claim rate -- claims the verifier could not ground in cited evidence
  abstention correctness -- did it decline exactly when it should have

A system that abstains correctly on suspended, unreviewed and nonexistent law, and grounds every
claim it does make, is doing the job. One that answers everything confidently is not.

Run: python3 scripts/baseline_eval.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker import claim_verifier as cv          # noqa: E402
from checker.model_adapter import (INSUFFICIENT_EVIDENCE, ModelTask, run)  # noqa: E402
from checker.retrieve import MODE_MODEL, retrieve  # noqa: E402

BENCH = ROOT / "corpus/benchmark/baseline_v1.json"
OUT = ROOT / "reports/baseline_v1_results.json"


def evaluate(model=None, model_name: str = "stub") -> dict:
    bench = json.loads(BENCH.read_text())
    rows = []
    for case in bench["cases"]:
        pack, route = retrieve(case["query"], mode=MODE_MODEL)
        result = run(ModelTask("APPLICABILITY_CHECK", case["question"], pack),
                     model=model, model_name=model_name)
        verifications = cv.verify_all(result.claims, pack)

        abstained = result.decision == INSUFFICIENT_EVIDENCE
        got_evidence = sorted({p.key for p in pack.usable})
        gradable = [v for v in verifications if v.verdict != cv.MISSING]
        unsupported = [v for v in gradable
                       if v.verdict in (cv.UNSUPPORTED, cv.CONTRADICTED)]

        rows.append({
            "id": case["id"], "kind": case["kind"], "query": case["query"],
            "decision": result.decision, "route": route,
            "decision_ok": result.decision in case["expect_decision_in"],
            "abstain_ok": abstained == case["expect_abstain"],
            # NOT exact match. A concept query legitimately returns several candidates -- asking
            # "which provision governs related party transactions" surfaces s.188 alongside s.177
            # and s.164, and that is retrieval working, not failing. Recall says whether the right
            # provision was found; precision says how much else came with it. Exact match conflates
            # the two and punishes correct behaviour. The LABELS are unchanged; only the metric
            # definition was wrong.
            "evidence_recall_ok": all(e in got_evidence for e in case["expect_evidence"]),
            "evidence_precision": (
                round(len([e for e in got_evidence if e in case["expect_evidence"]])
                      / len(got_evidence), 3) if got_evidence else
                (1.0 if not case["expect_evidence"] else 0.0)),
            "evidence_got": got_evidence, "evidence_want": sorted(case["expect_evidence"]),
            "claims": len(result.claims), "gradable_claims": len(gradable),
            "unsupported_claims": len(unsupported),
            "rejected_claims": len(result.rejected_claims),
            "verdicts": [v.verdict for v in verifications],
            # A mixed-pack case must SAY that a relevant rule was withheld. Serving the Act while
            # staying silent about the Rules reads as "the Act is the whole answer", which is a
            # different and wrong statement of the law.
            "withheld_rule_reported": any("RULE:" in m for m in pack.missing),
            "withheld_rule_ok": (any("RULE:" in m for m in pack.missing)
                                 == case.get("expect_withheld_rule", False)),
        })

    n = len(rows)
    gradable = sum(r["gradable_claims"] for r in rows)
    unsupported = sum(r["unsupported_claims"] for r in rows)
    summary = {
        "model": model_name,
        "cases": n,
        "decision_accuracy": round(sum(r["decision_ok"] for r in rows) / n, 3),
        "abstention_correctness": round(sum(r["abstain_ok"] for r in rows) / n, 3),
        "evidence_recall": round(sum(r["evidence_recall_ok"] for r in rows) / n, 3),
        "evidence_precision_mean": round(sum(r["evidence_precision"] for r in rows) / n, 3),
        "gradable_claims": gradable,
        "unsupported_claim_rate": round(unsupported / gradable, 3) if gradable else 0.0,
        "claims_rejected_at_parse": sum(r["rejected_claims"] for r in rows),
        "withheld_rule_reporting": round(sum(r["withheld_rule_ok"] for r in rows) / n, 3),
        "measures": "the harness, not model quality -- the default model is a stub",
    }
    return {"summary": summary, "cases": rows}


def main() -> None:
    res = evaluate()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    s = res["summary"]
    print(f"model                   : {s['model']}   ({s['measures']})")
    print(f"cases                   : {s['cases']}")
    print(f"decision accuracy       : {s['decision_accuracy']:.3f}")
    print(f"abstention correctness  : {s['abstention_correctness']:.3f}")
    print(f"evidence recall         : {s['evidence_recall']:.3f}")
    print(f"evidence precision (mean): {s['evidence_precision_mean']:.3f}")
    print(f"unsupported-claim rate  : {s['unsupported_claim_rate']:.3f} "
          f"over {s['gradable_claims']} gradable claims")
    print(f"claims rejected at parse: {s['claims_rejected_at_parse']}")
    print(f"withheld-rule reporting : {s['withheld_rule_reporting']:.3f}")
    bad = [r for r in res["cases"]
           if not (r["decision_ok"] and r["abstain_ok"] and r["evidence_recall_ok"]
                   and r["withheld_rule_ok"])]
    print(f"\nfailing cases: {len(bad)}")
    for r in bad:
        print(f"  {r['id']} [{r['kind']}] {r['query']!r}: decision={r['decision']} "
              f"decision_ok={r['decision_ok']} abstain_ok={r['abstain_ok']} "
              f"recall_ok={r['evidence_recall_ok']}")
    print(f"\nwritten: {OUT.relative_to(ROOT)}")


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    bench = json.loads(BENCH.read_text())
    check(len(bench["cases"]) >= 12, f"benchmark has {len(bench['cases'])} frozen cases")
    ids = [c["id"] for c in bench["cases"]]
    check(len(ids) == len(set(ids)), "case ids are unique")
    check(all(c["expect_decision_in"] for c in bench["cases"]), "every case has a gold decision")

    kinds = {c["kind"] for c in bench["cases"]}
    for k in ("suspended-source", "review-gated", "defect-limited", "out-of-domain"):
        check(k in kinds, f"the benchmark covers {k}")
    check("mixed-pack" in kinds, "the benchmark covers the mixed admissible/withheld case")

    # No case may depend on unreviewed law, or the benchmark blesses the thing the gate blocks.
    rules_cases = [c for c in bench["cases"]
                   if any("RULE:" in e for e in c.get("expect_evidence", []))]
    check(not rules_cases, "no case expects Rules evidence while review items are open")

    res = evaluate()
    s = res["summary"]
    check(s["abstention_correctness"] == 1.0,
          f"the harness abstains exactly when it should ({s['abstention_correctness']})")
    check(s["unsupported_claim_rate"] == 0.0,
          f"no ungrounded claim survives ({s['unsupported_claim_rate']})")

    gated = [r for r in res["cases"] if r["kind"] in ("suspended-source", "review-gated")]
    check(all(r["decision"] == INSUFFICIENT_EVIDENCE for r in gated),
          "every suspended or unreviewed source yields INSUFFICIENT_EVIDENCE")
    check(all(not r["evidence_got"] for r in gated),
          "...and no inadmissible evidence leaks into the pack")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        main()
