#!/usr/bin/env python3
"""Per-page text-layer census of the public test corpus. MEASURED, and narrow.

PLAN_12's intake routes each page by its text layer: native text, needs OCR, or
text present but untrusted. R5 (docs/research/LARGE_DOCUMENT_PROFILE.md) measured
that on a real 512-page scheme bundle -- 20.7% of pages image-only, some text
layers corrupted -- and found the local corpus contains none of those failures.
This script measures the local corpus with the repository's OWN reader, so the
routing a build would use can be checked against a number rather than assumed.

## What it is not

It is **not the 20-document test** (PLAN_05). Every document here is a public
filing or an ICSI specimen, chosen for a different purpose; nothing in it says
what a buyer's documents look like.

## Labels, and why none of them says "scanned"

`checker/pdf_text.py` is stdlib-only and is not a renderer. It returns nothing for
an image-only page -- and also for a page whose fonts it cannot decode. So an empty
page is NO_TEXT_EXTRACTED: this reader got nothing. Calling it "scanned" would
report a property of the toolchain as a property of the document, which is the
exact error pdf_text.py's own docstring was written about.

  TEXT               enough recognisable words to treat the layer as usable
  NO_TEXT_EXTRACTED  this reader extracted no words. Not evidence of a scan
  SUSPECT            characters came out, but few recognisable words -- a
                     corrupted layer, an undecoded font, or non-Latin script.
                     Never repaired, never decoded; reported for a human

The thresholds are heuristics chosen here, named below, and stated in the output.
They are not measured and must not be quoted as accuracy.

Run:  python3 scripts/text_layer_census.py            # writes the census
      python3 scripts/text_layer_census.py --test     # offline self-test
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEXT = "TEXT"
NO_TEXT_EXTRACTED = "NO_TEXT_EXTRACTED"
SUSPECT = "SUSPECT"

# Heuristics, not measurements. Stated in every output so nobody quotes them as one.
# "Recognised" means in pdf_text's own 33-word vocabulary (_englishness), reused
# rather than duplicated: a letter-shifted layer is all letters and still reads as
# nothing, which a plain word count cannot see.
MIN_WORDS_FOR_TEXT = 8         # recognised words on a page to call the layer usable
MIN_WORD_SHARE = 0.15          # recognised words as a share of all letter-run tokens
MAX_NON_ASCII_SHARE = 0.2      # above this, a page is SUSPECT: broken glyphs and
                               # non-Latin script both land here, by design
COVERS_PAGE = 0.95             # one image covering this share of the page: a scan, so
                               # any text layer on it is OCR we did not do


def page_image_share(images: list[dict], width: float, height: float) -> float:
    """The largest single image's share of the page area. Geometry, not pixels."""
    area = float(width or 0) * float(height or 0)
    if not area or not images:
        return 0.0
    largest = max(max(0.0, float(im["x1"]) - float(im["x0"]))
                  * max(0.0, float(im["bottom"]) - float(im["top"])) for im in images)
    return min(largest / area, 1.0)

_WORD = re.compile(r"[A-Za-z]{2,}")


def classify_page(text: str) -> str:
    """TEXT, NO_TEXT_EXTRACTED or SUSPECT for one page as this reader saw it."""
    chars = "".join((text or "").split())
    if not chars:
        return NO_TEXT_EXTRACTED
    from checker.pdf_text import _englishness
    if sum(1 for ch in chars if ord(ch) > 127) / len(chars) > MAX_NON_ASCII_SHARE:
        return SUSPECT
    tokens = len(_WORD.findall(text))
    recognised = _englishness(text)
    if recognised >= MIN_WORDS_FOR_TEXT and tokens and recognised / tokens >= MIN_WORD_SHARE:
        return TEXT
    return SUSPECT

CORPUS = ROOT / "corpus" / "testdocs"
OUT = CORPUS / "TEXT_LAYER_CENSUS.json"
SCOPE = ("public filings and ICSI specimens under corpus/testdocs -- not the "
         "20-document test, and not evidence of what a buyer's documents look like")


