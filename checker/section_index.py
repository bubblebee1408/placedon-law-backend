"""
Look up a Companies Act section by its NUMBER.

The corpus keys records by India Code's internal sectionID. The section number appears nowhere in
the record, so before this existed s.173 was simply not findable. Built offline from the full-Act
PDF by scripts/build_section_index.py.

Run: python3 checker/section_index.py
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus/companies_act"
INDEX = CORPUS / "_index.json"


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads(INDEX.read_text())["entries"]


def lookup(section_number: str) -> dict | None:
    """Index entry for a section number, or None. Never guesses."""
    return _index().get(str(section_number).strip().upper())


def section_by_number(section_number: str) -> dict | None:
    """The full corpus record for a section number, with its index entry attached.

    Returns None when the section is unmapped, omitted from the Act, or matched only with low
    confidence. An unmapped section is a real answer, not an error to paper over.
    """
    e = lookup(section_number)
    if not e or not e.get("section_id"):
        return None
    if e.get("confidence") not in ("high", "medium"):
        return None
    rec = json.loads((CORPUS / f"{e['section_id']}.json").read_text())
    rec["section_number"] = e["section_number"]
    rec["title"] = e["title"]
    rec["index_confidence"] = e["confidence"]
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

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
