"""
Register a downloaded subordinate-Rules PDF as a provenanced source.

Week 2.1 could not fetch the Meetings of Board Rules 2014: India Code's dynamic paths are down and
its upload host refuses connections, so the document's static address cannot be discovered. The
likely unblock is a human downloading it from eGazette or India Code once reachable. This script is
the other half of that handoff -- it verifies, hashes, stores and registers the file, so acquisition
does not depend on someone remembering the provenance steps at the moment they happen to have the
PDF.

It deliberately does NOT parse rule text. That is Week 2.2.

The check that matters is instrument identity. India Code publishes several near-identically-titled
instruments -- "The Companies (Meetings of Board and its Powers) Rules, 2014", the amendment
notifications that alter them, and consolidated as-amended reprints -- and confusing any of these
for the principal Rules would silently corrupt everything built on top. This script classifies the
file and refuses it rather than guessing, printing what it found for a human to confirm.

Outcomes are named, not merely encoded in an exit status:

    VERIFIED_PRINCIPAL     the document identifies itself as the principal 2014 Rules.
                           This means IDENTITY MATCHES. It is not human review, and it never sets
                           human_reviewed=True anywhere -- a human still has to read the file.
    REJECTED_AMENDMENT     an amending instrument. Detected from the title AND from body language,
                           because the short-title clause naming it an "Amendment Rules" often
                           falls past the pages we extract.
    UNCONFIRMED_DOCUMENT   identity not established: a consolidated/as-amended reprint, a missing
                           or unexpected gazette number, or an unrelated document.
    CORRUPT_OR_UNREADABLE  no text could be extracted, so no identity claim can be checked.

A rejected file is still evidence -- its hash and detected identity are printed so it can be
preserved deliberately -- but it is never copied into corpus/sources/. Only the principal Rules
belong there.

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

VERIFIED_PRINCIPAL = "VERIFIED_PRINCIPAL"
REJECTED_AMENDMENT = "REJECTED_AMENDMENT"
UNCONFIRMED_DOCUMENT = "UNCONFIRMED_DOCUMENT"
CORRUPT_OR_UNREADABLE = "CORRUPT_OR_UNREADABLE"

# Exit codes kept for shell callers, but they are now derived from the classification rather than
# being the outcome themselves. 5 ("principal title absent") is gone: it was one of several ways of
# failing to confirm identity and is now reported as UNCONFIRMED_DOCUMENT with a reason.
EXIT_CODES = {
    VERIFIED_PRINCIPAL: 0,
    CORRUPT_OR_UNREADABLE: 3,
    REJECTED_AMENDMENT: 4,
    UNCONFIRMED_DOCUMENT: 6,
}

# PDF extraction splits words at line-wrap points: the real gazette renders the title as
# "Meetings of Board an d its Powers". A regex demanding whole words therefore fails on the very
# document it exists to recognise, so every gap here tolerates a stray space. This is the known
# India Code artifact ("an d preserve", "sub -section"), not a typo in the source.
PRINCIPAL_TITLE = re.compile(
    r"C\s?o\s?m\s?p\s?a\s?n\s?i\s?e\s?s\s*\(\s*M\s?e\s?e\s?t\s?i\s?n\s?g\s?s\s+"
    r"o\s?f\s+B\s?o\s?a\s?r\s?d\s+a\s?n\s?d\s+i\s?t\s?s\s+P\s?o\s?w\s?e\s?r\s?s\s*\)"
    r"\s*R\s?u\s?l\s?e\s?s\s*,?\s*2\s?0\s?1\s?4", re.I)
PRINCIPAL_CLAUSE = re.compile(r"S\s?h\s?o\s?r\s?t\s+t\s?i\s?t\s?l\s?e\s+a\s?n\s?d\s+"
                              r"c\s?o\s?m\s?m\s?e\s?n\s?c\s?e\s?m\s?e\s?n\s?t", re.I)
AMENDMENT_TITLE = re.compile(r"Amendment\s+Rules", re.I)
NOTIFICATION = re.compile(r"G\.?S\.?R\.?\s*(\d{1,4})\s*\(\s*E\s*\)", re.I)
# Gazette notifications write the date both as "dated the 31st March, 2014" and, in the dateline,
# as "New Delhi, the 31st March, 2014". Accept either; the leading "dated" is optional.
DATED = re.compile(r"(?:dated\s+)?the\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4})", re.I)

# The title test alone is not enough. An amendment notification's operative sentence is "...makes
# the following rules further to amend the Companies (Meetings of Board and its Powers) Rules,
# 2014", which contains the PRINCIPAL title verbatim, while the clause that names it an "Amendment
# Rules" sits in the short-title paragraph that may fall past the pages we extract. Body language
# is therefore the more reliable signal, not a supplement to the title.
# A bare "in the said rules" is NOT amendment language and was removed after it produced a false
# rejection of the genuine principal Rules. Their definitions clause reads "...shall have the same
# meanings respectively assigned to them in the Act or in the said Rules", a cross-reference to the
# Definitions Rules. An amendment says it *amends*: it names itself an Amendment, says "further to
# amend", or carries an operative direction ("In the said rules, in rule 4, ... shall be
# substituted"). The operative form below requires that direction, not the bare phrase.
AMENDING_LANGUAGE = (
    ("further to amend", re.compile(r"further\s+to\s+amend", re.I)),
    ("operative amendment direction",
     re.compile(r"in\s+the\s+said\s+rules\s*,\s*(?:in\s+)?(?:rule|sub-?rule|the\s+Annexure|"
                r"for|after)\b", re.I)),
    ("shall be substituted", re.compile(r"shall\s+be\s+substituted", re.I)),
    ("shall be inserted", re.compile(r"shall\s+be\s+inserted", re.I)),
    ("shall be omitted", re.compile(r"shall\s+be\s+omitted", re.I)),
)

# A consolidated "as amended up to <date>" reprint is a DIFFERENT ARTIFACT from the principal
# notification as published: useful for reading the current rule, useless as the historical
# instrument, and the exact substitution already retracted once (docs/RETRACTIONS.md). Phrases are
# kept narrow on purpose -- a bare "consolidated" would fire on "consolidated financial statement",
# which is ordinary Board-powers subject matter.
CONSOLIDATION_MARKERS = (
    ("as amended up to", re.compile(r"as\s+amended\s+up\s*-?\s*to", re.I)),
    ("as amended by", re.compile(r"as\s+amended\s+by", re.I)),
    ("updated up to", re.compile(r"updated\s+up\s*-?\s*to", re.I)),
    ("incorporating amendments", re.compile(r"incorporat\w*\s+(?:all\s+)?(?:the\s+)?amendments?", re.I)),
    ("consolidated text", re.compile(r"consolidated\s+(?:version|text|copy)", re.I)),
)

# An UNVERIFIED third-party lead, mirroring PRINCIPAL_RULES_LEAD in checker/provenance.py. It is
# not a fact and must never be written into any record as one. Its only use here is as an
# expectation to CHECK the acquired document against and report a mismatch. Because the lead itself
# is unverified, a mismatch may mean the LEAD is wrong rather than the document -- which is why a
# mismatch stops for a human instead of rejecting outright.
# Held as a literal rather than imported so the script runs from any directory without PYTHONPATH;
# if provenance.py's lead ever changes, this must be changed with it.
LEAD_NOTIFICATION_NUMBER = "240"
LEAD_DATE_CLAIM = "31-03-2014"


def extract_text(pdf: Path) -> str:
    """Text of the PDF, by whichever route this machine actually has.

    checker/pdf_text.py is tried FIRST and is not optional. poppler is not installed here, and
    without a fallback this function returned "" for a perfectly readable official gazette -- the
    guard then reported CORRUPT_OR_UNREADABLE, which is a claim about the toolchain masquerading
    as a claim about the evidence. That is the most dangerous kind of wrong answer this repo can
    produce, so the dependency-free reader is the primary path and the external tools are extras.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from checker.pdf_text import extract_text as _pure
        text = _pure(pdf)
        if len(re.findall(r"[A-Za-z]{3,}", text)) >= 30:
            return text
    except Exception:
        pass
    for cmd in (["pdftotext", "-l", "3", str(pdf), "-"],
                ["mdls", "-name", "kMDItemTextContent", str(pdf)]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and len(r.stdout) > 200:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


def _matches(text: str, patterns: tuple) -> tuple[str, ...]:
    return tuple(label for label, rx in patterns if rx.search(text))


def inspect(text: str) -> dict:
    """What the document says about itself. Reports; never decides silently."""
    notification = NOTIFICATION.search(text)
    return {
        "principal_title_found": bool(PRINCIPAL_TITLE.search(text)),
        "amendment_title_found": bool(AMENDMENT_TITLE.search(text)),
        "amending_language": _matches(text, AMENDING_LANGUAGE),
        "consolidation_markers": _matches(text, CONSOLIDATION_MARKERS),
        "notification": (notification.group(0) if notification else None),
        "notification_number": (notification.group(1) if notification else None),
        "dated": (m.group(1) if (m := DATED.search(text)) else None),
        # None, not False, when there is nothing to compare: "did not match" and "could not check"
        # are different findings and collapsing them would hide the second.
        "matches_unverified_lead": (
            notification.group(1) == LEAD_NOTIFICATION_NUMBER if notification else None),
    }


def classify(found: dict) -> tuple[str, str]:
    """Classification plus the reason for it. Pure -- takes only what inspect() read."""
    # Consolidation is tested first because an as-amended reprint reproduces amending language in
    # its footnotes. Tested the other way round it would be reported as an amendment, which is the
    # wrong description of the artifact even though both outcomes refuse it.
    if found["consolidation_markers"]:
        return UNCONFIRMED_DOCUMENT, (
            "reads as a consolidated / as-amended text (" + ", ".join(found["consolidation_markers"])
            + ") -- a different artifact from the principal notification as published")
    if found["amendment_title_found"] or found["amending_language"]:
        signals = list(found["amending_language"])
        if found["amendment_title_found"]:
            signals.insert(0, "title says 'Amendment Rules'")
        return REJECTED_AMENDMENT, "amending instrument (" + ", ".join(signals) + ")"
    if not found["principal_title_found"]:
        return UNCONFIRMED_DOCUMENT, "the principal title was not found in the extracted pages"
    if found["notification_number"] is None:
        return UNCONFIRMED_DOCUMENT, (
            "no G.S.R. number in the extracted pages -- the notification cannot be identified")
    if not found["matches_unverified_lead"]:
        return UNCONFIRMED_DOCUMENT, (
            f"gazette number {found['notification']} does not match the unverified lead "
            f"G.S.R. {LEAD_NOTIFICATION_NUMBER}(E) / {LEAD_DATE_CLAIM}; since the lead is itself "
            f"unverified, either could be wrong")
    return VERIFIED_PRINCIPAL, "identifies itself as the principal 2014 Rules"


def classify_text(text: str) -> tuple[str, str, dict]:
    """Classify extracted text. Returns (classification, reason, what the document said)."""
    if not text.strip():
        # A scanned-image PDF extracts to nothing but form feeds. Nothing can be checked about it,
        # and a document whose identity cannot be checked must not enter the corpus.
        return CORRUPT_OR_UNREADABLE, "no text could be extracted", {}
    found = inspect(text)
    classification, reason = classify(found)
    return classification, reason, found


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance_block(digest: str, found: dict) -> str:
    """The SourceRecord to paste into checker/provenance.py. Reports only what was read."""
    return f'''
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
    notes="Notification {found.get('notification')}, dated {found.get('dated')}. "
          "Identity matched by scripts/acquire_rules.py; text not yet read by a human.",
)'''


def report(classification: str, reason: str, found: dict, digest: str, src: Path) -> None:
    print(f"\nclassification : {classification}")
    print(f"reason         : {reason}")
    print(f"sha256         : {digest}")
    print(f"file           : {src}")


def acquire(src: Path) -> str:
    if not src.is_file():
        # Folded into CORRUPT_OR_UNREADABLE rather than given an outcome of its own: a path with no
        # file behind it is unreadable in the only sense this script cares about.
        print(f"no such file: {src}")
        print(f"\nclassification : {CORRUPT_OR_UNREADABLE}")
        print("reason         : the path does not exist, so nothing could be read")
        return CORRUPT_OR_UNREADABLE

    digest = sha256(src)
    classification, reason, found = classify_text(extract_text(src))

    if found:
        print("document says of itself:")
        for k, v in found.items():
            print(f"  {k:<24} {v}")
    report(classification, reason, found, digest, src)

    if classification != VERIFIED_PRINCIPAL:
        print("\nREFUSED -- not copied into corpus/sources/. Only the principal Rules belong there.")
        if classification == REJECTED_AMENDMENT:
            print("An amendment is still evidence: it is one of the instruments that changed the")
            print("principal Rules, and its hash above identifies exactly the copy you hold. If you")
            print("want to keep it, file it deliberately under its own SourceRecord -- amendments")
            print("are modelled separately (see docs/WEEK2_RULE_INGESTION_PLAN.md). Do not let this")
            print("script decide that for you.")
        elif classification == UNCONFIRMED_DOCUMENT:
            print("Identity is not established. Read the file and decide; the hash above pins the")
            print("copy you looked at. Never substitute a consolidated text for the principal")
            print("instrument -- that mistake was made once and retracted (docs/RETRACTIONS.md).")
        else:
            print("Nothing about this file could be checked. Re-export or re-download it; an")
            print("image-only scan needs OCR before its identity can be confirmed at all.")
        return classification

    SOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, DEST)
    stored_digest = sha256(DEST)
    line = f"{stored_digest}  {DEST.name}\n"
    sums = SOURCES / "SHA256SUMS"
    existing = sums.read_text() if sums.exists() else ""
    if DEST.name not in existing:
        sums.write_text(existing + line)

    print(f"\nstored : {DEST.relative_to(ROOT)}")
    print("\nIdentity matched. This is NOT human review -- nothing here may set human_reviewed=True.")
    print("Now add this to checker/provenance.py, replacing BOARD_MEETING_RULES_2014:")
    print(provenance_block(stored_digest, found))
    print("\nThen: ./scripts/run_tests.sh")
    return VERIFIED_PRINCIPAL


