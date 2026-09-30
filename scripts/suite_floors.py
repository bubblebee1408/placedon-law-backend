#!/usr/bin/env python3
"""A suite may gain checks. It may not quietly lose them.

## What this catches that the count rule does not

`scripts/run_tests.sh` already refuses a suite that fails a check, and (since 2026-09-30) one
that prints no count at all. Neither notices a suite that still passes with FEWER checks than
it used to have. A suite edited down from 36 checks to 3 reports `3/3 passed` and is green —
which is exactly what deleting an inconvenient assertion looks like from the outside.

So each suite's passed count is recorded in `scripts/suite_floors.json`, committed, and a
suite reporting fewer than its floor is a FAILURE with both numbers printed.

## Floors rise by themselves and fall only in a commit

A suite that grows updates its own floor on the next green run, because a ratchet nobody
maintains is a ratchet that gets deleted. Lowering one is deliberately manual: it means
editing a committed file, which shows up in review with a message that has to say why.
There is no flag for it here, on purpose — a `--lower` option would be used.

This is the same shape as `checker/mvp_freeze.py`, which pins hand-verified mappings against
silent drift, and it exists for the same reason: the repository has twice paid for green
checks that could not turn red.

Run:  PYTHONPATH=. python3 scripts/suite_floors.py --gate <counts.tsv>
      PYTHONPATH=. python3 scripts/suite_floors.py --test
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOORS = ROOT / "scripts" / "suite_floors.json"


def load(path: Path | None = None) -> dict:
    p = path or FLOORS
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in raw.get("floors", {}).items()}


def save(floors: dict, path: Path | None = None) -> None:
    p = path or FLOORS
    p.write_text(json.dumps(
        {"note": ("Each suite's passed-check count, as a floor. A suite reporting fewer is "
                  "a FAILURE. Floors rise automatically on a green run; LOWERING one means "
                  "editing this file in a commit that says why."),
         "floors": dict(sorted(floors.items()))}, indent=2) + "\n", encoding="utf-8")


def compare(floors: dict, counts: dict) -> tuple[list, list, dict]:
    """(regressions, risen, new_floors).

    A suite absent from the floors is NOT a regression -- it is new, and its first green run
    sets its floor. A suite absent from `counts` is not judged here: it either failed or did
    not run, and `run_tests.sh` has already said so. Reporting it twice would double-count
    one defect.
    """
    regressions, risen = [], []
    new = dict(floors)
    for suite, count in counts.items():
        floor = floors.get(suite)
        if floor is None:
            new[suite] = count
            continue
        if count < floor:
            regressions.append((suite, floor, count))
        elif count > floor:
            risen.append((suite, floor, count))
            new[suite] = count
    return regressions, risen, new


def read_counts(path: Path) -> dict:
    """`suite<TAB>count` lines, as run_tests.sh writes them."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, count = line.partition("\t")
        name = name.strip()
        if not count.strip().isdigit():
            continue
        # A suite is a repo-relative path. Anything absolute came from somewhere else --
        # scripts/harness_selftest.py runs a harness copy over temp fixtures, and the first
        # version of this file happily recorded /var/folders/... as permanent suites.
        if name.startswith("/") or ".." in name:
            continue
        out[name] = int(count)
    return out


