"""The public documents D5 is allowed to read, and where a span sits in one.

Two jobs, both narrow:

  1. **Enumerate only what is public.** `corpus/testdocs/` and nothing else. Every
     file carries a `#`-prefixed provenance header naming its source and saying
     whether it is a REAL FILED DOCUMENT or an ICSI SPECIMEN, and a file without
     one is not a corpus document (`minutes_extracts/README.txt` is the case that
     exists today). `load_all()` refuses a path outside the root rather than
     trusting its caller, because the caller is what would send a private
     document to a third-party model.

  2. **Locate a span.** A model quotes verbatim; a reviewer needs to be told where
     to look. `locate()` returns the line number **in the corpus text file**, the
     character offset in the stripped body, and the surrounding text.

## Why there are no page numbers

`docs/OVERNIGHT_REPORT_2026_09_14.md` §4: the repository's own page reader agrees
with an independent reader on **0 of 14** corpus PDFs -- 1 page returned for a
169-page file, 0 for a 179-page file. A page number taken from it would be a
number that looks checkable and is not. The anchor is therefore the corpus text
file and its line, which is exactly reproducible with `sed -n '<line>p'`.

Run: python3 eval/prelabel/corpus.py
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "corpus" / "testdocs"

REAL = "real"
SPECIMEN = "specimen"

_REAL_HEADER = "# REAL FILED DOCUMENT"
_SPECIMEN_HEADER = "# ICSI SPECIMEN"

WINDOW = 130          # characters of document text shown either side of a span


@dataclass(frozen=True)
class Document:
    """One public corpus document, header stripped, with its line map kept."""
    doc_id: str
    path: str                     # relative to the repository root
    kind: str                     # REAL | SPECIMEN
    title: str                    # the first header line, verbatim
    source: str                   # the first http(s) line of the header, verbatim
    text: str                     # the body: every line NOT starting with '#'
    line_map: tuple[int, ...]     # body line index -> 1-based line in the file

    @property
    def chars(self) -> int:
        return len(self.text)


def _classify(header: list[str]) -> str | None:
    first = header[0] if header else ""
    if first.startswith(_REAL_HEADER):
        return REAL
    if first.startswith(_SPECIMEN_HEADER):
        return SPECIMEN
    return None


def read_document(path: Path) -> Document | None:
    """One file -> a Document, or None when it is not a corpus document.

    Returning None rather than raising: a directory gaining a README is normal,
    and a harness that dies on it would be reporting a repository problem as a
    corpus problem.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    header = [ln for ln in raw.splitlines() if ln.startswith("#")]
    kind = _classify(header)
    if kind is None:
        return None

    body: list[str] = []
    line_map: list[int] = []
    for n, line in enumerate(raw.splitlines(), start=1):
        if line.startswith("#"):
            continue
        body.append(line)
        line_map.append(n)

    source = next((ln.lstrip("# ").strip() for ln in header
                   if "http://" in ln or "https://" in ln), "")
    return Document(
        doc_id=str(path.relative_to(DOCS_ROOT)).replace(".txt", ""),
        path=str(path.relative_to(ROOT)),
        kind=kind,
        title=header[0].lstrip("# ").strip(),
        source=source,
        text="\n".join(body),
        line_map=tuple(line_map))


def load_all(root: Path | None = None) -> tuple[Document, ...]:
    """Every public corpus document, sorted. Refuses a root outside the corpus."""
    base = Path(root or DOCS_ROOT).resolve()
    if base != DOCS_ROOT and DOCS_ROOT not in base.parents:
        raise ValueError(
            f"{base} is outside {DOCS_ROOT}. D5 reads PUBLIC corpus documents "
            f"only; nothing else may be sent to a third-party model")
    docs = [d for d in (read_document(p) for p in sorted(base.rglob("*.txt")))
            if d is not None]
    return tuple(docs)


