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

Then an unsourced file (A-001). Two human checks say the file is the right
instrument and the clause is verbatim; they do not say where the file came from.
is_attested() also requires provenance: either the download address (https, an
official host) with its date, recorded by the person who downloaded it, or a
copy fetched from an official host that is byte-identical or carries the held
clause verbatim. A recorded source that is not official is refused outright --
corroboration does not cure a record that names a commentary site.
"""
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.provenance import OFFICIAL_SOURCE_HOSTS, official_source_url  # noqa: E402

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

# The instrument's date of publication. No copy of it can have been downloaded earlier.
PUBLISHED = date(2025, 12, 1)
# What a corroborating copy must be. "not-found" and "blocked" are outcomes of a
# search, not a corroboration, and anything looser than verbatim is not a match.
CORROBORATING_MATCHES = ("identical", "text-identical")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
# A date-only entry is read as midnight UTC; a person entering today's date from
# India can be up to a day "ahead" of that.
_CLOCK_SLACK = timedelta(days=1)

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


SOURCE_REFUSED = "SOURCE_REFUSED"


def register(src: Path, downloaded_from: str | None = None,
             downloaded_at: str | None = None) -> str:
    if downloaded_from is not None or downloaded_at is not None:
        problem = source_problem(downloaded_from, downloaded_at)
        if problem:
            print(f"download source refused: {problem}\nNOT registered. Nothing was written.")
            return SOURCE_REFUSED
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
        # Only the person who downloaded the file knows these. Recorded by --from/--at
        # on register, --attest or --source; is_attested() refuses without them unless
        # an official copy corroborates the file.
        "downloaded_from": downloaded_from,
        "downloaded_at": downloaded_at,
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
    print("  python3 scripts/register_gsr880e.py --attest <your-reviewer-id> "
          "--from <download-URL> --at <YYYY-MM-DD>")
    return outcome


def attest(reviewer_id: str, downloaded_from: str | None = None,
           downloaded_at: str | None = None) -> str:
    """Record that a person performed the checks, and optionally where they got the
    file. A bad source is refused BEFORE anything is stamped. Without provenance the
    record stays unusable and prescribed_thresholds keeps refusing."""
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return "NO_RECORD"
    if downloaded_from is not None or downloaded_at is not None:
        problem = source_problem(downloaded_from, downloaded_at)
        if problem:
            print(f"download source refused: {problem}\nNothing was written.")
            return SOURCE_REFUSED
        rec["downloaded_from"] = downloaded_from
        rec["downloaded_at"] = downloaded_at
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec["identity_checked_by"] = reviewer_id
    rec["identity_checked_at"] = now
    rec["verbatim_clause_checked_by"] = reviewer_id
    rec["verbatim_clause_checked_at"] = now
    rec["status"] = CORROBORATED
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {now}; status {CORROBORATED}")
    gaps = attestation_gaps(rec)
    if gaps:
        print("NOT usable yet: " + "; ".join(gaps))
        return PENDING_HUMAN_REVIEW
    print("prescribed_thresholds will now serve the 2025 limits. Run the suite.")
    return CORROBORATED


def record_source(downloaded_from: str | None, downloaded_at: str | None) -> str:
    """Record only where and when the file was downloaded. The human check fields and
    their timestamps are left exactly as they are."""
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return "NO_RECORD"
    problem = source_problem(downloaded_from, downloaded_at)
    if problem:
        print(f"download source refused: {problem}\nNothing was written.")
        return SOURCE_REFUSED
    rec["downloaded_from"] = downloaded_from
    rec["downloaded_at"] = downloaded_at
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"recorded: downloaded from {downloaded_from} on {downloaded_at}")
    gaps = attestation_gaps(rec)
    print("attested" if not gaps else "NOT usable yet: " + "; ".join(gaps))
    return CORROBORATED if not gaps else PENDING_HUMAN_REVIEW


def registration() -> dict | None:
    """The registration record, if one exists. Read by prescribed_thresholds."""
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _when(value: object) -> datetime | None:
    """An ISO date or date-time as an aware datetime, or None. Naive means UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def source_problem(url: object, at: object) -> str | None:
    """Why this (address, date) pair is not a usable download source, or None."""
    if not official_source_url(url):
        return (f"{url!r} is not an https address on an official host "
                f"({', '.join(sorted(OFFICIAL_SOURCE_HOSTS))})")
    when = _when(at)
    if when is None:
        return f"{at!r} is not an ISO date (YYYY-MM-DD or a full timestamp)"
    if when.date() < PUBLISHED:
        return f"{at} is before the instrument was published ({PUBLISHED.isoformat()})"
    if when > datetime.now(timezone.utc) + _CLOCK_SLACK:
        return f"{at} is in the future"
    return None


