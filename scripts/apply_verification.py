"""
Apply a lawyer's review back onto the corpus. The return path for BACKLOG H-2.

The pack (scripts/review_pack.py) is the outbound half and it has existed for a while. This is
the inbound half, and without it the review is a PDF that dies in an inbox: the only way to turn
"the lawyer said yes" into a working product was to hand-edit `verified_by` across 30 JSON
entries, which is exactly the kind of manual step that silently sets the wrong field on the
wrong section.

    python3 scripts/apply_verification.py --template   # emit the form to send
    python3 scripts/apply_verification.py --dry-run    # show what would change
    python3 scripts/apply_verification.py --apply      # write it

What this refuses to do:

  * Accept `accepted` on a section whose text has changed since the pack was generated. The
    reviewer signed off on a specific sha256; if the corpus was re-ingested in between, that
    signature no longer refers to what is on disk. Re-send the pack.
  * Accept a review with no reviewer name. `verified_by` is a provenance field — "true" is not
    a reviewer, and an anonymous verification is worth exactly as much as no verification.
  * Mark anything verified on the strength of a `corrected` verdict. A correction means our
    reading was wrong, so it stays unverified and lands in BACKLOG until the reading is fixed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"
RESPONSE = ROOT / "corpus/review_response.json"

# Imported, never restated. The pack and the form must describe the same set of sections, or a
# reviewer signs off on six and the product still abstains — which is exactly what happened when
# this was a hand-written tuple.
from scripts.review_pack import required_sections  # noqa: E402

TIER1 = tuple(sorted(required_sections()))
VERDICTS = ("accepted", "corrected", "not_reviewed")


def _template(provisions: dict) -> dict:
    return {
        "_instructions": (
            "One entry per section. Set verdict to 'accepted' if our reading is right, "
            "'corrected' if it is wrong (then write what it should say in `correction`), or "
            "leave 'not_reviewed'. reviewer_name and reviewer_credential are required before "
            "anything can be applied."
        ),
        "reviewer_name": "",
        "reviewer_credential": "",
        "reviewed_on": str(date.today()),
        "sections": {
            str(n): {
                "citation": provisions[n]["citation"],
                "heading": provisions[n]["heading"],
                "text_sha256": provisions[n]["text_sha256"],
                "verdict": "not_reviewed",
                "correction": "",
            }
            for n in TIER1
            if n in provisions
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--template", action="store_true", help="emit the blank response form")
    g.add_argument("--dry-run", action="store_true", help="validate and show the diff")
    g.add_argument("--apply", action="store_true", help="write verified_by onto the corpus")
    args = ap.parse_args()

    data = json.loads(CORPUS.read_text())
    provisions = {p["section_number"]: p for p in data["provisions"]}

    if args.template:
        if RESPONSE.exists():
            print(f"{RESPONSE.relative_to(ROOT)} already exists — not overwriting a filled form.")
            return 1
        RESPONSE.write_text(json.dumps(_template(provisions), indent=2) + "\n")
        print(f"→ {RESPONSE.relative_to(ROOT)}")
        print(f"  {len(TIER1)} Tier 1 sections, all 'not_reviewed'. Send with the pack.")
        return 0

    if not RESPONSE.exists():
        print(f"No {RESPONSE.relative_to(ROOT)}. Run --template first.", file=sys.stderr)
        return 1

    resp = json.loads(RESPONSE.read_text())
    name = str(resp.get("reviewer_name", "")).strip()
    cred = str(resp.get("reviewer_credential", "")).strip()
    if not name or not cred:
        print("Refusing: reviewer_name and reviewer_credential are both required.\n"
              "verified_by is a provenance field. An anonymous verification is worth nothing,\n"
              "and it is worth less than nothing if it looks like a real one.", file=sys.stderr)
        return 1

    on = str(resp.get("reviewed_on") or date.today())
    stamp = f"{name} ({cred}), {on}"

    to_verify: list[int] = []
    corrections: list[tuple[str, str]] = []
    problems: list[str] = []

    for key, entry in resp.get("sections", {}).items():
        n = int(key)
        verdict = entry.get("verdict")
        if verdict not in VERDICTS:
            problems.append(f"s.{n}: verdict {verdict!r} is not one of {VERDICTS}")
            continue
        if n not in provisions:
            problems.append(f"s.{n}: not in the corpus")
            continue
        if verdict == "not_reviewed":
            continue

        # The signature refers to a specific text. If the text moved, the signature does not
        # travel with it.
        if entry.get("text_sha256") != provisions[n]["text_sha256"]:
            problems.append(
                f"s.{n}: text_sha256 in the response does not match the corpus. The section was "
                f"re-ingested after the pack was generated — re-send it."
            )
            continue

        if verdict == "corrected":
            corr = str(entry.get("correction", "")).strip()
            if not corr:
                problems.append(f"s.{n}: verdict 'corrected' with no correction text")
                continue
            corrections.append((provisions[n]["citation"], corr))
            continue

        to_verify.append(n)

    if problems:
        print("REFUSED — the response does not apply cleanly:\n")
        for p in problems:
            print(f"  * {p}")
        return 1

    print(f"Reviewer: {stamp}\n")
    if to_verify:
        print(f"Would mark verified ({len(to_verify)}):")
        for n in sorted(to_verify):
            print(f"  s.{n:<3} {provisions[n]['heading'][:62]}")
    if corrections:
        print(f"\nCorrections — these stay UNVERIFIED until the reading is fixed ({len(corrections)}):")
        for cite, corr in corrections:
            print(f"  {cite}: {corr[:100]}")
    if not to_verify and not corrections:
        print("Nothing to apply — every section is still 'not_reviewed'.")
        return 0

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    verified = set(to_verify)
    data["provisions"] = [
        {**p, "verified_by": stamp, "verified_at": on}
        if p["section_number"] in verified else p
        for p in data["provisions"]
    ]
    CORPUS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(verified)} verifications to {CORPUS.relative_to(ROOT)}.")

    if corrections:
        backlog = ROOT / "BACKLOG.md"
        lines = [f"\n## Corrections from {stamp}\n"]
        lines += [f"- [ ] **{cite}** — {corr}\n" for cite, corr in corrections]
        backlog.write_text(backlog.read_text() + "".join(lines), encoding="utf-8")
        print(f"Appended {len(corrections)} correction(s) to BACKLOG.md — these block the "
              f"sections they touch.")

    print("\nNow run: python3 checker/test_unlock.py   (it proves the gate opened)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
