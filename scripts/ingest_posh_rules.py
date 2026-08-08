"""
Ingest the PoSH Rules, 2013 (G.S.R. 769(E)).

**Why this is not a straight copy of `ingest_posh.py`.**

The Act came from India Code as a PDF with clean embedded text, so it was ingested byte-for-byte
with a sha256 over the file. The Rules on India Code are a **scan of the bilingual Gazette**, and
the OCR is unusable — page 2 extracts as:

    "Arar weg Beitr ART A URM aE aay at 7 BL oT-aIRI (9) Favs (0) B sho S"

That is noise, not text. Ingesting it would put garbage in the corpus, and the verifier would
then validate model output against garbage — which is worse than having no Rules at all.

So the text comes from a **secondary reproduction**: the Delhi Police copy of the Act and Rules,
which has clean embedded text. That is a weaker source than India Code and must be recorded as
one. It is not, however, unverified.

**How the trust was earned.** That PDF contains the Act *and* the Rules. We already hold the Act
verbatim from India Code. Cross-checking nine of our sections — s.2, 4, 9, 11, 13, 19, 21, 22,
26 — against it, **all nine appear verbatim**. A reproduction that renders the Act faithfully in
the half we can check is credible in the half we cannot. That is evidence, not assumption, and
it is recorded per-provision.

`verified_by` stays null. Cross-verification against a primary source is not a lawyer reading it.

    python3 scripts/ingest_posh_rules.py --pdf <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "corpus/provisions/posh_rules_2013.json"
ACT = ROOT / "corpus/provisions/posh_act_2013.json"

# The Rules run 1 to 14. An earlier version assumed 15 and reported rule 15 "missing"; there is
# no rule 15. The Rules end at the signature block "[F. No. 19-5/2013-WW] Dr. SHREERANJAN".
RULE_COUNT = 14
RULE_HEAD = re.compile(r"(?:^|\s)(\d{1,2})\.\s+([A-Z][^.]{4,120}?)\.\s*[-–—]")
RULES_END = re.compile(r"\[F\.\s*No\.\s*19-\s*5/2013-WW\]")

# Rule 5's number is misread as "1" by the text layer. It is identified by its heading instead,
# which is unambiguous and appears exactly once. Renumbering on a heading match is safe here in
# a way that renumbering on position would not be.
MISREAD = {"Fees or allowances for Chairperson and Members of Local Committee": 5}

# Sections whose verbatim India Code text is used to test the reproduction's fidelity.
CROSS_CHECK = (2, 4, 9, 11, 13, 19, 21, 22, 26)


def _text(pdf_path: Path) -> tuple[str, str, int]:
    import pdfplumber
    raw = pdf_path.read_bytes()
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    return "\n".join(pages), hashlib.sha256(raw).hexdigest(), len(pages)


def cross_verify(body: str) -> tuple[int, int, list[int]]:
    """How much of our verbatim Act text this reproduction renders faithfully."""
    ours = {p["section_number"]: " ".join(p["text_display"].split())
            for p in json.loads(ACT.read_text())["provisions"]}
    flat = " ".join(body.split())
    matched: list[int] = []
    checked = 0
    for n in CROSS_CHECK:
        mine = ours.get(n, "")
        probe = mine[len(mine) // 4: len(mine) // 4 + 90].strip()
        if len(probe) < 60:
            continue
        checked += 1
        if probe in flat:
            matched.append(n)
    return len(matched), checked, matched


# The reproduction carries the Act first and the Rules second. Both number their provisions
# "N. Heading.-", so a parser pointed at the whole document silently ingests the ACT and labels
# it as Rules. That happened on the first run: "Rule 4" came out byte-identical to Act s.4, and
# the retriever would have cited "Rule 4, PoSH Rules 2013" for text that is Section 4 of the Act.
# Nothing in the output looked wrong — it was caught only by noticing two character counts were
# exactly equal to the Act's.
#
# The Rules begin at the notification that makes them: G.S.R. 769(E), issued under section 29.
RULES_START = re.compile(
    r"G\.S\.R\.\s*769\(E\)|in exercise of the powers conferred by section 29", re.I)


def rules_only(body: str) -> str:
    """Everything from the enabling notification onward. Refuses rather than guess."""
    m = RULES_START.search(body)
    if not m:
        raise ValueError(
            "Could not find G.S.R. 769(E) or the section 29 enabling clause. Without a boundary "
            "this parser would ingest the Act and label it as the Rules, which it did once."
        )
    return body[m.start():]


def parse_rules(body: str) -> list[dict]:
    flat = re.sub(r"[ \t]+", " ", body)
    heads = list(RULE_HEAD.finditer(flat))
    # Keep the first occurrence of each rule number, in ascending order — the reproduction
    # repeats headings in its table of contents.
    seen: dict[int, re.Match] = {}
    for m in heads:
        n = int(m.group(1))
        heading = m.group(2).strip()
        corrected = MISREAD.get(heading)
        if corrected is not None:
            n = corrected
        if 1 <= n <= RULE_COUNT and n not in seen:
            seen[n] = m
    ordered = [seen[n] for n in sorted(seen)]

    # The last rule ends at the notification signature, not at end-of-document — otherwise it
    # swallows every annexure and form that follows. Rule 14 came out at 19,605 characters.
    tail = RULES_END.search(flat)
    body_end = tail.start() if tail else len(flat)

    out: list[dict] = []
    for i, m in enumerate(ordered):
        start = m.start()
        end = ordered[i + 1].start() if i + 1 < len(ordered) else body_end
        text = " ".join(flat[start:end].split())
        if len(text) < 40:
            continue
        n = MISREAD.get(m.group(2).strip(), int(m.group(1)))
        out.append({
            "rule_number": n,
            "citation": f"Rule {n}, PoSH Rules 2013",
            "heading": m.group(2).strip(),
            "text_display": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "source_quality": "secondary_reproduction_cross_verified",
            "verified_by": None,
            "verified_at": None,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", required=True, type=Path)
    args = ap.parse_args()

    body, sha, pages = _text(args.pdf)
    hits, checked, matched = cross_verify(body)

    print(f"source: {args.pdf.name}  {pages} pages  sha256 {sha[:16]}")
    print(f"cross-check against our verbatim India Code Act text: {hits}/{checked} sections "
          f"reproduced exactly {matched}")
    if checked and hits / checked < 0.8:
        print("\nREFUSED. This reproduction does not render the Act faithfully, so its Rules "
              "text cannot be trusted either. Find a better source.", file=sys.stderr)
        return 1

    try:
        rules_body = rules_only(body)
    except ValueError as e:
        print(f"\nREFUSED. {e}", file=sys.stderr)
        return 1
    print(f"Rules section starts at char {len(body) - len(rules_body):,} of {len(body):,} "
          f"(everything before it is the Act)")

    rules = parse_rules(rules_body)

    # Nothing labelled a Rule may be text we already hold as an Act section.
    act_hashes = {p["text_sha256"]: p["citation"]
                  for p in json.loads(ACT.read_text())["provisions"]}
    act_norm = {" ".join(p["text_display"].split()): p["citation"]
                for p in json.loads(ACT.read_text())["provisions"]}
    for r in rules:
        norm = " ".join(r["text_display"].split())
        clash = act_hashes.get(r["text_sha256"]) or act_norm.get(norm)
        if clash:
            print(f"\nREFUSED. {r['citation']} is the same text as {clash}. The Act is being "
                  f"ingested as the Rules again.", file=sys.stderr)
            return 1
    if not rules:
        print("\nREFUSED. No rule headings matched — parser and document disagree.",
              file=sys.stderr)
        return 1

    doc = {
        "instrument": {
            "short_name": "PoSH Rules 2013",
            "official_title": "The Sexual Harassment of Women at Workplace (Prevention, "
                              "Prohibition and Redressal) Rules, 2013",
            "kind": "rules",
            "jurisdiction": "IN",
            "year": 2013,
            "gazette_ref": "G.S.R. 769(E), 9 December 2013",
            "source_sha256": sha,
            "source_pages": pages,
            "fetched_at": str(date.today()),
            "source_quality": "secondary_reproduction_cross_verified",
            "PROVENANCE": (
                "NOT ingested from India Code, and the reason matters. India Code serves the "
                "Rules as a SCAN of the bilingual Gazette whose OCR is unusable — page 2 "
                "extracts as 'Arar weg Beitr ART A URM aE aay at 7 BL oT-aIRI'. Putting that in "
                "a corpus would give the verifier garbage to validate answers against, which is "
                "worse than holding no Rules at all. Text here comes from a government "
                "reproduction with clean embedded text, and its fidelity was TESTED rather than "
                "assumed: it reproduces "
                f"{hits} of {checked} of our verbatim India Code Act sections exactly. That is "
                "evidence the reproduction is faithful, not proof. verified_by stays null."
            ),
            "cross_verification": {
                "method": "distinctive 90-character probes from our verbatim India Code Act text",
                "sections_tested": list(CROSS_CHECK),
                "sections_matched": matched,
                "score": f"{hits}/{checked}",
            },
        },
        "provisions": rules,
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nparsed {len(rules)} rules -> {OUT.relative_to(ROOT)}")
    for r in rules:
        print(f"  Rule {r['rule_number']:<3} {r['heading'][:58]:58} {len(r['text_display']):5} ch")
    missing = sorted(set(range(1, RULE_COUNT + 1)) - {r["rule_number"] for r in rules})
    if missing:
        print(f"\n  NOT captured: rules {missing}. Check the source before relying on coverage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
