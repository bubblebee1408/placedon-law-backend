"""
Register a downloaded subordinate-Rules PDF as a provenanced source.

Week 2.1 could not fetch the Meetings of Board Rules 2014: India Code's dynamic paths are down and
its upload host refuses connections, so the document's static address cannot be discovered. The
likely unblock is a human downloading it from eGazette or India Code once reachable. This script is
the other half of that handoff -- it verifies, hashes, stores and registers the file, so acquisition
does not depend on someone remembering the provenance steps at the moment they happen to have the
PDF.

It deliberately does NOT parse rule text. That is Week 2.2.

The check that matters is instrument identity. "The Companies (Meetings of Board and its Powers)
Rules, 2014" and "...Amendment Rules, 2014" are different instruments with near-identical titles,
and confusing an amendment for the principal rules would silently corrupt everything built on top.
This script refuses the file rather than guessing, and prints what it found for a human to confirm.

Usage:
    python3 scripts/acquire_rules.py <downloaded.pdf>
    python3 scripts/acquire_rules.py --test
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "corpus/sources"
DEST = SOURCES / "companies_meetings_board_powers_rules_2014.pdf"

PRINCIPAL_TITLE = re.compile(
    r"Companies\s*\(\s*Meetings\s+of\s+Board\s+and\s+its\s+Powers\s*\)\s*Rules,?\s*2014", re.I)
AMENDMENT_TITLE = re.compile(r"Amendment\s+Rules", re.I)
NOTIFICATION = re.compile(r"G\.?S\.?R\.?\s*(\d{1,4})\s*\(\s*E\s*\)", re.I)
# Gazette notifications write the date both as "dated the 31st March, 2014" and, in the dateline,
# as "New Delhi, the 31st March, 2014". Accept either; the leading "dated" is optional.
DATED = re.compile(r"(?:dated\s+)?the\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4})", re.I)


def extract_text(pdf: Path) -> str:
    for cmd in (["pdftotext", "-l", "3", str(pdf), "-"], ["mdls", "-name", "kMDItemTextContent", str(pdf)]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and len(r.stdout) > 200:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


def inspect(text: str) -> dict:
    """What the document says about itself. Reports; never decides silently."""
    return {
        "principal_title_found": bool(PRINCIPAL_TITLE.search(text)),
        "amendment_title_found": bool(AMENDMENT_TITLE.search(text)),
        "notification": (m.group(0) if (m := NOTIFICATION.search(text)) else None),
        "dated": (m.group(1) if (m := DATED.search(text)) else None),
    }


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def acquire(src: Path) -> int:
    if not src.is_file():
        print(f"no such file: {src}"); return 2

    text = extract_text(src)
    if not text:
        print("could not extract text -- cannot confirm instrument identity. REFUSING.")
        print("A PDF whose identity cannot be checked must not enter the corpus.")
        return 3

    found = inspect(text)
    print("document says of itself:")
    for k, v in found.items():
        print(f"  {k:<24} {v}")

    if found["amendment_title_found"] and not found["principal_title_found"]:
        print("\nREFUSED: this looks like an AMENDMENT instrument, not the principal 2014 Rules.")
        print("They are different instruments. Ingest the principal Rules first; amendments are")
        print("modelled separately (see docs/WEEK2_RULE_INGESTION_PLAN.md).")
        return 4
    if not found["principal_title_found"]:
        print("\nREFUSED: the principal title was not found in the first pages.")
        print("Not assuming this is the right document.")
        return 5
    if found["amendment_title_found"]:
        print("\nBOTH principal and amendment titles appear. This may be a consolidated or")
        print("amending document. STOPPING for human review rather than guessing.")
        return 6

    SOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, DEST)
    digest = sha256(DEST)
    line = f"{digest}  {DEST.name}\n"
    sums = SOURCES / "SHA256SUMS"
    existing = sums.read_text() if sums.exists() else ""
    if DEST.name not in existing:
        sums.write_text(existing + line)

    print(f"\nstored : {DEST.relative_to(ROOT)}")
    print(f"sha256 : {digest}")
    print("\nNow add this to checker/provenance.py, replacing BOARD_MEETING_RULES_2014:")
    print(f'''
BOARD_MEETING_RULES_2014 = SourceRecord(
    source_id="INDIACODE_MEETINGS_BOARD_RULES_2014",
    source_title="The Companies (Meetings of Board and its Powers) Rules, 2014",
    source_url="<the URL it was actually downloaded from>",
    official=True,
    accessibility=ACCESSIBLE,
    retrieved_on="<YYYY-MM-DD>",
    local_artifact="corpus/sources/{DEST.name}",
    artifact_sha256="{digest}",
    human_reviewed=False,   # stays False until a human has READ it; can_promote() enforces this
    notes="Notification {found['notification']}, dated {found['dated']}.",
)''')
    print("\nThen: ./scripts/run_tests.sh")
    return 0


def _test() -> int:
    ok = fail = 0

    def check(c: bool, label: str) -> None:
        nonlocal ok, fail
        if c:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    # Fixture values below are ILLUSTRATIVE strings for exercising the parser. They are not a
    # verified claim about the real notification number or date -- those must be read off the
    # actual document when it is acquired.
    principal = "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 31st March, 2014 " \
                "G.S.R. 240(E).- In exercise of the powers conferred under sections 173... " \
                "the Companies (Meetings of Board and its Powers) Rules, 2014."
    amendment = "G.S.R. 590(E).- the Companies (Meetings of Board and its Powers) Amendment " \
                "Rules, 2014, dated the 12th June, 2014."

    p = inspect(principal)
    check(p["principal_title_found"], "principal Rules title recognised")
    check(not p["amendment_title_found"], "principal document not flagged as an amendment")
    check(p["notification"] and "240" in p["notification"], f"notification read: {p['notification']}")
    check(p["dated"] and "March" in p["dated"], f"date read: {p['dated']}")

    a = inspect(amendment)
    check(a["amendment_title_found"], "amendment instrument detected")
    check(a["notification"] and "590" in a["notification"], "amendment notification read")

    check(inspect("unrelated text")["principal_title_found"] is False,
          "unrelated document is not accepted as the Rules")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    if len(sys.argv) != 2:
        print(__doc__); raise SystemExit(1)
    raise SystemExit(acquire(Path(sys.argv[1])))
