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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


def attest(reviewer_id: str) -> str:
    rec = registration()
    if rec is None:
        print("no registration on record — run register first")
        return "NO_RECORD"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec.update({"identity_checked_by": reviewer_id, "identity_checked_at": now,
                "verbatim_clause_checked_by": reviewer_id,
                "verbatim_clause_checked_at": now, "status": CORROBORATED})
    RECORD.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"attested by {reviewer_id} at {now}; status {CORROBORATED}")
    print("\nNOTE: s.203 remains REFUSED. This attests the principal Rules only;")
    print(f"{len(KNOWN_AMENDMENTS)} amendments are still unacquired and one of them")
    print("may have moved the Rule 8 threshold. Resolving the chain is a separate act.")
    return CORROBORATED


def registration() -> dict | None:
    if not RECORD.is_file():
        return None
    try:
        return json.loads(RECORD.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_attested(rec: dict | None) -> bool:
    """Both human checks recorded. NOTE: attested != servable for this instrument."""
    if not rec:
        return False
    return bool(rec.get("identity_checked_by") and rec.get("identity_checked_at")
                and rec.get("verbatim_clause_checked_by")
                and rec.get("verbatim_clause_checked_at")
                and rec.get("status") == CORROBORATED)


def is_servable(rec: dict | None) -> bool:
    """Attested AND the amendment chain resolved. Today this is always False."""
    return is_attested(rec) and bool(rec and rec.get("chain_resolved"))


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

    stub_attested = {"identity_checked_by": "R", "identity_checked_at": "t",
                     "verbatim_clause_checked_by": "R", "verbatim_clause_checked_at": "t",
                     "status": CORROBORATED, "chain_resolved": False}
    check(is_attested(stub_attested), "an attested record is attested")
    check(not is_servable(stub_attested),
          "...but NOT servable while the amendment chain is unresolved")
    check(is_servable(dict(stub_attested, chain_resolved=True)),
          "...and servable only once the chain is resolved")
    check(len(KNOWN_AMENDMENTS) == 5, "the five known amendments are recorded by date")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--test":
        raise SystemExit(_test())
    if args and args[0] == "--attest":
        if len(args) < 2:
            print("usage: register_kmp_rules.py --attest <reviewer-id>")
            raise SystemExit(2)
        raise SystemExit(0 if attest(args[1]) == CORROBORATED else 1)
    if not args:
        print(__doc__)
        print("usage: register_kmp_rules.py <downloaded-file>")
        raise SystemExit(2)
    raise SystemExit(EXIT.get(register(Path(args[0])), 1))
