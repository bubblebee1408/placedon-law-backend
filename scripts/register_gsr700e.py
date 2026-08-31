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
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STORE = Path("corpus/rules/gsr_700e_2022.txt")
RECORD = Path("corpus/sources/gsr700e_registration.json")

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
        "instrument_id": "INDIACODE_GSR_700E_DEFINITIONS_AMENDMENT_2022",
        "title": "G.S.R. 700(E) — Companies (Specification of Definition Details) "
                 "Amendment Rules, 2022, dated 15-09-2022",
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_file_sha256": digest,
        "stored_text": str(STORE),
        "stored_text_sha256": "sha256:" + hashlib.sha256(
            STORE.read_bytes()).hexdigest(),
        "operative_clause": clause,
        "classification": outcome,
        "evidence_state": "CORROBORATED",
        "not_yet": ("VERIFIED requires a hashed artifact AND human review. This script "
                    "performs the first half only. A person must read the clause above "
                    "against the stored text before the state moves to VERIFIED."),
    }, indent=1) + "\n", encoding="utf-8")

    print(f"stored         : {STORE}")
    print(f"record         : {RECORD}")
    print("\nNext, by hand:")
    print("  1. read the clause above against corpus/rules/gsr_700e_2022.txt")
    print("  2. in checker/prescribed_thresholds.py, change the two _PRESCRIBED")
    print("     entries from UNRESOLVED to CORROBORATED and cite this record")
    print("  3. run scripts/run_tests.sh — classify.small_company should stop")
    print("     answering INSUFFICIENT_DATA on the arithmetic")
    print("  4. close S-002 in research/TASKS.md")
    return outcome


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

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(EXIT[register(Path(sys.argv[1]))])
