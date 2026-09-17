#!/usr/bin/env python3
"""Register the Prospectus and Allotment Rules 2014 -- the rule that bounds paid-up capital.

`checker/mca_snapshot.py` reports every master-data field as blind by some width,
sourced from the Act. Two fields have no width at all:

    paid_up_capital   s.39(4) requires the return of allotment "in such manner as
                      may be prescribed" and states NO period. The period is in
                      rule 12 of these Rules, which we do not hold.
    din_status        a creature of the Directors Rules -- a separate acquisition.

So `assess("paid_up_capital")` returns UNBOUNDED_BLIND, and `capital_headroom`
refuses to return AGREES: headroom computed against an unbounded floor is not
headroom. That refusal is correct and it is also the single most annoying thing
about the strip, because it is the one a buyer notices.

This file is how it stops. Acquire the Rules, attest them, and the window becomes
real -- with its width read out of the artifact, not out of my memory.

## Why this rule is NOT in staleness.DEPENDENCIES

That inventory maps instruments to the *obligations* whose answer needs them. Rule
12 governs no obligation in the register. It bounds how stale a *fact* may be. Two
different kinds of dependency, and collapsing them would put a row in the
obligation inventory that governs nothing -- so `mca_snapshot` reads this record
directly instead.

## What the thirty days in mca_snapshot means before attestation

Nothing. There is no thirty-day constant anywhere in this file's output. The width
is parsed out of the clause the artifact actually contains (`_DAYS`), so if the
downloaded Rules say something else, that is what gets recorded. A number I typed
in from memory would be exactly the unsourced claim the whole project refuses.

Usage:
    python3 scripts/register_pas_rules.py <downloaded.pdf>
    python3 scripts/register_pas_rules.py --attest <your-reviewer-id>
    python3 scripts/register_pas_rules.py --test
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
    SOURCE_REFUSED, SourcePolicy, cli_exit, split_source_flags)

STORE = Path("corpus/rules/pas_rules_2014.txt")
RECORD = Path("corpus/sources/pas_rules_registration.json")

# Not looked up from a primary host, and guessing a handle would be a fabricated
# citation. The person who downloads the file records where they got it.
SOURCE_URL = "https://www.mca.gov.in/content/mca/global/en/acts-rules/ebooks/rules.html"

PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

# Where this record may say its artifact came from: India Code, which is where the
# record's own source_url points, or the Gazette. The Rules' own commencement date
# (01-04-2014, read from the artifact) is the floor for any download of them; their
# notification date is not stated on the file, so the weaker floor is the honest one.
SOURCE_HOSTS = GAZETTE_OR_INDIA_CODE_HOSTS
PUBLISHED = date(2014, 4, 1)
SOURCE_POLICY = SourcePolicy(SOURCE_HOSTS, PUBLISHED)

ATTESTATIONS = (
    "identity: this file is the principal Companies (Prospectus and Allotment of "
    "Securities) Rules, 2014, and not one of the Amendment Rules that share the "
    "title",
    "clause: rule 12's period and form are recorded verbatim from the file, with "
    "no repair, normalisation or reflow -- and the period recorded matches the "
    "words on the page",
    "currency: no later amendment substituting rule 12 was found, or the ones "
    "found are named in the record",
)

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"
WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
CLAUSE_NOT_FOUND = "CLAUSE_NOT_FOUND"
UNREADABLE = "UNREADABLE"
EXIT = {VERIFIED_INSTRUMENT: 0, WRONG_INSTRUMENT: 2, CLAUSE_NOT_FOUND: 3, UNREADABLE: 4}

_TITLE = re.compile(r"prospectus\s+and\s+allotment\s+of\s+securities", re.I)
_YEAR = re.compile(r"\b2014\b")
_AMENDMENT = re.compile(r"prospectus\s+and\s+allotment\s+of\s+securities\s*\)?\s*"
                        r"(second\s+|third\s+|fourth\s+)?amendment\s+rules", re.I)
_PRINCIPAL = re.compile(r"short\s+title\s+and\s+commencement", re.I)

# Rule 12. Matched on structure, not on a period I expect -- the period is read out
# of whatever the clause says.
_CLAUSE = re.compile(
    r"((?:whenever|where)\s+a\s+company[^.]{0,240}?allotment[^.]{0,320}?"
    r"(thirty|sixty|fifteen|forty-five|ninety)\s+days[^.]{0,320}?"
    r"PAS\s*[-.–]?\s*3[^.]{0,240}\.)", re.I | re.S)

_DAYS = {"fifteen": 15, "thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90}


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:4] == b"%PDF":
        try:
            from scripts.acquire_rules import extract_text   # type: ignore
            return extract_text(path)
        except Exception:                                     # noqa: BLE001
            return ""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def classify(text: str) -> tuple[str, str, str, int | None]:
    """(outcome, reason, operative_clause_verbatim, window_days)."""
    if not text.strip():
        return UNREADABLE, ("no text could be extracted, so no identity claim can be "
                            "checked"), "", None

    if not _TITLE.search(text):
        return WRONG_INSTRUMENT, ("does not identify itself by the title 'Prospectus "
                                  "and Allotment of Securities'"), "", None
    if not _YEAR.search(text):
        return WRONG_INSTRUMENT, "does not carry the year 2014", "", None

    # The trap the board-rules handoff already documented: the amendments share the
    # title and differ by one word. An amendment is a list of substitutions; it does
    # not carry rule 12 whole, so registering one would record a partial rule as the
    # principal one.
    if _AMENDMENT.search(text) and not _PRINCIPAL.search(text):
        return WRONG_INSTRUMENT, ("this is an Amendment to the Rules, not the "
                                  "principal Rules -- it amends rule text rather "
                                  "than containing it"), "", None

    m = _CLAUSE.search(text)
    if not m:
        return (CLAUSE_NOT_FOUND,
                "identifies as the Prospectus and Allotment Rules but rule 12's "
                "return-of-allotment clause naming a period and Form PAS-3 was not "
                "found. The extraction may be partial, or rule 12 has been "
                "substituted by an amendment. Read the file; do not proceed on an "
                "assumed period.", "", None)

    clause = re.sub(r"\s+", " ", m.group(1)).strip()
    return VERIFIED_INSTRUMENT, ("identifies as the principal Rules and carries rule "
                                 "12's period and form"), clause, _DAYS[m.group(2).lower()]


def register(src: Path) -> str:
    if not src.is_file():
        print(f"no such file: {src}")
        print(f"\nclassification : {UNREADABLE}")
        return UNREADABLE

    text = read_text(src)
    outcome, reason, clause, days = classify(text)
    digest = "sha256:" + hashlib.sha256(src.read_bytes()).hexdigest()

    print(f"file           : {src}")
    print(f"sha256         : {digest}")
    print(f"classification : {outcome}")
    print(f"reason         : {reason}")

    if outcome != VERIFIED_INSTRUMENT:
        print("\nNOT registered. Nothing was written.")
        return outcome

    print(f"\nrule 12, verbatim:\n  {clause}\n")
    print(f"period read from the clause : {days} days")
    print("(read from the file, not assumed -- if that is not what the page says, "
          "do not attest)")

    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(text, encoding="utf-8")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "instrument_id": "PAS_RULES_2014",
        "title": "Companies (Prospectus and Allotment of Securities) Rules, 2014",
        "rule": "12",
        "source_url": SOURCE_URL,
        "downloaded_from": None,        # filled by --attest; only a person knows it
        "downloaded_at": None,
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acquisition_method": "human_browser",
        "artifact_sha256": digest,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(STORE.read_bytes()).hexdigest(),
        "operative_clause": clause,
        "window_days": days,
        "window_form": "PAS-3",
        "classification": outcome,
        "identity_checked_by": None,
        "identity_checked_at": None,
        "verbatim_clause_checked_by": None,
        "verbatim_clause_checked_at": None,
        "status": PENDING_HUMAN_REVIEW,
        "attests_to": ATTESTATIONS,
    }, indent=1) + "\n", encoding="utf-8")

    print(f"\nstored         : {STORE}")
    print(f"record         : {RECORD}")
    print(f"status         : {PENDING_HUMAN_REVIEW}")
    print("\nThe artifact is stored and hashed. It is NOT yet a bound.")
    print("Until a person attests, mca_snapshot keeps returning UNBOUNDED_BLIND for")
    print("paid-up capital and capital_headroom keeps refusing to say AGREES.")
    for a in ATTESTATIONS:
        print(f"  - {a}")
    print("\nWhen you have done all three:")
    print("  python3 scripts/register_pas_rules.py --attest <your-reviewer-id>")
    return outcome


def attest(reviewer_id: str) -> str:
    """Record that a person performed the checks. Where the file came from is recorded
    separately, with --source: a date with no address is not a provenance."""
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return NO_RECORD
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = dict(rec)
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
        print("Where the file was downloaded from is recorded separately:")
        print("  python3 scripts/register_pas_rules.py --source --from <URL> --at <DATE>")
        return PENDING_HUMAN_REVIEW
    print(f"paid-up capital is now bounded at {rec.get('window_days')} days "
          f"(Form {rec.get('window_form')}). Run the suite.")
    return CORROBORATED


def registration() -> dict | None:
    """The registration record, if one exists. Read by checker/mca_snapshot.py."""
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def attestation_gaps(rec: dict | None) -> list[str]:
    """Everything that keeps this record from bounding anything. Empty means attested.

    The shared provenance rule (classification, the two human checks, the status, and a
    recorded or corroborated source) plus this record's own: a bound with no period
    read out of the artifact is not a bound.
    """
    gaps = SOURCE_POLICY.attestation_gaps(rec)
    if isinstance(rec, dict) and rec and not isinstance(rec.get("window_days"), int):
        gaps.append(f"window_days is {rec.get('window_days')!r}, not a number of days")
    return gaps


def is_attested(rec: dict | None) -> bool:
    """Classified VERIFIED_INSTRUMENT, both human checks recorded, the status says so,
    a period read from the artifact, and a source either recorded or corroborated from
    a Gazette or India Code host."""
    return not attestation_gaps(rec)


def record_source(downloaded_from: str | None, downloaded_at: str | None, *,
                  replace: bool = False) -> str:
    """Record only where and when the file was downloaded. The human check fields and
    their timestamps are left exactly as they are."""
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


# ── test support ─────────────────────────────────────────────────────────────
from contextlib import contextmanager as _contextmanager


def attested_stub(days: int = 30, reviewer: str = "TEST") -> dict:
    return {"instrument_id": "PAS_RULES_2014", "rule": "12",
            "classification": VERIFIED_INSTRUMENT,
            "downloaded_from": "https://indiacode.gov.in/test-stub.pdf",
            "downloaded_at": "2026-09-13",
            "operative_clause": "Whenever a company having a share capital makes any "
                                "allotment of its securities, the company shall, "
                                "within thirty days thereafter, file with the "
                                "Registrar a return of allotment in Form PAS-3.",
            "window_days": days, "window_form": "PAS-3",
            "artifact_sha256": "sha256:" + "ab" * 32,
            "identity_checked_by": reviewer, "identity_checked_at": "2026-01-01T00:00:00Z",
            "verbatim_clause_checked_by": reviewer,
            "verbatim_clause_checked_at": "2026-01-01T00:00:00Z",
            "status": CORROBORATED}


def registered_unattested_stub() -> dict:
    rec = attested_stub()
    rec.update(identity_checked_by=None, identity_checked_at=None,
               verbatim_clause_checked_by=None, verbatim_clause_checked_at=None,
               status=PENDING_HUMAN_REVIEW)
    return rec


@_contextmanager
def stub_registration(rec):
    """Control acquisition state within a block. Test-only.

    sys.modules[__name__] rather than a fresh import: run as a script this module is
    __main__, and importing it by name would patch a SECOND copy while the caller
    kept using the first. That trap has been hit three times in this repository.
    """
    mod = sys.modules[__name__]
    original = mod.registration
    mod.registration = lambda: rec          # type: ignore[assignment]
    try:
        yield
    finally:
        mod.registration = original         # type: ignore[assignment]


_PRINCIPAL_SAMPLE = (
    "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 31st March, 2014\n"
    "G.S.R. 251(E). In exercise of the powers conferred ... the Central Government "
    "hereby makes the following rules, namely:-\n"
    "1. Short title and commencement.- (1) These rules may be called the Companies "
    "(Prospectus and Allotment of Securities) Rules, 2014.\n"
    "12. Return of allotment.- (1) Whenever a company having a share capital makes "
    "any allotment of its securities, the company shall, within thirty days "
    "thereafter, file with the Registrar a return of allotment in Form PAS-3, along "
    "with the fee as specified in the Companies (Registration Offices and Fees) "
    "Rules, 2014.\n")


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [PASS] {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("register_pas_rules")

    outcome, reason, clause, days = classify(_PRINCIPAL_SAMPLE)
    check(outcome == VERIFIED_INSTRUMENT, f"the principal Rules are recognised ({outcome})")
    check(days == 30, f"the period is READ from the clause, not assumed ({days})")
    check("PAS-3" in clause and "thirty days" in clause,
          "...and the clause is captured verbatim, form and all")

    # The period comes from the page. Change the page, change the bound.
    _, _, _, d60 = classify(_PRINCIPAL_SAMPLE.replace("thirty days", "sixty days"))
    check(d60 == 60,
          "a file saying sixty days registers sixty -- no constant of mine overrides "
          "the artifact")

    amend = ("Companies (Prospectus and Allotment of Securities) Second Amendment "
             "Rules, 2018 ... further to amend the Companies (Prospectus and "
             "Allotment of Securities) Rules, 2014 ... in rule 12, for sub-rule (1), "
             "the following shall be substituted, namely 2014")
    check(classify(amend)[0] == WRONG_INSTRUMENT,
          "an Amendment sharing the title is refused -- it amends rule text rather "
          "than containing it")
    check(classify("Companies (Acceptance of Deposits) Rules, 2014")[0] == WRONG_INSTRUMENT,
          "a different set of 2014 Rules is refused on title")
    check(classify(_PRINCIPAL_SAMPLE.replace(
              "within thirty days thereafter, file with the Registrar a return of "
              "allotment in Form PAS-3", "file a return of allotment"))[0]
          == CLAUSE_NOT_FOUND,
          "the principal Rules without a readable rule 12 are CLAUSE_NOT_FOUND, not "
          "accepted with an assumed period")
    check(classify("")[0] == UNREADABLE, "an empty extraction is UNREADABLE")

    # ── attestation is a human act ───────────────────────────────────────────
    check(not is_attested(None), "no record is not attested")
    check(not is_attested(registered_unattested_stub()),
          "a stored, hashed, classified artifact is still not attested")
    check(is_attested(attested_stub()), "both checks recorded and CORROBORATED is")
    bad = attested_stub(); bad["window_days"] = None
    check(not is_attested(bad),
          "...and an attestation with no period read is refused -- attesting to a "
          "bound requires there to be a bound")

    check(registration() is None or RECORD.is_file(),
          "registration() reads disk and does not invent a record")

    # ── P-2: the A-001 guard. Attesting a rule whose source is unrecorded would
    # bound paid-up capital on a file nothing says the provenance of. ───────────
    _SOURCE_KEYS = ("downloaded_from", "downloaded_at", "corroborating_copy")
    unsourced = {k: v for k, v in attested_stub().items() if k not in _SOURCE_KEYS}
    check(not is_attested(unsourced),
          "both human checks with no recorded source and no corroboration is NOT attested")
    gaps = attestation_gaps(unsourced)
    check(any(g.startswith("source:") for g in gaps)
          and not any("checked_by" in g for g in gaps),
          f"...and the gap is named as the source, not as a missing reviewer ({gaps})")
    india = ("https://indiacode.gov.in/server/api/core/bitstreams/"
             "a4906475-d997-427d-a0e9-1bbc5078b69d/content")
    check(is_attested(unsourced | {"downloaded_from": india, "downloaded_at": "2026-09-13"}),
          "an India Code download address with its date makes it attested")
    for label, extra in (
            ("a prose description instead of an address",
             {"downloaded_from": "India Code DSpace REST (open API), item c1199089",
              "downloaded_at": "2026-09-13"}),
            ("a commentary site", {"downloaded_from": "https://taxguru.in/pas.pdf",
                                   "downloaded_at": "2026-09-13"}),
            ("an address with no date", {"downloaded_from": india}),
            ("an address carrying a space", {"downloaded_from": " " + india,
                                             "downloaded_at": "2026-09-13"})):
        check(not is_attested(unsourced | extra), f"{label} is not a recorded source")
    copy_ok = {"url": india, "retrieved_at": "2026-09-17T00:00:00Z",
               "sha256": unsourced["artifact_sha256"], "match": "identical",
               "recorded_by": "automated corroboration, not a human check"}
    check(is_attested(unsourced | {"corroborating_copy": copy_ok}),
          "a byte-identical copy from an official host stands in for the unrecorded source")
    check(not is_attested(unsourced | {"corroborating_copy": copy_ok | {
              "sha256": "sha256:" + "cd" * 32}}),
          "...and an 'identical' copy whose hash is not the artifact's does not")
    for cls in (WRONG_INSTRUMENT, CLAUSE_NOT_FOUND, None):
        check(not is_attested(attested_stub() | {"classification": cls}),
              f"a record classified {cls} is not attested, whatever the checks say")
    no_window = attested_stub(); no_window["window_days"] = None
    check(not is_attested(no_window),
          "and an attestation with no period read is still refused -- attesting to a "
          "bound requires there to be a bound")

    # The record on disk, asserted against whatever state it is in.
    live = registration()
    if live is not None:
        live_gaps = attestation_gaps(live)
        check(is_attested(live) == (not live_gaps),
              f"the live record's state is what its gaps say ({live_gaps})")

    # ── the CLI records a source, and refuses a bad one without writing ──────
    import io
    import tempfile
    from contextlib import redirect_stdout
    mod = sys.modules[__name__]
    saved = mod.RECORD
    with tempfile.TemporaryDirectory() as td:
        mod.RECORD = Path(td) / "rec.json"
        try:
            mod.RECORD.write_text(json.dumps(unsourced))
            before = mod.RECORD.read_text()
            with redirect_stdout(io.StringIO()):
                rc_bad = main(["--source", "--from", "https://taxguru.in/x.pdf",
                               "--at", "2026-09-13"])
            check(rc_bad == 2 and mod.RECORD.read_text() == before,
                  "--source refuses a commentary site and writes nothing")
            with redirect_stdout(io.StringIO()):
                rc_ok = main(["--source", "--from", india, "--at", "2026-09-13"])
            after = json.loads(mod.RECORD.read_text())
            check(rc_ok == 0 and after["downloaded_from"] == india
                  and all(after[k] == unsourced[k] for k in unsourced),
                  "--source records the address and date and changes nothing else")
            # The live record's own shape: a prose description already recorded is a
            # refusal, and replacing it is a deliberate act, not a silent one.
            mod.RECORD.write_text(json.dumps(
                unsourced | {"downloaded_from": "India Code DSpace REST (open API)",
                             "downloaded_at": "2026-09-13"}))
            before = mod.RECORD.read_text()
            out = io.StringIO()
            with redirect_stdout(out):
                rc_conflict = main(["--source", "--from", india, "--at", "2026-09-13"])
            check(rc_conflict == 2 and mod.RECORD.read_text() == before
                  and "--replace" in out.getvalue(),
                  "a description already on record is not silently replaced by an address")
            with redirect_stdout(io.StringIO()):
                rc_rep = main(["--source", "--replace", "--from", india, "--at", "2026-09-13"])
            check(rc_rep == 0
                  and json.loads(mod.RECORD.read_text())["downloaded_from"] == india,
                  "...and --replace is what records the address instead")
        finally:
            mod.RECORD = saved

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


USAGE = """usage: register_pas_rules.py <downloaded.pdf>
       register_pas_rules.py --attest <reviewer-id>
       register_pas_rules.py --source --from <URL> --at <DATE> [--replace]
       register_pas_rules.py --test
<URL>: the https address the file was downloaded from, on one of
       """ + ", ".join(sorted(SOURCE_HOSTS)) + """
<DATE>: when it was downloaded, YYYY-MM-DD (or a full ISO timestamp)
""" + EXIT_WORDING


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        print(USAGE)
        return 1
    if argv[:1] == ["--test"]:
        return _test()
    parsed = split_source_flags(argv)
    if parsed is None:
        print("--from and --at go together, once each\n" + USAGE)
        return 2
    rest, src_url, src_at = parsed
    replace = "--replace" in rest
    rest = [a for a in rest if a != "--replace"]
    if rest[:1] == ["--source"]:
        if len(rest) != 1 or src_url is None:
            print(USAGE)
            return 2
        return cli_exit(record_source(src_url, src_at, replace=replace))
    if rest[:1] == ["--attest"]:
        if len(rest) != 2:
            print(USAGE)
            return 2
        return cli_exit(attest(rest[1]))
    if len(rest) != 1 or rest[0].startswith("--"):
        print(USAGE)
        return 2
    return EXIT[register(Path(rest[0]))]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
