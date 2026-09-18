#!/usr/bin/env python3
"""Register the Companies (Appointment and Remuneration of Managerial Personnel)
Rules, 2014 -- the instrument s.203's prescribed KMP class rests on.

Sibling of register_gsr700e.py and register_gsr880e.py, with one difference that
changes what registration MEANS here.

## Holding this instrument is not enough to serve s.203, and the record says so

700(E) and 880(E) are single amending notifications: acquire one, verify its
clause, serve its figure. This is the PRINCIPAL rule set, G.S.R. 249(E) of
31-03-2014, and India Code's own index lists at least five later amendments to it:

    2014-06-09 · 2016-03-30 · 2018-09-12 · 2020-01-06 · 2023-01-19 (G.S.R. 41(E))

Rule 8 as enacted in 2014 says "every listed company and every other public
company having a paid-up share capital of ten crore rupees or more". Whether that
is still the operative text after five amendments is exactly the question this
system exists to refuse to guess at -- and it is the same shape as the failure
that put a superseded Rs 4 crore in front of users for nine months.

So this module registers the principal rules as HELD, and records the amendment
chain as KNOWN AND UNACQUIRED. `prescribed_thresholds` keeps refusing s.203 until
the chain is resolved. Acquiring the first link of a chain and serving it as
current is the bug, not the fix.

## What attestation means here

`--attest` records that a person checked this is G.S.R. 249(E) and that the Rule 8
text is verbatim. It does NOT make s.203 servable, and the script says so on
completion. That takes resolving the chain, which is a separate act.
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

STORE = Path("corpus/rules/kmp_rules_2014.txt")
RECORD = Path("corpus/sources/kmp_rules_registration.json")

SOURCE_URL = ("https://indiacode.gov.in/server/api/core/bitstreams/"
              "835c8cda-3dae-490a-836f-1e0171af2bd6/content")
INDIA_CODE_HANDLE = "https://indiacode.gov.in/handle/123456789/508693"

# Later amendments India Code lists against this rule set. Recorded so the gap is
# a named list rather than a vague doubt. Dates are India Code's dc.date.issued.
# The chain, now ACQUIRED and traced. `touches` records which rule each amendment
# actually operates on -- read from the instrument, not inferred from its title.
#
# The result is worth stating plainly, because it was not the expected one:
# **Rule 8 has never been amended.** Both instruments that mention it operate on
# Rule 8A, a different rule inserted after it. So the principal Rule 8 text --
# "ten crore rupees or more ... whole-time key managerial personnel" -- stands as
# enacted in 2014.
#
# But s.203's prescribed class is not Rule 8 alone. A company secretary is key
# managerial personnel (s.2(51)), so Rule 8A is part of the same class, and its
# text HAS moved: inserted 2014 at five crore for companies not covered by rule 8,
# substituted 2020 to "every private company which has a paid up share capital of
# ten crore rupees or more". The 2020 instrument also carries its own commencement
# rule -- applicable for financial years commencing on or after 1 April 2020 --
# which is a date condition, not a publication date, and must not be collapsed.
CHAIN = (
    ("2014-06-09", "G.S.R. 390(E)", "123456789/508688",
     "corpus/sources/kmp_amend_2014-06-09.pdf", "8A",
     "inserted rule 8A after rule 8: a company not covered by rule 8 with paid-up "
     "capital of five crore rupees or more shall have a whole-time company secretary"),
    ("2016-03-30", "Amendment Rules 2016", "123456789/508634",
     "corpus/sources/kmp_amend_2016-03-30.pdf", None,
     "does not operate on rule 8 or rule 8A"),
    ("2018-09-12", "Amendment Rules 2018", "123456789/508752",
     "corpus/sources/kmp_amend_2018-09-12.pdf", None,
     "does not operate on rule 8 or rule 8A"),
    ("2020-01-06", "G.S.R. 13(E)", "123456789/508811",
     "corpus/sources/kmp_amend_2020-01-06.pdf", "8A",
     "substituted rule 8A: every private company with paid-up capital of ten crore "
     "rupees or more shall have a whole-time company secretary. Applicable for "
     "financial years commencing on or after 1 April 2020"),
    ("2023-01-19", "Amendment Rules 2023", "123456789/508923",
     "corpus/sources/kmp_amend_2023-01-19.pdf", None,
     "does not operate on rule 8 or rule 8A"),
)

# Kept for the registration record's older shape.
KNOWN_AMENDMENTS = tuple((d, t, h) for d, t, h, _, _, _ in CHAIN)

PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
CORROBORATED = "CORROBORATED"

# Where this record may say its artifact came from: India Code, which is where
# SOURCE_URL points and what the acquisition used, or the Gazette that published the
# Rules. The date printed on the file is the floor for any download of it.
SOURCE_HOSTS = GAZETTE_OR_INDIA_CODE_HOSTS
PUBLISHED = date(2014, 3, 31)
# Rule 8, not "the operative clause": this record keeps its verbatim text under its own
# key, and a corroborating copy has to carry THAT.
SOURCE_POLICY = SourcePolicy(SOURCE_HOSTS, PUBLISHED,
                             clause_field="operative_clause_rule_8")

ATTESTATIONS = (
    "identity: this file is G.S.R. 249(E) of 31-03-2014, the PRINCIPAL Companies "
    "(Appointment and Remuneration of Managerial Personnel) Rules, 2014 -- not one "
    "of its amendment rules",
    "clause: the Rule 8 wording recorded here is verbatim from the file, with no "
    "repair, normalisation or reflow",
    "chain: the reviewer understands that attesting this does NOT make s.203 "
    "servable, because five later amendments to these Rules are unacquired",
)

VERIFIED_INSTRUMENT = "VERIFIED_INSTRUMENT"
WRONG_INSTRUMENT = "WRONG_INSTRUMENT"
CLAUSE_NOT_FOUND = "CLAUSE_NOT_FOUND"
UNREADABLE = "UNREADABLE"
EXIT = {VERIFIED_INSTRUMENT: 0, WRONG_INSTRUMENT: 2, CLAUSE_NOT_FOUND: 3, UNREADABLE: 4}

def _identity_form(text: str) -> str:
    """All whitespace removed, lowercased. For IDENTITY MATCHING ONLY.

    This PDF's text layer writes "Appointmen t and Remuneration" -- a space inside
    a word -- which is the third instance of this artifact we have hit, after
    G.S.R. 880(E)'s "s hall" and this file's own "tencrore". Government PDF text
    layers split words at arbitrary points, and an identity check that assumes
    otherwise refuses correct documents.

    Stripping whitespace to SEARCH is not repair: the stored artifact and the
    captured clause both stay exactly as extracted. Only the question "is this
    the right instrument" is asked of a normalised copy.
    """
    return re.sub(r"\s+", "", text).lower()


# Identity markers, matched against the whitespace-stripped form above.
_ID_GSR = "gsr249(e)"
_ID_TITLE = "appointmentandremunerationofmanagerialpersonnel"
_ID_YEAR = "2014"

# Rule 8. \s* rather than \s+ between words because this PDF's text layer writes
# "tencrore" -- the same class of artifact as G.S.R. 880(E)'s "s hall". Matching
# the layer as it is, rather than repairing it, is the discipline.
# `.` rather than `[^.]` because the rule's own title ends in a period --
# "8. Appointment of Key Managerial Personnel. - Every listed company..." -- so a
# no-period class stops before the operative words it is meant to capture.
_CLAUSE = re.compile(
    r"(8\.\s*Appointment\s+of\s+Key\s+Managerial\s+Personnel\..{0,400}?"
    r"ten\s*crore\s*rupees.{0,160}?whole[-\s]*time\s+key\s+managerial\s+personnel\.)",
    re.I | re.S)

# An amendment must never be registered in the principal rules' place.
_AMENDMENT = re.compile(r"amendment\s+rules", re.I)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:4] == b"%PDF":
        try:
            from scripts.acquire_rules import extract_text
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
    if not text.strip():
        return UNREADABLE, "no text could be extracted, so no identity claim can be checked", ""

    ident = _identity_form(text)
    missing = []
    if _ID_GSR not in ident.replace(".", ""):
        missing.append("the notification number G.S.R. 249(E)")
    if _ID_TITLE not in ident:
        missing.append("the title 'Appointment and Remuneration of Managerial Personnel'")
    if _ID_YEAR not in ident:
        missing.append("the year 2014")
    if missing:
        return WRONG_INSTRUMENT, "does not identify itself by " + ", ".join(missing), ""

    # If it calls itself amendment rules AND lacks the principal Rule 8, it is a
    # later amendment being offered in the principal's place.
    m = _CLAUSE.search(text)
    if m is None:
        if _AMENDMENT.search(text):
            return (WRONG_INSTRUMENT,
                    "this looks like an AMENDMENT to the Rules, not the principal "
                    "Rules -- Rule 8's full text is absent", "")
        return (CLAUSE_NOT_FOUND,
                "identifies as G.S.R. 249(E) but Rule 8's operative wording was not "
                "found; the extraction may be partial, or this is a different printing", "")
    clause = re.sub(r"\s+", " ", m.group(1)).strip()
    return VERIFIED_INSTRUMENT, "identifies as G.S.R. 249(E) of 2014 and carries Rule 8", clause


def register(src: Path) -> str:
    if not src.is_file():
        print(f"no such file: {src}\n\nclassification : {UNREADABLE}")
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

    print(f"\nRule 8, verbatim:\n  {clause}\n")
    held = repo_relative(src)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(text, encoding="utf-8")
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "instrument_id": "GSR_249E_MANAGERIAL_PERSONNEL_RULES_2014",
        "title": "G.S.R. 249(E) — Companies (Appointment and Remuneration of "
                 "Managerial Personnel) Rules, 2014, dated 31-03-2014 (PRINCIPAL)",
        "source_url": SOURCE_URL,
        "india_code_handle": INDIA_CODE_HANDLE,
        "acquisition_method": "india_code_dspace_api",
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifact_sha256": digest,
        # Which file this record holds, so the guard can re-read it later. A record
        # that names no file cannot be checked, and is refused rather than trusted.
        "local_artifact": held,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(STORE.read_bytes()).hexdigest(),
        "operative_clause_rule_8": clause,
        "classification": outcome,
        "is_principal": True,
        # traced: every amendment is held and its effect on rules 8/8A is read.
        # resolved: a person has confirmed the resulting operative text. Different
        # things, and collapsing them is how a chain "resolves" without a reader.
        "chain_traced": True,
        "chain_resolved": False,
        "amendment_chain": [
            {"issued": d, "instrument": t, "handle": h, "artifact": a,
             "operates_on_rule": r, "effect": e,
             "artifact_sha256": ("sha256:" + hashlib.sha256(Path(a).read_bytes()).hexdigest()
                                 if Path(a).is_file() else None)}
            for d, t, h, a, r, e in CHAIN],
        "rule_8_amended": False,
        "rule_8a_current_source": "G.S.R. 13(E) of 06-01-2020",
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
    print(f"\nThe amendment chain is HELD and TRACED ({len(CHAIN)} instruments):")
    for d, t, _, _, r, e in CHAIN:
        print(f"  {d}  {t:22} {'rule ' + r if r else 'not rules 8/8A'}")
    print("\n  Rule 8 has NEVER been amended — both instruments that mention it")
    print("  operate on rule 8A. So the principal Rule 8 text stands as enacted.")
    print("  Rule 8A HAS moved: inserted 2014 at five crore, substituted 2020 to")
    print("  ten crore for private companies, for FYs from 1 April 2020.")
    print("\ns.203 still REFUSES. Traced is not resolved: a person must confirm the")
    print("resulting operative text, and that rule 8A belongs to the s.203 class")
    print("because a company secretary is key managerial personnel (s.2(51)).")
    print("\n  python3 scripts/register_kmp_rules.py --attest <reviewer-id>")
    return outcome


def attest(reviewer_id: str, downloaded_from: str | None = None,
           downloaded_at: str | None = None, *, replace: bool = False) -> str:
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return NO_RECORD
    # The source goes in FIRST, and a bad one refuses before anything is stamped.
    # Taking --from/--at and then dropping them would record an attestation while
    # silently discarding the provenance the operator supplied: the worst of both.
    if downloaded_from is not None or downloaded_at is not None:
        outcome, written, message = SOURCE_POLICY.record_source(
            rec, downloaded_from, downloaded_at, replace=replace)
        if outcome in (SOURCE_REFUSED, SOURCE_CONFLICT):
            print(message)
            return outcome
        rec = written if written is not None else rec
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = dict(rec)
    rec.update({"identity_checked_by": reviewer_id, "identity_checked_at": now,
                "verbatim_clause_checked_by": reviewer_id,
                "verbatim_clause_checked_at": now, "status": CORROBORATED})
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {now}; status {CORROBORATED}")
    gaps = attestation_gaps(rec)
    if gaps:
        print("NOT usable yet: " + "; ".join(gaps))
        print("Where the file was downloaded from is recorded separately:")
        print("  python3 scripts/register_kmp_rules.py --source --from <URL> --at <DATE>")
    print("\nNOTE: s.203 remains REFUSED whatever this record says. This attests the")
    print("principal Rules only; the chain is traced but NOT resolved, and resolving it")
    print("-- a person confirming the operative text of rules 8 and 8A -- is a separate act.")
    return CORROBORATED if not gaps else PENDING_HUMAN_REVIEW


def registration() -> dict | None:
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def attestation_gaps(rec: dict | None) -> list[str]:
    """Everything that keeps this record from being usable law. Empty means attested.

    NOTE: attested is not servable for this instrument -- see is_servable().
    """
    return SOURCE_POLICY.attestation_gaps(rec)


def is_attested(rec: dict | None) -> bool:
    """Classified VERIFIED_INSTRUMENT, both human checks recorded, the status says so,
    and the file's source is either recorded or corroborated from a Gazette or India
    Code host. NOTE: attested != servable for this instrument."""
    return not attestation_gaps(rec)


def is_servable(rec: dict | None) -> bool:
    """Attested AND the amendment chain resolved. Today this is always False."""
    return is_attested(rec) and bool(rec and rec.get("chain_resolved"))


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


# The stubs name a file this repository really holds, with its real digest: the
# guard re-reads the artifact now, so a stub carrying an invented hash would be
# a record of a file that does not exist -- which is what it must refuse.
_STUB_ARTIFACT = "corpus/sources/kmp_rules_2014.pdf"
_STUB_ARTIFACT_SHA = file_digest(ROOT / _STUB_ARTIFACT) or "sha256:" + "00" * 32


# ── test support ─────────────────────────────────────────────────────────────
def attested_stub(reviewer: str = "TEST") -> dict:
    """Acquired, both checks done, and a download source recorded. The address is a
    test value on an official host, not a real India Code file."""
    return {"artifact_sha256": _STUB_ARTIFACT_SHA,
            "local_artifact": _STUB_ARTIFACT,
            "classification": VERIFIED_INSTRUMENT,
            "operative_clause_rule_8": (
                "8. Appointment of Key Managerial Personnel. - Every listed company and "
                "every other public company having a paid-up share capital of tencrore "
                "rupees or more shall have whole-time key managerial personnel."),
            "downloaded_from": "https://indiacode.gov.in/test-stub.pdf",
            "downloaded_at": "2026-09-11",
            "identity_checked_by": reviewer, "identity_checked_at": "2026-01-01T00:00:00Z",
            "verbatim_clause_checked_by": reviewer,
            "verbatim_clause_checked_at": "2026-01-01T00:00:00Z",
            "status": CORROBORATED, "chain_resolved": False}


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

    print("register_kmp_rules")
    good = ("MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 31 st March, 2014 "
            "G.S.R 249(E).- In exercise of the powers conferred under sub-section (4) of "
            "section 196, the Central Government makes the Companies (Appointment and "
            "Remuneration of Managerial Personnel) Rules, 2014. "
            "8. Appointment of Key Managerial Personnel. - Every listed company and every "
            "other public company having a paid-up share capital of tencrore rupees or "
            "more shall have whole-time key managerial personnel.")
    outcome, reason, clause = classify(good)
    check(outcome == VERIFIED_INSTRUMENT, f"the principal Rules verify ({outcome})")
    check("whole-time key managerial personnel" in clause,
          "...and Rule 8 is captured verbatim")
    check("tencrore" in clause,
          "...including the text layer's 'tencrore', unrepaired")

    amend = good.replace("G.S.R 249(E)", "G.S.R 249(E) Amendment Rules") \
                .replace("8. Appointment of Key Managerial Personnel. - Every listed company "
                         "and every other public company having a paid-up share capital of "
                         "tencrore rupees or more shall have whole-time key managerial "
                         "personnel.", "In rule 8, for the words ... substitute ...")
    o2, r2, _ = classify(amend)
    check(o2 == WRONG_INSTRUMENT, f"an amendment is not accepted as the principal Rules ({o2})")
    check("AMENDMENT" in r2, "...and the reason says which it looks like")

    o3, _, _ = classify(good.replace("Managerial Personnel) Rules", "Board Powers) Rules")
                            .replace("Appointment and Remuneration of Managerial Personnel",
                                     "Meetings of Board"))
    check(o3 == WRONG_INSTRUMENT, f"a different rule set is refused ({o3})")
    check(classify("")[0] == UNREADABLE, "an unreadable file is UNREADABLE")

    stub_attested = attested_stub()
    check(is_attested(stub_attested), "an attested record is attested")
    check(not is_servable(stub_attested),
          "...but NOT servable while the amendment chain is unresolved")
    check(is_servable(dict(stub_attested, chain_resolved=True)),
          "...and servable only once the chain is resolved")
    check(len(KNOWN_AMENDMENTS) == 5, "the five known amendments are recorded by date")

    # ── P-2: the A-001 guard. Two human checks do not say where the file came from ──
    _SOURCE_KEYS = ("downloaded_from", "downloaded_at", "corroborating_copy")
    unsourced = {k: v for k, v in attested_stub().items() if k not in _SOURCE_KEYS}
    check(not is_attested(unsourced) and not is_servable(dict(unsourced, chain_resolved=True)),
          "both human checks with no recorded source and no corroboration is NOT attested")
    gaps = attestation_gaps(unsourced)
    check(any(g.startswith("source:") for g in gaps)
          and not any("checked_by" in g for g in gaps),
          f"...and the gap is named as the source, not as a missing reviewer ({gaps})")
    india = ("https://indiacode.gov.in/server/api/core/bitstreams/"
             "835c8cda-3dae-490a-836f-1e0171af2bd6/content")
    check(is_attested(unsourced | {"downloaded_from": india, "downloaded_at": "2026-09-11"}),
          "an India Code download address with its date makes it attested")
    for label, extra in (
            ("a commentary site", {"downloaded_from": "https://taxguru.in/kmp.pdf",
                                   "downloaded_at": "2026-09-11"}),
            ("the ministry's own site", {"downloaded_from": "https://www.mca.gov.in/x.pdf",
                                         "downloaded_at": "2026-09-11"}),
            ("an address with no date", {"downloaded_from": india}),
            ("an address carrying a space", {"downloaded_from": india + " ",
                                             "downloaded_at": "2026-09-11"}),
            ("a download before the Rules were made",
             {"downloaded_from": india, "downloaded_at": "2014-03-30"})):
        check(not is_attested(unsourced | extra), f"{label} is not a recorded source")
    copy_ok = {"url": "https://egazette.gov.in/WriteReadData/2014/1.pdf",
               "retrieved_at": "2026-09-17T00:00:00Z", "sha256": "sha256:" + "cd" * 32,
               "match": "text-identical",
               "matched_clause": unsourced["operative_clause_rule_8"],
               "recorded_by": "automated corroboration, not a human check"}
    check(is_attested(unsourced | {"corroborating_copy": copy_ok}),
          "a Gazette copy carrying Rule 8 verbatim stands in for the unrecorded source")
    check(not is_attested(unsourced | {"corroborating_copy": copy_ok | {
              "matched_clause": "Every listed company shall have somebody or other."}}),
          "...and a copy whose Rule 8 differs does not")
    for cls in (WRONG_INSTRUMENT, CLAUSE_NOT_FOUND, None):
        check(not is_attested(attested_stub() | {"classification": cls}),
              f"a record classified {cls} is not attested, whatever the checks say")

    # The record on disk, asserted against whatever state it is in.
    live = registration()
    if live is not None:
        live_gaps = attestation_gaps(live)
        check(is_attested(live) == (not live_gaps),
              f"the live record's state is what its gaps say ({live_gaps})")
        check(not is_servable(live),
              "...and it is not servable: the chain is traced, not resolved")

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
                               "--at", "2026-09-11"])
            check(rc_bad == 2 and mod.RECORD.read_text() == before,
                  "--source refuses a commentary site and writes nothing")
            with redirect_stdout(io.StringIO()):
                rc_ok = main(["--source", "--from", india, "--at", "2026-09-11"])
            after = json.loads(mod.RECORD.read_text())
            check(rc_ok == 0 and after["downloaded_from"] == india
                  and all(after[k] == unsourced[k] for k in unsourced),
                  "--source records the address and date and changes nothing else")
            mod.RECORD.unlink()
            with redirect_stdout(io.StringIO()):
                rc_none = main(["--source", "--from", india, "--at", "2026-09-11"])
            check(rc_none == 2 and not mod.RECORD.exists(),
                  "with no registration to act on it exits 2 and writes nothing")

            # ── fix round 1: --attest must not stamp the checks and drop the source ──
            mod.RECORD.write_text(json.dumps(
                {k: v for k, v in unsourced.items()
                 if k not in ("identity_checked_by", "identity_checked_at",
                              "verbatim_clause_checked_by", "verbatim_clause_checked_at")}
                | {"status": PENDING_HUMAN_REVIEW}))
            before = mod.RECORD.read_text()
            with redirect_stdout(io.StringIO()):
                rc_att = main(["--attest", "R1", "--from", india, "--at", "2026-09-11"])
            stamped = json.loads(mod.RECORD.read_text())
            check(rc_att == 0 and stamped["downloaded_from"] == india
                  and stamped["identity_checked_by"] == "R1" and is_attested(stamped),
                  "--attest --from --at records the reviewer AND the source together")
            mod.RECORD.write_text(before)
            with redirect_stdout(io.StringIO()):
                rc_att_bad = main(["--attest", "R1", "--from", "https://taxguru.in/x.pdf",
                                   "--at", "2026-09-11"])
            check(rc_att_bad == 2 and mod.RECORD.read_text() == before,
                  "...and a bad source stamps nothing, not even the reviewer")
            mod.RECORD.write_text(before)
            with redirect_stdout(io.StringIO()):
                rc_att_bare = main(["--attest", "R1"])
            check(rc_att_bare == 1
                  and json.loads(mod.RECORD.read_text())["identity_checked_by"] == "R1"
                  and not is_attested(json.loads(mod.RECORD.read_text())),
                  "...while attesting with no source stamps the checks and says it is "
                  "not usable (exit 1)")
        finally:
            mod.RECORD = saved

    # ── fix round 1: the CLI's own contract ──────────────────────────────────
    check(main([]) == 2 and main(["--replace"]) == 2,
          "no arguments, or --replace alone, is refused with 2 -- nothing is written")
    check(main(["--replace", "nonexistent-file.pdf"]) == 2,
          "--replace applies only to --source or --attest; it is never ignored")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


USAGE = """usage: register_kmp_rules.py <downloaded-file>
       register_kmp_rules.py --attest <reviewer-id> [--from <URL> --at <DATE>] [--replace]
       register_kmp_rules.py --source --from <URL> --at <DATE> [--replace]
       register_kmp_rules.py --test
<URL>: the https address the file was downloaded from, on one of
       """ + ", ".join(sorted(SOURCE_HOSTS)) + """
<DATE>: when it was downloaded, YYYY-MM-DD (or a full ISO timestamp)
""" + EXIT_WORDING


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
        return cli_exit(attest(rest[1], src_url, src_at, replace=replace))
    if len(rest) != 1 or rest[0].startswith("--"):
        print(__doc__)
        print(USAGE)
        return 2
    return EXIT.get(register(Path(rest[0])), 1)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
