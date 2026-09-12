"""Reconciling a draft against the registry -- conflicts, never conclusions.

The pasted Master Data Strip spec renders three remediation cells:

    Authorized Capital  -> "Flagged: Insert CP - File Form SH-7"
    Active Charges      -> "Warranties Breached: Attach CHG-4 NOC"
    Director KYC Status -> "Signatory Invalid: Rectify before EGM"

Two of those three are wrong, and the third is under-specified. This module is the
corrected engine, and the corrections are the product.

## 1. "Warranties Breached" is not a finding a register can support

A charge shown on the index may have been discharged up to three hundred days ago
and lawfully not yet reported -- s.82(1) proviso says so in terms. A warranty may
also be qualified by a disclosure letter that is not in the document set, or speak
as at a different date. The register establishes a conflict. It cannot establish a
breach, and a tool that says "breached" to an Indian M&A partner loses the account
in the first meeting.

## 2. "Signatory Invalid" is a statement of law, and it is wrong

Deactivation of a DIN for KYC default arises under the Appointment and
Qualification of Directors Rules. The office of a director becomes vacant only on
the grounds in s.167(1), which is a closed list, and deactivation is not on it --
`_test()` re-reads s.167 from our corpus and fails if the word ever appears there.
Filing capacity and office are separate questions and the tool must keep them apart.

## 3. The capital rule cannot be run on an aggregate

s.4(1)(e)(i) registers share capital together with "the division thereof into shares
of a fixed amount". Headroom is a per-class quantity; an aggregate authorised figure
cannot answer it. And premium does not consume it -- s.52 sends premium to the
securities premium account -- so only nominal counts. Against an unbounded-blind
issued figure the rule returns UNRESOLVABLE and never AGREES, because headroom
computed from a floor is not headroom.

## The invariant, enforced at construction

No `Finding` may contain a legal conclusion. The words are rejected in
`__post_init__`, not checked in review -- so the next rule someone adds cannot
reintroduce "breached" by being written carefully in prose.

Run: python3 checker/mca_reconcile.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from checker.mca_snapshot import (BOUNDED_BLIND, UNBOUNDED_BLIND, Assessment,
                                  Snapshot, assess, may_assert_absence)

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "companies_act"

# ── verdicts ─────────────────────────────────────────────────────────────────
AGREES = "AGREES"
CONFLICTS = "CONFLICTS"              # both sides stated and they differ
UNRESOLVABLE = "UNRESOLVABLE"        # the register cannot settle it either way
DOCUMENT_SILENT = "DOCUMENT_SILENT"
REGISTRY_SILENT = "REGISTRY_SILENT"
REFUSED = "REFUSED"                  # we lack an input the rule requires

# ── severity: about evidence, not about legal outcome ────────────────────────
BLOCKING = "BLOCKING"            # do not execute until a human resolves it
MATERIAL = "MATERIAL"            # a real discrepancy, resolvable
QUESTION = "QUESTION"            # we cannot tell; here is what to ask
INFORMATIONAL = "INFORMATIONAL"
_ORDER = (INFORMATIONAL, QUESTION, MATERIAL, BLOCKING)

# Rejected in Finding.__post_init__. Each is a conclusion only a lawyer reaches.
CONCLUSIONS = ("breach", "invalid", "void", "violat", "illegal", "unlawful",
               "non-compliant", "noncompliant")


class Overclaim(ValueError):
    """Raised when a finding tries to state a legal conclusion."""


@dataclass(frozen=True)
class Finding:
    field: str
    headline: str
    verdict: str
    severity: str
    document_value: str
    registry_value: str
    question: str                      # what a human must resolve
    citations: tuple[str, ...] = ()
    blindness: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in (AGREES, CONFLICTS, UNRESOLVABLE, DOCUMENT_SILENT,
                                REGISTRY_SILENT, REFUSED):
            raise ValueError(f"unknown verdict {self.verdict!r}")
        if self.severity not in _ORDER:
            raise ValueError(f"unknown severity {self.severity!r}")
        blob = f"{self.headline} {self.question}".lower()
        for word in CONCLUSIONS:
            if word in blob:
                raise Overclaim(
                    f"a reconciliation finding may not state a conclusion "
                    f"({word!r} in {self.field}). The register shows a conflict; "
                    f"whether it is one is a lawyer's call.")


@dataclass(frozen=True)
class ClassCapital:
    """One class of share capital, as the memorandum divides it (s.4(1)(e)(i))."""
    name: str                          # "equity" / "preference"
    nominal_per_share: int             # rupees
    authorised_rupees: int | None = None
    issued_rupees: int | None = None


def worst(findings: tuple[Finding, ...]) -> str:
    return max((f.severity for f in findings), key=_ORDER.index, default=INFORMATIONAL)


# ── rule 1: headroom, per class, nominal only ────────────────────────────────

def capital_headroom(*, new_shares: int, class_name: str,
                     classes: tuple[ClassCapital, ...] | None,
                     aggregate_authorised: int | None = None,
                     issued_blindness: Assessment | None = None,
                     clause_ref: str = "") -> Finding:
    """Can the proposed allotment be made inside the registered capital?"""
    doc = f"{new_shares:,} new {class_name} shares" + (f" ({clause_ref})" if clause_ref else "")

    if not classes:
        return Finding(
            "authorised_capital", "Cannot be computed from an aggregate figure",
            REFUSED, QUESTION, doc,
            f"aggregate authorised {_rs(aggregate_authorised)}" if aggregate_authorised
            else "not stated",
            "s.4(1)(e)(i) registers capital together with 'the division thereof into "
            "shares of a fixed amount'. Headroom is per class. Supply the memorandum's "
            "capital clause -- an aggregate total cannot answer this.",
            ("s.4(1)(e)(i)",))

    match = [c for c in classes if c.name == class_name]
    if not match:
        return Finding(
            "authorised_capital", f"No {class_name} class in the registered capital",
            REFUSED, QUESTION, doc,
            f"classes on record: {', '.join(c.name for c in classes)}",
            f"the memorandum on record registers no {class_name} class. Confirm the "
            f"class before pricing the allotment.", ("s.4(1)(e)(i)",))
    cls = match[0]

    if cls.authorised_rupees is None or cls.issued_rupees is None:
        return Finding(
            "authorised_capital", "The register did not carry both figures",
            REFUSED, QUESTION, doc,
            f"authorised {_rs(cls.authorised_rupees)}, issued {_rs(cls.issued_rupees)}",
            "headroom needs both the authorised and the issued nominal for the class.",
            ("s.4(1)(e)(i)",))

    needed = new_shares * cls.nominal_per_share
    headroom = cls.authorised_rupees - cls.issued_rupees
    reg = (f"{class_name}: authorised {_rs(cls.authorised_rupees)}, "
           f"issued {_rs(cls.issued_rupees)}, headroom {_rs(headroom)}")
    blind = issued_blindness.sentence() if issued_blindness else ""

    if needed > headroom:
        # Overshoot is safe to report even against a blind issued figure: the issued
        # number is a FLOOR, so the real headroom can only be smaller than this one.
        return Finding(
            "authorised_capital",
            f"The allotment needs {_rs(needed)} of nominal capital; "
            f"the register leaves {_rs(headroom)}",
            CONFLICTS, BLOCKING, doc, reg,
            "an alteration under s.64 (filed in Form SH-7) would have to precede the "
            "allotment. Confirm the headroom against the memorandum itself, not "
            "against this record. Premium does not help: s.52 sends premium to the "
            "securities premium account, so only nominal consumes capital.",
            ("s.64(1)", "s.52(1)", "s.4(1)(e)(i)"), blind)

    if issued_blindness is not None and issued_blindness.state == UNBOUNDED_BLIND:
        # The register's issued figure is a floor with no bound, so "it fits" is a
        # claim we cannot make. This is the rule refusing to be useful dishonestly.
        return Finding(
            "authorised_capital",
            f"It fits the register's headroom of {_rs(headroom)}, "
            f"which is an upper bound only",
            UNRESOLVABLE, QUESTION, doc, reg,
            "the issued figure is a floor: an allotment already made and not yet "
            "returned would reduce this headroom, and we hold no rule that bounds "
            "how long that return may take. Confirm from the register of members.",
            ("s.64(1)", "s.4(1)(e)(i)"), blind)

    return Finding("authorised_capital",
                   f"The allotment fits inside the registered headroom",
                   AGREES, INFORMATIONAL, doc, reg,
                   "no action indicated on this field.", ("s.64(1)",), blind)


# ── rule 2: an encumbrance warranty against the index of charges ─────────────

def charge_warranty(*, document_states_unencumbered: bool | None,
                    registry_charges: tuple[dict, ...] | None,
                    blindness: Assessment, clause_ref: str = "") -> Finding:
    doc = ("no encumbrance" if document_states_unencumbered
           else "encumbrance disclosed" if document_states_unencumbered is False
           else "not stated") + (f" ({clause_ref})" if clause_ref else "")

    if document_states_unencumbered is None:
        return Finding("charges", "The document makes no encumbrance statement",
                       DOCUMENT_SILENT, INFORMATIONAL, doc,
                       f"{len(registry_charges or ())} on the index",
                       "nothing to reconcile against on this field.", (),
                       blindness.sentence())

    if registry_charges is None:
        return Finding("charges", "The response carried no charge index",
                       REGISTRY_SILENT, QUESTION, doc, "absent",
                       "the provider returned no index of charges. An absent field is "
                       "not an empty one.", ("s.77(1)",), blindness.sentence())

    if registry_charges:
        holders = ", ".join(str(c.get("holder", "?")) for c in registry_charges)
        return Finding(
            "charges",
            f"The index shows {len(registry_charges)} charge(s) against a document "
            f"stating none",
            CONFLICTS, MATERIAL, doc, f"{len(registry_charges)} charge(s): {holders}",
            "three things explain this and only a person can choose between them: "
            "(a) the charge is discharged and the satisfaction is inside the "
            "three-hundred-day window s.82(1) allows; (b) the statement is qualified "
            "by a disclosure letter that is not in this document set; (c) the "
            "statement speaks as at a different date. Resolve before execution.",
            ("s.77(1)", "s.82(1)"), blindness.sentence())

    # Empty index, document says unencumbered. The spec paints this green.
    permitted, why = may_assert_absence("charges")
    assert not permitted
    return Finding(
        "charges", "The index is empty, which does not confirm the statement",
        UNRESOLVABLE, QUESTION, doc, "no charges on the index",
        f"{why}. Corroborate from the company's own register of charges (s.85) "
        f"and the lenders' no-dues position.",
        ("s.77(1)", "s.85(1)"), blindness.sentence())


# ── rule 3: DIN status -- the correction that matters most ───────────────────

def din_reliance(*, din: str, registry_status: str | None,
                 blindness: Assessment, role: str = "signatory") -> Finding:
    if registry_status is None:
        return Finding("din_status", f"No status on record for DIN {din}",
                       REGISTRY_SILENT, QUESTION, f"named as {role}", "absent",
                       "the provider returned no status for this DIN.", (),
                       blindness.sentence())

    if registry_status.upper() in ("APPROVED", "ACTIVE"):
        return Finding("din_status", f"DIN {din} is shown active",
                       AGREES, INFORMATIONAL, f"named as {role}", registry_status,
                       "no action indicated on this field.", (), blindness.sentence())

    # Deactivated / disqualified / anything else. The register states a filing-system
    # status. It does not state that the office is vacant, and we do not hold the rule
    # that governs the status, so this is a question -- never a block.
    return Finding(
        "din_status", f"DIN {din} is shown as {registry_status}",
        UNRESOLVABLE, QUESTION, f"named as {role}", registry_status,
        "this bears on whether the person can authenticate an MCA e-form. It does not "
        "by itself vacate the office of director: s.167(1) sets out when the office "
        "becomes vacant and that list does not reach the status of a DIN. Treat "
        "filing capacity and office as two questions, and confirm the current status "
        "at source -- the rule that governs deactivation is not held here.",
        ("s.167(1)", "Appointment and Qualification of Directors Rules 2014 r.12A "
                     "-- NOT HELD"),
        blindness.sentence())


def _rs(n: int | None) -> str:
    if n is None:
        return "not stated"
    if n >= 10_000_000 and n % 100_000 == 0:
        return f"Rs {n / 10_000_000:.2f} Cr"
    return f"Rs {n:,}"


def summary(findings: tuple[Finding, ...]) -> dict:
    out: dict = {"worst": worst(findings)}
    for f in findings:
        out[f.verdict] = out.get(f.verdict, 0) + 1
    return out


def _section_text(number: str) -> str:
    idx = json.loads((CORPUS / "_index.json").read_text())["entries"]
    doc = json.loads((CORPUS / f"{idx[number]['section_id']}.json").read_text())
    return " ".join(re.sub(r"<[^>]*>", " ", doc["content"]).split())


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("mca_reconcile")
    today = date(2026, 9, 12)
    snap = Snapshot("U72200KA2021PTC145892", today, "MCA21 via contracted aggregator",
                    {"charges": [], "authorised_capital": 50_000_000,
                     "paid_up_capital": 32_000_000, "din_status": {}})
    charge_blind = assess(snap, "charges", today)
    issued_blind = assess(snap, "paid_up_capital", today)
    din_blind = assess(snap, "din_status", today)

    # ── the constructor refuses conclusions ──────────────────────────────────
    try:
        Finding("charges", "Warranties breached", CONFLICTS, BLOCKING, "a", "b", "q")
        check(False, "a finding may not say 'breached'")
    except Overclaim as e:
        check("lawyer's call" in str(e), "a finding that says 'breached' is refused "
                                         "at construction, not in review")
    for word in ("The signatory is invalid", "this is non-compliant", "the clause is void"):
        try:
            Finding("x", word, CONFLICTS, MATERIAL, "a", "b", "q")
            check(False, f"refused: {word}")
        except Overclaim:
            check(True, f"a finding is refused for saying {word!r}")
    try:
        Finding("x", "ok", CONFLICTS, MATERIAL, "a", "b", "this warranty is breached")
        check(False, "the question field is guarded too")
    except Overclaim:
        check(True, "the guard covers the question text, not just the headline")

    # ── rule 1 ───────────────────────────────────────────────────────────────
    classes = (ClassCapital("equity", 10, 50_000_000, 32_000_000),)
    over = capital_headroom(new_shares=2_500_000, class_name="equity", classes=classes,
                            issued_blindness=issued_blind, clause_ref="Cl 3.2")
    check(over.verdict == CONFLICTS and over.severity == BLOCKING,
          f"an allotment needing Rs 2.5 Cr against Rs 1.8 Cr of headroom conflicts "
          f"({over.verdict}/{over.severity})")
    check("s.64(1)" in over.citations and "s.52(1)" in over.citations,
          "...citing the alteration duty and the premium rule, so nobody argues "
          "premium fills the gap")
    check("breach" not in over.question.lower(),
          "...and the remediation is a filing to make, not a conclusion drawn")

    fits = capital_headroom(new_shares=100_000, class_name="equity", classes=classes,
                            issued_blindness=issued_blind)
    check(fits.verdict == UNRESOLVABLE,
          "an allotment that fits is UNRESOLVABLE while the issued figure is "
          "unbounded-blind -- headroom from a floor is not headroom")
    bounded = Assessment(BOUNDED_BLIND, "paid_up_capital", date(2026, 8, 13))
    check(capital_headroom(new_shares=100_000, class_name="equity", classes=classes,
                           issued_blindness=bounded).verdict == AGREES,
          "...and becomes AGREES once that blindness is bounded -- which is exactly "
          "what acquiring the Allotment Rules would buy")
    check(capital_headroom(new_shares=1, class_name="equity", classes=None,
                           aggregate_authorised=50_000_000).verdict == REFUSED,
          "an aggregate authorised figure cannot answer a per-class question (s.4)")
    check(capital_headroom(new_shares=1, class_name="preference",
                           classes=classes).verdict == REFUSED,
          "...and a class the memorandum does not register is refused, not assumed")

    # ── rule 2: the green chip that should not be green ──────────────────────
    empty = charge_warranty(document_states_unencumbered=True, registry_charges=(),
                            blindness=charge_blind, clause_ref="Cl 5.1")
    check(empty.verdict == UNRESOLVABLE,
          "an empty charge index does not confirm an unencumbered warranty")
    check("s.77" in empty.question and "s.85(1)" in empty.citations,
          "...and it says what would: the company's own register of charges")

    two = charge_warranty(document_states_unencumbered=True,
                          registry_charges=({"holder": "ICICI Bank", "amount": 25_000_000},),
                          blindness=charge_blind)
    check(two.verdict == CONFLICTS and two.severity == MATERIAL,
          f"a charge on the index against a 'nil' statement is a conflict, and "
          f"MATERIAL rather than BLOCKING ({two.severity})")
    check("three-hundred-day" in two.question and "disclosure letter" in two.question,
          "...and it names the satisfaction window and the disclosure letter, the "
          "two innocent explanations the spec's 'breached' cell erases")
    check(charge_warranty(document_states_unencumbered=None, registry_charges=(),
                          blindness=charge_blind).verdict == DOCUMENT_SILENT,
          "a document that says nothing about encumbrance is not reconciled against")
    check(charge_warranty(document_states_unencumbered=True, registry_charges=None,
                          blindness=charge_blind).verdict == REGISTRY_SILENT,
          "an absent charge index is REGISTRY_SILENT, not an empty one")

    # ── rule 3: the statement of law the spec gets wrong ─────────────────────
    s167 = _section_text("167")
    check("the office of a director shall become vacant" in s167.lower(),
          "s.167(1) is the provision that vacates the office (read from our corpus)")
    check("deactivat" not in s167.lower() and "kyc" not in s167.lower(),
          "...and nothing in it reaches the deactivation of a DIN -- which is why "
          "'Signatory Invalid' is a statement this data cannot support")
    d = din_reliance(din="08412345", registry_status="DEACTIVATED", blindness=din_blind)
    check(d.severity == QUESTION and d.verdict == UNRESOLVABLE,
          f"a deactivated DIN is a question, never a block ({d.severity})")
    check("s.167(1)" in d.citations and "NOT HELD" in " ".join(d.citations),
          "...citing the closed list, and admitting the governing rule is not held")
    check("authenticate an MCA e-form" in d.question,
          "...and separating filing capacity from office, which is the actual effect")
    check(din_reliance(din="1", registry_status="APPROVED",
                       blindness=din_blind).verdict == AGREES,
          "an active DIN reconciles quietly")

    # ── the aggregate ────────────────────────────────────────────────────────
    s = summary((over, empty, two, d))
    check(s["worst"] == BLOCKING and s[UNRESOLVABLE] == 2,
          f"the strip's aggregate is the worst finding, not a count of green ({s})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
