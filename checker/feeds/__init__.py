"""The `Feed` protocol: one adapter shape over heterogeneous live sources.

## Where this comes from

Ported from `bilawalsidhu/gods-eye-view`'s `server/providers/` (MIT), read via
`gh api` on 2026-09-17 -- `common/http.js`, `common/rate-limit.js`,
`common/request.js`, `common/source-root.js`, and one concrete adapter,
`vessels/ais-store.js`. That repo factors ~20 heterogeneous live sources (vessel
AIS, aircraft ADS-B, weather, ...) over one shared interface plus shared
http/rate-limit machinery. THAT SHAPE -- one small set of common plumbing,
adapters that each carry a name, a fetch, and a parse -- is what is ported here.
No code and no data crossed over: the JS is MIT but the bundled feed *data* is
not, and this module holds neither.

`ais-store.js` is the clearest example of why the shape needs three more fields
before it fits this repository. It keeps one mutable, in-memory, single-actuality
cache: a vessel's newest fix simply overwrites the last one (`_aisStreamVessels.set(mmsi, {...})`),
staleness is handled by pruning entries older than `AISSTREAM_STALE_MS`, and
nothing about the record's *licence* or *legal reliability window* is modeled --
because AIS position data doesn't need either. Corporate-law evidence does:

  - `licence`     Axis D. Whether a fact may be shown to a PAYING customer is a
                   legal question, independent of whether it is true.
  - `source_behaviour`  How the source behaved, INCLUDING a refusal. Ported from
                   `checker.provenance.ACCESSIBILITY_STATES`, which this module
                   reuses rather than re-inventing a fourth vocabulary for the
                   same four things (`ACCESSIBLE` / `BLOCKED` / `UNREACHABLE` /
                   `NOT_FOUND`) -- see `checker/provenance.py`'s own docstring on
                   why a 404 is not the same fact as a timeout.
  - `blindness`   FLOOR / CEILING / EITHER, imported from `checker.mca_snapshot`
                   for the same reason: `mca_snapshot.py`'s whole point is that
                   the registry holds FILINGS, not events, and the Act grants a
                   window between them, so `Active Charges: 0` is a FLOOR, not
                   "unencumbered". A live feed's fetched value is exactly that
                   kind of filing -- current as of a filing, not as of the world.

## Two objects, echoing a split this repo already made once

`checker/provenance.py` grades an artifact we HOLD. `checker/acquisition_log.py`
grades an ATTEMPT to obtain one, including every attempt that produced nothing.
This module makes the same split for live feeds:

  - `FetchResult`   what happened when we asked a source for bytes -- including a
                     refusal, a redirect we declined to follow, or a body too
                     large to buffer. Mirrors `AttemptRecord`.
  - `Observation`   what we think the bytes said, once accessible. Mirrors an
                     artifact entry in `provenance.py` -- except it stops one
                     step short on purpose (see below).

## `Observation` is Ring 2 output. It is not, and cannot become, a verified fact.

`checker/provenance.py` defines a promotion ladder ending in `VERIFIED` --
"hashed local artifact + human review". `Observation` is a **different type**,
deliberately outside that ladder: it has no `promote()`, no path to `VERIFIED`,
and nothing in this module ever constructs a `provenance` state from one. A
live feed is unattended machine ingestion of a third party's bytes; treating its
output as though it had passed the same bar as a hand-verified corpus entry is
exactly the "toolchain output as a fact about the world" failure that
`checker/pdf_pages.py` and `checker/mca_snapshot.py` each independently name.
Downstream code that wants to promote an `Observation` into something citable
must do real work to get there -- this module refuses to make that look free by
returning the same shape.

## Axis D has no default, anywhere in this file

`may_serve_commercially()` requires a licence position on every call; nothing in
this module ships a default licence, and `Observation`/`FetchResult` do not
default `licence`/`source_behaviour` either. A live source's own redistribution
terms are a fact to be *found*, not assumed from what kind of body publishes it --
"government-published" is not "public domain" until the source says so in its
own words (see `checker/feeds/common/fetch.py` for the concrete case this bit).
Where that hasn't been confirmed, `LICENCE_UNVERIFIED` exists precisely so
nobody has to guess.

Run: python3 checker/feeds/__init__.py
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from checker.mca_snapshot import CEILING, EITHER, FLOOR
from checker.provenance import (ACCESSIBLE, ACCESSIBILITY_STATES, BLOCKED, NOT_FOUND,
                                UNREACHABLE)

# ── blindness direction: one definition, reused from mca_snapshot.py ────────────
BLINDNESS_STATES = (FLOOR, CEILING, EITHER)

# ── Axis D: may this be shown to a paying customer? ─────────────────────────────
PUBLIC_DOMAIN = "PUBLIC_DOMAIN"          # the source states this itself; not inferred from who published it
ATTRIBUTION = "ATTRIBUTION"              # servable, with attribution to the source
CONTRACT_ONLY = "CONTRACT_ONLY"          # servable only under the terms of a specific, named contract
NONCOMMERCIAL = "NONCOMMERCIAL"          # e.g. CC BY-NC. Never servable commercially. Internal reasoning only.
LICENCE_UNVERIFIED = "LICENCE_UNVERIFIED"  # the source's own redistribution terms were not found

LICENCES = (PUBLIC_DOMAIN, ATTRIBUTION, CONTRACT_ONLY, NONCOMMERCIAL, LICENCE_UNVERIFIED)

# Never servable to a paying customer without further work. NONCOMMERCIAL is a source
# that affirmatively restricts; LICENCE_UNVERIFIED is us not yet knowing -- CLAUDE.md's
# "if evidence is incomplete, write UNVERIFIED, do not guess" applies to licence terms
# exactly as it applies to a legal claim. The two reasons are different; the answer
# ("no, not yet") is currently the same for both.
_NEVER_COMMERCIAL = (NONCOMMERCIAL, LICENCE_UNVERIFIED)


def may_serve_commercially(licence: str) -> tuple[bool, str]:
    """Whether an Observation carrying this licence may be shown to a paying customer.

    Raises on an invented licence rather than defaulting it to permissive or
    refused -- an unknown value is a bug in the caller, not a policy question.
    """
    if licence not in LICENCES:
        raise ValueError(f"{licence!r} is not a licence position; one of {LICENCES}")
    if licence == NONCOMMERCIAL:
        return False, "NONCOMMERCIAL: ingestible for internal reasoning only, never servable commercially"
    if licence == LICENCE_UNVERIFIED:
        return False, "LICENCE_UNVERIFIED: the source's own redistribution terms were not found; refuse until confirmed, do not assume"
    if licence == CONTRACT_ONLY:
        return True, "CONTRACT_ONLY: servable only under the governing contract's terms"
    if licence == ATTRIBUTION:
        return True, "ATTRIBUTION: servable with attribution to the source"
    return True, ""  # PUBLIC_DOMAIN


# ── shared validators ────────────────────────────────────────────────────────
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Same shape as acquisition_log.py's own timestamp field, deliberately: a bitemporal
# known_at and an acquisition-attempt timestamp must never quietly drift into two
# different formats.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256.match(value):
        raise ValueError(f"{label} must be a 64-character lowercase hex sha256, got {value!r}")


def _require_timestamp(value: str, label: str) -> None:
    if not _TIMESTAMP.match(value):
        raise ValueError(f"{label} must be an ISO-8601 date or UTC datetime, got {value!r}")


@dataclass(frozen=True)
class FetchResult:
    """What happened when we asked a source for bytes. Mirrors `AttemptRecord` in
    `checker/acquisition_log.py`: it exists to record an attempt, not just a success.

    `url` is ALWAYS the stable entry URL a feed was asked to fetch -- never a
    resolved redirect target, which for at least one real source (see
    `checker/feeds/common/fetch.py`) is a pre-signed link that expires within the
    hour. `resolved_host` names a redirect target only when one was explicitly
    trusted and followed; it is metadata about the transaction, never an identity
    to cache against.
    """

    source_id: str
    url: str
    sha256: str
    content: bytes
    source_behaviour: str          # one of checker.provenance.ACCESSIBILITY_STATES
    http_status: int | None = None
    resolved_host: str = ""        # set only when an explicitly-trusted redirect was followed
    note: str = ""                 # why, when the answer isn't just "it worked"

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("a FetchResult must name its source_id -- an unnamed fetch proves nothing")
        if not self.url:
            raise ValueError(f"{self.source_id}: a FetchResult must carry the entry url it was asked to fetch")
        if self.source_behaviour not in ACCESSIBILITY_STATES:
            raise ValueError(
                f"{self.source_id}: {self.source_behaviour!r} is not an accessibility state; "
                f"one of {ACCESSIBILITY_STATES}")
        _require_sha256(self.sha256, f"{self.source_id}: FetchResult.sha256")
        computed = hashlib.sha256(self.content).hexdigest()
        if computed != self.sha256:
            raise ValueError(
                f"{self.source_id}: sha256 {self.sha256} does not match the content's actual "
                f"hash {computed} -- a FetchResult may not claim a hash it does not carry")
        # A 404, a refusal, or an outage is evidence of nothing about the target. Carrying
        # bytes of an error page or a robots-refusal message as "the content" would be
        # exactly the toolchain-as-evidence failure this repo has hit before.
        if self.source_behaviour != ACCESSIBLE and self.content:
            raise ValueError(
                f"{self.source_id}: source_behaviour={self.source_behaviour!r} but content is "
                f"non-empty -- a refusal or outage must carry no bytes")


@dataclass(frozen=True)
class Observation:
    """One feed's read of a live source, at a moment. RING 2 OUTPUT ONLY.

    This is a DISTINCT TYPE from anything in `checker/provenance.py`'s
    ACCESSIBLE/CORROBORATED/VERIFIED ladder, and deliberately has no method that
    produces one. `Observation` is what a feed *claims*; it becomes evidence only
    once something outside this module hashes it, corroborates it, and has a
    human look at it -- the same bar `provenance.py` already enforces for every
    other artifact in this repository. Treating an `Observation` as a
    `VERIFIED_FACT` is a category error this type exists to make impossible to
    make by accident: there is no field to mistake for one, and no cast between
    the two.
    """

    source_id: str
    content_sha256: str
    observed_at: str      # bitemporal "known_at" -- when we came to know this, not when it happened
    licence: str           # Axis D. No default: see this module's docstring.
    source_behaviour: str  # one of checker.provenance.ACCESSIBILITY_STATES
    blindness: str          # FLOOR / CEILING / EITHER, from checker.mca_snapshot
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("an unnamed Observation is not evidence -- source_id is required")
        _require_sha256(self.content_sha256, f"{self.source_id}: Observation.content_sha256")
        _require_timestamp(self.observed_at, f"{self.source_id}: Observation.observed_at")
        if self.licence not in LICENCES:
            raise ValueError(f"{self.source_id}: {self.licence!r} is not a licence position; one of {LICENCES}")
        if self.source_behaviour not in ACCESSIBILITY_STATES:
            raise ValueError(
                f"{self.source_id}: {self.source_behaviour!r} is not an accessibility state; "
                f"one of {ACCESSIBILITY_STATES}")
        if self.blindness not in BLINDNESS_STATES:
            raise ValueError(f"{self.source_id}: {self.blindness!r} is not a blindness state; one of {BLINDNESS_STATES}")
        # The same invariant as FetchResult, for the same reason: a 404 is evidence of
        # nothing, so an Observation built from one may not carry parsed fields.
        if self.source_behaviour != ACCESSIBLE and self.payload:
            raise ValueError(
                f"{self.source_id}: source_behaviour={self.source_behaviour!r} but payload is "
                f"non-empty -- a refusal or outage is evidence of nothing, not partial data")

    def is_servable_commercially(self) -> tuple[bool, str]:
        return may_serve_commercially(self.licence)


@runtime_checkable
class Feed(Protocol):
    """Uniform adapter shape, ported from gods-eye-view's `server/providers/*`
    (see this module's docstring, STEP 1). Concrete adapters (a gazette feed, a
    listed-disclosures feed, an MCA-aggregator feed -- PLAN_15 §2 names three) are
    NOT built in this change; only the protocol and the shared plumbing under
    `checker/feeds/common/` are.

    Of the seven fields PLAN_15 §2.1 requires, two are static per adapter and two
    are methods; the remaining three (`observed_at`, `source_behaviour`,
    `blindness`) surface through the `FetchResult`/`Observation` that `fetch()`
    and `parse()` return, rather than living on the adapter itself -- a source's
    behaviour and an observation's staleness window are facts about ONE
    transaction, not fixed properties of the adapter that made it. Forcing them
    onto the adapter would mean either freezing them at construction time (wrong:
    the same feed sees ACCESSIBLE today and BLOCKED tomorrow) or silently picking
    "the last one seen" (exactly `ais-store.js`'s single-actuality cache, which is
    the pattern this repository's evidence needs cannot use).
    """

    source_id: str
    licence: str  # Axis D. No default -- see this module's docstring.

    def fetch(self, entry_url: str) -> FetchResult:
        """Bytes + sha256 for one entry URL. Mirrors checker/acquisition_log.py's
        AttemptRecord: called for its side of recording an attempt as much as for
        its bytes. Implementations route through checker.robots and fail closed --
        see checker/feeds/common/fetch.py."""
        ...

    def parse(self, result: FetchResult, *, observed_at: str, blindness: str) -> Observation:
        """FetchResult -> Observation. NEVER a verified fact -- see Observation's
        own docstring. `blindness` is supplied by the caller because only the
        concrete feed knows the statutory window (if any) that bounds its data,
        the way mca_snapshot.py's FIELDS table does per master-data column."""
        ...


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("feeds")

    # ── licences: the vocabulary and its meaning ─────────────────────────────
    check(set(LICENCES) == {PUBLIC_DOMAIN, ATTRIBUTION, CONTRACT_ONLY, NONCOMMERCIAL,
                            LICENCE_UNVERIFIED},
          "the required minimum licence positions are all present, plus LICENCE_UNVERIFIED")

    ok_pd, _ = may_serve_commercially(PUBLIC_DOMAIN)
    check(ok_pd, "PUBLIC_DOMAIN is servable commercially")
    ok_attr, why_attr = may_serve_commercially(ATTRIBUTION)
    check(ok_attr and "attribution" in why_attr.lower(), "ATTRIBUTION is servable, with attribution noted")
    ok_contract, why_contract = may_serve_commercially(CONTRACT_ONLY)
    check(ok_contract and "contract" in why_contract.lower(), "CONTRACT_ONLY is servable, under its contract")

    # ── negative control #1: NONCOMMERCIAL is refused for commercial serving ─
    ok_nc, why_nc = may_serve_commercially(NONCOMMERCIAL)
    check(not ok_nc, "NONCOMMERCIAL is refused for commercial serving")
    check("never" in why_nc.lower(), f"...and says why: {why_nc}")

    # ── negative control #2: an UNVERIFIED licence is refused too, not assumed permissive ─
    ok_uv, why_uv = may_serve_commercially(LICENCE_UNVERIFIED)
    check(not ok_uv, "LICENCE_UNVERIFIED is refused for commercial serving -- absence of a "
                     "known restriction is not evidence of permission")
    check("not found" in why_uv.lower() or "not yet" in why_uv.lower(),
          f"...and the reason names the actual gap, not an invented one: {why_uv}")

    try:
        may_serve_commercially("PROBABLY_FINE")
        check(False, "an invented licence position must raise")
    except ValueError:
        check(True, "an invented licence position is rejected rather than defaulted")

    # ── blindness reuses mca_snapshot.py's own constants, not a re-invented copy ─
    from checker import mca_snapshot
    check(BLINDNESS_STATES == (mca_snapshot.FLOOR, mca_snapshot.CEILING, mca_snapshot.EITHER),
          "blindness states are imported from mca_snapshot.py, not redefined")

    # ── source_behaviour reuses provenance.py's accessibility states ─────────
    from checker import provenance
    check(ACCESSIBILITY_STATES == provenance.ACCESSIBILITY_STATES,
          "source_behaviour vocabulary is imported from provenance.py, not redefined")

    # ── FetchResult: hash integrity ──────────────────────────────────────────
    body = b"<sdn>example</sdn>"
    good_hash = hashlib.sha256(body).hexdigest()
    fr = FetchResult(source_id="TEST_FEED", url="https://example.gov/x", sha256=good_hash,
                     content=body, source_behaviour=ACCESSIBLE, http_status=200)
    check(fr.sha256 == good_hash, "a well-formed FetchResult constructs")

    try:
        FetchResult(source_id="TEST_FEED", url="https://example.gov/x", sha256=EMPTY_SHA256,
                   content=body, source_behaviour=ACCESSIBLE)
        check(False, "a FetchResult whose declared hash disagrees with its content must raise")
    except ValueError as e:
        check("does not match" in str(e), f"...and it does: {e}")

    # ── negative control #3: a refusal cannot smuggle content ────────────────
    try:
        FetchResult(source_id="TEST_FEED", url="https://example.gov/x", sha256=good_hash,
                   content=body, source_behaviour=NOT_FOUND, http_status=404)
        check(False, "a NOT_FOUND FetchResult carrying non-empty content must raise")
    except ValueError as e:
        check("no bytes" in str(e), f"...and it does -- a 404 is evidence of nothing: {e}")

    for bad_state in ("SUCCESS", "MAYBE"):
        try:
            FetchResult(source_id="X", url="https://x", sha256=EMPTY_SHA256, content=b"",
                       source_behaviour=bad_state)
            check(False, f"an invented source_behaviour {bad_state!r} must be rejected")
        except ValueError:
            check(True, f"an invented source_behaviour {bad_state!r} is rejected")

    try:
        FetchResult(source_id="", url="https://x", sha256=EMPTY_SHA256, content=b"",
                   source_behaviour=UNREACHABLE, note="x")
        check(False, "an unnamed FetchResult must be rejected")
    except ValueError:
        check(True, "an unnamed FetchResult is rejected -- an unnamed observation is not evidence")

    # ── Observation: construction and its own refusal invariant ─────────────
    obs = Observation(source_id="TEST_FEED", content_sha256=good_hash, observed_at="2026-09-17",
                      licence=PUBLIC_DOMAIN, source_behaviour=ACCESSIBLE, blindness=FLOOR,
                      payload={"charges": 0})
    check(obs.payload == {"charges": 0}, "a well-formed Observation constructs")
    check(isinstance(obs, Observation) and not hasattr(obs, "promote"),
          "Observation has no promotion path into provenance.py's VERIFIED ladder")

    try:
        Observation(source_id="X", content_sha256=good_hash, observed_at="2026-09-17",
                   licence=PUBLIC_DOMAIN, source_behaviour=BLOCKED, blindness=FLOOR,
                   payload={"charges": 0})
        check(False, "a BLOCKED Observation carrying a non-empty payload must raise")
    except ValueError as e:
        check("evidence of nothing" in str(e), f"...and it does: {e}")

    for bad_kw, label in (
        (dict(licence="MAYBE"), "an invented licence"),
        (dict(blindness="SOMEWHAT"), "an invented blindness state"),
        (dict(observed_at="17-09-2026"), "a non-ISO observed_at"),
        (dict(content_sha256="not-a-hash"), "a malformed content_sha256"),
    ):
        base = dict(source_id="X", content_sha256=good_hash, observed_at="2026-09-17",
                   licence=PUBLIC_DOMAIN, source_behaviour=ACCESSIBLE, blindness=FLOOR)
        try:
            Observation(**{**base, **bad_kw})
            check(False, f"{label} must be rejected")
        except ValueError:
            check(True, f"{label} is rejected at construction")

    # ── negative control #4, end to end: NONCOMMERCIAL Observation refuses to serve ─
    nc_obs = Observation(source_id="SOME_NC_FEED", content_sha256=good_hash, observed_at="2026-09-17",
                         licence=NONCOMMERCIAL, source_behaviour=ACCESSIBLE, blindness=EITHER,
                         payload={"note": "internal reasoning only"})
    servable, why = nc_obs.is_servable_commercially()
    check(not servable, "an Observation built with licence=NONCOMMERCIAL refuses commercial serving")
    check("never" in why.lower(), f"...with a reason naming why: {why}")

    # ── Feed protocol: a minimal conforming adapter satisfies isinstance() ───
    class _FakeFeed:
        source_id = "FAKE_FEED"
        licence = LICENCE_UNVERIFIED

        def fetch(self, entry_url: str) -> FetchResult:
            return FetchResult(source_id=self.source_id, url=entry_url, sha256=EMPTY_SHA256,
                              content=b"", source_behaviour=NOT_FOUND, http_status=404)

        def parse(self, result: FetchResult, *, observed_at: str, blindness: str) -> Observation:
            return Observation(source_id=self.source_id, content_sha256=result.sha256,
                              observed_at=observed_at, licence=self.licence,
                              source_behaviour=result.source_behaviour, blindness=blindness)

    fake = _FakeFeed()
    check(isinstance(fake, Feed), "a conforming adapter satisfies the Feed protocol at runtime")

    class _NotAFeed:
        source_id = "INCOMPLETE"
        # no licence, no fetch, no parse

    check(not isinstance(_NotAFeed(), Feed), "an adapter missing fetch()/parse()/licence does not satisfy Feed")

    fr2 = fake.fetch("https://example.gov/sdn.xml")
    obs2 = fake.parse(fr2, observed_at="2026-09-17", blindness=EITHER)
    check(obs2.source_behaviour == NOT_FOUND and not obs2.payload,
          "the round trip through a conforming Feed preserves 'a 404 is evidence of nothing'")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
