#!/usr/bin/env python3
"""Register a human-downloaded G.S.R. 700(E) so the thresholds become servable.

Two official routes to this instrument are blocked and neither is our fault to
fix from here: indiacode.gov.in/robots.txt answers 502, so the compliant fetcher
declines under RFC 9309; and egazette.gov.in sends no intermediate certificate,
chaining to an ISRG root this machine's trust store does not carry. See
corpus/sources/acquisition_gsr700e.json for the full attempt chain.

A person with a browser is not a crawler and has a current trust store, so the
handoff is: download the file, run this, and it verifies, hashes and registers
it. That is the same shape as scripts/acquire_rules.py, which exists because the
same thing happened with the Board Rules.

## What this refuses

Identity, before anything else. India Code carries the principal Rules, six
amendments to them, and consolidated reprints, all with near-identical titles.
Registering an amendment as the principal Rules — or the 2021 amendment as the
2022 one — would silently corrupt every threshold built on top. So the document
must identify itself as G.S.R. 700(E) of 15-09-2022 AND carry the operative
clause, and anything else is rejected with what was found.

## What it does NOT do

It does not set the thresholds to VERIFIED. VERIFIED in this system means a
hashed local artifact PLUS human review, and a script cannot perform the second
half. It moves them to CORROBORATED, prints the clause verbatim for a person to
read, and says what remains.

## And where the file came from (A-001, P-2)

The two human checks say the file is the right instrument and its clause is
verbatim. Neither says where the file came from, and this record's own
attests_to makes no claim about that either -- but `prescribed_thresholds`
serves Rs 4 crore / Rs 40 crore with an ADDRESS printed beside them, and an
address the record cannot support is a citation we invented. So `is_attested()`
requires, on top of the human checks and the classifier's own
VERIFIED_INSTRUMENT outcome, either the download address (https, Gazette or
India Code) with its date, recorded by the person who downloaded it, or a copy
fetched from such a host that is byte-identical or carries the held clause
verbatim. The rule and its wording live in checker/provenance.SourcePolicy,
shared with the other register scripts, so the four cannot drift.
"""
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.provenance import (  # noqa: E402
    EXIT_WORDING, GAZETTE_OR_INDIA_CODE_HOSTS, NO_RECORD, SOURCE_CONFLICT, SOURCE_RECORDED,
    ROOT, SOURCE_REFUSED, SourcePolicy, cli_exit, file_digest, repo_relative, split_source_flags)

STORE = Path("corpus/rules/gsr_700e_2022.txt")
RECORD = Path("corpus/sources/gsr700e_registration.json")

SOURCE_URL = "https://indiacode.gov.in/handle/123456789/508916"
BITSTREAM_ID = "6d5e9902-44a7-4ee5-975a-1fd7fc5d51a5"

# The host class this record may cite: the Gazette that published the instrument and
# India Code, which is where the record's own source_url points. The ministry's site
# is official but nothing here came from it.
SOURCE_HOSTS = GAZETTE_OR_INDIA_CODE_HOSTS
# The instrument's date of publication, printed on the file. No copy of it can have
# been downloaded earlier.
PUBLISHED = date(2022, 9, 15)
SOURCE_POLICY = SourcePolicy(SOURCE_HOSTS, PUBLISHED)

# The record's own status, distinct from any evidence state. A registered
# artifact is not usable law until both human checks are recorded against it.
PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

ATTESTATIONS = (
    "identity: this file is G.S.R. 700(E) of 15-09-2022, and not the principal "
    "2014 Rules, the 2021 amendment, or a consolidated reprint",
    "clause: the operative wording recorded here is verbatim from the file, "
    "with no repair, normalisation or reflow",
)

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"
WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
CLAUSE_NOT_FOUND = "CLAUSE_NOT_FOUND"
UNREADABLE = "UNREADABLE"

EXIT = {VERIFIED_INSTRUMENT: 0, WRONG_INSTRUMENT: 2, CLAUSE_NOT_FOUND: 3, UNREADABLE: 4}

# Identity markers. Each must appear; together they distinguish this instrument
# from its six near-identically-titled siblings.
_GSR = re.compile(r"g\.?\s*s\.?\s*r\.?\s*\.?\s*700\s*\(\s*e\s*\)", re.I)
_TITLE = re.compile(r"specification\s+of\s+definitio?n?s?\s+details", re.I)
_YEAR = re.compile(r"\b2022\b")

