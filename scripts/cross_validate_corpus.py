"""
Compare the two renderings of the Companies Act we already hold.

Why this exists: the corpus was fetched from India Code's JSON endpoint; the section index was
built from India Code's full-Act PDF. Two different extraction pipelines rendering the same law,
never once compared. If they disagree about what a section says, that is a source or extraction
defect, and nothing in the test suite would otherwise notice it.

On circularity -- the trap this project has fallen into before. The index was BUILT by matching
corpus records against the PDF, so comparing the matched region proves nothing. Matching used five
60-character probes at offsets 0-320, about 17.5% of the corpus. This script reports the tail
(the other 82.5%) separately, because only the tail is an independent check.

This is NOT full independence: both renderings come from the same publisher. It cannot detect an
error present in India Code's own source. It can detect extraction defects, truncation, and
divergence between their two delivery paths.

Run: python3 scripts/cross_validate_corpus.py
"""
from __future__ import annotations

import importlib.util
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus/companies_act"
PDF_TXT = ROOT / "corpus/sources/companies_act_2013_indiacode.txt"
PROBE_REGION = 320  # chars the index matcher already used; the tail beyond this is the real test


def _builder():
    """Reuse the index builder's own offset logic, so this slices exactly the body the index used
    rather than a re-implementation that could drift (or re-hit the arrangement table)."""
    spec = importlib.util.spec_from_file_location("bsi", ROOT / "scripts/build_section_index.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def norm(s: str) -> str:
    """Collapse to comparable letters and digits.

    Both renderings carry different noise: the PDF injects page numbers, running headers and
    footnote digits mid-sentence; the JSON carries HTML and <sup> markers. Punctuation and case
    differ freely. Comparing bare alphanumerics is crude but it is the only fair basis -- anything
    finer would report formatting as disagreement.
    """
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s.lower())


# A differing region is only interesting if it is NOT one of the three known structural
# differences between these renderings. Anything left over is a real divergence.
_PAGENUM = re.compile(r"^\d{1,4}$")
_CITATION = re.compile(r"(subsby|insby|omittedby|wef|act\d+of\d{4}|sor\d+e|ibid|vide)")


def explain(region: str, title_n: str, num: str, footnote_n: str) -> str:
    """Why this region differs. UNEXPLAINED is the only answer that matters."""
    if not region:
        return "empty"
    if _PAGENUM.match(region):
        return "page number"          # PDF injects page numbers mid-sentence
    if region.startswith(num) and title_n[:14] and title_n[:14] in region:
        return "section heading"      # JSON content starts at "(1)"; the PDF carries the heading
    if footnote_n and region in footnote_n:
        return "footnote"             # PDF interleaves footnotes; JSON keeps them in a field
    if _CITATION.search(region):
        return "amendment citation"   # footnote text the JSON stores separately
    return "UNEXPLAINED"


def main() -> None:
    b = _builder()
    text = PDF_TXT.read_text()
    arrangement = b.parse_arrangement(text)
    offs = b.body_offsets(text, arrangement)
    idx = json.loads((CORPUS / "_index.json").read_text())["entries"]

    ordered = [(n, t) for n, t in arrangement if n in offs]
    bounds = {}
    for i, (num, _) in enumerate(ordered):
        nxt = offs[ordered[i + 1][0]] if i + 1 < len(ordered) else len(text)
        bounds[num] = (offs[num], nxt)

    rows, skipped = [], 0
    for num, e in idx.items():
        sid = e.get("section_id")
        if not sid or num not in bounds:
            skipped += 1
            continue
        lo, hi = bounds[num]
        pdf_n = norm(text[lo:hi])
        rec = json.loads((CORPUS / f"{sid}.json").read_text())["content"]
        json_n = norm(rec)
        if len(json_n) < 40:
            skipped += 1
            continue

        sm = SequenceMatcher(None, json_n, pdf_n, autojunk=False)
        # One-sided coverage, NOT SequenceMatcher.ratio(). ratio() is symmetric, so a PDF slice
        # much longer than the record collapses the score even on perfect agreement -- s.470 is
        # the last section in the arrangement, so its slice runs to end-of-document and swallows
        # every schedule (445 chars of record against 285,803 of slice, ratio 0.004). That
        # measures slice length, not disagreement. What we actually want to know is: how much of
        # the corpus record is present in the PDF?
        matched = sum(bl.size for bl in sm.get_matching_blocks())
        ratio = matched / len(json_n)
        title_n = norm(e.get("title", ""))
        foot_n = norm(json.loads((CORPUS / f"{sid}.json").read_text()).get("footnote") or "")

        unexplained = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            for region in (json_n[i1:i2], pdf_n[j1:j2]):
                if explain(region, title_n, num, foot_n) == "UNEXPLAINED":
                    unexplained.append(region)

        tail_len = max(0, len(json_n) - PROBE_REGION)
        rows.append((num, sid, ratio, tail_len, unexplained))

    total = len(rows)
    ratios = sorted(r[2] for r in rows)
    clean = [r for r in rows if not r[4]]
    dirty = sorted((r for r in rows if r[4]), key=lambda r: -sum(len(u) for u in r[4]))

    print(f"sections compared            : {total}   (skipped {skipped})")
    print(f"independent tail chars       : {sum(r[3] for r in rows):,} "
          f"(text beyond the index-matching region)")
    print()
    print(f"median record coverage       : {ratios[len(ratios)//2]:.4f}")
    print(f"lowest record coverage       : {ratios[0]:.4f}")
    print(f"sections >= 0.99             : {sum(1 for r in ratios if r >= 0.99)}/{total}")
    print(f"sections >= 0.95             : {sum(1 for r in ratios if r >= 0.95)}/{total}")
    print()
    print(f"AGREE once heading/page-number/footnote accounted for : {len(clean)}/{total} "
          f"({len(clean)/total*100:.1f}%)")
    print(f"with UNEXPLAINED differences                          : {len(dirty)}")

    for num, sid, ratio, tl, un in dirty[:12]:
        chars = sum(len(u) for u in un)
        print(f"\n  s.{num:<6} id={sid:<7} ratio={ratio:.4f}  {chars} unexplained chars "
              f"-- {idx[num]['title'][:34]}")
        for u in un[:2]:
            print(f"      {u[:88]!r}")
    if len(dirty) > 12:
        print(f"\n  ... and {len(dirty)-12} more")

    out = ROOT / "reports/corpus_cross_validation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "what": "India Code JSON corpus vs India Code full-Act PDF",
        "independence": "PARTIAL - same publisher, two delivery paths. Cannot detect an error "
                        "present in India Code's own source.",
        "circularity_note": f"The index was built by matching the first ~{PROBE_REGION} chars. "
                            "Only the tail figure below is an independent check.",
        "sections_compared": total,
        "independent_tail_chars": sum(r[3] for r in rows),
        "metric": "one-sided: fraction of the JSON record found in the PDF slice",
        "median_record_coverage": round(ratios[len(ratios) // 2], 4),
        "agree_after_structural": len(clean),
        "unexplained_sections": [
            {"section": n, "id": s, "ratio": round(rt, 4),
             "unexplained_chars": sum(len(u) for u in un),
             "samples": [u[:120] for u in un[:3]]}
            for n, s, rt, _, un in dirty],
    }, indent=2))
    print(f"\nwritten: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
