"""A contract, split into clauses by CODE, with the offsets that make a quote checkable.

PLAN_22 §6: "segment clauses (CODE, not a model)". The model's job downstream is to say
what a clause is; deciding where one starts is arithmetic over the document's own
numbering, and a model doing it would put a guess underneath every span the rest of the
pipeline treats as evidence.

## The invariant everything else rests on

    source[clause.start:clause.end] == clause.text

Exactly, for every clause, byte for byte. `quoted_span` verifies a model's quote by
finding it in the source; if a clause were normalised, de-hyphenated or re-wrapped on the
way through, every span offset computed against it would be wrong against the real
document, and the citation would point at the wrong words while looking correct. So
nothing here rewrites text. Splitting is choosing INDICES, never producing strings.

## What counts as the start of a clause

A line that opens with a decimal number (`1.`, `2.3`, `4.1.1`), a `Section`/`Article`
heading, or a short ALL-CAPS line -- the three ways commercial contracts actually mark
their own structure. Sub-items like `(a)` and `(i)` are NOT boundaries: they are the
inside of a clause, and promoting them shatters an obligation into fragments too small to
carry meaning. Measured on the CUAD specimens, that split a governing-law clause into its
sub-paragraphs and made every quote of it SPAN_OVERBROAD.

Text before the first boundary is a clause too, numbered None -- a preamble is where the
parties and the date live, and dropping it loses them.

Run: PYTHONPATH=. python3 checker/clauses.py
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# A decimal clause number: 1.  2.3  4.1.1  followed by space or the end of the line.
_NUMBER = re.compile(r"^\s{0,8}(\d{1,3}(?:\.\d{1,3}){0,3})\.?(?=\s|$)")
# Section 5 / ARTICLE IV / Clause 12 -- the word, then its designator.
_NAMED = re.compile(r"^\s{0,8}((?:SECTION|Section|ARTICLE|Article|CLAUSE|Clause)\s+"
                    r"(?:\d{1,3}(?:\.\d{1,3})*|[IVXLC]+))\b")
# A short all-capitals line: CONFIDENTIALITY, GOVERNING LAW. Length-capped because a
# whole paragraph shouted in capitals is not a heading, it is a limitation of liability.
_CAPS = re.compile(r"^\s{0,8}([A-Z][A-Z &'/,\.-]{2,48})\s*:?\s*$")

MAX_HEADING_WORDS = 8


class ContractUnreadable(OSError):
    """The file could not be read as a contract. Raised, never returned as empty text."""


@dataclass(frozen=True)
class Clause:
    number: str | None
    heading: str | None
    text: str
    start: int
    end: int

    def slice_of(self, source: str) -> bool:
        """The invariant, checkable by any caller that has the source."""
        return source[self.start:self.end] == self.text


def _boundary(line: str) -> tuple[str | None, str | None] | None:
    """(number, heading) when this line opens a clause, else None."""
    m = _NUMBER.match(line)
    if m:
        rest = line[m.end():].strip(" .:\t")
        return m.group(1), (rest or None)
    m = _NAMED.match(line)
    if m:
        rest = line[m.end():].strip(" .:\t")
        return m.group(1), (rest or None)
    m = _CAPS.match(line)
    if m and len(m.group(1).split()) <= MAX_HEADING_WORDS:
        return None, m.group(1).strip()
    return None


def split(source: str) -> tuple[Clause, ...]:
    """Every clause, as an exact slice of `source`.

    Offsets are computed by walking the string, never by re-finding a line with `index()`:
    two identical lines in one contract -- "Confidentiality" appearing in the table of
    contents and again as a heading -- would otherwise both resolve to the first.
    """
    if not source:
        return ()
    starts: list[tuple[int, str | None, str | None]] = []
    pos = 0
    for line in source.splitlines(keepends=True):
        b = _boundary(line)
        if b is not None:
            starts.append((pos, b[0], b[1]))
        pos += len(line)

    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, None, None))

    out = []
    for i, (at, num, head) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(source)
        body = source[at:end]
        if not body.strip():
            continue
        out.append(Clause(num, head, body, at, end))
    return tuple(out)


# ── getting the text out of a file, without changing it ──────────────────────

def from_docx(path: str | Path) -> str:
    """Paragraph text from a .docx, with the stdlib and no dependency.

    A .docx is a zip of XML. Each `w:p` is a paragraph and each `w:t` inside it a run of
    text; joining the runs within a paragraph and the paragraphs with newlines reproduces
    what a reader sees. `w:tab` becomes a tab and `w:br` a newline, because a clause
    number separated from its text by a tab is the ordinary case and losing it would
    merge the number into the first word.
    """
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise ContractUnreadable(f"{path} is not a readable .docx: {e}") from None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise ContractUnreadable(f"{path} holds unparseable document.xml: {e}") from None

    paras = []
    for p in root.iter(f"{W_NS}p"):
        buf = []
        for node in p.iter():
            if node.tag == f"{W_NS}t":
                buf.append(node.text or "")
            elif node.tag == f"{W_NS}tab":
                buf.append("\t")
            elif node.tag == f"{W_NS}br":
                buf.append("\n")
        paras.append("".join(buf))
    return "\n".join(paras)


def from_pdf(path: str | Path) -> str:
    """The TEXT LAYER of a PDF. A scanned page has none, and this says so rather than
    returning an empty contract that would review as having no clauses at all."""
    from checker.pdf_pages import PdfUnreadable, extract_pages
    try:
        pages = extract_pages(path)
    except PdfUnreadable as e:
        raise ContractUnreadable(f"{path}: {e}") from None
    text = "\n".join(pages)
    if not text.strip():
        raise ContractUnreadable(
            f"{path} has no text layer. This is a scanned document and needs OCR "
            f"(PLAN_22 D5); an empty string here would review as a contract with no "
            f"clauses in it, which is the opposite of what it is.")
    return text


def read(path: str | Path) -> str:
    """Dispatch on the extension. Unknown extensions are refused, never guessed."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        return from_docx(p)
    if ext == ".pdf":
        return from_pdf(p)
    if ext in (".txt", ".md", ""):
        try:
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ContractUnreadable(f"{p}: {e}") from None
    raise ContractUnreadable(
        f"{p.suffix!r} is not a contract format this reads (.docx, .pdf, .txt). "
        f"Guessing at the parser is how a spreadsheet gets reviewed as an NDA.")


