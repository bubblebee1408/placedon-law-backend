"""Text per page, for OFFLINE ingestion only. The reader that actually reads.

## Why this module exists, and why it is not `pdf_text.extract_pages`

`pdf_text.extract_pages` finds pages by running a regex over RAW FILE BYTES looking
for `/Type/Page`. In PDF 1.5+ the page objects and the cross-reference table live
inside zlib-compressed object streams (`/Type/ObjStm`) and cross-reference streams
(`/Type/XRef`). A byte regex cannot see inside a deflate stream, so the function
returns nothing — silently.

Measured against the corpus on 2026-09-17, before this module existed:

    icsi_gn_board.pdf      169 real pages -> the old reader found   1
    icsi_gn_general.pdf    179 real pages -> the old reader found   0
    route_agm_2024.pdf      22 real pages -> the old reader found  37

and across all 14 census documents it produced **0 words on 13 of them**.

There was a second, independent defect. The old code searched for `/Contents` only
in the 400 bytes FOLLOWING the `/Type/Page` match (`pdf_text.py:217`). Many writers
emit `/Contents` BEFORE `/Type/Page` in the same dictionary, so even files with no
object streams lost their text: `sonata_agm_notice_29th_2024.pdf` reported all 18
pages and extracted text from 0 of them; `titan_agm_2026.pdf` missed 12 of 15.

That second defect matters for the choice made here: it is NOT fixed by adding
object-stream support, so the standard-library path was two parsers, not one.

## The failure this module is really about

`pdf_text.py`'s own docstring states the rule this file is named after:

    "A guard that reports a property of the toolchain as a property of the evidence
    is worse than no guard, because the failure is invisible and reads as a fact
    about the law."

An empty page list from a 169-page gazette is exactly that. Downstream, "the reader
could not read it" is indistinguishable from "the document says nothing" — and in a
compliance engine the second reads as *no obligation found*. The bug was not that
pages were missed; it was that they were missed **quietly**.

## Decision D-2 (founder, 2026-09-17): pypdf, offline only

The standard-library fix was measured at ~400-450 lines — xref-stream parsing with
variable `/W` widths, `/Prev` chain walking with loop guards, object-stream
inflation, a balanced-bracket dictionary parser, page-tree DFS with cycle guards —
plus the separate `/Contents` fix, with pure-Python AES as a live risk the day an
encrypted gazette arrives. That is a PDF parser, and every line of it is a line that
can be quietly wrong about the source text of the law.

`pypdf` is BSD-3-Clause, pure Python, and has **zero mandatory transitive
dependencies**. It is declared in `requirements-dev.txt`, never in
`requirements.txt`.

**The boundary that keeps README honest.** The README claims "no dependencies
outside the standard library". That claim is about the SERVED path, and it stays
true: `checker/api.py` and `backend/` import nothing from this module or from
`pdf_text` -- verified 2026-09-17, zero hits. Every consumer of page extraction is
offline tooling (`sweep.py` and five scripts). `_test()` below asserts that boundary
rather than trusting it, in the same spirit as `api.py`'s assertion that the API
imports no model library.

**PyMuPDF was rejected on licence.** It is AGPL-3.0 or a paid Artifex commercial
licence. AGPL section 13 extends copyleft to network use, so shipping it in a served
backend sold to Indian corporates would compel disclosure of the whole product's
source. That is a legal exposure, not a preference.

**pdfplumber was rejected for a subtler reason.** It is already a declared dev
dependency, so it looked free. But `scripts/text_layer_census.py` uses pdfplumber as
the INDEPENDENT ORACLE that judges this repository's reader. Adopting it here would
make the census compare pdfplumber against pdfplumber, and the verification
instrument would stop being evidence. pypdf is its own parser; pdfplumber wraps
pdfminer.six. Two engines, so the two-reader census stays honest.

## What this module does not do

It does not repair anything. A page whose text layer is empty comes back as an empty
string, because that is what the document says -- `corpus/testdocs/` holds 17 pages
of OCR-over-scan whose figures are wrong, and `MANIFEST.md` records them unrepaired.
An encrypted document raises rather than returning plausible blanks.
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["extract_pages", "page_count"]


class PdfUnreadable(OSError):
    """The document could not be read as a PDF. Never returned as empty text."""


def _reader(path: str | Path):
    """Open `path`, failing loudly. Import is local so this file costs nothing to import."""
    p = Path(path)
    if not p.is_file():
        raise PdfUnreadable(f"no such PDF: {p}")
    try:
        from pypdf import PdfReader
    except ImportError as exc:                                    # pragma: no cover
        raise PdfUnreadable(
            "pypdf is required for page extraction and is declared in "
            "requirements-dev.txt. This module is offline tooling only."
        ) from exc

    try:
        r = PdfReader(str(p))
    except Exception as exc:
        raise PdfUnreadable(f"{p.name}: not readable as a PDF ({exc})") from exc

    # An encrypted document must not come back as a pile of empty pages: that is the
    # toolchain-as-evidence failure this module exists to refuse. Try the empty user
    # password, which is what permissions-only encryption uses, and raise otherwise.
    if getattr(r, "is_encrypted", False):
        try:
            if not r.decrypt(""):
                raise PdfUnreadable(f"{p.name}: encrypted, and not with an empty password")
        except PdfUnreadable:
            raise
        except Exception as exc:
            raise PdfUnreadable(f"{p.name}: encrypted and undecryptable ({exc})") from exc
    return r


def extract_pages(path: str | Path) -> list[str]:
    """Text per page, in document order. One entry per page, always.

    A page with no text layer yields "" and still occupies its slot, so page N of the
    return value is page N of the document. Callers cite pages; the indexing is the
    contract.

    Raises `PdfUnreadable` rather than returning [] — an empty list from a real
    document is the silent failure this module replaced.
    """
    r = _reader(path)
    out: list[str] = []
    for page in r.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            # One unreadable page must not lose the other 168. Preserve the slot,
            # say nothing about its content.
            out.append("")
    return out


def page_count(path: str | Path) -> int:
    """How many pages the document declares, without extracting any text."""
    return len(_reader(path).pages)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    root = Path(__file__).resolve().parent.parent

    # ---- the boundary the README depends on -------------------------------------
    # Asserted, not trusted. If the served path ever imports a PDF library, the
    # README's "no dependencies outside the standard library" becomes false and this
    # test is what says so.
    served = [root / "checker/api.py"] + sorted((root / "backend").rglob("*.py"))
    leaked = [
        f.relative_to(root)
        for f in served
        if f.is_file()
        and any(tok in f.read_text(encoding="utf-8", errors="replace")
                for tok in ("pypdf", "pdfplumber", "fitz", "pdf_pages", "pdf_text"))
    ]
    check(not leaked, f"the served path imports no PDF reader (leaked: {leaked})")

    # ---- reading a document the OLD reader could not see -------------------------
    # These are the regression that mattered. `pdf_text`'s only wired-in fixture was
    # companies_meetings_board_powers_rules_2014.pdf, which is PDF 1.4 with NO object
    # streams — structurally immune to the bug, which is why it went unnoticed for so
    # long. Every file below is one the old reader got wrong.
    cases = [
        ("corpus/testdocs/_raw/icsi_gn_board.pdf", 169, "compressed object streams"),
        ("corpus/testdocs/_raw/icsi_gn_general.pdf", 179, "object streams, 0 pages before"),
        ("corpus/testdocs/_raw/route_agm_2024.pdf", 22, "stale incremental-update objects"),
        ("corpus/testdocs/_raw/sonata_agm_notice_29th_2024.pdf", 18, "/Contents before /Type/Page"),
    ]
    seen_any = False
    for rel, want, why in cases:
        p = root / rel
        if not p.is_file():
            print(f"  [SKIP] {Path(rel).name} not present")
            continue
        seen_any = True
        pages = extract_pages(p)
        check(len(pages) == want,
              f"{Path(rel).name}: {want} pages ({why}) — got {len(pages)}")
        with_text = sum(1 for t in pages if t.strip())
        check(with_text >= max(1, int(want * 0.8)),
              f"{Path(rel).name}: >=80% of pages carry text — got {with_text}/{want}")

    if not seen_any:
        print("  [SKIP] no census fixtures present; page-reading unverified here")

    # ---- the file pdf_text already guarded, so behaviour is not lost -------------
    stored = root / "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
    if stored.is_file():
        pg = extract_pages(stored)
        check(len(pg) == 22, f"the Rules gazette still reports 22 pages (got {len(pg)})")
        check("Meetings of Board" in " ".join(pg), "page text still carries the title")
    else:
        print("  [SKIP] stored Rules PDF not present")

    # ---- failing loudly ----------------------------------------------------------
    try:
        extract_pages(root / "definitely-not-here-9x.pdf")
        check(False, "a missing file must raise")
    except PdfUnreadable:
        check(True, "a missing file raises PdfUnreadable, never []")

    import logging
    import tempfile
    # pypdf logs its own parse failure to stderr. That is correct of pypdf and noise
    # here: the raise IS the assertion. Silence it so a real error stays visible.
    _pypdf_log = logging.getLogger("pypdf")
    _prior = _pypdf_log.level
    _pypdf_log.setLevel(logging.CRITICAL)
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as fh:
            fh.write(b"this is not a PDF at all"); fh.flush()
            try:
                extract_pages(fh.name)
                check(False, "a non-PDF must raise")
            except PdfUnreadable:
                check(True, "a non-PDF raises rather than returning ''")
    finally:
        _pypdf_log.setLevel(_prior)

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