# The operative clause. Amounts are matched as words because that is how the
# instrument writes them; a digit-only match would also hit page numbers.
_CLAUSE = re.compile(
    r"(paid[\s-]*up\s+capital[^.]{0,200}?turnover[^.]{0,200}?"
    r"(four\s+crore|rupees\s+four\s+crore)[^.]{0,120}?(forty\s+crore)[^.]{0,80}\.)",
    re.I | re.S)

# Instruments we must NOT accept in its place.
_SIBLINGS = (
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
        missing.append("the notification number G.S.R. 700(E)")
    if not _TITLE.search(text):
        missing.append("the title 'Specification of Definition Details'")
    if not _YEAR.search(text):
        missing.append("the year 2022")
    if missing:
        return WRONG_INSTRUMENT, "does not identify itself by " + ", ".join(missing), ""

    m = _CLAUSE.search(text)
    if not m:
        return (CLAUSE_NOT_FOUND,
                "identifies as G.S.R. 700(E) but the operative clause naming four crore and "
                "forty crore was not found — the extraction may be partial, or this is a "
                "different printing", "")
    clause = re.sub(r"\s+", " ", m.group(1)).strip()
    return VERIFIED_INSTRUMENT, "identifies as G.S.R. 700(E) of 2022 and carries the clause", clause


def register(src: Path, downloaded_from: str | None = None,
             downloaded_at: str | None = None) -> str:
    if downloaded_from is not None or downloaded_at is not None:
        problem = SOURCE_POLICY.source_problem(downloaded_from, downloaded_at)
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
    held = repo_relative(src)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(text, encoding="utf-8")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "instrument_id": "INDIACODE_GSR_700E_DEFINITIONS_AMENDMENT_2022",
        "title": "G.S.R. 700(E) — Companies (Specification of Definition Details) "
                 "Amendment Rules, 2022, dated 15-09-2022",
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
        # Which file this record holds, so the guard can re-read it later. A record
        # that names no file cannot be checked, and is refused rather than trusted.
        "local_artifact": held,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(
            STORE.read_bytes()).hexdigest(),
        "operative_clause": clause,
        "classification": outcome,
        # The two human checks. Null until a person runs --attest. Nothing
        # downstream may treat this instrument as usable while either is null:
        # hashing proves the bytes did not change, not that they are the right
        # instrument or that the clause survived extraction intact.
        "identity_checked_by": None,
        "identity_checked_at": None,
        "verbatim_clause_checked_by": None,
        "verbatim_clause_checked_at": None,
        "status": PENDING_HUMAN_REVIEW,
        "attests_to": ATTESTATIONS,
    }, indent=1) + "\n", encoding="utf-8")

    if held is None:
        print("\nNOTE: the file you registered is OUTSIDE this repository, so the record")
        print("cannot name the file it holds, and the guard refuses a record it cannot")
        print("re-read. Copy the artifact into corpus/sources/ and register that copy.")
    print(f"stored         : {STORE}")
    print(f"record         : {RECORD}")
    print(f"status         : {PENDING_HUMAN_REVIEW}")
    print("\nThe artifact is stored and hashed. It is NOT yet usable law.")
    print("Two human checks remain, and both are recorded, not assumed:")
    for a in ATTESTATIONS:
        print(f"  - {a}")
    print("\nWhen you have done both:")
    print("  python3 scripts/register_gsr700e.py --attest <your-reviewer-id>")
    print("\nNo constant needs editing. prescribed_thresholds reads this record,")
    print("so the threshold becomes servable when the attestation lands and not")
    print("before. Then run scripts/run_tests.sh and close S-002.")
    return outcome


ATTEST_REFUSED = "ATTEST_REFUSED"


