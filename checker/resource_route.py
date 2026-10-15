#!/usr/bin/env python3
"""A conservative, DETERMINISTIC resource router: STATUTE vs CASE vs UNSURE.

`conversation.send` and the `ask` verb answer a research question from the held Companies
Act corpus only (`checker/retrieve.py`'s lexical match). That corpus has nothing to say
about "find the Tata Sons Cyrus Mistry case" -- it is not a statutory question -- so `ask`
reads nothing and abstains with "no provision on point", even though a judgment-discovery
index already exists (`checker/sources/judgment_index.py`, 8,977 judgments) and could have
answered.

This module decides, from the QUERY TEXT ALONE and with NO MODEL CALL, which RESOURCE a
research question should be read against:

    STATUTE   the question names a provision/section, or nothing case-shaped was found --
              the existing held-corpus path, unchanged.
    CASE      the question names parties, a citation, or 'vs'/'v.'/'versus', and (for the
              weaker signals -- 'case'/'judgment' alone) is corroborated by a named party or
              a year, so routing it to judgment discovery is worth the detour.
    UNSURE    a case-shaped word appears but routing would be a guess (no party, no year, or
              a statute citation sits next to a case signal). Treated exactly like STATUTE
              by every caller: the existing held-corpus path runs, unchanged.

This is NOT the model router (`checker/router.py` picks which model phrases an answer --
this module never touches that decision). This picks which RESOURCE (statute corpus, or
judgment index) a query is read against, before any model is involved.

## Why 'judgment' and 'case' are WEAK, not strong, signals

Both words have real statutory lives. The Companies Act 2013 itself uses "independent
judgment" (s.166(2), a director's duty), and legal drafting is full of "in case of", "in
such a case", "as the case may be". Treating either word as sufficient on its own would
misroute exactly the statute questions this module exists to leave alone. So each is
promoted to CASE only when corroborated by something a statute question does not carry: a
named party (a Title Case word beyond the sentence's own first word) or an explicit year --
reusing `checker/sources/judgment_index.py`'s own tokenizer and year pattern, the same
signal `discover()` itself would act on, rather than inventing a second idea of what a year
token is.

## Why an explicit provision citation always wins

"Does s.241 cover oppression and mismanagement cases?" names a section and uses the word
"cases" generically ("instances"), not as a request to find one. An explicit citation is
the strongest statute signal there is, so it is checked FIRST and forces STATUTE -- unless a
genuinely strong case signal (a 'vs'/'v.'/'versus' pattern, or a formal case citation like
"AIR 1973" / "(2021) 3 SCC 1") sits next to it, in which case the question is naming BOTH a
case and a provision and this module says so honestly: UNSURE, never a silent guess either
way.

Run: PYTHONPATH=. python3 checker/resource_route.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.sources.judgment_index import _tokens as _jtokens
from checker.sources.judgment_index import _YEAR as _JYEAR

STATUTE = "STATUTE"
CASE = "CASE"
UNSURE = "UNSURE"
RESOURCES = (STATUTE, CASE, UNSURE)


@dataclass(frozen=True)
class Decision:
    """One routing decision. `rule` is which branch fired (for tests and the run trace, the
    same job `agents/intake.Classification.rule` does); `reason` is a sentence."""
    resource: str
    rule: str
    reason: str

    def __post_init__(self) -> None:
        if self.resource not in RESOURCES:
            raise ValueError(f"{self.resource!r} is not one of {RESOURCES}")
        if not self.reason.strip():
            raise ValueError(f"{self.rule}: a decision with no reason is not one")


# An explicit provision/section citation. A heuristic, not the full grammar
# `checker/ask_read.not_one_citation` enforces on a structured field -- this reads free text
# and only ever needs to say "a citation-shaped token is present", which is enough to force
# STATUTE (the safe direction) even where the heuristic is slightly over-eager.
_SECTION_RE = re.compile(
    r"\b(?:s\.?\s?\d+[a-z]?(?:\(\d+\))?|sec(?:tion)?\.?\s+\d+|u/s\.?\s*\d+|"
    r"rule\s+\d+(?:\(\d+\))?|§\s?\d+)",
    re.IGNORECASE)

# A 'versus' pattern or a formal case citation. Either alone is enough: neither has a
# statutory life the way 'case'/'judgment' do.
_VS_RE = re.compile(r"\bvs\.?\b|\bversus\b|\bv\.", re.IGNORECASE)
_CITATION_RE = re.compile(r"\bair\s+\d{4}\b|\(\s*\d{4}\s*\)\s*\d*\s*scc\b", re.IGNORECASE)

# Idioms that use 'case' with no case in mind. Stripped before the word is looked for, so
# "in case of a casual vacancy" never reads as a request to find one.
_IDIOMS = ("in case of", "in such a case", "in such case", "in any case", "in which case",
           "as the case may be", "case may be", "in each case", "in that case")
_IDIOM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in sorted(_IDIOMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)

# Weak on their own (see module docstring): each has a genuine statutory use.
_WEAK_RE = re.compile(r"\b(?:case|cases|judgment|judgement|judgments|judgements)\b",
                      re.IGNORECASE)

# A named party, as a Title Case word -- NOT the sentence's own first word, whose capital is
# just English grammar ("What", "Find", "Does"). Read from the ORIGINAL text, before any
# lower-casing, which is why this module keeps the raw query around rather than folding it
# once at the top the way the other patterns do.
_TITLECASE_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")


def _strip_idioms(text: str) -> str:
    return _IDIOM_RE.sub(" ", text)


def _has_named_entity(text: str) -> bool:
    """A Title Case word anywhere but the sentence's own first word."""
    words = text.split()
    if len(words) < 2:
        return False
    return bool(_TITLECASE_RE.search(" ".join(words[1:])))


