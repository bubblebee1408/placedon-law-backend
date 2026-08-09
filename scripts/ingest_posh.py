"""
Ingest the PoSH Act 2013 — pipeline stages [1] FETCH, [2] PARSE, [3] SEGMENT.

Everything lands `verified_by: null`. Extraction of applicability conditions (stage [4]) and the
human gate (stage [6]) are separate; nothing here is servable to a customer.

Design notes that matter:

  * `text` is the RAW extraction, byte-for-byte from pdfplumber, and `text_sha256` hashes it.
    Verbatim means verbatim — the downstream "every number in the answer appears in the source"
    check compares against this. `text_display` carries the line-wrap-joined version for reading;
    it is never the thing we verify against.

  * The Act's own Arrangement of Sections (pages 1-2) is parsed independently and used to
    ASSERT completeness. If the body parser misses a section, the TOC diff catches it
    mechanically rather than leaving a silent hole in the corpus.

Run:  python3 scripts/ingest_posh.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "corpus" / "raw" / "posh_act_2013.pdf"
OUT = ROOT / "corpus" / "provisions" / "posh_act_2013.json"

SOURCE_URL = "https://www.indiacode.nic.in/bitstream/123456789/2104/1/A2013-14.pdf"
INSTRUMENT = "PoSH Act 2013"
OFFICIAL_TITLE = (
    "The Sexual Harassment of Women at Workplace "
    "(Prevention, Prohibition and Redressal) Act, 2013"
)
GAZETTE_REF = "Act No. 14 of 2013"
PUBLISHED = "2013-04-22"

# TOC lines look like:  "4. Constitution of Internal Complaints Committee."
TOC_LINE = re.compile(r"^\s*(\d{1,2})\.\s+(.+?)\.?\s*$")
# A section opens a line with its number. The heading may WRAP across a line break
# (s.16 does), so we only detect the START here and slice the heading separately.
BODY_START = re.compile(r"^(\d{1,2})\.\s+(?=[A-Z])", re.M)
# Heading runs until the em-dash terminator, possibly across one newline.
HEADING_END = re.compile(r"[.\s]*[—–]\s*")
# Chapter headings, so we can attribute each section to its chapter.
CHAPTER = re.compile(r"^\s*CHAPTER\s+([IVXL]+)\s*$", re.M)
# Amendment markers: "2[Local Committee]" — footnote 2 substituted this text.
# Load-bearing provenance. Preserved verbatim; recorded so the lawyer sees them.
AMENDMENT_MARK = re.compile(r"(\d+)\[")

FOOTNOTE_MARK = re.compile(r"^\s*\d+\.\s*(Subs\.|Ins\.|Omitted|Provided|w\.e\.f\.)", re.I)

# Pages 1-2 are the Arrangement of Sections; the Act proper starts on page 3.
BODY_FIRST_PAGE = 3


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# Footnote apparatus interleaved with the statute by the PDF's page furniture. The Act's
# footnotes sit at the foot of each page, and a section spanning a page break swallows them.
#
# This matters more than tidiness. `text_display` is what the number-checker compares a model's
# output against, so a footnote inside it WIDENS what counts as sourced: a model writing
# "6-5-2016" or "2016" against s.8 was accepted, because those digits appear in
# "Subs. by Act 23 of 2016 ... (w.e.f. 6-5-2016)" — editorial apparatus, not statute.
APPARATUS = re.compile(
    r"\s*\d+\.\s*(?:Subs|Ins|Omitted|Cl)\.\s+by\b.*?\(w\.e\.f\.[^)]*\)\s*\.?",
    re.I | re.S)
PAGE_NUM = re.compile(r"(?<=\.)\s+\d{1,2}\s+(?=[A-Z])")


def strip_apparatus(text: str) -> str:
    """
    Statutory text with footnotes and stray page numbers removed.

    Deliberately conservative: it removes only the recognised footnote form — a numbered
    "Subs./Ins./Omitted by ... (w.e.f. DATE)" — and page numbers stranded between sentences.
    Anything it does not recognise it leaves alone, because dropping statute is far worse than
    keeping apparatus. `text` retains everything; nothing is lost.
    """
    out = APPARATUS.sub(" ", text)
    out = PAGE_NUM.sub(" ", out)
    return " ".join(out.split())


def join_wraps(text: str) -> str:
    """Undo PDF line wrapping for display only. Never hashed, never verified against."""
    out = re.sub(r"-\n(?=[a-z])", "", text)          # de-hyphenate across a break
    out = re.sub(r"\n(?=[a-z(—])", " ", out)     # join a wrapped sentence
    return re.sub(r"[ \t]+", " ", out).strip()


def parse_toc(pages: list[str]) -> dict[int, str]:
    """The Act's own Arrangement of Sections — our completeness oracle."""
    toc: dict[int, str] = {}
    for page in pages[:2]:
        for line in page.splitlines():
            if CHAPTER.match(line) or "ARRANGEMENT" in line or "SECTIONS" == line.strip():
                continue
            m = TOC_LINE.match(line)
            if m:
                num = int(m.group(1))
                heading = m.group(2).strip()
                # A TOC entry is a heading, not prose: no trailing clause markers.
                if num not in toc and len(heading) > 3 and not heading.endswith((",", ";")):
                    toc[num] = heading
    return toc