def census_pages(name: str, pages: list[str],
                 image_shares: list[float] | None = None) -> dict:
    """One document's pages, labelled. An empty list is a reader failure.

    `image_shares` comes only from a reader that can see image geometry. Without
    it `text_over_page_image` is None -- not 0, which would claim someone looked.
    """
    per_page = []
    for i, t in enumerate(pages):
        entry = {"page_index": i, "label": classify_page(t),
                 "chars": len("".join(t.split()))}
        if image_shares is not None:
            share = image_shares[i] if i < len(image_shares) else 0.0
            entry["page_image_share"] = round(share, 3)
            entry["text_over_page_image"] = bool(entry["chars"]) and share >= COVERS_PAGE
        per_page.append(entry)
    counts: dict[str, int] = {}
    for p in per_page:
        counts[p["label"]] = counts.get(p["label"], 0) + 1
    over = (None if image_shares is None
            else sum(1 for p in per_page if p["text_over_page_image"]))
    return {"document": name, "pages": len(pages), "reader_failed": not pages,
            "counts": counts, "text_over_page_image": over, "per_page": per_page}


def compare_readers(name: str, *, repo_pages: list[str],
                    independent_pages: list[str] | None) -> dict:
    """Where the repository's reader and an independent one disagree, per page."""
    repo = [classify_page(t) for t in repo_pages]
    if independent_pages is None:
        return {"document": name, "repo_pages": len(repo), "independent_pages": None,
                "independent_failed": True, "page_count_mismatch": False,
                "pages_repo_missed": 0, "agree": False}
    ind = [classify_page(t) for t in independent_pages]
    # Walk the INDEPENDENT reader's pages: a page the repo reader never returned
    # is missed too, which a zip over both lists silently skips.
    missed = sum(1 for n, i in enumerate(ind)
                 if i == TEXT and (n >= len(repo) or repo[n] != TEXT))
    mismatch = len(repo) != len(ind)
    return {"document": name, "repo_pages": len(repo), "independent_pages": len(ind),
            "independent_failed": False, "page_count_mismatch": mismatch,
            "pages_repo_missed": missed,
            "agree": not mismatch and missed == 0 and repo == ind}


def _pdfplumber_read(path: Path) -> tuple[list[str], list[float]] | None:
    """The independent reader: text and image geometry per page. None when it
    cannot open the file -- recorded, never skipped.

    **The oracle is pypdf, not pdfplumber, since D-002b (25-09-2026).** The roles
    were swapped, not merged: `checker/pdf_pages` moved to pdfplumber because pypdf
    invented spaces inside words ("Board an d its") and emitted /uniXXXX glyph names
    for the bilingual gazette's Devanagari. Making the census read pdfplumber too
    would have left one library judging itself, which is the property that caught
    SD-006. The name is kept so callers and stored reports stay comparable; what it
    means is "the reader that is NOT the repo reader".

    pypdf cannot supply image geometry, so shares come back empty and
    `page_image_share` is applied by the repo reader's row only.
    """
    try:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        if getattr(r, "is_encrypted", False) and not r.decrypt(""):
            return None
        return [(pg.extract_text() or "") for pg in r.pages], []
    except Exception:                                            # noqa: BLE001
        return None


def summarise(rows: list[dict], *, reader: str =
              "checker/pdf_pages.extract_pages (pdfplumber; offline tooling)") -> dict:
    totals: dict[str, int] = {}
    for r in rows:
        for label, n in r["counts"].items():
            totals[label] = totals.get(label, 0) + n
    seen = [r["text_over_page_image"] for r in rows
            if r.get("text_over_page_image") is not None]
    return {"scope": SCOPE,
            "reader": reader,
            "heuristics": {"MIN_WORDS_FOR_TEXT": MIN_WORDS_FOR_TEXT,
                           "MIN_WORD_SHARE": MIN_WORD_SHARE,
                           "MAX_NON_ASCII_SHARE": MAX_NON_ASCII_SHARE,
                           "COVERS_PAGE": COVERS_PAGE},
            "documents": len(rows),
            "reader_failed": [r["document"] for r in rows if r["reader_failed"]],
            "page_totals": totals,
            "text_over_page_image": sum(seen) if seen else None,
            "rows": rows}


