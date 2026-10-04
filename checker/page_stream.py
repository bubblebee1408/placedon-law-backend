#!/usr/bin/env python3
"""Pages one at a time, with per-file caps, and a failed page that is NAMED not skipped.

A1 item 6 (ARCHITECTURE.md §12, "Large files"). `checker/pdf_pages.extract_pages` has three
properties this replaces for the intake path:

  * it builds a LIST of every page, so peak memory is the size of the whole extracted
    document rather than one page. A 1,500-page agreement is held entirely in memory.
  * a page that raises yields `""` and occupies its slot "saying nothing about its content".
    For the slot-indexing contract that is right; for INTAKE it means a document with an
    unreadable page is stored as complete with a blank page in the middle, and nobody is
    told. That is the silent skip this closes.
  * there is no cap, so a file of any size is attempted.

`extract_pages` is left exactly as it is -- callers that cite pages depend on its indexing --
and this is the streaming path intake uses.

## PARTIAL is a status, and it names the pages

A document whose page 7 failed is PARTIAL with `failed_pages == [7]`. Not COMPLETE, because
it is not; not FAILED, because the other 168 pages are present and useful. A reader who is
told PARTIAL and given the page numbers can decide; a reader given COMPLETE and a blank page
cannot know there is anything to decide.

## The caps are checked BEFORE anything is read

Both of them, with the cap that was exceeded named in the refusal, because "file too large"
without the limit tells an operator nothing they can act on.

Run: PYTHONPATH=. python3 checker/page_stream.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["MAX_PAGES", "MAX_BYTES", "COMPLETE", "PARTIAL", "Refusal", "Page",
           "Extraction", "check_file", "iter_pages", "extract_streaming"]

# A 1,500-page agreement is a real document; 5,000 is a mistake or an attack.
MAX_PAGES = 1_500
# 200 MiB. Above this the file is not a contract.
MAX_BYTES = 200 * 1024 * 1024

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class Refusal:
    code: str
    detail: str
    cap: str
    limit: int
    actual: int


@dataclass(frozen=True)
class Page:
    number: int                 # 1-indexed, as a citation names it
    text: str = ""
    error: str = ""             # non-empty means this page could not be read


@dataclass
class Extraction:
    status: str = COMPLETE
    pages: dict = field(default_factory=dict)      # number -> text
    failed_pages: tuple = ()
    page_count: int = 0
    peak_page_bytes: int = 0

    def to_dict(self) -> dict:
        return {"status": self.status, "page_count": self.page_count,
                "failed_pages": list(self.failed_pages),
                "peak_page_bytes": self.peak_page_bytes}


def check_file(path, *, max_pages: int = MAX_PAGES, max_bytes: int = MAX_BYTES,
               page_count=None, size_bytes=None) -> Refusal | None:
    """None if this file may be processed. A Refusal naming the cap it exceeds.

    BYTES first, then pages: the byte count is a stat() and the page count needs the file
    parsed, so refusing on size costs nothing. `page_count` and `size_bytes` are injectable
    so this is testable without a 200 MiB fixture -- measuring a cap should not require
    building something that breaches it.
    """
    from pathlib import Path as _P

    actual_bytes = size_bytes
    if actual_bytes is None:
        actual_bytes = _P(str(path)).stat().st_size
    if actual_bytes > max_bytes:
        return Refusal("FILE_TOO_LARGE",
                       f"the file is {actual_bytes} bytes, over the {max_bytes}-byte limit "
                       f"({max_bytes // (1024 * 1024)} MiB). Nothing was read",
                       "bytes", max_bytes, int(actual_bytes))

    pages = page_count
    if pages is None:
        from checker.pdf_pages import page_count as _pc
        pages = _pc(path)
    if pages > max_pages:
        return Refusal("TOO_MANY_PAGES",
                       f"the file declares {pages} pages, over the {max_pages}-page limit. "
                       f"Nothing was read",
                       "pages", max_pages, int(pages))
    return None


def _default_reader(path):
    """The real document, wrapped so `iter_pages` sees one shape.

    `pdf_pages._reader` is a context manager over the whole document; this holds it open for
    the life of the generator and reads ONE page per `page_text` call, which is what keeps
    peak memory at one page instead of the whole extraction.
    """
    from checker.pdf_pages import _reader

    class _Doc:
        def __init__(self):
            self._cm = _reader(path)
            self._doc = self._cm.__enter__()
            self.n = len(self._doc.pages)

        def page_text(self, i: int) -> str:
            return self._doc.pages[i - 1].extract_text() or ""

        def close(self):
            self._cm.__exit__(None, None, None)

    return _Doc()


def iter_pages(path, *, reader=None):
    """Yield one `Page` at a time, in document order, 1-indexed.

    A generator on purpose: the caller sees page N and may discard it before page N+1 is
    read, so peak memory is one page. `extract_pages` returns a list of every page, which is
    the right contract for citation indexing and the wrong one for a 1,500-page file.

    A page that raises yields a Page with `error` set and empty text. It is NOT skipped and
    NOT silently blanked -- the caller is told which page, by number.
    """
    doc = (reader or _default_reader)(path)
    try:
        for i in range(1, int(doc.n) + 1):
            try:
                yield Page(i, doc.page_text(i) or "")
            except Exception as e:                              # noqa: BLE001
                yield Page(i, "", f"{type(e).__name__}: {e}")
    finally:
        closer = getattr(doc, "close", None)
        if callable(closer):
            closer()


def extract_streaming(path, *, reader=None, on_page=None) -> Extraction:
    """Stream every page and report COMPLETE or PARTIAL with the pages that failed.

    `on_page(Page)` is called per page for a caller that wants to write each one out and keep
    none -- the point of streaming. Without it the pages are collected, which is convenient
    and gives up the memory property, so the docstring says so rather than implying both.
    """
    out = Extraction()
    failed: list[int] = []
    for page in iter_pages(path, reader=reader):
        out.page_count = page.number
        out.peak_page_bytes = max(out.peak_page_bytes, len(page.text.encode("utf-8")))
        if page.error:
            failed.append(page.number)
            continue
        if on_page is not None:
            on_page(page)
        else:
            out.pages[page.number] = page.text
    out.failed_pages = tuple(failed)
    out.status = PARTIAL if failed else COMPLETE
    return out


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def attempt(fn):
        """fn()'s value, or a string naming the exception. A check against a function that
        does not exist yet must FAIL with a count, not crash before the count is printed."""
        try:
            return fn()
        except Exception as e:                                  # noqa: BLE001
            return f"{type(e).__name__}: {e}"

    print("page_stream")

    class FakeDoc:
        """A document whose page `boom` raises when read."""
        def __init__(self, n, boom=None):
            self.n = n
            self.boom = boom

        def page_text(self, i):
            if self.boom is not None and i == self.boom:
                raise OSError(f"page {i} has no readable content stream")
            return f"page {i} text " + ("x" * 100)

    def reader_for(doc):
        return lambda _path: doc

    # ── the caps, refused BEFORE anything is read ──────────────────────────
    r = attempt(lambda: check_file("big.pdf", page_count=MAX_PAGES + 1, size_bytes=1))
    check(isinstance(r, Refusal), f"a file over the PAGE cap is refused ({r})")
    check(isinstance(r, Refusal) and r.limit == MAX_PAGES and r.cap == "pages",
          f"...naming the cap and its limit, so an operator knows what to change ({r})")
    check(isinstance(r, Refusal) and r.actual == MAX_PAGES + 1,
          "...and the actual size, so they know by how much")

    r = attempt(lambda: check_file("big.pdf", page_count=1, size_bytes=MAX_BYTES + 1))
    check(isinstance(r, Refusal) and r.cap == "bytes" and r.limit == MAX_BYTES,
          f"a file over the BYTE cap is refused, naming that cap ({r})")

    r = attempt(lambda: check_file("ok.pdf", page_count=10, size_bytes=1024))
    check(r is None, f"a file within both caps is not refused ({r})")
    r = attempt(lambda: check_file("edge.pdf", page_count=MAX_PAGES,
                                   size_bytes=MAX_BYTES))
    check(r is None, "a file exactly AT both caps is accepted, so the boundary is where it says")

    # ── pages come one at a time ───────────────────────────────────────────
    doc = FakeDoc(5)
    got = attempt(lambda: list(iter_pages("x.pdf", reader=reader_for(doc))))
    check(isinstance(got, list) and len(got) == 5,
          f"every page is yielded ({got if isinstance(got, str) else len(got)})")
    check(isinstance(got, list) and [p.number for p in got] == [1, 2, 3, 4, 5],
          "...numbered from 1, as a citation names them")
    import types
    gen = attempt(lambda: iter_pages("x.pdf", reader=reader_for(doc)))
    check(isinstance(gen, types.GeneratorType),
          f"iter_pages is a GENERATOR, so memory is one page and not the whole document "
          f"({type(gen).__name__})")

    # ── a failed page is named, and the document is PARTIAL ────────────────
    boom = FakeDoc(5, boom=3)
    ex = attempt(lambda: extract_streaming("x.pdf", reader=reader_for(boom)))
    check(isinstance(ex, Extraction) and ex.status == PARTIAL,
          f"a document with a failed page is PARTIAL, never COMPLETE "
          f"({ex if isinstance(ex, str) else ex.status})")
    check(isinstance(ex, Extraction) and list(ex.failed_pages) == [3],
          f"...and it NAMES the page ({ex if isinstance(ex, str) else ex.failed_pages})")
    check(isinstance(ex, Extraction) and sorted(ex.pages) == [1, 2, 4, 5],
          f"...while every OTHER page is present "
          f"({ex if isinstance(ex, str) else sorted(ex.pages)})")
    check(isinstance(ex, Extraction) and ex.page_count == 5,
          "...and the page count is the document's, not the number that succeeded")

    clean = attempt(lambda: extract_streaming("x.pdf", reader=reader_for(FakeDoc(4))))
    check(isinstance(clean, Extraction) and clean.status == COMPLETE
          and not clean.failed_pages,
          f"a document with no failed page is COMPLETE "
          f"({clean if isinstance(clean, str) else clean.status})")

    # The vacuity guard: PARTIAL must be reachable only when a page really failed.
    check(isinstance(clean, Extraction) and isinstance(ex, Extraction)
          and clean.status != ex.status,
          "COMPLETE and PARTIAL are both reachable, so neither check passes by default")

    # ── peak memory, MEASURED on a large document, not asserted ────────────
    # The claim is that streaming holds one page rather than the whole extraction. A
    # threshold here would be a number tuned to this machine, so the two figures are
    # measured side by side and PRINTED; the only assertion is the one that cannot be a
    # property of the laptop -- that collecting every page costs more than streaming it.
    import tracemalloc

    class BigDoc:
        """1,200 pages of 20 KB each: about 24 MB of text if it is all held at once."""
        n = 1_200

        def page_text(self, i):
            return f"page {i} " + ("lorem ipsum " * 1_700)

    big = BigDoc()

    tracemalloc.start()
    streamed_pages = 0
    seen_bytes = 0

    def _consume(page):
        nonlocal streamed_pages
        streamed_pages += 1

    extract_streaming("big.pdf", reader=lambda _p: big, on_page=_consume)
    streamed_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    tracemalloc.start()
    collected = extract_streaming("big.pdf", reader=lambda _p: big)
    collected_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()

    total_text = sum(len(t) for t in collected.pages.values())
    print(f"\n  peak memory over {big.n} pages, {total_text / 1e6:.1f} MB of text:")
    print(f"    streamed (on_page, keeps none)  {streamed_peak / 1e6:7.2f} MB")
    print(f"    collected (default, keeps all)  {collected_peak / 1e6:7.2f} MB")
    print(f"    ratio                           {collected_peak / max(1, streamed_peak):7.1f}x")
    print("  Measured, not asserted: a threshold here would be a number tuned to this "
          "machine.\n")

    check(streamed_pages == big.n,
          f"the streaming pass saw every page ({streamed_pages}/{big.n})")
    check(collected_peak > streamed_peak,
          f"collecting every page costs MORE peak memory than streaming it "
          f"({collected_peak / 1e6:.2f} MB vs {streamed_peak / 1e6:.2f} MB) -- that is a "
          f"property of the algorithm, not of this laptop, so it is the one thing asserted")
    check(streamed_peak < total_text,
          f"...and the streaming peak is below the total text size "
          f"({streamed_peak / 1e6:.2f} MB < {total_text / 1e6:.1f} MB), so the whole "
          f"document was never resident")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv else _test())
