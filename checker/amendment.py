"""
Parse India Code amendment footnotes into structured records.

This is the component that does not exist anywhere else. India Code publishes, per section, a
footnote block whose grammar is regular:

    1. Subs. by Act 1 of 2018, s. 2 (w.e.f. 7-5-2018).
    2. Subs. by Act 31 of 2016, s. 255 and the Eleventh Schedule, for clause (23) (w.e.f. 15-11-2016).
    3. Ins. by S.O. 1894(E), dated 24th July, 2014.
    4. Ibid.

Marker numbers pair with inline `1 [ ... ]` spans in the section content, so marker -> span ->
effective date is recoverable. That is what makes point-in-time reconstruction derivable rather
than hand-curated.

Pure functions, no I/O. Run: python3 checker/amendment.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

Operation = Literal["substituted", "inserted", "omitted", "unknown"]

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# A footnote entry starts with "N." at a boundary.
_ENTRY = re.compile(r"(?:^|\s)(\d{1,3})\.\s+")
_OPS = (
    (re.compile(r"\bsubs(?:titut\w*)?\.?\b", re.I), "substituted"),
    (re.compile(r"\bins(?:ert\w*)?\.?\b", re.I), "inserted"),
    (re.compile(r"\bomit\w*\b", re.I), "omitted"),
)
# "(w.e.f. 7-5-2018)" / "(w.e.f. 15-11-2016)"
# India Code writes this inconsistently: "w.e.f. 7-5-2018", "w.e.f 9-2-2018" (no terminal dot),
# and "w.e.f. 2-11- 2018" (space inside the date). Tolerate all three. An impossible date such as
# "21-21-2020" still fails date() and stays undated - we do not repair a bad government source.
_WEF = re.compile(r"w\.?\s*e\.?\s*f\.?\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", re.I)
# "dated 24th July, 2014"
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
_DATED = re.compile(r"dated\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s*(\d{4})", re.I)
# Instruments
_ACT = re.compile(r"\bAct\s+(\d+)\s+of\s+(\d{4})", re.I)
_GSR = re.compile(r"\bG\.?\s?S\.?\s?R\.?\s*(\d+)\s*\(\s*E\s*\)", re.I)
_SO = re.compile(r"\bS\.?\s?O\.?\s*(\d+)\s*\(\s*E\s*\)", re.I)
_IBID = re.compile(r"\bibid\b", re.I)
# The Companies Act 2013 received assent in 2013. Anything outside this window is a source defect,
# not a real effective date. India Code itself carries at least one: section id 48977 reads
# "(w.e.f. 26-5-5017)" where the amending Act is Act 7 of 2017. We flag it. We never correct it —
# silently repairing a government source is the failure mode this product exists to prevent.
PLAUSIBLE_YEARS = (2013, 2040)
# Inline span markers in the real India Code HTML are superscripts: "<sup>1</sup>[ ... ]".
# The bare "1 [" form appears in plain-text renderings, so accept both.
_SPAN = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>\s*\[|(?<![\d>])(\d{1,3})\s*\[")


@dataclass(frozen=True)
class Amendment:
    marker: int
    operation: Operation
    instrument: str | None       # "Act 1 of 2018" | "S.O. 1894(E)" | "G.S.R. 13(E)"
    wef: date | None             # effective date, when stated
    raw: str                     # the verbatim footnote entry
    ibid: bool = False           # back-reference to the preceding citation
    wef_implausible: bool = False  # source date outside the Act's lifetime — see PLAUSIBLE_YEARS


def _clean(html: str) -> str:
    return _WS.sub(" ", _TAGS.sub(" ", html)).strip()


def _parse_wef(text: str) -> date | None:
    m = _WEF.search(text)
    if m:
        d, mo, y = (int(g) for g in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = _DATED.search(text)
    if m:
        d, mon, y = m.group(1), m.group(2).lower(), m.group(3)
        if mon in _MONTHS:
            try:
                return date(int(y), _MONTHS[mon], int(d))
            except ValueError:
                return None
    return None


def _parse_instrument(text: str) -> str | None:
    m = _ACT.search(text)
    if m:
        return f"Act {m.group(1)} of {m.group(2)}"
    m = _GSR.search(text)
    if m:
        return f"G.S.R. {m.group(1)}(E)"
    m = _SO.search(text)
    if m:
        return f"S.O. {m.group(1)}(E)"
    return None


def _parse_operation(text: str) -> Operation:
    # Order matters: "omitted" can co-occur with "subs." in compound entries; the leading verb wins.
    best: tuple[int, Operation] | None = None
    for pat, op in _OPS:
        m = pat.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), op)
    return best[1] if best else "unknown"


def parse_footnote(footnote_html: str) -> list[Amendment]:
    """Split a section's footnote block into one Amendment per numbered marker."""
    text = _clean(footnote_html)
    if not text:
        return []

    hits = list(_ENTRY.finditer(text))
    if not hits:
        return []

    out: list[Amendment] = []
    carry_instrument: str | None = None
    for i, m in enumerate(hits):
        start = m.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        is_ibid = bool(_IBID.search(body))
        instrument = _parse_instrument(body)
        if instrument:
            carry_instrument = instrument
        elif is_ibid:
            instrument = carry_instrument  # "Ibid." inherits the preceding citation
        wef = _parse_wef(body)
        implausible = wef is not None and not (PLAUSIBLE_YEARS[0] <= wef.year <= PLAUSIBLE_YEARS[1])
        out.append(Amendment(
            marker=int(m.group(1)),
            operation=_parse_operation(body),
            instrument=instrument,
            wef=wef,
            raw=body,
            ibid=is_ibid,
            wef_implausible=implausible,
        ))
    return out


