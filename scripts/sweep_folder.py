#!/usr/bin/env python3
"""Run an instrument backwards across a folder of documents.

    python3 scripts/sweep_folder.py ~/clients/acme
    python3 scripts/sweep_folder.py ~/clients/acme --json > affected.json

Answers the practitioner's actual question -- "a notification landed; which of my
files does it touch?" -- rather than the one every other surface here answers,
which is "given this document, what changed".

It narrows. It does not judge: a document in the queue is one to READ, not one
that is wrong. And it never drops a file it could not open or date; those are
printed last, under a heading that says they are unexamined rather than clear.

The only instrument wired today is G.S.R. 880(E), which moved the small-company
limits on 01-12-2025 and therefore puts every document drafted under G.S.R.
700(E) -- 15-09-2022 to 30-11-2025 -- in scope. Adding another means adding its
window and markers below, which is a deliberate constraint: a sweep for an
instrument whose window nobody has established would be a guess wearing a date.
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.sweep import (CITES_SUPERSEDED, SweepRefused, documents_in,  # noqa: E402
                           sweep, window_for)

# instrument key -> everything needed to sweep for it.
INSTRUMENTS = {
    "gsr880e": dict(
        fragment="G.S.R. 700(E)",          # the SUPERSEDED one defines the window
        superseded="G.S.R. 700(E), Specification of Definition Details "
                   "Amendment Rules, 2022",
        governed_from=date(2022, 9, 15),
        governed_to=date(2025, 11, 30),    # the day before 880(E) took effect
        markers=("4 crore", "4,00,00,000", "four crore",
                 "40 crore", "40,00,00,000", "forty crore"),
        about="G.S.R. 880(E) raised the small-company limits to Rs 10 crore / "
              "Rs 100 crore with effect from 01-12-2025"),
}


def run(folder: Path, key: str, as_json: bool) -> int:
    spec = INSTRUMENTS[key]
    try:
        window = window_for(spec["fragment"], superseded=spec["superseded"],
                            governed_from=spec["governed_from"],
                            governed_to=spec["governed_to"],
                            markers=spec["markers"])
    except SweepRefused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2

    docs = documents_in(folder)
    if not docs:
        print(f"no files found under {folder}", file=sys.stderr)
        return 3

    result = sweep(window, docs, as_of=date.today())

    if as_json:
        print(json.dumps(result.to_json(), indent=1))
        return 0

    print(f"\n{spec['about']}")
    print(f"window swept : {window.governed_from} .. {window.governed_to}")
    print(f"obligations  : {', '.join(window.obligations)}")
    print(f"folder       : {folder}\n")
    print(result.headline())

    queue = result.review_queue
    if queue:
        print(f"\nREAD THESE ({len(queue)}) -- in the window, so they MAY rest on "
              f"the superseded position. Being listed is not a defect.")
        for h in queue:
            flag = "cites" if h.verdict == CITES_SUPERSEDED else "     "
            extra = f"  [{', '.join(h.matched)}]" if h.matched else ""
            print(f"  {flag}  {h.doc_date}  {h.doc_id}{extra}")

    undecided = result.undecided
    if undecided:
        print(f"\nCOULD NOT DECIDE ({len(undecided)}) -- these were NOT examined. "
              f"They are not clear; they are unknown.")
        for h in undecided:
            print(f"         {h.doc_id}: {h.reason}")

    out = result.by_verdict("OUT_OF_WINDOW")
    print(f"\noutside the window: {len(out)} (this instrument does not reach them)")
    return 0


def _test() -> int:
    import tempfile
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [PASS] {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("sweep_folder")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "in_window_cites.txt").write_text(
            "Resolved on 2024-06-14 that the Company, being a small company with "
            "paid-up capital not exceeding Rs 4 crore, ...")
        (p / "in_window_quiet.txt").write_text("Resolved on 2023-01-09. Minutes.")
        (p / "after.txt").write_text("Resolved on 2026-02-02. Rs 4 crore.")
        (p / "undated.txt").write_text("Resolved. No date.")
        (p / "scan.docx").write_bytes(b"PK\x03\x04")

        docs = documents_in(p)
        window = window_for(INSTRUMENTS["gsr880e"]["fragment"],
                            superseded=INSTRUMENTS["gsr880e"]["superseded"],
                            governed_from=INSTRUMENTS["gsr880e"]["governed_from"],
                            governed_to=INSTRUMENTS["gsr880e"]["governed_to"],
                            markers=INSTRUMENTS["gsr880e"]["markers"])
        r = sweep(window, docs, as_of=date(2026, 9, 13))

        check(len(r.hits) == 5, f"every file appears in the result ({len(r.hits)})")
        check([h.doc_id for h in r.by_verdict(CITES_SUPERSEDED)]
              == ["in_window_cites.txt"],
              "the document that cites the superseded figure inside the window is "
              "flagged")
        check(len(r.review_queue) == 2,
              f"the queue narrows 5 files to {len(r.review_queue)} -- which is the "
              f"entire value on a folder of two thousand")
        check(len(r.undecided) == 2,
              "the undated file and the .docx are both reported, not skipped")
        check("not clear, they are unexamined" in r.headline(),
              "the headline says what 'could not decide' does not mean")
        check(all(d in r.to_json()["review_queue"][0] for d in ("doc_id", "reason")),
              "the export carries a reason per document")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--test":
        return _test()
    if not argv:
        print(__doc__)
        return 1
    folder = Path(argv[0]).expanduser()
    if not folder.is_dir():
        print(f"not a folder: {folder}", file=sys.stderr)
        return 1
    key = "gsr880e"
    for a in argv[1:]:
        if a.startswith("--instrument="):
            key = a.split("=", 1)[1]
    if key not in INSTRUMENTS:
        print(f"unknown instrument {key!r}; have: {', '.join(INSTRUMENTS)}",
              file=sys.stderr)
        return 1
    return run(folder, key, "--json" in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