def attest(reviewer_id: str, downloaded_from: str | None = None,
           downloaded_at: str | None = None, *, replace: bool = False) -> str:
    """Record that a person performed both checks, and optionally where they got the
    file. Without this the artifact is stored but not usable, and
    prescribed_thresholds keeps refusing. A bad source, or one that would silently
    replace a different recorded source, is refused BEFORE anything is stamped.

    A reviewer id, not an address: benchmark and corpus files are meant to be
    distributable and a reviewer's address is not part of the evidence.
    """
    rec = registration()
    if rec is None:
        print(f"no registration to attest: {RECORD} does not exist")
        print("register the downloaded file first")
        return NO_RECORD
    if "@" in reviewer_id:
        print("record a pseudonymous reviewer id, not an email address")
        return ATTEST_REFUSED

    # The stored text must still hash to what was registered. An attestation
    # against a file that changed after registration attests to nothing.
    if STORE.is_file():
        now_hash = "sha256:" + hashlib.sha256(STORE.read_bytes()).hexdigest()
        if now_hash != rec.get("stored_text_sha256"):
            print("REFUSED: the stored text has changed since registration")
            print(f"  registered : {rec.get('stored_text_sha256')}")
            print(f"  on disk    : {now_hash}")
            print("re-register the artifact before attesting to it")
            return ATTEST_REFUSED
    else:
        print(f"REFUSED: {STORE} is missing; nothing to attest to")
        return ATTEST_REFUSED

    if downloaded_from is not None or downloaded_at is not None:
        outcome, written, message = SOURCE_POLICY.record_source(
            rec, downloaded_from, downloaded_at, replace=replace)
        if outcome in (SOURCE_REFUSED, SOURCE_CONFLICT):
            print(message)
            return outcome
        rec = written if written is not None else rec

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = dict(rec)
    rec.update({
        "identity_checked_by": reviewer_id,
        "identity_checked_at": stamp,
        "verbatim_clause_checked_by": reviewer_id,
        "verbatim_clause_checked_at": stamp,
        "status": CORROBORATED,
    })
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {stamp}")
    print(f"status         : {CORROBORATED}")
    gaps = attestation_gaps(rec)
    if gaps:
        print("NOT usable yet: " + "; ".join(gaps))
        print("The person who downloaded the file records where it came from:")
        print("  python3 scripts/register_gsr700e.py --source --from <URL> --at <YYYY-MM-DD>")
        return PENDING_HUMAN_REVIEW
    print("\nprescribed_thresholds derives its state from this record, so the")
    print("small-company limits are now servable. Run scripts/run_tests.sh and")
    print("close S-002 with the artifact hash, reviewer id and timestamps above.")
    return CORROBORATED


def record_source(downloaded_from: str | None, downloaded_at: str | None, *,
                  replace: bool = False) -> str:
    """Record only where and when the file was downloaded. The human check fields and
    their timestamps are left exactly as they are. A different source already on
    record is not overwritten unless replace is set."""
    outcome, written, message = SOURCE_POLICY.record_source(
        registration(), downloaded_from, downloaded_at, replace=replace)
    print(message)
    if outcome in (NO_RECORD, SOURCE_REFUSED, SOURCE_CONFLICT):
        return outcome
    if outcome == SOURCE_RECORDED:
        RECORD.write_text(json.dumps(written, indent=1) + "\n", encoding="utf-8")
    rec = written if written is not None else registration()
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


def local_copy_note(rec: dict | None) -> str | None:
    """What to say when the record names a stored copy that is no longer on disk.
    Not a gap: the corroboration is the address and hash recorded at fetch time."""
    return SOURCE_POLICY.local_copy_note(rec)


def attestation_gaps(rec: dict | None) -> list[str]:
    """Everything that keeps this record from being usable law. Empty means attested."""
    return SOURCE_POLICY.attestation_gaps(rec)


def provenance_problem(rec: dict) -> str | None:
    """Why the record does not say where its artifact came from, or None."""
    return SOURCE_POLICY.provenance_problem(rec)


def is_attested(rec: dict | None) -> bool:
    """Classified VERIFIED_INSTRUMENT, both human checks recorded, the status says so,
    and the file's source is either recorded or corroborated from a Gazette or India
    Code host (SOURCE_HOSTS)."""
    return not attestation_gaps(rec)


def served_source_url(rec: dict | None) -> str | None:
    """The address a served figure may point to: the recorded download, else the
    corroborating copy. None unless the record is attested -- an unusable record
    names no source for a figure, because no figure is served from it."""
    return SOURCE_POLICY.source_of(rec) if is_attested(rec) else None


