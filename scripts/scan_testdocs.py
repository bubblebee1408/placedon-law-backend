"""
Run the SS defect scanner against the REAL document corpus.

This is the check that matters. Every other test for defects.py was written by the same author as
the regexes, which is circular. These are documents the scanner did not author: ICSI's own
specimens, and real AGM notices / Regulation 30 filings from listed companies.

Note what this can and cannot measure. Every real document here is compliant, so this measures
FALSE POSITIVES only. Measuring false negatives needs documents known to be defective, and the
realistic source - minutes excerpts quoted in ROC adjudication orders - is behind the MCA WAF.

Run: python3 scripts/scan_testdocs.py
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker.ss.defects import Minutes, scan  # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "corpus/testdocs"


def main() -> None:
    files = sorted(p for p in DOCS.rglob("*.txt") if "_raw" not in p.parts)
    if not files:
        print(f"no .txt documents under {DOCS}"); raise SystemExit(2)

    per_check: dict[str, Counter] = {}
    evidence: dict[str, list[str]] = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        kind = "general" if "agm" in f.name.lower() or "egm" in f.name.lower() else "board"
        for fnd in scan(Minutes(text, kind)):
            per_check.setdefault(fnd.check_id, Counter())[fnd.status] += 1
            if fnd.status == "DEFECT" and not fnd.advisory_only:
                evidence.setdefault(fnd.check_id, []).append(f"{f.name}: {fnd.evidence[:60]}")

    n = len(files)
    print(f"=== SS scanner vs {n} real / specimen documents ===\n")
    print(f"{'check':<12} {'PASS':>5} {'DEFECT':>7} {'BOOK':>5} {'N/A':>5}   false-positive rate")
    print("-" * 62)
    for cid in sorted(per_check):
        c = per_check[cid]
        scored = c["PASS"] + c["DEFECT"]
        fp = c["DEFECT"] / scored * 100 if scored else 0
        flag = "  <-- OVER-FIRES" if fp > 40 and c["NEEDS_BOOK"] == 0 else ""
        print(f"{cid:<12} {c['PASS']:>5} {c['DEFECT']:>7} {c['NEEDS_BOOK']:>5} {c['N/A']:>5}   {fp:>5.1f}%{flag}")

    print("\nEvery real document in this corpus is compliant, so DEFECT here means FALSE POSITIVE.")
    print("Two exceptions are genuine and expected:")
    print("  - ICSI specimens are blank templates ('concluded at .... (Time)'), so value-level")
    print("    checks correctly find nothing. Template artifact, not a scanner bug.")
    print("  - ICSI's specimen AGM notice IS stale: it carries the s.139(1) ratification wording")
    print("    repealed by the Companies (Amendment) Act 2017, and 'service tax'. Zero defects on")
    print("    that clause would be the WRONG answer.")
    print("\nNot measured here: false negatives. Needs documents known to be defective; the")
    print("realistic source (minutes quoted in ROC orders) is behind the MCA WAF.")

    for cid, ex in sorted(evidence.items()):
        if len(ex) > n * 0.4:
            print(f"\n{cid} still fires on {len(ex)}/{n}:")
            for e in ex[:3]:
                print("   ", e)


if __name__ == "__main__":
    main()
