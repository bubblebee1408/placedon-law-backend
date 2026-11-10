#!/usr/bin/env python3
"""
Section SEBI's consolidated LODR Regulations, 2015 into one record per regulation and schedule.

Structure only, and nothing here is served. Every record is HUMAN_REVIEW_PENDING
(checker/admission.py) with `production_usable: false`, exactly like
corpus/rules/board_powers_2014.json. The index makes a regulation lookup-able by NUMBER
(checker/section_index.py); it does not make one answerable. checker/legal_retrieval.py still
resolves Companies Act citations only.

## Why the PDF and not corpus/rules/sebi_lodr_2015.txt

The flat text file was the obvious input and it is not usable, for two measured reasons:

1. **It is truncated.** It holds 129 page-lines; the registered PDF has 230 pages. Chapter VI
   onward (regulations 63-103) and every Schedule are simply absent from it, ending mid-sentence
   in regulation 62Q. Sectioning it would have produced an index that reports "no such
   regulation" for regulation 64 -- an answer about our extractor wearing the authority of law.
2. **It loses text.** Its extractor dropped the quoted defined terms ('"associate" shall mean'
   reads '(b) shall mean'), and runs footnotes into the body.

So this reads the registered artifact itself, corpus/sources/sebi_lodr_2015_consolidated.pdf,
whose SHA-256 is pinned in corpus/sources/SHA256SUMS and sebi_lodr_registration.json and is
re-checked here before a byte is parsed. The flat file is left untouched: it is what
register_sebi_lodr.py hashed, and rewriting it would be repairing a source after the fact.

## How the structure is found (pdfplumber, offline only -- requirements-dev.txt)

The PDF's typography is regular enough to parse by it, not by guessing at words:
body text is 12 pt, footnotes 10 pt, the page number 11 pt; marginal headings, regulation
numbers and chapter titles are bold. A regulation starts at a body line whose leading number
token ("17.", "405[37A.", "64A.") is bold AND is the next number in sequence -- (n, next letter)
or (n+1, ""). Anything else is rejected and reported, so a quoted "57. (1)" inside a footnote
or a "7." in Schedule IX can never open a regulation. The bold lines immediately before a
regulation are its heading. Footnotes are numbered globally, so a 10 pt line opens footnote N
only if it starts with the next expected N; everything else continues the footnote before it.

Every line of every page lands in exactly one place (preamble, chapter header, heading,
content, footnote, page number), and the self-test proves the partition loses nothing against
an independent extraction of the same pages.

Run:  python3 scripts/section_sebi_lodr.py           # (re)write corpus/sebi_lodr/
      python3 scripts/section_sebi_lodr.py --test    # validate committed output + rebuild match
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "corpus/sources/sebi_lodr_2015_consolidated.pdf"
FLAT_TXT = ROOT / "corpus/rules/sebi_lodr_2015.txt"
OUT = ROOT / "corpus/sebi_lodr"
REL_PDF = "corpus/sources/sebi_lodr_2015_consolidated.pdf"

INSTRUMENT_ID = "SEBI_LODR_2015"
ARTIFACT_SHA = "f3c187d46aeb15e10d05614400e653086df1799e575ee4e11a49b5d28d5c9b67"
STATE = "HUMAN_REVIEW_PENDING"          # checker/admission.py; never servable
STATUS_NOTE = ("PENDING LEGAL REVIEW: sectioned by machine from SEBI's consolidation; no "
               "lawyer has checked any record. Not admitted for model use.")

BODY_PT, FOOTNOTE_PT, PAGENO_PT = 12.0, 10.0, 11.0
FN_SKIP = 2
LAST_REGULATION = 103                   # the Regulations' own last: "103. Repeal and Savings"
SCHEDULES = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")

_REG = re.compile(r"^(?:\d{1,3}\[)?\s*((\d{1,3})([A-Z]{0,2}))\s*\.(?:\s|$)")
_CHAPTER = re.compile(r"^(?:\d{1,3}\[)?\s*CHAPTER\s+([IVX]+(?:\s?-?\s?A)?)\b(.*)$")
_SCHEDULE = re.compile(r"^(?:\d{1,3}\[)?\s*SCHEDULE\s+([IVX]+)\b")
_FN_START = re.compile(r"^(\d{1,3})\s")
_AMENDED = re.compile(r"\[Amended up to ([A-Z][a-z]+ \d{1,2}, \d{4})\]")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── page -> classified lines ────────────────────────────────────────────────────
def _lines(pdf: Path) -> list[list[dict]]:
    import pdfplumber
    pages = []
    with pdfplumber.open(str(pdf)) as doc:
        for page in doc.pages:
            out = []
            for ln in page.extract_text_lines():
                chars = [c for c in ln["chars"] if c["text"].strip()]
                if not chars:
                    continue
                size = statistics.median(round(c["size"], 1) for c in chars)
                bold = [("Bold" in c["fontname"]) for c in chars]
                # Bold-ness of a line is judged on its LETTERS: a heading opens with a
                # regular-weight superscript footnote marker ("170[Maximum number...").
                letters = [b for c, b in zip(chars, bold) if c["text"].isalpha()]
                kind = ("pageno" if size == PAGENO_PT else
                        "footnote" if size <= FOOTNOTE_PT else "body")
                out.append({"text": ln["text"], "kind": kind, "bold": bold,
                            "all_bold": bool(letters) and sum(letters) >= 0.9 * len(letters)})
            pages.append(out)
    return pages


def _independent_text(pdf: Path) -> list[str]:
    """The same pages through pdfplumber's page-level extract_text -- a second path."""
    sys.path.insert(0, str(ROOT))
    from checker.pdf_pages import extract_pages
    return extract_pages(pdf)


