"""Read a local .env so a key can live in a file instead of a shell session.

`export GEMINI_API_KEY=...` typed at a prompt dies with the shell that ran it, so
every fresh process sees nothing. A file survives. `.env` is line 4 of
`.gitignore`, so a key placed there cannot be committed.

## Two rules

**The real environment always wins.** A value already in `os.environ` is never
overwritten. Deployment sets real environment variables -- Cloud Run, CI, a
container -- and a stale `.env` silently shadowing a production secret is a bug
nobody finds until the wrong key is in use.

**Nothing here ever prints a value.** `report()` returns a length and the first
few characters, which is enough to tell "set" from "set to the wrong thing", and
not enough to leak. A key echoed into a log is a key in a log forever.

Run: python3 checker/env.py
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / ".env"


def load(path: Path | None = None, *, override: bool = False) -> tuple[str, ...]:
    """Load KEY=VALUE lines. Returns the names set, never the values."""
    p = path or DEFAULT
    if not p.is_file():
        return ()
    out = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key or (key in os.environ and not override):
            continue
        os.environ[key] = value
        out.append(key)
    return tuple(out)


def report(*names: str) -> str:
    """Whether each key is set, and enough of it to spot a paste error."""
    lines = []
    for n in names or ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY"):
        v = os.environ.get(n)
        lines.append(f"  {n:<20} " + (f"set ({len(v)} chars, {v[:5]}…)" if v
                                      else "not set"))
    return "\n".join(lines)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("env")
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / ".env"
        p.write_text('# a comment\nFOO_TEST_KEY=abc123\nBAR_TEST="quoted"\n\nbad line\n')
        os.environ.pop("FOO_TEST_KEY", None)
        os.environ.pop("BAR_TEST", None)
        names = load(p)
        check(set(names) == {"FOO_TEST_KEY", "BAR_TEST"},
              f"KEY=VALUE lines load; comments and malformed lines are skipped "
              f"({names})")
        check(os.environ["BAR_TEST"] == "quoted", "surrounding quotes are stripped")

        # The rule that matters in deployment.
        os.environ["FOO_TEST_KEY"] = "from_the_real_environment"
        load(p)
        check(os.environ["FOO_TEST_KEY"] == "from_the_real_environment",
              "a value already in the environment is NOT overwritten -- a stale "
              ".env shadowing a production secret is a bug nobody finds until the "
              "wrong key is in use")
        check(load(p, override=True) and os.environ["FOO_TEST_KEY"] == "abc123",
              "...unless override is asked for explicitly")

        r = report("FOO_TEST_KEY")
        check("abc123" not in r and "set (6 chars" in r,
              f"report names the key and its length, never its value: {r.strip()}")
        for k in ("FOO_TEST_KEY", "BAR_TEST"):
            os.environ.pop(k, None)

    check(load(Path("/nonexistent/.env")) == (),
          "a missing .env is not an error -- deployment has no file, only "
          "environment variables")
    check("not set" in report("DEFINITELY_NOT_SET_XYZ"),
          "an unset key reports as unset rather than as an empty string")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