def slice_heading(chunk: str) -> str:
    """
    Heading runs from the section number to the em-dash that opens the operative text.
    It may wrap across a line break — s.16 does — so join wraps before slicing.
    """
    body = re.sub(r"^\d{1,2}\.\s+", "", chunk)
    head = body[:400].replace("\n", " ")
    m = HEADING_END.search(head)
    return re.sub(r"\s+", " ", head[: m.start()] if m else head[:120]).strip(" .")


def parse_body(pages: list[str]) -> list[dict]:
    """Segment the operative text into sections, preserving page refs and chapter."""
    page_starts: list[tuple[int, int]] = []       # (abs_offset, page_number 1-indexed)
    parts: list[str] = []
    offset = 0
    for idx, page in enumerate(pages, start=1):
        page_starts.append((offset, idx))
        parts.append(page)
        offset += len(page) + 1
    blob = "\n".join(parts)

    # Only look at the operative text — pages 1-2 are the Arrangement of Sections, and
    # every section number appears there too.
    body_from = next(off for off, idx in page_starts if idx == BODY_FIRST_PAGE)

    chapters = [(m.start(), m.group(1)) for m in CHAPTER.finditer(blob)]

    def chapter_at(pos: int) -> str:
        out = ""
        for start, num in chapters:
            if start <= pos:
                out = num
            else:
                break
        return out

    def page_of(pos: int) -> int:
        page = 1
        for start, idx in page_starts:
            if start <= pos:
                page = idx
            else:
                break
        return page

    # Candidate starts, in document order, keeping only a strictly increasing run.
    # A section number that goes backwards is a footnote or a cross-reference, not a section.
    ordered: list[tuple[int, int]] = []
    highest = 0
    for m in BODY_START.finditer(blob, body_from):
        line_start = blob.rfind("\n", 0, m.start()) + 1
        if FOOTNOTE_MARK.match(blob[line_start:line_start + 60]):
            continue
        num = int(m.group(1))
        if num != highest + 1:
            continue
        highest = num
        ordered.append((m.start(), num))

    provisions: list[dict] = []
    for i, (start, num) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else len(blob)
        raw = blob[start:end].rstrip()
        amendments = sorted({int(n) for n in AMENDMENT_MARK.findall(raw)})
        provisions.append({
            "citation": f"s.{num}",
            "section_number": num,
            "chapter": chapter_at(start),
            "heading": slice_heading(raw),
            "text": raw,
            "text_sha256": sha256(raw.encode("utf-8")),
            "text_display": join_wraps(raw),
            # What a claim is checked against. See strip_apparatus.
            "text_statutory": strip_apparatus(join_wraps(raw)),
            "page_from": page_of(start),
            "page_to": page_of(end - 1),
            "ordinal": i,
            "char_count": len(raw),
            # Footnote numbers whose bracketed text was substituted or inserted by a
            # later amendment. Preserved in `text`; surfaced so the lawyer sees them.
            "amendment_markers": amendments,
            # ── the human gate ──────────────────────────────────────────
            "verified_by": None,
            "verified_at": None,
        })
    return provisions


def main() -> int:
    if not PDF.exists():
        print(f"missing {PDF} — fetch it first", file=sys.stderr)
        return 1

    pdf_bytes = PDF.read_bytes()
    with pdfplumber.open(PDF) as doc:
        pages = [(p.extract_text() or "") for p in doc.pages]

    toc = parse_toc(pages)
    provisions = parse_body(pages)
    got = {p["section_number"] for p in provisions}

    missing = sorted(set(toc) - got)
    extra = sorted(got - set(toc))
    mismatched = [
        (n, toc[n], p["heading"])
        for p in provisions
        if (n := p["section_number"]) in toc
        and toc[n].lower()[:22] != p["heading"].lower()[:22]
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "instrument": {
            "short_name": INSTRUMENT,
            "official_title": OFFICIAL_TITLE,
            "kind": "act",
            "jurisdiction": "IN",
            "year": 2013,
            "gazette_ref": GAZETTE_REF,
            "published_at": PUBLISHED,
            "source_url": SOURCE_URL,
            "source_sha256": sha256(pdf_bytes),
            "source_bytes": len(pdf_bytes),
            "source_pages": len(pages),
            "source_version_note": "PDF carries 'Last updated: 31-8-2021'",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fetch_method": "curl, browser UA (WebFetch client is 403'd; the site is not)",
            "ingested_by": "scripts/ingest_posh.py",
            "verified_by": None,
        },
        "completeness": {
            "toc_sections": len(toc),
            "parsed_sections": len(provisions),
            "missing_from_body": missing,
            "not_in_toc": extra,
            "heading_mismatches": mismatched,
        },
        "provisions": provisions,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"source     {PDF.relative_to(ROOT)}  {len(pdf_bytes):,}b  {len(pages)} pages")
    print(f"sha256     {sha256(pdf_bytes)}")
    print(f"TOC        {len(toc)} sections declared")
    print(f"parsed     {len(provisions)} sections")
    print(f"missing    {missing or '—'}")
    print(f"not in TOC {extra or '—'}")
    print(f"headings   {len(mismatched)} mismatched")
    print(f"verified   0 / {len(provisions)}  (all verified_by = null)")
    print(f"→ {OUT.relative_to(ROOT)}")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
