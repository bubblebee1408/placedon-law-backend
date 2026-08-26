#!/usr/bin/env python3
"""Resolve sections our PDF parse could not, using India Code as the authority.

    python3 scripts/resolve_missing_sections.py            # report only
    python3 scripts/resolve_missing_sections.py --write    # update the index
    python3 scripts/resolve_missing_sections.py --test

## What is being fixed

The section index was built by slicing a PDF. For some sections the slice was
ambiguous and the entry was left with `section_id: None, confidence: 'none'`.
Those are *parse failures*, not omitted provisions - s.51 (payment of dividend in
proportion to amount paid-up) is live law that our parser simply could not pin
down, and India Code holds it as id 1241.

They were invisible for two reasons. India Code returned 403 to everything, so
there was nothing to resolve them against; and our own verifier scored an
unresolved entry the same way it scored a legitimately omitted one, so the gap
looked like a correct answer.

## Why this is safe to write

The API returns `dc.identifier.section_number` and `dc.identifier.section_id` as
structured fields for a named Act, so this is not inference from rendered text.
Each write is additionally guarded:

- the record must come from `The Companies Act, 2013` (116 Acts have a s.96),
- the returned section number must equal the one requested,
- an entry we already resolved is never overwritten - if the source disagrees with
  a confident mapping, that is a MISMATCH to investigate by hand, not to
  silently apply,
- entries our index records as *omitted* are left alone.

Resolved entries are marked `method: 'india code api'` and
`confidence: 'source-confirmed'` so their provenance stays visible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.verify_section_index import (  # noqa: E402
    _we_call_it_omitted, lookup,
)

# Set only by the self-test, so the omission check can run against a fixture
# instead of the live index.
_ENTRIES_OVERRIDE: dict | None = None

INDEX = Path("corpus/companies_act/_index.json")
RESOLVED_METHOD = "india code api"
RESOLVED_CONFIDENCE = "source-confirmed"


def unresolved(entries: dict) -> list[str]:
    """Section numbers with no id that we do NOT record as omitted."""
    out = []
    for num, e in entries.items():
        if e.get("section_id"):
            continue
        if _ENTRIES_OVERRIDE is not None:
            e2 = _ENTRIES_OVERRIDE.get(num, {})
            if "omitted" in (e2.get("method", "") + " " + e2.get("title", "")).lower():
                continue
        elif _we_call_it_omitted(num):
            continue
        out.append(num)
    return sorted(out, key=lambda s: (len(s), s))


def resolve(numbers: list[str], verbose: bool = True) -> dict[str, tuple[str, str]]:
    """{number: (section_id, title)} for those the source can pin down."""
    found: dict[str, tuple[str, str]] = {}
    for num in numbers:
        sid, title = lookup(num)
        title = title.replace("\x00OMITTED", "")
        if sid:
            found[num] = (sid, title)
        if verbose:
            print(f"  s.{num:<8} {'-> ' + sid if sid else 'not in source'}  {title[:52]}",
                  flush=True)
    return found


def apply(found: dict[str, tuple[str, str]], entries: dict) -> int:
    """Write resolutions into the index. Never overwrites a resolved entry."""
    n = 0
    for num, (sid, title) in found.items():
        e = entries.get(num)
        if e is None or e.get("section_id"):
            continue                       # already resolved: not ours to change
        e["section_id"] = sid
        e["confidence"] = RESOLVED_CONFIDENCE
        e["method"] = RESOLVED_METHOD
        if title and not e.get("title"):
            e["title"] = title
        n += 1
    return n


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

    print("resolve_missing_sections")

    # The detector is exercised on a fixture, because the live index is now clean
    # and a test that needs real gaps would break the moment they were fixed.
    fixture = {
        "51":  {"section_id": None, "confidence": "none", "method": "ambiguous"},
        "11":  {"section_id": None, "confidence": "n/a", "method": "omitted in source",
                "title": "[Omitted.]"},
        "96":  {"section_id": "1287", "confidence": "high", "method": "anchored"},
    }
    import scripts.resolve_missing_sections as mod
    saved = mod._ENTRIES_OVERRIDE
    mod._ENTRIES_OVERRIDE = fixture
    try:
        u = unresolved(fixture)
        check(u == ["51"], f"only the ambiguous parse failure is reported missing ({u})")
        check("11" not in u, "an omitted section is not reported missing")
        check("96" not in u, "an already-resolved section is not reported missing")
    finally:
        mod._ENTRIES_OVERRIDE = saved

    # And the live index: every live section is now resolved. This is the state
    # the tool exists to reach, so it is asserted rather than assumed.
    entries = json.loads(INDEX.read_text())["entries"]
    live = unresolved(entries)
    check(live == [], f"no live section is left unresolved ({live})")

    # apply() must refuse to touch a resolved entry.
    fake = {"96": {"section_number": "96", "section_id": "1287", "confidence": "high"},
            "51": {"section_number": "51", "section_id": None, "confidence": "none"}}
    n = apply({"96": ("9999", "x"), "51": ("1241", "Payment of dividend")}, fake)
    check(fake["96"]["section_id"] == "1287",
          "a confident mapping is never overwritten by the source")
    check(fake["51"]["section_id"] == "1241", "an unresolved mapping is filled in")
    check(n == 1, f"exactly one entry was written ({n})")
    check(fake["51"]["confidence"] == RESOLVED_CONFIDENCE,
          "a filled entry is marked source-confirmed, keeping provenance visible")
    check(fake["51"]["method"] == RESOLVED_METHOD, "...and names the source")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--test" in args:
        _test()
        raise SystemExit(0)

    doc = json.loads(INDEX.read_text())
    entries = doc["entries"]
    todo = unresolved(entries)
    print(f"{len(todo)} unresolved, non-omitted section(s): {', '.join('s.' + n for n in todo)}\n")
    found = resolve(todo)
    print(f"\nresolved by India Code: {len(found)}/{len(todo)}")

    if "--write" in args and found:
        n = apply(found, entries)
        INDEX.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {n} entr(ies) to {INDEX}")
    elif found:
        print("re-run with --write to apply")
