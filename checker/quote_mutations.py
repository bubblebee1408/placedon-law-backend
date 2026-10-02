#!/usr/bin/env python3
"""Break a real statutory quote in six specific ways, so a verifier can be measured.

M1. A verifier that accepts everything passes every test written by someone who only feeds
it true things. These are the six ways a quote goes wrong in practice, each produced from
REAL held text so the measurement is about the checker and not about a fixture:

    negation          "shall not" <-> "shall"            -- reverses the duty
    number            a quantity changed                 -- "one third" -> "two thirds"
    date              a date changed                     -- a commencement that is not
    section_number    "s.173" -> "s.174"                 -- the right words, wrong provision
    shall_may         "shall" <-> "may"                  -- a duty becomes a discretion
    truncation        the last third removed             -- a proviso dropped

## Why these six

Each is a lie a model actually tells. Negation and number are the two that change what the
law REQUIRES while keeping every word a lexical check looks for -- which is why PLAN_23
and M1 both single them out, and why a false accept on either is a bug rather than a
number to report.

`shall_may` is the Indian drafting hazard specifically: the difference between a duty and
a power, invisible to a term-overlap check.

## A mutation that does not change the text is not a mutation

Every function returns None when it cannot apply -- no "not" to remove, no digits to
change. The harness counts those as NOT ATTEMPTED rather than as passes, because a
mutation that did nothing and was then "rejected" is a check that was never tested.

Run: PYTHONPATH=. python3 checker/quote_mutations.py --test
"""
from __future__ import annotations

import re

__all__ = ["MUTATIONS", "DANGEROUS", "mutate", "apply_all"]

# The two that change what the law requires while keeping the words a lexical check reads.
# M1: a false accept on either is a bug to fix, not a rate to report.
DANGEROUS = ("negation", "number")

_NUM_WORDS = {"one": "two", "two": "three", "three": "five", "four": "six",
              "five": "seven", "six": "nine", "seven": "ten", "nine": "eleven",
              "ten": "twelve", "fifteen": "twenty", "twenty": "thirty",
              "thirty": "sixty", "sixty": "ninety", "ninety": "thirty",
              "hundred": "thousand", "third": "fourth", "half": "quarter"}


def _negation(text: str) -> str | None:
    if re.search(r"\bshall not\b", text, re.I):
        return re.sub(r"\bshall not\b", "shall", text, count=1, flags=re.I)
    if re.search(r"\bnot\b", text, re.I):
        return re.sub(r"\bnot\b", "", text, count=1, flags=re.I)
    m = re.search(r"\bshall\b", text, re.I)
    if m:
        return text[:m.end()] + " not" + text[m.end():]
    return None


# A numeral that labels a provision is not a quantity, and mutating one produces a
# section_number mutation wearing a number's name. Measured 02-10-2026: before this filter,
# 8 of the 49 "number" false accepts were "(1)" -> "(2)" and cross-references like "34" ->
# "35" -- so the number rate was partly reporting the section_number rate, and the two
# classes have to be disjoint for either to mean anything. M1 lists them separately.
_STRUCTURAL = re.compile(
    r"\((?:\d+|[a-z]|[ivx]+)\)"                                    # (1) (a) (iv)
    r"|(?:section|sub-section|sub section|clause|chapter|rule|schedule|part|"
    r"article|form|act|order|regulation)s?\s*\(?\d+",              # section 34
    re.I)


def _quantity_spans(text: str):
    """Spans of `text` that a numeral may be drawn from: everything not a provision label."""
    out, at = [], 0
    for m in _STRUCTURAL.finditer(text):
        if m.start() > at:
            out.append((at, m.start()))
        at = m.end()
    if at < len(text):
        out.append((at, len(text)))
    return out


def _number(text: str) -> str | None:
    # Number WORDS first: in Indian statutory drafting these carry the legal quantity --
    # "two directors", "thirty days", "one-third of its total strength" -- while bare
    # digits are more often a label or a year.
    for lo, hi in _quantity_spans(text):
        chunk = text[lo:hi]
        for word, other in _NUM_WORDS.items():
            m = re.search(rf"\b{word}\b", chunk, re.I)
            if m:
                return text[:lo + m.start()] + other + text[lo + m.end():]
    for lo, hi in _quantity_spans(text):
        chunk = text[lo:hi]
        for m in re.finditer(r"\b\d+\b", chunk):
            if re.fullmatch(r"(19|20)\d{2}", m.group(0)):
                continue                    # a year is _date's mutation, not this one
            if chunk[m.end():m.end() + 1] == "[":
                continue                    # India Code's footnote marker: 1[substituted]
            return (text[:lo + m.start()] + str(int(m.group(0)) + 1)
                    + text[lo + m.end():])
    return None


def _date(text: str) -> str | None:
    m = re.search(r"\b(\d{1,2})(st|nd|rd|th)?\s+(day of\s+)?"
                  r"(January|February|March|April|May|June|July|August|September|"
                  r"October|November|December),?\s*(\d{4})\b", text, re.I)
    if m:
        return text[:m.start(5)] + str(int(m.group(5)) + 1) + text[m.end(5):]
    m = re.search(r"\b(19|20)\d{2}\b", text)
    if m:
        return text[:m.start()] + str(int(m.group(0)) + 1) + text[m.end():]
    return None