# The stubs name a file this repository really holds, with its real digest: the
# guard re-reads the artifact now, so a stub carrying an invented hash would be
# a record of a file that does not exist -- which is what it must refuse.
_STUB_ARTIFACT = "corpus/sources/gsr700e_2022.pdf"
_STUB_ARTIFACT_SHA = file_digest(ROOT / _STUB_ARTIFACT) or "sha256:" + "00" * 32


# ── test support ──────────────────────────────────────────────────────────────
# The acquisition state is on-disk and changes when a reviewer attests. Tests
# that exercise "refuses while unacquired" or "servable once acquired" must
# CONTROL that state rather than depend on the ambient record, or they flip red
# the moment 700(E) is attested (which is exactly what happened). These stub the
# registration lookup within a block. Test-only; no production path calls them.
from contextlib import contextmanager as _contextmanager
import sys as _sys


def registered_unattested_stub() -> dict:
    """A registration record that exists but carries neither human check."""
    return {"artifact_sha256": _STUB_ARTIFACT_SHA,
            "local_artifact": _STUB_ARTIFACT,
            "classification": VERIFIED_INSTRUMENT,
            "operative_clause": "paid up capital and turnover of the small company shall "
                                "not exceed rupees four crore and rupees forty crore [F .",
            "identity_checked_by": None, "identity_checked_at": None,
            "verbatim_clause_checked_by": None, "verbatim_clause_checked_at": None,
            "status": PENDING_HUMAN_REVIEW}


def attested_stub(reviewer: str = "TEST") -> dict:
    """Acquired, both checks done, and a download source recorded. The address is a
    test value on an official host, not a real Gazette file."""
    return {"artifact_sha256": _STUB_ARTIFACT_SHA,
            "local_artifact": _STUB_ARTIFACT,
            "classification": VERIFIED_INSTRUMENT,
            "operative_clause": "paid up capital and turnover of the small company shall "
                                "not exceed rupees four crore and rupees forty crore [F .",
            "downloaded_from": "https://egazette.gov.in/test-stub.pdf",
            "downloaded_at": "2026-01-01",
            "identity_checked_by": reviewer, "identity_checked_at": "2026-01-01T00:00:00Z",
            "verbatim_clause_checked_by": reviewer,
            "verbatim_clause_checked_at": "2026-01-01T00:00:00Z",
            "status": CORROBORATED}


