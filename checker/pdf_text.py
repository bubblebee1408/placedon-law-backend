"""
Extract text from a PDF using only the standard library.

Why this exists rather than shelling out to pdftotext: the acquisition guard called the official
eGazette copy of the Meetings of Board Rules CORRUPT_OR_UNREADABLE, and the document was fine --
poppler simply is not installed on this machine. A guard that reports a property of the toolchain
as a property of the evidence is worse than no guard, because the failure is invisible and reads
as a fact about the law.

The hard part is that gazette PDFs embed subset fonts whose character codes mean nothing on their
own: pulling the string literals out of the content stream yields noise like '! " # $'. The codes
only become text through the font's /ToUnicode CMap. This module parses those CMaps and applies
them, which is the difference between reading a gazette and guessing at one.

Scope: text extraction for identity checks. It is not a general PDF renderer -- no layout, no
column detection, no OCR. An image-only scan yields nothing, and callers must treat empty output
as "cannot read", never as "document is empty".

Run: python3 checker/pdf_text.py
"""
from __future__ import annotations

import re
import zlib
from pathlib import Path

__all__ = ["extract_text", "extract_pages", "has_extractable_text"]

# Scan streams globally rather than walking obj...endobj. Object bodies hold binary data that can
# contain the literal "endobj", so boundary-parsing silently drops most streams -- an early
# version of this file extracted 3 characters from a 22-page gazette for exactly that reason.
_STREAM = re.compile(rb"stream\r?\n?(.*?)endstream", re.S)
_BFCHAR = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_BFRANGE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_HEX = re.compile(rb"<([0-9A-Fa-f]+)>")
# A show-text operator: (lit) Tj  or  [(a) -20 (b)] TJ
_SHOW = re.compile(rb"(\((?:\\.|[^\\()])*\)|\[(?:[^\]\\]|\\.)*\])\s*(Tj|TJ)", re.S)
_LIT = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
_ESC = re.compile(rb"\\([nrtbf()\\]|[0-7]{1,3})")
_ESCMAP = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
           b"(": b"(", b")": b")", b"\\": b"\\"}


def _unescape(raw: bytes) -> bytes:
    def sub(m: re.Match) -> bytes:
        g = m.group(1)
        if g in _ESCMAP:
            return _ESCMAP[g]
        return bytes([int(g, 8) & 0xFF])
    return _ESC.sub(sub, raw)


def _inflate(chunk: bytes) -> bytes:
    for attempt in (chunk, chunk.lstrip(b"\r\n")):
        try:
            return zlib.decompress(attempt)
        except zlib.error:
            continue
    try:                                   # truncated streams still yield a usable prefix
        return zlib.decompressobj().decompress(chunk)
    except zlib.error:
        return b""


def _parse_cmap(data: bytes) -> dict[int, str]:
    """Character code -> unicode, from a /ToUnicode CMap.

    Both forms matter: bfchar lists codes one by one, bfrange gives a span. A range's destination
    may itself be a list, which is why the array form is handled rather than assumed contiguous.
    """
    out: dict[int, str] = {}

    def decode(h: bytes) -> str:
        raw = bytes.fromhex(h.decode("ascii"))
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            return raw.decode("latin-1", "replace")

    for block in _BFCHAR.findall(data):
        toks = _HEX.findall(block)
        for i in range(0, len(toks) - 1, 2):
            out[int(toks[i], 16)] = decode(toks[i + 1])

    for block in _BFRANGE.findall(data):
        for m in re.finditer(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[.*?\]|<[0-9A-Fa-f]+>)",
                             block, re.S):
            lo, hi, dst = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
            if dst.startswith(b"["):
                for off, h in enumerate(_HEX.findall(dst)):
                    out[lo + off] = decode(h)
            else:
                base = _HEX.match(dst).group(1)
                start = int(base, 16)
                width = len(base) // 2
                for off in range(hi - lo + 1):
                    v = (start + off).to_bytes(width, "big")
                    try:
                        out[lo + off] = v.decode("utf-16-be")
                    except UnicodeDecodeError:
                        out[lo + off] = v.decode("latin-1", "replace")
    return out


def _streams(data: bytes) -> list[bytes]:
    """Every stream in the file, inflated where possible."""
    out = []
    for raw in _STREAM.findall(data):
        blob = _inflate(raw)
        out.append(blob if blob else raw)
    return out


