"""Commencement provenance: which provisions a notification actually brought into force.

An amending Act's sections do not commence when the Act is passed. Section 1(2)
of the Companies (Amendment) Act 2017 lets the Central Government appoint dates,
and it did so in stages across 2018-2021. A w.e.f. date in India Code's footnote
records *a* date; it does not record which notification supplied it, and the two
can disagree.

They do disagree. S.O. 1833(E) of 7 May 2018 brings section 31 of the amending
Act into force — the section that amends s.121 of the principal Act. It does not
mention section 51, which amends s.161. Yet India Code's footnote gives s.161's
amendment the same 7 May 2018 date.

Under the strict definition of EXACT adopted 26 Aug 2026, that difference decides
whether a reconstruction may be promoted:

    EXACT requires clause identity, witness text, source hash, subsection
    identity, AND commencement provenance from a notification or the Act itself.

A date with no notification behind it is not provenance. It is a date.

## Source

Notifications are retrieved from India Code's own bitstream API, which serves the
Gazette text as published — `S.O. 1833(E)`, Gazette of India Extraordinary
No. 1646. That is the notification itself, not a summary of it. Secondary
compilations naming the same date are not used: they may be right, but a
commercial summary is not the instrument.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

CACHE = Path("corpus/sources/commencement")
API = "https://indiacode.gov.in/server/api"

CONFIRMED = "CONFIRMED"          # the notification names this provision
NOT_LISTED = "NOT_LISTED"        # the notification exists and does not name it
NO_NOTIFICATION = "NO_NOTIFICATION"   # no notification found for that date
UNREACHABLE = "UNREACHABLE"


@dataclass
class Notification:
    identifier: str              # e.g. "S.O. 1833(E)"
    date: str
    gazette_no: str | None
    url: str
    sha256: str
    sections: tuple[int, ...]    # amending-Act sections brought into force
    text: str = ""

    @property
    def locator(self) -> str:
        return f"{self.identifier} ({self.date}), Gazette No. {self.gazette_no or '?'}"


@dataclass
class Provenance:
    status: str
    amending_section: int | None = None
    notification: Notification | None = None
    note: str = ""

    @property
    def confirmed(self) -> bool:
        return self.status == CONFIRMED


# "Section 30 and 31", "Sections 54 to 58 (both inclusive)", "Section 8".
_SEC_RANGE = re.compile(r"Sections?\s+(\d+)\s+to\s+(\d+)", re.I)
_SEC_PAIR = re.compile(r"Sections?\s+(\d+)\s+and\s+(\d+)", re.I)
_SEC_ONE = re.compile(r"(?:Sections?|clause\s*\([ivx]+\)\s+of\s+section)\s+(\d+)", re.I)
# "Sub-Section (2) of Section 1" is the power the notification is made UNDER, not
# a provision it commences. Counting it put section 1 in the commenced list.
_ENABLING = re.compile(
    r"(?:conferred\s+by|exercise\s+of).{0,80}?Section\s+1\b", re.I | re.S)
_SO_ID = re.compile(r"(S\.O\.\s*\d+\(E\))")
_GAZ_NO = re.compile(r"No\.\s*(\d+)\]\s*NEW DELHI", re.I)


def parse_sections(english: str) -> tuple[int, ...]:
    """Amending-Act section numbers a notification brings into force.

    Ranges are expanded because "Sections 54 to 58 (both inclusive)" commences
    five provisions, and treating it as two would silently leave three
    uncommenced in our records.
    """
    out: set[int] = set()
    for a, b in _SEC_RANGE.findall(english):
        out.update(range(int(a), int(b) + 1))
    for a, b in _SEC_PAIR.findall(english):
        out.update({int(a), int(b)})
    for a in _SEC_ONE.findall(english):
        out.add(int(a))
    # Drop the enabling power. A notification made under s.1(2) does not thereby
    # commence s.1, and listing it overstates what the instrument did.
    if _ENABLING.search(english):
        out.discard(1)
    return tuple(sorted(out))


def _english_part(text: str) -> str:
    """The English body. The Gazette prints Hindi first; both say the same thing,
    but only one of them is parseable by these patterns."""
    i = text.find("S.O.")
    j = text.find("In exercise of the Power", i if i > 0 else 0)
    return text[j - 40:] if j > 40 else text


def _get(url: str, timeout: float = 45.0) -> bytes | None:
    from checker.robots import USER_AGENT, ssl_context
    ctx = ssl_context()
    if ctx is None:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read() if r.status == 200 else None
    except Exception:
        return None


def load_cached(date: str) -> Notification | None:
    p = CACHE / f"{date}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return Notification(**{**d, "sections": tuple(d["sections"])})


def save(n: Notification) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    d = {**n.__dict__, "sections": list(n.sections)}
    (CACHE / f"{n.date}.json").write_text(json.dumps(d, indent=1) + "\n")


def from_text(text: str, date: str, url: str) -> Notification:
    eng = _english_part(text)
    sid = _SO_ID.search(text)
    gz = _GAZ_NO.search(text)
    return Notification(
        identifier=sid.group(1).replace(" ", " ") if sid else "(unidentified)",
        date=date, gazette_no=gz.group(1) if gz else None, url=url,
        sha256="sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
        sections=parse_sections(eng), text=text[:12000])


def check(amending_section: int, wef: str) -> Provenance:
    """Was this amending-Act section brought into force on `wef`?"""
    n = load_cached(wef)
    if n is None:
        return Provenance(NO_NOTIFICATION, amending_section,
                          note=f"no commencement notification held for {wef}")
    if amending_section in n.sections:
        return Provenance(CONFIRMED, amending_section, n,
                          note=(f"{n.identifier} appoints {wef} for section "
                                f"{amending_section} of the amending Act"))
    return Provenance(NOT_LISTED, amending_section, n,
                      note=(f"{n.identifier} appoints {wef} for sections "
                            f"{list(n.sections)}, which does not include section "
                            f"{amending_section}"))


def _test() -> None:
    ok = fail = 0

    def check_(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("commencement")

    # The real enumeration from S.O. 1833(E).
    body = ("S.O. 1833(E).—In exercise of the Power conferred by Sub-Section (2) of "
            "Section 1 of the Companies (Amendment) Act, 2017 (1 of 2018), the "
            "Central Government hereby appoints the 7th May, 2018 as the date on "
            "which the following provisions of the said Act shall come into force, "
            "namely:— SI. No. Sections 1. Clause (i) and clause (xiii) of section 2; "
            "2. Section 8; 3. Section 13; 4. Sections 18 and 19; 5. Clauses (i) and "
            "(ii) of section 21; 6. Clauses (iii) and (iv) of section 23; 7. Section "
            "30 and 31; 8. Section 33; 9. Section 39 and 40; 10. Section 46; "
            "11. Section 49; 12. Section 52; 13. Sections 54 to 58 (both inclusive); "
            "14. Sections 61 and 62; 16. Section 83; 17. Sections 86 to 89 (both "
            "inclusive).")
    secs = parse_sections(body)
    check_(31 in secs, "section 31 is read as commenced (it amends s.121)")
    check_(39 in secs, "section 39 is read as commenced (it amends s.137)")
    check_(51 not in secs, "section 51 is NOT read as commenced (it amends s.161)")
    check_(all(k in secs for k in (54, 55, 56, 57, 58)),
           "'Sections 54 to 58 (both inclusive)' expands to all five")
    check_(all(k in secs for k in (86, 87, 88, 89)), "the second range expands too")
    check_(2 in secs and 8 in secs, "single-section entries are read")
    check_(1 not in secs,
           "the enabling power in s.1(2) is not counted as a commenced provision")
    check_(parse_sections("appoints the date. 1. Section 1; 2. Section 8;") == (1, 8),
           "...but a genuine s.1 entry, with no enabling language, is kept")

    n = from_text(body, "2018-05-07", "https://example/x")
    check_(n.identifier == "S.O. 1833(E)", f"the notification identifies itself ({n.identifier})")
    check_(n.sha256.startswith("sha256:"), "the notification text is hashed")
    check_("2018-05-07" in n.locator, "the locator carries the date")

    # Provenance semantics.
    check_(not Provenance(NO_NOTIFICATION).confirmed,
           "a missing notification is not provenance")
    check_(not Provenance(NOT_LISTED).confirmed,
           "a notification that omits the section is not provenance")
    check_(not Provenance(UNREACHABLE).confirmed, "an unreachable source is not provenance")
    check_(Provenance(CONFIRMED).confirmed, "only CONFIRMED counts")

    live = load_cached("2018-05-07")
    if live:
        check_(31 in live.sections, "the held 7 May 2018 notification commences s.31")
        check_(51 not in live.sections,
               "the held 7 May 2018 notification does NOT commence s.51")
        check_(live.identifier == "S.O. 1833(E)",
               f"the held notification is S.O. 1833(E) ({live.identifier})")
        p121 = check(31, "2018-05-07")
        p161 = check(51, "2018-05-07")
        check_(p121.confirmed, "s.121's amending section has commencement provenance")
        check_(not p161.confirmed,
               "s.161's amending section does NOT have provenance for that date")
    else:
        check_(False, "the 7 May 2018 notification is not cached; run the fetcher")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
