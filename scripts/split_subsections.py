"""
Make sub-sections addressable: s.2(o) as a unit, not 5,570 characters of s.2.

## The gap this closes

The corpus stores whole sections. s.2 is one blob of 5,570 characters containing every definition
in the Act. But the things we actually rely on are **clauses**: 2(o) defines "workplace", 2(n)
defines "woman", 4(1) creates the duty, 4(2) sets the composition.

Three consequences, and the third is the one that matters:

  * A citation to `s.2(o)` cannot be resolved to the workplace definition. The enforcer checks
    that the *section* was retrieved and that any parenthesised part appears somewhere in it —
    which is weaker than checking the clause itself was the source.
  * Retrieval returns the whole of s.2 for "what is a workplace", so the model is handed every
    definition in the Act to explain one of them.
  * **The lawyer pack asks for 5,570 characters of s.2 when two paragraphs are load-bearing.**
    That is the difference between an evening and twenty minutes, and it is the only lever we
    have on the one task that unblocks the product.

## What this does and does not do

It **splits**, it does not transcribe. The text is already byte-verified against the India Code
PDF — `check_transcription.py` proves 30/30 and re-proves on demand. Every clause extracted here
is a substring of text that already carries that proof, and the script refuses to write anything
that does not reproduce exactly from its parent.

It does **not** set any provision to QUOTED or VERIFIED. In our lattice those mean *a lawyer has
checked our reading*, and splitting a paragraph out of a verified transcription does not produce
a legal opinion. Sub-sections inherit `verified_by: null` from their parents. What changes is the
*size of the ask*, not its status.

    python3 scripts/split_subsections.py            # report only
    python3 scripts/split_subsections.py --write    # add them to the corpus
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"

# The clauses that carry the product's load-bearing claims. Deliberately a short, named list
# rather than "split everything": each entry is a clause we cite, and a clause nobody cites is
# noise in a review pack.
# Corrected against the Act itself. A proposed list named 2(n) as the definition of "woman";
# 2(n) is "sexual harassment", and **"woman" is not a defined term in this Act at all** — 2(a)
# defines "aggrieved woman". More importantly the list omitted 2(f), which is the clause our
# entire product turns on: every question we ask begins with a headcount, and 2(f) is what
# "employee" means. It is drawn very wide — "whether for remuneration or not" — which is exactly
# why the threshold question is not the simple arithmetic it looks like.
TARGETS: dict[int, list[str]] = {
    2: ["f", "g", "o", "p"],   # employee; employer; workplace; unorganised sector (the ten)
    4: ["1", "2"],             # the duty; the composition
}

# Numeric sub-sections "(1)" and lettered clauses "(a)" are marked identically but nest, so the
# pattern is chosen per parent rather than guessed.
NUMERIC = re.compile(r"\((\d{1,2})\)\s")
LETTERED = re.compile(r"\(([a-z]{1,2})\)\s")


def _clauses(body: str, numeric: bool) -> dict[str, tuple[int, int]]:
    """Span of each top-level clause. Nested markers are skipped by taking first occurrences."""
    pat = NUMERIC if numeric else LETTERED
    seen: dict[str, int] = {}
    for m in pat.finditer(body):
        label = m.group(1)
        if label not in seen:
            seen[label] = m.start()
    ordered = sorted(seen.items(), key=lambda kv: kv[1])
    spans: dict[str, tuple[int, int]] = {}
    for i, (label, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(body)
        spans[label] = (start, end)
    return spans


def extract(provisions: dict[int, dict]) -> list[dict]:
    out: list[dict] = []
    for section, wanted in TARGETS.items():
        parent = provisions[section]
        body = " ".join(parent["text_statutory"].split())
        numeric = wanted[0].isdigit()
        spans = _clauses(body, numeric)
        for label in wanted:
            if label not in spans:
                raise ValueError(f"s.{section}({label}) not found in the parent text")
            start, end = spans[label]
            text = body[start:end].strip()
            # A clause must reproduce exactly from its parent, or we have mis-sliced it.
            if text not in body:
                raise ValueError(f"s.{section}({label}) does not reproduce from its parent")
            out.append({
                "id": f"posh_s{section}_{label}",
                "section_number": section,
                "clause": label,
                "citation": f"s.{section}({label}), PoSH Act 2013",
                "parent_citation": parent["citation"],
                "text_statutory": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_count": len(text),
                "derived_from": {
                    "parent_sha256": parent["text_sha256"],
                    "method": "verbatim slice of the parent's statutory text at its clause marker",
                },
                # Inherited, deliberately. Splitting a verified transcription does not produce a
                # legal opinion; only a lawyer moves this.
                "verified_by": None,
                "verified_at": None,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    doc = json.loads(CORPUS.read_text())
    provisions = {p["section_number"]: p for p in doc["provisions"]}

    try:
        subs = extract(provisions)
    except ValueError as e:
        print(f"REFUSED: {e}. Nothing written.", file=sys.stderr)
        return 1

    print("  clause          chars   parent   reduction   opening words")
    print("  " + "-" * 92)
    for s in subs:
        parent_len = len(" ".join(provisions[s["section_number"]]["text_statutory"].split()))
        pct = 100 - round(100 * s["char_count"] / parent_len)
        opening = " ".join(s["text_statutory"].split())[:44]
        print(f"  {s['citation'][:14]:14} {s['char_count']:5}   {parent_len:5}   "
              f"{pct:3}% less   {opening}…")

    total_sub = sum(s["char_count"] for s in subs)
    total_parent = sum(len(" ".join(provisions[n]["text_statutory"].split())) for n in TARGETS)
    print(f"\n  A reviewer checking these four clauses reads {total_sub:,} characters")
    print(f"  instead of {total_parent:,} — {100 - round(100*total_sub/total_parent)}% less, "
          f"for the same claims.")

    if args.write:
        doc["subsections"] = subs
        CORPUS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n  Written → corpus.subsections ({len(subs)} clauses)")
        print("  verified_by stays null on every one. Splitting is not verifying.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
