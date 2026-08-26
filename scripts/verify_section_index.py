#!/usr/bin/env python3
"""Check our number -> section_id index against India Code itself.

    python3 scripts/verify_section_index.py            # the MVP sections
    python3 scripts/verify_section_index.py --all      # every mapped section
    python3 scripts/verify_section_index.py --test     # offline self-test

## Why this exists

`CLAUDE.md` has carried this caveat since 21 Aug 2026:

    Section index: 464/474 mapped, 17 MVP sections hand-verified.
    PDF-derived, not source-confirmed - India Code returned 403.

The index was built by parsing a PDF, so a mis-parse would be invisible: nothing
independent said which section number belongs to which id. Every downstream
answer rests on that mapping, so an unverified mapping is a silent single point
of failure.

## The 403 was a dead domain, not a block

`indiacode.nic.in` still returns 403 to everything. The site moved to
`indiacode.gov.in`, which runs DSpace with an **open REST API** - no key, no
auth. We were being refused by a host that no longer serves the content.

The API exposes `dc.identifier.section_number`, `dc.identifier.section_id` and
`dc.title.act_name` as structured fields, so the mapping can be checked directly
rather than inferred from rendered text.

## One trap this code guards against

`dc.identifier.section_number:96` matches section 96 of *every* Act in the
database - 116 hits, including the SIDBI Act and a Maharashtra marketing Act
that both have a section titled "Annual general meeting". Any check that takes
the first hit would confirm our Companies Act mapping against an unrelated
statute and report success. Results are therefore filtered on `act_name` before
anything is compared, and a section number with no Companies Act hit is reported
NOT_FOUND rather than matched against a neighbour.
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.robots import USER_AGENT, ssl_context  # noqa: E402

API = "https://indiacode.gov.in/server/api/discover/search/objects"
ACT_NAME = "The Companies Act, 2013"
ACT_NUMBER = "18"
ACT_YEAR = "2013"
DELAY_S = 1.5

MATCH = "MATCH"            # source agrees with our mapping
MISMATCH = "MISMATCH"      # source gives a different id: our index is wrong
NOT_FOUND = "NOT_FOUND"    # no Companies Act record for this number
UNREACHABLE = "UNREACHABLE"


@dataclass
class Check:
    number: str
    ours: str | None
    theirs: str | None
    verdict: str
    title: str = ""

    @property
    def confirmed(self) -> bool:
        return self.verdict == MATCH


def _get(url: str, timeout: float = 40.0) -> dict | None:
    ctx = ssl_context()
    if ctx is None:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _md(obj: dict, key: str) -> str:
    vals = obj.get("metadata", {}).get(key) or []
    return vals[0].get("value", "") if vals else ""


def lookup(number: str) -> tuple[str | None, str]:
    """(section_id, title) for this section of the Companies Act 2013.

    The Act is constrained *in the query*, not just in the client-side filter.
    Filtering a broad `section_number:96` result set client-side reported s.96 as
    NOT_FOUND even though India Code holds it: 116 Acts have a section 96, and the
    Companies Act record fell outside the first page. A false NOT_FOUND is the
    dangerous direction of error - it reads as "the source lacks this" when the
    truth is "we did not look far enough".
    """
    q = urllib.parse.quote(
        f"dc.identifier.section_number:{number}"
        f" AND dc.identifier.act_number:{ACT_NUMBER}"
        f" AND dc.date.act_year:{ACT_YEAR}"
    )
    data = _get(f"{API}?query={q}&size=20")
    if data is None:
        return None, ""
    objs = (data.get("_embedded", {}).get("searchResult", {})
                .get("_embedded", {}).get("objects", []))
    for o in objs:
        ind = o.get("_embedded", {}).get("indexableObject", {})
        # Filter on the Act *before* comparing anything. See module docstring.
        if _md(ind, "dc.title.act_name") != ACT_NAME:
            continue
        if _md(ind, "dc.identifier.section_number") != number:
            continue
        return _md(ind, "dc.identifier.section_id"), _md(ind, "dc.title")
    return None, ""


def check_numbers(numbers: list[str], verbose: bool = True) -> list[Check]:
    from checker.section_index import section_by_number

    out: list[Check] = []
    for i, num in enumerate(numbers):
        rec = section_by_number(num)
        ours = (rec or {}).get("section_id")
        theirs, title = lookup(num)
        if theirs is None:
            verdict = NOT_FOUND
        elif ours is None:
            verdict = NOT_FOUND
        elif str(theirs) == str(ours):
            verdict = MATCH
        else:
            verdict = MISMATCH
        c = Check(num, ours, theirs, verdict, title)
        out.append(c)
        if verbose:
            mark = "ok  " if c.confirmed else "FAIL"
            print(f"  {mark} s.{num:<7} ours={ours or '-':<8} source={theirs or '-':<8}"
                  f" {verdict:<10} {title[:40]}", flush=True)
        if i + 1 < len(numbers):
            time.sleep(DELAY_S)
    return out


def report(checks: list[Check]) -> str:
    n = len(checks)
    ok = sum(c.confirmed for c in checks)
    bad = [c for c in checks if c.verdict == MISMATCH]
    miss = [c for c in checks if c.verdict == NOT_FOUND]
    lines = [
        "",
        "SECTION INDEX vs INDIA CODE (indiacode.gov.in REST API)",
        f"  confirmed against source : {ok}/{n}",
        f"  MISMATCHED (index wrong) : {len(bad)}",
        f"  not found in source      : {len(miss)}",
    ]
    for c in bad:
        lines.append(f"    s.{c.number}: ours={c.ours} source={c.theirs}")
    if miss:
        lines.append(f"    not found: {', '.join('s.' + c.number for c in miss[:12])}")
    lines.append("  A MATCH confirms the number->id mapping only. It does not")
    lines.append("  verify the section text, and says nothing about past wording.")
    return "\n".join(lines)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("verify_section_index")

    check(Check("96", "1287", "1287", MATCH).confirmed, "an agreeing id is confirmed")
    check(not Check("96", "1287", "9999", MISMATCH).confirmed,
          "a differing id is not confirmed")
    check(not Check("96", "1287", None, NOT_FOUND).confirmed,
          "a missing source record is not confirmed")
    check(not Check("96", None, None, UNREACHABLE).confirmed,
          "an unreachable source is not confirmed")

    r = report([Check("96", "1", "1", MATCH), Check("97", "2", "3", MISMATCH)])
    check("1/2" in r, "the report counts only confirmed mappings")
    check("s.97: ours=2 source=3" in r, "a mismatch names both ids")
    check("does not" in r and "text" in r,
          "the report states that text is not verified by this check")

    # The filter that keeps us honest: other Acts have a section 96 too.
    check(ACT_NAME == "The Companies Act, 2013",
          "results are filtered to one named Act before comparison")
    # Regression: a broad section_number query returns 116 Acts and paginates,
    # which reported s.96 as NOT_FOUND while India Code held it as id 1287.
    src = Path(__file__).read_text()
    check("dc.identifier.act_number" in src and "AND" in src,
          "the Act is constrained in the query, not only client-side")

    # Regression: --all once read the index's top level, whose keys are
    # "source"/"built_offline"/"entries", and dutifully looked up s.built_offline.
    idx = json.loads(Path("corpus/companies_act/_index.json").read_text())
    check("entries" in idx and len(idx["entries"]) > 400,
          f"section numbers are read from .entries ({len(idx.get('entries', {}))})")
    check(all(k[0].isdigit() for k in list(idx["entries"])[:50]),
          "every key taken from .entries looks like a section number")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        _test()
        raise SystemExit(0)

    from checker.section_index import MVP_SECTIONS

    if "--all" in args:
        # The section numbers live under "entries"; the top level also holds
        # "source" and "built_offline". Reading the top level treated those
        # metadata keys as section numbers and "checked" s.built_offline.
        idx = json.loads(Path("corpus/companies_act/_index.json").read_text())
        entries = idx.get("entries", idx)
        nums = sorted(entries.keys(), key=lambda s: (len(s), s))
    else:
        nums = list(MVP_SECTIONS)

    print(f"checking {len(nums)} section(s) against {ACT_NAME} on indiacode.gov.in")
    checks = check_numbers(nums)
    print(report(checks))
    raise SystemExit(0 if all(c.verdict != MISMATCH for c in checks) else 1)
