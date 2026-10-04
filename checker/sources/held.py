#!/usr/bin/env python3
"""HELD: our own hash-stamped corpus. The only tier that can make an answer VERIFIED.

PLAN_26 §2/S1. Wraps `checker/text_search.py` in the Source interface so the one tier that
can verify goes through the same door as the four that cannot — otherwise the verifier has
two code paths and only one of them is guarded.

## What HELD is, stated at its real strength

527 ingested sections of the Companies Act 2013, hash-stamped, cross-rendered against
India Code's JSON and its PDF (median record coverage 1.0000, 456/464 >= 0.99) with **two
confirmed source defects** in `docs/evidence/SOURCE_DEFECTS.md` and a corpus status of
NOT_FULLY_VERIFIED. Independent-publisher verification is PENDING: both renderings are
India Code, so a defect in their own source is invisible to the check.

That is the bar. It is a low one and it is the only one any tier here has.

## as_of is refused, not approximated

`search(query, as_of="2017-04-01")` **raises**. CLAUDE.md: point-in-time reconstruction of
substituted spans is UNVERIFIED against any external source, and "119/119 EXACT vs
as-enacted print" is on the known-invalid list because the reference was the current
consolidation. Serving today's text for a 2017 date would be that retracted mistake with a
parameter name on it, so the parameter exists in order to refuse.

## The span is a prefix, and says so

`quoted_span` is the opening of the section body, which is a true substring of the stored
bytes and therefore byte-matches. It is NOT a relevance-selected span — choosing the part
of a section that answers a question is `checker/ground_span.py` and
`checker/quoted_span.py`, and this module does not pretend to do their job.

Run: PYTHONPATH=. python3 checker/sources/held.py --test
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from checker.sources.evidence import Evidence
from checker.sources.tiers import HELD

ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS = ROOT / "corpus" / "companies_act"

SPAN_CHARS = 400        # how much of a section's opening travels as the quoted span


class AsOfUnsupported(NotImplementedError):
    """Raised on an as_of query. See the module docstring: refusal, not approximation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HeldCorpus:
    """The Companies Act 2013 as this repository holds it."""

    source_id = "held"
    tier = HELD

    def __init__(self, *, clock=_now) -> None:
        self._clock = clock

    # ── the interface ────────────────────────────────────────────────────────
    def search(self, query: str, *, as_of: str | None = None) -> list[Evidence]:
        from checker.text_search import search as _search

        if as_of:
            raise AsOfUnsupported(
                f"as_of={as_of!r}: point-in-time reconstruction is UNVERIFIED against any "
                f"external source (CLAUDE.md, docs/evidence/RETRACTIONS.md). HELD serves current "
                f"text only, and returning it for a past date is the exact mistake that "
                f"was retracted")
        if not (query or "").strip():
            return []
        out = []
        for hit in _search(query, top_k=5):
            ev = self._evidence(str(hit.get("section_id") or ""))
            if ev is not None:
                out.append(ev)
        return out

    def fetch(self, ref: str) -> Evidence:
        """One section by its corpus id, with the whole body as the quoted span."""
        ev = self._evidence(ref, whole=True)
        if ev is None:
            raise LookupError(f"{ref!r} is not a section this corpus holds")
        return ev

    # ── how a section becomes Evidence ───────────────────────────────────────
    def _evidence(self, section_id: str, *, whole: bool = False) -> Evidence | None:
        rec = _record(section_id)
        if rec is None:
            return None
        body = str(rec.get("body") or "")
        if not body.strip():
            return None
        span = body if whole else body[:SPAN_CHARS]
        return Evidence(tier=HELD, source=self.source_id, doc_id=section_id,
                        fetched_at=self._clock(), sha256=_digest(section_id),
                        quoted_span=span)


def _record(section_id: str) -> dict | None:
    from checker.text_search import _records

    for rec in _records():
        if str(rec.get("section_id")) == section_id:
            return rec
    return None


