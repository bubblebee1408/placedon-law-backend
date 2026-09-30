#!/usr/bin/env python3
"""A synthetic MCA "Company Master Data" PDF, written by hand, for testing the parser.

PLAN_26 §5 S2-alt. The parser needs a document to parse and this repository may not hold a
real company's master data: CLAUDE.md permits "public ICSI specimens, public listed-company
disclosures" and a master-data page pulled for one company is neither a specimen nor a
disclosure. So the fixture is invented, end to end, and says so in its own text.

## What is synthetic here, and what that costs

**The layout is a reconstruction, not a capture.** Nobody on this branch fetched a real
Company Master Data page — mca.gov.in's WAF is on CLAUDE.md's do-not-bypass list, and the
route the job describes is a user downloading the page THEMSELVES and uploading it. So the
field labels below are plausible and they are **UNVERIFIED against a real MCA page**.

That is a real limitation and it lands on the parser, not just the fixture: a label this
file spells `Whether Listed or not` and MCA spells `Whether listed or not?` would parse here
and fail there. Two things contain the damage:

    1. the parser matches labels case-insensitively, tolerates a trailing `?` or `:`, and
       accepts several spellings per field (`mca_master_data._LABELS`)
    2. a field it cannot find is ABSENT, never guessed -- and `parse_text` returns the
       labels it did not match, so a real upload that half-parses says which labels it
       did not recognise instead of quietly returning four facts out of eight

The first real upload is what validates the label table. Until then the parser is tested,
and the layout is not.

## The company is obviously fake

`U00000ZZ0000ZZZ000000` is a shape-valid CIN that cannot be a real one (`ZZ` is not a State
code and `0000` is not a year). The name says SYNTHETIC. The email is `.invalid`, reserved
by RFC 2606. Nothing here can be mistaken for a real company's record.

## The director block is part of the fixture on purpose

A real master-data page carries a Directors/Signatory table with names and DINs. The
fixture includes one **so that the test that they are never persisted has something to
catch**. A fixture without directors would make that test vacuous.

Run: PYTHONPATH=. python3 checker/sources/mca_fixture.py --test
"""
from __future__ import annotations

from pathlib import Path

# The synthetic record. One place, so the parser's expectations and the fixture cannot drift.
SYNTHETIC = {
    "cin": "U00000ZZ0000ZZZ000000",
    "name": "SYNTHETIC EXAMPLE PRIVATE LIMITED",
    "roc": "RoC-Synthetic",
    "incorporated_on": "14/08/2010",
    "address": "5 FORT STREET, SYNTHETIC CITY, Maharashtra, 400001",
    "state": "Maharashtra",
    "listed": "Unlisted",
    "status": "Active",
}

# Director rows. NEVER parsed into a fact; present so the no-personal-data test can fail.
SYNTHETIC_DIRECTORS = [("01234567", "SYNTHETIC DIRECTOR ONE"),
                       ("07654321", "SYNTHETIC DIRECTOR TWO")]

_HEADER = "Company Master Data"
DIRECTOR_HEADING = "Directors/Signatory Details"


def master_data_lines(rec: dict | None = None, *, directors: bool = True) -> list[str]:
    """The page as lines of text, in the order a reader would see them."""
    r = dict(SYNTHETIC if rec is None else rec)
    lines = [
        _HEADER,
        "This is a SYNTHETIC test fixture. It is not a real company's record.",
        "",
        f"CIN                              {r['cin']}",
        f"Company Name                     {r['name']}",
        f"ROC Code                         {r['roc']}",
        "Registration Number              000000",
        "Company Category                 Company limited by Shares",
        "Company SubCategory              Non-govt company",
        "Class of Company                 Private",
        "Authorised Capital(Rs)           1000000",
        "Paid up Capital(Rs)              500000",
        f"Date of Incorporation            {r['incorporated_on']}",
        f"Registered Address               {r['address']}",
        "Email Id                         info@example.invalid",
        f"Whether Listed or not            {r['listed']}",
        "ACTIVE compliance                ACTIVE",
        f"Company Status(for efiling)      {r['status']}",
    ]
    if directors:
        lines += ["",
                  DIRECTOR_HEADING,
                  "DIN/PAN      Name                        Begin date",
                  *[f"{din}     {name}     14/08/2010"
                    for din, name in SYNTHETIC_DIRECTORS]]
    return lines


