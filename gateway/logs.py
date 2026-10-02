#!/usr/bin/env python3
"""One JSON object per operational event, and document text cannot get into it.

P2. `gateway/audit.py` is the hash-chained record of what a person did, and its own docstring
already says metadata only. This is the other log: the operational one, a JSON line per
request, for reading latency and failures in production. It is separate because the two have
different rules -- an audit record must never change, and a log line must never be the reason
a client's contract is sitting in a log file on a server.

## Why a denylist of FIELD NAMES, and why that alone is not enough

A field called `text` or `reading_text` is a document's own words, so those names are refused
outright: `DENIED_FIELDS` below. But the leak this is really guarding against does not announce
itself with a helpful name. Someone logs `detail=str(exc)` and the exception message contains
the clause it failed to parse, and now a paragraph of a client's NDA is in the log.

So there are two rules, and the second is the one that catches the real case:

  * a DENIED name is refused -- the value never reaches the line
  * any string over `MAX_VALUE_CHARS` is WITHHELD, whatever it is called

## Withheld, never truncated

A truncated value looks like a value. The first 200 characters of a contract clause are still
a contract clause, and a reader of the log cannot tell that more was cut. So an over-long
value is replaced by a marker naming the field, its length, and why it was withheld -- which
is also what tells whoever added the field that they are logging the wrong thing.

## It raises rather than dropping, when the name is denied

A denied FIELD NAME is a programming mistake, not a runtime condition: nobody means to log
`reading_text`. Dropping it silently would leave the author believing it was recorded. An
over-long value under an innocent name is the opposite -- that happens legitimately, at
runtime, to a `detail` that is usually short -- so that one is withheld and the line is still
emitted.

Run: PYTHONPATH=. python3 gateway/logs.py --test
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, TextIO

# Names that ARE a document's own text. Shared with scripts/hardening.py, which sweeps the
# repository for a call that passes one of these to a logging function.
DENIED_FIELDS = frozenset({
    "text", "raw_text", "reading_text", "content", "body", "quote", "page_text",
    "extracted_text", "document_text", "chunk", "clause_text", "prompt", "completion",
})

# Long enough for an id, a path, a verb name, a refusal code or a short reason. Short enough
# that a clause, a paragraph or a stack trace does not fit.
MAX_VALUE_CHARS = 300

WITHHELD = "WITHHELD"


class DeniedLogField(ValueError):
    """A field whose NAME is a document's text was passed to the log. Never dropped quietly."""