@_contextmanager
def stub_registration(rec):
    """Force registration() to return `rec` within the block.

    rec=None simulates 'not acquired'; registered_unattested_stub() simulates
    'downloaded but not attested'; attested_stub() simulates 'acquired'. Callers
    that do `from scripts.register_gsr700e import registration` inside a function
    pick up the patched attribute because the import runs at call time.
    """
    mod = _sys.modules[__name__]
    orig = mod.registration
    mod.registration = lambda: rec
    try:
        yield
    finally:
        mod.registration = orig


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

    print("register_gsr700e")

    real = ("MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 15th September, 2022 "
            "G.S.R. 700(E).—In exercise of the powers conferred by sub-sections (1) and (2) of "
            "section 469 of the Companies Act, 2013, the Central Government hereby makes the "
            "following rules further to amend the Companies (Specification of definition details) "
            "Rules, 2014, namely:— in clause (t), paid up capital and turnover of the small "
            "company shall not exceed rupees four crore and rupees forty crore respectively.")
    out, why, clause = classify(real)
    check(out == VERIFIED_INSTRUMENT, f"the real instrument verifies ({out}: {why})")
    check("four crore" in clause and "forty crore" in clause,
          f"...and the clause is captured verbatim ({clause[:60]}…)")

    sibling = real.replace("700(E)", "92(E)").replace("2022", "2021")
    out2, why2, _ = classify(sibling)
    check(out2 == WRONG_INSTRUMENT, f"the 2021 sibling is refused ({out2})")
    check("92(E)" in why2, f"...naming what it actually is ({why2})")

    principal = ("The Companies (Specification of definitions details) Rules, 2014. In exercise "
                 "of the powers conferred by section 469, 2014.")
    out3, why3, _ = classify(principal)
    check(out3 == WRONG_INSTRUMENT, "the principal 2014 Rules are refused")

    partial = ("G.S.R. 700(E) dated 15th September 2022 amending the Companies (Specification of "
               "definition details) Rules, 2014. [page 1 of 3]")
    out4, why4, _ = classify(partial)
    check(out4 == CLAUSE_NOT_FOUND,
          f"a correct instrument missing the clause is not accepted ({out4})")
    check("partial" in why4, "...and says the extraction may be partial")

    out5, _, _ = classify("")
    check(out5 == UNREADABLE, "empty text is UNREADABLE, not a rejection of identity")

    check(set(EXIT) == {VERIFIED_INSTRUMENT, WRONG_INSTRUMENT, CLAUSE_NOT_FOUND, UNREADABLE},
          "every outcome has an exit code")
    check(EXIT[VERIFIED_INSTRUMENT] == 0 and all(v for k, v in EXIT.items()
                                                 if k != VERIFIED_INSTRUMENT),
          "only success exits zero")

    # It must not be possible for this script to declare VERIFIED.
    src = Path(__file__).read_text()
    check('"evidence_state": "CORROBORATED"' in src,
          "the registration records CORROBORATED, never VERIFIED")

    # ── P-2: the A-001 guard, on the record whose figures are actually served ──
    # Two human checks say this is the right instrument and its clause is verbatim.
    # Neither says where the file came from -- and prescribed_thresholds serves the
    # 2022 amounts with an address printed beside them.
    check(not is_attested(None), "no record is not attested")
    check(not is_attested(registered_unattested_stub()),
          "a registered but unattested record is not attested")
    check(is_attested(attested_stub()), "an attested record is attested")
    half = attested_stub(); half["verbatim_clause_checked_by"] = None
    check(not is_attested(half), "one of the two checks alone is not enough")

    _SOURCE_KEYS = ("downloaded_from", "downloaded_at", "corroborating_copy")
    unsourced = {k: v for k, v in attested_stub().items() if k not in _SOURCE_KEYS}
    check(not is_attested(unsourced),
          "both human checks with no recorded source and no corroboration is NOT attested")
    gaps = attestation_gaps(unsourced)
    check(any(g.startswith("source:") for g in gaps)
          and not any("checked_by" in g for g in gaps),
          f"...and the gap is named as the source, not as a missing reviewer ({gaps})")
    gazette = "https://egazette.gov.in/WriteReadData/2022/238857.pdf"
    india = "https://indiacode.gov.in/handle/123456789/508916"
    check(is_attested(unsourced | {"downloaded_from": gazette, "downloaded_at": "2022-09-16"})
          and is_attested(unsourced | {"downloaded_from": india, "downloaded_at": "2026-09-04"}),
          "a Gazette or India Code download address with its date makes it attested")
    for label, extra in (
            ("an http address", {"downloaded_from": gazette.replace("https", "http"),
                                 "downloaded_at": "2026-09-04"}),
            ("a commentary site", {"downloaded_from": "https://taxguru.in/gsr-700e.pdf",
                                   "downloaded_at": "2026-09-04"}),
            ("the ministry's own site", {"downloaded_from": "https://www.mca.gov.in/x.pdf",
                                         "downloaded_at": "2026-09-04"}),
            ("an address with no date", {"downloaded_from": gazette}),
            ("a date with no address", {"downloaded_at": "2026-09-04"}),
            ("an address carrying a space", {"downloaded_from": " " + gazette,
                                             "downloaded_at": "2026-09-04"}),
            ("a download before the instrument was published",
             {"downloaded_from": gazette, "downloaded_at": "2022-09-14"}),
            ("a download dated in the future",
             {"downloaded_from": gazette, "downloaded_at": "2999-01-01"})):
        check(not is_attested(unsourced | extra), f"{label} is not a recorded source")

    clause = unsourced["operative_clause"]
    copy_ok = {"url": gazette, "retrieved_at": "2026-09-17T09:26:48Z",
               "sha256": "sha256:" + "cd" * 32, "match": "text-identical",
               "matched_clause": clause,
               "recorded_by": "automated corroboration, not a human check"}
    check(is_attested(unsourced | {"corroborating_copy": copy_ok}),
          "a Gazette copy carrying the held clause verbatim stands in for the unrecorded source")
    for label, bad in (
            ("a copy whose clause differs", copy_ok | {"matched_clause": "something else"}),
            ("a copy that only resembles the artifact", copy_ok | {"match": "similar"}),
            ("a copy that was not found", copy_ok | {"match": "not-found"}),
            ("a copy from a commentary site", copy_ok | {"url": "https://taxguru.in/x.pdf"}),
            ("a copy with a malformed hash", copy_ok | {"sha256": "bb19f1b2"}),
            ("an 'identical' copy whose hash is not the artifact's",
             copy_ok | {"match": "identical"})):
        check(not is_attested(unsourced | {"corroborating_copy": bad}),
              f"{label} does not corroborate")
    check(not is_attested(unsourced | {"downloaded_from": "https://taxguru.in/x.pdf",
                                       "downloaded_at": "2026-09-04",
                                       "corroborating_copy": copy_ok}),
          "a recorded non-official source is a contradiction that corroboration does not cure")
    check(not is_attested(registered_unattested_stub() | {"corroborating_copy": copy_ok}),
          "provenance never stands in for the human checks")
    for cls in (WRONG_INSTRUMENT, CLAUSE_NOT_FOUND, UNREADABLE, None):
        check(not is_attested(attested_stub() | {"classification": cls}),
              f"a record classified {cls} is not attested, whatever the checks say")

    # What a served figure may point at.
    check(served_source_url(attested_stub()) == "https://egazette.gov.in/test-stub.pdf",
          "an attested record serves its recorded download address")
    check(served_source_url(unsourced | {"corroborating_copy": copy_ok}) == gazette,
          "...or, with none recorded, the corroborating copy's address")
    check(served_source_url(unsourced) is None and served_source_url(None) is None
          and served_source_url(registered_unattested_stub()) is None,
          "...and nothing at all for a record that is not attested")

    # The record on disk, asserted against whatever state it is in, so the suite does
    # not flip red the day the founder records their own download source.
    live = json.loads(RECORD.read_text()) if RECORD.is_file() else None
    if live is not None:
        check(is_attested(live), f"the live record is attested ({attestation_gaps(live)})")
        cc = live.get("corroborating_copy")
        if cc:
            check(isinstance(cc, dict)
                  and cc.get("matched_clause") == live.get("operative_clause")
                  and "not a human check" in str(cc.get("recorded_by", "")),
                  "...its corroborating copy carries the held clause, labelled as automated")
        if live.get("downloaded_from") is None and live.get("downloaded_at") is None:
            check(not is_attested({k: v for k, v in live.items()
                                   if k != "corroborating_copy"}),
                  "...and without that copy it is not attested (the A-001 record)")

    # ── the CLI records a source, and refuses a bad one without writing ──────
    import io
    import tempfile
    from contextlib import redirect_stdout
    mod = sys.modules[__name__]
    saved = (mod.RECORD, mod.STORE)
    with tempfile.TemporaryDirectory() as td:
        mod.RECORD, mod.STORE = Path(td) / "rec.json", Path(td) / "text.txt"
        try:
            mod.RECORD.write_text(json.dumps(unsourced))
            before = mod.RECORD.read_text()
            with redirect_stdout(io.StringIO()):
                rc_bad = main(["--source", "--from", "https://taxguru.in/x.pdf",
                               "--at", "2026-09-04"])
                rc_half = main(["--source", "--from", gazette])
            check(rc_bad == 2 and rc_half == 2 and mod.RECORD.read_text() == before,
                  "--source refuses a commentary site, and needs both --from and --at")
            with redirect_stdout(io.StringIO()):
                rc_ok = main(["--source", "--from", india, "--at", "2026-09-04"])
            after = json.loads(mod.RECORD.read_text())
            check(rc_ok == 0 and after["downloaded_from"] == india
                  and after["downloaded_at"] == "2026-09-04",
                  "--source records an official address and date")
            check(all(after[k] == unsourced[k] for k in unsourced),
                  "...and nothing else changes: the human checks keep their names and times")
            out = io.StringIO()
            with redirect_stdout(out):
                rc_conflict = main(["--source", "--from", gazette, "--at", "2026-09-05"])
            check(rc_conflict == 2 and json.loads(mod.RECORD.read_text()) == after
                  and "--replace" in out.getvalue(),
                  "--source will not silently replace a different recorded source")
            with redirect_stdout(io.StringIO()):
                rc_rep = main(["--source", "--replace", "--from", gazette, "--at", "2026-09-05"])
            check(rc_rep == 0
                  and json.loads(mod.RECORD.read_text())["downloaded_from"] == gazette,
                  "...unless --replace is given")
            mod.RECORD.unlink()
            with redirect_stdout(io.StringIO()):
                rc_none = main(["--source", "--from", gazette, "--at", "2026-09-04"])
            check(rc_none == 2 and not mod.RECORD.exists(),
                  "with no registration to act on, --source exits 2 and writes nothing")
            check("no registration" in USAGE and "nothing is written" in USAGE,
                  "...and the usage line's exit wording says so")

            # attesting stamps the reviewer AND the source together, or neither
            mod.STORE.write_text("x")
            staged = registered_unattested_stub() | {
                "stored_text_sha256": "sha256:" + hashlib.sha256(b"x").hexdigest()}
            mod.RECORD.write_text(json.dumps(staged))
            before = mod.RECORD.read_text()
            with redirect_stdout(io.StringIO()):
                rc_attest_bad = main(["--attest", "R1", "--from", "https://taxguru.in/x.pdf",
                                      "--at", "2026-09-04"])
            check(rc_attest_bad == 2 and mod.RECORD.read_text() == before,
                  "--attest with a bad source stamps nothing, not even the reviewer")
            with redirect_stdout(io.StringIO()):
                rc_attest_ok = main(["--attest", "R1", "--from", india, "--at", "2026-09-04"])
            stamped = json.loads(mod.RECORD.read_text())
            check(rc_attest_ok == 0 and is_attested(stamped)
                  and stamped["identity_checked_by"] == "R1"
                  and stamped["downloaded_from"] == india,
                  "--attest --from --at records the reviewer and the source together")
            mod.RECORD.write_text(json.dumps(staged))
            with redirect_stdout(io.StringIO()):
                rc_attest_unsourced = main(["--attest", "R1"])
            check(rc_attest_unsourced == 1
                  and not is_attested(json.loads(mod.RECORD.read_text())),
                  "...and attesting without one stamps the reviewer but stays unusable (exit 1)")
        finally:
            mod.RECORD, mod.STORE = saved

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


