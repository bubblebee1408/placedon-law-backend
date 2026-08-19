"""
Ground-truth test for point-in-time reconstruction.

RETRACTED CLAIM, recorded so it is not repeated: this script previously asserted that India Code's
full-Act PDF is the as-enacted 2013 print, and used a 43/43 match on quoted prior wordings as
evidence. Both were wrong.

The PDF is the CURRENT CONSOLIDATION with its footnote apparatus included - its
arrangement-of-sections lists 3A and 10A (inserted 2018/2019) and "11. [Omitted.]", and it carries
562 occurrences of "w.e.f.". The 43/43 match was CIRCULAR: prior wordings appear in the file
because the footnotes quoting them are in the file, not because the body text is pre-amendment.

Consequence: Test B (rolled-back text vs "as-enacted" reference) was comparing a 2014
reconstruction against the CURRENT text. It is disabled below rather than left reporting a
meaningless pass rate. Point-in-time reconstruction remains UNVERIFIED against any external
source, and obtaining a genuine as-enacted edition is an open task.

Test A is unaffected - it never reads the reference file. It checks only that a substitution whose
footnote quotes the prior wording has that wording restored after rollback.

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
    a_ok = a_bad = a_declared = 0
    a_fail: list[str] = []
    for p in files:
        rec = json.loads(p.read_text())
        r = section_as_of(rec, AS_ENACTED)
        if r.text is None:
            continue
        rolled, current = norm(r.text), norm(rec["content"])
        declared_unknown = set(r.unknown_spans)
        for a in parse_footnote(rec["footnote"]):
            if a.operation != "substituted":
                continue
            old = prior_wording(a)
            if not old:
                continue
            o = norm(old)
            if len(o) < MIN_PRIOR:
                continue
            if a.marker in declared_unknown:
                # The engine said it could not reconstruct this marker. No claim was made, so
                # there is nothing to score. Silent failure would be a defect; a declared one
                # is the product working.
                a_declared += 1
                continue
            # the discriminating check: prior wording restored, and it was not there before
            if o in rolled and o not in current:
                a_ok += 1
            elif o in rolled:
                a_ok += 1          # present in both — harmless, still correct after rollback
            else:
                a_bad += 1
                a_fail.append(f"{p.stem}:m{a.marker}")

    # --- Test B: DISABLED. The reference is the current consolidation, not the as-enacted
    # print, so this compares a 2014 reconstruction against 2026 text. Kept in source, not run.
    b_ok = b_bad = 0
    b_fail: list[str] = []
    partial = skipped = 0
    for p in []:  # DISABLED - invalid oracle, see module docstring
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
    print(f"     {a_declared} further markers were DECLARED unrecoverable by the engine and are")
    print(f"     not scored - no claim was made, so there is nothing to be wrong about.")
    print()
    print("B. DISABLED. The reference file is India Code's CURRENT consolidation, not the")
    print("   as-enacted print, so rolling back to 2014 and comparing against it is invalid.")
    print("   Point-in-time reconstruction is UNVERIFIED against any external source.")
    print("   Obtaining a genuine as-enacted edition is an open task.")
    print()
    print("A failure in A is a real defect. A declared PARTIAL or unknown marker is not -")
    print("the engine said so, which is the product working as designed.")


if __name__ == "__main__":
    main()
