#!/usr/bin/env python3
"""One command: walk the whole product on synthetic data, and say pass or fail.

P1. The orchestration is here rather than in `scripts/demo.sh` because bash capturing exit
codes, timing out children and parsing their output is error-prone in ways this repository
has no reason to accept -- `demo.sh` is a two-line wrapper that sets PYTHONPATH so nobody
has to know it, and `--test` below can then check the runner's own logic in the gate.

## PASS, BLOCKED and FAIL are three different things

Inherited from `scripts/demo_inhouse.py`, which states the reason better than a restatement
would: a demo that prints PASS for a step it could not run is worse than no demo, because
the next person reads a green column as working software. Every component here already
speaks that vocabulary through its exit code:

    0  PASS     it ran and produced what it claims
    2  BLOCKED  it could not run, and printed the reason -- no database, no credential.
                Not a failure of the code under test, so it does NOT fail the demo.
    *  FAIL     it ran and produced the wrong thing

`scripts/rls_integration.py` is the component that actually needs this: without a throwaway
database it returns 2 and says so, and reading that as either a pass or a failure would be
wrong in different directions.

## The exit code is the authority; the quoted line is only context

Each component prints its own summary, and this shows the last line of it. That line is
GREPPED, so it can be the wrong line -- it is labelled as the component's own words and the
verdict never depends on it. `--verbose` prints everything.

## What "the whole product" means here, and what it leaves out

Two product walks -- the lawyer's day, and documents through the vault pipeline -- then the
measurements that say whether what those produced is any good: the verifier against broken
quotes, retrieval against the dev split, the date arithmetic, and tenant isolation in the
database. The walks show it runs; the measurements show it is worth running.

It leaves out everything that needs a live model or a credential, because P1 says synthetic
data. So the draft step produces its templates and records "prose not generated" with the
reason, which is the honest output of this machine rather than a stub standing in for one.

Run: scripts/demo.sh
     scripts/demo.sh --verbose
     PYTHONPATH=. python3 scripts/demo.py --test
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"
BLOCKED_CODE = 2
TIMEOUT = 600           # a component that hangs must not hang the demo

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Component:
    name: str
    argv: tuple[str, ...]
    shows: str


# The walks first, then the measurements. Order is the story, not an accident.
COMPONENTS = (
    Component("the lawyer's day", ("scripts/demo_inhouse.py",),
              "sign in, open a matter, ask, map the event, review the NDA, draft, calendar"),
    Component("documents through the vault", ("scripts/vault_load_test.py", "--test"),
              "the real ingest pipeline: file store, guard, classifier, chunker, tagger"),
    Component("the verifier, against broken quotes",
              ("scripts/verifier_error_rates.py",),
              "false accepts per mutation class; exits nonzero on a negation or number"),
    Component("retrieval, against the dev split",
              ("scripts/retrieval_dev_metrics.py", "--test"),
              "recall@1/5/10, MRR, nDCG@5 with bootstrap intervals"),
    Component("the date arithmetic", ("scripts/date_properties.py",),
              "13 properties over 5,000 seeded dates, and 8 mutants that must be caught"),
    Component("tenant isolation in the database",
              ("scripts/rls_integration.py", "--run"),
              "one firm cannot read another's rows; needs a throwaway database"),
)


@dataclass
class Result:
    name: str
    state: str
    code: int
    seconds: float
    last_line: str
    output: str


def _run_one(c: Component) -> Result:
    started = time.monotonic()
    try:
        p = subprocess.run([sys.executable, *c.argv], cwd=ROOT, capture_output=True,
                           text=True, timeout=TIMEOUT,
                           env={**_env(), "PYTHONPATH": str(ROOT)})
        out, code = (p.stdout or "") + (p.stderr or ""), p.returncode
    except subprocess.TimeoutExpired:
        out, code = f"timed out after {TIMEOUT}s", 1
    state = PASS if code == 0 else (BLOCKED if code == BLOCKED_CODE else FAIL)
    return Result(c.name, state, code, time.monotonic() - started, _summary(out), out)


# Lines that read as a verdict, most specific first. Without this the quoted line is just the
# last one printed, which for a component ending in a paragraph of caveats is a sentence
# fragment -- true, and useless in a summary column.
_VERDICT = (r"\d+/\d+ passed[^\n]*", r"(?i)^\s*(?:REFUSED|BLOCKED)\b[^\n]*",
            r"(?i)no false accept[^\n]*", r"\d+ mutant\(s\) NOT caught[^\n]*", r"\d+/\d+ properties held[^\n]*")


def _summary(out: str) -> str:
    """The component's own verdict line, or its last line. Context only, never the authority."""
    import re
    for pattern in _VERDICT:
        found = re.findall(pattern, out, re.M)
        if found:
            return found[-1].strip()[:150]
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1][:150] if lines else "(no output)"


def _env() -> dict:
    import os
    return dict(os.environ)


def run(components=COMPONENTS) -> list[Result]:
    return [_run_one(c) for c in components]


