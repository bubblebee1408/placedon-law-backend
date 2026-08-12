"""
The three numbers. Not one accuracy score.

## Why not "accuracy"

Every planning document for this product proposes a single figure with a target above 85%. Two
things are wrong with that on a compliance product.

A 15% error rate on statements of law is not a passing grade; it is the product's core failure
mode written down as a KPI. Stanford RegLab measured Lexis+ AI at >17% and Westlaw at ~33% on
exactly the retrieve-then-generate design those documents propose, so 85% is not an ambitious
target — it is roughly where that architecture already lands.

More importantly, one number hides the trade-off that *is* this product. Abstaining is how we
avoid fabricating. Push abstention up and fabrication falls to zero while the product becomes
useless; push it down and coverage rises while wrong answers reappear. A single score moves for
either reason and tells you neither.

So: three numbers, always reported together.

    fabrication    claims not supported by source           target 0, not "low"
    coverage       questions answered rather than abstained  rises as verified_by fills
    wrong          abstained though the corpus DID support an answer   <- the real cost

The third is the one nothing measured. It is what this design pays for its safety, and until it
is counted, "we abstain when unsure" is an aspiration rather than a claim.

## Two columns, because today's coverage is 0 by design

`verified_by` is null on all 30 sections, so the product abstains on everything. That is the
designed state, not a defect, and measuring only it would report 0% coverage forever and teach
nobody anything.

So every metric is reported twice: as the product stands **now**, and against
`test_unlock.verified_copy()` — the same corpus with verification applied. The second column is
what one evening of a lawyer's time actually buys, in advance of spending it.

    python3 scripts/bench_answers.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class Row:
    question: str
    supported: bool          # does the corpus contain the governing section at all?
    abstained: bool
    fabricated: bool
    status: str


class _Stub:
    """
    Stands in for the model, so coverage measures the GATE and not the API key.

    Without this, `AskEngine(provisions=verified_copy())` opened the gate (status QUOTED) and
    then failed at the network call, reporting 0% coverage after verification and implying that
    a lawyer's evening buys nothing. It buys everything; the harness was measuring the absence of
    ANTHROPIC_API_KEY.

    The stub answers the way a correct answer looks: it quotes the retrieved section verbatim and
    cites it. That is deliberately the best case — the point is to measure how many questions the
    gate lets through, not how well a model writes.
    """

    text: str
    degraded = False

    def __init__(self, text: str) -> None:
        self.text = text


def _stub_generate(question, provisions, context):
    p = provisions[0]
    body = " ".join((p.get("text_statutory") or "")[:280].split())
    return _Stub(f"Under {p.get('citation', 's.?')}: “{body}”")


def measure(provisions: list[dict] | None, label: str) -> list[Row]:
    """Run every benchmark question through the ask path over the given corpus."""
    from checker import verifier                              # noqa: PLC0415
    from checker.ask_engine import AskEngine                  # noqa: PLC0415
    from scripts.bench_retrieval import CASES, ground_truth, load  # noqa: PLC0415

    corpus = provisions if provisions is not None else load()
    truth, _ = ground_truth(load())
    # provisions is keyword-only. Passing it positionally would silently become `generate`.
    engine = (AskEngine(provisions=corpus, generate=_stub_generate)
              if provisions is not None else AskEngine())
    by_num = {p["section_number"]: p for p in corpus}

    rows: list[Row] = []
    for c in CASES:
        want = truth[c.phrase]
        # "Supported" means the corpus holds the section that answers it. It always does here —
        # the ground truth was located IN this corpus — so any abstention is a cost, never a
        # correct refusal for want of text.
        supported = bool(want) and all(s in by_num for s in want)
        a = engine.ask(c.question, {"state": "IN-KA", "employees": 40})

        fabricated = False
        if not a.abstained and a.answer:
            # Verify against what was RETRIEVED, which is what verifier.py receives in
            # production — not against the ground-truth sections. Checking a quotation of s.11
            # against s.9's text reported 24% fabrication from a stub that copies source text
            # verbatim and therefore cannot fabricate at all. A fabrication rate a perfect
            # answerer cannot achieve is a measurement of the harness.
            cited = [int(x["section"].split(".")[-1].split("(")[0])
                     for x in a.sources if x.get("section", "").startswith("s.")]
            provs = [by_num[s] for s in cited if s in by_num] or \
                    [by_num[s] for s in want if s in by_num]
            fabricated = bool(verifier.verify_citations(a.answer, provs)
                              or verifier.check_hallucination(a.answer, provs))

        rows.append(Row(c.question, supported, a.abstained, fabricated, a.status))
    return rows


def report(rows: list[Row], label: str) -> dict:
    n = len(rows)
    answered = sum(1 for r in rows if not r.abstained)
    fabricated = sum(1 for r in rows if r.fabricated)
    wrong = sum(1 for r in rows if r.abstained and r.supported)
    return {"label": label, "n": n,
            "fabrication": round(fabricated / answered, 3) if answered else 0.0,
            "coverage": round(answered / n, 3) if n else 0.0,
            "wrong_abstention": round(wrong / n, 3) if n else 0.0,
            "answered": answered, "fabricated": fabricated, "wrong": wrong}


def main() -> int:
    from checker.test_unlock import verified_copy              # noqa: PLC0415

    print("  Running every benchmark question through the ask path.\n")
    now = report(measure(None, "now"), "as it stands (verified_by null)")
    after = report(measure(verified_copy(), "unlocked"), "after a lawyer verifies")

    print(f"  {'':<34}{'fabrication':>12}{'coverage':>11}{'wrong abst.':>13}")
    print("  " + "-" * 70)
    for r in (now, after):
        print(f"  {r['label']:<34}{r['fabrication']:>12.0%}{r['coverage']:>11.0%}"
              f"{r['wrong_abstention']:>13.0%}")

    print(f"\n  now:   {now['answered']}/{now['n']} answered, {now['fabricated']} fabricated, "
          f"{now['wrong']} abstained though the corpus held the answer")
    print(f"  after: {after['answered']}/{after['n']} answered, {after['fabricated']} fabricated, "
          f"{after['wrong']} abstained though the corpus held the answer")

    if now["coverage"] == 0:
        print("\n  0% coverage today is the DESIGNED state, not a defect. Every one of those is a")
        print("  'wrong abstention' only in the sense that the text exists and no lawyer has")
        print("  confirmed our reading of it. That is the gate, and it is not a code problem.")
    delta = after["coverage"] - now["coverage"]
    print(f"\n  What one evening of a lawyer's time buys: coverage {now['coverage']:.0%} -> "
          f"{after['coverage']:.0%} ({delta:+.0%}), fabrication {after['fabrication']:.0%}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
