"""Chunk a statute section on its OWN structure, not on a token window.

The model-development plan (docs/MODEL_DEVELOPMENT_PLAN.md §3.3) makes the case:
generic RAG splits text into fixed blocks (512 tokens, "tokens 4096-4608"); the
Companies Act carries its own index — section -> sub-section -> clause -> proviso
-> sub-clause — and a retrieval that returns "s.2(85)(i), the paid-up-capital
limb, with its proviso" beats one that returns an arbitrary window. The law's
structure is the retrieval's best feature and it is free.

This module turns a section's cleaned text into a list of `Chunk`s, each carrying
its structural PATH (e.g. "96(1)", "96/proviso[1]", "2(85)(i)"), its kind, its
character span into the source text, and a content hash. Nothing here retrieves
or embeds; it produces the units a retriever indexes and the E-gate grounds
against. It is deterministic, self-testing, and depends on nothing outside stdlib.

## What it splits on, and what it does not (yet)

It splits on the markers the Act actually uses at unit boundaries:
  * numeric sub-sections / definition-clauses   (1) (2) ... (85)
  * provisos                                     "Provided that", "Provided further/also that"
  * roman sub-clauses                            (i) (ii) ... (xii)

Lettered clauses (a)(b)(c) are a documented extension, deliberately deferred
(YAGNI): the obligations this serves today key on numeric sub-sections, provisos,
and the roman limbs of s.2(85) / s.135. A section with only lettered sub-units
still yields a correct single sub-section chunk; it is just not split finer. When
an obligation needs (a)/(b) granularity, add it here with a fixture, not before.

## Offsets are into the text you pass in

`chunk_section(section, text)` returns spans into `text` exactly as given, so the
caller controls canonicalisation. Pass the same cleaned text the witness-span /
E-gate layer uses, and a chunk's (start, end) is directly usable as a span.
`clean_html(raw)` is provided for the corpus's HTML `content` field, but the
chunker never cleans implicitly — that would hide which text the offsets index.
"""
from __future__ import annotations

import hashlib
import html as _html
import re
from dataclasses import dataclass

# ── chunk kinds ───────────────────────────────────────────────────────────────
CHAPEAU = "CHAPEAU"        # the lead-in before the first numbered unit ("In this Act...")
SUBSECTION = "SUBSECTION"  # a numeric top-level unit: s.96(1), or a definition clause s.2(85)
PROVISO = "PROVISO"        # "Provided that ..." — carried apart from what it qualifies
SUBCLAUSE = "SUBCLAUSE"    # a roman sub-unit: s.2(85)(i)

KINDS = (CHAPEAU, SUBSECTION, PROVISO, SUBCLAUSE)

# Roman sub-clause markers we recognise, longest-first so "(ii)" wins over "(i)".
_ROMAN = ("xii", "xi", "x", "ix", "viii", "vii", "vi", "v", "iv", "iii", "ii", "i")

# A numeric top-level marker at a line start: "(1)", "(85)". Anchored to line
# start (after optional spaces) so "section 133" or "(1)" inside prose does not
# split a unit.
_NUM_MARKER = re.compile(r"(?m)^[ \t]*\((\d+)\)")
# A proviso opener at a line start.
_PROVISO = re.compile(r"(?m)^[ \t]*Provided\b")
# A roman marker at a line start.
_ROMAN_MARKER = re.compile(
    r"(?m)^[ \t]*\((" + "|".join(_ROMAN) + r")\)")


