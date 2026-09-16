"""Run an instrument backwards across a folder — the query a practitioner has.

`objection_sim` O-05, from the practising CS, and she drew the line herself:

    "My WhatsApp group catches the change. What it does not do is tell me which
    of my sixty-three companies is affected. Can your tool run a notification
    BACKWARDS across two thousand documents on my server, or do I open each Word
    file one by one like a clerk?"

Every existing surface here answers "given this document, what changed". This
answers the inverse: **given this change, which documents.** It is the same data
read the other way, and it is the difference between a demonstration and a tool.

## What the sweep may and may not conclude

It knows two things about a document without reading it: its date, and whether
that date falls inside the window the instrument superseded. That is enough to
narrow two thousand files to a few dozen, which is the whole value. It is NOT
enough to say a document is wrong.

So the verdicts separate what we established from what we merely suspect:

    CITES_SUPERSEDED   dated in the window AND the text carries the superseded
                       figure or provision. Read this one first.
    IN_WINDOW          dated in the window. It MAY rely on the moved position;
                       nobody has looked. This is a queue, not a finding.
    OUT_OF_WINDOW      dated outside it. The instrument does not reach it.
    UNDATED            no date could be established. REFUSED, never skipped.
    UNREADABLE         the file could not be read. Also refused, also listed.

**A limit worth stating.** Where several dates all fall INSIDE the window, the
sweep does not know which is the document's own, and does not need to: the verdict
is the same either way. It only refuses when the candidates straddle the boundary,
because that is the only case where the choice changes the answer. A document
placed in the window on a date that is not really its own is still a document worth
reading, so the error is bounded.

`IN_WINDOW` is deliberately not called "affected". A document dated in the window
that never mentions capital at all is in the window and unaffected, and a verdict
that said otherwise would send a sole practitioner to read sixty files for
nothing — which is how a tool gets switched off in week two.

## Nothing is dropped

A file we could not open and a document we could not date both appear in the
output with a reason. `coverage.py` holds the same line for obligations: silence
about a thing is not a finding about it. A sweep that quietly skipped the eleven
files it failed to parse would report a clean result over its own blind spot.

Run: python3 checker/sweep.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _field
from datetime import date
from pathlib import Path

from checker import currency

# ── verdicts ─────────────────────────────────────────────────────────────────
CITES_SUPERSEDED = "CITES_SUPERSEDED"
IN_WINDOW = "IN_WINDOW"
OUT_OF_WINDOW = "OUT_OF_WINDOW"
UNDATED = "UNDATED"
AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
UNREADABLE = "UNREADABLE"

# Ordered most-urgent first. Used to sort the export, and to decide the headline.
PRIORITY = (CITES_SUPERSEDED, IN_WINDOW, AMBIGUOUS_DATE, UNDATED, UNREADABLE,
            OUT_OF_WINDOW)

# The two that need a human before anything is relied on.
NEEDS_REVIEW = (CITES_SUPERSEDED, IN_WINDOW)
# The two the sweep could not decide at all. Never silently excluded.
COULD_NOT_DECIDE = (AMBIGUOUS_DATE, UNDATED, UNREADABLE)


class SweepRefused(ValueError):
    """The sweep cannot run, and running it anyway would produce a false clean."""


@dataclass(frozen=True)
class Document:
    """One file in the folder. `date` is what everything turns on."""
    doc_id: str
    date: date | None = None
    text: str = ""
    unreadable_reason: str = ""
    # Every date found, not just the first. A board-outcome letter opens with the
    # quarter end and names the meeting date pages later, so "first date wins"
    # reads the wrong one -- measured on a real filed document in corpus/testdocs.
    candidates: tuple[date, ...] = _field(default_factory=tuple)

    @property
    def usable(self) -> bool:
        return self.date is not None and not self.unreadable_reason


@dataclass(frozen=True)
class Window:
    """The period the superseded instrument governed."""
    instrument: str            # the NEW instrument that moved things
    superseded: str            # the one it replaced
    governed_from: date        # when the superseded instrument took effect
    governed_to: date          # its last day -- the day before the new one
    obligations: tuple[str, ...] = ()
    # Strings that, appearing in a document, show it engaging the moved position.
    markers: tuple[str, ...] = ()

    def covers(self, d: date) -> bool:
        return self.governed_from <= d <= self.governed_to


@dataclass(frozen=True)
class Hit:
    doc_id: str
    verdict: str
    reason: str
    doc_date: date | None = None
    matched: tuple[str, ...] = _field(default_factory=tuple)

    @property
    def needs_review(self) -> bool:
        return self.verdict in NEEDS_REVIEW


@dataclass(frozen=True)
class Result:
    window: Window
    hits: tuple[Hit, ...]

    def by_verdict(self, verdict: str) -> tuple[Hit, ...]:
        return tuple(h for h in self.hits if h.verdict == verdict)

    @property
    def review_queue(self) -> tuple[Hit, ...]:
        """Sorted most urgent first. This is the thing she exports."""
        return tuple(sorted((h for h in self.hits if h.needs_review),
                            key=lambda h: (PRIORITY.index(h.verdict),
                                           h.doc_date or date.min)))

    @property
    def undecided(self) -> tuple[Hit, ...]:
        return tuple(h for h in self.hits if h.verdict in COULD_NOT_DECIDE)

    def headline(self) -> str:
        cites = len(self.by_verdict(CITES_SUPERSEDED))
        window = len(self.by_verdict(IN_WINDOW))
        undecided = len(self.undecided)
        parts = []
        if cites:
            parts.append(f"{cites} cite the superseded position")
        if window:
            parts.append(f"{window} fall in the window and were not read")
        if not parts:
            parts.append("none fall in the window")
        head = f"{len(self.hits)} documents swept: " + "; ".join(parts) + "."
        if undecided:
            # Never let the count of decided documents stand alone. The sweep's
            # own blind spot is part of its result.
            head += (f" {undecided} could not be decided at all and are listed "
                     f"separately -- they are not clear, they are unexamined.")
        return head

    def to_json(self) -> dict:
        return {
            "instrument": self.window.instrument,
            "superseded": self.window.superseded,
            "window": [self.window.governed_from.isoformat(),
                       self.window.governed_to.isoformat()],
            "obligations": list(self.window.obligations),
            "headline": self.headline(),
            "counts": {v: len(self.by_verdict(v)) for v in PRIORITY},
            "review_queue": [{"doc_id": h.doc_id, "verdict": h.verdict,
                              "date": h.doc_date.isoformat() if h.doc_date else None,
                              "reason": h.reason, "matched": list(h.matched)}
                             for h in self.review_queue],
            "could_not_decide": [{"doc_id": h.doc_id, "verdict": h.verdict,
                                  "reason": h.reason} for h in self.undecided],
            "establishes_defect": False,
            "no_model": True,
        }


def sweep(window: Window, documents, *, as_of: date | None = None) -> Result:
    """Which of these documents does this instrument reach?"""
    if window.governed_to < window.governed_from:
        raise SweepRefused(
            f"{window.instrument}: the superseded window ends "
            f"({window.governed_to}) before it begins ({window.governed_from}). "
            f"A sweep on an inverted window would return nothing and read as a "
            f"clean result.")
    if as_of is not None and window.governed_from > as_of:
        raise SweepRefused(
            f"{window.instrument}: its window begins {window.governed_from}, "
            f"after the date being swept as of ({as_of}).")

    hits = []
    for d in documents:
        if d.unreadable_reason:
            hits.append(Hit(d.doc_id, UNREADABLE, d.unreadable_reason))
            continue
        if d.date is None:
            hits.append(Hit(
                d.doc_id, UNDATED,
                "no document date could be established; the sweep turns entirely "
                "on the date, and guessing today would place every old document "
                "outside the window"))
            continue
        # A document whose candidate dates fall on BOTH sides of the boundary
        # cannot be placed by date alone, and picking one would be a coin toss
        # wearing a citation.
        cands = d.candidates or ((d.date,) if d.date else ())
        if len(set(cands)) > 1 and any(window.covers(c) for c in cands) \
                and not all(window.covers(c) for c in cands):
            inside = sorted(c for c in set(cands) if window.covers(c))
            outside = sorted(c for c in set(cands) if not window.covers(c))
            hits.append(Hit(
                d.doc_id, AMBIGUOUS_DATE,
                f"carries dates on both sides of the window boundary "
                f"(inside: {inside[0]}; outside: {outside[0]}). Which is the "
                f"document's own date cannot be settled without reading it",
                d.date, tuple(str(c) for c in sorted(set(cands)))))
            continue
        if not window.covers(d.date):
            side = "before" if d.date < window.governed_from else "after"
            hits.append(Hit(
                d.doc_id, OUT_OF_WINDOW,
                f"dated {d.date}, which is {side} the window "
                f"{window.governed_from}..{window.governed_to}", d.date))
            continue

        matched = tuple(m for m in window.markers
                        if m.lower() in (d.text or "").lower())
        if matched:
            hits.append(Hit(
                d.doc_id, CITES_SUPERSEDED,
                f"dated {d.date}, inside the window, and the text carries the "
                f"superseded position", d.date, matched))
        else:
            hits.append(Hit(
                d.doc_id, IN_WINDOW,
                f"dated {d.date}, inside the window. Nobody has read it: it may "
                f"rely on the moved position or may not mention it at all",
                d.date))
    return Result(window, tuple(hits))


# ── building a window from the engine, rather than by hand ───────────────────

def window_for(instrument_fragment: str, *, superseded: str, governed_from: date,
               governed_to: date, markers: tuple[str, ...] = ()) -> Window:
    """A window whose obligation list comes from currency, not from memory.

    `currency.affected_by` is the reverse index the law-change monitor already
    uses. Reading it here means a sweep cannot claim to touch obligations the
    engine does not agree are touched.
    """
    obligations = tuple(currency.affected_by(instrument_fragment))
    if not obligations:
        raise SweepRefused(
            f"no obligation in the register is moved by {instrument_fragment!r}. "
            f"Sweeping for an instrument that touches nothing would return an "
            f"empty queue that reads like an all-clear.")
    return Window(instrument_fragment, superseded, governed_from, governed_to,
                  obligations, markers)


# ── the thin file adapter; the sweep itself stays pure ───────────────────────

_DATE_PATTERNS = (
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?"
               r"(January|February|March|April|May|June|July|August|September|"
               r"October|November|December),?\s+(\d{4})\b", re.I),
)
_MONTHS = {m: i for i, m in enumerate(
    ("january february march april may june july august september october "
     "november december").split(), 1)}


def dates_in(text: str) -> tuple[date, ...]:
    """Every date the text states, in order of appearance, de-duplicated.

    `date_in` returns the first, which is what a single-date document needs. But
    a board-outcome letter opens with "quarter ended 31 December 2024" and states
    the meeting date further down, so the first date is routinely the wrong one.
    Collecting them all lets the sweep REFUSE when they straddle a boundary
    instead of guessing.
    """
    found: list[date] = []
    for m in _DATE_PATTERNS[0].finditer(text or ""):
        try:
            d = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            continue
        if d not in found:
            found.append(d)
    for m in _DATE_PATTERNS[1].finditer(text or ""):
        try:
            d = date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        except (ValueError, KeyError):
            continue
        if d not in found:
            found.append(d)
    return tuple(found)


def date_in(text: str) -> date | None:
    """The date stated IN the document. Returns None rather than guessing.

    A resolution says when it was passed; a file's mtime says when somebody last
    touched it, which is a different fact and frequently a much later one. Only
    the stated date is used.
    """
    m = _DATE_PATTERNS[0].search(text or "")
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = _DATE_PATTERNS[1].search(text or "")
    if m:
        try:
            return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        except (ValueError, KeyError):
            return None
    return None


def documents_in(folder: Path, *, suffixes=(".txt", ".md", ".pdf")) -> list[Document]:
    """Read a folder into Documents. Every failure becomes a Document, not a skip.

    PDFs go through `checker.pdf_text`, which this repository already has and
    which the first version of this function ignored -- it reported 37 of 48 real
    documents as unreadable while the extractor sat one import away. A scanned
    PDF with no text layer still comes back UNREADABLE, correctly: an empty
    extraction is not an empty document.

    .docx is a zip and parsing it needs a dependency this repo does not have, so
    it is reported as unexamined. That is honest, and far better than silently
    ignoring the format the whole profession uses.
    """
    out = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in suffixes:
            out.append(Document(path.name, unreadable_reason=(
                f"{suffix or 'no extension'} is not readable without a new "
                f"dependency; this file was NOT examined")))
            continue
        try:
            if suffix == ".pdf":
                from checker.pdf_text import extract_text
                text = extract_text(path)
                if not (text or "").strip():
                    out.append(Document(path.name, unreadable_reason=(
                        "PDF has no extractable text layer (likely a scan); it "
                        "was NOT examined and needs OCR")))
                    continue
            else:
                text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError, ValueError) as e:
            out.append(Document(path.name, unreadable_reason=f"could not read: {e}"))
            continue
        cands = dates_in(text)
        out.append(Document(path.name, cands[0] if cands else None, text,
                            candidates=cands))
    return out


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("sweep")

    # The real case: G.S.R. 880(E) moved the small-company limits on 01-12-2025,
    # so everything drafted under 700(E) from 15-09-2022 to 30-11-2025 is in scope.
    w = window_for("G.S.R. 700(E)", superseded="G.S.R. 700(E)",
                   governed_from=date(2022, 9, 15), governed_to=date(2025, 11, 30),
                   markers=("4 crore", "4,00,00,000", "forty crore"))
    check(bool(w.obligations),
          f"the window's obligations come from currency.affected_by, not from "
          f"memory ({w.obligations})")

    docs = [
        Document("BR-2024-06.txt", date(2024, 6, 14),
                 "Resolved that the Company, being a small company with paid-up "
                 "capital not exceeding Rs 4 crore, ..."),
        Document("BR-2023-01.txt", date(2023, 1, 9),
                 "Resolved to approve the minutes of the previous meeting."),
        Document("BR-2026-02.txt", date(2026, 2, 2), "Resolved. Rs 4 crore."),
        Document("BR-2019-11.txt", date(2019, 11, 3), "Old resolution. Rs 4 crore."),
        Document("BR-undated.txt", None, "Resolved that the Company ..."),
        Document("BR-scan.docx", None, "", "docx needs a dependency; NOT examined"),
    ]
    r = sweep(w, docs, as_of=date(2026, 9, 13))

    # ── the narrowing, which is the whole value ──────────────────────────────
    check(r.by_verdict(CITES_SUPERSEDED)[0].doc_id == "BR-2024-06.txt",
          "a document in the window that carries the superseded figure is first "
          "in the queue")
    check(r.by_verdict(CITES_SUPERSEDED)[0].matched == ("4 crore",),
          "...and names the marker it matched, so she can see WHY it was flagged")
    check([h.doc_id for h in r.by_verdict(IN_WINDOW)] == ["BR-2023-01.txt"],
          "a document in the window that does not mention it is IN_WINDOW, not "
          "'affected' -- sending her to read it as a defect is how a tool gets "
          "switched off in week two")

    # ── the two the instrument does not reach ────────────────────────────────
    out = {h.doc_id for h in r.by_verdict(OUT_OF_WINDOW)}
    check(out == {"BR-2026-02.txt", "BR-2019-11.txt"},
          f"documents outside the window are excluded even when they carry the "
          f"figure ({out})")
    check(any("after the window" in h.reason for h in r.by_verdict(OUT_OF_WINDOW)),
          "...and the reason says which side, because a 2026 document mentioning "
          "Rs 4 crore is a different problem from a 2019 one")

    # ── nothing is dropped ───────────────────────────────────────────────────
    check({h.doc_id for h in r.undecided} == {"BR-undated.txt", "BR-scan.docx"},
          "an undated document and an unreadable file both appear in the result")
    check(len(r.hits) == len(docs),
          f"every document supplied appears in the output ({len(r.hits)}/{len(docs)})")
    check("they are not clear, they are unexamined" in r.headline(),
          f"...and the headline refuses to let the decided count stand alone: "
          f"{r.headline()}")

    # ── refusals that prevent a false clean ──────────────────────────────────
    try:
        sweep(Window("X", "Y", date(2025, 1, 1), date(2024, 1, 1)), docs)
        check(False, "an inverted window is refused")
    except SweepRefused as e:
        check("read as a clean result" in str(e),
              "an inverted window is refused -- it would return nothing and read "
              "as an all-clear")
    try:
        window_for("G.S.R. 9999(E)", superseded="x", governed_from=date(2020, 1, 1),
                   governed_to=date(2021, 1, 1))
        check(False, "an instrument touching nothing is refused")
    except SweepRefused as e:
        check("reads like an all-clear" in str(e),
              "sweeping for an instrument that moves no obligation is refused")

    # ── the defect a real corpus exposed, now refused ────────────────────────
    #
    # A board-outcome letter opens with "quarter ended 31 December 2024" and names
    # the meeting date, January 28 2025, pages later. The first version of this
    # module read the quarter end and called it the document date. Both happened
    # to fall inside the window so the verdict survived -- but it was right by
    # luck, and a boundary-straddling pair is the case where luck runs out.
    straddler = Document(
        "outcome.txt", date(2025, 11, 20),
        "Results for the quarter ended 30 November 2025. Board meeting held on "
        "the 3rd day of December, 2025.",
        candidates=(date(2025, 11, 30), date(2025, 12, 3)))
    r2 = sweep(w, [straddler], as_of=date(2026, 9, 13))
    check(r2.hits[0].verdict == AMBIGUOUS_DATE,
          "a document with dates on both sides of the boundary is REFUSED, not "
          "resolved by taking the first one")
    check("cannot be settled without reading it" in r2.hits[0].reason,
          "...and says why, naming a date from each side")
    check(r2.hits[0] in r2.undecided and r2.hits[0] not in r2.review_queue,
          "...and lands in could-not-decide, not in the read-these queue")

    same_side = Document("ok.txt", date(2024, 1, 1), "text",
                         candidates=(date(2024, 1, 1), date(2024, 3, 1)))
    check(sweep(w, [same_side]).hits[0].verdict != AMBIGUOUS_DATE,
          "...while several dates all INSIDE the window are not ambiguous -- the "
          "guard fires on the boundary, not on multiplicity")

    check(dates_in("quarter ended 2024-12-31. Meeting on the 28th day of "
                   "January, 2025.") == (date(2024, 12, 31), date(2025, 1, 28)),
          "dates_in collects every candidate, in order")

    # ── dates come from the document, never from the filesystem ──────────────
    check(date_in("passed on the 14th day of June, 2024") == date(2024, 6, 14),
          "an Indian-style stated date is read")
    check(date_in("dated 2024-06-14") == date(2024, 6, 14), "an ISO date is read")
    check(date_in("no date here at all") is None,
          "...and a document with no stated date returns None rather than a guess")
    check(date_in("the 31st day of February, 2024") is None,
          "an impossible date is None, not a silently-shifted one")

    # ── the export ───────────────────────────────────────────────────────────
    j = r.to_json()
    check(j["establishes_defect"] is False,
          "the export states that being in the queue is not a defect")
    check(len(j["review_queue"]) == 2 and j["review_queue"][0]["verdict"]
          == CITES_SUPERSEDED,
          "the queue is exportable and sorted most-urgent first")
    check(len(j["could_not_decide"]) == 2,
          "...and the undecided travel with it rather than being filtered out")

    # ── the file adapter reports what it cannot open ─────────────────────────
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "a.txt").write_text("Resolved on 2024-06-14. Rs 4 crore.")
        (p / "b.txt").write_text("No date in this one.")
        (p / "c.docx").write_bytes(b"PK\x03\x04 binary")
        got = documents_in(p)
    check(len(got) == 3, f"every file in the folder becomes a Document ({len(got)})")
    bad = [d for d in got if d.unreadable_reason]
    check(len(bad) == 1 and "NOT examined" in bad[0].unreadable_reason,
          "a .docx is reported as unexamined rather than skipped -- it is the "
          "format the whole profession uses and pretending otherwise is worse")
    check(any(d.date == date(2024, 6, 14) for d in got),
          "...and a readable file gets its stated date")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
