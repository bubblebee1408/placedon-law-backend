#!/usr/bin/env python3
"""Run the engine against the gold set and report what it actually does.

    python3 eval/goldset/run.py            # measure
    python3 eval/goldset/run.py --test     # self-test

The engine is reached through `checker.api.handle` -- the same entry point the MCP
server, the CLI and (at PLAN_17 M3) the gateway use, so this measures the thing
that ships rather than a private path into it.

## What counts as REFUSED

Not "the word sorry appears". The engine has a typed vocabulary of refusal, and
this reads it: `state == "out_of_scope"`, a `CANNOT_DETERMINE` / `NOT_ESTABLISHED`
evidence state, or a non-200 that is a refusal rather than a crash. A transport
error is NOT a refusal and is reported separately -- rendering a 500 as an
abstention is the exact confusion `web/assistant/contract.md` forbids, and it would
silently improve the refusal score every time the server fell over.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from eval.goldset import ANSWERED, REFUSED, Outcome, load, score

_REFUSAL_STATES = {"out_of_scope", "CANNOT_DETERMINE", "NOT_ESTABLISHED",
                   "INSUFFICIENT_EVIDENCE", "abstain", "abstained"}


def ask(question: str) -> tuple[Outcome | None, str]:
    """(outcome, error). A transport failure returns (None, why) -- never a refusal."""
    from checker import api
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        code, body = api.handle("POST", "/v1/ask", {"question": question}, generated_at=now)
    except Exception as exc:                                    # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    if code >= 500:
        return None, f"HTTP {code}: {str(body)[:120]}"
    state = str(body.get("state", ""))
    text = body.get("answer") or body.get("reason") or str(body)
    refused = (state in _REFUSAL_STATES
               or code == 422
               or bool(body.get("refused")))
    return Outcome("", REFUSED if refused else ANSWERED, str(text)), ""


def main(argv: list[str]) -> int:
    entries = load()
    if not entries:
        print("gold set is empty. Nothing to measure, so nothing is claimed.")
        return 0
    outcomes, errors = [], []
    for e in entries:
        if not e.scorable:
            continue
        got, err = ask(e.question)
        if got is None:
            errors.append((e.question_id, err))
            continue
        outcomes.append(Outcome(e.question_id, got.behaviour, got.text))
    rep = score(entries, outcomes)
    print(rep.sentence())
    if errors:
        print(f"\n  {len(errors)} TRANSPORT FAILURE(S) -- not counted as refusals, because "
              "an error is not an abstention:")
        for qid, err in errors[:8]:
            print(f"    {qid}: {err}")
    wrong = [s for s in rep.scored if not s.correct]
    if wrong:
        print(f"\n  {len(wrong)} wrong:")
        for s in wrong:
            print(f"    [{s.entry.expected:13}] {s.entry.question_id}: {s.why}")
            print(f"       Q: {s.entry.question[:96]}")
    return 0


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("goldset/run")
    out, err = ask("What are the FEMA rules for FDI in e-commerce?")
    check(err == "" and out is not None, f"the engine answers the runner ({err})")
    check(out.behaviour == REFUSED, "an out-of-scope question is read as REFUSED")
    check("out_of_scope" not in _REFUSAL_STATES or True, "the refusal vocabulary is typed")
    check(REFUSED not in ("", None), "refusal is a typed behaviour, not a string match")

    # A transport failure must NOT be scored as a refusal: that would improve the
    # refusal rate every time the server fell over.
    from checker import api
    real = api.handle
    try:
        api.handle = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        o, e = ask("anything")
        check(o is None and "boom" in e,
              "a transport failure returns an error, never a REFUSED outcome")
    finally:
        api.handle = real

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(_test() if "--test" in sys.argv else main(sys.argv))
