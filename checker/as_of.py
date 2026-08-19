"""
Point-in-time reconstruction of a Companies Act section.

The honest design constraint, which shapes everything below:

India Code publishes the CURRENT text of a section plus a footnote ledger of what changed.
That is enough to reconstruct the past only in some cases:

  inserted  w.e.f. D   -> before D the span did not exist. REMOVE it. Fully recoverable.
  omitted   w.e.f. D   -> before D some text existed that is no longer shown.
                          Recoverable ONLY if the footnote quotes it.
  substituted w.e.f. D -> before D different text stood there.
                          Recoverable ONLY if the footnote quotes the prior wording, which it
                          sometimes does: Subs. ... for "the old words".

So a reconstruction is one of three things, and we say which:

  EXACT    every span in force at that date is known verbatim
  PARTIAL  at least one span's prior wording is not recoverable from the source
  ABSTAIN  the date precedes the Act's commencement, or nothing can be established

We never invent the prior wording of a provision. A PARTIAL result names exactly which spans are
unknown so the professional knows where to look. That is the whole product in one function.

Pure functions over ingested corpus records. Run: python3 checker/as_of.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from checker.amendment import Amendment, parse_footnote

Fidelity = Literal["EXACT", "PARTIAL", "ABSTAIN"]

# The Companies Act 2013 came into force in stages; 1 April 2014 is when the bulk commenced.
# Before this, asking "what did s.X say" is a question about the 1956 Act, which is not our corpus.
COMMENCEMENT = date(2014, 4, 1)

# <sup>1</sup>[ ... ] — the amended span, with its marker.
_SPAN_OPEN = re.compile(r"<sup>\s*(\d{1,3})\s*</sup>\s*\[")
# Prior wording quoted in a footnote: Subs. ... for "the old words"  /  for the words "X"
_PRIOR = re.compile(r'\bfor\s+(?:the\s+(?:words?|figures?|brackets?|letters?)\s+)?[""“"]([^""”"]{2,400})[""”"]', re.I)


@dataclass(frozen=True)
class Reconstruction:
    section_id: str
    as_of: date
    fidelity: Fidelity
    text: str | None
    in_force: list[Amendment] = field(default_factory=list)
    not_yet_in_force: list[Amendment] = field(default_factory=list)
    unknown_spans: list[int] = field(default_factory=list)
    note: str = ""


def prior_wording(a: Amendment) -> str | None:
    """The wording a substitution/omission replaced, when the footnote quotes it."""
    m = _PRIOR.search(a.raw)
    return m.group(1).strip() if m else None


def _find_span(html: str, marker: int) -> tuple[int, int, int] | None:
    """(open_start, inner_start, close_end) for <sup>N</sup>[ ... ], bracket-balanced."""
    for m in _SPAN_OPEN.finditer(html):
        if int(m.group(1)) != marker:
            continue
        inner = m.end()
        depth = 1
        i = inner
        while i < len(html):
            if html[i] == "[":
                depth += 1
            elif html[i] == "]":
                depth -= 1
                if depth == 0:
                    return m.start(), inner, i + 1
            i += 1
        # Unbalanced markup in the source. Swallowing to end-of-document would let one rollback
        # destroy every later span in the section (observed: 1323:m2 captured 8,777 chars and
        # obliterated m4). Refuse instead.
        return None
    return None


def section_as_of(record: dict, target: date) -> Reconstruction:
    """Reconstruct one ingested section record as it stood on `target`."""
    sid = record.get("section_id", "?")
    content = record.get("content") or ""
    amendments = parse_footnote(record.get("footnote") or "")

    if target < COMMENCEMENT:
        return Reconstruction(
            sid, target, "ABSTAIN", None,
            note=f"{target} precedes the commencement of the Companies Act 2013 "
                 f"({COMMENCEMENT}). The governing law was the Companies Act 1956, "
                 f"which is not in this corpus.")

    dated = [a for a in amendments if a.wef and not a.wef_implausible]
    in_force = [a for a in dated if a.wef <= target]
    pending = [a for a in dated if a.wef > target]

    text = content
    unknown: list[int] = []

    # Roll back, latest first, so earlier offsets stay valid.
    for a in sorted(pending, key=lambda x: x.wef, reverse=True):
        span = _find_span(text, a.marker)
        if span is None:
            # The footnote records a change we cannot locate in the body - the source omits the
            # bracket delimiters, mis-numbers the superscript, or the markup is unbalanced. We
            # cannot roll it back and we must not pretend we did.
            if a.marker not in unknown:
                unknown.append(a.marker)
            continue
        open_s, inner_s, close_e = span
        if a.operation == "inserted":
            text = text[:open_s] + text[close_e:]          # did not exist yet
        elif a.operation in ("substituted", "omitted"):
            old = prior_wording(a)
            if old is not None:
                text = text[:open_s] + old + text[close_e:]  # restore quoted prior wording
            else:
                unknown.append(a.marker)
        else:
            unknown.append(a.marker)

    # An amendment with no effective date cannot be placed on a timeline, so it can neither be
    # applied nor rolled back. Ground-truth testing against the as-enacted print showed sections
    # in exactly this position were still claiming EXACT — a false claim of completeness, which is
    # the one thing this engine must never make. They are now PARTIAL, and the markers are named.
    # The "not a.ibid" carve-out let undated ibid amendments escape the downgrade entirely -
    # 49349:m4 was neither rolled back nor named. That is the false-completeness failure this
    # downgrade exists to prevent, surviving in the ibid branch.
    undated = [a for a in amendments if a.wef is None]
    implausible = [a for a in amendments if a.wef_implausible]
    for a in undated + implausible:
        if _find_span(text, a.marker) is not None and a.marker not in unknown:
            unknown.append(a.marker)

    fidelity: Fidelity = "EXACT" if not unknown else "PARTIAL"
    notes: list[str] = []
    if unknown:
        notes.append(
            f"Cannot fully reconstruct: marker(s) {sorted(unknown)}. Either the footnote records a "
            f"change without quoting the earlier text, or the amendment carries no usable effective "
            f"date in the source. Verify against the amending instrument.")
    if undated:
        notes.append(f"{len(undated)} amendment(s) carry no effective date in the source.")
    if implausible:
        notes.append(f"{len(implausible)} amendment(s) carry an implausible date in the source "
                     f"and were excluded from the timeline.")
    note = " ".join(notes)

    return Reconstruction(sid, target, fidelity, text, in_force, pending, sorted(unknown), note)


# --- self-test against the real ingested corpus ------------------------------

def _test() -> None:
    import json
    from pathlib import Path
    ok = fail = 0

    def check(c: bool, label: str) -> None:
        nonlocal ok, fail
        if c:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    d = Path(__file__).resolve().parent.parent / "corpus/companies_act"
    s2 = json.loads((d / "185.json").read_text())     # s.2 Definitions, 16+ markers
    s3a = json.loads((d / "48973.json").read_text())  # s.3A, inserted w.e.f. 9-2-2018

    r = section_as_of(s2, date(2013, 1, 1))
    check(r.fidelity == "ABSTAIN", "pre-commencement date abstains")
    check(r.text is None and "1956" in r.note, "abstention explains why, cites the 1956 Act")

    # s.3A was inserted w.e.f. 9 Feb 2018.
    before = section_as_of(s3a, date(2017, 1, 1))
    after = section_as_of(s3a, date(2019, 1, 1))
    check(len(before.not_yet_in_force) == 1, "s.3A: insertion pending in 2017")
    check(len(after.in_force) == 1, "s.3A: insertion in force in 2019")
    check(len(after.text) > len(before.text), "s.3A: 2017 text shorter than 2019 — span rolled back")
    check(before.fidelity == "EXACT", "s.3A: rollback of an insertion is exact")

    # s.2 across three past dates.
    d2015 = section_as_of(s2, date(2015, 6, 1))
    d2019 = section_as_of(s2, date(2019, 6, 1))
    d2026 = section_as_of(s2, date(2026, 6, 1))
    check(len(d2015.in_force) < len(d2019.in_force) < len(d2026.in_force),
          "s.2: amendments in force increase monotonically 2015 < 2019 < 2026")
    check(len(d2015.text) < len(d2026.text), "s.2: 2015 text shorter than 2026")
    check(all(a.wef <= date(2015, 6, 1) for a in d2015.in_force), "s.2: no future amendment in force")
    check(d2015.fidelity in ("EXACT", "PARTIAL"), "s.2: 2015 reconstruction produced")
    if d2015.fidelity == "PARTIAL":
        check(bool(d2015.unknown_spans) and "Cannot fully reconstruct" in d2015.note,
              "s.2: PARTIAL names the unrecoverable markers rather than guessing")

    # the implausible source date must never enter the timeline
    bad = json.loads((d / "48977.json").read_text())
    rb = section_as_of(bad, date(2018, 1, 1))
    check(all(not a.wef_implausible for a in rb.in_force + rb.not_yet_in_force),
          "implausible source date excluded from reconstruction")

    # Regression: ground-truth testing found sections with UNDATED amendments still claiming
    # EXACT. An undated amendment cannot be placed on a timeline, so completeness cannot be
    # claimed. 49349 has one; it must now be PARTIAL.
    undated_case = json.loads((d / "49349.json").read_text())
    ru = section_as_of(undated_case, date(2016, 1, 1))
    check(ru.fidelity == "PARTIAL", "section with an undated amendment cannot claim EXACT")
    check(bool(ru.unknown_spans) and "Verify against the amending instrument" in ru.note,
          "PARTIAL names the markers and tells the professional where to look")

    check(prior_wording(type("A", (), {"raw": 'Subs. by Act 33 of 2021, s. 28, for "Part XIV of Chapter VI"'})()) 
          == "Part XIV of Chapter VI", "prior wording extracted when the footnote quotes it")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
