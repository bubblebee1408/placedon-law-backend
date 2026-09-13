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


def _flat(s: str) -> str:
    return re.sub(r"[^a-z ]+", " ", (s or "").lower())


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
    if field not in _NAMES:
        # Only the mutually-exclusive money fields are checked. A date or a class
        # has no sibling it could be confused with in this way.
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

    # ── fields with no sibling are not checked at all ────────────────────────
    for f in ("document_date", "company_class", "director_count", "cin"):
        c(check(f, "anything at all").verdict == UNNAMED,
          f"{f} is not subject to this check -- it has no sibling it could be "
          f"confused with")

    # ── every money field is covered, or the check has a silent hole ─────────
    c(set(_NAMES) == set(MONEY_FIELDS),
      f"every money field has identifying terms ({len(_NAMES)}/{len(MONEY_FIELDS)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
