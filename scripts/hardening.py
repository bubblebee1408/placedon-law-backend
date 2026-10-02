#!/usr/bin/env python3
"""P2's cross-cutting invariants, asserted structurally rather than by convention.

Three of P2's parts are not a feature in one file, they are a property of the whole
repository: every outbound call has a timeout, no log line carries document text, and the
things that bound a request are actually wired into the request path. A comment saying so
relies on every future diff being read by someone who remembers. These walk the code.

The technique is `checker/rings.py`' and `checker/entailment_gate.py`', pointed at hardening:
parse each module and look at what it DOES, because a grep for "timeout" matches the word in a
docstring explaining that there isn't one.

## No exception list, on purpose

`scripts/serve_api.py` had three untimed `urlopen` calls -- a test client against its own
in-process server, so the risk was a hung gate rather than a hung request. They were given
timeouts rather than an entry in an allow-list here, because an invariant with three
exceptions is an invariant where the fourth one hides. If a future call genuinely cannot
carry a timeout, the honest move is to argue for it in the diff, not to add a name here.

## Each sweep proves it can find a violation

A clean structural result is the kind most prone to vacuity: a scanner with a typo in its
matcher reports zero findings and looks like a pass. So every sweep below is also run against
a synthetic violation and must find it.

Run: PYTHONPATH=. python3 scripts/hardening.py --test
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = (".claude/", "build/", ".git/", "node_modules/")

# Field names that carry a document's own text. A log line with one of these in it has put a
# client's contract into a log file, which is the thing P2 forbids.
DOCUMENT_TEXT_FIELDS = ("text", "raw_text", "reading_text", "content", "body", "quote",
                        "page_text", "extracted_text", "document_text", "chunk")


def _modules():
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIP_DIRS):
            continue
        try:
            yield rel, ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return ""


def untimed_outbound(trees=None) -> list[str]:
    """Every `urlopen(...)` with no `timeout=`. A socket with no timeout waits forever."""
    out = []
    for rel, tree in (trees if trees is not None else _modules()):
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and _call_name(n) == "urlopen":
                if "timeout" not in {k.arg for k in n.keywords}:
                    out.append(f"{rel}:{n.lineno}")
    return out


def outbound_count(trees=None) -> int:
    """How many `urlopen` calls exist at all. A sweep over nothing proves nothing."""
    total = 0
    for _rel, tree in (trees if trees is not None else _modules()):
        total += sum(1 for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and _call_name(n) == "urlopen")
    return total


# Functions whose keyword arguments become a log line or an audit record.
LOGGING_CALLS = ("emit", "build", "log", "record", "append")


def logged_document_text(trees=None) -> list[str]:
    """Any logging call passing a keyword named after a document's own text.

    `gateway/logs.build` raises on these at runtime, which protects a path that executes. This
    finds the call before it runs, including on a branch no test reaches.
    """
    from gateway.logs import DENIED_FIELDS

    out = []
    for rel, tree in (trees if trees is not None else _modules()):
        if rel in ("gateway/logs.py", "scripts/hardening.py"):
            continue            # the denylist itself, and this sweep's own fixtures
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or _call_name(n) not in LOGGING_CALLS:
                continue
            for kw in n.keywords:
                if kw.arg in DENIED_FIELDS:
                    out.append(f"{rel}:{n.lineno} passes {kw.arg}=")
    return out


def _fixture(src: str):
    """One synthetic module, so a sweep can be run against a known violation."""
    return [("<probe>", ast.parse(src))]


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

    print("hardening")

    # ── every outbound call carries a timeout, with NO exception list ───────
    total = outbound_count()
    check(total > 15, f"the sweep walked real outbound calls ({total} urlopen calls)")
    untimed = untimed_outbound()
    check(not untimed,
          f"EVERY urlopen in the repository carries a timeout -- a socket with none waits "
          f"forever ({untimed})")

    # The sweep must be able to find one, or the clean result above is a scanner with a typo.
    found = untimed_outbound(_fixture(
        "import urllib.request\n"
        "def f():\n"
        "    return urllib.request.urlopen('https://example.gov.in/x')\n"))
    check(len(found) == 1,
          f"...and the sweep DETECTS a synthetic untimed call, so the clean result is "
          f"evidence rather than a broken matcher ({found})")
    check(not untimed_outbound(_fixture(
              "import urllib.request\n"
              "def f():\n"
              "    return urllib.request.urlopen('https://x', timeout=30)\n")),
          "...and does not flag one that has a timeout, so it is not merely refusing "
          "everything")

    # ── no logging call passes a document's own text ────────────────────────
    leaks = logged_document_text()
    check(not leaks,
          f"NO logging or audit call passes a field named after a document's text ({leaks})")
    found = logged_document_text(_fixture(
        "from gateway.logs import emit\n"
        "def f(doc):\n"
        "    emit('verb.call', reading_text=doc.reading_text)\n"))
    check(len(found) == 1 and "reading_text" in found[0],
          f"...and the sweep detects one, including on a branch no test reaches ({found})")
    check(not logged_document_text(_fixture(
              "from gateway.logs import emit\n"
              "def f(doc):\n"
              "    emit('verb.call', document_id=doc.id, chars=len(doc.reading_text))\n")),
          "...while logging an id and a LENGTH is exactly what it asks for instead")

    # ── the two modules agree on what counts as document text ──────────────
    from gateway.logs import DENIED_FIELDS
    check(set(DOCUMENT_TEXT_FIELDS) <= DENIED_FIELDS,
          f"this module's field list is a SUBSET of gateway/logs.DENIED_FIELDS, so the sweep "
          f"cannot pass on names the runtime refuses "
          f"({sorted(set(DOCUMENT_TEXT_FIELDS) - DENIED_FIELDS)})")

    # ── the runtime guard and the sweep are both present ───────────────────
    from gateway.logs import DeniedLogField, build
    try:
        build("probe", text="a clause")
        check(False, "gateway/logs refuses a denied field at runtime")
    except DeniedLogField:
        check(True, "gateway/logs ALSO refuses at runtime, so a dynamically-built field that "
                    "this sweep cannot see is still caught")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps({"untimed_outbound": untimed_outbound(),
                          "outbound_calls": outbound_count(),
                          "logged_document_text": logged_document_text()}, indent=2))
        raise SystemExit(0)
    raise SystemExit(_test())