def _token_bold(line: dict, m: re.Match) -> bool:
    """Is the regulation-number token itself bold? Offsets counted in non-space chars."""
    start = len(line["text"][:m.start(1)].replace(" ", ""))
    n = len(m.group(1))
    span = line["bold"][start:start + n]
    return bool(span) and all(span)


def _next_ok(prev: tuple[int, str], base: int, suf: str) -> bool:
    pb, ps = prev
    if base == pb + 1 and suf == "":
        return True
    if base == pb and suf:
        want = "A" if ps == "" else chr(ord(ps[-1]) + 1)
        return len(suf) == 1 and suf == want
    return False


def _clean_heading(raw: str) -> str:
    h = re.sub(r"\d{1,3}(?=[\[{])", "", raw)            # footnote markers glued to brackets
    h = re.sub(r"(?<=[\]}.])\d{1,3}\b", "", h)
    h = re.sub(r"[\[\]{}]", "", h)
    h = re.sub(r"\s+", " ", h).strip()
    return h.rstrip(".:").strip()


# ── the parse ───────────────────────────────────────────────────────────────────
def parse(pdf: Path = PDF) -> dict:
    data = pdf.read_bytes()
    if sha256(data) != ARTIFACT_SHA:
        raise SystemExit(f"{pdf}: SHA-256 is not the registered artifact {ARTIFACT_SHA}. "
                         "Refusing to section an unregistered document.")
    pages = _lines(pdf)

    first = " ".join(l["text"] for l in pages[0][:6])
    m = _AMENDED.search(first)
    if not m:
        raise SystemExit("no '[Amended up to ...]' line on page 1; refusing to guess the date")
    consolidated = datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()

    preamble: list[dict] = []
    chapters: list[dict] = []
    records: list[dict] = []
    footnotes: list[dict] = []
    rejected: list[dict] = []
    pagenos: list[str] = []
    cur: dict | None = None
    chapter: dict | None = None
    in_chapter_title = False
    prev = (0, "")
    in_schedules = False
    next_fn = 1
    skipped: list[str] = []

    def open_record(kind: str, number: str, page: int, heading_lines: list[str],
                    inline_heading: str = "") -> dict:
        raw = " ".join(heading_lines + ([inline_heading] if inline_heading else []))
        rec = {"kind": kind, "number": number, "heading_raw": raw,
               "chapter": dict(chapter) if chapter and kind == "regulation" else None,
               "lines": [], "page_start": page, "page_end": page}
        records.append(rec)
        return rec

    for pno, lines in enumerate(pages, 1):
        for ln in lines:
            t = ln["text"]
            if ln["kind"] == "pageno":
                pagenos.append(t); continue
            if ln["kind"] == "footnote":
                fm = _FN_START.match(t)
                # A footnote number the source skips (it prints 448 then 450) must not
                # stall the count, so the next two numbers are accepted -- and the gap is
                # recorded, never silently closed.
                if fm and next_fn <= int(fm.group(1)) <= next_fn + FN_SKIP:
                    skipped.extend(str(n) for n in range(next_fn, int(fm.group(1))))
                    footnotes.append({"number": fm.group(1), "page": pno, "lines": [t]})
                    next_fn = int(fm.group(1)) + 1
                elif footnotes:
                    footnotes[-1]["lines"].append(t)
                else:
                    preamble.append({"text": t, "all_bold": False, "page": pno})
                continue

            # body
            if in_chapter_title:
                if ln["all_bold"] and t.upper() == t and not _REG.match(t):
                    chapter["title_lines"].append(t); continue
                in_chapter_title = False
            cm = _CHAPTER.match(t)
            if cm and ln["all_bold"] and not in_schedules:
                chapter = {"number": re.sub(r"[\s-]", "", cm.group(1)), "header_lines": [t],
                           "title_lines": [], "page": pno}
                chapters.append(chapter)
                in_chapter_title = True
                continue
            sm = _SCHEDULE.match(t)
            if sm and ln["all_bold"]:
                roman = sm.group(1)
                if cur is None or cur["kind"] != "schedule" or cur["number"] != roman:
                    in_schedules = True
                    cur = open_record("schedule", roman, pno, [t])
                    continue
            rm = _REG.match(t) if not in_schedules else None
            # The number is bold almost everywhere; 26A and 59A print it regular-weight
            # under a bold heading. Either signal, and sequence is required in both cases.
            tail_now = cur["lines"] if cur is not None else preamble
            if rm and (_token_bold(ln, rm) or (tail_now and tail_now[-1]["all_bold"])):
                base, suf = int(rm.group(2)), rm.group(3)
                if _next_ok(prev, base, suf):
                    heading: list[str] = []
                    first_page = pno
                    while tail_now and tail_now[-1]["all_bold"]:
                        popped = tail_now.pop()
                        heading.insert(0, popped["text"])
                        first_page = popped["page"]
                    inline = t[rm.end():].strip() if ln["all_bold"] else ""
                    cur = open_record("regulation", rm.group(1), first_page, heading, inline)
                    prev = (base, suf)
                    cur["lines"].append({"text": t, "all_bold": False, "page": pno})
                    continue
                rejected.append({"page": pno, "text": t[:80],
                                 "reason": f"bold number {rm.group(1)} out of sequence "
                                           f"after {prev[0]}{prev[1]}"})
            elif rm and _next_ok(prev, int(rm.group(2)), rm.group(3)):
                # In sequence but with no typographic signal: never opened silently and
                # never dropped silently. A non-empty list fails validation.
                rejected.append({"page": pno, "text": t[:80],
                                 "reason": f"number {rm.group(1)} in sequence but neither "
                                           f"bold nor under a bold heading"})
            if cur is None:
                preamble.append({"text": t, "all_bold": ln["all_bold"], "page": pno})
            else:
                cur["lines"].append({"text": t, "all_bold": ln["all_bold"], "page": pno})
                cur["page_end"] = pno

    _place_footnotes(records, footnotes, chapters)
    return {"consolidated_up_to": consolidated, "marker": m.group(0),
            "preamble": [l["text"] for l in preamble],
            "chapters": chapters, "records": records, "footnotes": footnotes,
            "rejected": rejected, "pagenos": pagenos, "pages": len(pages),
            "footnote_numbers_absent": skipped}


