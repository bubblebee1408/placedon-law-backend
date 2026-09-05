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
    """Text per page, in document order.

    Page provenance is not decoration here: a legal record has to say where in the source it came
    from, so a reviewer can open the gazette at that page and check it. Content streams are not
    1:1 with pages (22 pages, 25 text-bearing streams in this gazette), so the /Type/Page objects
    and their /Contents references are followed rather than guessed at by position.

    Returns [] when the page tree cannot be read; callers must not mistake that for a blank
    document.
    """
    data = Path(path).read_bytes()
    bodies: dict[int, bytes] = {}
    starts = [(int(m.group(1)), m.end()) for m in _OBJ_HDR.finditer(data)]
    for i, (num, off) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(data)
        bodies[num] = data[off:end]

    cmap = _cmaps(data)
    pages: list[str] = []
    for m in _PAGE.finditer(data):
        ref = _CONTENTS.search(data[m.start():m.start() + 400])
        if not ref:
            pages.append("")
            continue
        body = bodies.get(int(ref.group(1)), b"")
        sm = _STREAM.search(body)
        blob = _inflate(sm.group(1)) if sm else b""
        raw = _render_stream(blob, {})
        mapped = _render_stream(blob, cmap) if cmap else ""
        pages.append(mapped if _englishness(mapped) > _englishness(raw) else raw)
    return pages


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
    stored = Path(__file__).resolve().parent.parent / \
        "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
    if stored.is_file():
        pg = extract_pages(stored)
        check(len(pg) == 22, f"the Rules gazette reports 22 pages (got {len(pg)})")
        check(sum(1 for p in pg if p.strip()) >= 20, "at least 20 pages carry text")
        joined = " ".join(pg)
        check("Meetings of Board" in joined, "page text carries the title")
        check(_englishness(joined) > 500, "page text reads as prose")
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
