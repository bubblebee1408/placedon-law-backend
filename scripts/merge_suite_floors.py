"""Git merge driver for scripts/suite_floors.json: the MAX floor per suite, never a lower.

Two branches both ratchet floors up as they run green, so a merge nearly always conflicts on
this file -- and the one correct resolution is mechanical: keep the higher floor for every
suite, and keep every suite either side has. A human resolving it by hand can only get it
wrong (and has: the whole reason this exists is the merge churn across #68/#69/#71). So the
resolution is code.

Registered by `setup.sh` as:

    git config merge.suitefloors.driver "python3 scripts/merge_suite_floors.py %O %A %B"

and selected by `.gitattributes`. Git calls it with %O (ancestor), %A (ours -- also the
file to leave the result in) and %B (theirs). Exit 0 means resolved.

A floor may be a plain int, or a capability-gated dict
`{"floor": N, "requires": "<import>", "unavailable_floor": M}`. The gate on the dict is kept,
and the recorded floor `N` and the `unavailable_floor` `M` are each taken at their max -- the
gate is a property of the suite, not of a branch, so a merge must never drop it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The driver runs from the repo root; `scripts/` is not on the path there. Reuse
# suite_floors.load/save so the merged file is byte-identical to what the gate writes --
# a driver that serialised JSON its own way would churn the file on every merge.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite_floors import load, save  # noqa: E402


def _floor_of(spec) -> int:
    return int(spec["floor"]) if isinstance(spec, dict) else int(spec)


def merge_spec(a, b):
    """The higher floor, keeping any capability gate. Either side may be absent (None)."""
    if a is None:
        return b
    if b is None:
        return a
    floor = max(_floor_of(a), _floor_of(b))
    da = a if isinstance(a, dict) else None
    db = b if isinstance(b, dict) else None
    if not (da or db):
        return floor
    merged = dict(da or db)              # carry requires / unavailable_floor
    merged["floor"] = floor
    requires = next((d.get("requires") for d in (da, db) if d and d.get("requires")), None)
    if requires:
        merged["requires"] = requires
    unavs = [d["unavailable_floor"] for d in (da, db)
             if d and d.get("unavailable_floor") is not None]
    if unavs:
        merged["unavailable_floor"] = max(int(u) for u in unavs)
    return merged


def merge_floors(ours: dict, theirs: dict) -> dict:
    return {s: merge_spec(ours.get(s), theirs.get(s)) for s in set(ours) | set(theirs)}


def main(argv: list[str]) -> int:
    # %O %A %B — ancestor, ours, theirs. The ancestor is not needed: max is associative and
    # a floor only ever rises, so there is no "deleted on one side" case to honour.
    _ancestor, ours_path, theirs_path = argv[1], argv[2], argv[3]
    merged = merge_floors(load(Path(ours_path)), load(Path(theirs_path)))
    save(merged, Path(ours_path))
    return 0


def _test() -> None:
    import json
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

    # ── the spec merge, directly ────────────────────────────────────────────
    check(merge_spec(10, 7) == 10, "two ints take the higher")
    check(merge_spec(7, 10) == 10, "...in either order")
    check(merge_spec(10, None) == 10, "a suite only one side has is kept")
    check(merge_spec(None, 7) == 7, "...from either side")

    gated = {"floor": 8, "requires": "sentence_transformers", "unavailable_floor": 1}
    m = merge_spec(gated, 12)
    check(isinstance(m, dict) and m["floor"] == 12 and m["requires"] == "sentence_transformers"
          and m["unavailable_floor"] == 1,
          f"a gate survives a merge against a plain int, floor rises to 12 ({m})")
    m2 = merge_spec({"floor": 8, "requires": "x", "unavailable_floor": 1},
                    {"floor": 5, "requires": "x", "unavailable_floor": 3})
    check(m2["floor"] == 8 and m2["unavailable_floor"] == 3,
          f"two gated specs take the max of BOTH floor and unavailable_floor ({m2})")

    # ── the whole-file merge, never lowering ────────────────────────────────
    ours = {"a.py": 10, "b.py": 5, "c.py": 20}
    theirs = {"a.py": 7, "b.py": 9, "d.py": 3}
    merged = merge_floors(ours, theirs)
    check(merged == {"a.py": 10, "b.py": 9, "c.py": 20, "d.py": 3},
          f"union of suites, max of shared floors, none lowered ({merged})")
    for s in set(ours) | set(theirs):
        want = max(ours.get(s, 0), theirs.get(s, 0))
        check(_floor_of(merged[s]) >= want, f"{s} is not below either parent")

    # ── the driver end to end, with the gate's own serialisation ────────────
    with tempfile.TemporaryDirectory() as d:
        o = Path(d) / "O"; a = Path(d) / "A"; b = Path(d) / "B"
        save(ours, a)
        save(theirs, b)
        o.write_text("{}\n")
        rc = main(["merge_suite_floors.py", str(o), str(a), str(b)])
        check(rc == 0, "the driver exits 0 (resolved)")
        got = json.loads(a.read_text())
        check(got["floors"]["a.py"] == 10 and got["floors"]["d.py"] == 3,
              "the written file carries the merged floors")
        check("note" in got and list(got["floors"]) == sorted(got["floors"]),
              "...in the gate's canonical shape (note + sorted floors), so no spurious diff")

    print(f"{passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        sys.exit(main(sys.argv))