def report(results: list[Result], *, verbose: bool = False) -> str:
    lines = ["", "  the product, on synthetic data", ""]
    width = max(len(r.name) for r in results) if results else 10
    for r in results:
        lines.append(f"  {r.state:<8} {r.name:<{width}}  {r.seconds:5.1f}s")
        lines.append(f"  {'':8} {'':<{width}}  said: {r.last_line}")
        if verbose:
            lines += [f"  {'':8} | {ln}" for ln in r.output.splitlines()]
        lines.append("")
    failed = [r for r in results if r.state == FAIL]
    blocked = [r for r in results if r.state == BLOCKED]
    passed = [r for r in results if r.state == PASS]
    lines.append(f"  {len(passed)}/{len(results)} passed, {len(blocked)} blocked, "
                 f"{len(failed)} failed")
    if blocked:
        lines.append("  BLOCKED is not a failure of the code: each one printed its reason "
                     "above. Nothing")
        lines.append("  here needs a model or a credential; a blocked component needs a "
                     "database.")
    if failed:
        lines.append("")
        lines.append(f"  FAIL: {', '.join(r.name for r in failed)}")
    lines.append("")
    lines.append("  PASS" if not failed else "  FAIL")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    results = run()
    print(report(results, verbose="--verbose" in argv))
    return 1 if any(r.state == FAIL for r in results) else 0


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

    print("demo")

    # ── every component exists and is reachable ────────────────────────────
    missing = [c.name for c in COMPONENTS if not (ROOT / c.argv[0]).exists()]
    check(not missing, f"every component script exists ({missing})")
    check(len(COMPONENTS) >= 6, f"the demo walks the whole product ({len(COMPONENTS)})")

    # ── the three states come from exit codes, and each is reachable ───────
    # Synthetic components, so this tests the RUNNER rather than re-running the product.
    def stub(code: int, text: str = "stub line") -> Component:
        return Component(f"stub-{code}",
                         ("-c", f"print({text!r}); raise SystemExit({code})"), "stub")

    # `-c` is passed to sys.executable, so argv[0] is the flag rather than a path.
    res = [_run_one(stub(0)), _run_one(stub(BLOCKED_CODE)), _run_one(stub(1)),
           _run_one(stub(7))]
    check([r.state for r in res] == [PASS, BLOCKED, FAIL, FAIL],
          f"exit 0 -> PASS, 2 -> BLOCKED, 1 and 7 -> FAIL ({[r.state for r in res]})")
    check(res[0].last_line == "stub line",
          f"the component's own last line is quoted ({res[0].last_line!r})")

    # ── THE property: the runner must be able to report FAIL ───────────────
    # A demo runner that always prints PASS is the classic way this goes wrong, and it
    # would pass every check above.
    text = report([_run_one(stub(0)), _run_one(stub(1))])
    check(text.rstrip().endswith("FAIL"),
          "one failing component makes the WHOLE demo print FAIL")
    check("FAIL: stub-1" in text, "...and names which one failed")

    # ── a BLOCKED component does NOT fail the demo ─────────────────────────
    text = report([_run_one(stub(0)), _run_one(stub(BLOCKED_CODE))])
    check(text.rstrip().endswith("PASS"),
          "a BLOCKED component does NOT fail the demo -- it could not run, which is not "
          "the same as running wrongly")
    check("BLOCKED is not a failure" in text,
          "...and the report says so, so a reader cannot mistake it for a pass either")
    check("1/2 passed, 1 blocked, 0 failed" in text,
          "...and all three are counted separately")

    # ── and FAIL wins over BLOCKED ─────────────────────────────────────────
    text = report([_run_one(stub(BLOCKED_CODE)), _run_one(stub(1))])
    check(text.rstrip().endswith("FAIL"),
          "FAIL beats BLOCKED in the verdict -- a demo with one broken component is not "
          "passing because another was skipped")

    # ── a hanging component cannot hang the demo ───────────────────────────
    check(TIMEOUT > 0 and isinstance(TIMEOUT, int),
          f"every component runs under a timeout ({TIMEOUT}s)")
    slow = Component("slow", ("-c", "import time; time.sleep(5)"), "stub")
    real = globals()["TIMEOUT"]
    try:
        globals()["TIMEOUT"] = 1
        r = _run_one(slow)
        check(r.state == FAIL and "timed out" in r.output,
              f"a component that exceeds the timeout is a FAIL, with the reason "
              f"({r.last_line[:40]!r})")
    finally:
        globals()["TIMEOUT"] = real
    check(globals()["TIMEOUT"] == real and TIMEOUT == 600,
          "...and the timeout is restored afterwards")

    # ── verbose shows the component output; quiet does not ─────────────────
    r0 = _run_one(stub(0, "a distinctive marker line"))
    check("a distinctive marker line" in report([r0], verbose=True),
          "--verbose prints the component's full output")

    # ── the shell wrapper exists and defers to this file ───────────────────
    sh = ROOT / "scripts" / "demo.sh"
    check(sh.exists(), "scripts/demo.sh exists -- P1 asks for ONE command")
    if sh.exists():
        body = sh.read_text(encoding="utf-8")
        check("demo.py" in body and "PYTHONPATH" in body,
              "...and it sets PYTHONPATH and defers here, rather than duplicating the "
              "orchestration in bash")
        import os
        check(os.access(sh, os.X_OK), "...and is executable, or it is not one command")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test() if "--test" in sys.argv else main())
