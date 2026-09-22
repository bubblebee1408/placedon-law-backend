"""Two models read the same document. This decides where they disagree.

The founder's cheap substitute for a legal expert: where two independently-run
models, each of whose values has already survived the repository's own
value-support and field-binding gates, still say different things, a person looks.

## What agreement is NOT

Agreement between two models is **not evidence of correctness**. Two models can be
wrong in the same way -- they read the same sentence, they share training data,
and Indian digit grouping ("Rs. 4,00,00,000") has already produced the same 10x
misreading in this repository more than once. This module therefore labels an
agreement `model-verified, NOT expert-verified` and nothing stronger, and the
label is a string constant so it cannot drift into something stronger by accident.

Expert review is still required; the open task is `research/TASKS.md` H-001.

## What the gates have already done before a value reaches here

`checker.reasoning.review()` has dropped any value that

  * quoted no span                       FACT_WITHOUT_SPAN
  * quoted a span not in the document    FACT_NOT_GROUNDED
  * quoted a span that does not yield it FACT_VALUE_UNSUPPORTED
  * quoted a span naming another field   FACT_MISBOUND

A dropped value is **dropped, never repaired**. So this module compares admitted
values only, and treats "the model proposed it and the gate refused it" as a
distinct state from "the model never proposed it" -- because they are different
facts about the model, and collapsing them would hide which one happened.

## The four outcomes

    AGREE        both admitted, same value          -> model-verified, not expert-verified
    DISAGREE     both admitted, different values    -> a row for the founder
    ONE_SIDED    exactly one admitted               -> a row for the founder
    NEITHER      neither admitted                   -> counted, no row

A document where either model failed to answer at all produces **no rows**. A
one-sided row means "one model supported this and the other did not", and that
sentence is false when the other model never ran. Those documents are listed
separately, by name and reason.

Run: python3 eval/prelabel/compare.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from checker.document_extract import (DATE_FIELDS, INT_FIELDS, KNOWN_FIELDS,
                                      MONEY_FIELDS)

# The only label an agreement may carry. A constant, so no caller can quietly
# write a stronger one.
AGREEMENT_LABEL = "model-verified, NOT expert-verified"

AGREE = "AGREE"
DISAGREE = "DISAGREE"
ONE_SIDED = "ONE_SIDED"
NEITHER = "NEITHER"

# States a single model can be in for one field.
ADMITTED = "ADMITTED"        # proposed, and every gate passed
REFUSED = "REFUSED"          # proposed, and a gate dropped it
ABSENT = "ABSENT"            # never proposed


# ── priority: how likely is this field to change an obligation row ────────────
# Rank 1 decides an obligation directly. Rank 2 decides WHICH period or deadline
# the rank-1 figures are tested against. Rank 3 decides which company it is,
# which matters and is not itself a threshold.
#
# Each reason names the code that consumes the field, so the ordering is checkable
# rather than asserted.
FIELD_PRIORITY: dict[str, tuple[int, str]] = {
    "net_worth_rupees":       (1, "s.135(1) CSR threshold — obligations._CSR_TESTS"),
    "turnover_rupees":        (1, "s.135(1) CSR threshold and s.2(85) small company "
                                  "— obligations._CSR_TESTS, classify.small_company"),
    "net_profit_rupees":      (1, "s.135(1) CSR threshold — obligations._CSR_TESTS"),
    "paid_up_capital_rupees": (1, "s.2(85) small company and the Board Powers Rules "
                                  "— classify.small_company"),
    "company_class":          (1, "gates s.2(85) outright: a public company is never "
                                  "small — classify.small_company"),
    "director_count":         (1, "s.149(3) / OPC board-size rows — obligations"),
    "financial_year":         (2, "chooses WHICH year's figures a threshold is "
                                  "tested against — company_profile.amount_for "
                                  "refuses a year mismatch"),
    "document_date":          (2, "the as-of date: which text of the law applies, "
                                  "and every deadline counted from the document"),
    "incorporation_date":     (2, "s.96(1) first-AGM proviso and the s.149(3) "
                                  "first-year proviso"),
    "cin":                    (3, "identity of the company. Decides no threshold; "
                                  "decides which company the thresholds are about"),
}

# DISAGREE before ONE_SIDED at the same priority: two models asserting different
# values is a contradiction on the page, and one model asserting where the other
# was silent is a gap. A contradiction is the faster thing for a person to settle.
_OUTCOME_ORDER = {DISAGREE: 0, ONE_SIDED: 1}


@dataclass(frozen=True)
class Side:
    """What one model ended up with for one field."""
    state: str                       # ADMITTED | REFUSED | ABSENT
    value: object = None
    span: str = ""
    refusal: str = ""                # the violation name, when state is REFUSED


@dataclass(frozen=True)
class Row:
    document: str
    field: str
    outcome: str
    a: Side
    b: Side
    priority: int
    priority_reason: str
    anchor_span: str = ""            # the span the founder should look at
    verdict: str = ""                # deliberately blank: a person fills this in


@dataclass(frozen=True)
class Comparison:
    """Every field of one document, compared. Agreements and rows, never one alone."""
    document: str
    agreements: tuple[Row, ...] = ()
    rows: tuple[Row, ...] = ()
    neither: tuple[str, ...] = ()
    label: str = AGREEMENT_LABEL


# ── value normalisation ───────────────────────────────────────────────────────
def normalise(name: str, value: object) -> object:
    """One comparable form per field kind. Applied to BOTH sides identically.

    This is not a repair. It never changes what is reported to the founder -- the
    raw values from each model are what the row carries. It only decides whether
    two values are the same value written two ways.
    """
    if value is None:
        return None
    if name in MONEY_FIELDS or name in INT_FIELDS:
        digits = re.sub(r"[^0-9-]", "", str(value))
        return int(digits) if digits not in ("", "-") else None
    if name in DATE_FIELDS:
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(str(value).strip()).isoformat()
        except (ValueError, TypeError):
            return " ".join(str(value).split()).casefold()
    return " ".join(str(value).split()).casefold().rstrip(".")


def _has_value(normalised: object) -> bool:
    """An empty value is not a value.

    Caught by this module's own tests: two models both returning `""` normalise to
    the same thing, and `==` called that an agreement. Two absences of a value are
    not agreement about a value. The gate already refuses an empty text value
    (`document_extract`: "no span can support it"), so this cannot arrive from the
    live path today -- which is exactly why the comparison must not depend on that
    staying true.
    """
    return normalised is not None and str(normalised).strip() != ""


def compare_field(name: str, a: Side, b: Side) -> str:
    """The outcome for one field. No side effects, no I/O."""
    if a.state == ADMITTED and b.state == ADMITTED:
        na, nb = normalise(name, a.value), normalise(name, b.value)
        return AGREE if na == nb and _has_value(na) else DISAGREE
    if a.state == ADMITTED or b.state == ADMITTED:
        return ONE_SIDED
    return NEITHER


def compare_document(document: str, a_sides: dict, b_sides: dict) -> Comparison:
    """Compare two models' admitted facts for one document.

    `a_sides` / `b_sides` map field name -> Side. A field missing from either map
    is ABSENT: a model that said nothing about a field said nothing about it.
    """
    agreements: list[Row] = []
    rows: list[Row] = []
    neither: list[str] = []

    for name in KNOWN_FIELDS:
        a = a_sides.get(name) or Side(ABSENT)
        b = b_sides.get(name) or Side(ABSENT)
        outcome = compare_field(name, a, b)
        if outcome == NEITHER:
            neither.append(name)
            continue
        rank, reason = FIELD_PRIORITY.get(name, (9, "not a declared obligation input"))
        row = Row(document=document, field=name, outcome=outcome, a=a, b=b,
                  priority=rank, priority_reason=reason,
                  anchor_span=(a.span if a.state == ADMITTED else b.span))
        (agreements if outcome == AGREE else rows).append(row)

    return Comparison(document=document, agreements=tuple(agreements),
                      rows=tuple(rows), neither=tuple(neither))


def order(rows) -> tuple[Row, ...]:
    """Most likely to matter first: priority, then contradiction before gap."""
    return tuple(sorted(
        rows, key=lambda r: (r.priority, _OUTCOME_ORDER.get(r.outcome, 9),
                             r.document, r.field)))


def cut_to_budget(rows, budget: int) -> tuple[tuple[Row, ...], tuple[Row, ...]]:
    """(kept, cut). Cut strictly by priority order, so the cut is recordable.

    A review list longer than the hour it was asked for is not a shorter list; it
    is the same list with the end quietly unread. Cutting it explicitly means the
    founder is told what was dropped instead of discovering it.
    """
    ranked = order(rows)
    if budget < 0:
        raise ValueError("a negative review budget is not a budget")
    return ranked[:budget], ranked[budget:]


def cut_summary(cut) -> dict:
    """What was dropped, by field and by outcome. Never just a count."""
    by_field: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    for r in cut:
        by_field[r.field] = by_field.get(r.field, 0) + 1
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
    return {"cut_total": len(tuple(cut)), "by_field": by_field,
            "by_outcome": by_outcome}


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("prelabel.compare")

    adm = lambda v, s="": Side(ADMITTED, v, s)          # noqa: E731

    # ── the four outcomes ─────────────────────────────────────────────────────
    check(compare_field("turnover_rupees", adm(100), adm(100)) == AGREE,
          "both admitted, same value -> AGREE")
    check(compare_field("turnover_rupees", adm(100), adm(200)) == DISAGREE,
          "both admitted, different values -> DISAGREE")
    check(compare_field("turnover_rupees", adm(100), Side(ABSENT)) == ONE_SIDED,
          "one admitted, other silent -> ONE_SIDED")
    check(compare_field("turnover_rupees", adm(100),
                        Side(REFUSED, 200, "x", "FACT_VALUE_UNSUPPORTED")) == ONE_SIDED,
          "one admitted, other's value refused by the gate -> ONE_SIDED")
    check(compare_field("turnover_rupees", Side(ABSENT),
                        Side(REFUSED, 1, "x", "FACT_MISBOUND")) == NEITHER,
          "nothing admitted -> NEITHER, and no row")

    # A refused value is NOT a proposal the founder must adjudicate as a value.
    # It is dropped. What the founder sees is that the other model stood alone.
    c = compare_document("d", {"cin": adm("U74999KA2019PTC123456")},
                         {"cin": Side(REFUSED, "Acme Ltd", "Acme Ltd",
                                      "FACT_VALUE_UNSUPPORTED")})
    check(len(c.rows) == 1 and c.rows[0].outcome == ONE_SIDED
          and c.rows[0].b.state == REFUSED
          and c.rows[0].b.refusal == "FACT_VALUE_UNSUPPORTED",
          "a gate-refused value is dropped but its refusal is still named in the row")

    # ── normalisation is symmetric and does not invent agreement ──────────────
    check(compare_field("paid_up_capital_rupees", adm("40000000"), adm(40000000))
          == AGREE, "'40000000' and 40000000 are the same rupee figure")
    check(compare_field("paid_up_capital_rupees", adm(40000000), adm(400000000))
          == DISAGREE,
          "the 10x Indian-digit-grouping misreading stays a DISAGREE")
    check(compare_field("document_date", adm("2025-07-22"), adm(date(2025, 7, 22)))
          == AGREE, "an ISO string and a date object are the same date")
    check(compare_field("company_class", adm("Public"), adm("public")) == AGREE,
          "company_class compares case-insensitively")
    check(compare_field("financial_year", adm("2024-25"), adm("2024-2025"))
          == DISAGREE,
          "'2024-25' and '2024-2025' are NOT silently merged — a year is a value")
    check(compare_field("cin", adm(""), adm("")) == DISAGREE,
          "two empty values are not an agreement")
    check(normalise("turnover_rupees", "not a number") is None,
          "a money value with no digits normalises to None, never to 0")
    check(compare_field("turnover_rupees", adm("n/a"), adm("none")) == DISAGREE,
          "two unparseable money values do not agree with each other")

    # ── the agreement label cannot be strengthened ────────────────────────────
    c = compare_document("d", {"cin": adm("U74999KA2019PTC123456")},
                         {"cin": adm("U74999KA2019PTC123456")})
    check(c.label == AGREEMENT_LABEL and "NOT expert-verified" in c.label,
          "an agreement is labelled model-verified, NOT expert-verified")
    check(len(c.agreements) == 1 and not c.rows,
          "an agreement produces no founder row")
    check("accurate" not in AGREEMENT_LABEL.lower()
          and "correct" not in AGREEMENT_LABEL.lower()
          and "verified by" not in AGREEMENT_LABEL.lower(),
          "the label claims no accuracy")

    # ── ordering: obligation inputs first ─────────────────────────────────────
    rows = [
        Row("d", "cin", ONE_SIDED, adm("x"), Side(ABSENT), 3, ""),
        Row("d", "document_date", DISAGREE, adm("a"), adm("b"), 2, ""),
        Row("d", "turnover_rupees", ONE_SIDED, adm(1), Side(ABSENT), 1, ""),
        Row("d", "net_worth_rupees", DISAGREE, adm(1), adm(2), 1, ""),
    ]
    got = [r.field for r in order(rows)]
    check(got[:2] == ["net_worth_rupees", "turnover_rupees"],
          f"obligation-threshold fields sort first ({got})")
    check(got == ["net_worth_rupees", "turnover_rupees", "document_date", "cin"],
          f"at equal priority a contradiction sorts before a gap ({got})")
    check(all(f in FIELD_PRIORITY for f in KNOWN_FIELDS),
          "every declared field has a priority and a stated reason")
    check(all(FIELD_PRIORITY[f][1] for f in KNOWN_FIELDS),
          "no priority is asserted without naming what consumes the field")

    # ── the budget cut is explicit and recorded ───────────────────────────────
    kept, cut = cut_to_budget(rows, 2)
    check([r.field for r in kept] == ["net_worth_rupees", "turnover_rupees"],
          "the cut keeps the highest-priority rows")
    check(len(cut) == 2 and cut_summary(cut)["cut_total"] == 2
          and cut_summary(cut)["by_field"] == {"document_date": 1, "cin": 1},
          "what was cut is reported by field, not as a bare count")
    kept, cut = cut_to_budget(rows, 99)
    check(len(kept) == 4 and not cut, "a budget larger than the list cuts nothing")
    try:
        cut_to_budget(rows, -1)
        check(False, "a negative budget is refused")
    except ValueError:
        check(True, "a negative budget is refused")

    # ── a blank verdict column, because an agent must never self-attest ───────
    check(all(r.verdict == "" for r in order(rows)),
          "every row's verdict is blank — no agent writes a human's verdict")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
