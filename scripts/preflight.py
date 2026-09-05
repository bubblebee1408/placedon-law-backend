"""
Check whether this checkout can actually run, and say what to do if not.

The statutory corpus is deliberately not in version control (see README.md — a public repository of
bare Act text is an Act download, which Copyright Act 1957 s.52(1)(q)(ii) does not permit and
CLAUDE.md forbids this project from building). It regenerates from the ingestion scripts.

Without this, a fresh clone's first command is a FileNotFoundError pointing at a JSON file the
reader has no reason to know about. That is a bad first five minutes and an avoidable one.

Run: python3 scripts/preflight.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED = [
    ("corpus/companies_act/_index.json",
     "section number -> corpus id index",
     "python3 scripts/ingest_companies_act.py && python3 scripts/build_section_index.py"),
    ("corpus/admission",
     "admission records and the review queue",
     "python3 scripts/seed_admission.py"),
]

OPTIONAL = [
    ("corpus/sources/companies_meetings_board_powers_rules_2014.pdf",
     "the Board Powers Rules gazette",
     "see docs/ACQUISITION_HANDOFF_board_rules_2014.md — a human must download it"),
    ("corpus/rules/board_powers_2014.json",
     "the parsed Rules",
     "python3 scripts/parse_board_rules.py (needs the gazette above)"),
]


def main() -> int:
    missing_required, missing_optional = [], []
    print("Placedon backend — preflight\n")

    for path, what, fix in REQUIRED:
        present = (ROOT / path).exists()
        print(f"  [{'ok' if present else 'MISSING'}] {what}")
        if not present:
            missing_required.append((path, fix))

    for path, what, fix in OPTIONAL:
        present = (ROOT / path).exists()
        print(f"  [{'ok' if present else '--'}] {what}"
              + ("" if present else "   (optional)"))
        if not present:
            missing_optional.append((path, fix))

    if missing_required:
        print("\nThis checkout cannot run yet. The statutory corpus is not in version control")
        print("on purpose — a public repository of bare Act text is an Act download. Rebuild it:\n")
        seen = set()
        for _, fix in missing_required:
            if fix not in seen:
                print(f"  {fix}")
                seen.add(fix)
        print("\nIngestion fetches from India Code and needs network access.")
        return 1

    print("\nReady. Try:  python3 scripts/slice_s96.py")
    if missing_optional:
        print("\nNot present, and not needed for the Section 96 slice:")
        for path, fix in missing_optional:
            print(f"  {path}\n    {fix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
