#!/usr/bin/env python3
"""Company facts with the basis they rest on, and a confirmation before anything uses them.

PLAN_26 §5 S2-alt. `data.gov.in` refuses automated access (S0 measured `Disallow: /` on the
apex and a 403 on `www`), and CLAUDE.md forbids working around it. So a company fact reaches
this engine by one of exactly two lawful routes, and each carries its own basis:

    USER_FACT      the user typed it. Labelled "you told us". No document exists, so there
                   is nothing to quote and a quote is REFUSED
    COMPANY_FACT   read out of the MCA "Company Master Data" page the USER downloaded from
                   mca.gov.in and uploaded to us. Labelled "MCA master data, as uploaded by
                   the user on <date>", and it MUST carry the span it was read from

## Neither basis can verify anything

`can_verify` is False for both, and it is False by delegation to
`checker/sources/tiers.py` rather than by a literal here -- there is one place that decides
what may be called VERIFIED and this is not it. A company fact is a fact about a company,
never a rule about companies: "this company is listed" plus "listed companies must do X" is
an argument, and only the second half is law we hold.

## Confirmation is an attestation, and it is the gate

`confirmed` is False on every fact this module produces. Only the caller can set it, and it
means "the surface showed this field, with its quoted span, to a person and they said yes".
Exactly the shape of `quote_viewed` in `gateway/migrations/008_decision_evidence.sql`: it is
not proof a person read anything, it is the record of a surface claiming they did. What it
buys is that `for_event_table()` drops every unconfirmed fact, so a misparsed registered
office cannot silently decide a stamp-duty question.

## No personal data

`FIELDS` has no director name and no DIN, and that is the decision rather than an oversight.
PLAN_26 §7.3 records it: director data is personal data, outside GODL, and the
recommendation is not to store it. `mca_master_data.py` refuses to emit one and asserts it.

Run: PYTHONPATH=. python3 checker/sources/company_facts.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.sources.tiers import COMPANY_FACT, can_verify

# The basis a fact rests on. USER_FACT is not a source tier -- no third party is involved --
# so it lives here rather than in tiers.py, and `tier_of()` maps it for rendering.
USER_FACT = "USER_FACT"
BASES = (USER_FACT, COMPANY_FACT)

YOU_TOLD_US = "you told us"

# Every field either route may carry. Deliberately closed, and deliberately without
# `director_name` or `din`.
CIN = "cin"
NAME = "name"
STATUS = "status"
ROC = "roc"
ADDRESS = "address"
STATE = "state"
INCORPORATED_ON = "incorporated_on"
LISTED = "listed"
FIELDS = (CIN, NAME, STATUS, ROC, ADDRESS, STATE, INCORPORATED_ON, LISTED)

# Fields a user may type directly. The job names three; the rest come only from a document,
# because asking someone to retype their registered office from memory invites the error
# the quoted span exists to prevent.
TYPEABLE = (LISTED, STATE, CIN)

# Which of these the event table actually reads (checker/events.FACTS). Everything else is
# recorded and reported as recorded -- never silently dropped, because "a fact that is
# silently ignored reads as one that was taken into account" (gateway/verbs.py).
EVENT_TABLE_FIELDS = (LISTED, STATE)

# A CIN is 21 characters: L/U + 5 digits + 2 letters + 4 digits + 3 letters + 6 digits.
# Shape only. A well-formed CIN is not a real one, and this module never claims it is.
_CIN = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")
_DIN = re.compile(r"\b\d{8}\b")


class FactError(ValueError):
    """Raised on a fact that cannot be shown with its basis. Never a warning."""


@dataclass(frozen=True)
class CompanyFact:
    field: str
    value: str
    basis: str
    quoted_span: str = ""
    source_label: str = ""
    confirmed: bool = False

    def __post_init__(self) -> None:
        if self.field not in FIELDS:
            raise FactError(f"{self.field!r} is not a company fact this engine holds; one "
                            f"of {FIELDS}. `director_name` and `din` are absent on "
                            f"purpose: personal data (PLAN_26 §7.3)")
        if self.basis not in BASES:
            raise FactError(f"{self.basis!r} is not a basis; one of {BASES}")
        if not str(self.value).strip():
            raise FactError(f"{self.field}: a fact with no value is not a fact")
        if _DIN.search(self.quoted_span) and self.field != CIN:
            raise FactError(
                f"{self.field}: the quoted span carries an 8-digit token, which is the "
                f"shape of a DIN. A span is shown to the user and stored with the fact, so "
                f"it may not carry director personal data")
        self._check_basis()

    def _check_basis(self) -> None:
        if self.basis == COMPANY_FACT:
            if not self.quoted_span.strip():
                raise FactError(
                    f"{self.field}: a fact read from a document MUST carry the span it was "
                    f"read from. Without it the user is asked to confirm a value with no "
                    f"way to check it, which is the confirmation being theatre")
            if not self.source_label.strip():
                raise FactError(f"{self.field}: a document fact must say which document")
            return
        # USER_FACT
        if self.quoted_span:
            raise FactError(
                f"{self.field}: a fact the user typed cannot carry a quoted span -- there "
                f"is no document to quote. A span here would be us inventing provenance")
        if self.field not in TYPEABLE:
            raise FactError(
                f"{self.field}: not typeable by hand; one of {TYPEABLE}. The rest come "
                f"only from a document, because retyping them from memory invites exactly "
                f"the error a quoted span prevents")
        if self.source_label and self.source_label != YOU_TOLD_US:
            raise FactError(f"{self.field}: a USER_FACT is labelled {YOU_TOLD_US!r}, not "
                            f"{self.source_label!r}")

    @property
    def label(self) -> str:
        """What the user is shown. Never the word 'verified'."""
        return self.source_label or YOU_TOLD_US

    @property
    def can_verify(self) -> bool:
        """Always False, and decided by tiers.py rather than asserted here."""
        return can_verify(tier_of(self.basis))

    def to_dict(self) -> dict:
        return {"field": self.field, "value": self.value, "basis": self.basis,
                "label": self.label, "quoted_span": self.quoted_span,
                "confirmed": self.confirmed, "can_verify": self.can_verify}


def tier_of(basis: str) -> str:
    """The source tier a basis renders as. Both are COMPANY_FACT: neither can verify."""
    if basis not in BASES:
        raise FactError(f"{basis!r} is not a basis; one of {BASES}")
    return COMPANY_FACT


def user_fact(field: str, value: object) -> CompanyFact:
    """A fact the user typed. Unconfirmed, labelled "you told us", and never verified."""
    if field == LISTED:
        value = _yes_no(value, field)
    elif field == CIN:
        value = str(value).strip().upper()
        if not _CIN.match(value):
            raise FactError(
                f"cin {value!r} is not the shape of a CIN (21 chars: L/U, 5 digits, 2 "
                f"letters, 4 digits, 3 letters, 6 digits). Shape only -- a well-formed CIN "
                f"is not a real one and this engine never claims it is")
    return CompanyFact(field=field, value=str(value).strip(), basis=USER_FACT,
                       source_label=YOU_TOLD_US, confirmed=False)


def _yes_no(value: object, field: str) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip().lower()
    if text in ("yes", "true", "listed", "y"):
        return "yes"
    if text in ("no", "false", "unlisted", "n"):
        return "no"
    raise FactError(f"{field}: {value!r} is neither yes nor no. An unclear answer about "
                    f"whether a company is listed is not a fact about it")


def confirmed(facts: list) -> list:
    return [f for f in facts if f.confirmed]


def unconfirmed(facts: list) -> list:
    return [f for f in facts if not f.confirmed]


def for_event_table(facts: list) -> tuple[dict, list, list]:
    """(what events.assess may read, the facts recorded but not read, the unconfirmed ones).

    Three return values because all three must be reported. Dropping the unconfirmed ones
    silently would defeat the confirmation, and dropping the unread ones silently would
    break the rule `gateway/verbs.py` already keeps: a fact the caller supplied and believes
    changed the answer is never quietly ignored.
    """
    out: dict = {}
    recorded: list = []
    for f in confirmed(facts):
        if f.field not in EVENT_TABLE_FIELDS:
            recorded.append(f)
            continue
        out[f.field] = (f.value == "yes") if f.field == LISTED else f.value
    return out, recorded, unconfirmed(facts)


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

    print("sources.company_facts")
    MCA = "MCA master data, as uploaded by the user on 2026-10-01"

    # ── a fact with no quoted span is rejected ───────────────────────────────
    try:
        CompanyFact(field=STATE, value="Maharashtra", basis=COMPANY_FACT,
                    source_label=MCA)
        check(False, "a DOCUMENT fact with no quoted span is rejected")
    except FactError as e:
        check("MUST carry the span" in str(e),
              f"a document fact with no quoted span is rejected ({e!s:.44})")
    try:
        CompanyFact(field=STATE, value="Maharashtra", basis=COMPANY_FACT,
                    quoted_span="   ", source_label=MCA)
        check(False, "...and whitespace is not a span")
    except FactError:
        check(True, "...and a whitespace span is rejected too, not just an empty one")
    try:
        CompanyFact(field=STATE, value="Maharashtra", basis=COMPANY_FACT,
                    quoted_span="Registered Address: ... Maharashtra")
        check(False, "...and a document fact must name its document")
    except FactError as e:
        check("which document" in str(e), "...and a document fact must name its document")

    # The other direction: a typed fact may NOT carry a span.
    try:
        CompanyFact(field=STATE, value="Maharashtra", basis=USER_FACT,
                    quoted_span="Registered Address: Mumbai, Maharashtra")
        check(False, "a USER_FACT cannot carry a quoted span")
    except FactError as e:
        check("no document to quote" in str(e),
              "a USER_FACT cannot carry a span -- that would be inventing provenance")

    good = CompanyFact(field=STATE, value="Maharashtra", basis=COMPANY_FACT,
                       quoted_span="Registered Address: 5 Fort, Mumbai, Maharashtra",
                       source_label=MCA)
    check(good.quoted_span and good.label == MCA, "a well-formed document fact is accepted")

    # ── never verified, either way ───────────────────────────────────────────
    check(not good.can_verify, "a document fact cannot verify")
    check(not user_fact(LISTED, True).can_verify, "a typed fact cannot verify")
    check(tier_of(USER_FACT) == COMPANY_FACT and tier_of(COMPANY_FACT) == COMPANY_FACT,
          "both bases render at tier COMPANY_FACT")
    for f in (good, user_fact(LISTED, True), user_fact(STATE, "Kerala")):
        check("verified" not in f.label.lower(),
              f"the label for {f.field} never says 'verified' ({f.label!r:.44})")
    check(user_fact(LISTED, False).label == YOU_TOLD_US,
          f"a typed fact is labelled {YOU_TOLD_US!r}")

    # ── an unconfirmed fact is never used ────────────────────────────────────
    typed = [user_fact(LISTED, True), user_fact(STATE, "Maharashtra")]
    check(all(not f.confirmed for f in typed), "every fact starts UNCONFIRMED")
    read, recorded, pending = for_event_table(typed)
    check(read == {}, f"for_event_table gives the event table NOTHING unconfirmed ({read})")
    check(len(pending) == 2, "...and reports both as pending confirmation")
    okd = [CompanyFact(**{**f.__dict__, "confirmed": True}) for f in typed]
    read, recorded, pending = for_event_table(okd)
    check(read == {"listed": True, "state": "Maharashtra"},
          f"once confirmed, the event table reads them ({read})")
    check(pending == [], "...and nothing is pending")
    check(read["listed"] is True,
          "...`listed` reaches the event table as a bool, as events.FACTS expects")

    # Mixed: one confirmed, one not.
    mixed = [okd[0], typed[1]]
    read, recorded, pending = for_event_table(mixed)
    check(read == {"listed": True} and len(pending) == 1,
          f"a mixed set passes only the confirmed fact ({read})")

    # A confirmed fact the event table does not read is REPORTED, not dropped.
    cin = CompanyFact(field=CIN, value="U72200MH2010PTC123456", basis=USER_FACT,
                      source_label=YOU_TOLD_US, confirmed=True)
    read, recorded, pending = for_event_table([cin])
    check(read == {} and [f.field for f in recorded] == [CIN],
          "a confirmed CIN is RECORDED and reported, never silently ignored")

    # ── no personal data ────────────────────────────────────────────────────
    for bad in ("director_name", "din", "signatory"):
        try:
            CompanyFact(field=bad, value="x", basis=USER_FACT)
            check(False, f"{bad} is not a field")
        except FactError as e:
            check("personal data" in str(e) or "not a company fact" in str(e),
                  f"{bad!r} is not a field this engine holds")
    check(CIN not in ("din",) and "din" not in FIELDS and "director_name" not in FIELDS,
          f"FIELDS carries no director name and no DIN ({FIELDS})")
    try:
        CompanyFact(field=NAME, value="Acme", basis=COMPANY_FACT, source_label=MCA,
                    quoted_span="RAJESH KUMAR 01234567 Director")
        check(False, "a span carrying a DIN-shaped token is rejected")
    except FactError as e:
        check("shape of a DIN" in str(e),
              "a span carrying an 8-digit DIN-shaped token is rejected")
    check(CompanyFact(field=CIN, value="U72200MH2010PTC123456", basis=COMPANY_FACT,
                      source_label=MCA,
                      quoted_span="CIN: U72200MH2010PTC123456").field == CIN,
          "...but a CIN span is allowed: its own digits are not a DIN")

    # ── typing rules ─────────────────────────────────────────────────────────
    check(user_fact(LISTED, True).value == "yes" and user_fact(LISTED, False).value == "no",
          "listed is normalised to yes/no")
    for v in ("Listed", "unlisted", "TRUE", "n"):
        check(user_fact(LISTED, v).value in ("yes", "no"), f"listed accepts {v!r}")
    for v in ("maybe", "", "probably"):
        try:
            user_fact(LISTED, v)
            check(False, f"listed refuses {v!r}")
        except FactError as e:
            check("neither yes nor no" in str(e) or "no value" in str(e),
                  f"listed refuses {v!r} rather than guessing")
    check(user_fact(CIN, "u72200mh2010ptc123456").value == "U72200MH2010PTC123456",
          "a CIN is upper-cased")
    for bad in ("U72200MH2010PTC12345", "X72200MH2010PTC123456", "not-a-cin"):
        try:
            user_fact(CIN, bad)
            check(False, f"CIN {bad!r} is refused")
        except FactError as e:
            check("shape of a CIN" in str(e), f"CIN {bad!r} is refused on shape")
    try:
        user_fact(ADDRESS, "5 Fort, Mumbai")
        check(False, "an address cannot be typed by hand")
    except FactError as e:
        check("not typeable" in str(e),
              "an address cannot be typed by hand -- it comes from the document or not "
              "at all")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
