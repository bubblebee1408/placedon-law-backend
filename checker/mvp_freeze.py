"""
Freeze the 17 MVP section mappings that were hand-verified on 21 Aug 2026.

These are the only mappings in the corpus that a human has actually read and confirmed: each
section's text was checked against its title. Everything downstream -- retrieval, citations, the
applicability engine -- assumes they are right. A parser change that silently moves one of them
would be invisible until it produced a wrong legal answer.

That is not hypothetical. During the build, one parser fix moved s.185 from 49111 to unmapped and
nothing failed; it was caught only by a hand-written comparison. This file makes that a test.

If a mapping here changes, the test fails and the change must be re-verified BY READING THE TEXT,
not by re-running the builder and accepting its new opinion.

Run: python3 checker/mvp_freeze.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "corpus/companies_act/_index.json"
CORPUS = INDEX.parent

# section number -> (section_id, title as verified). Hand-verified 2026-08-21.
VERIFIED: dict[str, tuple[str, str]] = {
    "96": ("1287", "Annual general meeting"),
    "101": ("1292", "Notice of meeting"),
    "102": ("1293", "Statement to be annexed to notice"),
    "103": ("1294", "Quorum for meetings"),
    "114": ("1305", "Ordinary and special resolutions"),
    "117": ("1308", "Resolutions and agreements to be filed"),
    "173": ("49099", "Meetings of Board"),
    "174": ("49100", "Quorum for meetings of Board"),
    "175": ("49101", "Passing of resolution by circulation"),
    "179": ("49105", "Powers of Board"),
    "184": ("49110", "Disclosure of interest by director"),
    "188": ("49114", "Related party transactions"),
    "177": ("49103", "Audit committee"),
    "178": ("49104", "Nomination and Remuneration Committee and Stakeholders Relationship Committee"),
    "180": ("49106", "Restrictions on powers of Board"),
    "185": ("49111", "Loan to directors, etc"),
    "186": ("49112", "Loan and investment by company"),
}

# A phrase that must appear in the section's own text. Guards against the mapping pointing at a
# plausible-looking but wrong record -- an ID match alone would not catch that.
TEXT_ANCHOR: dict[str, str] = {
    "96": "one person company",
    "101": "twenty-one days",
    "103": "articles of the company",
    "173": "first meeting of the board",
    "174": "one-third of its total strength",
    "184": "every director",
    "185": "advance any loan",
    "188": "consent of the board of directors",
}


def _body(section_id: str) -> str:
    raw = json.loads((CORPUS / f"{section_id}.json").read_text())["content"]
    return " ".join(re.sub(r"<[^>]+>", " ", raw).split()).lower()


def _test() -> None:
    entries = json.loads(INDEX.read_text())["entries"]
    from checker.legal_ref import ACT, AmbiguousReference, LegalRef, parse_key, resolve
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            print(f"[FAIL] {label}")

    for num, (sid, title) in VERIFIED.items():
        e = entries.get(num)
        if e is None:
            check(False, f"s.{num} missing from index entirely")
            continue
        check(str(e.get("section_id")) == sid,
              f"s.{num} moved: {sid} -> {e.get('section_id')} (re-verify by READING the text)")
        check(e.get("confidence") == "high", f"s.{num} confidence dropped to {e.get('confidence')}")
        check(e.get("title", "").lower().startswith(title.lower()[:18]),
              f"s.{num} title changed: {title!r} -> {e.get('title')!r}")

    for num, phrase in TEXT_ANCHOR.items():
        sid = VERIFIED[num][0]
        check(phrase in _body(sid), f"s.{num} (id {sid}) text no longer contains {phrase!r}")

    # An MVP section must stay an ACT reference. If one silently became a RULE reference, every
    # citation built on it would name the wrong instrument while still looking well-formed.
    refs = [LegalRef(ACT, "COMPANIES_ACT_2013", n, t, sid) for n, (sid, t) in VERIFIED.items()]
    for r in refs:
        check(parse_key(r.key()).instrument_type == ACT, f"{r.key()} is still an ACT reference")
        check(r.key().startswith("ACT:COMPANIES_ACT_2013:S"), f"{r.key()} keeps the Act namespace")

    # Number-only lookup must never resolve once the Rules land alongside the Act in Week 2.
    from checker.legal_ref import COLLISION_FIXTURE
    try:
        resolve(refs + COLLISION_FIXTURE, "56")
        check(False, "bare number 56 resolved -- Act/Rule namespaces have collapsed")
    except AmbiguousReference:
        check(True, "bare number 56 still refuses to resolve across instruments")

    print(f"{ok}/{ok + fail} passed" + ("" if not fail else "  <-- MVP MAPPING DRIFT"))
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
