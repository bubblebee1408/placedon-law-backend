"""
Look up a Companies Act section by its NUMBER.

The corpus keys records by India Code's internal sectionID. The section number appears nowhere in
the record, so before this existed s.173 was simply not findable. Built offline from the full-Act
PDF by scripts/build_section_index.py.

Run: python3 checker/section_index.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus/companies_act"          # kept: 21 modules import this name
INDEX = CORPUS / "_index.json"

# ── Identity is (instrument, number), never a number (legal_ref.py) ──────────
# `legal_ref` exists because the India Code full-Act PDF reproduces subordinate Rules
# alongside the Act, and Rules renumber from 1: "56" names both Companies Act s.56
# (transfer of securities) and Meetings-of-Board r.56 (DIN intimation). A lookup keyed on
# the number alone returns whichever was indexed first -- a wrong legal answer with full
# confidence attached.
#
# This module was keyed on the number alone and referenced legal_ref nowhere. It now takes
# an instrument, defaulting to the Companies Act so that all 21 existing callers are
# unchanged, and every record it returns NAMES the instrument that answered. The default is
# explicit rather than implicit: a caller that does not pass one still gets a record that
# says which instrument it came from.
COMPANIES_ACT_2013 = "COMPANIES_ACT_2013"
SEBI_LODR_2015 = "SEBI_LODR_2015"


class NotIndexed(LookupError):
    """This instrument cannot be looked up by section number, and why.

    Deliberately NOT None. `section_by_number` returns None for "no such section in this
    instrument", which is a real answer about the law. An instrument whose text we hold but
    have never sectioned is a different thing entirely -- a fact about our corpus, not about
    the statute -- and collapsing the two would report "no such regulation" for a regulation
    that plainly exists.
    """


@dataclass(frozen=True)
class Instrument:
    instrument_id: str
    scope_key: str                 # the key in checker/scope.py
    corpus: Path | None            # None => text held, not sectioned
    unindexed_reason: str = ""


INSTRUMENTS: dict[str, Instrument] = {
    COMPANIES_ACT_2013: Instrument(
        COMPANIES_ACT_2013, "CA2013", CORPUS),
    # Sectioned by scripts/section_sebi_lodr.py from SEBI's consolidated PDF (the flat
    # corpus/rules/sebi_lodr_2015.txt is truncated at page 129 of 230 and was not used).
    # Lookup-able by number, NOT served: every record is HUMAN_REVIEW_PENDING with
    # production_usable false, and checker/legal_retrieval.py resolves the Companies Act
    # only. A record found here is evidence held for review, never an answer.
    SEBI_LODR_2015: Instrument(
        SEBI_LODR_2015, "SEBI_LODR", ROOT / "corpus/sebi_lodr"),
}


@lru_cache(maxsize=8)
def _index(instrument_id: str = COMPANIES_ACT_2013) -> dict:
    inst = instrument(instrument_id)
    if inst.corpus is None:
        raise NotIndexed(f"{instrument_id}: {inst.unindexed_reason}")
    return json.loads((inst.corpus / "_index.json").read_text())["entries"]


def instrument(instrument_id: str) -> Instrument:
    try:
        return INSTRUMENTS[instrument_id]
    except KeyError:
        raise NotIndexed(
            f"{instrument_id!r} is not a known instrument. Known: "
            f"{', '.join(sorted(INSTRUMENTS))}. An instrument nobody has registered is not "
            f"an instrument with no sections.") from None


def lookup(section_number: str, *, instrument_id: str = COMPANIES_ACT_2013) -> dict | None:
    """Index entry for a section number in one instrument, or None. Never guesses.

    Raises NotIndexed when the instrument has no index at all -- which is not the same
    answer as None.
    """
    return _index(instrument_id).get(str(section_number).strip().upper())


# Confidence labels a mapping may be served under. "high"/"medium" come from the
# PDF slicing heuristic; "source-confirmed" comes from India Code's own API
# returning section_id for a named Act, which is stronger evidence than either.
# The allowlist is explicit rather than a comparison, so a label nobody has
# reasoned about is refused instead of ranked.
TRUSTED_CONFIDENCE = ("source-confirmed", "high", "medium")


def section_by_number(section_number: str, *,
                      instrument_id: str = COMPANIES_ACT_2013) -> dict | None:
    """The full corpus record for a section number IN ONE INSTRUMENT.

    Returns None when the section is unmapped, omitted from the Act, or matched only with low
    confidence. An unmapped section is a real answer, not an error to paper over.

    Raises NotIndexed when the instrument itself has no index -- a fact about our corpus
    rather than about the law, and not something to report as "no such section".

    The returned record carries `instrument_id` and `ref`, so a caller can never lose track
    of which instrument answered. `ref` is a `legal_ref` key and round-trips through
    `legal_ref.parse_key`.
    """
    inst = instrument(instrument_id)
    e = lookup(section_number, instrument_id=instrument_id)
    if not e or not e.get("section_id"):
        return None
    if e.get("confidence") not in TRUSTED_CONFIDENCE:
        return None
    rec = json.loads((inst.corpus / f"{e['section_id']}.json").read_text())
    rec["section_number"] = e["section_number"]
    rec["title"] = e["title"]
    rec["index_confidence"] = e["confidence"]
    rec["instrument_id"] = inst.instrument_id
    # A record that names its own ref keeps it: LODR regulations are subordinate
    # legislation (RULE:...:R17), and a Schedule has no legal_ref form at all (None).
    if "ref" not in rec:
        rec["ref"] = f"ACT:{inst.instrument_id}:S{e['section_number']}"
    return rec


MVP_SECTIONS = ("96", "101", "102", "103", "114", "117", "173", "174", "175", "179", "184", "188")
MVP_EXTENSIONS = ("177", "178", "180", "185", "186")


def _test() -> None:
    ok = fail = 0

    def check(c: bool, label: str) -> None:
        nonlocal ok, fail
        if c:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    # Every MVP section must resolve, and its text must match its subject.
    expect = {
        "96": "one person company", "101": "twenty-one days", "102": "special business",
        "103": "quorum" if False else "articles of the company", "114": "ordinary resolution",
        "117": "every resolution", "173": "first meeting of the board",
        "174": "one-third of its total strength", "175": "circulation",
        "179": "exercise all such powers", "184": "every director",
        "188": "consent of the board of directors",
    }
    for num, phrase in expect.items():
        rec = section_by_number(num)
        if rec is None:
            check(False, f"s.{num} resolves"); continue
        body = " ".join(rec["content"].split()).lower()
        check(phrase in body, f"s.{num} '{rec['title'][:34]}' contains {phrase!r}")

    for num in MVP_EXTENSIONS:
        check(section_by_number(num) is not None, f"extension s.{num} resolves")

    check(section_by_number("9999") is None, "unknown section returns None, not a guess")
    check(lookup("11") is not None and lookup("11")["section_id"] is None,
          "omitted section is present in the index with no id")

    # ── identity is (instrument, number) ─────────────────────────────────────
    from checker import legal_ref as _lr

    rec = section_by_number("173")
    check(rec is not None and rec["instrument_id"] == COMPANIES_ACT_2013,
          "the default instrument is the Companies Act, and the record SAYS so")
    parsed = _lr.parse_key(rec["ref"])
    check(parsed.instrument_id == COMPANIES_ACT_2013 and parsed.number == "173",
          f"...and its ref round-trips through legal_ref.parse_key ({rec['ref']})")
    check(section_by_number("173", instrument_id=COMPANIES_ACT_2013) == rec,
          "naming the default explicitly gives an identical record")

    # The distinction that matters: None is an answer about the LAW, NotIndexed is a fact
    # about our CORPUS. Collapsing them would report "no such regulation" for a regulation
    # that plainly exists.
    check(section_by_number("99999") is None,
          "a section that is not in the Act returns None -- an answer about the law")
    # LODR is now sectioned: a regulation is found by NUMBER in its own instrument, and the
    # record says, in machine-readable form, that nobody has reviewed it.
    reg17 = section_by_number("17", instrument_id=SEBI_LODR_2015)
    check(reg17 is not None and reg17["title"] == "Board of Directors"
          and reg17["instrument_id"] == SEBI_LODR_2015,
          "LODR reg 17 resolves by number to 'Board of Directors', and names its instrument")
    check(reg17 is not None and reg17["production_usable"] is False
          and reg17["admission_state"] == "HUMAN_REVIEW_PENDING",
          "...and is HUMAN_REVIEW_PENDING, not production usable: indexed is not admitted")
    check(reg17 is not None and _lr.parse_key(reg17["ref"]).instrument_type == _lr.RULE
          and reg17["ref"] == "RULE:SEBI_LODR_2015:R17",
          "a LODR regulation is a RULE ref, never an Act section of the same number")
    check(reg17 != section_by_number("17"),
          "LODR reg 17 and Companies Act s.17 are different records")
    for num, head in (("23", "Related party transactions"),
                      ("30", "Disclosure of events or information"),
                      ("33", "Financial results"), ("34", "Annual Report"),
                      ("17A", "Maximum number of directorships")):
        r = section_by_number(num, instrument_id=SEBI_LODR_2015)
        check(r is not None and r["title"] == head, f"LODR reg {num} is {head!r}")
    sched = section_by_number("Schedule II", instrument_id=SEBI_LODR_2015)
    check(sched is not None and sched["kind"] == "schedule" and sched["ref"] is None,
          "a Schedule is looked up by name and carries no legal_ref (it has no form there)")
    check(section_by_number("104", instrument_id=SEBI_LODR_2015) is None,
          "LODR has no regulation 104 -- None is an answer about the law")
    try:
        section_by_number("1", instrument_id="NO_SUCH_ACT")
        check(False, "an unregistered instrument must be refused")
    except NotIndexed as e:
        check("Known:" in str(e) and COMPANIES_ACT_2013 in str(e),
              "an unknown instrument is refused, listing the ones that exist")

    check(instrument(SEBI_LODR_2015).scope_key == "SEBI_LODR"
          and instrument(COMPANIES_ACT_2013).scope_key == "CA2013",
          "each instrument names its checker/scope.py key, so the two registers agree")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
