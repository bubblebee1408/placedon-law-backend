"""
Cross-validate the ingested corpus against an INDEPENDENT rendering of the same Act.

Why this exists: every other test in this repo is an internal consistency check. They prove the
code does what it was told, not that the data is right. This is the one non-circular check
available without buying a commercial database.

India Code publishes the Companies Act twice: as per-section JSON (what we ingest) and as a single
370-page PDF. Different pipelines, same source of truth. If the JSON text and the amendment
instruments both appear verbatim in the PDF, ingestion and the footnote parser are corroborated by
something we did not write.

SCOPE CORRECTION: the PDF is the CURRENT CONSOLIDATION, not the as-enacted 2013 print - it lists
sections 3A and 10A (inserted 2018/2019) and carries the full footnote apparatus. That does not
weaken THIS test, which only asks whether ingested text and parsed instruments appear in an
independently produced rendering of the same current Act. It does invalidate any use of this file
as a pre-amendment reference. See verify_reconstruction.py.

Normalisation strips all non-alphanumerics, which also neutralises the PDF's spurious intra-word
spaces ("an d preserve", "sub -section") from Word justification.

Run: python3 scripts/verify_against_pdf.py [--n 40]
Requires: /tmp/ca2013.pdf  (https://www.indiacode.nic.in/bitstream/123456789/2114/5/A2013-18.pdf)
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checker.amendment import parse_footnote  # noqa: E402

PDF = Path("/tmp/ca2013.pdf")
CACHE = Path("/tmp/ca2013.txt")
CORPUS = Path(__file__).resolve().parent.parent / "corpus/companies_act"
SEED = 7


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", re.sub(r"<[^>]+>", " ", s).lower())


def pdf_text() -> str:
    if CACHE.exists():
        return CACHE.read_text()
    import pdfplumber
    with pdfplumber.open(PDF) as pdf:
        txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
    CACHE.write_text(txt)
    return txt


def main() -> None:
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 40
    if not (PDF.exists() or CACHE.exists()):
        print(f"missing {PDF} — download the full-Act PDF first"); raise SystemExit(2)

    ref = norm(pdf_text())
    files = [p for p in CORPUS.glob("*.json") if not p.name.startswith("_")]
    rng = random.Random(SEED)

    # 1. Section text present in the independent rendering
    hit = miss = skip = 0
    missed: list[str] = []
    for p in rng.sample(files, min(n, len(files))):
        c = norm(json.loads(p.read_text())["content"])
        if len(c) < 120:
            skip += 1
            continue
        if c[60:220] in ref:
            hit += 1
        else:
            miss += 1
            missed.append(p.stem)

    # 2. Amendment instruments present in the independent rendering
    cands = []
    for p in files:
        rec = json.loads(p.read_text())
        for a in parse_footnote(rec["footnote"]):
            if a.instrument and a.wef and not a.wef_implausible:
                cands.append(a)
    rng.shuffle(cands)
    sample = cands[: n + 20]
    ihit = sum(1 for a in sample if norm(a.instrument) in ref)
    dhit = sum(1 for a in sample if f"wef{a.wef.day}{a.wef.month}{a.wef.year}" in ref)

    print("=== corpus cross-validation against independent PDF rendering ===")
    print(f"section text   : {hit}/{hit + miss} verbatim  ({hit / max(hit + miss, 1) * 100:.1f}%)"
          f"   [{skip} too short to probe]")
    if missed:
        print(f"  not matched  : {missed}")
    print(f"instruments    : {ihit}/{len(sample)} present  ({ihit / max(len(sample), 1) * 100:.1f}%)")
    print(f"w.e.f. dates   : {dhit}/{len(sample)} present  ({dhit / max(len(sample), 1) * 100:.1f}%)")
    print()
    print("Scope: corroborates INGESTION and the AMENDMENT LEDGER.")
    print("Does NOT corroborate point-in-time RECONSTRUCTION — verifying that a section as")
    print("reconstructed for a past date matches what it actually said then still requires an")
    print("independent as-amended edition for that date. That check does not yet exist.")


if __name__ == "__main__":
    main()