def _cmaps(data: bytes) -> dict[int, str]:
    """Every ToUnicode mapping in the file, merged.

    Merging rather than tracking which font is current is a deliberate simplification: identity
    checks need the words, not the typography. It fails only where two subset fonts assign
    different meanings to the same code, which shows up as a few wrong characters, not silence.
    """
    merged: dict[int, str] = {}
    for blob in _streams(data):
        if b"beginbfchar" in blob or b"beginbfrange" in blob:
            merged.update(_parse_cmap(blob))
    return merged


def _content_streams(data: bytes) -> list[bytes]:
    return [b for b in _streams(data) if b"Tj" in b or b"TJ" in b]


def _decode(lit: bytes, cmap: dict[int, str]) -> str:
    raw = _unescape(lit[1:-1])
    if not cmap:
        return raw.decode("latin-1", "replace")
    # Subset fonts here are single-byte; try that first and fall back to raw bytes for codes the
    # CMap does not cover, so partial coverage degrades instead of blanking the line.
    return "".join(cmap.get(b, chr(b) if 32 <= b < 127 else "") for b in raw)


_COMMON = frozenset(
    "the of and to in for or be shall a an is are as by with on that this such any may not "
    "company board rules act section meeting director powers government india".split())


def _englishness(text: str) -> int:
    """How much of this reads as English. The tie-breaker between two renderings."""
    return sum(1 for w in re.findall(r"[A-Za-z]{2,}", text.lower()) if w in _COMMON)


def _render_stream(stream: bytes, cmap: dict[int, str]) -> str:
    parts: list[str] = []
    for m in _SHOW.finditer(stream):
        for lit in _LIT.findall(m.group(1)):
            parts.append(_decode(lit, cmap))
        parts.append(" ")
    return re.sub(r"[ \t]{2,}", " ", "".join(parts))


def _render(data: bytes, cmap: dict[int, str], max_chars: int) -> str:
    parts: list[str] = []
    for stream in _content_streams(data):
        for m in _SHOW.finditer(stream):
            for lit in _LIT.findall(m.group(1)):
                parts.append(_decode(lit, cmap))
            parts.append(" ")
        parts.append("\n")
        if sum(len(p) for p in parts) > max_chars:
            break
    return re.sub(r"[ \t]{2,}", " ", "".join(parts))


def extract_text(path: str | Path, *, max_chars: int = 400_000) -> str:
    """Best-effort text of the PDF. Empty means 'could not read', never 'document is empty'.

    Two renderings are produced and the more English one wins. Applying a CMap is NOT always an
    improvement: this gazette's Latin body text uses standard encoding with no ToUnicode, while its
    small CMaps belong to the Devanagari and symbol fonts. Forcing every code through the merged
    map turned clean prose into noise -- 1008 recognisable words became 0. Which rendering is right
    is a property of the file, so it is measured rather than assumed.
    """
    data = Path(path).read_bytes()
    raw = _render(data, {}, max_chars)
    cmap = _cmaps(data)
    if not cmap:
        return raw
    mapped = _render(data, cmap, max_chars)
    return mapped if _englishness(mapped) > _englishness(raw) else raw


_OBJ_HDR = re.compile(rb"(?m)^\s*(\d+)\s+(\d+)\s+obj\b")
_PAGE = re.compile(rb"/Type\s*/Page\b(?!s)")
_CONTENTS = re.compile(rb"/Contents\s+(\d+)\s+0\s+R")