def run_census() -> dict:
    """Corpus totals from the independent reader; the repository reader beside them.

    The first single-reader run measured checker/pdf_text rather than the corpus
    (see _test), so page totals are taken from pdfplumber and the repo reader's
    view is reported next to them with the per-document disagreement.
    """
    from checker.pdf_pages import extract_pages
    independent_rows, repo_rows, comparison = [], [], []
    for p in sorted(CORPUS.rglob("*.pdf")):
        name = str(p.relative_to(CORPUS))
        repo = extract_pages(p)
        read = _pdfplumber_read(p)
        ind, shares = read if read is not None else (None, None)
        repo_rows.append(census_pages(name, repo))
        if ind is not None:
            independent_rows.append(census_pages(name, ind, image_shares=shares))
        comparison.append(compare_readers(name, repo_pages=repo, independent_pages=ind))
    report = summarise(independent_rows, reader="pypdf 6.16.1, the independent oracle (declared in "
                                                 "requirements-dev.txt)")
    repo_summary = summarise(repo_rows)
    report["repo_reader"] = {"reader": repo_summary["reader"],
                             "page_totals": repo_summary["page_totals"],
                             "reader_failed": repo_summary["reader_failed"]}
    report["reader_comparison"] = {
        "documents_agreeing": sum(1 for c in comparison if c["agree"]),
        "documents": len(comparison), "rows": comparison}
    return report