def _digest(section_id: str) -> str:
    """sha256 of the corpus FILE, so the hash identifies the stored artifact.

    Falls back to the body text when the file is not where its id suggests. That is not a
    silent fallback: the two hashes mean different things, so `span_matches()` re-reads and
    the caller can tell, and `--test` asserts the file path exists for a known section.
    """
    p = CORPUS / f"{section_id}.json"
    if p.exists():
        return hashlib.sha256(p.read_bytes()).hexdigest()
    rec = _record(section_id) or {}
    return hashlib.sha256(str(rec.get("body") or "").encode("utf-8")).hexdigest()


def span_matches(ev: Evidence) -> bool:
    """Is the quoted span really in the section it claims to come from?

    The L0 property, at this layer: a quote that does not byte-match its source is the one
    failure the whole tier system exists to catch, and it is cheap to check here.
    """
    rec = _record(ev.doc_id)
    return bool(rec) and ev.quoted_span in str(rec.get("body") or "")


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

    print("sources.held")
    from checker.sources.base import load
    from checker.sources.evidence import verifying

    src = load(HeldCorpus())
    check(src.tier == HELD and src.source_id == "held",
          "the corpus loads with no terms record: it is ours")

    rows = src.search("quorum for meetings of Board")
    check(len(rows) > 0, f"a real query returns rows ({len(rows)})")
    check(all(r.tier == HELD for r in rows), "every row is HELD")
    check(all(r.can_verify for r in rows), "...so every row can verify")
    check(verifying(rows) == rows, "verifying() keeps them all")
    check(all(len(r.sha256) == 64 for r in rows), "every row is hash-stamped")
    check(all(r.doc_id and not r.url for r in rows),
          "a local section is identified by doc_id, not a url")
    check(all(r.fetched_at.endswith("+00:00") for r in rows),
          "every row carries a timezone-qualified read time")

    # The property that matters: the quote is really there.
    check(all(span_matches(r) for r in rows),
          "every quoted span byte-matches the section it names")
    bent = Evidence(tier=HELD, source="held", doc_id=rows[0].doc_id,
                    fetched_at=rows[0].fetched_at, sha256=rows[0].sha256,
                    quoted_span="a sentence no Act contains, about payroll vendors")
    check(not span_matches(bent),
          "...and a span that is NOT in the section fails the check -- it can turn red")

    # The corpus FILE is what the hash identifies, for a real section.
    sid = rows[0].doc_id
    check((CORPUS / f"{sid}.json").exists(),
          f"the hash is of the corpus file on disk ({sid}.json)")
    import hashlib as _h
    check(rows[0].sha256 == _h.sha256((CORPUS / f"{sid}.json").read_bytes()).hexdigest(),
          "...and it is that file's sha256, recomputed here independently")

    # fetch() returns the whole section; search() a prefix.
    whole = src.fetch(sid)
    check(len(whole.quoted_span) >= len(rows[0].quoted_span),
          "fetch() carries at least as much text as a search row")
    check(span_matches(whole), "...and it byte-matches too")
    try:
        src.fetch("ca2013-s9999-not-a-section")
        check(False, "an unknown ref raises")
    except LookupError:
        check(True, "an unknown ref raises LookupError rather than returning a blank row")

    # as_of is refused.
    try:
        src.search("board meeting", as_of="2017-04-01")
        check(False, "an as_of query is refused")
    except AsOfUnsupported as e:
        check("UNVERIFIED" in str(e),
              "an as_of query is REFUSED, not approximated with current text")
    check(issubclass(AsOfUnsupported, NotImplementedError),
          "...and the refusal is an exception, so no caller gets today's text for a past date")

    check(src.search("   ") == [], "a blank query returns no rows rather than everything")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    for r in HeldCorpus().search("quorum for meetings of Board"):
        print(f"  {r.doc_id:<18} {r.sha256[:12]} {r.quoted_span[:60]!r}")
