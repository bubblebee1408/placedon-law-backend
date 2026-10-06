"""Git merge driver for docs/REPO_MAP.md: regenerate, never hand-merge.

The map is generated from the code (`scripts/repo_map.py`), so a merge conflict on it is
noise -- both branches regenerated it, and the merged WORKING TREE already has the real
module set. The driver throws away both conflicting versions and writes a fresh map built
from the tree being merged.

Registered by `setup.sh` as:

    git config merge.repomap.driver "python3 scripts/merge_repo_map.py %A"

and selected by `.gitattributes`. Git passes %A (ours), which is both ignored as input and
used as the output path. Exit 0 means resolved.

The map the driver writes may be one regeneration behind if code files are themselves still
being merged in the same operation -- the gate regenerates and checks it anyway, so the
committed result converges. What this kills is the textual conflict, which never carried
information a regeneration could not recover.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_map  # noqa: E402


def main(argv: list[str]) -> int:
    out_path = argv[1]
    Path(out_path).write_text(repo_map.render(repo_map.tracked_python()), encoding="utf-8")
    return 0


def _test() -> None:
    import tempfile

    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "REPO_MAP.md"
        # A file full of conflict markers: the driver must ignore it entirely and regenerate.
        target.write_text("<<<<<<< HEAD\ngarbage\n=======\nmore garbage\n>>>>>>> x\n")
        rc = main(["merge_repo_map.py", str(target)])
        body = target.read_text(encoding="utf-8")
        check(rc == 0, "the driver exits 0 (resolved)")
        check("<<<<<<<" not in body and ">>>>>>>" not in body,
              "the conflict markers are gone -- the input was discarded, not merged")
        check("`gateway/verbs.py`" in body and "modules listed" in body,
              "a real regenerated map was written")
        check(body == repo_map.render(repo_map.tracked_python()),
              "the output equals a fresh generation, so the gate's staleness check passes")

    print(f"{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        sys.exit(main(sys.argv))
