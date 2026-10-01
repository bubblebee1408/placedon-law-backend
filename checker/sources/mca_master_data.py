#!/usr/bin/env python3
"""Read an MCA "Company Master Data" page the USER downloaded and uploaded to us.

PLAN_26 §5 S2-alt, replacing S2. `data.gov.in` is BLOCKED for us — S0 measured `Disallow: /`
on the apex and HTTP 403 on `www` — and CLAUDE.md forbids working around it, so the MCA
open-data route is closed. What remains is lawful and narrow: **the user fetches their own
company's master-data page from mca.gov.in and uploads it.** We never fetch it. mca.gov.in's
WAF is on CLAUDE.md's do-not-bypass list and nothing here touches a network.

    document tier   CLIENT        it is the tenant's own upload
    fact basis      COMPANY_FACT  labelled "MCA master data, as uploaded by the user on
                                  <date>", and every field carries the span it came from

## Four properties, each with a test that can fail

**A field that is not found is ABSENT, never guessed.** And `unmatched` names every label
this parser looked for and did not find, so a real upload that half-parses reports which
labels it did not recognise rather than quietly returning four facts out of eight.

**No text layer is "cannot read", not "no facts".** `checker/pdf_pages` raises on a file it
cannot open, but a scan opens fine and yields an empty string — so the toolchain-as-evidence
failure that module was built to refuse reappears one layer up, wearing a different hat:
"this scan has no text" would read as "this company has no registered office". `parse_pdf`
raises `CannotRead`.

**Director names and DINs never leave this module.** The text is cut at the
Directors/Signatory heading before any label is matched, and `_refuse_personal_data` then
re-checks the output against the lines below that cut. Two mechanisms because the first is a
parser and the second is an assertion, and only the second still works when the heading is
spelled differently.

**Nothing is used until the user confirms.** Every fact comes back
`confirmed=False`; `company_facts.for_event_table()` drops the unconfirmed.

## The label table is UNVERIFIED against a real MCA page

Nobody here has seen one — see `mca_fixture.py`. Labels are matched case-insensitively with
optional trailing `?`/`:` and several spellings per field, and a miss is reported rather than
guessed. **The first real upload is what validates this table**, and until one happens the
parser is tested against a layout this repository invented. That is the honest state of it.

Run: PYTHONPATH=. python3 checker/sources/mca_master_data.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _field
from pathlib import Path

from checker.sources import company_facts as cf
from checker.sources.tiers import COMPANY_FACT

# Where the personal-data section starts. Several spellings, because the cut is the first
# line of defence and a missed heading must not be the only thing standing.
_DIRECTOR_HEADINGS = (
    "directors/signatory details", "director/signatory details",
    "directors / signatory details", "directors details", "signatory details",
    "din/pan",
)

# field -> the label spellings we accept. Order matters only for reporting.
_LABELS: dict[str, tuple[str, ...]] = {
    cf.CIN: ("cin", "corporate identity number", "cin/fcrn"),
    cf.NAME: ("company name", "name of company", "company / llp name"),
    cf.ROC: ("roc code", "roc", "registrar of companies"),
    cf.INCORPORATED_ON: ("date of incorporation", "incorporation date",
                         "date of registration"),
    cf.ADDRESS: ("registered address", "registered office address",
                 "address of registered office", "registered office"),
    cf.LISTED: ("whether listed or not", "whether listed", "listed status", "listing status"),
    cf.STATUS: ("company status(for efiling)", "company status for efiling",
                "company status", "status"),
}

# Used ONLY to locate a State inside an address string. Not an authority on anything: it
# decides no obligation, validates nothing, and a State absent from it makes `state` ABSENT
# rather than wrong. Ordered longest-first so "Andhra Pradesh" wins over a substring.
_STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
)
_STATES_LONGEST_FIRST = tuple(sorted(_STATES, key=len, reverse=True))

_DIN = re.compile(r"\b\d{8}\b")


class CannotRead(ValueError):
    """The document could not be read. NEVER returned as an empty set of facts."""


class PersonalDataLeak(AssertionError):
    """A director name or DIN reached the output. A bug, and it stops the parse."""


@dataclass(frozen=True)
class ParsedMasterData:
    facts: tuple = ()
    unmatched: tuple = ()
    source_label: str = ""
    director_lines_dropped: int = 0
    pages: int = 0

    @property
    def by_field(self) -> dict:
        return {f.field: f for f in self.facts}

    def to_dict(self) -> dict:
        return {"source_label": self.source_label,
                "facts": [f.to_dict() for f in self.facts],
                "unmatched": list(self.unmatched),
                "director_lines_dropped": self.director_lines_dropped,
                "pages": self.pages,
                "note": ("Every field carries the span it was read from. Nothing is used "
                         "until you confirm it. Director names and DINs are not read, not "
                         "stored and not returned (personal data, PLAN_26 §7.3).")}


def source_label(uploaded_on: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", uploaded_on or ""):
        raise CannotRead(f"uploaded_on must be an ISO date, got {uploaded_on!r} -- a "
                         f"document fact must say WHEN it was uploaded")
    return f"MCA master data, as uploaded by the user on {uploaded_on}"


def split_directors(text: str) -> tuple[str, list[str]]:
    """(the page above the director block, the lines at or below it).

    Cut before any label is matched, so a director row can never be a candidate for a
    company field however it is laid out.
    """
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if any(low.startswith(h) for h in _DIRECTOR_HEADINGS):
            return "\n".join(lines[:i]), lines[i:]
    return text or "", []


def _value_after(line: str, label: str) -> str:
    """The text after `label` on `line`, with an optional `?`/`:` separator."""
    m = re.match(rf"^\s*{re.escape(label)}\s*[?:]?\s*(.+?)\s*$", line, re.I)
    return m.group(1).strip() if m else ""


def _find(lines: list[str], labels: tuple[str, ...]) -> tuple[str, str]:
    """(value, the whole line it came from) for the first label that matches."""
    for label in labels:
        for line in lines:
            if line.strip().lower().startswith(label):
                value = _value_after(line, label)
                if value and value not in ("-", "--", "NA", "N/A"):
                    return value, line
    return "", ""


def state_in(address: str) -> str:
    """The State named inside an address, or "" when none of the known names appears."""
    low = (address or "").lower()
    for name in _STATES_LONGEST_FIRST:
        if name.lower() in low:
            return name
    return ""


def parse_text(text: str, *, uploaded_on: str) -> ParsedMasterData:
    """Company facts from the page's text. Unconfirmed, each with its span."""
    label = source_label(uploaded_on)
    if not (text or "").strip():
        raise CannotRead(
            "the document carries no text at all. That is 'we could not read it', not "
            "'the company has no details' -- an empty parse would read as a fact about "
            "the company")

    body, dropped = split_directors(text)
    lines = body.splitlines()
    facts, unmatched = [], []

    for field_name, labels in _LABELS.items():
        value, line = _find(lines, labels)
        if not value:
            unmatched.append(f"{field_name} (looked for: {', '.join(labels)})")
            continue
        if field_name == cf.LISTED:
            value = _listed(value)
            if not value:
                unmatched.append(f"{field_name} (found the label, could not read "
                                 f"{_find(lines, labels)[0]!r} as listed/unlisted)")
                continue
        facts.append(cf.CompanyFact(field=field_name, value=value, basis=COMPANY_FACT,
                                    quoted_span=line.strip(), source_label=label,
                                    confirmed=False))

    # State is DERIVED from the address, and quotes the address line -- the span a user is
    # shown must be text that is really in the document, not a word we lifted out of it.
    addr = next((f for f in facts if f.field == cf.ADDRESS), None)
    if addr is not None:
        st = state_in(addr.value)
        if st:
            facts.append(cf.CompanyFact(field=cf.STATE, value=st, basis=COMPANY_FACT,
                                        quoted_span=addr.quoted_span, source_label=label,
                                        confirmed=False))
        else:
            unmatched.append(f"state (no known State name appears in the registered "
                             f"address; it is ABSENT rather than guessed)")
    else:
        unmatched.append("state (no registered address to read it from)")

    out = ParsedMasterData(facts=tuple(facts), unmatched=tuple(unmatched),
                           source_label=label, director_lines_dropped=len(dropped))
    _refuse_personal_data(out, dropped)
    return out


