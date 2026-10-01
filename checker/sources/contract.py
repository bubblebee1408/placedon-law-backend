#!/usr/bin/env python3
"""The five rules `checker/sources/` must obey, tested as one suite.

They live together rather than one per module because each spans two or three of them.
"a non-HELD result can never make a claim VERIFIED" is a statement about `tiers`,
`Evidence` and the adapters at once, and three per-module tests would let it pass three
times while the composition failed.

Written before the modules they test, and run against nothing: the first run was an
ImportError, which is the right kind of red.

Run: PYTHONPATH=. python3 checker/sources/contract.py --test
"""
from __future__ import annotations

import sys

from checker.sources.base import (FetchError, SourceError, check_payload, load,
                                  needs_terms)
from checker.sources.evidence import Evidence, EvidenceError
from checker.sources.terms import NoTermsRecord, attribution_for
from checker.sources.tiers import (ATTRIBUTION_REQUIRED, CLIENT, COMPANY_FACT, HELD,
                                   LICENSED, OFFICIAL_LIVE, TIERS, VERIFYING_TIERS,
                                   can_verify)


def _test() -> int:
    """The five rules the job named, tested against the package as a whole.

    These are written as the CONTRACT rather than per-module unit tests, because each one
    spans two or three modules -- "a non-HELD result can never make a claim VERIFIED" is a
    statement about tiers, Evidence and the adapters at once, and a per-module test would
    let it pass three times while the composition failed.
    """
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

    print("sources (package contract)")
    NOW = "2026-09-30T23:15:00+05:30"
    H = hashlib.sha256(b"x").hexdigest()

    # ── 1. a connector with no terms record fails to load ────────────────────
    class Nowhere:
        source_id, tier = "manupatra", LICENSED

        def search(self, query, *, as_of=None): return []
        def fetch(self, ref): raise NotImplementedError

    try:
        load(Nowhere())
        check(False, "1. a connector with no terms record fails to load")
    except NoTermsRecord as e:
        check("manupatra" in str(e),
              f"1. a connector with no terms record fails to load ({e!s:.54})")

    class Blocked:
        source_id, tier = "rbi", OFFICIAL_LIVE

        def search(self, query, *, as_of=None): return []
        def fetch(self, ref): raise NotImplementedError

    try:
        load(Blocked())
        check(False, "...and one whose terms record says BLOCKED also fails to load")
    except SourceError as e:
        check("418" in str(e) or "robots" in str(e),
              f"...and one whose record says BLOCKED also fails ({e!s:.50})")

    # HELD and CLIENT are exempt, and the exemption is narrow and stated.
    check(not needs_terms(HELD) and not needs_terms(CLIENT),
          "...HELD and CLIENT need no terms record: neither is a fetch from a third party")
    for t in (OFFICIAL_LIVE, LICENSED, COMPANY_FACT):
        check(needs_terms(t), f"...{t} DOES need one")

    # ── 2. a non-HELD result can never make a claim VERIFIED ─────────────────
    check(VERIFYING_TIERS == (HELD,), f"2. exactly one tier can verify: {VERIFYING_TIERS}")
    for t in TIERS:
        want = t == HELD
        check(can_verify(t) is want,
              f"...can_verify({t}) is {want}")
        ev = Evidence(tier=t, source="sebi" if t != CLIENT else "client",
                      url="https://x.gov.in/a" if t != CLIENT else "",
                      doc_id="" if t != CLIENT else H, fetched_at=NOW, sha256=H,
                      quoted_span="a quoted span",
                      attribution=attribution_for("sebi") if t in ATTRIBUTION_REQUIRED
                      else "")
        check(ev.can_verify is want, f"...an Evidence at {t} has can_verify={want}")

    # The composition: a pack of many tiers verifies only on its HELD rows.
    pack = [Evidence(tier=t, source="sebi", url="https://x.gov.in/a", fetched_at=NOW,
                     sha256=H, quoted_span="s",
                     attribution=attribution_for("sebi") if t in ATTRIBUTION_REQUIRED else "")
            for t in (OFFICIAL_LIVE, LICENSED, COMPANY_FACT)]
    check(not any(e.can_verify for e in pack),
          "...a pack with no HELD row cannot verify anything, however many rows it has")

    # ── 3. every Evidence carries tier, hash and time ────────────────────────
    for missing, why in [({"sha256": ""}, "hash"), ({"fetched_at": ""}, "time"),
                         ({"tier": ""}, "tier"), ({"quoted_span": ""}, "quoted span"),
                         ({"url": "", "doc_id": ""}, "url or doc_id")]:
        kw = dict(tier=HELD, source="held", url="https://indiacode.gov.in/a",
                  fetched_at=NOW, sha256=H, quoted_span="s")
        kw.update(missing)
        try:
            Evidence(**kw)
            check(False, f"3. Evidence without a {why} is refused")
        except EvidenceError as e:
            check(True, f"3. Evidence without a {why} is refused ({e!s:.42})")
    try:
        Evidence(tier=HELD, source="held", url="https://indiacode.gov.in/a",
                 fetched_at="2026-09-30", sha256=H, quoted_span="s")
        check(False, "...a date with no time of day is not a fetch time")
    except EvidenceError as e:
        check("timezone" in str(e) or "offset" in str(e),
              f"...a bare date is not a fetch time: it has no timezone ({e!s:.40})")
    try:
        Evidence(tier=HELD, source="held", url="https://indiacode.gov.in/a",
                 fetched_at=NOW, sha256="deadbeef", quoted_span="s")
        check(False, "...a short hash is refused")
    except EvidenceError as e:
        check("sha256" in str(e), f"...a truncated hash is refused ({e!s:.40})")

    # ── 4. a 200 carrying HTML where JSON or PDF was expected is an ERROR ────
    #     Not an empty result. This is the soft-404 CLAUDE.md exists to refuse: the
    #     Angular shell served 200/text/html where a document was asked for.
    import checker.robots as R
    shell = b"<!DOCTYPE html><html><head><title>Loading</title></head><body></body></html>"
    for expect, ct in [((R.JSON,), "text/html"), ((R.PDF,), "text/html"),
                       ((R.JSON, R.PDF), "text/html")]:
        try:
            check_payload(shell, expect=expect, content_type=ct,
                          url="https://indiacode.gov.in/bitstream/x")
            check(False, f"4. HTML where {expect} was expected raises")
        except FetchError as e:
            check("200 is not evidence" in str(e) or "Content-Type" in str(e),
                  f"4. HTML where {'/'.join(expect)} was expected RAISES ({e!s:.44})")
    check(check_payload(b'{"a":1}', expect=(R.JSON,), content_type="application/json",
                        url="https://x/a") is None,
          "...real JSON passes and returns None")
    try:
        check_payload(b"", expect=(R.JSON,), content_type="application/json", url="https://x/a")
        check(False, "...an EMPTY 200 is also an error, not an empty result")
    except FetchError:
        check(True, "...an empty 200 is an error too, not an empty result")

    # ── 5. LICENSED results always carry their attribution string ────────────
    ik = attribution_for("indiankanoon")
    try:
        Evidence(tier=LICENSED, source="indiankanoon", url="https://indiankanoon.org/doc/1/",
                 fetched_at=NOW, sha256=H, quoted_span="held that...")
        check(False, "5. a LICENSED Evidence with no attribution is refused")
    except EvidenceError as e:
        check("attribution" in str(e),
              f"5. a LICENSED Evidence with no attribution is refused ({e!s:.40})")
    try:
        Evidence(tier=LICENSED, source="indiankanoon", url="https://indiankanoon.org/doc/1/",
                 fetched_at=NOW, sha256=H, quoted_span="held that...",
                 attribution="Powered by IKanoon")
        check(False, "...and an attribution that is NOT the terms' words is refused")
    except EvidenceError as e:
        check("terms" in str(e),
              f"...an invented attribution is refused: the terms require the LOGO, and "
              f"'Powered by IKanoon' is the text PLAN_26 guessed ({e!s:.34})")
    good = Evidence(tier=LICENSED, source="indiankanoon",
                    url="https://indiankanoon.org/doc/1/", fetched_at=NOW, sha256=H,
                    quoted_span="held that...", attribution=ik)
    check(good.attribution == ik and "Retrieval-Augmented Generation" in good.attribution,
          "...the terms' own words are accepted, RAG clause included")
    check(ATTRIBUTION_REQUIRED == (LICENSED, COMPANY_FACT),
          f"...attribution is required for {ATTRIBUTION_REQUIRED}, the tiers whose terms "
          f"demand it")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