def _section_number(text: str) -> str | None:
    m = re.search(r"\b(section|s\.)\s*(\d+)\b", text, re.I)
    if m:
        return text[:m.start(2)] + str(int(m.group(2)) + 1) + text[m.end(2):]
    return None


def _shall_may(text: str) -> str | None:
    if re.search(r"\bshall\b", text, re.I):
        return re.sub(r"\bshall\b", "may", text, count=1, flags=re.I)
    if re.search(r"\bmay\b", text, re.I):
        return re.sub(r"\bmay\b", "shall", text, count=1, flags=re.I)
    return None


def _truncation(text: str) -> str | None:
    words = text.split()
    if len(words) < 8:
        return None            # too short to lose a third and still be a quote
    keep = int(len(words) * 2 / 3)
    out = " ".join(words[:keep])
    return out if out != text else None


MUTATIONS = {
    "negation": _negation,
    "number": _number,
    "date": _date,
    "section_number": _section_number,
    "shall_may": _shall_may,
    "truncation": _truncation,
}


def mutate(text: str, kind: str) -> str | None:
    """The mutated text, or None when this mutation cannot apply to this quote."""
    if kind not in MUTATIONS:
        raise KeyError(f"{kind!r} is not a mutation; one of {sorted(MUTATIONS)}")
    out = MUTATIONS[kind](str(text or ""))
    if out is None or out.strip() == str(text or "").strip():
        # A mutation that changed nothing is NOT a mutation. Returning the original would
        # make the verifier "correctly accept" it and count as a pass.
        return None
    return out


def apply_all(text: str) -> dict:
    """{kind: mutated text or None}. None means NOT ATTEMPTED, never 'passed'."""
    return {kind: mutate(text, kind) for kind in MUTATIONS}


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

    print("quote_mutations")

    QUORUM = ("The quorum for a meeting of the Board of Directors of a company shall be "
              "one third of its total strength or two directors, whichever is higher.")

    check(mutate(QUORUM, "negation") == QUORUM.replace("shall be", "shall not be"),
          "negation inserts 'not' after 'shall' when there is none to remove")
    check(mutate("A director shall not vote on a contract in which he is interested.",
                 "negation") == "A director shall vote on a contract in which he is "
                                "interested.",
          "...and removes 'shall not' where there is one, which is the commoner lie")

    out = mutate(QUORUM, "number")
    check(out == QUORUM.replace("one third", "two third"),
          f"number changes a QUANTITY -- here the fraction, the first one in the "
          f"sentence ({out!r})")

    # The classes have to be disjoint or neither rate means anything. Measured 02-10-2026:
    # 8 of 49 "number" false accepts were "(1)" -> "(2)" and cross-references, which is
    # the section_number class wearing a number's name. M1 lists them separately.
    # Each case pairs the structural token that must SURVIVE with the sentence it sits
    # in. Asserting survival is stronger than asserting the output is unchanged: the
    # first case must still be free to mutate "four", which is a real quantity.
    for label, keep, text in (
            ("a subsection marker", "(1)", "(1) The Board shall meet four times."),
            ("a cross-reference", "section 173", "Nothing in section 173 shall apply."),
            ("a footnote marker", "1[", "The 1[substituted words] shall apply here."),
            ("a year", "2014", "Commenced on the 1st day of April, 2014 in full.")):
        out = mutate(text, "number")
        check(out is None or keep in out,
              f"number does NOT mutate {label} -- {keep!r} survives, because that is "
              f"section_number's or date's class, not this one's ({out!r})")

    check(mutate(QUORUM, "shall_may") == QUORUM.replace("shall be", "may be"),
          "shall_may turns the duty into a power")

    # ── a mutation that changes nothing is NOT a mutation ──────────────────
    check(mutate("No digits or quantities appear in this sentence at all here.",
                 "number") is None,
          "a quote with no quantity returns None -- NOT ATTEMPTED, never a pass")
    check(mutate("A plain sentence with no date in it whatsoever here.", "date") is None,
          "...and so does one with no date")
    for kind in MUTATIONS:
        out = mutate(QUORUM, kind)
        check(out is None or out.strip() != QUORUM.strip(),
              f"{kind}: the result is either None or genuinely different -- a mutation "
              f"that changed nothing and was then rejected is a check never tested")

    check(set(apply_all(QUORUM)) == set(MUTATIONS),
          "apply_all reports every kind, including the ones that did not apply")
    check(apply_all("x")["negation"] is None,
          "...and reports them as None rather than omitting them, so a caller cannot "
          "mistake 'not attempted' for 'passed'")

    try:
        mutate(QUORUM, "nonsense")
        check(False, "an unknown mutation kind raises")
    except KeyError as e:
        check("nonsense" in str(e) and "negation" in str(e),
              "an unknown mutation kind raises and names the valid ones")

    check(DANGEROUS == ("negation", "number") and all(k in MUTATIONS for k in DANGEROUS),
          "the two M1 calls bugs rather than rates are real mutation kinds")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv else _test())
