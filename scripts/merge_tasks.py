"""Git merge driver for research/TASKS.md: a three-way merge, with conflicts unioned by row.

TASKS.md is the task ledger. Two branches each append rows, so a merge conflicts on the
table almost every time -- and the right resolution is "keep every row from both sides",
which is what the merge churn kept doing by hand.

The driver runs the ordinary three-way merge first (`git merge-file`). Where that leaves a
conflict, it UNIONS the two sides of the hunk: a table row -- a line beginning `| <id> |` --
is keyed by its id, with OURS winning a clash (so a row edited on our side is kept over the
ancestor's wording on theirs); every other line is deduplicated by exact text. Order is
preserved: ours first, then whatever theirs adds that ours did not have.

Registered by `setup.sh` as:

    git config merge.tasks-union.driver "python3 scripts/merge_tasks.py %O %A %B"

Git calls it with %O (ancestor), %A (ours, and the output file) and %B (theirs). Exit 0.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROW = re.compile(r"^\|\s*([^|]+?)\s*\|")  # a markdown table row, keyed by its first cell


def _row_id(line: str) -> str | None:
    m = ROW.match(line)
    return m.group(1).strip() if m else None


def union_hunk(ours: list[str], theirs: list[str]) -> list[str]:
    """Ours, then every line of theirs ours did not already carry.

    Table rows are identified by their first cell, so a row present on both sides appears
    once (ours), and a row only theirs has is appended. Non-row lines dedupe on exact text.
    """
    out = list(ours)
    seen_ids = {rid for rid in (_row_id(l) for l in ours) if rid}
    seen_lines = set(ours)
    for line in theirs:
        rid = _row_id(line)
        if rid is not None:
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
        elif line in seen_lines:
            continue
        seen_lines.add(line)
        out.append(line)
    return out


def resolve(merged_text: str) -> str:
    """Replace every `<<<<<<< / ======= / >>>>>>>` block with the union of its two sides."""
    lines = merged_text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<<"):
            j = i + 1
            ours: list[str] = []
            while j < len(lines) and not lines[j].startswith("======="):
                ours.append(lines[j]); j += 1
            k = j + 1
            theirs: list[str] = []
            while k < len(lines) and not lines[k].startswith(">>>>>>>"):
                theirs.append(lines[k]); k += 1
            out.extend(union_hunk(ours, theirs))
            i = k + 1  # skip the closing >>>>>>> marker
        else:
            out.append(lines[i]); i += 1
    return "".join(out)


def three_way(ancestor: str, ours: str, theirs: str) -> str:
    """`git merge-file -p`, which prints the merge with conflict markers where it cannot."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        o = Path(d) / "O"; a = Path(d) / "A"; b = Path(d) / "B"
        o.write_text(ancestor, encoding="utf-8")
        a.write_text(ours, encoding="utf-8")
        b.write_text(theirs, encoding="utf-8")
        proc = subprocess.run(
            ["git", "merge-file", "-p", "--", str(a), str(o), str(b)],
            capture_output=True, text=True)
        # Exit code is the conflict count (>=0) on a clean run, <0 on error. Either way the
        # stdout is the merged text; a negative exit is a real failure we must not swallow.
        if proc.returncode < 0:
            raise RuntimeError(f"git merge-file failed: {proc.stderr.strip()}")
        return proc.stdout


def merge_text(ancestor: str, ours: str, theirs: str) -> str:
    return resolve(three_way(ancestor, ours, theirs))


def main(argv: list[str]) -> int:
    ancestor_path, ours_path, theirs_path = argv[1], argv[2], argv[3]
    merged = merge_text(
        Path(ancestor_path).read_text(encoding="utf-8"),
        Path(ours_path).read_text(encoding="utf-8"),
        Path(theirs_path).read_text(encoding="utf-8"))
    Path(ours_path).write_text(merged, encoding="utf-8")
    return 0


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    base = "# Tasks\n\n| id | what |\n|---|---|\n| A-1 | one |\n"
    ours = base + "| A-2 | two (ours) |\n"
    theirs = base + "| A-3 | three (theirs) |\n"
    merged = merge_text(base, ours, theirs)
    check("| A-1 | one |" in merged, "a shared row survives")
    check("| A-2 | two (ours) |" in merged, "a row only ours added survives")
    check("| A-3 | three (theirs) |" in merged, "a row only theirs added survives")
    check("<<<<<<<" not in merged and ">>>>>>>" not in merged,
          "no conflict markers are left behind")

    # A row edited on BOTH sides: ours wins, and it appears exactly once.
    o2 = "| A-1 | base |\n"
    ours2 = "| A-1 | ours wins |\n| A-2 | two |\n"
    theirs2 = "| A-1 | theirs loses |\n| A-4 | four |\n"
    m2 = merge_text(o2, ours2, theirs2)
    check(m2.count("| A-1 |") == 1, "a row changed on both sides appears once")
    check("ours wins" in m2 and "theirs loses" not in m2, "ours wins the clash")
    check("| A-2 | two |" in m2 and "| A-4 | four |" in m2, "both sides' new rows are kept")

    # union_hunk is order-stable: ours first, theirs' additions after.
    uh = union_hunk(["| A-2 | x |\n"], ["| A-2 | y |\n", "| A-9 | z |\n"])
    check(uh == ["| A-2 | x |\n", "| A-9 | z |\n"],
          f"union keeps ours' row and appends only theirs' new id ({uh})")

    print(f"{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        sys.exit(main(sys.argv))
