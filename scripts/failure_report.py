#!/usr/bin/env python3
"""Weekly counts of why runs did not answer.

PLAN_23 O8's reporting half. `checker/failure_tags.py` names the category and
`gateway/store.set_run` records it; this counts them by week, so the question "are we
losing more runs than last week, and to what" has an answer.

## What the report refuses to do

**It does not drop the untagged.** Every run written before 015 has no category, and they
appear as their own line. Excluding them would shrink the denominator and make the tagged
failures look like the whole picture, which is the same error as a hit rate that hides its
stale finds.

**It does not count a scope refusal as a fault.** Refusing by name a question about a body
of law this engine does not hold is the product working. It is reported -- the trend says
what to acquire next -- under its own heading, and the fault total excludes it. A weekly
report that read "six kinds of broken" when one of them was correct behaviour would be
pointing the next week's work at the wrong thing.

**It states no rate over a week with no runs.** No runs is not a 0% failure rate.

Run: PYTHONPATH=. python3 scripts/failure_report.py
     PLACEDON_DATABASE_URL=postgres://... PYTHONPATH=. python3 scripts/failure_report.py
"""
from __future__ import annotations

import sys


def summarise(rows) -> dict:
    """{weeks: {week: {category: count}}, totals, faults, not_faults, untagged}. Pure."""
    from checker import failure_tags as ft
    weeks: dict = {}
    totals: dict = {}
    untagged = 0
    for r in rows or ():
        week = r.get("week") or "(no date recorded)"
        cat = r.get("category")
        n = int(r.get("count") or 0)
        key = cat if cat else "(not recorded)"
        weeks.setdefault(week, {})[key] = weeks.setdefault(week, {}).get(key, 0) + n
        totals[key] = totals.get(key, 0) + n
        if not cat:
            untagged += n
    faults = sum(n for c, n in totals.items() if ft.is_fault(c))
    return {"weeks": weeks, "totals": totals, "faults": faults,
            "not_faults": sum(totals.values()) - faults, "untagged": untagged,
            "runs": sum(totals.values())}


def report(rows) -> str:
    from checker import failure_tags as ft
    s = summarise(rows)
    if not s["runs"]:
        return ("failure report\n  no non-answered runs are recorded.\n"
                "  That is not a 0% failure rate -- it is no measurement.")
    out = ["failure report", ""]
    for week in sorted(s["weeks"]):
        out.append(f"  {week}")
        for cat, n in sorted(s["weeks"][week].items(), key=lambda kv: (-kv[1], kv[0])):
            mark = "  " if ft.is_fault(cat) else " ·"
            out.append(f"   {mark} {cat:<16} {n}")
    out += ["", f"  totals over {len(s['weeks'])} week(s): {s['runs']} non-answered run(s)",
            f"    faults            {s['faults']}",
            f"    not faults        {s['not_faults']}  "
            f"(· scope refusals, cancellations, uncategorised)",
            f"    not recorded      {s['untagged']}  "
            f"(runs from before migration 015; never backfilled)"]
    if s["untagged"]:
        out.append("")
        out.append("  A category computed today and stored as though observed at the time "
                   "would be a\n  fabricated measurement, so those stay NULL and are "
                   "counted here instead.")
    return "\n".join(out)


def main() -> int:
    from gateway.store import select
    try:
        backend = select()
    except Exception as e:                                       # noqa: BLE001
        print(f"no store: {type(e).__name__}: {str(e)[:160]}")
        return 2
    print(report(backend.read_failure_counts()))
    return 0


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

    print("failure_report")
    ROWS = [{"week": "2026-W39", "category": "transport", "count": 3},
            {"week": "2026-W39", "category": "scope_refusal", "count": 5},
            {"week": "2026-W40", "category": "transport", "count": 1},
            {"week": "2026-W40", "category": "verifier_reject", "count": 2},
            {"week": "2026-W40", "category": None, "count": 4}]
    s = summarise(ROWS)
    check(s["runs"] == 15, f"every row is counted ({s['runs']})")
    check(s["faults"] == 6,
          f"faults are transport+verifier_reject only: 3+1+2 ({s['faults']})")
    check(s["not_faults"] == 9,
          "...and the 5 scope refusals and 4 untagged are NOT faults")
    check(s["untagged"] == 4, "untagged runs are counted, not dropped")
    r = report(ROWS)
    check("2026-W39" in r and "2026-W40" in r, "every week appears")
    check("scope_refusal" in r,
          "a scope refusal is REPORTED -- the trend says what to acquire next")
    check("· scope_refusal" in r,
          "...but marked apart from the faults, because refusing by name is the product "
          "working, not six kinds of broken")
    check("not recorded      4" in r,
          "...and the untagged runs get their own line rather than shrinking the "
          "denominator")
    check("never backfilled" in r,
          "...with why they stay NULL: a category computed later and stored as though "
          "observed would be a fabricated measurement")
    empty = report([])
    check("not a 0% failure rate" in empty,
          "no runs at all is NO MEASUREMENT, never a 0% failure rate")
    check("(not recorded)" in report([{"week": "2026-W40", "category": "", "count": 1}]),
          "an empty-string category reads as not recorded, not as a category named ''")
    check(summarise([])["runs"] == 0, "summarising nothing is zero runs, not an error")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main())