# ── locating a span ───────────────────────────────────────────────────────────
def _flatten(text: str) -> tuple[str, tuple[int, ...]]:
    """Whitespace-collapsed, lowercased text plus each character's source offset.

    The same normalisation `checker.reasoning._norm` applies before it asks
    whether a span is in the document, so a span that review() admitted is a span
    this can find. Written out rather than reused because that one discards the
    offsets, and the offsets are the whole point here.
    """
    out: list[str] = []
    offs: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            pending_space = bool(out)
            continue
        if pending_space:
            out.append(" ")
            offs.append(i)
            pending_space = False
        out.append(ch.lower())
        offs.append(i)
    return "".join(out), tuple(offs)


@dataclass(frozen=True)
class Anchor:
    line: int                # 1-based, in the corpus TEXT FILE
    offset: int              # 0-based, in the stripped body
    quote: str               # what the document says there, verbatim


def locate(doc: Document, span: str) -> Anchor | None:
    """Where `span` sits in `doc`, or None if it is not there.

    None is a real answer: a span review() refused as ungrounded has no anchor,
    and inventing one would be the repair this repository forbids.
    """
    if not span or not span.strip():
        return None
    flat, offs = _flatten(doc.text)
    needle, _ = _flatten(span)
    at = flat.find(needle)
    if at < 0:
        return None
    start = offs[at]
    end = offs[min(at + len(needle), len(offs)) - 1] + 1

    line_starts = [0]
    for i, ch in enumerate(doc.text):
        if ch == "\n":
            line_starts.append(i + 1)
    body_line = bisect_right(line_starts, start) - 1
    file_line = (doc.line_map[body_line] if body_line < len(doc.line_map)
                 else doc.line_map[-1] if doc.line_map else 1)

    lo = max(0, start - WINDOW)
    hi = min(len(doc.text), end + WINDOW)
    quote = " ".join(doc.text[lo:hi].split())
    return Anchor(line=file_line, offset=start, quote=quote)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("prelabel.corpus")
    import tempfile

    docs = load_all()
    check(len(docs) >= 25, f"the public corpus loads ({len(docs)} documents)")
    check(all(d.path.startswith("corpus/testdocs/") for d in docs),
          "every document loaded is under corpus/testdocs")
    check(not any("README" in d.doc_id for d in docs),
          "a file with no provenance header is not a corpus document")
    check(all(not ln.startswith("#") for d in docs for ln in d.text.splitlines()),
          "the '#' provenance header is stripped from every body")
    kinds = {d.kind for d in docs}
    check(kinds == {REAL, SPECIMEN},
          f"both a real filing and an ICSI specimen are present ({sorted(kinds)})")
    check(all(d.source.startswith("http") for d in docs),
          "every document carries its own source URL")

    # The guard that matters: nothing outside the public corpus.
    with tempfile.TemporaryDirectory() as td:
        Path(td, "private.txt").write_text("# REAL FILED DOCUMENT — minutes\nsecret\n")
        try:
            load_all(Path(td))
            check(False, "a root outside corpus/testdocs is refused")
        except ValueError as e:
            check("PUBLIC" in str(e),
                  "a root outside corpus/testdocs is refused, by name")

    # ── locating a span in a real document ────────────────────────────────────
    titan = next(d for d in docs if "titan_41st" in d.doc_id)
    a = locate(titan, "Forty-First Annual General")
    check(a is not None and a.line > 5,
          f"a verbatim span locates to a file line ({a.line if a else None})")
    line_text = Path(ROOT, titan.path).read_text().splitlines()[a.line - 1]
    check("Forty-First" in line_text or "Annual" in line_text,
          f"the line number points at the span in the FILE: {line_text.strip()[:60]!r}")
    check("Forty-First Annual General" in a.quote and len(a.quote) > 60,
          "the anchor carries what the document says around the span")

    # A span whose whitespace differs still locates -- review() admitted it on the
    # same normalisation, so refusing it here would lose an admitted value.
    b = locate(titan, "Forty-First   Annual\n General")
    check(b is not None and b.offset == a.offset,
          "a span with different whitespace locates to the same place")

    check(locate(titan, "the company hereby confirms it is compliant") is None,
          "a span that is not in the document has no anchor — none is invented")
    check(locate(titan, "   ") is None, "a blank span has no anchor")

    # Line mapping must survive the header strip.
    first_body_line = titan.line_map[0]
    check(first_body_line > 1,
          f"body line 1 maps past the header (file line {first_body_line})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