def _marker_rx(n: str) -> re.Pattern:
    # The forms the source uses: "255[(1)", "551(2)", "]244.", "[***]372", "2008]15,".
    return re.compile(rf"(?<![\d.,/]){n}(?=\s?[\[{{(])|(?<=[\]}}])\s?{n}(?!\d)")


def _place_footnotes(records: list[dict], footnotes: list[dict],
                     chapters: list[dict]) -> None:
    """Attach each footnote to the record (or chapter header) carrying its marker on the
    footnote's page. Fallback, recorded per footnote: the record open on that page.
    """
    for fn in footnotes:
        rx = _marker_rx(fn["number"])
        entry = {"number": fn["number"], "page": fn["page"], "placed_by": "marker",
                 "text": "\n".join(fn["lines"])}
        ch = next((c for c in chapters if c["page"] == fn["page"] and any(
            rx.search(x) for x in c["header_lines"] + c["title_lines"])), None)
        if ch is not None:
            ch.setdefault("footnotes", []).append(entry)
            continue
        home, how = None, "marker"
        for rec in records:
            if rec["page_start"] <= fn["page"] <= rec["page_end"]:
                hay = [rec["heading_raw"]] + [l["text"] for l in rec["lines"]
                                              if l["page"] == fn["page"]]
                if any(rx.search(h) for h in hay):
                    home = rec; break
        if home is None:
            how = "page"
            open_at = [r for r in records if r["page_start"] <= fn["page"]]
            home = open_at[-1] if open_at else records[0]
        home.setdefault("footnotes", []).append({**entry, "placed_by": how})