USAGE = """usage: register_gsr700e.py <downloaded-file> [--from <URL> --at <DATE>]
       register_gsr700e.py --attest <reviewer-id> [--from <URL> --at <DATE>] [--replace]
       register_gsr700e.py --source --from <URL> --at <DATE> [--replace]
       register_gsr700e.py --test
<URL>: the https address you downloaded the file from, on one of
       """ + ", ".join(sorted(SOURCE_HOSTS)) + """
<DATE>: when you downloaded it, YYYY-MM-DD (or a full ISO timestamp)
--source records only the address and date; it leaves the checks as they are.
--replace overwrites a different source already on record (refused without it).
""" + EXIT_WORDING + """
Registering a file exits 0 once it is registered (which is not yet usable law), and
2, 3 or 4 when the file is refused as the wrong instrument, missing the clause, or
unreadable."""


def main(argv: list[str]) -> int:
    if argv[:1] == ["--test"]:
        return _test()
    parsed = split_source_flags(argv)
    if parsed is None:
        print("--from and --at go together, once each\n" + USAGE)
        return 2
    rest, src_url, src_at = parsed
    replace = "--replace" in rest
    rest = [a for a in rest if a != "--replace"]
    if replace and rest[:1] not in (["--source"], ["--attest"]):
        print("--replace applies only to --source or --attest\n" + USAGE)
        return 2
    if rest[:1] == ["--source"]:
        if len(rest) != 1 or src_url is None:
            print(USAGE)
            return 2
        return cli_exit(record_source(src_url, src_at, replace=replace))
    if rest[:1] == ["--attest"]:
        if len(rest) != 2:
            print(USAGE)
            return 2
        out = attest(rest[1], src_url, src_at, replace=replace)
        # ATTEST_REFUSED is this script's own refusal (an address for a reviewer
        # id, or a stored text that changed); it writes nothing, so it exits 2.
        return 2 if out == ATTEST_REFUSED else cli_exit(out)
    if len(rest) != 1 or rest[0].startswith("--"):
        print(__doc__)
        print(USAGE)
        return 2
    out = register(Path(rest[0]), src_url, src_at)
    return 2 if out == SOURCE_REFUSED else EXIT.get(out, 1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