def corroboration_problem(rec: dict) -> str | None:
    """Why the record's corroborating copy does not corroborate, or None."""
    copy_ = rec.get("corroborating_copy")
    if not copy_:
        return "no corroborating copy from an official host"
    if not isinstance(copy_, dict):
        return "corroborating_copy is not a record"
    problem = source_problem(copy_.get("url"), copy_.get("retrieved_at"))
    if problem:
        return f"corroborating copy: {problem}"
    sha = copy_.get("sha256")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        return "corroborating copy has no well-formed sha256"
    match = copy_.get("match")
    if match not in CORROBORATING_MATCHES:
        return f"corroborating copy match is {match!r}, not one of {CORROBORATING_MATCHES}"
    if match == "identical" and sha != rec.get("artifact_sha256"):
        return "corroborating copy is called identical but its sha256 is not the held artifact's"
    if match == "text-identical" and (not rec.get("operative_clause")
                                      or copy_.get("matched_clause") != rec.get("operative_clause")):
        return ("corroborating copy is called text-identical but does not carry the held "
                "operative clause verbatim")
    return None


def provenance_problem(rec: dict) -> str | None:
    """None when the record says where the artifact came from, or an official copy
    corroborates it. A recorded source that fails is a contradiction, and is refused
    whatever the corroboration says."""
    if rec.get("downloaded_from") is not None or rec.get("downloaded_at") is not None:
        problem = source_problem(rec.get("downloaded_from"), rec.get("downloaded_at"))
        return None if problem is None else f"the recorded download source is refused: {problem}"
    problem = corroboration_problem(rec)
    if problem is None:
        return None
    return f"where the file was downloaded from is not recorded, and {problem}"


_HUMAN_CHECKS = ("identity_checked_by", "identity_checked_at",
                 "verbatim_clause_checked_by", "verbatim_clause_checked_at")


def attestation_gaps(rec: dict | None) -> list[str]:
    """Everything that keeps this record from being usable law. Empty means attested."""
    if not isinstance(rec, dict) or not rec:
        return ["no registration on record"]
    gaps = [k for k in _HUMAN_CHECKS if not rec.get(k)]
    if rec.get("status") != CORROBORATED:
        gaps.append("status is not CORROBORATED")
    problem = provenance_problem(rec)
    if problem:
        gaps.append(f"source: {problem}")
    return gaps


def is_attested(rec: dict | None) -> bool:
    """Both human checks recorded, the status says so, and the file's source is
    either recorded or corroborated from an official host."""
    return not attestation_gaps(rec)


# ── test support ──────────────────────────────────────────────────────────────
from contextlib import contextmanager as _contextmanager


def registered_unattested_stub() -> dict:
    return {"artifact_sha256": "sha256:" + "ab" * 32,
            "identity_checked_by": None, "identity_checked_at": None,
            "verbatim_clause_checked_by": None, "verbatim_clause_checked_at": None,
            "status": PENDING_HUMAN_REVIEW}


