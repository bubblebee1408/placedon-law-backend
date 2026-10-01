#!/usr/bin/env python3
"""One result from one source, with everything needed to distrust it correctly.

PLAN_26 §4. The record is `{tier, source, url or doc_id, fetched_at, sha256, quoted_span,
attribution}` and every field is required for a reason that has already gone wrong
somewhere in this repository:

    tier          without it, a judgment and a statute are the same shape, and the
                  verifier has nothing to refuse on
    source        the source_id, so the terms that govern this row are findable
    url / doc_id  a result that cannot be pointed at cannot be checked by a lawyer
    fetched_at    "real time" in this product means READ AT THE MOMENT YOU ASK, with the
                  time shown. A result with no time is a result of unknown age
    sha256        of the bytes the span was taken from. Hash-stamped or it never happened
    quoted_span   the words themselves. `checker/quoted_span.py` is the L0 verifier and it
                  needs something to byte-match
    attribution   Indian Kanoon's terms require it for RAG context, not only for display

## Why the constructor is strict

Every check below is `raise`, never a default. A default is how an empty field becomes a
confident answer: the run that reported `E = Rs 0.0000 while spending on two models`
(2026-09-30) did it by defaulting one absent number to zero. An Evidence that cannot be
fully described does not exist.

**A bare date is not a fetch time.** `fetched_at` must carry a timezone offset. An IST
timestamp read as UTC is off by 5h30m, which is enough to put a fetch on the wrong side of
a commencement date -- and this product's whole claim is about what the law said *on a
date*.

Run: PYTHONPATH=. python3 checker/sources/evidence.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from checker.sources.terms import attribution_for
from checker.sources.tiers import ATTRIBUTION_REQUIRED, TIERS, can_verify

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """Raised on an Evidence that cannot be fully described. Never a warning."""


@dataclass(frozen=True)
class Evidence:
    tier: str
    source: str
    url: str = ""
    doc_id: str = ""
    fetched_at: str = ""
    sha256: str = ""
    quoted_span: str = ""
    attribution: str = ""

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise EvidenceError(f"tier {self.tier!r} is not one of {TIERS}")
        if not self.source.strip():
            raise EvidenceError("source is required: without it the terms that govern "
                                "this row cannot be found")
        if not (self.url.strip() or self.doc_id.strip()):
            raise EvidenceError(
                f"{self.source}: a url or a doc_id is required -- a result that cannot be "
                f"pointed at cannot be checked")
        if not _SHA256.match(self.sha256 or ""):
            raise EvidenceError(
                f"{self.source}: sha256 must be 64 lowercase hex characters, got "
                f"{self.sha256!r} -- hash-stamped or it never happened")
        if not self.quoted_span.strip():
            raise EvidenceError(
                f"{self.source}: a quoted_span is required -- checker/quoted_span.py has "
                f"nothing to byte-match without one")
        self._check_time()
        self._check_attribution()

    def _check_time(self) -> None:
        if not self.fetched_at.strip():
            raise EvidenceError(
                f"{self.source}: fetched_at is required -- a result with no time is a "
                f"result of unknown age, and freshness is what this tier system sells")
        try:
            when = datetime.fromisoformat(self.fetched_at)
        except ValueError as exc:
            raise EvidenceError(f"{self.source}: fetched_at {self.fetched_at!r} is not "
                                f"ISO 8601 ({exc})") from None
        if when.tzinfo is None:
            raise EvidenceError(
                f"{self.source}: fetched_at {self.fetched_at!r} has no timezone offset. "
                f"An IST reading parsed as UTC is 5h30m out, which is enough to put a "
                f"fetch on the wrong side of a commencement date")

    def _check_attribution(self) -> None:
        required = self.tier in ATTRIBUTION_REQUIRED
        if not required:
            return
        if not self.attribution.strip():
            raise EvidenceError(
                f"{self.source}: tier {self.tier} requires attribution and none was "
                f"given. Indian Kanoon's terms require it for RAG context, not only for "
                f"display, so an unattributed row cannot be shown or fed to a model")
        want = attribution_for(self.source)
        if not want:
            raise EvidenceError(
                f"{self.source}: tier {self.tier} requires attribution and the terms "
                f"record states none (its attribution clause is OPEN, i.e. unread). There "
                f"is no correct string to render, so this row cannot exist")
        if self.attribution.strip() != want.strip():
            raise EvidenceError(
                f"{self.source}: the attribution must be the terms' own words, not a "
                f"label we chose. PLAN_26 §2 guessed 'Powered by IKanoon'; the clause "
                f"actually requires the LOGO and names RAG context. Use "
                f"terms.attribution_for({self.source!r})")

    @property
    def can_verify(self) -> bool:
        """May a claim resting on THIS row be called VERIFIED? Only ever true for HELD."""
        return can_verify(self.tier)

    @property
    def ref(self) -> str:
        return self.url or self.doc_id


def verifying(pack: list) -> list:
    """The rows of a pack that may support a legal claim.

    A function rather than a caller's list comprehension because the mistake being
    prevented is a caller summarising a mixed pack as verified on the strength of its
    longest row. `checker/model_cascade.py` already learned this the other way round.
    """
    return [e for e in pack if e.can_verify]


def _test() -> int:
    import hashlib
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("sources.evidence")
    H = hashlib.sha256(b"the section text").hexdigest()
    NOW = "2026-09-30T23:15:00+05:30"

    e = Evidence(tier="HELD", source="held", doc_id="ca2013-s173", fetched_at=NOW,
                 sha256=H, quoted_span="Every company shall hold")
    check(e.can_verify, "a HELD row can verify")
    check(e.ref == "ca2013-s173", "ref falls back to doc_id when there is no url")

    # Time.
    for bad, why in [("", "absent"), ("2026-09-30", "a bare date"),
                     ("2026-09-30T23:15:00", "no offset"), ("yesterday", "not ISO")]:
        try:
            Evidence(tier="HELD", source="held", doc_id="x", fetched_at=bad, sha256=H,
                     quoted_span="s")
            check(False, f"fetched_at {why} is refused")
        except EvidenceError:
            check(True, f"fetched_at {why!r} is refused")
    check(Evidence(tier="HELD", source="held", doc_id="x",
                   fetched_at="2026-09-30T23:15:00Z", sha256=H,
                   quoted_span="s").fetched_at.endswith("Z"),
          "a Z-suffixed UTC timestamp is accepted")

    # Hash.
    for bad in ("", "deadbeef", H.upper(), H + "0", "z" * 64):
        try:
            Evidence(tier="HELD", source="held", doc_id="x", fetched_at=NOW, sha256=bad,
                     quoted_span="s")
            check(False, f"sha256 {bad[:12]!r} is refused")
        except EvidenceError:
            check(True, f"sha256 {bad[:12]!r} is refused (64 lowercase hex, exactly)")

    # Pointability and the span.
    try:
        Evidence(tier="HELD", source="held", fetched_at=NOW, sha256=H, quoted_span="s")
        check(False, "a row with neither url nor doc_id is refused")
    except EvidenceError as e2:
        check("pointed at" in str(e2), "a row with neither url nor doc_id is refused")
    try:
        Evidence(tier="HELD", source="held", doc_id="x", fetched_at=NOW, sha256=H,
                 quoted_span="   ")
        check(False, "a whitespace quoted_span is refused")
    except EvidenceError:
        check(True, "a whitespace quoted_span is refused, not just an empty one")

    # Attribution, the LICENSED rule.
    ik = attribution_for("indiankanoon")
    lic = dict(tier="LICENSED", source="indiankanoon",
               url="https://indiankanoon.org/doc/1/", fetched_at=NOW, sha256=H,
               quoted_span="held that")
    try:
        Evidence(**lic)
        check(False, "LICENSED with no attribution is refused")
    except EvidenceError as e2:
        check("requires attribution" in str(e2), "LICENSED with no attribution is refused")
    try:
        Evidence(**lic, attribution="Powered by IKanoon")
        check(False, "LICENSED with an invented attribution is refused")
    except EvidenceError as e2:
        check("terms' own words" in str(e2),
              "LICENSED with an invented attribution is refused")
    check(Evidence(**lic, attribution=ik).attribution == ik,
          "LICENSED with the terms' own words is accepted")
    check(not Evidence(**lic, attribution=ik).can_verify,
          "...and still cannot verify")

    # A LICENSED source whose attribution clause is OPEN cannot produce a row at all.
    try:
        Evidence(tier="LICENSED", source="bse", url="https://www.bseindia.com/x",
                 fetched_at=NOW, sha256=H, quoted_span="s", attribution="BSE")
        check(False, "a source with an OPEN attribution clause cannot produce a row")
    except EvidenceError as e2:
        check("OPEN" in str(e2),
              "a source whose attribution clause is UNREAD cannot produce a row: there is "
              "no correct string to render")

    # HELD and CLIENT need no attribution.
    check(Evidence(tier="CLIENT", source="client", doc_id=H, fetched_at=NOW, sha256=H,
                   quoted_span="the NDA says").attribution == "",
          "CLIENT needs no attribution -- it is the tenant's own document")

    # The pack helper.
    rows = [Evidence(tier="HELD", source="held", doc_id="a", fetched_at=NOW, sha256=H,
                     quoted_span="s"),
            Evidence(**lic, attribution=ik),
            Evidence(tier="CLIENT", source="client", doc_id=H, fetched_at=NOW, sha256=H,
                     quoted_span="s")]
    check(len(verifying(rows)) == 1 and verifying(rows)[0].tier == "HELD",
          "verifying() returns only the HELD row of a three-tier pack")
    check(verifying([r for r in rows if r.tier != "HELD"]) == [],
          "...and nothing at all when the pack has no HELD row")

    check(Evidence(tier="HELD", source="held", doc_id="a", fetched_at=NOW, sha256=H,
                   quoted_span="s") == Evidence(tier="HELD", source="held", doc_id="a",
                                                fetched_at=NOW, sha256=H, quoted_span="s"),
          "Evidence is frozen and compares by value")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