def _test() -> None:
    ok = fail = 0

    def c(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("text_layer_census")

    prose = ("The Board of Directors of the Company at its meeting held on "
             "14 June 2024 approved the audited financial statements for the "
             "financial year ended 31 March 2024 and recommended a dividend.")
    c(classify_page(prose) == TEXT, "ordinary prose is TEXT")
    c(classify_page("") == NO_TEXT_EXTRACTED,
      "an empty page is NO_TEXT_EXTRACTED -- this reader got nothing")
    c(classify_page("   \n\t  ") == NO_TEXT_EXTRACTED,
      "...and so is whitespace")
    c(NO_TEXT_EXTRACTED != "SCANNED" and "scan" not in NO_TEXT_EXTRACTED.lower(),
      "no label claims a page is scanned -- an empty result is a property of "
      "the reader until something that renders the page says otherwise")

    # R5, LARGE_DOCUMENT_PROFILE C-1: a units header letter-shifted in the layer.
    shifted = ("DOODPRXQWVLQ WKRXVDQGXQOHVVRWKHUZLVHVWDWHG " * 6).strip()
    c(classify_page(shifted) == SUSPECT,
      "a letter-shifted layer (R5's real corrupted units header) is SUSPECT")
    glyphs = "ZeƉorƚ >iŵiƚaƚioŶƐ " * 8
    c(classify_page(glyphs) == SUSPECT,
      "a broken-ToUnicode layer (R5 pp.493/505) is SUSPECT")
    c(classify_page("Note 23 12,345 (6,789) 1,00,000 45,678 9,87,654") == SUSPECT,
      "a numbers-only table page is SUSPECT, not TEXT -- few words is not a "
      "usable prose layer, and saying so is cheaper than trusting it")

    # ── the census over a document ──────────────────────────────────────────
    pages = [prose, "", shifted]
    row = census_pages("fixture.pdf", pages)
    c(row["pages"] == 3 and row["counts"] == {TEXT: 1, NO_TEXT_EXTRACTED: 1, SUSPECT: 1},
      f"a document row counts every page by label ({row['counts']})")
    c([p["page_index"] for p in row["per_page"]] == [0, 1, 2],
      "pages are identified by PDF page index, not a printed label")
    c(census_pages("unreadable.pdf", [])["reader_failed"] is True,
      "an empty page list is reader_failed -- pdf_text returns [] when it cannot "
      "read the page tree, and that is never a zero-page document")

    # ── two readers, and their disagreement is the finding ──────────────────
    # First run, 14-09-2026: checker/pdf_text extracted text from 2 of 135 pages
    # and got page counts of 1 and 0 for guidance notes pypdf reads as 169 and
    # 179 pages -- while R5 and MANIFEST.md record every page as text-bearing. A
    # census from one reader measured the reader. So each document is read twice:
    # by the repository's stdlib reader and by pdfplumber (already a declared dev
    # dependency), and disagreement is reported, never averaged away.
    good = [prose] * 3
    same = compare_readers("a.pdf", repo_pages=good, independent_pages=good)
    c(same["agree"] is True and same["page_count_mismatch"] is False,
      "two readers that see the same pages and labels agree")
    blind = compare_readers("b.pdf", repo_pages=["", "", ""], independent_pages=good)
    c(blind["agree"] is False and blind["pages_repo_missed"] == 3,
      f"a repo reader that sees nothing where the independent reader sees text is "
      f"reported, page by page ({blind['pages_repo_missed']} missed)")
    short = compare_readers("c.pdf", repo_pages=[prose], independent_pages=good)
    c(short["page_count_mismatch"] is True and short["agree"] is False,
      "a different page count is a disagreement in its own right -- pdf_text "
      "returned 1 page for a 169-page file")
    # The first two-reader run printed "repo missed text on 0 page(s)" for the
    # 1-of-169 and 0-of-179 files: the miss count only walked pages both readers
    # returned. Pages the repo reader never returned are missed too.
    c(short["pages_repo_missed"] == 2,
      f"a page the repo reader never returned counts as missed "
      f"({short['pages_repo_missed']} of 2)")
    c(compare_readers("f.pdf", repo_pages=[], independent_pages=good)["pages_repo_missed"] == 3,
      "...so a reader that returns no pages for a 3-page file missed all 3")
    over = compare_readers("d.pdf", repo_pages=good + [prose] * 2, independent_pages=good)
    c(over["page_count_mismatch"] is True,
      "...in either direction: it returned 37 pages for a 22-page file")
    c(compare_readers("e.pdf", repo_pages=good, independent_pages=None)["independent_failed"],
      "an independent reader that cannot open the file is recorded, not skipped")

    # ── text laid over a page-covering image: an OCR'd scan, which words cannot see ─
    # 14-09-2026: all 14 pages of _raw/rm_bm_20250128.pdf are full-page images under
    # someone else's OCR layer, and the errors are in the FIGURES ('1.1124.31',
    # '621.8.)', '7.(,4'). The word heuristic called 10 of those pages TEXT. The
    # signal that does see it is geometric: one image covering the page.
    c(page_image_share([{"x0": 0, "x1": 612, "top": 0, "bottom": 792}], 612, 792) >= COVERS_PAGE,
      "a single image the size of the page covers it")
    c(page_image_share([{"x0": 20, "x1": 120, "top": 20, "bottom": 60}], 612, 792) < COVERS_PAGE,
      "a letterhead logo does not")
    c(page_image_share([], 612, 792) == 0.0 and page_image_share([], 0, 0) == 0.0,
      "no image, or a page with no area, covers nothing")
    scanned = census_pages("g.pdf", [prose, prose], image_shares=[1.0, 0.05])
    c(scanned["text_over_page_image"] == 1
      and scanned["per_page"][0]["text_over_page_image"] is True
      and scanned["counts"] == {TEXT: 2},
      "a TEXT page over a page-covering image is counted apart -- the label says "
      "what the words look like, this says the words may be someone else's OCR")
    c(census_pages("h.pdf", [prose])["text_over_page_image"] is None,
      "a reader that reports no image geometry records None, never 0 -- the repo "
      "reader cannot see images, and 0 would claim it looked")

    report = summarise([row])
    c(report["heuristics"] == {"MIN_WORDS_FOR_TEXT": MIN_WORDS_FOR_TEXT,
                               "MIN_WORD_SHARE": MIN_WORD_SHARE,
                               "MAX_NON_ASCII_SHARE": MAX_NON_ASCII_SHARE,
                               "COVERS_PAGE": COVERS_PAGE},
      "the report carries its thresholds, labelled as heuristics")
    c("not the 20-document test" in report["scope"],
      "...and says in words what it is not")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
        raise SystemExit(0)
    report = run_census()
    OUT.write_text(json.dumps(report, indent=1))
    print(f"CORPUS (independent reader: {report['reader']})")
    print(f"  {report['documents']} documents; pages by label: {report['page_totals']}; "
          f"text over a page-covering image (OCR we did not do): "
          f"{report['text_over_page_image']}")
    for r in report["rows"]:
        over = r["text_over_page_image"]
        print(f"  {r['document']:<44} {r['pages']:>4} pp  {r['counts']}"
              + (f"  [text over page image: {over}]" if over else ""))
    rr, cmp_ = report["repo_reader"], report["reader_comparison"]
    print(f"\nREPO READER ({rr['reader']})")
    print(f"  pages by label: {rr['page_totals']}; reader failed on: "
          f"{rr['reader_failed'] or 'none'}")
    print(f"  agrees with the independent reader on {cmp_['documents_agreeing']} of "
          f"{cmp_['documents']} documents")
    for c_ in cmp_["rows"]:
        if not c_["agree"]:
            print(f"  DISAGREE {c_['document']:<44} repo {c_['repo_pages']} pp vs "
                  f"{c_['independent_pages']} pp; repo missed text on "
                  f"{c_['pages_repo_missed']} page(s)")
    print(f"heuristics (not measurements): {report['heuristics']}")
    print(f"scope: {report['scope']}")
    print(f"written: {OUT.relative_to(ROOT)}")
