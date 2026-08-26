"""Post-fix inventory of amendment spans, and the gate into witness work.

After the `_SPAN_OPEN` correction, every span that could not be resolved falls
into exactly one of four buckets. Which bucket a span is in determines whether an
amending Act can help it, so the classification is the gate: parser-fixed spans
are excluded from witness work entirely, because nothing about them was ever
missing from the source.

    PARSER_FIXED     resolvable now; the bracket was there behind a <b> or <i>
    OMISSION_MARKER  no bracket because the text was omitted from the
                     consolidation. India Code cannot supply the prior wording at
                     any price — only the amending Act can
    UNCLOSED         opens and never closes. A genuine India Code defect
    MARKER_ABSENT    the footnote names a marker that appears nowhere in the
                     content. Also a genuine defect

## Why the old pattern is kept

`OLD_SPAN_OPEN` is retained so the before/after comparison is *computed* rather
than quoted from a commit message. A count in prose drifts; a count derived from
both patterns against the same corpus cannot.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import timedelta
from pathlib import Path

from checker.amendment import parse_footnote
from checker.as_of import _SPAN_OPEN, _find_span

CORPUS = Path("corpus/companies_act")

# The pattern before the SD-003 correction. Only whitespace was allowed between
# the marker and its bracket.
OLD_SPAN_OPEN = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>\s*\[")

PARSER_FIXED = "PARSER_FIXED"
OMISSION_MARKER = "OMISSION_MARKER"
UNCLOSED = "UNCLOSED"
MARKER_ABSENT = "MARKER_ABSENT"
RESOLVED_ALL_ALONG = "RESOLVED_ALL_ALONG"

# Only these may enter Act-based witness work.
WITNESS_ELIGIBLE = (OMISSION_MARKER, UNCLOSED, MARKER_ABSENT)

# Amending Acts we hold a copy of, per checker/corroborate.py.
HELD_ACTS = ("Act 29 of 2020", "Act 1 of 2018", "Act 21 of 2015")


@dataclass
class Span:
    section: str
    section_id: str
    marker: int
    operation: str
    instrument: str | None
    wef: str | None
    bucket: str

    @property
    def witness_eligible(self) -> bool:
        return self.bucket in WITNESS_ELIGIBLE

    @property
    def witness_held(self) -> bool:
        return self.instrument in HELD_ACTS


def _old_find(html: str, marker: int) -> bool:
    for m in OLD_SPAN_OPEN.finditer(html):
        if int(m.group(1)) != marker:
            continue
        depth, i = 1, m.end()
        while i < len(html):
            if html[i] == "[":
                depth += 1
            elif html[i] == "]":
                depth -= 1
                if depth == 0:
                    return True
            i += 1
        return False
    return False


def _records():
    idx = json.loads((CORPUS / "_index.json").read_text())["entries"]
    by_id = {v["section_id"]: k for k, v in idx.items() if v.get("section_id")}
    for p in sorted(CORPUS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        num = by_id.get(p.stem)
        if not num:
            continue
        try:
            yield num, p.stem, json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue


def classify(html: str, marker: int) -> str:
    """Which bucket this span falls into, under the corrected pattern."""
    now_ok = _find_span(html, marker) is not None
    was_ok = _old_find(html, marker)
    if now_ok:
        return RESOLVED_ALL_ALONG if was_ok else PARSER_FIXED
    if not re.search(rf"<sup>\s*{marker}\s*</sup>", html):
        return MARKER_ABSENT
    # The marker is present. Is there a bracket it could have opened?
    m = _SPAN_OPEN.search(html) and re.search(
        rf"<sup>\s*{marker}\s*</sup>(?:\s|<[^>]{{1,12}}>){{0,6}}\[", html)
    return UNCLOSED if m else OMISSION_MARKER


def inventory() -> list[Span]:
    out: list[Span] = []
    for num, sid, rec in _records():
        html = rec.get("content") or ""
        for a in parse_footnote(rec.get("footnote") or ""):
            out.append(Span(
                section=num, section_id=sid, marker=a.marker,
                operation=a.operation, instrument=a.instrument,
                wef=a.wef.isoformat() if a.wef else None,
                bucket=classify(html, a.marker),
            ))
    return out


def fidelity_counts(pattern_is_old: bool = False) -> dict[str, int]:
    """(before, on-date) fidelity across amended sections, for either pattern."""
    from checker.as_of import section_as_of
    import checker.as_of as mod
    saved = mod._SPAN_OPEN
    if pattern_is_old:
        mod._SPAN_OPEN = OLD_SPAN_OPEN
    try:
        counts: dict[str, int] = {}
        for num, sid, rec in _records():
            ams = [a for a in parse_footnote(rec.get("footnote") or "")
                   if a.wef and not a.wef_implausible]
            if not ams:
                continue
            d = min(a.wef for a in ams)
            k = (f"{section_as_of(rec, d - timedelta(days=1)).fidelity}/"
                 f"{section_as_of(rec, d).fidelity}")
            counts[k] = counts.get(k, 0) + 1
        return counts
    finally:
        mod._SPAN_OPEN = saved


def sections_changed_by_fix() -> list[str]:
    """Sections whose before-amendment fidelity improved because of the fix."""
    from checker.as_of import section_as_of
    import checker.as_of as mod
    changed = []
    for num, sid, rec in _records():
        ams = [a for a in parse_footnote(rec.get("footnote") or "")
               if a.wef and not a.wef_implausible]
        if not ams:
            continue
        d = min(a.wef for a in ams) - timedelta(days=1)
        new = section_as_of(rec, d).fidelity
        saved = mod._SPAN_OPEN
        mod._SPAN_OPEN = OLD_SPAN_OPEN
        try:
            old = section_as_of(rec, d).fidelity
        finally:
            mod._SPAN_OPEN = saved
        if old != new:
            changed.append(f"s.{num}: {old} -> {new}")
    return sorted(changed)


def batch_candidates(limit: int = 10) -> list[Span]:
    """Witness-eligible omission spans whose amending Act we already hold.

    Selection is deliberately narrow. Priority is omission markers with a named
    instrument, a commencement date, and a resolvable section — the cases where
    a deterministic answer is plausible. Hard cases are not mixed in to reach a
    round number; if fewer than `limit` qualify, fewer are returned.
    """
    elig = [s for s in inventory()
            if s.bucket == OMISSION_MARKER and s.witness_held
            and s.instrument and s.wef and s.operation == "omitted"]
    elig.sort(key=lambda s: (s.instrument or "", s.section, s.marker))
    return elig[:limit]


def report() -> str:
    inv = inventory()
    buckets: dict[str, int] = {}
    for s in inv:
        buckets[s.bucket] = buckets.get(s.bucket, 0) + 1

    old_f, new_f = fidelity_counts(True), fidelity_counts(False)
    changed = sections_changed_by_fix()
    elig = [s for s in inv if s.witness_eligible]
    held = [s for s in elig if s.witness_held]

    lines = [
        "", "POST-FIX SPAN INVENTORY", "=" * 62, "",
        f"total amendment spans: {len(inv)}", "",
        "buckets:",
    ]
    for k in (RESOLVED_ALL_ALONG, PARSER_FIXED, OMISSION_MARKER, UNCLOSED,
              MARKER_ABSENT):
        lines.append(f"   {k:<20} {buckets.get(k, 0)}")
    lines += [
        "", "SD-003, as filed vs corrected:",
        "   as filed    : 120 unbalanced spans, attributed to India Code",
        f"   corrected   : {buckets.get(PARSER_FIXED, 0)} were our regex; "
        f"{buckets.get(UNCLOSED, 0) + buckets.get(MARKER_ABSENT, 0)} are genuine "
        f"India Code defects",
        f"                 {buckets.get(OMISSION_MARKER, 0)} are omissions — "
        "correct source behaviour, witness-dependent",
        "", "section fidelity (before/on first amendment date):",
        f"   {'':<18}{'old pattern':>12}{'corrected':>12}",
    ]
    for k in sorted(set(old_f) | set(new_f)):
        lines.append(f"   {k:<18}{old_f.get(k, 0):>12}{new_f.get(k, 0):>12}")
    lines += [
        "", f"sections whose status changed because of the fix: {len(changed)}",
    ]
    lines += [f"   {c}" for c in changed[:12]]
    if len(changed) > 12:
        lines.append(f"   ... and {len(changed) - 12} more")
    lines += [
        "", "GATE INTO ACT-BASED WITNESS WORK",
        f"   witness-eligible spans        : {len(elig)}",
        f"   ...of which the Act is held   : {len(held)}",
        f"   parser-fixed spans excluded   : {buckets.get(PARSER_FIXED, 0)}",
        "   Parser-fixed spans are excluded by construction: nothing about them",
        "   was ever missing from the source.",
    ]
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

    print("span_inventory")

    check(classify("<sup>1</sup>[x]", 1) == RESOLVED_ALL_ALONG,
          "a plain bracketed span always worked")
    check(classify("<sup>1</sup><b>[x]</b>", 1) == PARSER_FIXED,
          "a bracket behind <b> is PARSER_FIXED, not a source defect")
    check(classify("<sup>1</sup>[unclosed", 1) == UNCLOSED,
          "an opening with no close is UNCLOSED")
    check(classify("text with no marker", 1) == MARKER_ABSENT,
          "a footnote marker absent from content is MARKER_ABSENT")
    check(classify("some text <sup>1</sup> more text", 1) == OMISSION_MARKER,
          "a bare marker with no bracket is an OMISSION_MARKER")

    inv = inventory()
    check(len(inv) > 400, f"the inventory covers the corpus ({len(inv)} spans)")
    buckets = {}
    for s in inv:
        buckets[s.bucket] = buckets.get(s.bucket, 0) + 1
    check(buckets.get(PARSER_FIXED, 0) >= 35,
          f"the parser fix is visible in the inventory ({buckets.get(PARSER_FIXED)})")
    check(buckets.get(UNCLOSED, 0) + buckets.get(MARKER_ABSENT, 0) <= 15,
          f"genuine India Code defects are a small residual "
          f"({buckets.get(UNCLOSED, 0) + buckets.get(MARKER_ABSENT, 0)})")

    # The gate.
    check(all(s.bucket != PARSER_FIXED for s in inv if s.witness_eligible),
          "no parser-fixed span is witness-eligible")
    check(all(s.witness_eligible for s in batch_candidates(50)),
          "every batch candidate passes the gate")
    check(all(s.witness_held for s in batch_candidates(50)),
          "every batch candidate's amending Act is one we hold")
    check(all(s.operation == "omitted" for s in batch_candidates(50)),
          "batch 1 is omissions only")

    cands = batch_candidates(10)
    check(len(cands) <= 10, f"the batch is capped at ten ({len(cands)})")
    check(all(c.wef and c.instrument for c in cands),
          "every candidate has a commencement date and a named instrument")

    old_f, new_f = fidelity_counts(True), fidelity_counts(False)
    check(new_f.get("EXACT/EXACT", 0) > old_f.get("EXACT/EXACT", 0),
          f"the fix improved exact reconstruction "
          f"({old_f.get('EXACT/EXACT')} -> {new_f.get('EXACT/EXACT')})")
    check(sum(old_f.values()) == sum(new_f.values()),
          "the fix changed fidelity, not the number of sections considered")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _test()
    else:
        print(report())