def extract_pages(path: str | Path) -> list[str]:
    """RETIRED 2026-09-17 — it was wrong, quietly, on 13 of 14 corpus documents.

    Use `checker.pdf_pages.extract_pages`. This function is kept as a raising guard
    rather than deleted, so that any caller resurrected from an old branch fails
    loudly instead of re-acquiring the defect.

    It located pages by regexing RAW FILE BYTES for `/Type/Page`. In PDF 1.5+ the
    page objects and the cross-reference table live inside zlib-deflated object
    streams (`/Type/ObjStm`) and cross-reference streams (`/Type/XRef`), which no
    byte regex can see into. Measured before retirement:

        icsi_gn_board.pdf      169 real pages -> returned   1
        icsi_gn_general.pdf    179 real pages -> returned   0
        route_agm_2024.pdf      22 real pages -> returned  37   (stale revisions)

    A second, independent defect: `/Contents` was sought only in the 400 bytes
    FOLLOWING the `/Type/Page` match, but many writers emit it BEFORE. On
    sonata_agm_notice_29th_2024.pdf that lost the text of 17 of 18 pages while
    still reporting all 18 — a file with no object streams at all.

    Why this is a raise and not a fallback: an empty or short page list from a real
    gazette is indistinguishable downstream from "the document says nothing", and in
    a compliance engine that reads as *no obligation found*. This module's own
    docstring names the rule — a guard that reports a property of the toolchain as a
    property of the evidence is worse than no guard.

    `extract_text` (whole-document) is unaffected and still used; it was verified
    working on all 14 census documents.
    """
    raise NotImplementedError(
        "checker.pdf_text.extract_pages was retired on 2026-09-17: it silently "
        "returned wrong pages for PDF 1.5+ files (compressed object streams) and "
        "lost text when /Contents preceded /Type/Page. "
        "Use checker.pdf_pages.extract_pages instead. "
        "See docs/D002_CLOSURE_REPORT_2026_09_17.md."
    )


def has_extractable_text(path: str | Path, *, min_words: int = 30) -> bool:
    """Whether enough real words came out to judge the document's identity."""
    words = re.findall(r"[A-Za-z]{3,}", extract_text(path))
    return len(words) >= min_words


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    check(_unescape(rb"a\(b\)c") == b"a(b)c", "escaped parens unescape")
    check(_unescape(rb"x\101y") == b"xAy", "octal escape decodes")
    check(_parse_cmap(b"beginbfchar <20> <0041> endbfchar") == {0x20: "A"}, "bfchar maps a code")
    r = _parse_cmap(b"beginbfrange <20> <22> <0041> endbfrange")
    check(r == {0x20: "A", 0x21: "B", 0x22: "C"}, "bfrange expands contiguously")
    r2 = _parse_cmap(b"beginbfrange <20> <21> [<0058> <005A>] endbfrange")
    check(r2 == {0x20: "X", 0x21: "Z"}, "bfrange with an array destination")

    check(_decode(b"(ABC)", {}) == "ABC", "no cmap falls back to literal bytes")
    check(_decode(b"(!\")", {0x21: "H", 0x22: "i"}) == "Hi", "cmap rewrites subset codes")
    check(_decode(b"(!?)", {0x21: "H"}) == "H?", "codes absent from the cmap degrade, not blank")

    check(_englishness("the company shall of and") > _englishness("qx zk pv"),
          "englishness separates prose from noise")

    # The real gazette, if it has been acquired. Guards the regression that mattered: a merged
    # CMap destroyed this document's text, and the naive reading was the correct one.
    # Page extraction moved to checker/pdf_pages.py on 2026-09-17 (D-002). The page
    # assertions that used to live here now run there, against fixtures that can
    # actually exhibit the defect -- the old fixture was PDF 1.4 with no object
    # streams, i.e. structurally immune, which is why the bug survived 163 suites.
    try:
        extract_pages("/dev/null")
        check(False, "the retired page reader must refuse to run")
    except NotImplementedError as exc:
        check("pdf_pages" in str(exc), "the retired page reader names its replacement")

    stored = Path(__file__).resolve().parent.parent / \
        "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
    if stored.is_file():
        # Whole-document extraction is the half that was never broken; keep guarding it.
        t = extract_text(stored)
        check("Meetings of Board" in t, "whole-document text carries the title")
        check(_englishness(t) > 500, "whole-document text reads as prose")
    else:
        print("[SKIP] stored Rules PDF not present")

    gaz = Path.home() / "Downloads/placedon-review/egazette_159201_31mar2014.pdf"
    if gaz.is_file():
        t = extract_text(gaz)
        check("Meetings of Board" in t, "the acquired gazette's title is readable")
        check(_englishness(t) > 500, f"gazette reads as prose ({_englishness(t)} common words)")
        check(has_extractable_text(gaz), "gazette reports as extractable")
    else:
        print("[SKIP] gazette fixture not present")

    missing = Path("/tmp/definitely-not-here-9x.pdf")
    try:
        extract_text(missing); check(False, "a missing file must raise")
    except OSError:
        check(True, "a missing file raises rather than returning ''")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