def _test() -> int:
    ok = fail = 0

    def check(c: bool, label: str) -> None:
        nonlocal ok, fail
        if c:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    # Fixture values below are ILLUSTRATIVE strings for exercising the parser. The gazette numbers
    # and dates in them -- including "G.S.R. 240(E)" and "31st March, 2014" -- are UNVERIFIED
    # third-party claims, not a statement about the real notification. They must be read off the
    # actual document when it is acquired.
    principal = "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 31st March, 2014 " \
                "G.S.R. 240(E).- In exercise of the powers conferred under sections 173, 175, " \
                "177, 179, 184 and 188 read with sub-section (1) of section 469 of the Companies " \
                "Act, 2013 (18 of 2013), the Central Government hereby makes the following rules, " \
                "namely:- 1. Short title and commencement.-(1) These rules may be called the " \
                "Companies (Meetings of Board and its Powers) Rules, 2014."
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

    # --- classification of the principal notification -------------------------------------------
    cls, reason, found = classify_text(principal)
    check(cls == VERIFIED_PRINCIPAL, f"principal notification -> VERIFIED_PRINCIPAL (got {cls})")
    check(found["matches_unverified_lead"] is True,
          "principal fixture's gazette number matches the unverified lead")
    check(not found["amending_language"], "principal notification carries no amending language")

    # VERIFIED_PRINCIPAL means identity matched. It must never imply a human has read the file.
    block = provenance_block("deadbeef", found)
    check("human_reviewed=False" in block, "provenance block records human_reviewed=False")
    check("human_reviewed=True" not in block, "provenance block never sets human_reviewed=True")

    # --- amendments -----------------------------------------------------------------------------
    titled_amendment = "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 12th June, 2014 " \
                       "G.S.R. 590(E).- In exercise of the powers conferred by section 173 read " \
                       "with section 469 of the Companies Act, 2013, the Central Government hereby " \
                       "makes the following rules further to amend the Companies (Meetings of " \
                       "Board and its Powers) Rules, 2014, namely:- 1. (1) These rules may be " \
                       "called the Companies (Meetings of Board and its Powers) Amendment Rules, " \
                       "2014."
    cls, reason, found = classify_text(titled_amendment)
    check(cls == REJECTED_AMENDMENT, f"'Amendment Rules' title -> REJECTED_AMENDMENT (got {cls})")
    check(found["principal_title_found"],
          "amendment quoting the principal title is still rejected, not rescued by it")

    # The short-title clause naming it an "Amendment Rules" can fall past the extracted pages. The
    # operative body language is what has to catch this one.
    untitled_amendment = "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 14th " \
                         "December, 2020 G.S.R. 806(E).- In exercise of the powers conferred by " \
                         "sections 173 and 175 read with section 469 of the Companies Act, 2013, " \
                         "the Central Government hereby makes the following rules further to " \
                         "amend the Companies (Meetings of Board and its Powers) Rules, 2014, " \
                         "namely:- 2. In the said rules, in rule 4, for sub-rule (2), the " \
                         "following shall be substituted, namely:-"
    cls, reason, found = classify_text(untitled_amendment)
    check(not found["amendment_title_found"], "fixture genuinely lacks 'Amendment Rules' in title")
    check(cls == REJECTED_AMENDMENT,
          f"amendment without 'Amendment Rules' in title -> REJECTED_AMENDMENT (got {cls})")

    phrase_fixtures = (
        ("further to amend",
         "the Central Government hereby makes the following rules further to amend the Companies "
         "(Meetings of Board and its Powers) Rules, 2014, namely:-"),
        ("in the said rules", "2. In the said rules, in rule 4, after clause (a),"),
        ("shall be substituted",
         "for the words 'seven days', the words 'three days' shall be substituted"),
        ("shall be inserted", "after rule 6, the following rule shall be inserted, namely:-"),
        ("shall be omitted", "in rule 15, sub-rule (2) shall be omitted"),
    )
    for phrase, fixture in phrase_fixtures:
        cls, _, _ = classify_text(fixture)
        check(cls == REJECTED_AMENDMENT, f"body language '{phrase}' -> REJECTED_AMENDMENT")

    # --- consolidated / as-amended reprint -------------------------------------------------------
    consolidated = "The Companies (Meetings of Board and its Powers) Rules, 2014 [As amended up " \
                   "to 1st April, 2021] Note: this is a consolidated text prepared for reference, " \
                   "incorporating all amendments notified up to the date shown above. " \
                   "1. Short title and commencement..."
    cls, reason, found = classify_text(consolidated)
    check(cls == UNCONFIRMED_DOCUMENT, f"consolidated text -> UNCONFIRMED_DOCUMENT (got {cls})")
    check("consolidated" in reason, f"consolidation named in the reason: {reason[:60]}...")
    check(found["principal_title_found"],
          "consolidated text carries the principal title yet is still not accepted")

    # --- unreadable ------------------------------------------------------------------------------
    check(classify_text("")[0] == CORRUPT_OR_UNREADABLE, "empty extraction -> CORRUPT_OR_UNREADABLE")
    check(classify_text("\x0c \n \x0c")[0] == CORRUPT_OR_UNREADABLE,
          "image-only scan (form feeds only) -> CORRUPT_OR_UNREADABLE")

    # --- gazette number that disagrees with the unverified lead ----------------------------------
    mismatched = "MINISTRY OF CORPORATE AFFAIRS NOTIFICATION New Delhi, the 31st March, 2014 " \
                 "G.S.R. 418(E).- In exercise of the powers conferred by section 469 of the " \
                 "Companies Act, 2013, the Central Government hereby makes the following rules, " \
                 "namely:- 1. Short title.- These rules may be called the Companies (Meetings of " \
                 "Board and its Powers) Rules, 2014."
    cls, reason, found = classify_text(mismatched)
    check(cls == UNCONFIRMED_DOCUMENT, f"gazette mismatch -> UNCONFIRMED_DOCUMENT (got {cls})")
    check(found["matches_unverified_lead"] is False, "mismatch against the lead is recorded")
    check("418" in reason and LEAD_NOTIFICATION_NUMBER in reason,
          "mismatch reason names both the number read and the lead it was checked against")
    check("unverified" in reason.lower(),
          "mismatch reason says the lead is unverified, so neither side is asserted as fact")

    no_notification = "1. Short title and commencement. These rules may be called the Companies " \
                      "(Meetings of Board and its Powers) Rules, 2014. They shall come into force " \
                      "on the 1st day of April, 2014."
    cls, reason, found = classify_text(no_notification)
    check(cls == UNCONFIRMED_DOCUMENT, "principal title but no gazette number -> UNCONFIRMED_DOCUMENT")
    check(found["matches_unverified_lead"] is None,
          "no gazette number reads as 'could not check', not 'did not match'")

    check(classify_text("some entirely unrelated circular")[0] == UNCONFIRMED_DOCUMENT,
          "unrelated document -> UNCONFIRMED_DOCUMENT")

    # --- the exit-code map must cover every classification the code can produce ------------------
    produced = {VERIFIED_PRINCIPAL, REJECTED_AMENDMENT, UNCONFIRMED_DOCUMENT, CORRUPT_OR_UNREADABLE}
    check(produced <= set(EXIT_CODES), "every classification maps to an exit code")
    check([c for c, e in EXIT_CODES.items() if e == 0] == [VERIFIED_PRINCIPAL],
          "only VERIFIED_PRINCIPAL exits 0")

    # The lead is stated in two places -- here, and checker/provenance.py. Duplicating a value
    # that NOBODY HAS VERIFIED is how a wrong number quietly becomes load-bearing in two files at
    # once. This script must run from any directory without PYTHONPATH, so it cannot import that
    # module at runtime; instead the test asserts the two copies still agree, and fails if they
    # drift. Soft: skipped when run outside the repo, where the check is not possible anyway.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from checker.provenance import PRINCIPAL_RULES_LEAD as _lead
    except Exception:
        print("[SKIP] lead-drift check (checker.provenance not importable from here)")
    else:
        check(LEAD_NOTIFICATION_NUMBER in _lead["claimed_notification"],
              f"lead notification agrees with provenance.py ({_lead['claimed_notification']})")
        check(LEAD_DATE_CLAIM == _lead["claimed_date"],
              f"lead date agrees with provenance.py ({_lead['claimed_date']})")
        # Was UNFETCHED_CORROBORATION until the gazette was acquired and stated its own
        # notification. Confirmed from the document is exactly CORROBORATED; it is not VERIFIED,
        # because nobody has read the document yet.
        check(_lead["evidence_state"] == "CORROBORATED",
              "the shared lead is now confirmed from the document, not promoted past it")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    if len(sys.argv) != 2:
        print(__doc__); raise SystemExit(1)
    raise SystemExit(EXIT_CODES[acquire(Path(sys.argv[1]))])
