#!/usr/bin/env python3
"""The firm's company profile: confirmed company facts, entered once and reused.

Design: docs/architecture/COMPANY_PROFILE.md. Storage: gateway/migrations/032_company_profile.sql.

The vocabulary is `checker/sources/company_facts.FIELDS` (and its rules: no director data,
a document fact quotes its line, a typed fact quotes nothing), plus one field the calendar
cannot proceed without, `company_class`. Only CONFIRMED facts are stored: the profile is
what a person said yes to, never what a parser proposed.

Run: PYTHONPATH=. python3 gateway/company_profile.py --test
"""
from __future__ import annotations

import re

from checker.sources import company_facts as cf

COMPANY_CLASS = "company_class"
# checker/company_profile.CompanyClass. Typed only: the MCA extractor does not read it.
CLASSES = ("private", "public", "opc")
FIELDS = cf.FIELDS + (COMPANY_CLASS,)

_MCA_LABEL = re.compile(r"MCA master data, as uploaded by the user on (\d{4}-\d{2}-\d{2})")


def parse(raw: object) -> tuple[list[dict], str | None]:
    """(rows to store, the reason they cannot be) from `company_profile.set`'s `facts`.

    All or nothing: one bad fact refuses the set, because a profile saved minus the fact
    the person typed wrong would be read later as the whole profile.
    """
    if not isinstance(raw, list):
        return [], "facts must be a list of objects"
    rows: list[dict] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], f"facts[{i}] must be an object"
        if item.get("confirmed") is not True:
            return [], (f"facts[{i}] is not confirmed. Only a fact a person has confirmed "
                        f"is stored in the company profile")
        field = str(item.get("field") or "")
        if field in seen:
            return [], f"facts[{i}]: {field!r} given twice"
        seen.add(field)
        row, err = _row(field, item)
        if err:
            return [], f"facts[{i}]: {err}"
        rows.append(row)
    return rows, None


def _row(field: str, item: dict) -> tuple[dict, str | None]:
    basis = item.get("basis") or cf.USER_FACT
    if field == COMPANY_CLASS:
        value = str(item.get("value") or "").strip().lower()
        if basis != cf.USER_FACT or value not in CLASSES:
            return {}, f"company_class is typed by a person and is one of {CLASSES}"
        return _shape(field, value, cf.USER_FACT, cf.YOU_TOLD_US, "", None), None
    try:
        if basis == cf.USER_FACT:
            fact = cf.user_fact(field, item.get("value"))
            return _shape(field, fact.value, fact.basis, fact.label, "", None), None
        fact = cf.CompanyFact(field=field, value=str(item.get("value") or "").strip(),
                              basis=basis, quoted_span=str(item.get("quoted_span") or ""),
                              source_label=str(item.get("source_label") or ""))
    except cf.FactError as e:
        return {}, str(e)
    m = _MCA_LABEL.fullmatch(fact.source_label)
    if not m:
        return {}, ("a document fact must carry the label company_facts.extract gave it, "
                    "with the date the page was uploaded")
    return _shape(field, fact.value, fact.basis, fact.source_label, fact.quoted_span,
                  m.group(1)), None


def _shape(field, value, basis, label, span, uploaded_on) -> dict:
    return {"field": field, "value": value, "basis": basis, "source_label": label,
            "quoted_span": span, "uploaded_on": uploaded_on}


def same_fact(a: dict, b: dict) -> bool:
    """Unchanged facts keep their row, and with it who confirmed them and when."""
    keys = ("field", "value", "basis", "source_label", "quoted_span")
    return all(str(a.get(k) or "") == str(b.get(k) or "") for k in keys)


def as_company_facts(rows: list[dict]) -> list:
    """The stored rows `ask` and `events.assess` read, as confirmed CompanyFacts.
    company_class is not in that vocabulary and is left to the calendar."""
    return [cf.CompanyFact(field=r["field"], value=r["value"], basis=r["basis"],
                           quoted_span=r.get("quoted_span") or "",
                           source_label=r["source_label"], confirmed=True)
            for r in rows if r["field"] in cf.FIELDS]


def public(row: dict) -> dict:
    """A stored row as `company_profile.get` serves it: the fact and its provenance."""
    return {"field": row["field"], "value": row["value"], "basis": row["basis"],
            "label": row["source_label"], "quoted_span": row.get("quoted_span") or "",
            "uploaded_on": _iso(row.get("uploaded_on")), "confirmed": True,
            "can_verify": False, "confirmed_by": str(row.get("confirmed_by") or ""),
            "confirmed_at": _iso(row.get("confirmed_at"))}


def _iso(v) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")

    print("gateway.company_profile")
    label = "MCA master data, as uploaded by the user on 2026-10-01"
    good = [{"field": "listed", "value": "yes", "confirmed": True},
            {"field": "company_class", "value": "Private", "confirmed": True},
            {"field": "state", "value": "Maharashtra", "basis": "COMPANY_FACT",
             "quoted_span": "Registered Address: 5 Fort, Mumbai, Maharashtra",
             "source_label": label, "confirmed": True}]
    rows, err = parse(good)
    check(err is None and len(rows) == 3, f"three confirmed facts parse ({err})")
    check(rows[1]["value"] == "private", "company_class is normalised")
    check(rows[2]["uploaded_on"] == "2026-10-01", "uploaded_on is read from the MCA label")
    check(rows[0]["source_label"] == cf.YOU_TOLD_US and rows[0]["uploaded_on"] is None,
          "a typed fact is 'you told us' with no upload date")
    for bad, why in ((dict(good[0], confirmed=False), "unconfirmed"),
                     ({"field": "director_name", "value": "X", "confirmed": True}, "personal data"),
                     ({"field": "company_class", "value": "section8", "confirmed": True}, "class"),
                     (dict(good[2], source_label="my notes"), "label"),
                     (dict(good[2], quoted_span=""), "span"),
                     ({"field": "address", "value": "5 Fort", "confirmed": True}, "untypeable")):
        check(parse([bad])[1] is not None, f"refused: {why}")
    check(parse([good[0], good[0]])[1] is not None, "a field given twice is refused")
    check(parse("x")[1] is not None and parse([])[1] is None, "shape: list required, empty ok")
    facts = as_company_facts(rows)
    check([f.field for f in facts] == ["listed", "state"] and all(f.confirmed for f in facts),
          "as_company_facts drops company_class and returns confirmed facts")
    check(same_fact(rows[0], dict(rows[0], confirmed_by="x"))
          and not same_fact(rows[0], dict(rows[0], value="no")), "same_fact compares the fact")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
