#!/usr/bin/env python3
"""The Source interface, the terms gate a connector loads through, and the payload check.

PLAN_24 §4: `Source.search(query, *, as_of) -> list[Evidence]` and
`Source.fetch(ref) -> Evidence`. Two methods, because two questions are being asked of
every source and conflating them is how a search result gets served as a document.

## The gate: nothing loads on an unread term

`load()` refuses a connector unless its tier is HELD or CLIENT -- the two that are not
fetches from a third party -- or `terms.py` holds a record saying we may fetch. After S0
that means five of the seven recorded sources cannot load a connector at all, which is the
measurement and not a temporary state.

**Why HELD and CLIENT are exempt, and why the exemption is this narrow.** HELD is
`corpus/companies_act/`, already ours and already hash-stamped. CLIENT is the tenant's own
upload. Neither has a third party whose terms could govern it, so demanding a terms record
would be demanding a record of nobody's terms. Every other tier reaches someone else's
server. The exemption is a function, `needs_terms()`, rather than an `if` inside `load()`,
so it is one thing to test and one thing to find.

## The payload check: a 200 is not evidence of what came back

`check_payload()` RAISES. That is the entire difference between it and
`robots.payload_refusal()`, which returns a string, and it is the point: CLAUDE.md's rule is
"a 200 of HTML where a PDF was expected is the silent failure this repository exists to
refuse", and a function whose bad news is a return value can be ignored by a caller that
treats it as "no results". An empty result set is an answer about the law. A soft-404 is not
an answer about anything.

`indiacode.gov.in/bitstream/...` is the measured case: HTTP 200, `text/html`, the Angular
shell, where a 3.2 MB PDF was expected.

Run: PYTHONPATH=. python3 checker/sources/base.py --test
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import checker.robots as robots
from checker.sources.evidence import Evidence
from checker.sources.terms import may_fetch, record_for
from checker.sources.tiers import CLIENT, HELD, TIERS, UnknownTier


class SourceError(RuntimeError):
    """A connector cannot be used. Raised at load, not discovered at query time."""


class FetchError(SourceError):
    """What came back is not what was asked for. NEVER reported as an empty result."""


# Tiers that are not a fetch from a third party, and so have no terms to read.
_NO_TERMS = (HELD, CLIENT)


@runtime_checkable
class Source(Protocol):
    """What every connector is, whatever it talks to.

    `as_of` is keyword-only and part of the interface even though only HELD can honour it,
    because a source that cannot answer as-of must SAY so rather than quietly serve today's
    text for a historical date. `held.py` raises; that is the intended shape.
    """
    source_id: str
    tier: str

    def search(self, query: str, *, as_of: str | None = None) -> list[Evidence]: ...

    def fetch(self, ref: str) -> Evidence: ...


def needs_terms(tier: str) -> bool:
    """Must a connector at this tier have a terms record before it may load?"""
    if tier not in TIERS:
        raise UnknownTier(f"{tier!r} is not a tier; one of {TIERS}")
    return tier not in _NO_TERMS


def load(source: Source) -> Source:
    """Return the connector, or raise. A connector that cannot load is never returned.

    Raises `NoTermsRecord` when there is no record at all -- a LookupError, so a caller
    cannot mistake it for a transient failure -- and `SourceError` when there is a record
    and it says no.
    """
    tier = getattr(source, "tier", "")
    source_id = getattr(source, "source_id", "")
    if tier not in TIERS:
        raise SourceError(
            f"{source_id or type(source).__name__}: tier {tier!r} is not one of {TIERS}. "
            f"A connector that cannot state its tier does not load (PLAN_24 §2)")
    if not source_id.strip():
        raise SourceError(f"a connector at tier {tier} must state its source_id")
    for name in ("search", "fetch"):
        if not callable(getattr(source, name, None)):
            raise SourceError(f"{source_id}: a Source must implement {name}()")
    if not needs_terms(tier):
        return source
    record_for(source_id)               # raises NoTermsRecord
    ok, why = may_fetch(source_id)
    if not ok:
        raise SourceError(
            f"{source_id}: its terms record refuses the fetch -- {why}. Never worked "
            f"around (CLAUDE.md: do not bypass the WAF, robots restrictions, access "
            f"controls, or source terms)")
    return source


def check_payload(body: bytes, *, expect: tuple[str, ...], content_type: str,
                  url: str) -> None:
    """Raise FetchError unless `body` is one of `expect`. Returns None on success.

    `expect` has no default, inherited deliberately from `robots.payload_refusal`: a caller
    that has not decided what it asked for has not decided whether it got it.
    """
    why = robots.payload_refusal(body, expect=expect, content_type=content_type)
    if why:
        raise FetchError(f"{url}: {why}")


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

    print("sources.base")

    from checker.sources.terms import NoTermsRecord
    from checker.sources.tiers import COMPANY_FACT, LICENSED, OFFICIAL_LIVE

    class Fake:
        def __init__(self, sid, tier):
            self.source_id, self.tier = sid, tier

        def search(self, query, *, as_of=None): return []
        def fetch(self, ref): raise NotImplementedError

    # The gate.
    check(load(Fake("held", HELD)) is not None, "a HELD connector loads with no terms record")
    check(load(Fake("client", CLIENT)) is not None, "a CLIENT connector loads likewise")
    for t in (OFFICIAL_LIVE, LICENSED, COMPANY_FACT):
        check(needs_terms(t), f"{t} needs a terms record")
    check(not needs_terms(HELD) and not needs_terms(CLIENT),
          "HELD and CLIENT do not -- there is no third party whose terms could govern them")

    try:
        load(Fake("manupatra", LICENSED))
        check(False, "an unrecorded source does not load")
    except NoTermsRecord:
        check(True, "an unrecorded source does not load (NoTermsRecord, a LookupError)")

    for sid, tier in [("rbi", OFFICIAL_LIVE), ("bse", COMPANY_FACT),
                      ("data_gov_in", COMPANY_FACT), ("nse", COMPANY_FACT),
                      ("egazette", OFFICIAL_LIVE)]:
        try:
            load(Fake(sid, tier))
            check(False, f"{sid} does not load: its record refuses")
        except SourceError as e:
            check("refuses the fetch" in str(e),
                  f"{sid} does not load: {str(e).split('--')[1].strip()[:46] if '--' in str(e) else ''}")
    for sid, tier in [("indiankanoon", LICENSED), ("sebi", OFFICIAL_LIVE)]:
        check(load(Fake(sid, tier)) is not None, f"{sid} DOES load: robots permit, terms read")

    # Shape checks.
    for bad_tier in ("", "WEB", "Held"):
        try:
            load(Fake("x", bad_tier))
            check(False, f"tier {bad_tier!r} does not load")
        except SourceError as e:
            check("not one of" in str(e),
                  f"a connector whose tier is {bad_tier!r} does not load")
    try:
        load(Fake("  ", HELD))
        check(False, "a blank source_id does not load")
    except SourceError as e:
        check("source_id" in str(e), "a blank source_id does not load")

    class Half:
        source_id, tier = "held", HELD

        def search(self, query, *, as_of=None): return []

    try:
        load(Half())
        check(False, "a connector with no fetch() does not load")
    except SourceError as e:
        check("fetch()" in str(e), "a connector missing fetch() does not load")

    # The payload check RAISES.
    shell = (b"<!DOCTYPE html><html><head><title>Themis</title></head>"
             b"<body><app-root></app-root></body></html>")
    for expect in [(robots.PDF,), (robots.JSON,), (robots.JSON, robots.PDF)]:
        try:
            check_payload(shell, expect=expect, content_type="text/html",
                          url="https://indiacode.gov.in/bitstream/x")
            check(False, f"the Angular shell is refused where {expect} was expected")
        except FetchError as e:
            check("bitstream" in str(e) and "200 is not evidence" in str(e),
                  f"soft-404 refused where {'/'.join(expect)} expected, naming the URL")
    check(check_payload(b"%PDF-1.7\nx", expect=(robots.PDF,),
                        content_type="application/pdf", url="https://x/a.pdf") is None,
          "a real PDF passes and returns None")
    check(check_payload(b'{"records": []}', expect=(robots.JSON,),
                        content_type="application/json", url="https://x/a") is None,
          "an EMPTY JSON result set passes -- no results is a legitimate answer")
    try:
        check_payload(b"", expect=(robots.JSON,), content_type="application/json",
                      url="https://x/a")
        check(False, "a zero-byte 200 is refused")
    except FetchError:
        check(True, "a zero-byte 200 is refused: nothing came back, which is not 'no results'")
    check(issubclass(FetchError, SourceError),
          "FetchError is a SourceError, so one except clause covers a connector's refusals")

    # A raising guard cannot be read as an empty list. This is the rule, asserted.
    swallowed = None
    try:
        check_payload(shell, expect=(robots.JSON,), content_type="text/html", url="https://x")
    except FetchError:
        swallowed = "raised"
    check(swallowed == "raised",
          "check_payload cannot be mistaken for an empty result: it has no return path "
          "for failure")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