@dataclass(frozen=True)
class Chunk:
    section: str          # "96"
    path: str             # "96(1)", "96/proviso[1]", "2(85)(i)"
    kind: str             # one of KINDS
    text: str
    start: int            # offset into the source text passed to chunk_section
    end: int
    sha256: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.kind!r} is not a chunk kind")
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"bad span [{self.start}, {self.end}) for {self.path}")


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_html(raw: str) -> str:
    """Strip the corpus HTML to text while KEEPING line breaks as structure.

    Newlines are load-bearing here: sub-section and proviso markers are anchored
    to line starts, so collapsing newlines would merge units. Spaces and tabs are
    collapsed; blank lines are preserved as single newlines.
    """
    if not raw:
        return ""
    # <br>, <p>, </div> etc. become newlines so run-together HTML keeps unit breaks.
    s = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", raw)
    s = re.sub(r"(?i)</\s*(p|div|li|tr)\s*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s)      # trim spaces around newlines
    s = re.sub(r"\n{2,}", "\n", s)               # collapse blank runs to one newline
    return s.strip()


def _slice(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _split_within(section: str, subsection_no: str, text: str,
                  base: int) -> list[Chunk]:
    """Split one numeric unit's body into its head, roman sub-clauses and provisos.

    `text` is the unit body; `base` is its absolute offset in the whole section so
    the returned spans are absolute. Order in the source is preserved: markers are
    collected, sorted by position, and the text between markers is attributed to
    the marker that opens it. The text before the first sub-marker is the
    sub-section's own chunk.
    """
    marks: list[tuple[int, str, str]] = []   # (pos, kind, label)
    for m in _ROMAN_MARKER.finditer(text):
        marks.append((m.start(), SUBCLAUSE, m.group(1)))
    prov_k = 0
    for m in _PROVISO.finditer(text):
        prov_k += 1
        marks.append((m.start(), PROVISO, str(prov_k)))
    marks.sort(key=lambda t: t[0])

    chunks: list[Chunk] = []
    head_end = marks[0][0] if marks else len(text)
    head = _slice(text, 0, head_end)
    if head:
        chunks.append(Chunk(section, f"{section}({subsection_no})", SUBSECTION,
                            head, base, base + head_end, _sha(head)))
    for i, (pos, kind, label) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = _slice(text, pos, nxt)
        if not body:
            continue
        if kind == SUBCLAUSE:
            path = f"{section}({subsection_no})({label})"
        else:
            path = f"{section}({subsection_no})/proviso[{label}]"
        chunks.append(Chunk(section, path, kind, body,
                            base + pos, base + nxt, _sha(body)))
    return chunks


def chunk_section(section: str, text: str) -> list[Chunk]:
    """Structural chunks for one section. Spans index into `text` as given.

    A section with no numeric markers yields a single SUBSECTION-less body as one
    CHAPEAU chunk — better than returning nothing, and honest about the lack of
    structure. A section that is all one sub-section (no (1)) is treated the same.
    """
    if not text or not text.strip():
        return []

    marks = list(_NUM_MARKER.finditer(text))
    chunks: list[Chunk] = []

    # Lead-in before the first numeric marker (e.g. s.2 "In this Act...").
    lead_end = marks[0].start() if marks else len(text)
    lead = _slice(text, 0, lead_end)
    if lead:
        # If there are no numeric markers at all, the whole thing is one unit; we
        # still record it, as a chapeau, so the section is representable.
        chunks.append(Chunk(section, f"{section}/chapeau", CHAPEAU, lead,
                            0, lead_end, _sha(lead)))

    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        number = m.group(1)
        # Body starts after the "(N)" marker token so the marker is not repeated
        # inside the sub-section text.
        body_start = m.end()
        chunks.extend(_split_within(section, number, text[body_start:end],
                                    base=body_start))
    return chunks


def paths(chunks: list[Chunk]) -> list[str]:
    return [c.path for c in chunks]


def by_path(chunks: list[Chunk], path: str) -> Chunk | None:
    for c in chunks:
        if c.path == path:
            return c
    return None


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("structural_chunk")

    # ── clean_html keeps unit breaks ────────────────────────────────────────
    raw = "<p>(1) first thing.</p><br/>Provided that a caveat applies:"
    cleaned = clean_html(raw)
    check("\n" in cleaned, "clean_html preserves line breaks as structure")
    check("<" not in cleaned, "clean_html strips tags")

    # ── s.96: one sub-section, two provisos ─────────────────────────────────
    s96 = ("(1) Every company other than a One Person Company shall in each year hold "
           "a general meeting as its annual general meeting, and not more than fifteen "
           "months shall elapse between one and the next:\n"
           "Provided that in case of the first annual general meeting, it shall be held "
           "within nine months from the closing of the first financial year:\n"
           "Provided further that the Registrar may, for special reason, extend the time.")
    c96 = chunk_section("96", s96)
    p96 = paths(c96)
    check("96(1)" in p96, f"s.96(1) is a sub-section chunk ({p96})")
    check("96(1)/proviso[1]" in p96 and "96(1)/proviso[2]" in p96,
          "both provisos are separate chunks")
    prov1 = by_path(c96, "96(1)/proviso[1]")
    check(prov1 and prov1.kind == PROVISO and "nine months" in prov1.text,
          "proviso[1] carries the nine-month limb")
    check("fifteen months" in by_path(c96, "96(1)").text,
          "the sub-section head keeps its own operative text, not the proviso's")

    # Spans are real: each chunk's text matches the source at its offset.
    for c in c96:
        span_text = re.sub(r"\s+", " ", s96[c.start:c.end]).strip()
        if span_text != c.text:
            check(False, f"span mismatch for {c.path}")
            break
    else:
        check(True, "every chunk's (start,end) span reproduces its text")

    # ── s.2(85): numeric definition-clause with roman sub-clauses ───────────
    s2 = ("In this Act, unless the context otherwise requires,--\n"
          "(84) \"share\" means a share in the share capital of a company;\n"
          "(85) \"small company\" means a company, other than a public company,--\n"
          "(i) paid-up share capital of which does not exceed fifty lakh rupees or such "
          "higher amount as may be prescribed which shall not be more than ten crore rupees; and\n"
          "(ii) turnover of which does not exceed two crore rupees or such higher amount as "
          "may be prescribed which shall not be more than one hundred crore rupees:\n"
          "Provided that nothing in this clause shall apply to a holding company;\n"
          "(86) \"subsidiary company\" means a company in which the holding company controls;")
    c2 = chunk_section("2", s2)
    p2 = paths(c2)
    check("2/chapeau" in p2, "the 'In this Act' lead-in is a chapeau chunk")
    check("2(84)" in p2 and "2(85)" in p2 and "2(86)" in p2,
          f"each definition clause is its own numeric chunk ({[x for x in p2 if x.startswith('2(')][:6]})")
    check("2(85)(i)" in p2 and "2(85)(ii)" in p2,
          "s.2(85) splits into its (i) capital and (ii) turnover limbs")
    limb_i = by_path(c2, "2(85)(i)")
    check(limb_i and "fifty lakh" in limb_i.text and "turnover" not in limb_i.text,
          "the (i) limb is the capital limb only, not the turnover limb")
    limb_ii = by_path(c2, "2(85)(ii)")
    check(limb_ii and "two crore" in limb_ii.text,
          "the (ii) limb is the turnover limb")
    check("2(85)/proviso[1]" in p2,
          "the proviso under (85) is captured, attached to (85) not (86)")
    prov = by_path(c2, "2(85)/proviso[1]")
    check(prov and "holding company" in prov.text, "...and carries the holding-company carve-out")
    # (85) head must not swallow (86)
    head85 = by_path(c2, "2(85)")
    check(head85 and "subsidiary" not in head85.text,
          "the (85) chunk does not bleed into (86)")

    # ── content hashing + spans are consistent and unique-ish ───────────────
    check(all(c.sha256.startswith("sha256:") for c in c2),
          "every chunk carries a content hash")
    check(all(0 <= c.start <= c.end <= len(s2) for c in c2),
          "every span lies within the source text")

    # ── degenerate inputs ───────────────────────────────────────────────────
    check(chunk_section("x", "") == [], "empty text yields no chunks")
    solo = chunk_section("5", "This section has no numbered sub-units at all.")
    check(len(solo) == 1 and solo[0].kind == CHAPEAU,
          "an unmarked section yields one chapeau chunk, not nothing")

    # ── a bad chunk cannot be constructed ───────────────────────────────────
    try:
        Chunk("9", "9(1)", "NONSENSE", "x", 0, 1, _sha("x"))
        check(False, "an invalid kind is rejected")
    except ValueError:
        check(True, "an invalid chunk kind is rejected at construction")
    try:
        Chunk("9", "9(1)", SUBSECTION, "x", 5, 2, _sha("x"))
        check(False, "an inverted span is rejected")
    except ValueError:
        check(True, "an inverted span is rejected at construction")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
