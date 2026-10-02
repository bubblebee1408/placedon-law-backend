#!/usr/bin/env python3
"""Refuse an archive that would cost more to open than it claims to be.

V1. A vault takes files from clients. Some of those files are archives, and an archive is
the one upload that can be small on the wire and ruinous in memory: 42.zip is 42 kilobytes
and expands to 4.5 petabytes. The defence is not a scanner -- it is reading the archive's
own declared sizes BEFORE extracting anything, and refusing on three independent limits.

## Three limits, because each catches what the others miss

    MAX_ENTRIES          10,000 files. A zip of a million empty files costs nothing to
                         store and exhausts inodes and loop iterations on open.
    MAX_TOTAL_BYTES      2 GiB uncompressed. The straightforward bomb.
    MAX_RATIO            200x. A 10 MiB archive expanding to 1.9 GiB passes the total
                         limit and is still almost certainly hostile.

A file can pass two and fail the third, which is why all three are checked and the refusal
names which one fired.

## The declared size is not trusted, it is USED AS A CEILING

A zip's central directory states each entry's uncompressed size, and a hostile zip can lie.
So this refuses on the DECLARED sizes first -- a lie that understates is still bounded by
the real extraction being capped separately -- and `safe_extract` enforces the same budget
while reading, byte by byte, so an entry whose real size exceeds its declaration stops at
the limit rather than at the end.

Refusing on declared size alone would be a check that a liar passes; extracting first and
measuring would be the attack succeeding. Both, in that order.

## Not an archive is not an error

`inspect` returns NOT_ARCHIVE for anything it cannot read as one, and the caller stores it
as an ordinary file. A PDF is not a failed zip.

Run: PYTHONPATH=. python3 checker/archive_guard.py --test
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

__all__ = ["MAX_ENTRIES", "MAX_TOTAL_BYTES", "MAX_RATIO", "OK", "NOT_ARCHIVE",
           "TOO_MANY_ENTRIES", "TOO_LARGE", "RATIO", "UNREADABLE", "Verdict", "inspect",
           "safe_extract", "ArchiveRefused"]

MAX_ENTRIES = 10_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024          # 2 GiB
MAX_RATIO = 200

OK = "OK"
NOT_ARCHIVE = "NOT_ARCHIVE"
TOO_MANY_ENTRIES = "TOO_MANY_ENTRIES"
TOO_LARGE = "TOO_LARGE"
RATIO = "RATIO"
UNREADABLE = "UNREADABLE"


class ArchiveRefused(ValueError):
    """An archive this system will not open. Never a silent truncation."""


@dataclass(frozen=True)
class Verdict:
    state: str
    entries: int = 0
    declared_bytes: int = 0
    packed_bytes: int = 0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state in (OK, NOT_ARCHIVE)

    @property
    def ratio(self) -> float | None:
        """Declared expansion, or None when there are no packed bytes to divide by.

        An EMPTY archive has a real ratio of 0.0 -- it genuinely does not expand -- and
        that is reported as 0.0, not None. None means the input had no bytes at all, which
        is `NOT_ARCHIVE` anyway; it exists so this property cannot raise rather than to
        express anything about the archive.
        """
        return None if not self.packed_bytes else round(
            self.declared_bytes / self.packed_bytes, 2)

    def to_dict(self) -> dict:
        return {"state": self.state, "entries": self.entries,
                "declared_bytes": self.declared_bytes, "packed_bytes": self.packed_bytes,
                "ratio": self.ratio, "reason": self.reason, "ok": self.ok}


def inspect(data: bytes) -> Verdict:
    """Read the archive's own declared sizes. Extracts NOTHING."""
    packed = len(data or b"")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        # Not a zip. A PDF is not a failed archive, and saying so is not a refusal.
        return Verdict(NOT_ARCHIVE, packed_bytes=packed,
                       reason="not readable as a zip archive; stored as an ordinary file")
    n = len(infos)
    declared = sum(max(0, int(i.file_size or 0)) for i in infos)
    if n > MAX_ENTRIES:
        return Verdict(TOO_MANY_ENTRIES, n, declared, packed,
                       f"{n} entries, over the {MAX_ENTRIES} limit. A million empty files "
                       f"costs nothing to send and exhausts the machine that opens it")
    if declared > MAX_TOTAL_BYTES:
        return Verdict(TOO_LARGE, n, declared, packed,
                       f"declares {declared} uncompressed bytes, over the "
                       f"{MAX_TOTAL_BYTES} limit")
    if packed and declared / packed > MAX_RATIO:
        return Verdict(RATIO, n, declared, packed,
                       f"declares {declared} bytes from {packed} packed, a ratio of "
                       f"{declared / packed:.0f}x over the {MAX_RATIO}x limit")
    return Verdict(OK, n, declared, packed, f"{n} entr(ies), {declared} declared bytes")


