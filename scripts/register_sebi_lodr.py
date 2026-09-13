#!/usr/bin/env python3
"""Register SEBI's consolidated LODR text -- and record what a consolidation is not.

SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015. The
highest-value declared body in `checker/scope.py`: a listed company's Companies
Act answer is routinely incomplete without it.

## The finding that shapes this module

MCA and SEBI publish law differently, and the difference lands directly on the
one thing this product sells.

MCA publishes DISCRETE AMENDING NOTIFICATIONS -- G.S.R. 700(E), then G.S.R.
880(E). Each is a self-contained instrument with its own commencement date, so a
point-in-time chain can be built from them, which is exactly what s.2(85) now
has: Rs 4 crore until 30-11-2025, Rs 10 crore after.

SEBI publishes a CONSOLIDATION: one document headed "Amended up to July 14,
2026". It is authoritative for what the law is TODAY and says nothing about what
it was on any earlier date. Reconstructing a past date needs every amending
notification acquired separately.

`docs/RETRACTIONS.md` records this exact mistake being made and retracted here
once already -- "Never use a current consolidated Act as pre-amendment ground
truth." So this module registers the text as CURRENT_ONLY and refuses to let it
answer a dated question.

## What that means in practice

  "Does regulation 30A apply to this company?"        answerable once attested
  "Did regulation 30A apply on 15 March 2019?"        REFUSED -- we hold one
                                                      snapshot, not a history

The second refusal is not a limitation to apologise for. It is the difference
between this engine and every tool that would answer both questions from the
same consolidated PDF without noticing it had been asked two different things.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STORE = Path("corpus/rules/sebi_lodr_2015.txt")
RECORD = Path("corpus/sources/sebi_lodr_registration.json")
SOURCE_URL = "https://www.sebi.gov.in/sebi_data/attachdocs/jul-2026/1784630770711.pdf"
LANDING = ("https://www.sebi.gov.in/legal/regulations/jul-2026/securities-and-exchange"
           "-board-of-india-listing-obligations-and-disclosure-requirements-regulations"
           "-2015-last-amended-on-july-14-2026-_102974.html")

PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

ATTESTATIONS = (
    "identity: this file is the SEBI (Listing Obligations and Disclosure "
    "Requirements) Regulations, 2015, notification SEBI/LAD-NRO/GN/2015-16/013",
    "consolidation: the reviewer has read the 'Amended up to' line and understands "
    "this is SEBI's own consolidation, not an as-enacted instrument",
    "point-in-time: the reviewer understands that attesting this makes CURRENT "
    "questions answerable and leaves DATED questions refused, because one snapshot "
    "is not a history",
)

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"
WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
NO_CONSOLIDATION_DATE = "NO_CONSOLIDATION_DATE"
UNREADABLE = "UNREADABLE"
EXIT = {VERIFIED_INSTRUMENT: 0, WRONG_INSTRUMENT: 2, NO_CONSOLIDATION_DATE: 3,
        UNREADABLE: 4}


def _ident(text: str) -> str:
    """Whitespace-stripped, lowercased. SEBI's text layer writes 'EXCHA NGE' and
    'LAD - NRO', so an identity check that assumes intact words rejects the real
    document. Search-only: nothing stored is altered."""
    return re.sub(r"\s+", "", text).lower()


_ID_TITLE = "listingobligationsanddisclosurerequirements"
_ID_YEAR = "regulations,2015"
_ID_NOTIF = "sebi/lad-nro/gn/2015-16/013"
# "Amended up to <Month> <day>, <year>" -- the marker that makes this a snapshot.
_CONSOLIDATED = re.compile(
    r"amended\s*up\s*to\s*([A-Za-z]+)\s*(\d{1,2})\s*,?\s*(\d{4})?", re.I)


def classify(text: str) -> tuple[str, str, str]:
    """(outcome, reason, consolidation marker)."""
    if not text.strip():
        return UNREADABLE, "no text could be extracted", ""
    ident = _ident(text)
    missing = []
    if _ID_TITLE not in ident:
        missing.append("the title 'Listing Obligations and Disclosure Requirements'")
    if _ID_YEAR not in ident:
        missing.append("'Regulations, 2015'")
    if _ID_NOTIF not in ident:
        missing.append("the notification SEBI/LAD-NRO/GN/2015-16/013")
    if missing:
        return WRONG_INSTRUMENT, "does not identify itself by " + ", ".join(missing), ""

    m = _CONSOLIDATED.search(text)
    if not m:
        # A LODR text with no "amended up to" line is either as-enacted or an
        # unknown printing. Either way it is not what this module registers, and
        # guessing which would defeat the point of the module.
        return (NO_CONSOLIDATION_DATE,
                "identifies as LODR 2015 but carries no 'Amended up to' line. This "
                "module registers SEBI's consolidation specifically; a text without "
                "that marker has an unknown relationship to the current law", "")
    marker = re.sub(r"\s+", " ", m.group(0)).strip()
    return VERIFIED_INSTRUMENT, f"identifies as LODR 2015, consolidated: {marker}", marker


def register(src: Path) -> str:
    if not src.is_file():
        print(f"no such file: {src}\n\nclassification : {UNREADABLE}")
        return UNREADABLE
    from scripts.acquire_rules import extract_text
    text = extract_text(src) if src.read_bytes()[:4] == b"%PDF" else src.read_text()
    outcome, reason, marker = classify(text)
    digest = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()

    print(f"file           : {src}")
    print(f"sha256         : {digest}")
    print(f"classification : {outcome}")
    print(f"reason         : {reason}")
    if outcome != VERIFIED_INSTRUMENT:
        print("\nNOT registered. Nothing was written.")
        return outcome

    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(text, encoding="utf-8")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "instrument_id": "SEBI_LODR_2015_CONSOLIDATED",
        "title": "SEBI (Listing Obligations and Disclosure Requirements) "
                 "Regulations, 2015 — SEBI's consolidation",
        "notification": "SEBI/LAD-NRO/GN/2015-16/013",
        "source_url": SOURCE_URL,
        "landing_page": LANDING,
        "acquisition_method": "sebi_gov_in_direct",
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifact_sha256": digest,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(STORE.read_bytes()).hexdigest(),
        "consolidation_marker": marker,
        # The PDF's own text layer truncates the year -- it reads "Amended up to
        # July 14" and stops. SEBI's landing page title supplies "2026". Two
        # sources, recorded separately, because silently completing the artifact
        # from a different document is repair, and repair is how a wrong date
        # acquires the authority of the file it was not in.
        "consolidation_year_from_landing_page": "2026",
        "consolidation_year_in_artifact": False,
        # The load-bearing fields. A consolidation is one snapshot.
        "is_consolidation": True,
        "point_in_time_capable": False,
        "point_in_time_note":
            "SEBI publishes a consolidation, not discrete amending notifications. "
            "This text is authoritative for the current law and silent on any "
            "earlier date. Dated questions must be refused until the amending "
            "notifications are acquired individually.",
        "identity_checked_by": None,
        "identity_checked_at": None,
        "consolidation_understood_by": None,
        "status": PENDING_HUMAN_REVIEW,
        "attests_to": ATTESTATIONS,
    }, indent=1) + "\n", encoding="utf-8")

    print(f"\nconsolidated   : {marker}")
    print(f"stored         : {STORE}")
    print(f"record         : {RECORD}")
    print(f"status         : {PENDING_HUMAN_REVIEW}")
    print("\nThis is SEBI's CONSOLIDATION, not an as-enacted instrument.")
    print("Once attested it answers questions about the law NOW. Dated questions")
    print("stay refused: one snapshot is not a history, and docs/RETRACTIONS.md")
    print("records this exact mistake being made and retracted here once already.")
    print("\n  python3 scripts/register_sebi_lodr.py --attest <reviewer-id>")
    return outcome


def attest(reviewer_id: str) -> str:
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return "NO_RECORD"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec.update({"identity_checked_by": reviewer_id, "identity_checked_at": now,
                "consolidation_understood_by": reviewer_id, "status": CORROBORATED})
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {now}; status {CORROBORATED}")
    print("\nLODR now answers CURRENT questions. DATED questions remain refused.")
    return CORROBORATED


def registration() -> dict | None:
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_attested(rec: dict | None) -> bool:
    if not rec:
        return False
    return bool(rec.get("identity_checked_by")
                and rec.get("consolidation_understood_by")
                and rec.get("status") == CORROBORATED)


def answers_dated_questions(rec: dict | None) -> bool:
    """Always False for a consolidation. Kept as a function so the reason is
    expressible in code rather than assumed."""
    return bool(rec and rec.get("point_in_time_capable"))


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("register_sebi_lodr")
    good = ("SECURITIES AND EXCHA NGE BOARD OF INDIA ( LISTING OBLIGATIONS AND "
            "DISCLOSURE REQUI REMENTS) REGULATIONS , 2015 [Amended up to July 14, "
            "2026] No. SEBI/LAD - NRO/GN/2015 - 16/013 In exercise of the powers "
            "conferred by section 11...")
    o, r, marker = classify(good)
    check(o == VERIFIED_INSTRUMENT, f"the consolidated LODR verifies ({o})")
    check("July 14" in marker, f"...and the consolidation date is captured ({marker})")
    check("EXCHA NGE" in good and o == VERIFIED_INSTRUMENT,
          "...despite the text layer splitting words — identity is matched on a "
          "whitespace-stripped copy, never on repaired text")

    no_marker = good.replace("[Amended up to July 14, 2026] ", "")
    o2, r2, _ = classify(no_marker)
    check(o2 == NO_CONSOLIDATION_DATE,
          f"a LODR text with no 'Amended up to' line is refused ({o2})")
    check("unknown relationship to the current law" in r2,
          "...because its relationship to current law is unknown, and guessing "
          "would defeat the module")

    o3, _, _ = classify(good.replace("LISTING OBLIGATIONS AND DISCLOSURE REQUI REMENTS",
                                     "ISSUE OF CAPITAL AND DISCLOSURE REQUIREMENTS")
                            .replace("listingobligations", "x"))
    check(o3 == WRONG_INSTRUMENT, f"a different SEBI regulation is refused ({o3})")
    check(classify("")[0] == UNREADABLE, "an unreadable file is UNREADABLE")

    # the load-bearing property
    stub = {"identity_checked_by": "R", "consolidation_understood_by": "R",
            "status": CORROBORATED, "point_in_time_capable": False}
    check(is_attested(stub), "an attested consolidation is attested")
    check(not answers_dated_questions(stub),
          "...and STILL does not answer dated questions — a snapshot is not a history")
    check(not answers_dated_questions(None), "no record answers nothing")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--test":
        raise SystemExit(_test())
    if args and args[0] == "--attest":
        if len(args) < 2:
            print("usage: register_sebi_lodr.py --attest <reviewer-id>")
            raise SystemExit(2)
        raise SystemExit(0 if attest(args[1]) == CORROBORATED else 1)
    if not args:
        print(__doc__)
        print("usage: register_sebi_lodr.py <downloaded-file>")
        raise SystemExit(2)
    raise SystemExit(EXIT.get(register(Path(args[0])), 1))
