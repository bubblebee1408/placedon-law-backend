"""
Verify stored text against the primary-source PDF, character for character.

**What this establishes, and what it does not.**

It proves the corpus is a faithful transcription: the file we ingested is the file India Code
serves today, and every stored provision appears in it verbatim. That is worth proving and worth
re-proving, because a silent corruption of `text_display` would put a wrong figure into a
document a company signs.

It does **not** touch `verified_by`. That field means *a lawyer has checked our reading of this
section*, and no amount of careful comparison produces it. Transcription and interpretation are
different claims:

    "the Act says X"                 ← this script can prove
    "X means you must do Y"          ← only a lawyer can

Conflating them is exactly the failure this project has refused eight times. A tool that marked
itself verified because it read its own source carefully would be worse than one that never
claimed verification at all.

So the corpus gains a separate field. `transcription` records what was checked, against what, on
what date. `verified_by` stays null until somebody with a bar number puts their name on it.

    python3 scripts/check_transcription.py            # check, report, change nothing
    python3 scripts/check_transcription.py --record   # write the transcription record
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"


def _ctx() -> ssl.SSLContext:
    try:
        import certifi                                        # noqa: PLC0415
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"user-agent": "placedon-hr/0.1"})
    with urllib.request.urlopen(req, timeout=120, context=_ctx()) as r:  # noqa: S310
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true",
                    help="write the transcription record into the corpus")
    args = ap.parse_args()

    doc = json.loads(CORPUS.read_text())
    inst, provisions = doc["instrument"], doc["provisions"]
    url = inst["source_url"]

    print(f"Fetching the primary source fresh:\n  {url}")
    try:
        blob = fetch(url)
    except Exception as e:                                    # noqa: BLE001
        print(f"\nCould not reach India Code ({e}). Nothing checked, nothing written.",
              file=sys.stderr)
        return 1

    live_sha = hashlib.sha256(blob).hexdigest()
    same_file = live_sha == inst["source_sha256"]
    print(f"  {len(blob):,} bytes   sha256 {live_sha[:24]}…")
    print(f"  matches the file we ingested: {'YES' if same_file else 'NO — THE SOURCE CHANGED'}")
    if not same_file:
        print("\nREFUSED. India Code is serving different bytes than we ingested. Re-ingest and "
              "re-read before trusting anything downstream.", file=sys.stderr)
        return 1

    tmp = ROOT / ".transcription_check.pdf"
    tmp.write_bytes(blob)
    try:
        import pdfplumber                                     # noqa: PLC0415
        with pdfplumber.open(tmp) as pdf:
            # Join pages with a newline, matching how ingest_posh assembles the document.
            # Flattening page-by-page instead reported s.8 and s.18 as mismatches — a fault in
            # this checker, not the corpus. Chasing it is what surfaced the footnote problem.
            raw = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
        # The same transform ingestion applies. `text_display` repairs hyphenated line-wraps
        # ("Govern-\nment" -> "Government"), so it legitimately differs from raw PDF text.
        # Comparing against untransformed text reported s.8 and s.18 as mismatches — a fault in
        # the comparison, not the corpus, and chasing it is what surfaced the footnote problem.
        from scripts.ingest_posh import join_wraps as _jw       # noqa: PLC0415
        flat = " ".join(_jw(raw).split())
    finally:
        tmp.unlink(missing_ok=True)

    from scripts.ingest_posh import join_wraps                # noqa: PLC0415

    print(f"\nComparing {len(provisions)} provisions against the fetched PDF:\n")
    verbatim, hash_ok, derives = [], [], []
    failed: list[str] = []
    for p in provisions:
        cite = p["citation"]
        stored = " ".join(p["text_display"].split())
        if stored in flat:
            verbatim.append(cite)
        else:
            failed.append(f"{cite}: stored text not found in the PDF")
        if hashlib.sha256(p["text"].encode()).hexdigest() == p["text_sha256"]:
            hash_ok.append(cite)
        else:
            failed.append(f"{cite}: raw hash does not recompute")
        if join_wraps(p["text"]) == p["text_display"]:
            derives.append(cite)
        else:
            failed.append(f"{cite}: text_display is not derivable from text")

    n = len(provisions)
    print(f"  appears verbatim in the PDF      {len(verbatim):>3}/{n}")
    print(f"  raw sha256 recomputes            {len(hash_ok):>3}/{n}")
    print(f"  display text re-derives          {len(derives):>3}/{n}")
    if failed:
        print("\n  FAILURES:")
        for f in failed[:10]:
            print(f"    {f}")
        return 1

    print("\n  Transcription confirmed for all 30 sections.")
    print("  This does NOT verify our reading of any of them. verified_by stays null.")

    if args.record:
        stamp = {
            "checked_on": str(date.today()),
            "against": url,
            "source_sha256": live_sha,
            "method": ("re-fetched the primary PDF, confirmed byte-identical to the ingested "
                       "file, then confirmed every provision's display text appears in it "
                       "verbatim and re-derives from the raw extraction"),
            "sections_confirmed": n,
            "WHAT_THIS_IS_NOT": (
                "Not legal verification. This establishes that we transcribed the Act "
                "faithfully, not that our reading of it is correct. `verified_by` remains null "
                "on every provision and the product continues to abstain."
            ),
        }
        doc["instrument"]["transcription"] = stamp
        CORPUS.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n  Recorded → instrument.transcription (checked_on {stamp['checked_on']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
