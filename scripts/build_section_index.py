"""
Build the section_number -> section_id index for the Companies Act corpus.

Why this exists: the ingested corpus keys sections by India Code's internal sectionID (185, 48973,
49492...). The section NUMBER appears nowhere in the record — content begins at "(1)", the
sub-section. So s.173 was not findable at all. Nothing downstream works without this.

Why it reads the PDF: India Code's dynamic endpoints (/handle/, SectionPageContent) returned 404 on
20 Aug 2026 having worked hours earlier. The static full-Act PDF still serves. This runs entirely
offline against the already-extracted text, so it does not care whether the source is up.

Method:
  1. Parse the arrangement of sections from the PDF -> (number, title)
  2. Locate each section's body text in the PDF
  3. Fingerprint the body opening and match it to a corpus record
  4. Emit confidence and method per entry; never guess

Run: python3 scripts/build_section_index.py
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus/companies_act"
PDF_TXT = Path("/tmp/ca2013.txt")
OUT = CORPUS / "_index.json"

# "173. Meetings of Board." / "3A. Members severally liable..." / "11. [Omitted.]."
_ARR = re.compile(r"^(\d{1,3}[A-Z]{0,2})\.\s+(.{3,160}?)\.?\s*$", re.M)
_CHAPTER = re.compile(r"^CHAPTER\s+[IVXLC]+", re.M | re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"<[^>]+>", " ", s).lower())


# A contents line is followed by more numbered titles; a body opening is followed by prose.
# Measured on this PDF: contents runs score 7-13, real bodies 1-3.
LISTING = re.compile(r"\d{1,3}[A-Z]{0,2}\.\s*[A-Z\[]")
DENSITY_WINDOW = 400
DENSITY_MAX = 5
TITLE_MIN = 0.75


def title_score(text: str, off: int, num: str, title: str) -> float:
    """How well the text at `off` carries `title`. Amendments reword headings slightly -- the
    arrangement says "Loan to directors, etc" where the body says "Loans to directors, etc." -- so
    this is a similarity, not an equality."""
    head = text[off:off + len(num) + len(title) + 28]
    # Strip the number itself before comparing, including the "N[" amendment-span prefix that a
    # wholesale-substituted section carries ("3[185. Loans to directors" -> "Loans to directors").
    lead = re.match(r"(?:\d{1,3}\[)?" + re.escape(num) + r"\.\s*", head)
    head = head[lead.end():] if lead else head
    return SequenceMatcher(None, norm(title), norm(head)[:len(norm(title))]).ratio()


def parse_arrangement(text: str) -> list[tuple[str, str]]:
    """(number, title) from the arrangement block, which ends where the enacting text starts."""
    end = text.find("BE it enacted")
    block = text[:end if end > 0 else 60_000]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _ARR.finditer(block):
        num, title = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
        if num in seen or len(title) < 3:
            continue
        seen.add(num)
        out.append((num, title))
    return out


def body_offsets(text: str, arrangement: list[tuple[str, str]]) -> dict[str, int]:
    """Where each section's body starts in the PDF.

    A section number is NOT unique in this file, so first-match-wins is wrong. Two traps, both
    observed and both silent:

    1. The arrangement-of-sections table is repeated at the head of every chapter, so "56. Transfer
       and transmission of securities." appears as a contents line long before the real body.
       Contents lines sit in a dense run of other numbered titles; body text does not. That is what
       LISTING_DENSITY measures.
    2. The PDF also reproduces subordinate rules, which renumber from 1. The Act's s.56 is "Transfer
       and transmission of securities"; a rule's s.56 is "Director to intimate Director
       Identification Number". Only the title separates them.

    So: gather every candidate, keep those whose following text actually carries this section's own
    title, and among those prefer the one least like a contents listing.
    """
    start = text.find("BE it enacted")
    start = start if start > 0 else 0
    offs: dict[str, int] = {}
    for num, title in arrangement:
        # "\s*" not "\s+": extraction drops the space after the number ("207.Conduct of ...").
        # The optional "N[" prefix catches a section substituted wholesale, whose heading sits
        # inside the amendment span ("3[185. Loans to directors, etc.").
        pat = re.compile(r"(?:^|\d{1,3}\[)" + re.escape(num) + r"\.\s*\S", re.M)
        best: tuple[float, int] | None = None
        for m in pat.finditer(text, start):
            o = m.start()
            if title_score(text, o, num, title) < TITLE_MIN:
                continue
            density = len(LISTING.findall(text[o:o + DENSITY_WINDOW]))
            if density > DENSITY_MAX:
                continue
            rank = (title_score(text, o, num, title) - 0.05 * density, -o)
            if best is None or rank > best:
                best = rank
                offs[num] = o
    return offs


def main() -> None:
    if not PDF_TXT.exists():
        print(f"missing {PDF_TXT} — run scripts/verify_against_pdf.py first"); raise SystemExit(2)
    text = PDF_TXT.read_text()

    arrangement = parse_arrangement(text)
    print(f"arrangement entries parsed : {len(arrangement)}")

    numbers = [n for n, _ in arrangement]
    offs = body_offsets(text, arrangement)
    print(f"body offsets located       : {len(offs)}")

    # Corpus fingerprints: the first real run of characters of each record.
    records: dict[str, str] = {}
    for p in CORPUS.glob("*.json"):
        if p.name.startswith("_"):
            continue
        c = norm(json.loads(p.read_text())["content"])
        if len(c) >= 40:
            records[p.stem] = c
    print(f"corpus records             : {len(records)}")

    # Anchored matching. Earlier greedy matching drifted by one section - a record claimed by the
    # wrong number pushed every later assignment down, and the whole index shifted silently. So:
    # slice the PDF body for EXACTLY this section (heading N to heading N+1), then ask which corpus
    # record that slice contains. No global search, no claiming, no drift.
    ordered = [(n, t) for n, t in arrangement if n in offs]
    bounds: dict[str, tuple[int, int]] = {}
    for i, (num, _) in enumerate(ordered):
        nxt = offs[ordered[i + 1][0]] if i + 1 < len(ordered) else len(text)
        bounds[num] = (offs[num], nxt)

    index: dict[str, dict] = {}
    for num, title in arrangement:
        entry = {"section_number": num, "title": title, "section_id": None,
                 "confidence": "none", "method": "unmatched"}
        if "omitted" in title.lower():
            entry.update(confidence="n/a", method="omitted in source")
            index[num] = entry
            continue
        if num not in bounds:
            entry["method"] = "no body heading located in PDF"
            index[num] = entry
            continue

        lo, hi = bounds[num]
        body = norm(text[lo:min(hi, lo + 8000)])
        # score every record against THIS section's own text only
        scored = []
        for sid, rec in records.items():
            probes = [rec[o:o + 60] for o in (0, 40, 90, 160, 260) if len(rec) >= o + 60]
            if not probes:
                continue
            hits = sum(1 for pr in probes if pr in body)
            if hits:
                scored.append((hits, len(probes), sid))
        if not scored:
            index[num] = entry
            continue
        scored.sort(reverse=True)
        hits, nprobes, sid = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0
        ratio = hits / nprobes
        if hits >= 3 and hits > runner:
            conf = "high"
        elif hits >= 2 and hits > runner:
            conf = "medium"
        else:
            conf = "low"
        if conf == "low":
            entry["method"] = f"ambiguous ({hits} hits, runner-up {runner})"
        else:
            entry.update(section_id=sid, confidence=conf,
                         method=f"anchored body slice ({hits}/{nprobes} probes, runner-up {runner})")
        index[num] = entry

    matched = sum(1 for e in index.values() if e["section_id"])
    omitted = sum(1 for e in index.values() if e["method"] == "omitted in source")
    total = len(index) - omitted
    print(f"\nmatched                    : {matched}/{total} ({matched/max(total,1)*100:.1f}%)")
    print(f"omitted sections (no text) : {omitted}")
    claimed = {e["section_id"] for e in index.values() if e["section_id"]}
    dupes = [sid for sid in claimed
             if sum(1 for e in index.values() if e["section_id"] == sid) > 1]
    print(f"distinct records claimed   : {len(claimed)} of {len(records)}")
    print(f"DUPLICATE claims (a record mapped to >1 section): {len(dupes)}")
    if dupes:
        for sid in dupes[:5]:
            who = [n for n, e in index.items() if e["section_id"] == sid]
            print(f"    id {sid} claimed by sections {who}")

    OUT.write_text(json.dumps({"source": "India Code full-Act PDF, arrangement + body alignment",
                               "built_offline": True, "entries": index}, indent=1))
    print(f"written                    : {OUT}")

    MVP = ["96", "101", "102", "103", "114", "117", "173", "174", "175", "179", "184", "188"]
    EXT = ["177", "178", "180", "185", "186"]
    print("\n--- MVP sections ---")
    for n in MVP + EXT:
        e = index.get(n)
        tag = "core" if n in MVP else "ext "
        if not e:
            print(f"  {tag} s.{n:<4} NOT IN ARRANGEMENT")
        else:
            print(f"  {tag} s.{n:<4} id={str(e['section_id'] or '-'):<7} {e['title'][:52]}")


if __name__ == "__main__":
    main()
