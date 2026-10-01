#!/usr/bin/env python3
"""Why a run did not answer, in one of seven words.

PLAN_23 O8. Without this, "it did not work" is one undifferentiated pile, and the two
questions that matter cannot be asked: *is retrieval the problem, or the verifier?* and
*are we losing more runs this week than last?* Those have different fixes, and a single
failure count hides which one is needed.

## The seven, and the eighth that stops them lying

    retrieval_miss    nothing on point was found to answer from
    verifier_reject   something was proposed and the verifier refused it
    scope_refusal     the question reaches a body of law this engine does not hold
    transport         the attempt broke -- a socket, a 500, a crash
    model_refusal     no model could be served, or the one served declined
    timeout           the step did not return in time
    budget            the spend cap stopped it

**UNCATEGORISED is the eighth**, and it exists so the other seven stay true. A run that
matches none of them is recorded as uncategorised WITH THE REASON, never pushed into
`transport` because that is the nearest-looking box. A category assigned by elimination is
a category that will be counted, charted, and acted on as though it had been observed.

`scope_refusal` is NOT a failure of this system -- it is the product working, refusing by
name rather than answering about law it does not hold. It is counted because the trend
matters (it says what to acquire next), and `is_fault()` is what separates it from the
rest so a weekly report does not read as six kinds of broken.

A CANCELLED run is likewise not a failure: a person stopped it. It comes back
uncategorised with that said, rather than being forced into one of the seven.

Run: PYTHONPATH=. python3 checker/failure_tags.py --test
"""
from __future__ import annotations

__all__ = ["CATEGORIES", "FAULTS", "RETRIEVAL_MISS", "VERIFIER_REJECT", "SCOPE_REFUSAL",
           "TRANSPORT", "MODEL_REFUSAL", "TIMEOUT", "BUDGET", "UNCATEGORISED",
           "classify", "is_fault", "TagError"]

RETRIEVAL_MISS = "retrieval_miss"
VERIFIER_REJECT = "verifier_reject"
SCOPE_REFUSAL = "scope_refusal"
TRANSPORT = "transport"
MODEL_REFUSAL = "model_refusal"
TIMEOUT = "timeout"
BUDGET = "budget"
UNCATEGORISED = "uncategorised"

CATEGORIES = (RETRIEVAL_MISS, VERIFIER_REJECT, SCOPE_REFUSAL, TRANSPORT, MODEL_REFUSAL,
              TIMEOUT, BUDGET, UNCATEGORISED)

# The ones that mean something is wrong with US. A scope refusal is the product working,
# and an uncategorised run is a gap in this file, not in the engine.
FAULTS = (RETRIEVAL_MISS, VERIFIER_REJECT, TRANSPORT, MODEL_REFUSAL, TIMEOUT, BUDGET)


class TagError(ValueError):
    """A run that cannot be classified at all. Never a silent default."""


# Refusal codes this gateway really emits, mapped to the category each means. Written out
# rather than pattern-matched on substrings: `NO_MODEL` and `NO_STORE` share a prefix and
# mean entirely different things, and a prefix rule would have found that out in
# production.
_BY_CODE = {
    "NO_BUDGET": BUDGET,
    "NO_MODEL": MODEL_REFUSAL,
    "MODEL_REFUSED": MODEL_REFUSAL,
    "REGION_UNCONFIRMED": MODEL_REFUSAL,
    "NOT_HELD": SCOPE_REFUSAL,
    "OUT_OF_SCOPE": SCOPE_REFUSAL,
    "AS_OF_UNSUPPORTED": SCOPE_REFUSAL,
    "TIMEOUT": TIMEOUT,
    "STEP_TIMEOUT": TIMEOUT,
}

_TIMEOUT_WORDS = ("timeout", "timed out", "did not return within", "deadline")
_TRANSPORT_WORDS = ("connection", "socket", "502", "503", "504", "reset by peer",
                    "temporarily unavailable")


def _text(run: dict) -> str:
    result = run.get("result")
    bits = [str(run.get("refusal_code") or "")]
    if isinstance(result, dict):
        bits += [str(result.get("error") or ""), str(result.get("detail") or ""),
                 str(result.get("code") or "")]
    return " ".join(bits).lower()


def classify(run: dict) -> tuple[str, str]:
    """(category, why). Raises only when handed something that is not a run.

    Order matters and is deliberate: a run that both timed out and had no model is a
    TIMEOUT, because the timeout is what a reader can act on and "no model" was a
    consequence of it.
    """
    if not isinstance(run, dict):
        raise TagError(f"a run record is required, got {type(run).__name__}")
    status = str(run.get("status") or "").upper()
    if status == "ANSWERED":
        raise TagError("an ANSWERED run has no failure to categorise; ask is_fault() "
                       "about a category, never classify() about a success")
    code = str(run.get("refusal_code") or "").upper()
    blob = _text(run)

    if status == "CANCELLED" or code == "CANCELLED":
        return UNCATEGORISED, ("a person cancelled this run. It is not a failure, and it "
                               "is not pushed into one of the seven to make the tally "
                               "tidy")
    for word in _TIMEOUT_WORDS:
        if word in blob:
            return TIMEOUT, f"the record says {word!r}"
    if code in _BY_CODE:
        return _BY_CODE[code], f"refusal code {code}"
    if status == "FAILED":
        for word in _TRANSPORT_WORDS:
            if word in blob:
                return TRANSPORT, f"the error names {word!r}"
        return TRANSPORT, ("the run FAILED, which in this system means the attempt broke "
                           "rather than that an answer was declined")
    if status in ("NEEDS_LAWYER", "PARTIAL") or "verifier" in blob or "rejected" in blob:
        return VERIFIER_REJECT, (f"status {status or '?'}: something was proposed and not "
                                 f"admitted")
    if "no provision" in blob or "nothing on point" in blob or "no evidence" in blob:
        return RETRIEVAL_MISS, "the record says nothing on point was found"
    if "not held" in blob or "declared" in blob or "out of scope" in blob:
        return SCOPE_REFUSAL, "the record names a body of law this engine does not hold"
    return UNCATEGORISED, (
        f"status {status or '(none)'} with refusal code {code or '(none)'} matches none of "
        f"{list(CATEGORIES[:-1])}. Recorded as uncategorised rather than guessed: a "
        f"category assigned by elimination would be counted as though it had been observed")


