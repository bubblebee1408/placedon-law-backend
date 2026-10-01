#!/usr/bin/env python3
"""What the lawyer labels can and cannot support, per (task, body of law).

CAL-1's reporting half. `checker/calibration.py` has the rules; this reads the decisions a
lawyer actually made and prints, per bucket, how many labels exist and what follows.

Today the answer is "nothing follows", in two different ways, and the report keeps them
apart because they need different work:

    insufficient labels (n<100)   get more decisions
    enough labels, no score       nothing records a score, and C4 forbids a confidence
                                  field, so an admissible one has to be CODE-DERIVED

**This report makes no accuracy claim and cannot.** It says where review effort should go.
It says nothing about how often the engine is right, and a threshold out of it may never
gate an answer -- that would be a probability deciding a legal question, which
`checker/rings.py` and C4 both forbid.

Run: PYTHONPATH=. python3 scripts/calibration_report.py
"""
from __future__ import annotations

import sys


def report(rows, *, alpha: float = 0.1) -> str:
    """The printable report, from [{task, body, decision}] rows. Pure."""
    from checker.calibration import MIN_LABELS, Label, calibrate
    labels = [Label(task=str(r.get("task") or ""), body=str(r.get("body") or ""),
                    decision=str(r.get("decision") or ""),
                    # No score source exists yet; see the module docstring. Passing None
                    # rather than a stand-in is the whole point.
                    score=r.get("score"))
              for r in rows or ()]
    buckets = calibrate(labels, alpha=alpha)
    if not buckets:
        return ("calibration\n  no lawyer decisions are recorded.\n"
                f"  Nothing is calibrated and nothing changes. The floor is "
                f"{MIN_LABELS} labels per (task, body).")
    out = ["calibration", ""]
    for b in buckets:
        state = "READY" if b.ready else "not ready"
        out.append(f"  {b.task} / {b.body}")
        out.append(f"    labels {b.labels:<5} rejected {b.rejected:<5} "
                   f"scored {b.scored:<5} {state}")
        if b.threshold is not None:
            out.append(f"    threshold {b.threshold} at alpha={b.alpha}")
        out.append(f"    {b.note}")
        out.append("")
    ready = [b for b in buckets if b.ready]
    out.append(f"  {len(ready)} of {len(buckets)} bucket(s) can support a threshold.")
    out.append("  This says where REVIEW EFFORT should go. It is not an accuracy figure, "
               "and\n  a threshold from it may never gate an answer (C4, checker/rings.py).")
    return "\n".join(out)


def main() -> int:
    from gateway.store import select
    try:
        backend = select()
    except Exception as e:                                       # noqa: BLE001
        print(f"no store: {type(e).__name__}: {str(e)[:160]}")
        return 2
    print(report(backend.read_labels()))
    return 0


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("calibration_report")
    check("no lawyer decisions are recorded" in report([]),
          "no decisions at all says so, rather than printing an empty table")
    rows = [{"task": "research_question", "body": "CA2013", "decision": "REJECTED"}] * 40
    r = report(rows)
    check("insufficient labels (n<100)" in r,
          "40 labels report 'insufficient labels (n<100)' in those words")
    check("0 of 1 bucket(s) can support a threshold" in r,
          "...and the summary says nothing is ready")
    enough = [{"task": "t", "body": "b", "decision": "REJECTED", "score": float(i)}
              for i in range(100)]
    r2 = report(enough)
    check("READY" in r2 and "threshold" in r2,
          "100 scored rejections DO produce a threshold")
    # No accuracy CLAIM -- which is not the same as never saying the word. The footer
    # says "not an accuracy figure", and banning the string made that denial fail its own
    # test. What must not appear is a NUMBER presented as one.
    import re as _re
    _claim = _re.compile(r"(accuracy|accurate|correct)\s*(is|:|=)?\s*\d|"
                         r"\d+(\.\d+)?\s*%\s*(accurate|correct)", _re.IGNORECASE)
    check(not _claim.search(r + r2),
          "the report states no accuracy FIGURE -- no number presented as accuracy or as "
          "a percentage correct")
    check("not an accuracy figure" in r2,
          "...and says in words that what it does print is not one, which is why the "
          "check above looks for a claim and not for the word")
    check("may never gate an answer" in r2,
          "...and states that a threshold may never gate an answer")
    check("REVIEW EFFORT" in r2,
          "...and what it IS for: where review effort should go")
    noscore = [{"task": "t", "body": "b", "decision": "REJECTED"}] * 120
    check("NO item carries a score" in report(noscore),
          "enough labels but no score is reported as its OWN problem, not as too few "
          "labels")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main())
