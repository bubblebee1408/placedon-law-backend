"""What an MCA master-data snapshot can and cannot be asked.

The pasted Master Data Strip spec puts a badge on the bar reading `Synced 14m ago`
and a green pill reading `MCA Reconciled (0 Conflicts)`. Both are honest about the
wrong quantity. The registry does not hold events; it holds *filings*, and the
Act itself grants the company a window between the two. A fetch that is fourteen
minutes old is still reporting a world that may be sixty days out of date, and in
one direction three hundred days out of date.

So this module replaces freshness with **blindness**: for each field, how far back
could a lawful, not-yet-filed event have occurred, and in which direction would it
move the number.

## Direction is the part a lawyer can act on

    FLOOR    the truth is at least the registry value (an unfiled creation)
    CEILING  the truth is at most the registry value (an unfiled satisfaction)
    EITHER   both failure modes are open

`Active Charges: 0` is not "unencumbered". Under s.77 a charge created up to sixty
days ago may lawfully be unregistered, so zero is a FLOOR. That single distinction
is the difference between a green chip and a correct one.

## Every window is quoted from our own corpus

Not from memory, and not from a blog. Each `Window` carries a verbatim fragment and
the section it came from, and `_test()` re-reads `corpus/companies_act/` and fails
if the fragment is no longer there. A window that drifts from the Act breaks the
build rather than quietly mis-stating how blind we are.

## Two fields cannot be bounded at all, and say so

s.39(4) (return of allotment) and the DIR-3 KYC regime prescribe their timing by
*rule*, and we do not hold those rules. `staleness.py` established the principle for
law: nothing may be reported CURRENT while resting on an unread rule. The same
applies to a fact. Paid-up capital and DIN status therefore come back
UNBOUNDED_BLIND naming what we would have to acquire — never with a number.

Run: python3 checker/mca_snapshot.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "companies_act"

# ── direction of error ───────────────────────────────────────────────────────
FLOOR = "FLOOR"        # truth >= registry value
CEILING = "CEILING"    # truth <= registry value
EITHER = "EITHER"      # both directions open

# ── assessment states ────────────────────────────────────────────────────────
ABSENT = "ABSENT"                      # the response did not carry this field
FETCH_STALE = "FETCH_STALE"            # our copy is older than policy allows
BOUNDED_BLIND = "BOUNDED_BLIND"        # blindness has a width, from held law
UNBOUNDED_BLIND = "UNBOUNDED_BLIND"    # the timing rule is not held; no width
NEEDS_ANCHOR = "NEEDS_ANCHOR"          # window runs from an event we were not given

# A fetch older than this is not refused -- it is reported. Seven days because the
# shortest duty window in the Act is thirty: a week of fetch age is a quarter of the
# tightest window and is the point at which it stops being noise.
MAX_FETCH_AGE_DAYS = 7


@dataclass(frozen=True)
class Window:
    """One statutory filing window, quoted from the corpus."""
    form: str            # the e-form the duty is discharged through
    section: str         # human citation, e.g. "s.77(1)"
    section_number: str  # corpus index key, e.g. "77"
    days: int
    direction: str
    quote: str           # verbatim fragment; _test() proves it is still in the Act
    kind: str = "DUTY"   # DUTY = the primary period; OUTER = the longest lawful late filing

    def __post_init__(self) -> None:
        if self.direction not in (FLOOR, CEILING, EITHER):
            raise ValueError(f"unknown direction {self.direction!r}")
        if self.days <= 0:
            raise ValueError("a filing window is a positive number of days")


@dataclass(frozen=True)
class Field:
    """One column of the strip, and what bounds its blindness."""
    name: str
    windows: tuple[Window, ...] = ()
    anchor: str = "EVENT"        # EVENT = window runs from the event; AGM = from the meeting
    unbounded_reason: str = ""   # non-empty => blindness has no bound from held law
    acquire: str = ""            # what acquiring would bound it
    absence_is_denial: bool = False   # may registry silence be read as "there is none"?


# ── the windows, each verbatim from corpus/companies_act ──────────────────────

_CHG1_DUTY = Window(
    "CHG-1", "s.77(1)", "77", 30, FLOOR,
    "with the Registrar within thirty days of its creation")
_CHG1_OUTER = Window(
    "CHG-1", "s.77(1) first proviso (b)", "77", 60, FLOOR,
    "within a period of sixty days of such creation", kind="OUTER")
_CHG4_DUTY = Window(
    "CHG-4", "s.82(1)", "82", 30, CEILING,
    "within a period of thirty days from the date of such payment or satisfaction")
_CHG4_OUTER = Window(
    "CHG-4", "s.82(1) proviso", "82", 300, CEILING,
    "within a period of three hundred days of such payment or satisfaction", kind="OUTER")
_SH7 = Window(
    "SH-7", "s.64(1)", "64", 30, FLOOR,
    "with the Registrar within a period of thirty days of such alteration")
_DIR12 = Window(
    "DIR-12", "s.170(2)", "170", 30, EITHER,
    "filed with the Registrar within thirty days from the appointment of every director")
_AOC4 = Window(
    "AOC-4", "s.137(1)", "137", 30, EITHER,
    "filed with the Registrar within thirty days of the date of annual general meeting")
_MGT7 = Window(
    "MGT-7", "s.92(4)", "92", 60, EITHER,
    "within sixty days from the date on which the annual general meeting is held")


FIELDS: dict[str, Field] = {
    # Charges are blind in BOTH directions, and asymmetrically: sixty days for a
    # charge that exists and is not yet registered, three hundred for one that is
    # discharged and still shown. The spec's "Active Charges: 2" chip is therefore
    # capable of being wrong in the company's favour for most of a year.
    "charges": Field("charges", (_CHG1_DUTY, _CHG1_OUTER, _CHG4_DUTY, _CHG4_OUTER),
                     absence_is_denial=False),

    "authorised_capital": Field("authorised_capital", (_SH7,)),

    # s.39(4) requires the return of allotment "in such manner as may be
    # prescribed" and states no period. The period is in the Prospectus and
    # Allotment Rules, which we do not hold, so paid-up capital gets no bound.
    "paid_up_capital": Field(
        "paid_up_capital",
        unbounded_reason="s.39(4) prescribes the return of allotment by rule and "
                         "states no period in the Act; the rule is not held",
        acquire="Companies (Prospectus and Allotment of Securities) Rules, 2014, rule 12"),

    "directors": Field("directors", (_DIR12,), absence_is_denial=False),

    # DIR-3 KYC deactivation is a creature of the Appointment and Qualification of
    # Directors Rules, not of the Act. We hold neither the rule nor its timing.
    "din_status": Field(
        "din_status",
        unbounded_reason="DIN deactivation for KYC default arises under the "
                         "Appointment and Qualification of Directors Rules, which "
                         "are not held",
        acquire="Companies (Appointment and Qualification of Directors) Rules, 2014, rule 12A"),

    # These run from the AGM, not from the event, so they cannot be assessed
    # without being told when the AGM was.
    "financial_statements": Field("financial_statements", (_AOC4,), anchor="AGM"),
    "annual_return": Field("annual_return", (_MGT7,), anchor="AGM"),
}


@dataclass(frozen=True)
class Snapshot:
    """One fetched master-data record, with its provenance."""
    cin: str
    fetched_at: date
    source: str
    values: dict          # field name -> whatever the provider returned
    payload_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("a snapshot must name its source")
        for k in self.values:
            if k not in FIELDS:
                raise ValueError(f"unknown master-data field {k!r}")

    @property
    def evidence_grade(self) -> str:
        """An aggregator payload is secondary evidence, and hashing does not promote it.

        The hash proves we did not alter what we received. It says nothing about what
        MCA holds. The primary artefact is an MCA-issued signed document -- which
        `scripts/verify_document.py` can actually check.
        """
        return "SECONDARY"


@dataclass(frozen=True)
class Assessment:
    state: str
    field: str
    floor_blind_since: date | None = None
    ceiling_blind_since: date | None = None
    windows: tuple[Window, ...] = ()
    note: str = ""

    def sentence(self) -> str:
        if self.state == ABSENT:
            return f"{self.field}: not present in the response."
        if self.state == FETCH_STALE:
            return f"{self.field}: {self.note}"
        if self.state == UNBOUNDED_BLIND:
            return f"{self.field}: blindness cannot be bounded -- {self.note}"
        if self.state == NEEDS_ANCHOR:
            return f"{self.field}: {self.note}"
        bits = []
        if self.floor_blind_since:
            bits.append(f"an event on or after {self.floor_blind_since} may raise the "
                        f"true value above this one")
        if self.ceiling_blind_since:
            bits.append(f"an event on or after {self.ceiling_blind_since} may lower it")
        return f"{self.field}: " + "; ".join(bits) + "."


def assess(snap: Snapshot, field_name: str, as_of: date,
           agm_date: date | None = None) -> Assessment:
    """How blind are we about this field, as at `as_of`?"""
    f = FIELDS.get(field_name)
    if f is None:
        raise ValueError(f"unknown master-data field {field_name!r}")

    if field_name not in snap.values:
        return Assessment(ABSENT, field_name)

    age = (as_of - snap.fetched_at).days
    if age > MAX_FETCH_AGE_DAYS:
        return Assessment(FETCH_STALE, field_name,
                          note=f"fetched {age} days ago, policy allows "
                               f"{MAX_FETCH_AGE_DAYS}; re-fetch before relying on it")

    if f.unbounded_reason:
        return Assessment(UNBOUNDED_BLIND, field_name,
                          note=f"{f.unbounded_reason}. Acquire: {f.acquire}")

    if f.anchor == "AGM":
        if agm_date is None:
            return Assessment(NEEDS_ANCHOR, field_name, windows=f.windows,
                              note=f"the window runs from the annual general meeting "
                                   f"({f.windows[0].section}); no AGM date was given")
        base = agm_date
    else:
        base = as_of

    floor = ceiling = None
    for w in f.windows:
        since = base - timedelta(days=w.days)
        if w.direction in (FLOOR, EITHER):
            floor = since if floor is None else min(floor, since)
        if w.direction in (CEILING, EITHER):
            ceiling = since if ceiling is None else min(ceiling, since)
    return Assessment(BOUNDED_BLIND, field_name, floor, ceiling, f.windows)


def may_assert_absence(field_name: str) -> tuple[bool, str]:
    """May registry silence be reported as "there is none"?

    The same rule `entity_graph` holds for edges: absence is not denial. For charges
    and directors the answer is a flat no, and the reason names the window that makes
    it so -- because a UI that renders a floor as a fact is the whole failure.
    """
    f = FIELDS[field_name]
    if f.absence_is_denial:
        return True, ""
    # Absence asks "could there be MORE than the register shows", so only a window
    # that moves the value UP is relevant. Citing s.82 (which governs discharge, and
    # is the wider window) would be a real-sounding reason for the wrong direction.
    upward = [w for w in f.windows if w.direction in (FLOOR, EITHER)]
    widest = max(upward, key=lambda w: w.days, default=None)
    if widest is None:
        return False, (f"{field_name}: the timing rule is not held, so silence bounds "
                       f"nothing. Acquire: {f.acquire}")
    return False, (f"{field_name}: {widest.section} allows up to {widest.days} days "
                   f"between the event and the filing, so an empty register is a "
                   f"floor, not a finding")


# ── corpus check: a quote that left the Act must break the build ──────────────

def _section_text(number: str) -> str:
    idx = json.loads((CORPUS / "_index.json").read_text())["entries"]
    entry = idx[number]
    doc = json.loads((CORPUS / f"{entry['section_id']}.json").read_text())
    # Normalise for SEARCH only. The stored content keeps its markup verbatim --
    # repairing a source is forbidden, reading past its markup is not.
    return " ".join(re.sub(r"<[^>]*>", " ", doc["content"]).split())


def all_windows() -> tuple[Window, ...]:
    seen, out = set(), []
    for f in FIELDS.values():
        for w in f.windows:
            if id(w) not in seen:
                seen.add(id(w)); out.append(w)
    return tuple(out)


def verify_against_corpus() -> list[str]:
    """Return a failure line per window whose quote is no longer in the Act."""
    bad = []
    for w in all_windows():
        try:
            text = _section_text(w.section_number)
        except (KeyError, FileNotFoundError):
            bad.append(f"{w.section}: section {w.section_number} not in corpus")
            continue
        if w.quote not in text:
            bad.append(f"{w.section}: quote not found in corpus text -- {w.quote!r}")
    return bad


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("mca_snapshot")

    # ── every window is still in the Act we hold ─────────────────────────────
    bad = verify_against_corpus()
    check(not bad, f"every filing window is quoted verbatim from the corpus "
                   f"({len(all_windows())} windows)" + ("" if not bad else f" -- {bad}"))

    today = date(2026, 9, 12)
    snap = Snapshot(
        cin="U72200KA2021PTC145892", fetched_at=date(2026, 9, 12),
        source="MCA21 via contracted aggregator",
        values={"charges": [], "authorised_capital": 50_000_000,
                "paid_up_capital": 32_000_000, "directors": ["08412345"],
                "din_status": {"08412345": "DEACTIVATED"},
                "financial_statements": "FY2024-25"})

    # ── the finding that the spec's green chip hides ─────────────────────────
    a = assess(snap, "charges", today)
    check(a.state == BOUNDED_BLIND, "a charges field fetched today is bounded-blind, not current")
    check(a.floor_blind_since == today - timedelta(days=60),
          f"a charge created within 60 days may lawfully be unregistered "
          f"(s.77 proviso) -- floor blind since {a.floor_blind_since}")
    check(a.ceiling_blind_since == today - timedelta(days=300),
          f"a charge satisfied within 300 days may lawfully still be shown "
          f"(s.82 proviso) -- ceiling blind since {a.ceiling_blind_since}")
    check(a.ceiling_blind_since < a.floor_blind_since,
          "the two blindnesses are asymmetric: the registry is far staler about "
          "discharge than about creation")

    permitted, why = may_assert_absence("charges")
    check(not permitted, "an empty charge register may not be reported as unencumbered")
    check("floor, not a finding" in why and "s.77" in why,
          f"...and the refusal cites the window that moves the value UP: {why}")

    # ── unbounded fields refuse to produce a number ──────────────────────────
    for f in ("paid_up_capital", "din_status"):
        r = assess(snap, f, today)
        check(r.state == UNBOUNDED_BLIND and r.floor_blind_since is None,
              f"{f} is unbounded-blind and states no width")
        check("Acquire:" in r.sentence(), f"...and names what would bound it")

    # ── an AGM-anchored field will not be guessed from today ─────────────────
    r = assess(snap, "financial_statements", today)
    check(r.state == NEEDS_ANCHOR, "an AGM-anchored window refuses without an AGM date")
    r = assess(snap, "financial_statements", today, agm_date=date(2026, 9, 1))
    check(r.state == BOUNDED_BLIND and r.floor_blind_since == date(2026, 8, 2),
          f"...and computes from the AGM once given ({r.floor_blind_since})")

    # ── fetch age is reported, not hidden behind a badge ─────────────────────
    old = Snapshot(cin=snap.cin, fetched_at=date(2026, 8, 1), source=snap.source,
                   values=snap.values)
    check(assess(old, "charges", today).state == FETCH_STALE,
          "a 42-day-old fetch reports as stale rather than rendering a chip")

    # ── absence of the field is not absence of the thing ─────────────────────
    thin = Snapshot(cin=snap.cin, fetched_at=today, source=snap.source,
                    values={"authorised_capital": 50_000_000})
    check(assess(thin, "charges", today).state == ABSENT,
          "a response that omits charges reports ABSENT, not zero")

    # ── provenance is not laundered by hashing ───────────────────────────────
    check(snap.evidence_grade == "SECONDARY",
          "a hashed aggregator payload is still secondary evidence")

    # ── construction refuses nonsense ────────────────────────────────────────
    for bad_kw in (dict(direction="SOON"), dict(days=0)):
        try:
            Window("X", "s.1", "1", 30, FLOOR, "q", **{**{}, **bad_kw})  # type: ignore[arg-type]
            check(False, f"a malformed window is rejected: {bad_kw}")
        except (ValueError, TypeError):
            check(True, f"a malformed window is rejected at construction: {bad_kw}")
    try:
        Snapshot("U1", today, "src", {"revenue": 1})
        check(False, "an unknown field is rejected")
    except ValueError:
        check(True, "a snapshot carrying an unknown field is rejected at construction")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
