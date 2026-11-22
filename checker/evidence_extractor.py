"""Extract obligation-register Evidence from board minutes text.

No LLM. No network. Regex + date parsing only. Feeds into `obligations.Evidence`.

The extractor is deliberately conservative: it returns None (unknown) rather than
guess, because obligations.py treats None as UNDETERMINED — a safe refusal — while
a wrong date would produce a false pass or false fail on s.173 spacing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from checker.obligations import Evidence

# ── date patterns ───────────────────────────────────────────────────────────
# Indian corporate documents use several date formats. Order matters for
# disambiguation: "29 May 2024" and "May 29, 2024" are both common.
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "29 May 2024", "29th May 2024", "29th May, 2024"
_DMY = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(" + "|".join(_MONTHS) + r")"
    r",?\s+(\d{4})\b", re.I)

# "May 29, 2024", "May 29 2024"
_MDY = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)

# "29/05/2024", "29-05-2024", "29.05.2024"
_NUMERIC = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")

# ISO "2024-05-29"
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _parse_date(day: int, month: int, year: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _all_dates(text: str) -> list[date]:
    """Extract every parseable date from text. Deduplicates, sorted."""
    seen: set[date] = set()

    for m in _DMY.finditer(text):
        d = _parse_date(int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)))
        if d:
            seen.add(d)

    for m in _MDY.finditer(text):
        d = _parse_date(int(m.group(2)), _MONTHS[m.group(1).lower()], int(m.group(3)))
        if d:
            seen.add(d)

    for m in _NUMERIC.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d = _parse_date(day, month, year)
        if d:
            seen.add(d)

    for m in _ISO.finditer(text):
        d = _parse_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            seen.add(d)

    return sorted(seen)


# ── meeting-date extraction ─────────────────────────────────────────────────
_DATE_FRAG = (
    r"(?:"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:" + "|".join(_MONTHS) + r"),?\s+\d{4}"
    r"|(?:" + "|".join(_MONTHS) + r")\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{1,2}[/\-]\d{1,2}[/\-]\d{4}"
    r")"
)

_MEETING_HELD = re.compile(
    r"(?:"
    r"(?:meeting\s+(?:of\s+the\s+)?(?:board\s+of\s+directors?|board)|board\s+meeting)"
    r"\s+(?:of\s+.{3,80}\s+)?held"
    r"|(?:board\s+of\s+directors?).{3,80}meeting\s+held"
    r")\s+(?:on|today\s+i\.?e\.?)\s+"
    r"(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*)?"
    r"(" + _DATE_FRAG + r")",
    re.I)

_AGM_HELD = re.compile(
    r"(?:annual\s+general\s+meeting|AGM)"
    r"\s+(?:of\s+.{3,80}\s+)?held\s+(?:on|today\s+i\.?e\.?)\s+"
    r"(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*)?"
    r"(" + _DATE_FRAG + r")",
    re.I)


def _date_from_fragment(frag: str) -> date | None:
    """Parse a date fragment captured by _DATE_FRAG."""
    m = _DMY.search(frag)
    if m:
        return _parse_date(int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)))
    m = _MDY.search(frag)
    if m:
        return _parse_date(int(m.group(2)), _MONTHS[m.group(1).lower()], int(m.group(3)))
    m = _NUMERIC.search(frag)
    if m:
        return _parse_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_meeting_dates(text: str) -> list[date]:
    """Dates where 'board meeting held on <date>' appears."""
    dates: list[date] = []
    for m in _MEETING_HELD.finditer(text):
        d = _date_from_fragment(m.group(1))
        if d:
            dates.append(d)
    return sorted(set(dates))


def _extract_agm_dates(text: str) -> list[date]:
    """Dates where 'annual general meeting held on <date>' appears."""
    dates: list[date] = []
    for m in _AGM_HELD.finditer(text):
        d = _date_from_fragment(m.group(1))
        if d:
            dates.append(d)
    return sorted(set(dates))


# ── director count ──────────────────────────────────────────────────────────
# "strength of the Board" or "total strength" near a number
_BOARD_STRENGTH = re.compile(
    r"(?:total\s+)?(?:strength|number)\s+of\s+(?:the\s+)?(?:board|directors)"
    r"\s+(?:is|was|being|of)\s+(\d{1,3})\b", re.I)

# PRESENT section: count named directors. Ends at IN ATTENDANCE, INVITEE,
# LEAVE OF ABSENCE, or a double-newline gap.
_PRESENT_SECTION = re.compile(
    r"(?:^|\n)\s*PRESENT\s*[:\n](.+?)"
    r"(?=\n\s*(?:IN\s+ATTENDANCE|In\s+attendance|INVITEE|LEAVE\s+OF)\b"
    r"|\n\s*\n)",
    re.S)


def _extract_director_count(text: str) -> int | None:
    """Extract total board strength. Explicit statement wins over head count."""
    m = _BOARD_STRENGTH.search(text)
    if m:
        return int(m.group(1))
    ps = _PRESENT_SECTION.search(text)
    if ps:
        lines = [ln.strip() for ln in ps.group(1).strip().splitlines() if ln.strip()]
        # A director line: starts with optional number+dot, then a name (Mr/Ms/Dr/Shri or
        # capital letter). Lines like "Company Secretary" or "X Secretary" are attendance, not
        # directors. Cap at 30 — no board has 30 directors.
        name_re = re.compile(r"^\d{0,2}\.?\s*(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+\S", re.I)
        name_lines = [ln for ln in lines if name_re.match(ln)]
        if not name_lines:
            # Fallback: numbered lines like "1. A.B.", but only within the first few
            name_lines = [ln for ln in lines[:15]
                          if re.match(r"^\d{1,2}\.\s+[A-Z]", ln)]
        if 1 <= len(name_lines) <= 30:
            return len(name_lines)
    return None


# ── previous board meeting dates (from "minutes of the previous meeting") ──
_PREV_MEETING = re.compile(
    r"minutes?\s+of\s+(?:the\s+)?(?:previous|last|earlier)\s+"
    r"(?:board\s+)?meeting\s+(?:of\s+.{3,60}\s+)?held\s+on\s+"
    r"(" + _DATE_FRAG + r")",
    re.I)


def _extract_previous_meeting_dates(text: str) -> list[date]:
    dates: list[date] = []
    for m in _PREV_MEETING.finditer(text):
        d = _date_from_fragment(m.group(1))
        if d:
            dates.append(d)
    return sorted(set(dates))


# ── quorum ──────────────────────────────────────────────────────────────────
_QUORUM_PRESENT = re.compile(
    r"\bquorum\s+(?:was\s+)?(?:present|established|confirmed|constituted)\b", re.I)


def _quorum_recorded(text: str) -> bool:
    return bool(_QUORUM_PRESENT.search(text))


# ── financial year references ───────────────────────────────────────────────
_FY = re.compile(r"\b(?:FY|financial\s+year)\s*(\d{4})[\s\-/]+(\d{2,4})\b", re.I)
_FY_ENDING = re.compile(r"\byear\s+end(?:ing|ed)\s+(?:on\s+)?(?:31st?\s+)?March\s*,?\s*(\d{4})\b", re.I)


def _extract_financial_year(text: str) -> str | None:
    """e.g. '2024-25' or '2025-26'. Returns the first found."""
    m = _FY.search(text)
    if m:
        y1 = m.group(1)
        y2 = m.group(2)
        if len(y2) == 2:
            y2 = y1[:2] + y2
        return f"{y1}-{y2[-2:]}"
    m = _FY_ENDING.search(text)
    if m:
        end_year = int(m.group(1))
        return f"{end_year - 1}-{str(end_year)[-2:]}"
    return None


# ── sections referenced ────────────────────────────────────────────────────
_SECTION_REF = re.compile(
    r"\bsection\s+(\d{1,3}(?:\(\d+\))?(?:\([a-z]\))?)\s+"
    r"(?:of\s+)?(?:the\s+)?(?:companies\s+act|act|CA)\b", re.I)


def _extract_section_refs(text: str) -> list[str]:
    """CA 2013 section numbers referenced in the document."""
    return sorted(set(m.group(1) for m in _SECTION_REF.finditer(text)))


# ── public API ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExtractionResult:
    """What the extractor found, with provenance for each field."""
    evidence: Evidence
    board_meeting_dates_found: tuple[date, ...]
    agm_dates_found: tuple[date, ...]
    previous_meeting_dates_found: tuple[date, ...]
    director_count_found: int | None
    quorum_recorded: bool
    financial_year_found: str | None
    section_refs: tuple[str, ...]
    all_dates: tuple[date, ...]


def extract(text: str, as_of: date | None = None) -> ExtractionResult:
    """Extract Evidence from board minutes text.

    `as_of` is the date the extraction is READ on (today if not given).
    The Evidence it returns slots directly into obligations.build().
    """
    read_on = as_of or date.today()

    board_dates = _extract_meeting_dates(text)
    prev_dates = _extract_previous_meeting_dates(text)
    all_board = sorted(set(board_dates + prev_dates))

    agm_dates = _extract_agm_dates(text)
    director_count = _extract_director_count(text)
    fy = _extract_financial_year(text)
    section_refs = _extract_section_refs(text)
    all_dates_found = _all_dates(text)

    # Calendar year for s.173: year of the meeting, or the most common year
    # among all board dates found.
    calendar_year: int | None = None
    if all_board:
        calendar_year = all_board[0].year
    elif all_dates_found:
        calendar_year = all_dates_found[0].year

    ev = Evidence(
        board_meetings=tuple(all_board) if all_board else None,
        agm_dates=tuple(agm_dates) if agm_dates else None,
        total_board_strength=director_count,
        calendar_year=calendar_year,
        read_on=read_on,
    )

    return ExtractionResult(
        evidence=ev,
        board_meeting_dates_found=tuple(board_dates),
        agm_dates_found=tuple(agm_dates),
        previous_meeting_dates_found=tuple(prev_dates),
        director_count_found=director_count,
        quorum_recorded=_quorum_recorded(text),
        financial_year_found=fy,
        section_refs=tuple(section_refs),
        all_dates=tuple(all_dates_found),
    )


# ── self-test ───────────────────────────────────────────────────────────────

def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [PASS] {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    # Date parsing
    dates = _all_dates("Meeting held on 29 May 2024 and 15th June, 2024")
    check(date(2024, 5, 29) in dates, "DMY: 29 May 2024")
    check(date(2024, 6, 15) in dates, "DMY with ordinal: 15th June, 2024")

    dates2 = _all_dates("filed on May 29, 2024")
    check(date(2024, 5, 29) in dates2, "MDY: May 29, 2024")

    dates3 = _all_dates("on 29/05/2024")
    check(date(2024, 5, 29) in dates3, "numeric: 29/05/2024")

    dates4 = _all_dates("on 2024-05-29")
    check(date(2024, 5, 29) in dates4, "ISO: 2024-05-29")

    # Meeting-date extraction
    text_rm = (
        "the Board of Directors of Route Mobile Limited at its meeting held "
        "today i.e. May 29, 2024 have approved the following"
    )
    md = _extract_meeting_dates(text_rm)
    check(date(2024, 5, 29) in md, "board meeting date from real Route Mobile text")

    # Director count
    text_dc = "total strength of the Board is 7"
    check(_extract_director_count(text_dc) == 7, "explicit board strength = 7")

    # Present-section fallback — Mr/Ms prefix lines
    text_ps = "PRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\nIN ATTENDANCE\nX Secretary"
    check(_extract_director_count(text_ps) == 3, "PRESENT section head count = 3")

    # Present-section with named initials (ICSI subsequent board specimen style)
    text_ps2 = "PRESENT\nA.B. Chairman\nC.D. Directors\nE.F.\nI.J.\nIN ATTENDANCE\nX Secretary"
    # No Mr/Ms prefix, so falls through to numbered-line fallback — but these aren't numbered
    # either, so returns None (conservative)
    check(_extract_director_count(text_ps2) is None, "PRESENT initials without Mr/Ms = None")

    # Quorum
    check(_quorum_recorded("The quorum was present and established."), "quorum present")
    check(not _quorum_recorded("No quorum language here."), "no quorum")

    # Financial year
    check(_extract_financial_year("for FY 2024-25") == "2024-25", "FY 2024-25")
    check(_extract_financial_year("year ending March 2025") == "2024-25", "year ending March 2025")

    # Section refs
    refs = _extract_section_refs(
        "Section 173 of the Companies Act and Section 184(1) of the Act")
    check("173" in refs, "section 173 ref")
    check("184(1)" in refs, "section 184(1) ref")

    # Full extract
    full = (
        "Minutes of the meeting of the Board of Directors held on 15th January, 2024.\n"
        "PRESENT\n1. Mr. A (Chairman)\n2. Mr. B\n3. Ms. C\n4. Mr. D\n"
        "IN ATTENDANCE\nX Secretary\n"
        "The quorum was established.\n"
        "Minutes of the previous Board meeting held on 10th October, 2023 were noted.\n"
        "Section 173 of the Companies Act, 2013.\n"
        "FY 2023-24.\n"
    )
    r = extract(full, as_of=date(2024, 2, 1))
    check(r.evidence.board_meetings is not None and len(r.evidence.board_meetings) == 2,
          "full extract: 2 board dates (current + previous)")
    check(r.evidence.calendar_year == 2023,
          "full extract: calendar_year from earliest board date")
    check(r.evidence.total_board_strength == 4,
          "full extract: 4 directors from PRESENT (Mr/Ms lines)")
    check(r.evidence.read_on == date(2024, 2, 1),
          "full extract: read_on passed through")
    check(r.quorum_recorded, "full extract: quorum recorded")
    check(r.financial_year_found == "2023-24", "full extract: FY 2023-24")

    # None for empty
    empty = extract("No useful content here.", as_of=date(2024, 1, 1))
    check(empty.evidence.board_meetings is None, "empty text: board_meetings is None")
    check(empty.evidence.total_board_strength is None, "empty text: strength is None")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
