"""Is our AMENDMENT record current? -- the currency map, turned on ourselves.

`currency.py` asks whether the law behind an obligation is still the law. This
module asks the question one layer up: **is the amendment ledger we hold complete
enough to answer that at all?**

The distinction is the whole reason this file exists. `as_of.py` returns fidelity
EXACT when every span it knows about is accounted for -- but EXACT means "every
amendment we HOLD is applied", not "we hold every amendment that was made". A
section last amended in 2021 in our corpus, and amended again in 2025 in the
Gazette, reconstructs as EXACT and is wrong. That is the G.S.R. 880(E) failure
exactly one layer up, and nothing was watching for it.

So this module measures the gap and REFUSES to close it. Closing it means
acquiring instruments, which is browser-gated and human-attested. A loop that
types in an amendment defeats the design the same way a loop that types in a
threshold does.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from checker.amendment import PLAUSIBLE_YEARS, parse_footnote
from checker.lattice import Lattice

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "companies_act"

# Ordered weakest -> strongest concern, so findings compose by weakest link the
# way currency does. The order lives in lattice.Lattice; see checker/lattice.py.
# The GAP axis: how far our newest held amendment is from the date asked about.
FRESH = "FRESH"                  # the ledger reaches this date
AGEING = "AGEING"                # no amendment held for over a year
STALE = "STALE"                  # no amendment held for over GAP_STALE_YEARS
STATES = (FRESH, AGEING, STALE)
_LATTICE = Lattice("corpus_currency", STATES)
_SEVERITY = {s: _LATTICE.rank(s) for s in STATES}

# `implausible` is a SEPARATE axis and is deliberately NOT on the ladder above.
# A held record with a date outside the Act's lifetime says something about one
# source defect; the gap says something about our coverage. Conflating them is the
# mistake provenance.py:38-40 documents about conflating evidence with
# accessibility -- the two need opposite responses (flag the record vs acquire
# more records), so they are reported on their own axes and composed by the
# caller, never collapsed into one word.

GAP_AGEING_DAYS = 365
GAP_STALE_YEARS = 2


@dataclass(frozen=True)
class CorpusFinding:
    """What we can say about the amendment ledger's own currency."""
    status: str
    newest_wef: date | None
    gap_days: int | None
    sections_scanned: int
    amendments_parsed: int
    implausible: int
    note: str

    @property
    def needs_action(self) -> bool:
        """True on either axis. A clean gap with a defective record still needs a person."""
        return self.status != FRESH or self.implausible > 0


def _records() -> list[dict]:
    return [json.loads(p.read_text())
            for p in sorted(CORPUS.glob("*.json")) if not p.name.startswith("_")]


def report(as_of: date) -> CorpusFinding:
    """The amendment ledger's own currency, derived from what is on disk.

    Never asserts a state; computes it from the newest `w.e.f.` we actually hold.
    """
    sections = amendments = implausible = 0
    newest: date | None = None

    for rec in _records():
        sections += 1
        for a in parse_footnote(rec.get("footnote") or ""):
            amendments += 1
            if a.wef_implausible:
                # Counted, surfaced, and NOT used to move the newest date. A source
                # defect must not be repaired into a fact -- CLAUDE.md.
                implausible += 1
                continue
            if a.wef and (newest is None or a.wef > newest):
                newest = a.wef

    if newest is None:
        return CorpusFinding(
            STALE, None, None, sections, amendments, implausible,
            "no amendment with a usable effective date is held at all. Acquire the "
            "Act's amendment history from India Code or the Gazette before relying "
            "on any point-in-time reconstruction.")

    gap = (as_of - newest).days
    if gap < 0:
        # Asking about a date before our newest amendment. The ledger is not stale
        # for that question; it reaches past it.
        status = FRESH
    elif gap >= GAP_STALE_YEARS * 365:
        status = STALE
    elif gap >= GAP_AGEING_DAYS:
        status = AGEING
    else:
        status = FRESH

    note = (f"newest amendment held takes effect {newest.isoformat()}; "
            f"{gap} days before the date asked about. ")
    if status == FRESH:
        note += "The ledger reaches this date."
    else:
        note += ("Either the Act has not moved since, or our footnote ledger is "
                 "stale -- this module cannot tell which, and must not guess. "
                 "Acquire the amendment history from India Code or the Gazette "
                 "and register it; do not type it in.")
    if implausible:
        note += (f" {implausible} held record(s) carry a w.e.f. date outside "
                 f"{PLAUSIBLE_YEARS} and are preserved, flagged, and excluded from "
                 "the newest-date calculation.")
    return CorpusFinding(status, newest, gap, sections, amendments, implausible, note)


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

    print("corpus_currency")

    # Asserted against the INGESTED CORPUS, never a constant -- house rule.
    f = report(date(2026, 9, 11))

    check(f.sections_scanned > 400,
          f"the whole Act corpus was scanned ({f.sections_scanned} sections)")
    check(f.amendments_parsed > 300,
          f"...and its amendment ledger parsed ({f.amendments_parsed} amendments)")
    check(f.newest_wef is not None and f.newest_wef.year == 2023,
          f"the newest amendment we HOLD is from 2023 ({f.newest_wef})")
    check(f.status == STALE,
          f"...so against a 2026 date the ledger is STALE ({f.status})")
    check(f.gap_days is not None and f.gap_days > 900,
          f"...and the gap is stated in days, not implied ({f.gap_days})")
    check("acquire" in f.note.lower() or "gazette" in f.note.lower(),
          "the note names what a person must do, rather than only complaining")

    # The implausible record (year 5017) is a KNOWN source defect. It must be
    # counted and surfaced, never silently dropped -- CLAUDE.md: never repair a
    # defective government source, flag it and preserve it verbatim.
    check(f.implausible >= 1,
          f"a wef date outside {PLAUSIBLE_YEARS} is counted, not dropped ({f.implausible})")
    check(f.needs_action, "...and the finding is flagged as needing a person")

    # Behaviour must be DERIVED from the corpus, not pinned to today. Asking as of
    # a date inside the ledger's own coverage must not report STALE.
    f_then = report(date(2023, 6, 1))
    check(_SEVERITY[f_then.status] < _SEVERITY[STALE],
          f"as of a 2023 date the same ledger is not STALE ({f_then.status})")
    # The two axes stay separate: the defective record is still counted on a date
    # where the gap is fine, and it must not silently become a gap verdict.
    check(f_then.implausible == f.implausible and f_then.status != f.status,
          "the defect count is independent of the gap verdict, on both axes")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