def _has_year(text: str) -> bool:
    """A four-digit year token, by judgment_index's own rule for what counts as one --
    reused rather than re-decided here, so the two never disagree about a year."""
    return any(_JYEAR.match(t) for t in _jtokens(text))


def classify(query: str) -> Decision:
    """STATUTE, CASE or UNSURE, from the text alone. No model call, ever.

    Callers: route CASE to judgment discovery; treat STATUTE and UNSURE identically -- both
    mean "run the existing held-corpus path, unchanged".
    """
    text = (query or "").strip()
    if not text:
        return Decision(STATUTE, "empty", "an empty query has nothing case-shaped to find; "
                        "the existing path's own BAD_REQUEST handles it")

    section = bool(_SECTION_RE.search(text))
    strong = bool(_VS_RE.search(text) or _CITATION_RE.search(text))
    weak = bool(_WEAK_RE.search(_strip_idioms(text)))

    if section:
        if strong:
            return Decision(UNSURE, "section+strong_case_signal",
                            "the question names a provision AND a 'vs'/'v.'/'versus' "
                            "pattern or a formal case citation -- it may be about a "
                            "judgment's reading of a section, which is neither a plain "
                            "statute question nor a plain case lookup")
        return Decision(STATUTE, "section_cited",
                        "the question names a provision; an explicit citation is the "
                        "strongest statute signal there is and is never overridden by "
                        "'case'/'judgment' alone, each of which the Companies Act itself "
                        "also uses")

    if strong:
        return Decision(CASE, "vs_or_citation",
                        "a 'vs'/'v.'/'versus' pattern or a formal case citation (e.g. "
                        "'AIR 1973', '(2021) 3 SCC 1') names a case directly")

    if weak:
        if _has_named_entity(text) or _has_year(text):
            return Decision(CASE, "case_word+named_party_or_year",
                            "'case'/'judgment' is corroborated by a named party or a year, "
                            "so this reads as a request to find a specific judgment rather "
                            "than the word's ordinary statutory use ('in case of', "
                            "'independent judgment')")
        return Decision(UNSURE, "case_word_uncorroborated",
                        "'case'/'judgment' appears with no named party and no year to "
                        "search by -- routing to judgment discovery would be a guess, and "
                        "discovery is metadata-only (party/title/year), so it would find "
                        "nothing to justify the detour anyway")

    return Decision(STATUTE, "no_case_signal",
                    "no provision citation, case-vs pattern, formal case citation, or "
                    "'case'/'judgment' word was found")


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("resource_route")

    # ── the worked example: CASE, by the weak word + named parties ──────────
    for q in ("find the Tata Sons Cyrus Mistry case", "find the Tata-Mistry case",
              "Find the Tata Sons Cyrus Mistry Case"):
        d = classify(q)
        check(d.resource == CASE, f"{q!r} -> CASE (got {d.resource}/{d.rule})")

    # ── a 'vs'/'v.' pattern is CASE on its own, no 'case' word needed ───────
    d = classify("Tata Sons Pvt Ltd v. Cyrus Investments Pvt Ltd")
    check(d.resource == CASE and d.rule == "vs_or_citation",
          f"a 'v.' pattern is CASE without the word 'case' (got {d.resource}/{d.rule})")
    d = classify("the Tata vs Mistry dispute")
    check(d.resource == CASE, f"bare 'vs' is CASE (got {d.resource})")

    # ── a formal case citation is CASE on its own ───────────────────────────
    d = classify("What was held in (2021) 3 SCC 1?")
    check(d.resource == CASE and d.rule == "vs_or_citation",
          f"an SCC citation is CASE (got {d.resource}/{d.rule})")
    d = classify("Discuss AIR 1973 SC 1461.")
    check(d.resource == CASE, f"an AIR citation is CASE (got {d.resource})")

    # ── plain statute questions are untouched: STATUTE, no case signal ──────
    for q in ("What is the quorum for a meeting of the Board?",
              "Must independent directors form part of the audit committee?",
              "Can the NCLT wind up the company on just and equitable grounds?",
              "What are our annual filings under the Companies Act, 2013?",
              "Does a further issue of capital need a special resolution under s.62?"):
        d = classify(q)
        check(d.resource == STATUTE,
              f"{q[:50]!r} -> STATUTE, unchanged (got {d.resource}/{d.rule})")

    # ── 'case' used as an idiom, with no party, is STATUTE -- not routed ────
    for q in ("In case of a casual vacancy, who presides at the meeting?",
              "What happens in such a case?", "As the case may be, is this exempt?",
              "In any case, what is the quorum?"):
        d = classify(q)
        check(d.resource == STATUTE,
              f"{q!r} is an idiom, not a case lookup (got {d.resource}/{d.rule})")

    # ── 'judgment' is weak: the Companies Act itself uses it (s.166(2)) ──────
    d = classify("What does exercising independent judgment mean for a director?")
    check(d.resource == UNSURE,
          f"'independent judgment' with no named party is UNSURE, not CASE "
          f"(got {d.resource}/{d.rule})")

    # ── a 'case'/'judgment' word with no party and no year is UNSURE, not CASE ─
    for q in ("What case law exists on related party transactions?",
              "Is there a recent judgment on this?"):
        d = classify(q)
        check(d.resource == UNSURE,
              f"{q!r}: a bare case word with nothing to search by is UNSURE "
              f"(got {d.resource}/{d.rule})")

    # ── a year corroborates a case word even with no named party ────────────
    d = classify("find a 2026 data protection case")
    check(d.resource == CASE, f"a year corroborates 'case' (got {d.resource}/{d.rule})")

    # ── an explicit section citation always wins over a bare case word ──────
    d = classify("Does s.241 cover oppression and mismanagement cases?")
    check(d.resource == STATUTE and d.rule == "section_cited",
          f"a section cite beats a bare 'cases' (got {d.resource}/{d.rule})")
    for q in ("Under section 7, can a financial creditor file for insolvency?",
              "What does rule 3(1) prescribe?"):
        d = classify(q)
        check(d.resource == STATUTE, f"{q!r} is STATUTE (got {d.resource})")

    # ── a section cite NEXT TO a strong case signal is UNSURE, not a guess ──
    d = classify("What does the Tata Sons v. Cyrus Mistry judgment say about s.242?")
    check(d.resource == UNSURE and d.rule == "section+strong_case_signal",
          f"a section cite beside a 'v.' pattern is UNSURE, never a silent guess "
          f"(got {d.resource}/{d.rule})")

    # ── never raises on ragged input ─────────────────────────────────────────
    for q in ("", "   ", "?", "vs", "s.", "a" * 500):
        d = classify(q)
        check(d.resource in RESOURCES, f"{q[:20]!r} classifies without raising ({d.resource})")

    # ── the record refuses to be built wrong ─────────────────────────────────
    try:
        Decision("CASELAW", "x", "y")
        check(False, "a resource outside the closed set is refused")
    except ValueError:
        check(True, "a resource outside the closed set is refused")
    try:
        Decision(CASE, "x", "")
        check(False, "a decision with no reason is refused")
    except ValueError:
        check(True, "a decision with no reason is refused")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
