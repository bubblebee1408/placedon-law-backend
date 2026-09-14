"""Does the quoted span describe the field it was filed under?

The leak that closed on 14-09-2026 -- a span present in the document but not
supporting its value -- immediately exposed the next one, because `shadow.py`'s
replacement test is exactly it: a quantity whose span is real, whose value is
genuinely what that span states, and whose FIELD is wrong.

    {"paid_up_capital_rupees": {"value": 150000000,
                                "span": "turnover of Rs 15,00,00,000"}}

Every existing gate passes this. The span is in the document. The span states
Rs 15,00,00,000 and the value is 150000000. Only the binding is wrong -- and on a
flattened PDF table, where four figures sit under four labels that the extraction
has separated from them, this is the ordinary failure rather than the exotic one.

## The rule: silence is not contradiction

This refuses ONLY when the span positively names a DIFFERENT field and does not
name the claimed one. A span that names nothing is not refused, because a caller
quoting a bare figure from a table has not done anything wrong -- the label is
simply somewhere else, and refusing it would convert a formatting accident into a
compliance failure.

That asymmetry is the whole design. Every session this week has produced at least
one false positive that sent someone to fix work that was already right, and a
binding checker is the easiest place in this repository to build another.

## Widened to text and date fields, 14-09-2026 -- on evidence, not imagination

Text and date fields were exempt: a date or a class was said to have no sibling
it could be confused with. That was declined for widening on 13-09 because the
failure had never been observed. `eval/realrun/text_field_probe.py` then observed
it: llama3 filed five text facts under spans naming a different field, and one
(an empty CIN) served. Replaying every stored probe run through this widening
newly refuses 0 of the 33 facts gpt-5-mini and Llama-3.3-70B served.

Same asymmetry, whole-word terms, and checked within the text family only.

**What it does not catch, stated so nobody assumes it does:** a wrong value
quoted with the claimed field's OWN term. T05's previous-meeting date filed as
document_date quotes "held on" -- document_date's term -- and binds. Binding
cannot see that; comparing a served document_date with the declared one can.

## Why this is not entail_binding

`entail_binding.judge()` asks whether a CLAIM's quantity-to-obligation pairing is
one a statutory SOURCE makes -- narration against law. This asks whether an
extracted field's span describes that field. Same family of error, different
inputs, and forcing one to serve both would blur a checker that is currently
precise.

Run: python3 checker/field_binding.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.document_extract import MONEY_FIELDS

# ── verdicts ─────────────────────────────────────────────────────────────────
BOUND = "BOUND"                  # the span names this field
UNNAMED = "UNNAMED"              # the span names no field. NOT a refusal.
MISBOUND = "MISBOUND"            # the span names a DIFFERENT field. Refused.

# Terms that identify a field, as Indian corporate documents actually write them.
# Only fields that are mutually exclusive appear here: two figures that could
# legitimately be the same number must never be compared this way.
_NAMES: dict[str, tuple[str, ...]] = {
    "paid_up_capital_rupees": ("paid-up", "paid up", "paidup", "subscribed"),
    "turnover_rupees": ("turnover", "revenue from operations", "gross receipts"),
    "net_worth_rupees": ("net worth", "networth"),
    "net_profit_rupees": ("net profit", "profit after tax", "profit for the year"),
}

# Named in documents, never extracted, and the single most common mis-binding:
# the authorised figure sits directly above the paid-up figure in every capital
# table ever drafted, and it is always the larger number.
_NOT_A_FIELD: dict[str, tuple[str, ...]] = {
    "authorised capital": ("authorised", "authorized"),
    "called-up capital": ("called-up", "called up"),
}


# Text and date fields, widened 14-09-2026 -- see the module docstring. Checked
# within their own family only: a class span that happens to mention capital is
# not evidence of a text binding error.
_TEXT_NAMES: dict[str, tuple[str, ...]] = {
    "document_date": ("dated", "date of this", "passed on", "held on",
                      "this resolution"),
    "incorporation_date": ("incorporated on", "date of incorporation",
                           "incorporation", "certificate of incorporation"),
    "financial_year": ("financial year", "f y", "fy", "year ended",
                       "year ending", "for the year"),
    "company_class": ("private limited", "public limited", "small company",
                      "one person company", "private company", "public company"),
    "cin": ("cin", "corporate identity number"),
}
_TEXT_NOT_A_FIELD: dict[str, tuple[str, ...]] = {
    "registration number": ("registration no", "registration number", "gstin",
                            "pan", "tan"),
    "meeting date": ("previous meeting", "last meeting", "adjourned meeting"),
}


def _flat(s: str) -> str:
    return re.sub(r"[^a-z ]+", " ", (s or "").lower())


def _words(s: str) -> str:
    """Whole words, space-padded. A short term like 'pan' or 'cin' must never
    match inside a longer word -- 'pan' inside 'company' is how the realrun probe
    once scored a correct span as a misbinding."""
    return " " + " ".join(re.findall(r"[a-z0-9]+", (s or "").lower())) + " "


def _check_text(field: str, span: str) -> BindingCheck:
    text = _words(span)
    own = tuple(t for t in _TEXT_NAMES[field] if _words(t) in text)
    if own:
        return BindingCheck(BOUND, field, own, f"the span names {field}")
    others = [f"{other}:{t}" for other, terms in _TEXT_NAMES.items()
              if other != field for t in terms if _words(t) in text]
    others += [f"{label}:{t}" for label, terms in _TEXT_NOT_A_FIELD.items()
               for t in terms if _words(t) in text]
    if others:
        return BindingCheck(MISBOUND, field, tuple(others),
                            f"the span names {others[0].split(':')[0]}, not {field}")
    return BindingCheck(UNNAMED, field,
                        detail="the span names no field; a bare value quoted from "
                               "a table is not a binding error")


@dataclass(frozen=True)
class BindingCheck:
    verdict: str
    field: str
    names_found: tuple[str, ...] = ()
    detail: str = ""

    @property
    def refused(self) -> bool:
        return self.verdict == MISBOUND


def check(field: str, span: str) -> BindingCheck:
    """Does `span` describe `field`, describe another field, or say nothing?"""
    if field in _TEXT_NAMES:
        return _check_text(field, span)
    if field not in _NAMES:
        # director_count has no sibling it could be confused with.
        return BindingCheck(UNNAMED, field, detail="field not subject to this check")

    text = _flat(span)
    own = tuple(t for t in _NAMES[field] if _flat(t) in text)
    if own:
        return BindingCheck(BOUND, field, own,
                            f"the span names {field.replace('_rupees', '')}")

    others: list[str] = []
    for other, terms in _NAMES.items():
        if other == field:
            continue
        others += [f"{other}:{t}" for t in terms if _flat(t) in text]
    for label, terms in _NOT_A_FIELD.items():
        others += [f"{label}:{t}" for t in terms if _flat(t) in text]

    if others:
        return BindingCheck(
            MISBOUND, field, tuple(others),
            f"the span names {others[0].split(':')[0]}, not "
            f"{field.replace('_rupees', '')}")

    # Names nothing. Not refused -- see the module docstring.
    return BindingCheck(UNNAMED, field,
                        detail="the span names no field; a bare figure quoted "
                               "from a table is not a binding error")


def _test() -> None:
    ok = fail = 0

    def c(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("field_binding")

    # ── the leak this exists for ─────────────────────────────────────────────
    r = check("paid_up_capital_rupees", "turnover of Rs 15,00,00,000")
    c(r.verdict == MISBOUND and r.refused,
      f"a turnover span filed as paid-up capital is MISBOUND ({r.verdict})")
    c("turnover" in r.detail, f"...and the detail names what it actually is: "
                              f"{r.detail}")

    # ── the mis-binding that happens most ────────────────────────────────────
    r = check("paid_up_capital_rupees", "Authorised share capital Rs 10,00,00,000")
    c(r.verdict == MISBOUND,
      "the AUTHORISED figure filed as paid-up is MISBOUND -- it sits directly "
      "above paid-up in every capital table and is always the larger number")

    # ── correct bindings, in the forms documents actually use ────────────────
    for span in ("paid-up share capital of Rs 4,00,00,000",
                 "the paid up share capital is Rs. 6,00,00,000",
                 "subscribed capital Rs 4,00,00,000"):
        c(check("paid_up_capital_rupees", span).verdict == BOUND,
          f"...and a correct paid-up span binds: {span[:40]!r}")
    c(check("turnover_rupees", "turnover of Rs 15,00,00,000").verdict == BOUND,
      "a turnover span filed as turnover binds")
    c(check("net_profit_rupees", "profit after tax of Rs 2,00,00,000").verdict
      == BOUND, "profit after tax binds to net profit")

    # ── the asymmetry that keeps false refusals out ──────────────────────────
    r = check("paid_up_capital_rupees", "4,00,00,000")
    c(r.verdict == UNNAMED and not r.refused,
      "a bare figure from a flattened table is NOT refused -- the label is "
      "elsewhere, and refusing it would turn a formatting accident into a "
      "compliance failure")
    c("not a binding error" in r.detail, "...and the reason says so explicitly")
    c(check("paid_up_capital_rupees", "Rs 4,00,00,000 as at 31 March 2025"
            ).verdict == UNNAMED,
      "a figure with a date and no label is also not refused")

    # ── a span naming BOTH is bound, not refused ─────────────────────────────
    c(check("paid_up_capital_rupees",
            "paid-up capital Rs 4,00,00,000 against turnover Rs 15,00,00,000"
            ).verdict == BOUND,
      "a span naming the claimed field AND another is BOUND -- the claimed name "
      "is present, so the quote supports the filing")

    # ── text and date fields: widened on evidence, 14-09-2026 ────────────────
    # These were exempt ("no sibling it could be confused with"). llama3 via
    # eval/realrun/text_field_probe.py filed text facts under spans that name a
    # different field, and one served. Replaying every stored probe run, this
    # widening newly refuses 0 of 33 facts the stronger models served.
    r = check("company_class", "The Company was incorporated on 01 April 2015 "
                               "under the Companies Act, 2013.")
    c(r.refused and "incorporation" in r.detail,
      f"llama3 T01: a class filed from the incorporation sentence is MISBOUND "
      f"({r.verdict}: {r.detail})")
    c(check("financial_year", "incorporated on 2015-04-01").refused,
      "shadow.py's hand-written leak -- a financial year quoted from the "
      "incorporation date -- is now refused")
    c(check("cin", "Its holding company, ACME HOLDINGS PUBLIC LIMITED, is a "
                   "public limited company.").refused,
      "llama3 T04: a CIN filed from a sentence naming only a company class is "
      "MISBOUND")

    # ...and the asymmetry holds for them exactly as for money
    for field, span in (
            ("company_class", "The Company is a private limited company and a "
                              "small company within the meaning of section 2(85)."),
            ("cin", "CIN U74999KA2019PTC123456, Registration No. 123456 of 2019,"),
            ("incorporation_date", "The Company was incorporated on 01 April 2015."),
            ("financial_year", "for the financial year 2023-24"),
            ("document_date", "BOARD RESOLUTION dated 14 June 2024.")):
        c(check(field, span).verdict == BOUND,
          f"a correct {field} span still binds: {span[:44]!r}")
    for field, span in (("company_class", "Private Limited"),
                        ("financial_year", "2023-24"),
                        ("cin", "U74999KA2019PTC123456")):
        c(not check(field, span).refused,
          f"a bare {field} value from a flattened table is not refused: {span!r}")
    c(check("company_class", "Class of company").verdict == UNNAMED,
      "terms match whole words: 'Class of company' does not name a PAN -- the "
      "probe scored exactly that as a misbinding before its matcher was fixed")

    # ...and what it does NOT catch is stated, not hidden
    r = check("document_date", "the previous meeting held on 12 March 2024")
    c(r.verdict == BOUND,
      "KNOWN GAP: T05's previous-meeting date filed as document_date BINDS -- "
      "its span says 'held on', which is document_date's own term. Binding "
      "cannot see it; comparing the date to the declared document date can")
    c(check("director_count", "anything at all").verdict == UNNAMED,
      "director_count has no sibling and stays outside this check")

    # ── every money field is covered, or the check has a silent hole ─────────
    c(set(_NAMES) == set(MONEY_FIELDS),
      f"every money field has identifying terms ({len(_NAMES)}/{len(MONEY_FIELDS)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