def is_fault(category: str) -> bool:
    """Does this category mean something is wrong with US?

    A scope refusal is the product working as designed, and `uncategorised` is a gap in
    this file. Neither belongs in a count of what is broken.
    """
    return category in FAULTS


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

    print("failure_tags")

    def cat(**run):
        return classify(run)[0]

    # ── the seven the brief names ──────────────────────────────────────────
    check(set(CATEGORIES) - {UNCATEGORISED} == {
        "retrieval_miss", "verifier_reject", "scope_refusal", "transport",
        "model_refusal", "timeout", "budget"},
        f"the seven categories are exactly those PLAN_23 O8 names ({sorted(CATEGORIES)})")
    check(cat(status="REFUSED", refusal_code="NO_BUDGET") == BUDGET,
          "NO_BUDGET is budget")
    check(cat(status="REFUSED", refusal_code="NO_MODEL") == MODEL_REFUSAL,
          "NO_MODEL is model_refusal")
    check(cat(status="FAILED", result={"error": "ConnectionResetError: reset by peer"})
          == TRANSPORT, "a broken socket is transport")
    check(cat(status="FAILED", result={"error": "StepTimeout: research exceeded 30s"})
          == TIMEOUT, "a timeout is timeout, NOT transport")
    check(cat(status="REFUSED", refusal_code="AS_OF_UNSUPPORTED") == SCOPE_REFUSAL,
          "a past as_of is a scope refusal: the engine will not read the law as at a date "
          "it cannot reconstruct")
    check(cat(status="REFUSED", result={"detail": "FEMA is declared and not held"})
          == SCOPE_REFUSAL, "a body of law we do not hold is scope_refusal")
    check(cat(status="NEEDS_LAWYER") == VERIFIER_REJECT,
          "NEEDS_LAWYER is verifier_reject: something was proposed and not admitted")
    check(cat(status="REFUSED", result={"detail": "no provision on point was retrieved"})
          == RETRIEVAL_MISS, "nothing found is retrieval_miss")

    # ── ORDER: a timeout that also lost its model is a timeout ──────────────
    both = classify({"status": "FAILED", "refusal_code": "NO_MODEL",
                     "result": {"error": "the deployment timed out"}})
    check(both[0] == TIMEOUT,
          f"a run that BOTH timed out and had no model is a TIMEOUT: that is what a reader "
          f"can act on, and 'no model' was its consequence ({both[0]})")

    # ── the eighth, which keeps the other seven honest ─────────────────────
    u = classify({"status": "WEIRD", "refusal_code": "SOMETHING_NEW"})
    check(u[0] == UNCATEGORISED,
          "a status and code matching nothing is UNCATEGORISED, not the nearest-looking box")
    check("assigned by elimination" in u[1],
          "...and the reason says why guessing would be worse")
    check("SOMETHING_NEW" in u[1],
          f"...naming the code it did not recognise, so the mapping can be extended "
          f"({u[1][:60]!r})")
    c = classify({"status": "CANCELLED"})
    check(c[0] == UNCATEGORISED and "person cancelled" in c[1],
          "a CANCELLED run is not a failure and is not forced into one of the seven")

    # ── a scope refusal is the product WORKING ─────────────────────────────
    check(not is_fault(SCOPE_REFUSAL),
          "a scope refusal is NOT a fault: refusing by name is what this product does")
    check(not is_fault(UNCATEGORISED),
          "...and an uncategorised run is a gap in this file, not in the engine")
    for f in (RETRIEVAL_MISS, VERIFIER_REJECT, TRANSPORT, MODEL_REFUSAL, TIMEOUT, BUDGET):
        check(is_fault(f), f"{f} IS a fault")
    check(set(FAULTS) < set(CATEGORIES),
          "every fault is a category, and not every category is a fault")

    # ── never asked about a success ────────────────────────────────────────
    try:
        classify({"status": "ANSWERED"})
        check(False, "classifying an ANSWERED run raises")
    except TagError:
        check(True, "classifying an ANSWERED run RAISES: there is no failure to name, and "
                    "returning a category would put one in the tally")
    try:
        classify("not a run")
        check(False, "a non-run raises")
    except TagError:
        check(True, "a non-run raises rather than returning uncategorised")

    # Prefix matching would have broken this, which is why the map is explicit.
    check(cat(status="REFUSED", refusal_code="NO_STORE") != MODEL_REFUSAL,
          "NO_STORE is not NO_MODEL: they share a prefix and mean entirely different "
          "things, which is why the map is written out rather than matched on prefixes")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
