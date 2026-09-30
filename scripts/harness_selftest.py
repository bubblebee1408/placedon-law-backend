#!/usr/bin/env python3
"""Does the gate prove WHICH suite passed, or only that something exited 0?

## The incident this reproduces

On 2026-09-30 an edit script assigned `p = gateway/schema.py`, read
`scripts/rls_integration.py` into the same variable, and wrote the result back to `p`.
`gateway/schema.py` was replaced wholesale by the RLS harness. **The gate stayed green.**

It stayed green because `gateway/schema.py` is invoked bare in `scripts/run_tests.sh`, the
RLS harness prints a banner and exits 0 when it is not given `--run`, and the harness's
own comment admitted the gap:

    *) return 1 ;;            # no count line: handled separately, not a mismatch

It was not handled separately. The caller's `else` branch printed `ok (no count)` and moved
on. So ANY file that exits 0 -- a script, a stub, an empty file -- passed as the suite whose
name it wore.

This module reproduces that end to end against the REAL harness: a temp copy of
`scripts/run_tests.sh` whose suite list is replaced with fixtures, one of them the incident's
exact shape. It then asserts the harness now refuses it, and -- because a check that cannot
fail proves nothing -- that a copy with the new rule removed still accepts it.

Run: PYTHONPATH=. python3 scripts/harness_selftest.py --test
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "scripts" / "run_tests.sh"

# The incident's shape: prints something that is not a count, exits 0. This is what
# rls_integration.py does without --run, and what the overwritten schema.py therefore did.
INCIDENT = """#!/usr/bin/env python3
print("scripts/rls_integration.py")
print("  (pass --run with PLACEDON_DATABASE_URL set to prove it against a real server)")
raise SystemExit(0)
"""

HEALTHY = """#!/usr/bin/env python3
print("  [PASS] something real")
print()
print("2/2 passed")
raise SystemExit(0)
"""

FAILING = """#!/usr/bin/env python3
print("  [FAIL] something real")
print()
print("1/2 passed")
raise SystemExit(0)
"""


def _harness_with(suite_paths, *, drop_rule: str = "") -> str:
    """A copy of the real harness whose suite list is `suite_paths` and whose extras are
    empty. `drop_rule` removes one line by regex, to prove the rule is load-bearing."""
    src = HARNESS.read_text(encoding="utf-8")
    # The copy lives in a temp dir, so its own `cd "$(dirname "$0")/.."` would land outside
    # the repo and check_deps.py would report BLOCKED. Pinned to the real root instead:
    # everything else about the harness is left exactly as it ships.
    src = src.replace('cd "$(dirname "$0")/.."', f'cd "{ROOT}"')
    listing = "\n".join(f"  {p}" for p in suite_paths)
    src = re.sub(r"^suites=\(.*?^\)", f"suites=(\n{listing}\n)", src,
                 count=1, flags=re.S | re.M)
    # The extras are emptied AT THE POINT OF USE rather than by deleting their
    # definitions. Deleting them left `extra[@]` unbound and every run died at line 95 --
    # the reproduction was measuring my regex, not the harness.
    src = src.replace("\nfails=0\n", "\nextra=()\nfails=0\n", 1)
    # bash 3.2 (what macOS ships) treats "${arr[@]}" on an EMPTY array as an unbound
    # variable under `set -u`. Only the copy ever has an empty extras list, so this is a
    # fixture concern and the shipped harness is left alone.
    src = src.replace('for e in "${extra[@]}"; do',
                      'for e in ${extra[@]+"${extra[@]}"}; do')
    if drop_rule:
        src = re.sub(drop_rule, "", src, flags=re.M)
    return src


def run_harness(fixtures: dict, *, drop_rule: str = "") -> tuple[int, str]:
    """Run a temp harness over `fixtures` ({name: source}). Returns (exit code, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        paths = []
        for name, source in fixtures.items():
            f = d / name
            f.write_text(source, encoding="utf-8")
            paths.append(str(f))
        script = d / "run_tests_copy.sh"
        script.write_text(_harness_with(paths, drop_rule=drop_rule), encoding="utf-8")
        # cd'ing to ROOT is what the real harness does; check_deps must find the repo.
        proc = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                              cwd=str(ROOT), timeout=300,
                              env={**os.environ, "PYTHONPATH": str(ROOT)})
        return proc.returncode, proc.stdout + proc.stderr


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

    # ── the harness still works on ordinary suites ──────────────────────────
    rc, out = run_harness({"good.py": HEALTHY})
    check(rc == 0 and "status=GREEN" in out,
          f"a suite printing '2/2 passed' is green (rc={rc})")

    rc, out = run_harness({"bad.py": FAILING})
    check(rc != 0 and "status=RED" in out,
          f"a suite printing '1/2 passed' is RED even though it exits 0 (rc={rc})")

    # ── THE INCIDENT ────────────────────────────────────────────────────────
    rc, out = run_harness({"overwritten.py": INCIDENT})
    check(rc != 0 and "status=RED" in out,
          f"a suite replaced by a script that prints no count and exits 0 is REFUSED "
          f"(rc={rc}) -- this is the schema.py incident, and it used to pass")
    check("NO COUNT" in out.upper() or "no count" in out,
          "...and the report says WHY, naming the missing count line")
    check("overwritten.py" in out,
          "...naming the suite, so a reader knows which file to look at")

    # A check that cannot fail proves nothing. With the rule removed, the incident passes
    # again -- which is the harness as it stood on the morning of 2026-09-30.
    rc_old, out_old = run_harness({"overwritten.py": INCIDENT},
                                  drop_rule=r"^\s*elif \[ -z \"\$res\" \]; then$\n"
                                            r"(?:^\s{4}.*$\n)*")
    check(rc_old == 0 and "status=GREEN" in out_old,
          f"...while the SAME fixture passes a harness with the rule removed "
          f"(rc={rc_old}) -- so the rule is what makes the difference, not the fixture")

    # ── mixed: one good, one overwritten ────────────────────────────────────
    rc, out = run_harness({"good.py": HEALTHY, "overwritten.py": INCIDENT})
    check(rc == 1 and "1 suite(s) failing" in out,
          f"one overwritten suite among healthy ones fails exactly one (rc={rc})")
    check("suites=2" in out, "...and the total still counts every suite")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test() if "--test" in sys.argv else _test())
