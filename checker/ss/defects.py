"""
Deterministic SS-1 / SS-2 defect checks over minutes text.

No LLM. No corpus. No network. Every rule traces to a real ROC adjudication order — see RULES.md.

The scope boundary matters and is stated in the output: some penalised defects are properties of the
**physical minutes book** (consecutive pagination across the book, Chairman initials on every page,
blank pages scored out). Those cannot be decided from a .docx and are reported as NEEDS_BOOK rather
than guessed at. Reporting them as PASS would be the same failure mode this product exists to prevent.

Run: python3 checker/ss/defects.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

Status = Literal["PASS", "DEFECT", "NEEDS_BOOK", "N/A"]
MeetingKind = Literal["board", "general"]
# The document type decides which checks even apply. Running minutes checks against a notice
# was the largest defect the real-document corpus exposed: an AGM NOTICE is issued BEFORE the
# meeting, so it cannot record when the meeting concluded, whether a quorum was present, or the
# date minutes were entered in the book. Reporting those as DEFECT is a category error, and it
# produced false-positive rates of 80-93% against genuinely compliant filings.
DocType = Literal["minutes", "notice", "outcome", "unknown"]

APPLICABILITY: dict[str, frozenset[str]] = {
    "T1.1": frozenset({"minutes"}), "T1.2": frozenset({"minutes"}),
    "T1.3": frozenset({"minutes"}), "T1.4a": frozenset({"minutes"}),
    "T1.4b": frozenset({"minutes"}), "T1.5": frozenset({"minutes"}),
    "T1.6a": frozenset({"minutes", "notice", "outcome"}),
    "T1.6b": frozenset({"minutes", "outcome"}),
    "T1.6c": frozenset({"minutes", "outcome"}),
    "T1.7": frozenset({"minutes"}), "T1.8": frozenset({"minutes"}),
    "C.quorum": frozenset({"minutes"}),
}

_NOTICE_HINT = re.compile(r"notice\s+is\s+hereby\s+given|NOTICE\s+OF\s+THE|explanatory\s+statement|proxy\s+form|e-?voting", re.I)
_MINUTES_HINT = re.compile(r"minutes\s+of\s+the|the\s+meeting\s+(?:commenced|concluded)|chairman.{0,30}signed", re.I)
_OUTCOME_HINT = re.compile(r"outcome\s+of\s+(?:the\s+)?board|regulation\s+30", re.I)


def classify(text: str) -> DocType:
    """Infer document type. Order matters - an outcome filing also uses notice language."""
    if _OUTCOME_HINT.search(text):
        return "outcome"
    if _MINUTES_HINT.search(text):
        return "minutes"
    if _NOTICE_HINT.search(text):
        return "notice"
    return "unknown"

# s.118(11). s.446B halves both for small company / startup / OPC / producer company.
PENALTY_COMPANY = 25_000
PENALTY_OFFICER = 5_000

# SS-1 7.5.2 / SS-2 17.4.2 read with Rule 25(1)(b).
ENTRY_DEADLINE_DAYS = 30
# SS-1 7.4 — draft circulation.
DRAFT_CIRCULATION_DAYS = 15


@dataclass(frozen=True)
class Finding:
    check_id: str
    status: Status
    ss_cite: str
    defect: str
    evidence: str                    # verbatim from the document, or the reason it is absent
    precedent: str                   # a real order that penalised this
    advisory_only: bool = False      # True => zero penalty precedent; never present as a violation


@dataclass(frozen=True)
class Minutes:
    """What we can read out of a document. doc_type gates which checks apply."""
    text: str
    kind: MeetingKind
    meeting_date: date | None = None
    entry_date: date | None = None
    # Physical-book facts a scanner cannot see. None => unknown, report NEEDS_BOOK.
    pages_consecutive_across_book: bool | None = None
    every_page_initialled: bool | None = None
    blank_pages_scored_out: bool | None = None
    doc_type: DocType | None = None      # None => infer with classify()


# --- textual detectors -------------------------------------------------------
# Deliberately permissive: a false PASS is worse than a false DEFECT here, because the user is
# checking a document they are about to rely on. Each pattern was written against the language the
# ICSI specimen minutes actually use.

_ORDINAL_WORDS = (r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|"
                  r"twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|"
                  r"nineteenth|twentieth|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety")
# Two forms occur in practice and both must pass:
#   explicit label   -> "Meeting No: 14", "Serial No. 3"
#   ordinal in title -> "the 62nd Annual General Meeting", 'the Twenty First ("21st") Meeting'
# The first form alone was the author's own fixture phrasing and fired DEFECT on 18/18 real
# documents, including all five ICSI specimens. That was circular testing, caught by real corpus.
_SERIAL = re.compile(
    r"\b(?:meeting\s+(?:no|number|serial)|serial\s+(?:no|number)|minutes?\s+no)\b\.?\s*[:\-]?\s*\d+"
    r"|\b\d{1,3}(?:st|nd|rd|th)\s+(?:annual\s+general|extra-?ordinary\s+general|general|board)\s+meeting\b"
    r"|\b(?:" + _ORDINAL_WORDS + r")[\s\-]*(?:" + _ORDINAL_WORDS + r")?\s*\(?\"?\d{0,3}(?:st|nd|rd|th)?\"?\)?\s*"
    r"(?:annual\s+general|extra-?ordinary\s+general|general|board)\s+meeting\b",
    re.I,
)
_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\s*(?:a\.?m\.?|p\.?m\.?|hours|hrs)\b", re.I)
_COMMENCED = re.compile(r"\b(commenc\w+|began|started|convened)\b", re.I)
# Contexts where a "commenced ... at TIME" sentence is about something other than the meeting.
# Remote e-voting windows are the common trap in modern Indian AGM notices.
_NOT_THE_MEETING = re.compile(
    r"\b(e-?voting|remote\s+voting|voting\s+period|book\s+closure|register\s+of\s+members|"
    r"cut-?off\s+date|dividend|window\s+closure|trading\s+window)\b", re.I)
_CONCLUDED = re.compile(r"\b(conclud\w+|terminat\w+|ended|closed|dispers\w+)\b", re.I)
# "Place" must sit in a signing context. The bare word appears constantly in ordinary prose
# ("place of business", "took place"), and matching it false-PASSED 8 real AGM notices on a check
# backed by real penalty orders (Wind World, Sany).
_PLACE_SIGNED = re.compile(
    r"\b(?:signed\s+at|place\s+of\s+signing|place\s+of\s+meeting)\b\s*[:\-]?\s*[A-Z][\w\s]{2,40}"
    r"|^\s*place\s*[:\-]\s*[A-Z][\w\s]{2,40}",
    re.I | re.M)
_ENTRY_DATE = re.compile(r"\b(date\s+of\s+entry|entered\s+(?:in|on)|recorded\s+in\s+the\s+minutes?\s+book)\b", re.I)
_QUORUM = re.compile(r"\bquorum\b", re.I)
_CHAIR_ELECTED = re.compile(r"\b(chair(?:man|person)?)\b.{0,60}\b(elect\w+|took\s+the\s+chair|presided)\b", re.I | re.S)
_ON_BEHALF = re.compile(r"\bon\s+behalf\s+of\b.{0,40}\bchair(?:man|person)?\b", re.I | re.S)
# SS-1 7.3.2 — resolutions in present tense; minutes otherwise third person past tense.
_RESOLVED = re.compile(r"\bRESOLVED\s+THAT\b")
# Indian corporate documents are full of roman-numeral list markers - "i)", "(iii)", "ii." - which
# a naive \bI\b match reads as the first-person pronoun. It fired on 15/18 real documents.
_ROMAN_MARKER = re.compile(r"\(?\b[ivx]{1,4}\b\s*[).\]]", re.I)
_FIRST_PERSON = re.compile(r"\b(we|our|us)\b|(?<![\w(])I\b(?!\s*[).\]])", re.I)


def _has(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0).strip() if m else None


def check_serial_number(m: Minutes) -> Finding:
    """T1.6a — serial number of the meeting stated at the beginning."""
    hit = _has(_SERIAL, m.text)
    return Finding(
        "T1.6a", "PASS" if hit else "DEFECT",
        "SS-1 7.1.x / SS-2 17.2.2.1",
        "Serial number of the meeting not stated in the minutes",
        hit or "no meeting serial number found",
        "Sunima Trading P Ltd, ROC UP-I, 13.07.2026 — Rs 45,000; Merino Shelters, 15.05.2026",
    )


def check_commencement_and_conclusion(m: Minutes) -> list[Finding]:
    """T1.6b — time of commencement AND conclusion. Conclusion is the commonly missed half."""
    out = []
    for label, verb, cid in (("commencement", _COMMENCED, "T1.6b"), ("conclusion", _CONCLUDED, "T1.6c")):
        # a time must appear in the same sentence as the commence/conclude verb
        found = None
        for sent in re.split(r"(?<=[.;])\s+", m.text):
            if verb.search(sent) and _TIME.search(sent) and not _NOT_THE_MEETING.search(sent):
                found = sent.strip()[:120]
                break
        out.append(Finding(
            cid, "PASS" if found else "DEFECT",
            "SS-2 17.2.2.1(o) / SS-1 equivalent",
            f"Time of {label} of the meeting not recorded",
            found or f"no time recorded against {label}",
            "Rashi Steel and Power, ROC Chhattisgarh, 24.03.2026 & 07.04.2026; Triveni Nidhi, 04.09.2024",
        ))
    return out


def check_place_of_signing(m: Minutes) -> Finding:
    """T1.7 — place at which the minutes were signed."""
    hit = _has(_PLACE_SIGNED, m.text)
    return Finding(
        "T1.7", "PASS" if hit else "DEFECT",
        "SS-1 7.6",
        "Place at which the minutes were signed not recorded",
        hit or "no place of signing found",
        "Wind World (India) Ltd, ROC Goa/Daman & Diu, 2024; Sany Heavy Industry, 17.05.2024",
    )


def check_entry_recorded(m: Minutes) -> Finding:
    """T1.4a — date of entry in the minutes book recorded."""
    hit = _has(_ENTRY_DATE, m.text) or (m.entry_date and str(m.entry_date))
    return Finding(
        "T1.4a", "PASS" if hit else "DEFECT",
        "SS-1 7.5.2 / SS-2 17.4.2 r/w R.25(1)(b)",
        "Date of entry of the minutes in the Minutes Book not recorded",
        str(hit) if hit else "no date of entry found",
        "Harsh Gathani Enterprise, ROC Ahmedabad, 24.06.2025; Sen Hon Lee, 13.10.2025",
    )


def check_entry_within_30_days(m: Minutes) -> Finding:
    """T1.4b — entered within 30 days. Highest financial exposure in the corpus."""
    if m.meeting_date is None or m.entry_date is None:
        return Finding(
            "T1.4b", "NEEDS_BOOK", "R.25(1)(b), SS-1 7.5.2",
            "Cannot verify the 30-day entry deadline",
            "meeting date and/or entry date not supplied",
            "Trouw Nutrition India, ROC Telangana, 22.10.2024 — Rs 21.35 lakh across 54 board meetings",
        )
    lag = (m.entry_date - m.meeting_date).days
    ok = 0 <= lag <= ENTRY_DEADLINE_DAYS
    return Finding(
        "T1.4b", "PASS" if ok else "DEFECT",
        "R.25(1)(b), SS-1 7.5.2 / SS-2 17.4.2",
        f"Minutes entered {lag} days after the meeting (limit {ENTRY_DEADLINE_DAYS})",
        f"meeting {m.meeting_date} -> entry {m.entry_date}",
        "Trouw Nutrition India, 22.10.2024 — Rs 21.35 lakh; Tamilnad Mercantile Bank, 182-day delay",
    )


def check_signatory(m: Minutes) -> Finding:
    """T1.5 — never a third director 'on behalf of' the Chairman."""
    bad = _has(_ON_BEHALF, m.text)
    return Finding(
        "T1.5", "DEFECT" if bad else "PASS",
        "SS-1 7.6",
        "Minutes signed by another director on behalf of the Chairman",
        bad or "no 'on behalf of' signature found",
        "Landomus Realty Ventures, ROC Bangalore, 31.03.2026; Dystar India, 09.09.2025",
    )


def check_quorum_recorded(m: Minutes) -> Finding:
    """Mandatory content. ComplyRelax auto-inserts this one, so it should usually pass."""
    hit = _has(_QUORUM, m.text)
    return Finding(
        "C.quorum", "PASS" if hit else "DEFECT",
        "SS-1 7.2.2.1(e)",
        "Presence of quorum not recorded",
        hit or "no reference to quorum",
        "Mandatory enumerated content; SS-1 7.2.2.1",
    )


def check_tense(m: Minutes) -> Finding:
    """SS-1 7.3.2 — third person and past tense; resolutions in present tense."""
    stripped = _ROMAN_MARKER.sub(" ", m.text)
    bad = _has(_FIRST_PERSON, stripped)
    return Finding(
        "T1.8", "DEFECT" if bad else "PASS",
        "SS-1 7.3.2 / SS-2 17.3.2",
        "Minutes not written in the third person",
        f"first-person usage: {bad!r}" if bad else "no first-person usage found",
        "No penalty order found for tense alone — advisory",
        advisory_only=True,
    )


def check_physical_book(m: Minutes) -> list[Finding]:
    """T1.1-T1.3 — properties of the physical book. Never guessed from text."""
    specs = [
        ("T1.1", m.pages_consecutive_across_book,
         "SS-1 7.1.4 / SS-2 17.1.4",
         "Minutes book pages not consecutively numbered across the whole book",
         "Rosmerta Technologies, ROC Delhi, 07.10.2025 — numbering restarted each FY; ~24 of 68 orders"),
        ("T1.2", m.every_page_initialled,
         "SS-1 7.6.2",
         "Chairman did not initial every page of the minutes",
         "Chartered Mercantile Mutual Benefits, ROC Kanpur, 10.02.2026; Rashi Steel, 24.03.2026"),
        ("T1.3", m.blank_pages_scored_out,
         "SS-1 7.1.4",
         "Blank pages not scored out and not initialled by the Chairman",
         "Madhyam Agrivet Industries, ROC Pune, 30.06.2023; Rosmerta Autotech, 09.10.2025"),
    ]
    out = []
    for cid, val, cite, defect, prec in specs:
        if val is None:
            out.append(Finding(cid, "NEEDS_BOOK", cite, defect,
                               "physical minutes book not inspected", prec))
        else:
            out.append(Finding(cid, "PASS" if val else "DEFECT", cite, defect,
                               f"inspected: {val}", prec))
    return out


def scan(m: Minutes) -> list[Finding]:
    dt = m.doc_type or classify(m.text)
    findings = [
        check_serial_number(m),
        *check_commencement_and_conclusion(m),
        check_place_of_signing(m),
        check_entry_recorded(m),
        check_entry_within_30_days(m),
        check_signatory(m),
        check_quorum_recorded(m),
        check_tense(m),
        *check_physical_book(m),
    ]
    # A check that does not apply to this document type makes no claim at all.
    out = []
    for f in findings:
        allowed = APPLICABILITY.get(f.check_id)
        if allowed is not None and dt not in allowed:
            out.append(Finding(f.check_id, "N/A", f.ss_cite, f.defect,
                               f"not applicable to a document of type {dt!r}",
                               f.precedent, f.advisory_only))
        else:
            out.append(f)
    return out


def exposure(findings: list[Finding], officers: int, small_company: bool = False) -> int:
    """Penalty exposure for ONE meeting in ONE book.

    The corpus shows exposure multiplies per meeting, per book and per financial year — Om Shyamji
    drew three separate orders for the same defect in three books on one day. This returns the
    single-instance figure; the caller multiplies.
    """
    if not any(f.status == "DEFECT" and not f.advisory_only for f in findings):
        return 0
    total = PENALTY_COMPANY + PENALTY_OFFICER * officers
    return total // 2 if small_company else total


# --- self-test ---------------------------------------------------------------

CLEAN = """
Minutes of the 14th Meeting of the Board of Directors. Meeting No: 14.
Held on Monday, 12 May 2026. The Meeting commenced at 11:00 a.m.
Mr A Sharma took the Chair. The requisite quorum being present, the Chairman called the
Meeting to order. RESOLVED THAT the accounts be approved.
The Meeting concluded at 12:30 p.m.
The minutes were entered in the Minutes Book on 20 May 2026.
Place: Bengaluru. Signed by the Chairman.
"""

DEFECTIVE = """
Minutes of the Board Meeting held on 12 May 2026. We discussed the accounts and our auditor
was present. RESOLVED THAT the accounts be approved.
Signed on behalf of the Chairman by Mr B Rao, Director.
"""


def _test() -> None:
    passed = failed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"[PASS] {label}")
        else:
            failed += 1
            print(f"[FAIL] {label}")

    clean = scan(Minutes(CLEAN, "board", date(2026, 5, 12), date(2026, 5, 20)))
    by = {f.check_id: f for f in clean}
    ok(by["T1.6a"].status == "PASS", "clean: serial number found")
    ok(by["T1.6b"].status == "PASS", "clean: commencement time found")
    ok(by["T1.6c"].status == "PASS", "clean: conclusion time found")
    ok(by["T1.7"].status == "PASS", "clean: place of signing found")
    ok(by["T1.4a"].status == "PASS", "clean: date of entry recorded")
    ok(by["T1.4b"].status == "PASS", "clean: entered within 30 days (8 days)")
    ok(by["C.quorum"].status == "PASS", "clean: quorum recorded")
    ok(by["T1.5"].status == "PASS", "clean: no 'on behalf of' signature")
    ok(all(by[c].status == "NEEDS_BOOK" for c in ("T1.1", "T1.2", "T1.3")),
       "clean: physical-book checks abstain rather than guess")

    bad = scan(Minutes(DEFECTIVE, "board", date(2026, 5, 12), date(2026, 7, 30)))
    b = {f.check_id: f for f in bad}
    ok(b["T1.6a"].status == "DEFECT", "defective: missing serial number caught")
    ok(b["T1.6c"].status == "DEFECT", "defective: missing conclusion time caught")
    ok(b["T1.7"].status == "DEFECT", "defective: missing place of signing caught")
    ok(b["T1.4b"].status == "DEFECT", "defective: 79-day entry delay caught")
    ok(b["T1.5"].status == "DEFECT", "defective: 'on behalf of' signature caught")
    ok(b["C.quorum"].status == "DEFECT", "defective: missing quorum caught")
    ok(b["T1.8"].advisory_only, "tense finding is advisory-only, never a violation")

    ok(exposure(bad, officers=3) == 25_000 + 15_000, "exposure: Rs 40,000 for 3 officers")
    ok(exposure(bad, officers=3, small_company=True) == 20_000, "exposure: s.446B halves it")
    ok(exposure(clean, officers=3) == 0, "exposure: clean minutes carry no penalty")

    # The four non-rules must not exist as checks at all.
    ids = {f.check_id for f in clean}
    ok(not ids & {"route_map", "leave_of_absence", "dissent"},
       "zero-precedent rules are absent, not merely disabled")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
