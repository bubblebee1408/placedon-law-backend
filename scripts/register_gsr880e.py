#!/usr/bin/env python3
"""Register a human-downloaded G.S.R. 880(E) so the 2025 thresholds become servable.

Sibling of scripts/register_gsr700e.py, and it exists because 700(E) stopped
being the operative instrument. The Companies (Specification of Definition
Details) Amendment Rules, 2025 -- G.S.R. 880(E), dated 01-12-2025 -- raise the
small-company limits from Rs 4 crore / Rs 40 crore to Rs 10 crore / Rs 100 crore
with effect from the date of publication.

## Why this file had to be written before anything else

The engine was serving Rs 4 crore as CURRENT on a date after 01-12-2025. That is
the one failure this whole system exists to prevent -- serving superseded law as
current -- and it was invisible because 700(E)'s record carried effective_to=None,
which asserts "still in force so far as we know". It was no longer true.

The fix is not to type the new amounts in. It is to record that a newer
instrument governs, refuse to serve ANY prescribed amount for dates it covers,
and name what a person must acquire. That is what this module does.

## What the amounts in prescribed_thresholds mean before attestation

Rs 10 crore / Rs 100 crore appear in prescribed_thresholds as a CLAIM TO BE
CHECKED, not an asserted fact -- exactly as Rs 4 crore did for 700(E). They are
not servable until this module records both human checks, and _CLAUSE below
requires the downloaded artifact to contain those words. If the artifact says
something else, registration fails and the claim is refused, loudly.

The provenance of the claim is secondary reporting (MCA press coverage), which is
why it may not be served. Only the Gazette artifact settles it.

## What this refuses

Identity, before anything else. India Code carries the principal 2014 Rules and
several near-identically-titled amendments. Registering the 2022 amendment as the
2025 one would silently restore the very figure this instrument replaced.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STORE = Path("corpus/rules/gsr_880e_2025.txt")
RECORD = Path("corpus/sources/gsr880e_registration.json")

# The exact India Code handle for this instrument is UNRESOLVED -- it was not
# looked up from a primary host, and guessing one would be a fabricated citation.
# The person who downloads the file records where they got it.
SOURCE_URL = "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/rules.html"
BITSTREAM_ID = None

PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

ATTESTATIONS = (
    "identity: this file is G.S.R. 880(E) of 01-12-2025, and not the principal "
    "2014 Rules, the 2021 amendments, or the 2022 amendment G.S.R. 700(E)",
    "clause: the operative wording recorded here is verbatim from the file, "
    "with no repair, normalisation or reflow",
    "source: the URL and date this artifact was downloaded from are recorded, "
    "and the host was the Gazette or India Code, not a commentary site",
)

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"
WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
CLAUSE_NOT_FOUND = "CLAUSE_NOT_FOUND"
UNREADABLE = "UNREADABLE"

EXIT = {VERIFIED_INSTRUMENT: 0, WRONG_INSTRUMENT: 2, CLAUSE_NOT_FOUND: 3, UNREADABLE: 4}

_GSR = re.compile(r"g\.?\s*s\.?\s*r\.?\s*\.?\s*880\s*\(\s*e\s*\)", re.I)
_TITLE = re.compile(r"specification\s+of\s+definitio?n?s?\s+details", re.I)
_YEAR = re.compile(r"\b2025\b")

# The operative clause. Amounts matched as words, as the instrument writes them;
# a digit-only match would also hit page numbers.
_CLAUSE = re.compile(
    r"(paid[\s-]*up\s+capital[^.]{0,200}?turnover[^.]{0,200}?"
    r"(ten\s+crore|rupees\s+ten\s+crore)[^.]{0,160}?"
    r"(one\s+hundred\s+crore|hundred\s+crore)[^.]{0,80}\.)",
    re.I | re.S)

# Instruments we must NOT accept in its place.
_SIBLINGS = (
    (re.compile(r"g\.?\s*s\.?\s*r\.?\s*\.?\s*700\s*\(\s*e\s*\)", re.I),
     "G.S.R. 700(E) — the 2022 amendment this one replaces, not this one"),
    (re.compile(r"g\.?\s*s\.?\s*r\.?\s*\.?\s*92\s*\(\s*e\s*\)", re.I),
     "G.S.R. 92(E) — the 2021 amendment, not this one"),
    (re.compile(r"g\.?\s*s\.?\s*r\.?\s*\.?\s*123\s*\(\s*e\s*\)", re.I),
     "G.S.R. 123(E) — the 2021 second amendment, not this one"),
)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:4] == b"%PDF":
        try:
            from scripts.acquire_rules import extract_text  # type: ignore
            return extract_text(path)
        except Exception:                                    # noqa: BLE001
            return ""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def classify(text: str) -> tuple[str, str, str]:
    """(outcome, reason, operative_clause_verbatim)."""
    if not text.strip():
        return UNREADABLE, "no text could be extracted, so no identity claim can be checked", ""

    for pat, what in _SIBLINGS:
        if pat.search(text) and not _GSR.search(text):
            return WRONG_INSTRUMENT, f"this document is {what}", ""

    missing = []
    if not _GSR.search(text):
        missing.append("the notification number G.S.R. 880(E)")
    if not _TITLE.search(text):
        missing.append("the title 'Specification of Definition Details'")
    if not _YEAR.search(text):
        missing.append("the year 2025")
    if missing:
        return WRONG_INSTRUMENT, "does not identify itself by " + ", ".join(missing), ""

    m = _CLAUSE.search(text)
    if not m:
        return (CLAUSE_NOT_FOUND,
                "identifies as G.S.R. 880(E) but the operative clause naming ten crore and "
                "one hundred crore was not found — the extraction may be partial, or the "
                "amounts differ from what secondary reporting claimed. Do not proceed on "
                "the claimed figures; read the file.", "")
    clause = re.sub(r"\s+", " ", m.group(1)).strip()
    return VERIFIED_INSTRUMENT, "identifies as G.S.R. 880(E) of 2025 and carries the clause", clause


def register(src: Path) -> str:
    if not src.is_file():
        print(f"no such file: {src}")
        print(f"\nclassification : {UNREADABLE}")
        return UNREADABLE

    text = read_text(src)
    outcome, reason, clause = classify(text)
    digest = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()

    print(f"file           : {src}")
    print(f"sha256         : {digest}")
    print(f"classification : {outcome}")
    print(f"reason         : {reason}")

    if outcome != VERIFIED_INSTRUMENT:
        print("\nNOT registered. Nothing was written.")
        return outcome

    print(f"\noperative clause, verbatim:\n  {clause}\n")
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(text, encoding="utf-8")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "instrument_id": "GSR_880E_DEFINITIONS_AMENDMENT_2025",
        "title": "G.S.R. 880(E) — Companies (Specification of Definition Details) "
                 "Amendment Rules, 2025, dated 01-12-2025",
        "source_url": SOURCE_URL,
        "bitstream_id": BITSTREAM_ID,
        "downloaded_from": None,        # filled by --attest; only a person knows it
        "downloaded_at": None,
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acquisition_method": "human_browser",
        "artifact_sha256": digest,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(
            STORE.read_bytes()).hexdigest(),
        "operative_clause": clause,
        "classification": outcome,
        "identity_checked_by": None,
        "identity_checked_at": None,
        "verbatim_clause_checked_by": None,
        "verbatim_clause_checked_at": None,
        "status": PENDING_HUMAN_REVIEW,
        "attests_to": ATTESTATIONS,
    }, indent=1) + "\n", encoding="utf-8")

    print(f"stored         : {STORE}")
    print(f"record         : {RECORD}")
    print(f"status         : {PENDING_HUMAN_REVIEW}")
    print("\nThe artifact is stored and hashed. It is NOT yet usable law.")
    print("Until a person attests, prescribed_thresholds refuses EVERY prescribed")
    print("small-company amount for dates on or after 01-12-2025 — it does not")
    print("fall back to the 2022 figure, because that figure is superseded.")
    for a in ATTESTATIONS:
        print(f"  - {a}")
    print("\nWhen you have done all three:")
    print("  python3 scripts/register_gsr880e.py --attest <your-reviewer-id>")
    return outcome


def attest(reviewer_id: str, downloaded_at: str | None = None) -> str:
    """Record that a person performed the checks. Without this the artifact is
    stored but not usable, and prescribed_thresholds keeps refusing."""
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return "NO_RECORD"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec["identity_checked_by"] = reviewer_id
    rec["identity_checked_at"] = now
    rec["verbatim_clause_checked_by"] = reviewer_id
    rec["verbatim_clause_checked_at"] = now
    if downloaded_at:
        rec["downloaded_at"] = downloaded_at
    rec["status"] = CORROBORATED
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {now}; status {CORROBORATED}")
    print("prescribed_thresholds will now serve the 2025 limits. Run the suite.")
    return CORROBORATED


def registration() -> dict | None:
    """The registration record, if one exists. Read by prescribed_thresholds."""
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_attested(rec: dict | None) -> bool:
    """Both human checks recorded, and the status says so."""
    if not rec:
        return False
    return bool(rec.get("identity_checked_by")
                and rec.get("identity_checked_at")
                and rec.get("verbatim_clause_checked_by")
                and rec.get("verbatim_clause_checked_at")
                and rec.get("status") == CORROBORATED)


# ── test support ──────────────────────────────────────────────────────────────
from contextlib import contextmanager as _contextmanager


def registered_unattested_stub() -> dict:
    return {"artifact_sha256": "sha256:" + "ab" * 32,
            "identity_checked_by": None, "identity_checked_at": None,
            "verbatim_clause_checked_by": None, "verbatim_clause_checked_at": None,
            "status": PENDING_HUMAN_REVIEW}


def attested_stub(reviewer: str = "TEST") -> dict:
    return {"artifact_sha256": "sha256:" + "ab" * 32,
            "identity_checked_by": reviewer,
            "identity_checked_at": "2026-01-01T00:00:00Z",
            "verbatim_clause_checked_by": reviewer,
            "verbatim_clause_checked_at": "2026-01-01T00:00:00Z",
            "status": CORROBORATED}


@_contextmanager
def stub_registration(rec):
    """Control the acquisition state within a block. Test-only."""
    # sys.modules[__name__] rather than a fresh import: run as a script this
    # module is __main__, and importing it by name would patch a SECOND copy
    # while the test kept calling the first.
    mod = sys.modules[__name__]
    original = mod.registration
    mod.registration = lambda: rec         # type: ignore[assignment]
    try:
        yield
    finally:
        mod.registration = original        # type: ignore[assignment]


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

    print("register_gsr880e")

    good = ("MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 1st December, 2025 "
            "G.S.R. 880(E).— In exercise of the powers conferred by section 469, the Central "
            "Government hereby makes the following rules to amend the Companies (Specification "
            "of Definition Details) Rules, 2014. For the purposes of clause (85) of section 2 "
            "of the Act, paid up capital and turnover of the small company shall not exceed "
            "rupees ten crore and rupees one hundred crore respectively.")
    outcome, reason, clause = classify(good)
    check(outcome == VERIFIED_INSTRUMENT, f"the real instrument verifies ({outcome})")
    check("ten crore" in clause and "one hundred crore" in clause,
          "...and the operative clause is captured verbatim")

    # the instrument it replaces must never be accepted in its place
    seven = good.replace("880(E)", "700(E)").replace("2025", "2022") \
                .replace("ten crore", "four crore").replace("one hundred crore", "forty crore")
    o2, r2, _ = classify(seven)
    check(o2 == WRONG_INSTRUMENT, f"G.S.R. 700(E) is rejected, not accepted as 880(E) ({o2})")
    check("700(E)" in r2, "...and the reason names what was found instead")

    # right instrument, wrong amounts => refuse rather than trust the claim
    wrong_amounts = good.replace("rupees ten crore", "rupees five crore") \
                        .replace("rupees one hundred crore", "rupees fifty crore")
    o3, r3, _ = classify(wrong_amounts)
    check(o3 == CLAUSE_NOT_FOUND,
          f"880(E) whose amounts differ from the claim is refused, not registered ({o3})")

    o4, _, _ = classify("")
    check(o4 == UNREADABLE, f"an unreadable file is UNREADABLE, not verified ({o4})")

    check(not is_attested(None), "no record is not attested")
    check(not is_attested(registered_unattested_stub()),
          "a registered but unattested record is not attested")
    check(is_attested(attested_stub()), "an attested record is attested")
    half = attested_stub()
    half["verbatim_clause_checked_by"] = None
    check(not is_attested(half), "one of the checks alone is not enough")

    with stub_registration(attested_stub()):
        check(is_attested(registration()), "stub_registration controls the state")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--test":
        raise SystemExit(_test())
    if args and args[0] == "--attest":
        if len(args) < 2:
            print("usage: register_gsr880e.py --attest <reviewer-id>")
            raise SystemExit(2)
        raise SystemExit(0 if attest(args[1]) == CORROBORATED else 1)
    if not args:
        print(__doc__)
        print("usage: register_gsr880e.py <downloaded-file>")
        print("       register_gsr880e.py --attest <reviewer-id>")
        raise SystemExit(2)
    raise SystemExit(EXIT.get(register(Path(args[0])), 1))
