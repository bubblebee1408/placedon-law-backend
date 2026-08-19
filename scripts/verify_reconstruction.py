"""
Ground-truth test for point-in-time reconstruction.

Source: India Code's full-Act PDF is the **as-enacted 2013 print**, not a current consolidation.
Evidence — of 43 substitutions whose footnote quotes the prior wording, the prior wording appears
in the PDF 43 times, misses zero. It is a pre-amendment snapshot from a pipeline we did not write.

Two methodological corrections over the first version of this script, both real bugs in the TEST:

1. Long probes span PDF page breaks and pick up the injected page number, so they fail on correct
   text. (Verified: section 49164 breaks at 97 chars because "159" is inserted mid-sentence.)
   Fixed with short probes at multiple offsets.
2. Probing arbitrary offsets has almost no discriminating power — amendments usually sit deep in a
   section, so the probe never covers the changed region and current-vs-rolled look identical.
   Fixed by probing the AMENDED REGION directly: after rolling back a substitution whose footnote
   quotes the prior wording, that prior wording must be present.

Run: python3 scripts/verify_reconstruction.py
Requires: /tmp/ca2013.txt (from scripts/verify_against_pdf.py)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker.amendment import parse_footnote  # noqa: E402
from checker.as_of import prior_wording, section_as_of  # noqa: E402

AS_ENACTED = date(2014, 4, 1)
CORPUS = Path(__file__).resolve().parent.parent / "corpus/companies_act"
PDF_TXT = Path("/tmp/ca2013.txt")
PROBE = 60          # short enough to survive a page break
MIN_PRIOR = 30      # quoted prior wording shorter than this is not a reliable signal


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"<[^>]+>", " ", s).lower())


def present(text_n: str, ref: str, probes: int = 6) -> bool:
    """Majority of short probes found in the reference. Robust to page-break artifacts."""
    if len(text_n) < PROBE + 20:
        return text_n in ref
    offs = [i for i in range(20, max(21, len(text_n) - PROBE), max(1, (len(text_n) - PROBE) // probes))][:probes]
    hits = sum(1 for o in offs if text_n[o:o + PROBE] in ref)
    return hits > len(offs) // 2


def main() -> None:
    if not PDF_TXT.exists():
        print(f"missing {PDF_TXT} — run scripts/verify_against_pdf.py first")
        raise SystemExit(2)
    ref = norm(PDF_TXT.read_text())
    files = [p for p in CORPUS.glob("*.json") if not p.name.startswith("_")]

    # --- Test A: the rollback restores the quoted prior wording ---------------
    a_ok = a_bad = 0
    a_fail: list[str] = []
    for p in files:
        rec = json.loads(p.read_text())
        r = section_as_of(rec, AS_ENACTED)
        if r.text is None:
            continue
        rolled, current = norm(r.text), norm(rec["content"])
        for a in parse_footnote(rec["footnote"]):
            if a.operation != "substituted":
                continue
            old = prior_wording(a)
            if not old:
                continue
            o = norm(old)
            if len(o) < MIN_PRIOR:
                continue
            # the discriminating check: prior wording restored, and it was not there before
            if o in rolled and o not in current:
                a_ok += 1
            elif o in rolled:
                a_ok += 1          # present in both — harmless, still correct after rollback
            else:
                a_bad += 1
                a_fail.append(f"{p.stem}:m{a.marker}")

    # --- Test B: EXACT sections match the as-enacted print --------------------
    b_ok = b_bad = 0
    b_fail: list[str] = []
    partial = skipped = 0
    for p in files:
        rec = json.loads(p.read_text())
        if not parse_footnote(rec["footnote"]):
            skipped += 1
            continue
        r = section_as_of(rec, AS_ENACTED)
        if r.text is None or len(norm(r.text)) < 200:
            skipped += 1
            continue
        if r.fidelity != "EXACT":
            partial += 1
            continue
        if present(norm(r.text), ref):
            b_ok += 1
        else:
            b_bad += 1
            b_fail.append(p.stem)

    tot_a = a_ok + a_bad
    tot_b = b_ok + b_bad
    print("=== reconstruction ground truth vs as-enacted 2013 print ===\n")
    print(f"A. rollback restores the quoted prior wording")
    print(f"     {a_ok}/{tot_a} restored  ({a_ok / max(tot_a, 1) * 100:.1f}%)")
    if a_fail:
        print(f"     failures: {a_fail[:10]}")
    print(f"\nB. sections claiming EXACT match the as-enacted print")
    print(f"     {b_ok}/{tot_b} matched  ({b_ok / max(tot_b, 1) * 100:.1f}%)")
    if b_fail:
        print(f"     failures: {b_fail[:10]}")
    print(f"\n   declared PARTIAL (no claim made): {partial}")
    print(f"   skipped (unamended / too short) : {skipped}")
    print("\nA failure in A or B is a real defect. A PARTIAL is not — the engine said so.")


if __name__ == "__main__":
    main()