def _scrub(key: str, value: Any) -> Any:
    """The value as it may be logged, or a marker saying what was withheld and why."""
    if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
        return (f"<{WITHHELD}: {key} is {len(value)} chars, over the {MAX_VALUE_CHARS}-char "
                f"limit. Not truncated -- the first {MAX_VALUE_CHARS} characters of a clause "
                f"are still a clause>")
    if isinstance(value, dict):
        return {k: _scrub(f"{key}.{k}", v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(f"{key}[]", v) for v in value]
    return value


def build(event: str, **fields: Any) -> dict:
    """The log object. Raises on a denied field name; withholds an over-long value."""
    denied = sorted(k for k in fields if k in DENIED_FIELDS)
    if denied:
        raise DeniedLogField(
            f"{event}: {denied} name a document's own text and may not be logged. Log an id, "
            f"a length or a sha256 instead. gateway/audit.py has the same rule for the same "
            f"reason: a log line must never be why a client's contract is on a server's disk")
    return {"event": event, **{k: _scrub(k, v) for k, v in fields.items()}}


def emit(event: str, *, stream: TextIO | None = None, **fields: Any) -> dict:
    """Write one JSON line and return what was written."""
    row = build(event, **fields)
    out = stream if stream is not None else sys.stdout
    out.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    return row


def _test() -> int:
    import io
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("logs")

    CLAUSE = ("Each party shall keep the other's Confidential Information secret and shall "
              "not disclose it to any third party without prior written consent, " * 4)

    # ── the ordinary line ──────────────────────────────────────────────────
    row = build("verb.call", verb="conversation.send", tenant="firm-a", ms=42, status="OK")
    check(row["event"] == "verb.call" and row["ms"] == 42,
          "an ordinary line carries its fields unchanged")
    check(json.loads(json.dumps(row)) == row, "...and is JSON-serialisable")

    out = io.StringIO()
    emit("verb.call", stream=out, verb="x", ms=1)
    check(out.getvalue().endswith("\n") and len(out.getvalue().splitlines()) == 1,
          "emit writes exactly ONE line, so a log file stays line-delimited JSON")
    check(json.loads(out.getvalue())["verb"] == "x", "...and that line parses")

    # ── a denied NAME raises, and is not dropped ───────────────────────────
    for field in ("text", "reading_text", "quote", "prompt", "clause_text"):
        try:
            build("verb.call", **{field: CLAUSE})
            check(False, f"{field!r} is refused")
        except DeniedLogField as e:
            check(field in str(e) and "sha256" in str(e),
                  f"{field!r} RAISES and says what to log instead -- dropping it silently "
                  f"would leave the author believing it was recorded")

    check(len(DENIED_FIELDS) >= 10,
          f"the denied set covers the names a document's text actually arrives under "
          f"({len(DENIED_FIELDS)})")

    # ── and the case a denylist alone would miss ────────────────────────────
    # Nobody logs `reading_text` by accident. What happens is `detail=str(exc)` where the
    # exception carried the clause it could not parse.
    row = build("verb.call", detail=CLAUSE)
    check(WITHHELD in row["detail"] and CLAUSE[:50] not in row["detail"],
          "an over-long value under an INNOCENT name is withheld -- this is the leak a name "
          "denylist alone does not catch")
    check(str(len(CLAUSE)) in row["detail"] and "detail" in row["detail"],
          "...and the marker names the field and its length, which is what tells the author "
          "they are logging the wrong thing")
    check("truncated" not in row["detail"].lower()
          or "Not truncated" in row["detail"],
          "...and says it was NOT truncated: the first 300 characters of a clause are still "
          "a clause, and a truncated value looks like a value")

    # It is WITHHELD, not refused: an over-long `detail` happens legitimately at runtime, so
    # the line must still be emitted rather than the request failing on a log call.
    out = io.StringIO()
    emit("verb.call", stream=out, detail=CLAUSE)
    check(json.loads(out.getvalue())["event"] == "verb.call",
          "...and the line is still EMITTED, because a long detail is a runtime condition "
          "and not a programming mistake")

    # ── nesting, because document text arrives inside a dict ───────────────
    row = build("verb.call", result={"status": "OK", "detail": CLAUSE})
    check(WITHHELD in row["result"]["detail"],
          "an over-long value NESTED in a dict is withheld too")
    check(row["result"]["status"] == "OK", "...and its siblings are untouched")
    row = build("verb.call", items=[{"detail": CLAUSE}, {"detail": "short"}])
    check(WITHHELD in row["items"][0]["detail"] and row["items"][1]["detail"] == "short",
          "...and inside a list, element by element")
    check("result.detail" in build("v", result={"detail": CLAUSE})["result"]["detail"],
          "...with the marker naming the PATH, so a nested leak is findable")

    # ── short values are left completely alone ─────────────────────────────
    row = build("verb.call", code="NOT_FOUND", ms=0, ok=False, ratio=0.5, nothing=None)
    check(row["code"] == "NOT_FOUND" and row["ms"] == 0 and row["ok"] is False
          and row["ratio"] == 0.5 and row["nothing"] is None,
          "short strings, zero, False and None pass through unchanged -- a falsy value is "
          "not a missing one")
    check(len(build("v", x="a" * MAX_VALUE_CHARS)["x"]) == MAX_VALUE_CHARS,
          f"a value exactly at the {MAX_VALUE_CHARS}-char limit is kept, not withheld")
    check(WITHHELD in build("v", x="a" * (MAX_VALUE_CHARS + 1))["x"],
          "...and one character over is withheld, so the boundary is where it says it is")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test() if "--test" in sys.argv else _test())