def span_markers(content_html: str) -> list[int]:
    """Marker numbers that open an amended span in the section content."""
    seen, out = set(), []
    for m in _SPAN.finditer(content_html):
        n = int(m.group(1) or m.group(2))
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def coverage(content_html: str, footnote_html: str) -> tuple[int, int]:
    """(markers resolved to a footnote, markers found in content). Diagnostic for ingest quality."""
    marks = set(span_markers(content_html))
    notes = {a.marker for a in parse_footnote(footnote_html)}
    return len(marks & notes), len(marks)


# --- self-test against real India Code data ----------------------------------

REAL_S2 = ("""</br><hr style="border-top:1px solid #0778be"/>1. The <i>Explanation</i> subs. by """
           """Act 1 of 2018, s. 2 (w.e.f. 7-5-2018).</br><hr class="hr2"/> 2. Subs. by Act 31 of 2016, """
           """s. 255 and the Eleventh Schedule, for clause (23) (w.e.f. 15-11-2016).</br>"""
           """<hr class="hr2"/> 3. Subs. by Act 1 of 2018, s. 2, for clause (28) (w.e.f. 9-2-2018)."""
           """</br><hr class="hr2"/> 16. Ins. by S.O. 1894 (E), dated 24th July, 2014.""")

REAL_S3A = ("""</br><hr style="border-top:1px solid #0778be"/>1. Ins. by Act 1 of 2018, s. 3 """
            """(w.e.f. 9-2-2018).</br><hr class="hr2"/>""")

IBID_CASE = "1. Subs. by Act 29 of 2020, s. 2 (w.e.f. 22-1-2021). 2. Ibid., for clause (b)."


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"[PASS] {label}")
        else:
            fail += 1
            print(f"[FAIL] {label}")

    a = parse_footnote(REAL_S2)
    by = {x.marker: x for x in a}
    check(len(a) == 4, f"s.2: parsed 4 entries (got {len(a)})")
    check(by[1].operation == "substituted", "s.2 m1: substituted")
    check(by[1].instrument == "Act 1 of 2018", "s.2 m1: instrument Act 1 of 2018")
    check(by[1].wef == date(2018, 5, 7), "s.2 m1: w.e.f. 7-5-2018")
    check(by[2].instrument == "Act 31 of 2016", "s.2 m2: instrument Act 31 of 2016")
    check(by[2].wef == date(2016, 11, 15), "s.2 m2: w.e.f. 15-11-2016")
    check(by[3].wef == date(2018, 2, 9), "s.2 m3: w.e.f. 9-2-2018")
    check(by[16].operation == "inserted", "s.2 m16: inserted")
    check(by[16].instrument == "S.O. 1894(E)", "s.2 m16: gazette instrument S.O. 1894(E)")
    check(by[16].wef == date(2014, 7, 24), "s.2 m16: 'dated 24th July, 2014' parsed")

    b = parse_footnote(REAL_S3A)
    check(len(b) == 1 and b[0].operation == "inserted", "s.3A: single insertion")
    check(b[0].wef == date(2018, 2, 9), "s.3A: w.e.f. 9-2-2018")

    c = parse_footnote(IBID_CASE)
    check(c[1].ibid, "ibid: flagged")
    check(c[1].instrument == "Act 29 of 2020", "ibid: inherits preceding instrument")
    check(c[1].wef is None, "ibid: no own w.e.f., not fabricated")

    check(span_markers("text 1 [ amended ] more 2[ also ] and 1 [ again ]") == [1, 2],
          "span markers deduped in document order")
    check(span_markers("<sup>1</sup>[<i>Explanation.</i>--] and <sup>16</sup>[ x ]") == [1, 16],
          "span markers parsed from real <sup>N</sup>[ HTML")

    # India Code's own source defect, preserved and flagged rather than corrected.
    defect = parse_footnote("1. Ins. by Act 7 of 2017, s. 172 (w.e.f. 26-5-5017).")[0]
    check(defect.wef_implausible, "implausible source date flagged")
    check(defect.wef == date(5017, 5, 26), "implausible date preserved verbatim, not silently fixed")
    check(not parse_footnote(REAL_S3A)[0].wef_implausible, "genuine date not flagged")
    check(parse_footnote("") == [], "empty footnote yields no amendments, not a guess")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
