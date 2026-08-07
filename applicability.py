"""
Applicability expression evaluator.

Pure function, no I/O, no eval(). This is the component that decides whether a
legal provision applies to a company — NEVER the LLM.

Run: python applicability.py   (executes the built-in test cases)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Literal


class Result(str, Enum):
    APPLIES = "APPLIES"
    DOES_NOT_APPLY = "DOES_NOT_APPLY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class CompanyProfile:
    """Aggregate-only by design. No employee-level PII — keeps DPDP exposure low."""
    state: str                                   # 'IN-KA'
    employee_count: int
    establishment_type: Literal["shop_or_commercial", "factory", "it_ites", "other"]
    entity_type: Literal["pvt_ltd", "llp", "partnership", "proprietorship", "opc"]
    as_of: date
    contractor_count: int = 0
    has_women_employees: bool = True
    employees_below_wage_ceiling: int | None = None   # ESI: monthly wage <= ceiling
    wage_bill_monthly: int | None = None
    has_hazardous_process: bool = False
    districts: list[str] = field(default_factory=list)

    def get(self, name: str) -> Any:
        return getattr(self, name, None)


@dataclass
class Trace:
    """Why the evaluator decided what it decided. Shown to the user verbatim."""
    node: str
    result: Result
    detail: str
    children: list["Trace"] = field(default_factory=list)

    def render(self, indent: int = 0) -> str:
        pad = "  " * indent
        out = f"{pad}{self.result.value:18} {self.detail}\n"
        for c in self.children:
            out += c.render(indent + 1)
        return out


_COMPARATORS = {
    "eq":  lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt":  lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt":  lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def evaluate(expr: dict, profile: CompanyProfile) -> tuple[Result, Trace]:
    """Evaluate an applicability expression against a company profile."""
    op = expr.get("op")

    # ---------- boolean combinators ----------
    if op in ("and", "or"):
        child_results = [evaluate(a, profile) for a in expr["args"]]
        results = [r for r, _ in child_results]
        traces = [t for _, t in child_results]

        if op == "and":
            if Result.DOES_NOT_APPLY in results:
                res = Result.DOES_NOT_APPLY          # short-circuit: definitive
            elif Result.INSUFFICIENT_DATA in results:
                res = Result.INSUFFICIENT_DATA
            else:
                res = Result.APPLIES
        else:  # or
            if Result.APPLIES in results:
                res = Result.APPLIES                 # short-circuit: definitive
            elif Result.INSUFFICIENT_DATA in results:
                res = Result.INSUFFICIENT_DATA
            else:
                res = Result.DOES_NOT_APPLY

        return res, Trace(op, res, f"{op.upper()} of {len(traces)} conditions", traces)

    if op == "not":
        inner, t = evaluate(expr["args"][0], profile)
        if inner is Result.INSUFFICIENT_DATA:
            res = Result.INSUFFICIENT_DATA
        else:
            res = (Result.DOES_NOT_APPLY if inner is Result.APPLIES else Result.APPLIES)
        return res, Trace("not", res, "NOT", [t])

    # ---------- leaf predicates ----------
    field_name = expr.get("field")
    actual = profile.get(field_name)

    if actual is None:
        return Result.INSUFFICIENT_DATA, Trace(
            field_name, Result.INSUFFICIENT_DATA,
            f"'{field_name}' is not set on the company profile — need this to decide",
        )

    if op in _COMPARATORS:
        expected = expr["value"]
        ok = _COMPARATORS[op](actual, expected)
        res = Result.APPLIES if ok else Result.DOES_NOT_APPLY
        return res, Trace(
            field_name, res, f"{field_name} ({actual}) {op} {expected}"
        )

    if op == "in":
        # 'in' compares a scalar field against a set of allowed values. Applied to a
        # list-valued field (districts) it silently evaluates False — a wrong answer with no
        # error. Refuse the mis-encoding instead of serving it.
        if isinstance(actual, (list, tuple, set)):
            raise ValueError(
                f"'in' applied to list-valued field {field_name!r}; "
                f"use 'contains' (list holds a value) or 'intersects' (lists overlap)"
            )
        ok = actual in expr["value"]
        res = Result.APPLIES if ok else Result.DOES_NOT_APPLY
        return res, Trace(field_name, res, f"{field_name} ({actual}) in {expr['value']}")

    if op == "contains":
        # List-valued field holds this specific value. e.g. districts contains 'IN-KA-BLR'.
        if not isinstance(actual, (list, tuple, set)):
            raise ValueError(f"'contains' applied to non-list field {field_name!r}")
        if not actual:
            # Empty means "we never asked", not "none". Ask; don't decide.
            return Result.INSUFFICIENT_DATA, Trace(
                field_name, Result.INSUFFICIENT_DATA,
                f"'{field_name}' is empty — we have not asked which district(s) they operate in",
            )
        ok = expr["value"] in actual
        res = Result.APPLIES if ok else Result.DOES_NOT_APPLY
        return res, Trace(
            field_name, res, f"{field_name} ({list(actual)}) contains {expr['value']!r}"
        )

    if op == "intersects":
        # List-valued field overlaps a set of values — the district-scoped obligation case.
        if not isinstance(actual, (list, tuple, set)):
            raise ValueError(f"'intersects' applied to non-list field {field_name!r}")
        overlap = sorted(set(actual) & set(expr["value"]))
        res = Result.APPLIES if overlap else Result.DOES_NOT_APPLY
        return res, Trace(
            field_name, res,
            f"{field_name} ({list(actual)}) intersects {expr['value']}"
            + (f" → {overlap}" if overlap else " → no overlap"),
        )

    if op == "between":
        lo, hi = expr["value"]
        ok = lo <= actual <= hi
        res = Result.APPLIES if ok else Result.DOES_NOT_APPLY
        return res, Trace(field_name, res, f"{field_name} ({actual}) between {lo} and {hi}")

    if op == "exists":
        res = Result.APPLIES if actual is not None else Result.DOES_NOT_APPLY
        return res, Trace(field_name, res, f"{field_name} exists")

    raise ValueError(f"Unknown operator: {op!r}")


def missing_fields(expr: dict, profile: CompanyProfile) -> list[str]:
    """Which profile fields would we need to resolve INSUFFICIENT_DATA? Drives the follow-up question."""
    out: list[str] = []

    def walk(e: dict) -> None:
        if e.get("op") in ("and", "or", "not"):
            for a in e["args"]:
                walk(a)
        else:
            f = e.get("field")
            if not f:
                return
            v = profile.get(f)
            # None means unset. An empty list also means unset — we never asked which
            # districts they operate in — and must drive the same follow-up question,
            # or INSUFFICIENT_DATA reports no field to ask for.
            if v is None or (isinstance(v, (list, tuple, set)) and not v):
                out.append(f)

    walk(expr)
    return sorted(set(out))


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    # PoSH: Internal Committee required at 10+ employees (illustrative encoding).
    POSH_IC = {
        "op": "gte", "field": "employee_count", "value": 10,
    }

    # ESI (illustrative): 10+ employees AND at least one below the wage ceiling
    # AND establishment type covered.
    ESI = {
        "op": "and",
        "args": [
            {"op": "gte", "field": "employee_count", "value": 10},
            {"op": "gte", "field": "employees_below_wage_ceiling", "value": 1},
            {"op": "in", "field": "establishment_type",
             "value": ["shop_or_commercial", "factory", "it_ites"]},
        ],
    }

    # Gurugram's District Officer notified 28 February for the PoSH annual return.
    # The deadline is district-set, so the condition must be too — see jurisdiction.py.
    GGN_DEADLINE = {
        "op": "and",
        "args": [
            {"op": "gte", "field": "employee_count", "value": 10},
            {"op": "contains", "field": "districts", "value": "IN-HR-GGN"},
        ],
    }

    base = dict(
        state="IN-KA",
        establishment_type="it_ites",
        entity_type="pvt_ltd",
        as_of=date(2026, 8, 6),
    )

    cases = [
        ("PoSH, 42 employees",
         POSH_IC, CompanyProfile(employee_count=42, **base), Result.APPLIES),
        ("PoSH, 8 employees",
         POSH_IC, CompanyProfile(employee_count=8, **base), Result.DOES_NOT_APPLY),
        ("PoSH, exactly 10 (boundary)",
         POSH_IC, CompanyProfile(employee_count=10, **base), Result.APPLIES),
        ("ESI, wage-ceiling count unknown",
         ESI, CompanyProfile(employee_count=42, **base), Result.INSUFFICIENT_DATA),
        ("ESI, 42 employees, 30 below ceiling",
         ESI, CompanyProfile(employee_count=42, employees_below_wage_ceiling=30, **base),
         Result.APPLIES),
        ("ESI, 42 employees, 0 below ceiling",
         ESI, CompanyProfile(employee_count=42, employees_below_wage_ceiling=0, **base),
         Result.DOES_NOT_APPLY),

        # ── district-scoped conditions (C-1) ──────────────────────────────
        # Gurugram's PoSH annual return is 28 Feb, not the widely-repeated 31 Jan.
        # These encode "does the Gurugram notification apply to you".
        ("District matches → applies",
         GGN_DEADLINE,
         CompanyProfile(employee_count=42, districts=["IN-HR-GGN"], **base),
         Result.APPLIES),
        ("Different district → does not apply (no silent fallback)",
         GGN_DEADLINE,
         CompanyProfile(employee_count=42, districts=["IN-KA-BLR"], **base),
         Result.DOES_NOT_APPLY),
        ("District never asked → INSUFFICIENT_DATA, not a guess",
         GGN_DEADLINE,
         CompanyProfile(employee_count=42, **base),
         Result.INSUFFICIENT_DATA),
        ("Multi-district company, one matches → applies",
         GGN_DEADLINE,
         CompanyProfile(employee_count=42, districts=["IN-KA-BLR", "IN-HR-GGN"], **base),
         Result.APPLIES),
    ]

    failures = 0
    for name, expr, prof, expected in cases:
        res, trace = evaluate(expr, prof)
        ok = res is expected
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(trace.render(indent=1), end="")
        if res is Result.INSUFFICIENT_DATA:
            print(f"       → need: {missing_fields(expr, prof)}")
        print()

    print(f"{len(cases) - failures}/{len(cases)} passed")
    raise SystemExit(1 if failures else 0)