def master_data_text(rec: dict | None = None, *, directors: bool = True) -> str:
    return "\n".join(master_data_lines(rec, directors=directors))


# ── a minimal PDF, written by hand ───────────────────────────────────────────
#
# Pure stdlib on purpose. Adding a PDF WRITER as a dependency to test a PDF READER would
# mean a test that passes because two libraries agree with each other. Hand-written bytes
# are what the reader is actually given in production.

def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(lines: list[str]) -> bytes:
    out = ["BT", "/F1 9 Tf", "12 TL", "40 800 Td"]
    for line in lines:
        out.append(f"({_escape(line)}) Tj")
        out.append("T*")
    out.append("ET")
    return "\n".join(out).encode("latin-1", "replace")


def _no_text_content() -> bytes:
    """A page that draws a grey box and no text: a scan, as far as any reader can tell."""
    return b"0.85 g\n40 40 515 760 re\nf\n"


def _build(content: bytes) -> bytes:
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length %d>>\nstream\n" % len(content) + content + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
    ]
    buf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_at = len(buf)
    buf += b"xref\n0 %d\n" % (len(objs) + 1)
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += b"%010d 00000 n \n" % off
    buf += (b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref_at))
    return bytes(buf)


def write_pdf(path: str | Path, *, rec: dict | None = None, directors: bool = True) -> Path:
    """A one-page PDF with a real text layer, in the master-data layout."""
    p = Path(path)
    p.write_bytes(_build(_content_stream(master_data_lines(rec, directors=directors))))
    return p


def write_scanned_pdf(path: str | Path) -> Path:
    """A one-page PDF with NO text layer. Stands in for a scan or a photographed page."""
    p = Path(path)
    p.write_bytes(_build(_no_text_content()))
    return p


def _test() -> int:
    import tempfile
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("sources.mca_fixture")
    text = master_data_text()
    check(_HEADER in text and "SYNTHETIC" in text, "the fixture text renders")
    check("SYNTHETIC" in SYNTHETIC["name"] and SYNTHETIC["cin"].startswith("U00000ZZ"),
          "the company is unmistakably fake: SYNTHETIC name, ZZ State code, 0000 year")
    check("example.invalid" in text,
          "the email is in .invalid, reserved by RFC 2606 so it can never resolve")
    check(DIRECTOR_HEADING in text and "01234567" in text,
          "the director block IS present -- without it the no-personal-data test is vacuous")
    check(master_data_text(directors=False).find(DIRECTOR_HEADING) == -1,
          "...and can be left out, for a page that has none")

    with tempfile.TemporaryDirectory() as d:
        p = write_pdf(Path(d) / "master.pdf")
        raw = p.read_bytes()
        check(raw.startswith(b"%PDF-"), "the written file opens with the %PDF magic bytes")
        check(raw.rstrip().endswith(b"%%EOF"), "...and ends with %%EOF")

        from checker.pdf_pages import extract_pages, page_count
        check(page_count(p) == 1, "pdfplumber reads it as one page")
        pages = extract_pages(p)
        got = pages[0]
        check(bool(got.strip()), f"...and finds a text layer ({len(got)} chars)")
        for field, value in (("cin", SYNTHETIC["cin"]), ("name", "SYNTHETIC EXAMPLE"),
                             ("listed", "Unlisted"), ("state", "Maharashtra")):
            check(value in got, f"...carrying {field}: {value[:30]!r}")
        check("01234567" in got,
              "...and the director DIN too: the parser must DROP it, not be handed a page "
              "without it")

        s = write_scanned_pdf(Path(d) / "scan.pdf")
        check(page_count(s) == 1, "the scanned fixture is also one page")
        scanned = extract_pages(s)
        check(len(scanned) == 1 and not scanned[0].strip(),
              f"...with NO text layer ({scanned[0][:20]!r}) -- which is the case the parser "
              f"must call 'cannot read' rather than 'no facts'")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    import tempfile
    d = Path(tempfile.mkdtemp())
    print(write_pdf(d / "mca_master_data_synthetic.pdf"))
    print(write_scanned_pdf(d / "mca_master_data_scanned.pdf"))
