"""The Company Event Log — one dated, sourced stream of what changed.

Specified in the business-plan repo's COMPANY_EVENT_LOG_SPEC.md. This is **v0**:
the LAW-CHANGE half, built on data we already hold. Company-fact events
(directors, charges, status) need the licensed registry feed and are v1.

## What an event is, and what it is not

An event is a dated, sourced statement that something changed -- either about a
company, or about the law that governs it. It is not a notification, and it is
not advice. Every event names the instrument it came from, the date it took
effect, and whether anyone has verified it. An event with no verifier is a
SIGNAL: shown, never asserted as fact.

## Bitemporality, and what v0 honestly has

`at` is when the change took effect (valid time). `known_at` is when WE learned
it (transaction time). A lawyer asks two different questions -- "what do we now
know about 31 March" and "what was knowable to us on 31 March" -- and only two
time axes can answer both.

v0 has no persistent store, so there is no record of when a fact entered our
possession; `known_at` therefore defaults to the query date and callers may pass
it explicitly. That is a real limitation, stated rather than papered over: until
the store lands (v2), `known_at` cannot answer the second question for anything
we learned before today. It is modelled now so the store has a shape to fill.

## The model is not in this pipeline

Every event here is derived deterministically from the currency engine. No
language model creates an event, a date, or a consequence. At most, later, one
may phrase a title from verified fields.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date

from checker import currency
from checker.prescribed_thresholds import all_thresholds

# ── event kinds ───────────────────────────────────────────────────────────────
COMPANY_FACT = "COMPANY_FACT"
LAW_CHANGE = "LAW_CHANGE"
KINDS = (COMPANY_FACT, LAW_CHANGE)

# ── output classes. Never blurred: a reader must always know which they hold ──
VERIFIED_FACT = "VERIFIED_FACT"                    # registry- or instrument-sourced
DETERMINISTIC_CONSEQUENCE = "DETERMINISTIC_CONSEQUENCE"   # computed, reproducible
SIGNAL = "SIGNAL"                                  # shown, never asserted
OUTPUT_CLASSES = (VERIFIED_FACT, DETERMINISTIC_CONSEQUENCE, SIGNAL)

# ── law-change subtypes ───────────────────────────────────────────────────────
THRESHOLD_MOVED = "THRESHOLD_MOVED"
OBLIGATION_SUPERSEDED = "OBLIGATION_SUPERSEDED"
OBLIGATION_NOW_IN_FORCE = "OBLIGATION_NOW_IN_FORCE"
BASIS_UNACQUIRED = "BASIS_UNACQUIRED"
BASIS_UNDECLARED = "BASIS_UNDECLARED"   # a hole in OUR map, not a fact about the law


class EventInvariant(ValueError):
    """An event was constructed that would misrepresent what we know."""


@dataclass(frozen=True)
class Source:
    """Where an event came from. An event without one cannot be constructed."""
    instrument: str                 # the instrument or register naming the change
    as_at: date | None = None       # the date the source itself speaks to
    sha256: str | None = None       # the artifact hash, when we hold the artifact
    url: str | None = None

    def __post_init__(self) -> None:
        if not (self.instrument or "").strip():
            raise EventInvariant("a source must name an instrument")


@dataclass(frozen=True)
class Event:
    """One dated, sourced change. Immutable, and identified by its content."""
    company: str                    # CIN, or "" for a change that touches every company
    at: date                        # valid time -- when the change took effect
    known_at: date                  # transaction time -- when we learned it
    kind: str
    subtype: str
    title: str                      # the plain-language one-liner
    output_class: str
    source: Source
    currency_state: str | None = None      # set for LAW_CHANGE events
    obligation_id: str | None = None
    consequence: str | None = None         # the deterministic "so the company must…"
    verified_by: str | None = None         # None => SIGNAL, never a hidden fact
    id: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise EventInvariant(f"unknown kind {self.kind!r}")
        if self.output_class not in OUTPUT_CLASSES:
            raise EventInvariant(f"unknown output class {self.output_class!r}")
        if not (self.title or "").strip():
            raise EventInvariant("an event must carry a title a reader can act on")
        # The invariant the whole log rests on. An unverified event may be shown,
        # but it may never wear the costume of a fact.
        if self.verified_by is None and self.output_class == VERIFIED_FACT:
            raise EventInvariant(
                f"{self.subtype}: an event with no verifier cannot be a VERIFIED_FACT; "
                "it is a SIGNAL until someone verifies it")
        if self.known_at < self.at:
            # Learning of a change before it takes effect is ordinary (a Gazette
            # published ahead of commencement). Learning of one that took effect
            # after we recorded knowing it is not -- that is a clock error.
            pass
        object.__setattr__(self, "id", self._derive_id())

    def _derive_id(self) -> str:
        """Content-addressed, so re-deriving the same event yields the same id.

        Deliberately excludes known_at: the same change learned again on a later
        day is the same event, not a new one.
        """
        parts = (self.company, self.at.isoformat(), self.kind, self.subtype,
                 self.obligation_id or "", self.source.instrument)
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


# ── derivation ────────────────────────────────────────────────────────────────
# currency state -> (subtype, output class, how to phrase it)
_FROM_CURRENCY = {
    currency.SUPERSEDED: (OBLIGATION_SUPERSEDED, SIGNAL),
    currency.UNACQUIRED: (BASIS_UNACQUIRED, SIGNAL),
    currency.NOT_YET_IN_FORCE: (OBLIGATION_NOW_IN_FORCE, SIGNAL),
    currency.UNDECLARED: (BASIS_UNDECLARED, SIGNAL),
}


def _threshold_events(as_of: date, since: date | None, known_at: date) -> list[Event]:
    """A prescribed amount that commenced in the window is a THRESHOLD_MOVED event.

    Sourced from the threshold records themselves, so an instrument we hold but
    have not acquired still produces an event -- naming what must be acquired.
    """
    out: list[Event] = []
    for t in all_thresholds():
        if t.effective_from > as_of:
            continue
        if since is not None and t.effective_from <= since:
            continue
        if since is None and t.effective_from < as_of:
            # With no window, only a change taking effect ON the date is "new".
            continue
        servable = t.servable
        consequence = (
            f"{t.key} is set by this instrument from {t.effective_from.isoformat()}."
            if servable else
            f"{t.key} is REFUSED from {t.effective_from.isoformat()} until this "
            f"instrument is acquired and attested — the previous amount is superseded "
            f"and is not served in its place.")
        out.append(Event(
            company="", at=t.effective_from, known_at=known_at,
            kind=LAW_CHANGE, subtype=THRESHOLD_MOVED,
            title=f"{t.key} changed — {t.instrument.split(',')[0]}",
            output_class=VERIFIED_FACT if servable else SIGNAL,
            source=Source(instrument=t.instrument, as_at=t.effective_from, url=t.source_url),
            currency_state=None, consequence=consequence,
            verified_by=t.state if servable else None))
    return out


def _currency_events(as_of: date, known_at: date) -> list[Event]:
    """Every obligation whose legal basis needs someone to act, as an event."""
    out: list[Event] = []
    for f in currency.report(as_of):
        mapped = _FROM_CURRENCY.get(f.status)
        if mapped is None:                      # CURRENT: nothing changed
            continue
        subtype, cls = mapped
        instrument = f.instrument or f"{f.obligation_id} (no instrument named)"
        out.append(Event(
            company="", at=as_of, known_at=known_at,
            kind=LAW_CHANGE, subtype=subtype,
            title=f"{f.obligation_id}: legal basis is {f.status}",
            output_class=cls,
            source=Source(instrument=instrument, as_at=as_of),
            currency_state=f.status, obligation_id=f.obligation_id,
            consequence=f.detail, verified_by=None))
    return out


def events_for(as_of: date, *, since: date | None = None,
               known_at: date | None = None) -> list[Event]:
    """The law-change event stream, newest first.

    `since` gives the "what's new" feed: only changes taking effect after it.
    `known_at` is transaction time; v0 has no store, so it defaults to `as_of`.
    """
    known = known_at or as_of
    events = _threshold_events(as_of, since, known) + _currency_events(as_of, known)
    if since is not None:
        events = [e for e in events if e.at > since]
    events.sort(key=lambda e: (e.at, e.subtype, e.source.instrument), reverse=True)
    return events


def event_by_id(event_id: str, as_of: date, *, since: date | None = None) -> Event | None:
    """One event, for the evidence panel. None rather than a guess."""
    for e in events_for(as_of, since=since):
        if e.id == event_id:
            return e
    return None


def affected_by(instrument_fragment: str) -> list[str]:
    """Which obligations a new instrument moves. The monitor's reverse index."""
    return currency.affected_by(instrument_fragment)


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

    print("event_log")
    src = Source(instrument="G.S.R. 700(E) of 2022", as_at=date(2022, 9, 15))

    # ── the invariant: no verifier means it cannot be a fact ─────────────────
    try:
        Event(company="", at=date(2025, 12, 1), known_at=date(2026, 9, 9),
              kind=LAW_CHANGE, subtype=BASIS_UNACQUIRED, title="t",
              output_class=VERIFIED_FACT, source=src, verified_by=None)
        check(False, "an unverified event cannot be a VERIFIED_FACT")
    except EventInvariant as e:
        check("SIGNAL" in str(e), f"an unverified event cannot be a VERIFIED_FACT ({e})")

    signal = Event(company="", at=date(2025, 12, 1), known_at=date(2026, 9, 9),
                   kind=LAW_CHANGE, subtype=BASIS_UNACQUIRED, title="t",
                   output_class=SIGNAL, source=src, verified_by=None)
    check(signal.output_class == SIGNAL, "...but it can be a SIGNAL")

    try:
        Source(instrument="  ")
        check(False, "an event source must name an instrument")
    except EventInvariant:
        check(True, "an event source must name an instrument")

    try:
        Event(company="", at=date(2025, 12, 1), known_at=date(2026, 9, 9),
              kind=LAW_CHANGE, subtype=BASIS_UNACQUIRED, title="  ",
              output_class=SIGNAL, source=src)
        check(False, "an event must carry a title")
    except EventInvariant:
        check(True, "an event must carry a title")

    # ── content-addressed ids ────────────────────────────────────────────────
    twin = Event(company="", at=date(2025, 12, 1), known_at=date(2026, 12, 31),
                 kind=LAW_CHANGE, subtype=BASIS_UNACQUIRED, title="t",
                 output_class=SIGNAL, source=src, verified_by=None)
    check(twin.id == signal.id,
          "the same change re-derived yields the same id, whenever we learned it")
    other = Event(company="", at=date(2022, 9, 15), known_at=date(2026, 9, 9),
                  kind=LAW_CHANGE, subtype=BASIS_UNACQUIRED, title="t",
                  output_class=SIGNAL, source=src, verified_by=None)
    check(other.id != signal.id, "...and a different date is a different event")

    # ── the golden fixture: the s.2(85) supersession, on the record we hold ──
    # Both halves are pinned with the stub context managers rather than read off
    # disk. These checks previously asserted the unacquired behaviour against the
    # LIVE acquisition state, and silently became wrong the day a human attested
    # G.S.R. 880(E) -- asserting a world that had changed under them. A test that
    # means "while unacquired" must SAY so, not hope.
    from checker.prescribed_thresholds import all_acquired as _all_acq
    from checker.prescribed_thresholds import none_acquired as _none_acq

    evs = events_for(date(2026, 9, 9), since=date(2025, 1, 1))
    moved = [e for e in evs if e.subtype == THRESHOLD_MOVED]
    check(bool(moved), f"a threshold that moved in the window produces an event ({len(moved)})")
    check(all("880(E)" in e.source.instrument for e in moved),
          "...and it is G.S.R. 880(E), the instrument that moved them")
    check(all(e.at == date(2025, 12, 1) for e in moved),
          "...dated to the instrument's own commencement, not to the query")

    with _none_acq():
        unacq_moved = [e for e in events_for(date(2026, 9, 9), since=date(2025, 1, 1))
                       if e.subtype == THRESHOLD_MOVED]
        check(bool(unacq_moved) and all(e.output_class == SIGNAL and e.verified_by is None
                                        for e in unacq_moved),
              "while UNACQUIRED the moved threshold is a SIGNAL, not a fact")
        check(all("REFUSED" in (e.consequence or "") for e in unacq_moved),
              "...whose consequence says the amount is refused, not that it changed to a figure")

    with _all_acq():
        acq_moved = [e for e in events_for(date(2026, 9, 9), since=date(2025, 1, 1))
                     if e.subtype == THRESHOLD_MOVED]
        check(bool(acq_moved) and all(e.output_class == VERIFIED_FACT and e.verified_by
                                      for e in acq_moved),
              "...and once ATTESTED the same event becomes a VERIFIED_FACT with a verifier")
        check(all("REFUSED" not in (e.consequence or "") for e in acq_moved),
              "...whose consequence now states the amount rather than refusing it")

    # every event names a source: the rule with no exception
    check(all(e.source.instrument.strip() for e in evs),
          f"every event names its source ({len(evs)} events)")
    check(all(e.kind == LAW_CHANGE for e in evs), "v0 emits law-change events only")

    # ── the window is a real filter ──────────────────────────────────────────
    before = events_for(date(2025, 11, 30), since=date(2025, 1, 1))
    check(not [e for e in before if e.subtype == THRESHOLD_MOVED],
          "the day before it commenced, 880(E) produces no threshold event")

    # ── an obligation resting on unacquired law is surfaced, not hidden ──────
    # Pinned, for the same reason as above: whether s.2(85) currently rests on
    # unacquired law is a fact about the disk, not about this behaviour.
    with _none_acq():
        unacq = [e for e in events_for(date(2026, 9, 9), since=date(2025, 1, 1))
                 if e.subtype == BASIS_UNACQUIRED]
        check(any(e.obligation_id == "CA13-S2-85-SMALL" for e in unacq),
              "the small-company duty is surfaced as resting on unacquired law")
        check(all(e.output_class == SIGNAL for e in unacq),
              "...as a SIGNAL, because no one has verified it")
    with _all_acq():
        still = [e for e in events_for(date(2026, 9, 9), since=date(2025, 1, 1))
                 if e.subtype == BASIS_UNACQUIRED
                 and e.obligation_id == "CA13-S2-85-SMALL"]
        check(not still,
              "...and once attested it no longer reports its basis as unacquired")

    # ── T0's guarantee, asserted here too: no holes in our own map ───────────
    check(not [e for e in evs if e.subtype == BASIS_UNDECLARED],
          "no obligation reaches the log with an undeclared basis")

    # ── ordering and lookup ──────────────────────────────────────────────────
    check([e.at for e in evs] == sorted([e.at for e in evs], reverse=True),
          "the stream is newest-first")
    if evs:
        found = event_by_id(evs[0].id, date(2026, 9, 9), since=date(2025, 1, 1))
        check(found is not None and found.id == evs[0].id, "an event can be fetched by id")
    check(event_by_id("nosuchid", date(2026, 9, 9)) is None,
          "an unknown id returns None, not a guess")

    # ── the reverse index the monitor runs on ────────────────────────────────
    check(affected_by("880(E)") == ["CA13-S2-85-SMALL"],
          f"affected_by names the obligations an instrument moves ({affected_by('880(E)')})")

    # ── once acquired, the same instrument becomes a verified fact ───────────
    from checker.prescribed_thresholds import all_acquired
    with all_acquired():
        acq = [e for e in events_for(date(2026, 9, 9), since=date(2025, 1, 1))
               if e.subtype == THRESHOLD_MOVED]
        check(bool(acq) and all(e.output_class == VERIFIED_FACT for e in acq),
              "once the instrument is attested the event becomes a VERIFIED_FACT")
        check(all(e.verified_by for e in acq), "...carrying who/what verified it")

    # ── the one correctness metric, at the surface ───────────────────────────
    # "Never render CURRENT on a superseded instrument." In event-log terms: no
    # event may claim a current legal basis, or wear VERIFIED_FACT, while the
    # instrument behind it is not acquired. Checked across a span of dates that
    # straddles the 880(E) boundary, so a regression at any one of them is caught.
    for d in (date(2025, 11, 30), date(2025, 12, 1), date(2026, 9, 9)):
        for e in events_for(d, since=date(2020, 1, 1)):
            if e.verified_by is None:
                check(e.currency_state != currency.CURRENT,
                      f"{d}: an unverified event never claims CURRENT ({e.subtype})")
                check(e.output_class != VERIFIED_FACT,
                      f"{d}: an unverified event is never a VERIFIED_FACT ({e.subtype})")
    check(True, "no unverified event claims a current basis, across the 880(E) boundary")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