def safe_extract(data: bytes, *, budget: int = MAX_TOTAL_BYTES):
    """Yield (name, bytes) for each entry, stopping the moment the BUDGET is exceeded.

    The second half of the defence. `inspect` refuses on what the archive DECLARES; this
    enforces the same ceiling on what it actually produces, so an entry whose real size
    exceeds its declaration stops at the limit rather than at the end of the stream.

    Reading in chunks, not `read()`: `read()` on a lying entry allocates the real size
    before anything can check it, which is the attack.
    """
    verdict = inspect(data)
    if verdict.state == NOT_ARCHIVE:
        raise ArchiveRefused("not an archive; nothing to extract")
    if not verdict.ok:
        raise ArchiveRefused(f"{verdict.state}: {verdict.reason}")
    spent = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            out = bytearray()
            with zf.open(info) as fh:
                while True:
                    chunk = fh.read(64 * 1024)
                    if not chunk:
                        break
                    spent += len(chunk)
                    if spent > budget:
                        raise ArchiveRefused(
                            f"extraction exceeded {budget} bytes at {info.filename!r}: "
                            f"the archive produced more than it declared, which is the "
                            f"case a declared-size check alone would pass")
                    out.extend(chunk)
            yield info.filename, bytes(out)


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

    print("archive_guard")

    def zipped(entries, *, compress=zipfile.ZIP_DEFLATED) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=compress) as zf:
            for name, body in entries:
                zf.writestr(name, body)
        return buf.getvalue()

    # ── an ordinary archive passes, and so does a non-archive ───────────────
    good = zipped([("a.txt", "hello"), ("b.txt", "world")])
    v = inspect(good)
    check(v.state == OK and v.ok and v.entries == 2,
          f"an ordinary two-file zip is OK ({v.state}, {v.entries} entries)")
    check(v.declared_bytes == 10, f"...with its declared size read, not guessed "
                                  f"({v.declared_bytes})")
    pdf = inspect(b"%PDF-1.7\nnot a zip at all")
    check(pdf.state == NOT_ARCHIVE and pdf.ok,
          "a PDF is NOT_ARCHIVE and that is not a refusal: a PDF is not a failed zip")
    check("ordinary file" in pdf.reason, "...and the reason says it is stored as one")
    check(inspect(b"").state == NOT_ARCHIVE, "empty bytes are not an archive")

    # ── the bomb: a high ratio is refused ──────────────────────────────────
    bomb = zipped([("z.txt", "0" * 5_000_000)])
    b = inspect(bomb)
    check(b.state == RATIO and not b.ok,
          f"a 5 MB run of zeros compresses past the ratio limit and is REFUSED "
          f"({b.state}, ratio {b.ratio})")
    check(b.ratio and b.ratio > MAX_RATIO,
          f"...and the ratio is reported ({b.ratio}x over {MAX_RATIO}x)")
    check(str(MAX_RATIO) in b.reason, "...with the limit it crossed named in the reason")

    # ── too many entries ───────────────────────────────────────────────────
    many = zipped([(f"f{i}.txt", "x") for i in range(MAX_ENTRIES + 5)],
                  compress=zipfile.ZIP_STORED)
    m = inspect(many)
    check(m.state == TOO_MANY_ENTRIES and not m.ok,
          f"{MAX_ENTRIES + 5} entries is refused on COUNT, which the size limits would "
          f"not catch: a million empty files is tiny ({m.state})")
    check(m.entries == MAX_ENTRIES + 5, "...and the count is reported")

    # Each limit catches what the others miss -- the reason there are three.
    check(inspect(many).declared_bytes < MAX_TOTAL_BYTES,
          "...the entry-count bomb is well under the SIZE limit, so size alone would pass "
          "it")
    check(inspect(bomb).entries <= MAX_ENTRIES,
          "...and the ratio bomb is one entry, so a count limit alone would pass it")

    # ── the limits themselves ──────────────────────────────────────────────
    check((MAX_ENTRIES, MAX_TOTAL_BYTES, MAX_RATIO)
          == (10_000, 2 * 1024 * 1024 * 1024, 200),
          "the three limits are 10,000 entries, 2 GiB and 200x")
    check(inspect(zipped([])).ratio == 0.0,
          f"an EMPTY archive has a ratio of 0.0 -- it genuinely does not expand -- and "
          f"that is a real answer, not a missing one ({inspect(zipped([])).ratio})")
    check(Verdict(NOT_ARCHIVE, packed_bytes=0).ratio is None,
          "...while NO packed bytes gives None: the guard against dividing by zero, which "
          "says nothing about an archive because there is no archive")

    # ── extraction stops at the budget, not at the end ─────────────────────
    got = dict(safe_extract(good))
    check(got == {"a.txt": b"hello", "b.txt": b"world"},
          f"a safe archive extracts its entries ({sorted(got)})")
    try:
        list(safe_extract(good, budget=3))
        check(False, "extraction past the budget raises")
    except ArchiveRefused as e:
        check("exceeded 3 bytes" in str(e),
              f"extraction STOPS at the budget mid-entry, rather than reading to the end "
              f"and measuring afterwards ({str(e)[:46]})")
    try:
        list(safe_extract(bomb))
        check(False, "a refused archive does not extract")
    except ArchiveRefused as e:
        check(RATIO in str(e),
              "an archive `inspect` refuses is never extracted: the guard runs first")
    try:
        list(safe_extract(b"%PDF-1.7"))
        check(False, "a non-archive raises on extract")
    except ArchiveRefused:
        check(True, "extracting a non-archive raises rather than yielding nothing, which "
                    "would read as an empty archive")

    import inspect as _inspect
    src = _inspect.getsource(safe_extract)
    check(".read(64 * 1024)" in src and "fh.read()" not in src,
          "extraction reads in CHUNKS, never fh.read(): read() on a lying entry allocates "
          "its real size before anything can check it, which is the attack")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
