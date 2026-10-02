#!/usr/bin/env python3
"""What falls due in the next 90 days, and what cannot be dated at all.

8c. A compliance calendar built from `checker/obligations.py` and dated with
`checker/derived_date.py`. Two rules, and the second is the one that makes it usable:

1. **Never a guessed date.** A deadline is derived from an ANCHOR the company supplied and
   an INTERVAL quoted from the provision. If either is missing the entry is UNKNOWN and
   says which fact is missing. `derived_date.derive` already refuses to invent an interval
   -- it raises unless the interval appears verbatim in the source text -- and this module
   does the same for the anchor.

2. **An UNKNOWN entry is never dropped from the view.** It cannot be placed in the window,
   so the obvious implementation filters it out -- and the obligations that silently vanish
   are exactly the ones a lawyer needs to act on, because the missing fact is the action.
   A calendar that shows four dated duties and hides three undatable ones reads as "three
   things to do" when the truth is "three things to do and three we cannot even schedule".

So `upcoming()` returns both buckets and the caller cannot get one without the other.

## Why a date is UNKNOWN, as separate facts

    missing_anchor    the company has not told us the date this runs from
    missing_fact      the obligation's own row is undetermined for want of a fact
    no_interval       the provision's text does not state an interval we can parse
    not_applicable    the obligation does not apply to this company

They need different work -- ask the client, ask the client something else, acquire the
source, nothing -- so they are different values rather than one "unknown".

Run: PYTHONPATH=. python3 checker/compliance_calendar.py --test
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

__all__ = ["HORIZON_DAYS", "DUE", "UNKNOWN", "Entry", "Calendar", "upcoming",
           "MISSING_ANCHOR", "MISSING_FACT", "NO_INTERVAL", "NOT_APPLICABLE",
           "CalendarError"]

HORIZON_DAYS = 90

DUE = "DUE"
UNKNOWN = "UNKNOWN"

MISSING_ANCHOR = "missing_anchor"
MISSING_FACT = "missing_fact"
NO_INTERVAL = "no_interval"
NOT_APPLICABLE = "not_applicable"


class CalendarError(ValueError):
    """A calendar that cannot be built. Never a silently empty one."""


@dataclass(frozen=True)
class Entry:
    obligation_id: str
    duty: str
    provision: str
    state: str                      # DUE or UNKNOWN
    due: str = ""                   # ISO date, only when state is DUE
    reason: str = ""                # why it is UNKNOWN
    missing: tuple = ()             # the named facts to go and get
    anchor_label: str = ""
    quote: str = ""                 # the interval, verbatim from the provision

    def to_dict(self) -> dict:
        return {"obligation_id": self.obligation_id, "duty": self.duty,
                "provision": self.provision, "state": self.state,
                "due": self.due or None, "reason": self.reason,
                "missing": list(self.missing), "anchor_label": self.anchor_label,
                "quote": self.quote}


@dataclass(frozen=True)
class Calendar:
    as_of: str
    horizon_days: int
    due: tuple = ()
    unknown: tuple = ()
    out_of_window: int = 0

    def to_dict(self) -> dict:
        return {"as_of": self.as_of, "horizon_days": self.horizon_days,
                "due": [e.to_dict() for e in self.due],
                "unknown": [e.to_dict() for e in self.unknown],
                "out_of_window": self.out_of_window,
                "note": (
                    f"{len(self.due)} obligation(s) fall due in the next "
                    f"{self.horizon_days} days. {len(self.unknown)} CANNOT BE DATED and "
                    f"are listed separately -- they are not scheduled, and dropping them "
                    f"would show a shorter list that reads as less to do. "
                    f"{self.out_of_window} dated obligation(s) fall outside the window.")}


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


def upcoming(rows, *, anchors, source_texts, as_of, horizon_days: int = HORIZON_DAYS,
             intervals=None) -> Calendar:
    """The calendar. `rows` are `obligations.Row`-shaped; nothing here calls a model.

    `anchors`   {anchor_label: date} the company has actually supplied.
    `source_texts` {obligation_id: the provision's text}, so the interval is read from the
                provision rather than from a table in this file. An obligation with no
                text is NO_INTERVAL, not a default.
    `intervals` {obligation_id: anchor_label} -- which supplied fact each duty runs from.
    """
    from checker import derived_date as dd
    from checker import obligations as ob

    if not isinstance(as_of, date):
        raise CalendarError(f"as_of must be a date, got {type(as_of).__name__}")
    if horizon_days <= 0:
        raise CalendarError(f"a horizon of {horizon_days} days schedules nothing")
    anchors = dict(anchors or {})
    source_texts = dict(source_texts or {})
    intervals = dict(intervals or {})
    end = as_of + timedelta(days=horizon_days)

    due, unknown, outside = [], [], 0
    for row in rows or ():
        oid = str(getattr(row, "obligation_id", "") or "")
        duty = str(getattr(row, "duty", "") or "")
        prov = str(getattr(row, "provision", "") or "")
        state = str(getattr(row, "state", "") or "")
        missing = tuple(getattr(row, "missing_facts", ()) or ())

        def unk(reason: str, why: str, extra=()) -> None:
            unknown.append(Entry(obligation_id=oid, duty=duty, provision=prov,
                                 state=UNKNOWN, reason=f"{reason}: {why}",
                                 missing=tuple(extra) or missing,
                                 anchor_label=intervals.get(oid, "")))

        if state == ob.DOES_NOT_APPLY:
            continue                      # not a gap; it is simply not this company's duty
        if state in (ob.APPLIES_UNDETERMINED, ob.CANNOT_DETERMINE):
            unk(MISSING_FACT,
                f"the obligation itself is {state} for want of a fact, so a date would be "
                f"a date for a duty we cannot say applies")
            continue
        label = intervals.get(oid, "")
        if not label:
            unk(MISSING_ANCHOR, "no anchor is declared for this duty, so there is nothing "
                                "to count from", extra=())
            continue
        if label not in anchors or anchors[label] is None:
            unk(MISSING_ANCHOR,
                f"the company has not supplied {label!r}, which this duty runs from",
                extra=(label,))
            continue
        text = source_texts.get(oid) or ""
        if not text.strip():
            unk(NO_INTERVAL, "the provision's text is not held, so the interval cannot be "
                             "read from it")
            continue
        try:
            derived = dd.derive(anchor=anchors[label], anchor_label=label,
                                source_text=text, citation=prov)
        except dd.IntervalNotInSource:
            # derived_date refuses to invent an interval, and this is that refusal
            # surfacing as a calendar entry rather than as a crash or a default.
            unk(NO_INTERVAL,
                "the provision's text states no interval this system can parse, and one "
                "is never assumed")
            continue
        when = derived.result
        if as_of <= when <= end:
            due.append(Entry(obligation_id=oid, duty=duty, provision=prov, state=DUE,
                             due=_iso(when), anchor_label=label,
                             quote=str(derived.interval_text or "")))
        else:
            outside += 1
    due.sort(key=lambda e: (e.due, e.obligation_id))
    unknown_sorted = tuple(sorted(unknown, key=lambda e: e.obligation_id))
    return Calendar(as_of=_iso(as_of), horizon_days=horizon_days, due=tuple(due),
                    unknown=unknown_sorted, out_of_window=outside)


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

    print("compliance_calendar")
    from checker import obligations as ob

    AS_OF = date(2026, 10, 2)
    # A real interval, in the words a provision uses -- derived_date reads it from here
    # and refuses anything it cannot find.
    TEXT = "every company shall hold a general meeting within six months from the date"
    NOTICE = "a meeting may be called by giving not less than twenty-one days notice"

    def row(oid, state=ob.APPLIES_NOT_SATISFIED, missing=()):
        return ob.Row(obligation_id=oid, duty=f"duty {oid}", provision=f"s.{oid}",
                      state=state, basis="b", missing_facts=tuple(missing))

    ANCH = {"financial_year_end": date(2026, 6, 30),
            "notice_sent": date(2026, 10, 1)}

    # ── a dated obligation lands in the window ─────────────────────────────
    cal = upcoming([row("96")], anchors=ANCH, source_texts={"96": TEXT},
                   intervals={"96": "financial_year_end"}, as_of=AS_OF)
    check(len(cal.due) == 1 and cal.due[0].due == "2026-12-30",
          f"six months from 30 June 2026 is 30 December 2026, inside the 90-day window "
          f"({cal.due[0].due if cal.due else None})")
    check(cal.due[0].quote and "six months" in cal.due[0].quote,
          f"...and the entry carries the interval VERBATIM from the provision "
          f"({cal.due[0].quote!r})")
    check(cal.due[0].anchor_label == "financial_year_end",
          "...and names the fact it counted from")
    check(not cal.unknown, "...with nothing unknown")

    # ── NEVER a guessed date ───────────────────────────────────────────────
    no_anchor = upcoming([row("96")], anchors={}, source_texts={"96": TEXT},
                         intervals={"96": "financial_year_end"}, as_of=AS_OF)
    check(not no_anchor.due and len(no_anchor.unknown) == 1,
          "a missing ANCHOR produces NO date")
    check(no_anchor.unknown[0].reason.startswith(MISSING_ANCHOR)
          and "financial_year_end" in no_anchor.unknown[0].reason,
          f"...and says which fact is missing, by name "
          f"({no_anchor.unknown[0].reason[:56]!r})")
    check(no_anchor.unknown[0].missing == ("financial_year_end",),
          "...listed in `missing`, so a UI can ask for exactly that")

    no_text = upcoming([row("96")], anchors=ANCH, source_texts={},
                       intervals={"96": "financial_year_end"}, as_of=AS_OF)
    check(no_text.unknown and no_text.unknown[0].reason.startswith(NO_INTERVAL),
          "a provision whose TEXT is not held gives NO_INTERVAL, not a default period")
    bad_text = upcoming([row("96")], anchors=ANCH,
                        source_texts={"96": "the company shall comply promptly"},
                        intervals={"96": "financial_year_end"}, as_of=AS_OF)
    check(bad_text.unknown and bad_text.unknown[0].reason.startswith(NO_INTERVAL),
          "...and text with NO parseable interval does too: derived_date refuses to "
          "invent one, and that refusal surfaces as a calendar entry rather than a crash")
    check("never assumed" in bad_text.unknown[0].reason,
          "...saying so in words")

    undet = upcoming([row("149", ob.APPLIES_UNDETERMINED, missing=("listed",))],
                     anchors=ANCH, source_texts={"149": TEXT},
                     intervals={"149": "financial_year_end"}, as_of=AS_OF)
    check(not undet.due and undet.unknown[0].reason.startswith(MISSING_FACT),
          "an obligation that is UNDETERMINED is not dated: a date for a duty we cannot "
          "say applies is worse than no date")
    check(undet.unknown[0].missing == ("listed",),
          "...and the fact it needs is carried through from the obligation row")

    # ── THE RULE: an UNKNOWN entry is never dropped ────────────────────────
    mixed = upcoming([row("96"), row("149", ob.APPLIES_UNDETERMINED, ("listed",)),
                      row("173")],
                     anchors=ANCH, source_texts={"96": TEXT, "173": TEXT},
                     intervals={"96": "financial_year_end"}, as_of=AS_OF)
    check(len(mixed.due) == 1 and len(mixed.unknown) == 2,
          f"**the undatable obligations are returned, not filtered out** "
          f"({len(mixed.due)} due, {len(mixed.unknown)} unknown)")
    check("CANNOT BE DATED" in mixed.to_dict()["note"],
          "...and the note says so, because a shorter list reads as less to do")
    check(len(mixed.to_dict()["unknown"]) == 2,
          "...and they survive to_dict, so a UI cannot render only the dated ones by "
          "accident")
    check({e.reason.split(":")[0] for e in mixed.unknown} == {MISSING_FACT, MISSING_ANCHOR},
          f"...each with its OWN reason, because 'ask the client for a date' and 'ask the "
          f"client something else' are different work "
          f"({sorted(e.reason.split(':')[0] for e in mixed.unknown)})")

    # ── a duty that does not apply is not a gap ────────────────────────────
    na = upcoming([row("96", ob.DOES_NOT_APPLY)], anchors=ANCH,
                  source_texts={"96": TEXT}, intervals={"96": "financial_year_end"},
                  as_of=AS_OF)
    check(not na.due and not na.unknown,
          "a duty that DOES NOT APPLY is absent from both buckets: it is not a gap, and "
          "listing it as unknown would send someone to find a fact that changes nothing")

    # ── the window ─────────────────────────────────────────────────────────
    far = upcoming([row("96")], anchors={"financial_year_end": date(2027, 6, 30)},
                   source_texts={"96": TEXT}, intervals={"96": "financial_year_end"},
                   as_of=AS_OF)
    check(not far.due and far.out_of_window == 1,
          f"a date beyond the horizon is COUNTED but not listed, so '0 due' is "
          f"distinguishable from 'nothing scheduled' ({far.out_of_window})")
    check(HORIZON_DAYS == 90, "the horizon is 90 days (8c)")
    check(upcoming([row("96")], anchors=ANCH, source_texts={"96": NOTICE},
                   intervals={"96": "notice_sent"}, as_of=AS_OF).due[0].due
          == "2026-10-22",
          "twenty-one days from 1 October 2026 is 22 October 2026")

    for bad, why in ((("2026-10-02", 90), "a string as_of"), ((AS_OF, 0), "a zero horizon"),
                     ((AS_OF, -5), "a negative horizon")):
        try:
            upcoming([], anchors={}, source_texts={}, as_of=bad[0], horizon_days=bad[1])
            check(False, f"{why} raises")
        except CalendarError:
            check(True, f"{why} RAISES rather than producing an empty calendar")
    check(upcoming([], anchors={}, source_texts={}, as_of=AS_OF).to_dict()["due"] == [],
          "no obligations at all is an empty calendar, not an error")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