# ── records on disk ─────────────────────────────────────────────────────────────
def _record_id(rec: dict) -> str:
    return ("R" + rec["number"]) if rec["kind"] == "regulation" else f"SCHEDULE_{rec['number']}"


def _index_key(rec: dict) -> str:
    return rec["number"] if rec["kind"] == "regulation" else f"SCHEDULE {rec['number']}"


_OMITTED = re.compile(r"^\W*(?:\d{1,3})?\W*\*{3}\W*(?:\d{1,3})?\W*$")


def _is_omitted(rec: dict, content: str) -> bool:
    body = content
    if rec["kind"] == "regulation":
        body = _REG.sub("", content, count=1)
    else:
        body = re.sub(r"^.*?SCHEDULE\s+[IVX]+", "", rec["heading_raw"]) + content
    return bool(_OMITTED.match(body.strip())) or body.strip() == ""


def build(parsed: dict) -> dict[str, bytes]:
    """Every output file, name -> bytes. Deterministic: no clock, sorted keys."""
    files: dict[str, bytes] = {}
    entries: dict[str, dict] = {}
    omitted: list[str] = []
    common = {"instrument_id": INSTRUMENT_ID, "source_artifact": REL_PDF,
              "source_artifact_sha256": ARTIFACT_SHA,
              "consolidated_up_to": parsed["consolidated_up_to"],
              "consolidation_marker": parsed["marker"],
              "admission_state": STATE, "production_usable": False, "status": STATUS_NOTE}
    for rec in parsed["records"]:
        rid = _record_id(rec)
        content = "\n".join(l["text"] for l in rec["lines"])
        heading = _clean_heading(rec["heading_raw"])
        if rec["kind"] == "schedule":
            heading = re.sub(r"^SCHEDULE\s+[IVX]+\s*[-:–]?\s*", "", heading).strip() or heading
        om = _is_omitted(rec, content)
        if om:
            omitted.append(_index_key(rec))
        ch = rec["chapter"]
        body = {
            "section_id": rid,
            "ref": (f"RULE:{INSTRUMENT_ID}:R{rec['number']}" if rec["kind"] == "regulation"
                    else None),
            "kind": rec["kind"], "number": rec["number"],
            "heading": heading, "heading_raw": rec["heading_raw"],
            "chapter": ({"number": ch["number"],
                         "title": " ".join(ch["title_lines"])} if ch else None),
            "omitted": om,
            "content": content,
            "footnotes": rec.get("footnotes", []),
            "page_start": rec["page_start"], "page_end": rec["page_end"],
            "sha256": sha256(content.encode()),
            **common,
        }
        files[f"{rid}.json"] = (json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode()
        entries[_index_key(rec)] = {
            "section_number": _index_key(rec), "title": heading, "section_id": rid,
            "kind": rec["kind"], "omitted": om,
            # "high" because the number is a bold token that is next in sequence; this is
            # a claim about the PARSE, and says nothing about legal review (admission_state).
            "confidence": "high",
            "method": "bold number token in sequence (pdfplumber, 12pt body)",
            "page_start": rec["page_start"]}
    regs = [r for r in parsed["records"] if r["kind"] == "regulation"]
    scheds = [r for r in parsed["records"] if r["kind"] == "schedule"]
    files["_index.json"] = (json.dumps({
        "source": "SEBI consolidated PDF, bold-number structure parse",
        "built_offline": True, "script": "scripts/section_sebi_lodr.py",
        **{k: common[k] for k in ("instrument_id", "source_artifact", "source_artifact_sha256",
                                  "consolidated_up_to", "admission_state",
                                  "production_usable", "status")},
        "entries": entries}, indent=1, ensure_ascii=False) + "\n").encode()
    placed = ([f for r in parsed["records"] for f in r.get("footnotes", [])]
              + [f for c in parsed["chapters"] for f in c.get("footnotes", [])])
    files["_manifest.json"] = (json.dumps({
        **common,
        "section_ids": [_record_id(r) for r in parsed["records"]],
        "count": len(parsed["records"]),
        "regulations": len(regs), "schedules": len(scheds),
        "last_regulation": regs[-1]["number"] if regs else None,
        "omitted": omitted,
        "pages": parsed["pages"],
        "footnotes": len(parsed["footnotes"]),
        "footnotes_placed_by_page_fallback": sum(f["placed_by"] == "page" for f in placed),
        "footnote_numbers_absent_from_source": parsed["footnote_numbers_absent"],
        "chapters": [{"number": c["number"], "title": " ".join(c["title_lines"]),
                      "header": " ".join(c["header_lines"]), "page": c["page"],
                      "footnotes": c.get("footnotes", [])}
                     for c in parsed["chapters"]],
        "preamble": "\n".join(parsed["preamble"]),
        "rejected_number_candidates": parsed["rejected"],
        "flat_text_not_used": {
            "path": "corpus/rules/sebi_lodr_2015.txt",
            "sha256": sha256(FLAT_TXT.read_bytes()) if FLAT_TXT.is_file() else None,
            "reason": "truncated: 129 page-lines of the PDF's 230 (ends in regulation 62Q; "
                      "regulations 63-103 and all Schedules absent) and drops quoted "
                      "defined terms. Left untouched; see the script docstring."},
    }, indent=1, ensure_ascii=False) + "\n").encode()
    names = sorted(n for n in files)
    files["SHA256SUMS"] = "".join(f"{sha256(files[n])}  {n}\n" for n in names).encode()
    return files


def write(files: dict[str, bytes]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        if old.name not in files:
            old.unlink()
    for name, data in files.items():
        (OUT / name).write_bytes(data)


# ── validation ──────────────────────────────────────────────────────────────────
ANCHORS = {"17": "Board of Directors", "23": "Related party transactions",
           "30": "Disclosure of events or information", "33": "Financial results",
           "34": "Annual Report", "1": "Short title and commencement", "2": "Definitions",
           "103": "Repeal and Savings", "17A": "Maximum number of directorships",
           "37A": "Sale, lease or disposal of an undertaking outside Scheme of Arrangement",
           "64A": "Applicability",
           "26A": "Vacancies in respect of certain Key Managerial Personnel",
           "59A": "Draft Scheme of Arrangement and Scheme of Arrangement"}


def validate(out: Path = OUT, check=None) -> tuple[int, int]:
    ok = fail = 0

    def c(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    idx = json.loads((out / "_index.json").read_text())
    man = json.loads((out / "_manifest.json").read_text())
    entries = idx["entries"]
    regs = [k for k, e in entries.items() if e["kind"] == "regulation"]
    bases = [int(re.match(r"\d+", k).group()) for k in regs]

    plain = [b for k, b in zip(regs, bases) if k.isdigit()]
    c(plain == list(range(1, LAST_REGULATION + 1)),
      f"every regulation 1..{LAST_REGULATION} appears exactly once, in order ({len(plain)})")
    c(len(set(regs)) == len(regs), f"no regulation number twice ({len(regs)} incl. lettered)")
    lettered = sorted({k for k in regs if not k.isdigit()},
                      key=lambda k: (int(re.match(r"\d+", k).group()), k))
    by_base: dict[int, list[str]] = {}
    for k in lettered:
        by_base.setdefault(int(re.match(r"\d+", k).group()), []).append(k[-1])
    c(all(v == [chr(ord("A") + i) for i in range(len(v))] for v in by_base.values()),
      f"lettered regulations run A, B, C... with no gap ({', '.join(lettered)})")
    scheds = [k for k, e in entries.items() if e["kind"] == "schedule"]
    c(scheds == [f"SCHEDULE {s}" for s in SCHEDULES],
      f"Schedules I-X each once, in order ({len(scheds)})")
    for num, want in ANCHORS.items():
        got = entries.get(num, {}).get("title")
        c(got == want, f"reg {num} heading is {want!r} (got {got!r})")
    c(man["omitted"] == sorted(man["omitted"], key=lambda k: list(entries).index(k))
      and all(entries[k]["omitted"] for k in man["omitted"]),
      f"omitted provisions listed explicitly from the text: {man['omitted']}")
    c("SCHEDULE VIII" in man["omitted"],
      "Schedule VIII, printed '[***]', is recorded as omitted rather than dropped")
    c(man["consolidated_up_to"] == "2026-07-14"
      and man["consolidation_marker"] == "[Amended up to July 14, 2026]",
      "consolidated-up-to date is read from the artifact's own first page")
    c(idx["production_usable"] is False and idx["admission_state"] == STATE,
      "the index is HUMAN_REVIEW_PENDING and not production usable")
    recs = [json.loads((out / f"{e['section_id']}.json").read_text()) for e in entries.values()]
    c(all(r["production_usable"] is False and r["admission_state"] == STATE for r in recs),
      f"every record ({len(recs)}) is pending legal review, none servable")
    c(all(r["source_artifact_sha256"] == ARTIFACT_SHA for r in recs),
      "every record names the registered artifact's hash")
    c(all(r["sha256"] == sha256(r["content"].encode()) for r in recs),
      "every record's content hash matches its content")
    sums = dict(reversed(l.split("  ")) for l in (out / "SHA256SUMS").read_text().splitlines())
    c(set(sums) == {p.name for p in out.iterdir()} - {"SHA256SUMS"}
      and all(sha256((out / n).read_bytes()) == h for n, h in sums.items()),
      f"SHA256SUMS covers every file and every hash holds ({len(sums)})")
    c(man["rejected_number_candidates"] == [],
      f"no bold number was rejected as out of sequence ({len(man['rejected_number_candidates'])})")
    c(man["footnotes_placed_by_page_fallback"] <= 0.02 * man["footnotes"],
      f"footnotes placed by marker, not page fallback: "
      f"{man['footnotes'] - man['footnotes_placed_by_page_fallback']}/{man['footnotes']}")
    return ok, fail


def _text_loss(parsed: dict, files: dict[str, bytes], check) -> None:
    """Every character of the source body lands in a record, a footnote, or the manifest."""
    def nonspace(s: str) -> int:
        return len(re.sub(r"\s", "", s))
    pages = _independent_text(PDF)
    source = sum(nonspace(p) for p in pages) - sum(nonspace(p) for p in parsed["pagenos"])
    recs = [json.loads(v) for k, v in files.items() if not k.startswith("_") and k.endswith(".json")]
    man = json.loads(files["_manifest.json"])
    held = (sum(nonspace(r["content"]) + nonspace(r["heading_raw"])
                + sum(nonspace(f["text"]) for f in r["footnotes"]) for r in recs)
            + nonspace(man["preamble"])
            + sum(nonspace(c["header"]) + nonspace(c["title"])
                  + sum(nonspace(f["text"]) for f in c["footnotes"]) for c in man["chapters"]))
    ratio = held / source
    check(abs(1 - ratio) <= 0.002,
          f"no text lost: records+footnotes+preamble+chapters hold {held:,} of {source:,} "
          f"non-space source characters ({ratio:.5f}, tolerance 0.2%)")


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    a, b = validate()
    ok += a; fail += b
    try:
        import pdfplumber  # noqa: F401
    except ImportError:
        print("pdfplumber unavailable: rebuild and text-loss checks skipped")
    else:
        parsed = parse()
        files = build(parsed)
        on_disk = {p.name: p.read_bytes() for p in OUT.iterdir()}
        check(files == on_disk,
              f"a fresh parse of the PDF reproduces corpus/sebi_lodr/ byte for byte "
              f"({len(files)} files) -- the script is deterministic and the output is not "
              f"hand-edited")
        _text_loss(parsed, files, check)
        flat = FLAT_TXT.read_text(encoding="utf-8").splitlines() if FLAT_TXT.is_file() else []
        check(len(flat) == 129 and parsed["pages"] == 230,
              f"the flat text file is the truncated one this script refuses to use "
              f"({len(flat)} page-lines vs {parsed['pages']} PDF pages)")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def main() -> None:
    parsed = parse()
    files = build(parsed)
    write(files)
    man = json.loads(files["_manifest.json"])
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}: {man['regulations']} "
          f"regulations, {man['schedules']} schedules, omitted {man['omitted']}, "
          f"consolidated up to {man['consolidated_up_to']}")
    for r in man["rejected_number_candidates"]:
        print(f"  rejected p{r['page']}: {r['reason']}: {r['text']}")
    a, b = validate()
    if b:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        main()