def _listed(value: str) -> str:
    low = value.strip().lower()
    if low.startswith("listed") or low in ("yes", "y", "true"):
        return "yes"
    if low.startswith("unlisted") or low in ("no", "n", "false"):
        return "no"
    return ""


def _refuse_personal_data(parsed: ParsedMasterData, dropped: list[str]) -> None:
    """Raise if any director name or DIN reached the output.

    The second mechanism, and the one that still works when the heading is spelled in a way
    `split_directors` does not know: it checks the RESULT, against the lines that were cut.
    """
    blob = "\n".join([f.value for f in parsed.facts]
                     + [f.quoted_span for f in parsed.facts])
    for f in parsed.facts:
        if f.field != cf.CIN and _DIN.search(f.quoted_span + " " + f.value):
            raise PersonalDataLeak(
                f"{f.field}: an 8-digit DIN-shaped token reached the output "
                f"({f.quoted_span[:60]!r})")
    for line in dropped:
        stripped = line.strip()
        if len(stripped) > 8 and stripped in blob:
            raise PersonalDataLeak(
                f"a line from the director block reached the output ({stripped[:60]!r})")


def parse_pdf(path: str | Path, *, uploaded_on: str) -> ParsedMasterData:
    """Parse an uploaded master-data PDF. Raises CannotRead on a page with no text layer."""
    from checker.pdf_pages import PdfUnreadable, extract_pages

    try:
        pages = extract_pages(path)
    except PdfUnreadable as exc:
        raise CannotRead(f"cannot read: {exc}") from None
    if not pages:
        raise CannotRead("cannot read: the document declares no pages")
    text = "\n".join(pages)
    if not text.strip():
        raise CannotRead(
            f"cannot read: {len(pages)} page(s) and no text layer on any of them. This "
            f"looks like a scan or a photograph. We will not return an empty set of facts "
            f"for it -- 'we could not read this page' and 'this company has no registered "
            f"office' must never be the same answer. Upload the PDF as downloaded from "
            f"mca.gov.in rather than a scan or a screenshot")
    out = parse_text(text, uploaded_on=uploaded_on)
    return ParsedMasterData(facts=out.facts, unmatched=out.unmatched,
                            source_label=out.source_label,
                            director_lines_dropped=out.director_lines_dropped,
                            pages=len(pages))


