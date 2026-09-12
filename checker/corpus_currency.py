"""Is the ACT's amendment ledger current? -- the currency map, turned on ourselves.

## Read the scope before the verdict

This module measures ONE thing: the footnote ledger of the Companies Act 2013 as
we hold it. It does NOT measure delegated legislation. Rules, and the G.S.R./S.O.
instruments that amend them, are tracked by `staleness.py` against the S-00x rule
register, and by `prescribed_thresholds` for the amounts they prescribe.

That distinction is load-bearing, because the two move at different speeds and
have done exactly that. The Act's ledger has not moved since 2023-10-30, while
several sets of Rules were amended through 2025 -- including G.S.R. 880(E), which
this repo holds and a human attested. A reader who took STALE to mean "we are
behind on everything" would have it backwards: the Act specifically is the thing
that has not moved. So the finding carries a `scope` and the note says so.

`currency.py` asks whether the law behind an obligation is still the law. This
module asks the question one layer up: **is the Act's amendment ledger we hold
complete enough to answer that at all?**

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

# What this module measures. Stated on the finding so a verdict cannot be read
# wider than the evidence behind it.
SCOPE = "companies_act_2013_amendment_ledger"

# ── UNVERIFIED leads, recorded so they are not re-researched ──────────────────
# Gathered 2026-09-11 from SECONDARY reporting (news, commentary, aggregators).
# None has been read off an official document by us. This is a search hint for
# whoever retrieves the files, and a thing to CHECK against the Gazette -- never
# a thing to assert. Same status and same reason as provenance.PRINCIPAL_RULES_LEAD.
#
# Their existence is also the evidence for the scope note above: the Act stood
# still through 2025 while its Rules did not.
AMENDMENT_LEADS = (
    ("Corporate Laws (Amendment) Bill, 2026", "Bill No. 85 of 2026",
     "107 clauses, amends the Companies Act 2013 AND the LLP Act 2008. Introduced "
     "23-03-2026; PRS confirms it was still before a 31-member Joint Committee in "
     "July 2026. NOT LAW, so it is not an amendment and must not enter the ledger. "
     "Recorded because it is the largest scheduled disruption to this corpus, and "
     "nothing in the engine watches pending legislation -- see staleness.py, "
     "'Discovery of a successor is human.'"),
    ("Companies (Accounts) Amendment Rules, 2025", "reported as G.S.R. 317(E), 19-05-2025",
     "delegated legislation, not an Act amendment; belongs to the rule register"),
    ("Companies (Accounts) Second Amendment Rules, 2025", "reported dated 30-05-2025",
     "delegated legislation; belongs to the rule register"),
    ("Companies (Compromises, Arrangements and Amalgamations) Amendment Rules, 2025",
     "reported dated 04-09-2025",
     "reported to widen fast-track mergers under s.233; delegated legislation"),
)


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
    scope: str = SCOPE

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
            "on any point-in-time reconstruction. (Scope: the Act's own ledger. "
            "Rules are tracked by staleness.py, not here.)")

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
                 "and register it; do not type it in. NOTE THE SCOPE: this counts "
                 "amendments to the ACT only. Rules moved through 2025 and are "
                 "tracked by staleness.py against the rule register, so a stale "
                 "Act ledger does not mean we are behind on delegated legislation "
                 "-- see AMENDMENT_LEADS.")
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

    # ── the SCOPE is stated, so a verdict cannot be read wider than its evidence
    check(f.scope == SCOPE, f"the finding declares what it measured ({f.scope})")
    check("ACT only" in f.note or "Act's own ledger" in f.note,
          "...and the note says the Rules are tracked elsewhere")
    check("staleness" in f.note,
          "...naming the module that does track them, not just disclaiming")

    # ── leads are recorded as leads, and never as facts ──────────────────────
    check(len(AMENDMENT_LEADS) >= 4, f"the 2026 research is recorded ({len(AMENDMENT_LEADS)} leads)")
    bill = [l for l in AMENDMENT_LEADS if "Bill" in l[0]][0]
    check("NOT LAW" in bill[2],
          "the pending 107-clause Bill is recorded as NOT LAW, so it cannot enter the ledger")
    check(all("reported" in l[1].lower() or "Bill No" in l[1] for l in AMENDMENT_LEADS),
          "...and every lead is marked as reported, never as read off an instrument")
    held = {i for _, i, _ in AMENDMENT_LEADS}
    check(not any("880(E)" in i for i in held),
          "an instrument we already hold and attested is not carried as an open lead")

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