def gate(counts_path: Path, *, floors_path: Path | None = None, write: bool = True) -> int:
    floors = load(floors_path)
    counts = read_counts(counts_path)
    regressions, risen, new = compare(floors, counts)

    for suite, floor, count in risen:
        print(f"  floor raised  {suite}  {floor} -> {count}")
    for suite, floor, count in regressions:
        print(f"  FLOOR BREACH  {suite}  had {floor} checks, now reports {count}")

    if regressions:
        print(f"\n{len(regressions)} suite(s) report FEWER checks than their recorded floor.")
        print("Nothing is written. If the drop is intended, edit "
              "scripts/suite_floors.json in a commit that says why.")
        return 1

    if write and (risen or new.keys() != floors.keys()):
        save(new, floors_path)
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

    import tempfile

    base = {"a.py": 10, "b.py": 20}

    # ── the ratchet ─────────────────────────────────────────────────────────
    reg, risen, new = compare(base, {"a.py": 10, "b.py": 20})
    check(not reg and not risen and new == base, "unchanged counts change nothing")

    reg, risen, new = compare(base, {"a.py": 12, "b.py": 20})
    check(not reg and risen == [("a.py", 10, 12)] and new["a.py"] == 12,
          "a suite that GAINS checks raises its own floor")

    reg, risen, new = compare(base, {"a.py": 3, "b.py": 20})
    check(reg == [("a.py", 10, 3)],
          f"a suite that LOSES checks is a regression, with both numbers {reg}")
    check(new["a.py"] == 10,
          "...and the floor is NOT lowered by the run that breached it")

    reg, risen, new = compare(base, {"a.py": 10, "b.py": 20, "c.py": 5})
    check(not reg and new["c.py"] == 5,
          "a NEW suite is not a regression; its first run sets its floor")

    reg, _r, _n = compare(base, {"a.py": 10})
    check(not reg,
          "a suite MISSING from the counts is not judged here: it failed or did not run, "
          "and run_tests.sh has already said so -- reporting it twice double-counts one "
          "defect")

    # ── the gate, end to end, on temp files ─────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        fl, co = d / "floors.json", d / "counts.tsv"
        save({"a.py": 10}, fl)
        co.write_text("a.py\t10\nb.py\t7\n", encoding="utf-8")
        rc = gate(co, floors_path=fl)
        check(rc == 0, f"a green run exits 0 ({rc})")
        check(load(fl) == {"a.py": 10, "b.py": 7},
              f"...and the new suite's floor is written ({load(fl)})")

        co.write_text("a.py\t14\nb.py\t7\n", encoding="utf-8")
        gate(co, floors_path=fl)
        check(load(fl)["a.py"] == 14, "a risen floor is persisted")

        co.write_text("a.py\t9\nb.py\t7\n", encoding="utf-8")
        rc = gate(co, floors_path=fl)
        check(rc == 1, f"a breach exits non-zero ({rc})")
        check(load(fl)["a.py"] == 14,
              "...and NOTHING is written on a breach: the floor that caught it survives "
              "the run that broke it")

    # No input lowers a floor. Asserted on BEHAVIOUR over many inputs rather than by
    # scanning this file for the string "--lower": the docstring has to name the flag in
    # order to say it does not exist, so a source scan matches its own explanation. That
    # is the self-referential trap scripts/ingest_companies_act.py fell into once already.
    import random
    rng = random.Random(7)
    lowered = []
    for _ in range(200):
        f = {"s.py": rng.randint(1, 50)}
        c = {"s.py": rng.randint(1, 50)}
        _reg, _ris, after = compare(f, c)
        if after["s.py"] < f["s.py"]:
            lowered.append((f, c, after))
    check(not lowered,
          f"over 200 random (floor, count) pairs, NOTHING lowers a floor {lowered[:1]}")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        co = d / "counts.tsv"
        co.write_text(f"checker/real.py\t5\n{d}/fixture.py\t2\n", encoding="utf-8")
        got = read_counts(co)
        check(got == {"checker/real.py": 5},
              f"an ABSOLUTE path is not a suite and is ignored {got} -- the harness "
              f"self-test runs fixtures out of /tmp, and the first version of this file "
              f"recorded them as permanent suites")

    # ── the real file ───────────────────────────────────────────────────────
    real = load()
    check(real, f"the committed floors file holds {len(real)} suite(s)")
    check(all(isinstance(v, int) and v > 0 for v in real.values()),
          "...every floor a positive integer")
    check(FLOORS.is_file() and "floors" in json.loads(
              FLOORS.read_text(encoding="utf-8")),
          "...and the file is committed, not generated at run time")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    if "--gate" in sys.argv:
        raise SystemExit(gate(Path(sys.argv[sys.argv.index("--gate") + 1])))
    print(__doc__.strip().splitlines()[0])
    raise SystemExit(2)