def _test() -> int:
    import tempfile
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("sources.mca_master_data")
    from checker.sources import mca_fixture as fx
    UP = "2026-10-01"

    text = fx.master_data_text()
    p = parse_text(text, uploaded_on=UP)
    got = p.by_field

    # ── the fields, each with a span that is really in the document ──────────
    check(set(got) == {cf.CIN, cf.NAME, cf.ROC, cf.INCORPORATED_ON, cf.ADDRESS,
                       cf.LISTED, cf.STATUS, cf.STATE},
          f"all eight fields parse ({sorted(got)})")
    check(got[cf.CIN].value == fx.SYNTHETIC["cin"], f"cin = {got[cf.CIN].value}")
    check(got[cf.NAME].value == fx.SYNTHETIC["name"], "company name parses")
    check(got[cf.ROC].value == fx.SYNTHETIC["roc"], "roc parses")
    check(got[cf.INCORPORATED_ON].value == "14/08/2010", "date of incorporation parses")
    check(got[cf.STATUS].value == "Active", f"status = {got[cf.STATUS].value}")
    check(got[cf.LISTED].value == "no",
          f"'Unlisted' becomes listed=no ({got[cf.LISTED].value})")
    check(got[cf.STATE].value == "Maharashtra",
          f"state is DERIVED from the address ({got[cf.STATE].value})")
    for f in p.facts:
        check(f.quoted_span and f.quoted_span in text,
              f"{f.field}: its span byte-matches the document ({f.quoted_span[:38]!r})")
    check(got[cf.STATE].quoted_span == got[cf.ADDRESS].quoted_span,
          "state quotes the ADDRESS line -- a span shown to a user must be text really in "
          "the document, not a word lifted out of it")

    # ── every fact is unconfirmed, at tier COMPANY_FACT, never verified ─────
    check(all(not f.confirmed for f in p.facts), "every fact comes back UNCONFIRMED")
    check(all(f.basis == COMPANY_FACT for f in p.facts), "every fact is basis COMPANY_FACT")
    check(all(not f.can_verify for f in p.facts), "no fact can verify")
    check(p.source_label == f"MCA master data, as uploaded by the user on {UP}",
          f"the source label names the upload date ({p.source_label})")
    check(all(f.source_label == p.source_label for f in p.facts),
          "...and every fact carries it")
    try:
        parse_text(text, uploaded_on="01-10-2026")
        check(False, "a non-ISO upload date is refused")
    except CannotRead as e:
        check("ISO date" in str(e), "a non-ISO upload date is refused")

    # ── an unconfirmed fact is never used by the event table ────────────────
    read, recorded, pending = cf.for_event_table(list(p.facts))
    check(read == {}, f"events.assess gets NOTHING from a fresh parse ({read})")
    check(len(pending) == len(p.facts), "...all eight are pending confirmation")

    # ── director names and DINs are not persisted ───────────────────────────
    blob = repr(p.to_dict())
    for din, name in fx.SYNTHETIC_DIRECTORS:
        check(din not in blob, f"DIN {din} is absent from the output")
        check(name not in blob, f"director name {name!r} is absent from the output")
    check(p.director_lines_dropped >= 3,
          f"the director block was cut, and the count is reported ({p.director_lines_dropped})")
    check("SYNTHETIC DIRECTOR" not in blob and "DIN" not in str(
        [f.value for f in p.facts]),
          "no director row reached a value")

    # An UNKNOWN heading defeats the cut. The property that must survive is not "it
    # raises" -- it is "no name and no DIN reaches the output", and it survives because a
    # director row matches no company label. Asserted as the property, not as an exception:
    # the first version of this test demanded a raise and was simply wrong about what the
    # guard is for.
    sneaky = text.replace(fx.DIRECTOR_HEADING, "Persons associated with the company")
    sp = parse_text(sneaky, uploaded_on=UP)
    check(sp.director_lines_dropped == 3,
          f"renaming the section heading does NOT defeat the cut: `DIN/PAN` is in the "
          f"heading list too, so the column header catches it "
          f"({sp.director_lines_dropped} lines dropped)")

    # Now defeat it properly -- no known heading anywhere -- and check the property that
    # has to survive anyway.
    bare = "\n".join(l for l in sneaky.splitlines() if not l.strip().startswith("DIN/PAN"))
    bp = parse_text(bare, uploaded_on=UP)
    bblob = repr(bp.to_dict())
    check(bp.director_lines_dropped == 0, "with every known heading gone, nothing is cut ...")
    for din, name in fx.SYNTHETIC_DIRECTORS:
        check(din not in bblob and name not in bblob,
              f"...and {name!r} STILL does not reach the output: a director row matches no "
              f"company label, so it produces no fact")
    check(len(bp.facts) == 8,
          f"...while the eight real fields still parse ({len(bp.facts)})")

    # And the second mechanism must be able to FIRE. A director row dressed as a company
    # label is the case where the cut is bypassed AND a fact is produced.
    dressed = ("Company Master Data\n"
               "Company Name   01234567 SYNTHETIC DIRECTOR ONE\n")
    try:
        parse_text(dressed, uploaded_on=UP)
        check(False, "a DIN-bearing line dressed as a company label is refused")
    except (PersonalDataLeak, cf.FactError) as e:
        check("DIN" in str(e),
              f"a DIN-bearing line dressed as a company label is REFUSED -- the guard can "
              f"turn red ({type(e).__name__})")
    check(_DIN.search("01234567") is not None and _DIN.search("0123456") is None,
          "the DIN shape is 8 digits exactly -- the guard is not matching everything")

    # ── a field that is not found is ABSENT, and reported ───────────────────
    thin = "Company Master Data\nCIN   U00000ZZ0000ZZZ000000\n"
    t = parse_text(thin, uploaded_on=UP)
    check(list(t.by_field) == [cf.CIN], f"only the field present parses ({list(t.by_field)})")
    check(len(t.unmatched) == 7 and any("state" in u for u in t.unmatched),
          f"...and the other seven are REPORTED as unmatched, with the labels looked for "
          f"({len(t.unmatched)})")
    noaddr = "Company Master Data\nRegistered Address   5 Nowhere Street, 999999\n"
    n = parse_text(noaddr, uploaded_on=UP)
    check(cf.STATE not in n.by_field and any("no known State" in u for u in n.unmatched),
          "an address with no known State leaves state ABSENT rather than guessing")

    # ── a page with no text is "cannot read", not "no facts" ────────────────
    for blank in ("", "   \n\n  "):
        try:
            parse_text(blank, uploaded_on=UP)
            check(False, "empty text raises CannotRead")
        except CannotRead as e:
            check("could not read it" in str(e),
                  f"empty text raises CannotRead, not an empty parse ({e!s:.40})")

    with tempfile.TemporaryDirectory() as d:
        good = fx.write_pdf(Path(d) / "m.pdf")
        pp = parse_pdf(good, uploaded_on=UP)
        check(pp.pages == 1 and len(pp.facts) == 8,
              f"the real PDF path parses all eight fields ({len(pp.facts)}, "
              f"{pp.pages} page)")
        check(all(not f.confirmed for f in pp.facts), "...still unconfirmed")
        gblob = repr(pp.to_dict())
        check(all(din not in gblob for din, _ in fx.SYNTHETIC_DIRECTORS),
              "...and no DIN survived the PDF path either")

        scan = fx.write_scanned_pdf(Path(d) / "scan.pdf")
        try:
            parse_pdf(scan, uploaded_on=UP)
            check(False, "a scanned PDF raises CannotRead")
        except CannotRead as e:
            check("no text layer" in str(e) and "must never be the same answer" in str(e),
                  "a scanned PDF with no text layer says CANNOT READ and says why")

        missing = Path(d) / "nope.pdf"
        try:
            parse_pdf(missing, uploaded_on=UP)
            check(False, "a missing file raises CannotRead")
        except CannotRead as e:
            check("cannot read" in str(e),
                  "a missing file is CannotRead too, not an empty parse")
        notpdf = Path(d) / "x.pdf"
        notpdf.write_bytes(b"this is not a pdf at all")
        try:
            parse_pdf(notpdf, uploaded_on=UP)
            check(False, "a non-PDF raises CannotRead")
        except CannotRead:
            check(True, "a file that is not a PDF is CannotRead, never empty facts")

    # ── label tolerance, the thing most likely to be wrong on a real page ───
    for variant, label in [("Whether listed or not?   Listed", cf.LISTED),
                           ("CORPORATE IDENTITY NUMBER: U00000ZZ0000ZZZ000000", cf.CIN),
                           ("Registered Office Address - 1 Road, Kerala, 600001",
                            cf.ADDRESS)]:
        v = parse_text("Company Master Data\n" + variant, uploaded_on=UP)
        check(label in v.by_field, f"label variant parses: {variant[:42]!r}")
    v = parse_text("Company Master Data\nWhether listed or not?   Listed", uploaded_on=UP)
    check(v.by_field[cf.LISTED].value == "yes", "'Listed' becomes yes")
    v = parse_text("Company Master Data\nWhether Listed or not   Somewhat", uploaded_on=UP)
    check(cf.LISTED not in v.by_field and any("could not read" in u for u in v.unmatched),
          "an unreadable listed value is unmatched, never defaulted to 'no'")
    check(state_in("1 Road, Andhra Pradesh") == "Andhra Pradesh",
          "the State match is longest-first, so Andhra Pradesh is not read as a substring")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    from checker.sources import mca_fixture as fx
    import json
    print(json.dumps(parse_text(fx.master_data_text(),
                                uploaded_on="2026-10-01").to_dict(), indent=2))