def attested_stub(reviewer: str = "TEST") -> dict:
    """Acquired, both checks done, and a download source recorded. The address is a
    test value on an official host, not a real Gazette file."""
    return {"artifact_sha256": "sha256:" + "ab" * 32,
            "downloaded_from": "https://egazette.gov.in/test-stub.pdf",
            "downloaded_at": "2026-01-01",
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

    # ── provenance (A-001): two human checks do not say where the file came from ──
    _SOURCE_KEYS = ("downloaded_from", "downloaded_at", "corroborating_copy")
    unsourced = {k: v for k, v in attested_stub().items() if k not in _SOURCE_KEYS}
    check(not is_attested(unsourced),
          "both human checks with no recorded source and no corroboration is NOT attested")
    gazette = "https://egazette.gov.in/WriteReadData/2025/268124.pdf"
    check(is_attested(unsourced | {"downloaded_from": gazette,
                                   "downloaded_at": "2025-12-02"}),
          "...and a Gazette download address with its date makes it attested")
    for label, extra in (
            ("an http address", {"downloaded_from": gazette.replace("https", "http"),
                                 "downloaded_at": "2025-12-02"}),
            ("a commentary site", {"downloaded_from": "https://taxguru.in/gsr-880e.pdf",
                                   "downloaded_at": "2025-12-02"}),
            ("an address with no date", {"downloaded_from": gazette}),
            ("a date with no address", {"downloaded_at": "2025-12-02"}),
            ("a date that is not a date", {"downloaded_from": gazette,
                                           "downloaded_at": "last week"}),
            ("a download before the instrument was published",
             {"downloaded_from": gazette, "downloaded_at": "2025-11-30"}),
            ("a download dated in the future",
             {"downloaded_from": gazette, "downloaded_at": "2999-01-01"})):
        check(not is_attested(unsourced | extra), f"{label} is not a recorded source")

    held = "sha256:" + "ab" * 32
    copy_ok = {"url": gazette, "retrieved_at": "2026-09-17T05:40:14Z",
               "sha256": held, "match": "identical",
               "recorded_by": "automated corroboration, not a human check"}
    check(is_attested(unsourced | {"corroborating_copy": copy_ok}),
          "an identical official copy stands in for the unrecorded download source")
    for label, bad in (
            ("an 'identical' copy whose hash differs from the held artifact",
             copy_ok | {"sha256": "sha256:" + "cd" * 32}),
            ("a copy that only resembles the artifact", copy_ok | {"match": "similar"}),
            ("a copy that was not found", copy_ok | {"match": "not-found"}),
            ("a copy from a commentary site", copy_ok | {"url": "https://taxguru.in/x.pdf"}),
            ("a copy with no retrieval date",
             {k: v for k, v in copy_ok.items() if k != "retrieved_at"}),
            ("a copy with a malformed hash", copy_ok | {"sha256": "44faa58c"}),
            ("a 'text-identical' copy that does not carry the held clause",
             copy_ok | {"match": "text-identical", "sha256": "sha256:" + "cd" * 32}),
            ("a copy that is not a record", "https://egazette.gov.in/x.pdf")):
        check(not is_attested(unsourced | {"corroborating_copy": bad}),
              f"{label} does not corroborate")
    clause = "paid up capital ... s hall not exceed rupees ten crores ... respectively."
    check(is_attested(unsourced | {"operative_clause": clause, "corroborating_copy": copy_ok | {
              "match": "text-identical", "sha256": "sha256:" + "cd" * 32,
              "matched_clause": clause}}),
          "a text-identical copy carrying the held clause verbatim corroborates")
    check(not is_attested(unsourced | {"downloaded_from": "https://taxguru.in/x.pdf",
                                       "downloaded_at": "2025-12-02",
                                       "corroborating_copy": copy_ok}),
          "a recorded non-official source is a contradiction that corroboration does not cure")
    check(not is_attested(registered_unattested_stub() | {"corroborating_copy": copy_ok}),
          "provenance never stands in for the human checks")
    gaps = attestation_gaps(unsourced)
    check(any("source" in g for g in gaps) and not any("checked_by" in g for g in gaps),
          f"the gap is named as the source, not as a missing reviewer ({gaps})")

    # The record on disk. Asserted against whatever state it is in, so the suite does
    # not flip red the day the founder records their own download source.
    live = json.loads(RECORD.read_text()) if RECORD.is_file() else None
    if live is not None:
        check(is_attested(live), f"the live record is attested ({attestation_gaps(live)})")
        cc = live.get("corroborating_copy")
        if cc:
            check(isinstance(cc, dict) and cc.get("sha256") == live.get("artifact_sha256")
                  and "not a human check" in str(cc.get("recorded_by", "")),
                  "...its corroborating copy is the held bytes, labelled as automated")
        if live.get("downloaded_from") is None and live.get("downloaded_at") is None:
            # Attested only through the copy. Without it this is exactly the record
            # A-001 found, and it must be refused.
            check(not is_attested({k: v for k, v in live.items()
                                   if k != "corroborating_copy"}),
                  "...and without its corroborating copy it is not (the A-001 record)")

    # ── the CLI records a source, and refuses a bad one without writing ──────
    import tempfile
    mod = sys.modules[__name__]
    saved = (mod.RECORD, mod.STORE)
    with tempfile.TemporaryDirectory() as td:
        mod.RECORD, mod.STORE = Path(td) / "rec.json", Path(td) / "text.txt"
        try:
            mod.RECORD.write_text(json.dumps(unsourced))
            before = mod.RECORD.read_text()
            check(main(["--source", "--from", "https://taxguru.in/x.pdf",
                        "--at", "2025-12-02"]) != 0
                  and mod.RECORD.read_text() == before,
                  "--source refuses a commentary site and writes nothing")
            check(main(["--source", "--from", gazette]) != 0
                  and mod.RECORD.read_text() == before,
                  "--source needs both --from and --at")
            check(main(["--source", "--from", gazette, "--at", "2025-12-02"]) == 0,
                  "--source records an official address and date")
            after = json.loads(mod.RECORD.read_text())
            check(after["downloaded_from"] == gazette and after["downloaded_at"] == "2025-12-02",
                  "...both fields are written as given")
            check(all(after[k] == unsourced[k] for k in unsourced),
                  "...and nothing else changes: the human checks keep their names and times")
            check(is_attested(after), "...which makes the record attested")

            mod.RECORD.write_text(json.dumps(registered_unattested_stub()))
            before = mod.RECORD.read_text()
            check(main(["--attest", "R1", "--from", gazette.replace("https", "http"),
                        "--at", "2025-12-02"]) != 0
                  and mod.RECORD.read_text() == before,
                  "--attest with a bad source stamps nothing, not even the reviewer")
            check(main(["--attest", "R1", "--from", gazette, "--at", "2025-12-02"]) == 0
                  and is_attested(json.loads(mod.RECORD.read_text())),
                  "--attest --from --at records the reviewer and the source together")

            doc = Path(td) / "g880.txt"
            doc.write_text(good)
            before = mod.RECORD.read_text()
            check(main([str(doc), "--from", "https://taxguru.in/x", "--at", "2025-12-02"]) != 0
                  and mod.RECORD.read_text() == before and not mod.STORE.exists(),
                  "register refuses a bad source before writing anything")
            check(main([str(doc), "--from", gazette, "--at", "2025-12-02"]) == 0,
                  "register accepts --from/--at")
            reg = json.loads(mod.RECORD.read_text())
            check(reg["downloaded_from"] == gazette and reg["status"] == PENDING_HUMAN_REVIEW
                  and not is_attested(reg),
                  "...records them, and a source alone does not attest")
        finally:
            mod.RECORD, mod.STORE = saved

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


USAGE = """usage: register_gsr880e.py <downloaded-file> [--from <URL> --at <DATE>]
       register_gsr880e.py --attest <reviewer-id> [--from <URL> --at <DATE>]
       register_gsr880e.py --source --from <URL> --at <DATE>
       register_gsr880e.py --test
<URL>: the https address you downloaded the file from, on one of
       """ + ", ".join(sorted(OFFICIAL_SOURCE_HOSTS)) + """
<DATE>: when you downloaded it, YYYY-MM-DD (or a full ISO timestamp)
--source records only the address and date; it leaves the checks as they are."""


def _source_flags(args: list[str]) -> tuple[list[str], str | None, str | None] | None:
    """(remaining args, --from, --at); None when the flags are malformed."""
    rest: list[str] = []
    got: dict[str, str] = {}
    i = 0
    while i < len(args):
        if args[i] in ("--from", "--at"):
            if i + 1 >= len(args) or args[i] in got:
                return None
            got[args[i]] = args[i + 1]
            i += 2
            continue
        rest.append(args[i])
        i += 1
    if len(got) == 1:
        return None                     # an address without a date, or the reverse
    return rest, got.get("--from"), got.get("--at")


def main(argv: list[str]) -> int:
    if argv[:1] == ["--test"]:
        return _test()
    parsed = _source_flags(argv)
    if parsed is None:
        print("--from and --at go together, once each\n" + USAGE)
        return 2
    rest, src_url, src_at = parsed
    if rest[:1] == ["--source"]:
        if len(rest) != 1 or src_url is None:
            print(USAGE)
            return 2
        return {SOURCE_REFUSED: 2, "NO_RECORD": 1}.get(record_source(src_url, src_at), 0)
    if rest[:1] == ["--attest"]:
        if len(rest) != 2:
            print(USAGE)
            return 2
        out = attest(rest[1], src_url, src_at)
        return 0 if out == CORROBORATED else (2 if out == SOURCE_REFUSED else 1)
    if len(rest) != 1 or rest[0].startswith("--"):
        print(__doc__)
        print(USAGE)
        return 2
    out = register(Path(rest[0]), src_url, src_at)
    return 2 if out == SOURCE_REFUSED else EXIT.get(out, 1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