SPECIMEN = """MUTUAL NON-DISCLOSURE AGREEMENT

This Agreement is made on 1 April 2026 between Acme Private Limited and Beta Limited.

1. Definitions
"Confidential Information" means any information disclosed by one party to the other.

2.1 Confidentiality
Each party shall keep the other's Confidential Information secret, and shall not:
(a) disclose it to any third party; or
(i) use it for any purpose other than the Purpose.

Section 5 Term
This Agreement continues for three years from the date above.

GOVERNING LAW
This Agreement is governed by the laws of India.
"""


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

    cl = split(SPECIMEN)
    nums = [c.number for c in cl]
    heads = [c.heading for c in cl]

    # ── the invariant, first, because everything downstream rests on it ──────
    check(all(c.slice_of(SPECIMEN) for c in cl),
          "EVERY clause is an exact slice of the source -- the property quoted_span needs")
    check("".join(c.text for c in cl) == SPECIMEN,
          "...and the clauses concatenate back to the document, so nothing was dropped "
          "between them and no text belongs to two clauses")
    check([c.start for c in cl] == sorted(c.start for c in cl),
          "...in document order")

    # ── the three ways a contract marks its own structure ───────────────────
    check("1" in nums and "2.1" in nums,
          f"a decimal clause number opens a clause, nested ones included ({nums})")
    check(any(n and n.startswith("Section 5") for n in nums),
          f"a Section heading opens one ({nums})")
    check("GOVERNING LAW" in heads,
          f"a short ALL-CAPS line is a heading ({heads})")
    check(cl[0].number is None and "MUTUAL NON-DISCLOSURE" in cl[0].text,
          "the preamble before the first number is a clause too -- it holds the parties "
          "and the date")

    # ── what is NOT a boundary ──────────────────────────────────────────────
    body = next(c.text for c in cl if c.number == "2.1")
    check("(a) disclose it" in body and "(i) use it" in body,
          "(a) and (i) stay INSIDE their clause: promoting a sub-item shatters an "
          "obligation into fragments too small to quote")
    shouted = split("THIS PARAGRAPH IS ENTIRELY IN CAPITALS AND RUNS ON AT SOME LENGTH "
                    "ABOUT LIABILITY AND IS NOT A HEADING AT ALL\n")
    check(len(shouted) == 1 and shouted[0].heading is None,
          "a long shouted paragraph is not a heading -- capitals alone do not make one")

    # ── two identical lines must not collapse to one offset ─────────────────
    dup = "CONFIDENTIALITY\nsee page 4\n\n1. Scope\nbody\n\nCONFIDENTIALITY\nthe real one\n"
    d = split(dup)
    offs = [c.start for c in d if c.heading == "CONFIDENTIALITY"]
    check(len(offs) == 2 and offs[0] != offs[1],
          f"a heading that appears twice gets TWO distinct offsets ({offs}) -- walking the "
          f"string rather than re-finding the line is what stops a contents entry and the "
          f"real clause resolving to the same place")
    check(all(c.slice_of(dup) for c in d), "...and both are still exact slices")

    check(split("") == (), "an empty document is no clauses, not one empty clause")
    check(len(split("just a sentence with no structure at all")) == 1,
          "an unstructured document is ONE clause, not zero -- it still has text in it")

    # ── .docx, with the stdlib ──────────────────────────────────────────────
    import io as _io
    import tempfile

    def docx(body_xml: str) -> bytes:
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml",
                       f'<?xml version="1.0"?><w:document xmlns:w="'
                       f'http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                       f'<w:body>{body_xml}</w:body></w:document>')
        return buf.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "nda.docx"
        f.write_bytes(docx(
            '<w:p><w:r><w:t>1.</w:t></w:r><w:r><w:tab/><w:t>Definitions</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Confidential Information means anything.</w:t></w:r></w:p>'))
        text = from_docx(f)
        check(text.startswith("1.\tDefinitions"),
              f"a .docx paragraph joins its runs and keeps the tab between the number and "
              f"its heading ({text[:24]!r})")
        check("\n" in text and "anything." in text, "...and paragraphs are separated")
        check(split(text)[0].number == "1",
              "...so the number survives into the split, tab and all")
        check(read(f) == text, "read() dispatches .docx by extension")

        bad = Path(tmp) / "broken.docx"
        bad.write_bytes(b"not a zip at all")
        try:
            from_docx(bad)
            check(False, "an unreadable .docx raises")
        except ContractUnreadable:
            check(True, "an unreadable .docx RAISES rather than returning empty text -- "
                        "empty would review as a contract with no clauses")

        odd = Path(tmp) / "book.xlsx"
        odd.write_bytes(b"x")
        try:
            read(odd)
            check(False, "an unknown extension is refused")
        except ContractUnreadable as e:
            check("not a contract format" in str(e),
                  "...and an unknown extension is refused rather than guessed: that is how "
                  "a spreadsheet gets reviewed as an NDA")

        plain = Path(tmp) / "a.txt"
        plain.write_text(SPECIMEN)
        check(read(plain) == SPECIMEN, "read() handles .txt unchanged, byte for byte")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
