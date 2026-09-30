#!/usr/bin/env python3
"""Ingest the Companies Act 2013. Thin wrapper over `scripts/ingest_act.py`.

The implementation moved to `ingest_act.py` on 2026-09-27 so that one ingester serves every
Act in its register. This entry point is kept because it is the name in
`scripts/preflight.py`'s fresh-clone instructions and in several dated reports, and because
deleting a command people have in their shell history is a cost with no benefit.

**One copy of the logic, and this file proves it rather than asserting it.** The last wrapper
in this repository whose docstring said "one copy, no drift" was `.claude/scripts/verify.py`,
which `runpy`'d a file that had been deleted and raised FileNotFoundError on every
invocation for weeks. Nothing tested it. So `_test()` below asserts that the delegate
exists, that it is importable, that the Act key this file passes is really in its register,
and that this file contains no ingestion logic of its own to drift.

Run:  python3 scripts/ingest_companies_act.py [--limit N]     # == ingest_act.py companies_act
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import ingest_act                                              # noqa: E402

ACT_KEY = "companies_act"


def main(argv: list[str]) -> int:
    return ingest_act.main([ACT_KEY] + [a for a in argv if a != ACT_KEY])


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

    print("ingest_companies_act (wrapper)")

    # The failure mode this file exists to avoid: a wrapper pointing at nothing.
    check((ROOT / "scripts/ingest_act.py").exists(),
          "the delegate scripts/ingest_act.py is on disk")
    check(hasattr(ingest_act, "main") and hasattr(ingest_act, "ACTS"),
          "...and exposes main() and ACTS")
    check(ACT_KEY in ingest_act.ACTS,
          f"...and {ACT_KEY!r} is in its register, so this wrapper cannot pass a key that "
          f"resolves to nothing")
    act = ingest_act.ACTS[ACT_KEY]
    check(not act.pending,
          "...and that entry is READY (a confirmed actid and handle), not PENDING_ID")
    check("indiacode.gov.in" in (act.handle or ""),
          f"...on the permitted host ({act.handle})")

    # No logic of its own means nothing to drift out of step with the delegate.
    # Only the code ABOVE _test() is scanned: the token list below is itself made of these
    # strings, so scanning the whole file makes the check fail on its own evidence. Found
    # by writing it the naive way first.
    whole = Path(__file__).read_text(encoding="utf-8")
    code = whole.split("def _test(")[0]
    for token in ("urlopen", "sha256", "_manifest", "hashlib", "PdfReader"):
        check(token not in code,
              f"this wrapper contains no {token!r} -- the logic lives in one file only")
    check("ingest_act.main" in code,
          "...and it delegates by CALLING ingest_act.main, not by copying it")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main(sys.argv[1:]))
