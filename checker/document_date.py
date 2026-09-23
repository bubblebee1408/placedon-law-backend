"""The date a document declares on its own face — or nothing, said plainly.

Every temporal answer in this repository turns on the document's date
(`checker/orchestrator.py`: it will not run without one). So the date has to come
from the document, and a wrong one is worse than none: it silently moves which law
the check is run against, and the answer still looks careful.

## The rule, and why it is this narrow

A **date declaration** is a line of the form `Date: <a bare date>`:

  * **The colon is required.** `dated April 13, 2020 and subsequent circulars` is a
    wrapped sentence about somebody else's instrument, not this document's date
    line. Extraction breaks such sentences at the margin, so "starts a line" alone
    admits them — this is the case that would have dated TCPL's 2025 AGM notice to
    the MCA circular of 13 April 2020.
  * **The date must begin immediately after the colon.** That refuses
    `Date of Birth 7th August 1979`, `Date of first appointment on …`, and
    `Date: Friday, June 5, 2026` — the last being a record-date table row, not the
    date the notice bears.
  * **Every declaration this reader can read must agree**, or there is no date.
    `routemobile_outcome_board_meeting_2025-11-03` declares 4 November on the
    letter and 3 November over the signatures; the document really does bear two,
    and choosing between them is not a reading, it is a guess.

Measured over the 29 public documents in `corpus/testdocs/`: 9 declare a date this
reader accepts, 20 do not. The 20 are not failures to be tuned away — the ICSI
specimens carry `Date : ______ 20_.` because a specimen has no date, Titan's date
line did not survive text extraction, and the Route Mobile filing above is
genuinely two-dated.

## The limitation this does NOT hide

A declaration whose date this reader cannot parse — `Date: 2026.05.07 21:59:27
+05'30'` (a PDF signature stamp), `Date: 28 Janua ry 2025` (somebody else's OCR,
preserved unrepaired), `Date: 7` (truncated) — is **counted and reported**, never
dropped. It could in principle carry a date that disagrees with the ones read. The
count travels with the reading so a caller can show it; `Reading.unread` is the
unresolved marker, and CLAUDE.md forbids losing it silently.

Nothing here repairs a document. `28 Janua ry 2025` is left exactly as the source
has it and simply not read.

Run: python3 checker/document_date.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS: dict[str, int] = {}
for _i, _name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], start=1):
    MONTHS[_name] = _i
    MONTHS[_name[:3]] = _i
MONTHS["sept"] = 9

_MON = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?"
        r"|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
# "April 23, 2025" and "28 January 2025" / "7th May, 2024". Both spellings appear in
# the corpus, often in the same filing. A purely numeric date (28/01/2025, 2026.05.07)
# is deliberately NOT read: day-first and year-first cannot be told apart from the
# digits, and this file exists to refuse exactly that kind of guess.
_MDY = re.compile(rf"(?i)^({_MON})\s+(\d{{1,2}})\s*,\s*(\d{{4}})(?!\d)")
_DMY = re.compile(rf"(?i)^(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\s*,?\s*(\d{{4}})(?!\d)")
_DECLARATION = re.compile(r"(?i)^[ \t]*date[ \t]*:[ \t]*(\S.*)$")

NO_DECLARATION = ("no line in this document declares the date it bears (a date "
                  "declaration is a line reading 'Date: ' and then that date)")
CONFLICT = ("this document declares more than one date on its own face ({dates}); "
            "which one it bears is not this reader's to choose")


@dataclass(frozen=True)
class Reading:
    """What one document says about its own date. `value is None` means: it does not say."""
    value: date | None
    line: int | None              # 1-based, in the text handed to read()
    quote: str                    # the declaration line, verbatim and unrepaired
    conflicting: tuple[date, ...]  # every date read, when they disagree
    unread: int                   # declarations whose date this reader could not read
    why: str                      # why there is no date; empty when there is one


def parse_date(text: str) -> date | None:
    """The date `text` OPENS with, or None. Never a numeric-only date (see the module doc)."""
    m = _MDY.match(text)
    if m:
        return _build(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    m = _DMY.match(text)
    if m:
        return _build(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def _build(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:            # "February 30, 2025" is not a date, and is not repaired
        return None


def read(text: str) -> Reading:
    """The date this document declares, or a Reading that says why there is none."""
    found: dict[date, tuple[int, str]] = {}
    unread = 0
    for n, line in enumerate(text.splitlines(), start=1):
        m = _DECLARATION.match(line)
        if not m:
            continue
        value = parse_date(m.group(1).strip())
        if value is None:
            unread += 1
        elif value not in found:
            found[value] = (n, line.strip())
    if len(found) == 1:
        value, (line, quote) = next(iter(found.items()))
        return Reading(value, line, quote, (), unread, "")
    dates = tuple(sorted(found))
    why = (CONFLICT.format(dates=", ".join(d.isoformat() for d in dates)) if dates
           else NO_DECLARATION)
    return Reading(None, None, "", dates, unread, why)


# ── tests ────────────────────────────────────────────────────────────────────
def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if cond:
            ok += 1
        else:
            fail += 1

    print("document_date")

    # ── the date a document declares ─────────────────────────────────────────
    r = read("To,\nBSE Limited\nDate: January 28, 2025 \nYours faithfully,")
    check(r.value == date(2025, 1, 28) and r.line == 3 and r.why == "",
          f"a 'Date: January 28, 2025' line is that document's date ({r.value}, line {r.line})")
    check(r.quote == "Date: January 28, 2025",
          f"the reading carries the line it was read from, verbatim ({r.quote!r})")
    check(read("Date: 28 January 2025").value == date(2025, 1, 28),
          "the day-first spelling reads the same")
    check(read("Date : 3 November 2025 Managing Director and CEO").value == date(2025, 11, 3),
          "a space before the colon and a signature after the date are still a declaration")
    check(read("Date: July 19,  2024").value == date(2024, 7, 19),
          "a doubled space inside the date is still that date")
    check(read("Date: 7th May, 2024").value == date(2024, 5, 7),
          "an ordinal day reads")
    check(read("DATE: Apr 21, 2026").value == date(2026, 4, 21),
          "the label and the month may be any case, and the month may be abbreviated")
    check(read("Date: Sept 30, 2025").value == date(2025, 9, 30),
          "'Sept' is September")

    # ── what is NOT a declaration ────────────────────────────────────────────
    # The case that matters most: a sentence about somebody else's instrument, broken
    # across lines by text extraction, used to date the document to that instrument.
    wrapped = ("General Meeting through VC/OAVM in accordance with General Circular 14/2020\n"
               "dated April 13, 2020 and subsequent circulars issued in\n"
               "Date: April 23, 2025  Company Secretary")
    r = read(wrapped)
    check(r.value == date(2025, 4, 23),
          f"'dated <instrument's date>' at a line start is not this document's date ({r.value})")
    check(read("Date of Birth 7th August 1979 9th February 1973").value is None,
          "'Date of Birth' is not a declaration: the date must follow the colon at once")
    check(read("Date of first appointment on the Board May 8, 2024").value is None,
          "'Date of first appointment' is not a declaration either")
    check(read("Date: Friday, June 5, 2026").value is None,
          "a weekday before the date means this line is not a bare date declaration")
    check(read("Date: 2026.05.07 21:59:27 +05'30'").value is None,
          "a numeric-only date is not read: day-first and year-first are indistinguishable")
    check(read("Date: 28/01/2025").value is None, "nor is a slashed numeric date")
    check(read("Date: February 30, 2025").value is None,
          "a date that does not exist is not read, and is not corrected")

    # ── no date, and why ─────────────────────────────────────────────────────
    r = read("MINUTES OF THE PROCEEDINGS\nHELD ON __________ (date) 20_\nDate : ______ 20_.")
    check(r.value is None and r.why == NO_DECLARATION and r.conflicting == (),
          f"a specimen with blanks where its date would be has no date ({r.why[:40]}…)")
    check(r.unread == 1, f"…and the blank declaration is counted, not dropped ({r.unread})")
    check(read("Nothing here says a date.").why == NO_DECLARATION,
          "a document with no date line at all says so the same way")

    r = read("Date: November 4, 2025\nDate: 3 November 2025\nDate: 2025.11.03")
    check(r.value is None and r.conflicting == (date(2025, 11, 3), date(2025, 11, 4)),
          f"two different declared dates are a refusal, not a choice ({r.conflicting})")
    check("2025-11-03" in r.why and "2025-11-04" in r.why,
          f"…and the refusal names both dates ({r.why[:60]}…)")
    check(r.unread == 1, f"the unparsed third declaration is still counted ({r.unread})")

    r = read("Date: July 17, 2025\nDate: July 17, 2025 Company Secretary")
    check(r.value == date(2025, 7, 17) and r.conflicting == (),
          "the same date declared twice is one date, not a conflict")

    # ── the unresolved marker is never dropped ───────────────────────────────
    r = read("Date: April 21, 2026\nDate: 2026.04.21 10:00:00 +05'30'\nDate: 7")
    check(r.value == date(2026, 4, 21) and r.unread == 2,
          f"a date is read, and the declarations that could not be are reported ({r.unread})")

    # ── nothing is repaired ──────────────────────────────────────────────────
    ocr = "Date: 28 Janua ry 2025 Managing Director"
    r = read(ocr)
    check(r.value is None and r.unread == 1,
          "someone else's OCR damage is not repaired into a date; it is counted as unread")

    # ── every public corpus document, end to end ─────────────────────────────
    # The reader meets documents it did not author. Named here so a change of rule
    # shows up as a change to this list rather than as a silently different answer.
    from eval.prelabel.corpus import load_all
    readings = {d.doc_id: read(d.text) for d in load_all()}
    dated = {i: r.value.isoformat() for i, r in readings.items() if r.value}
    check(len(readings) == 29, f"29 public documents were read ({len(readings)})")
    check(dated == {
        "agm_notices/routemobile_20th_agm_notice_2024": "2024-07-19",
        "agm_notices/routemobile_21st_agm_notice_2025": "2025-07-17",
        "agm_notices/routemobile_22nd_agm_notice_2026": "2026-07-23",
        "agm_notices/tataelxsi_37th_agm_notice_2026": "2026-04-21",
        "agm_notices/tcpl_62nd_agm_notice_2025": "2025-04-23",
        "agm_notices/tcpl_63rd_agm_notice_2026": "2026-05-08",
        "board_outcomes/routemobile_outcome_board_meeting_2024-05-29": "2024-05-29",
        "board_outcomes/routemobile_outcome_board_meeting_2025-01-28": "2025-01-28",
        "board_outcomes/routemobile_outcome_board_meeting_2026-05-07": "2026-05-07",
    }, f"the 9 documents that declare a date, and the date each declares ({dated})")
    specimens = [i for i in readings if i.startswith("icsi_specimens/")]
    check(specimens and all(readings[i].value is None for i in specimens),
          "no ICSI specimen has a date: a specimen is undated by construction")
    two_dated = readings["board_outcomes/routemobile_outcome_board_meeting_2025-11-03"]
    check(two_dated.value is None and len(two_dated.conflicting) == 2,
          f"the filing that bears two dates is refused ({two_dated.conflicting})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
