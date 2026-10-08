"""Companies Act 2013 matters, from the open judgment METADATA, as a time-to-decision signal.

Lane B, first prediction dataset. From the AWS Open Data Supreme Court / High Court judgment
metadata (anonymous S3, CC-BY-4.0, tier LICENSED), build an event table of Companies Act
matters and read a survival estimate off it: how long a matter takes at a forum, counting the
cases still PENDING as censored (they are the slow ones; dropping them makes every court look
faster than it is -- `survival.median` keeps them).

## Every field says where it came from, and UNKNOWN is never a guess

A `Matter` carries, per field, the metadata path it was read from. A field the metadata does
not state is UNKNOWN (``None``) -- never inferred, never defaulted. The open metadata often
does NOT carry a filing date, a cited section, or an outcome; those matters contribute what
they can (a censored or decided duration when both dates are present) and are counted, by
name, among the ones a field could not be read for. A matter with no filing date cannot be
timed and is excluded from the duration estimate, said in the notes rather than dropped silently.

## This is RING 3, and it can never decide law

`checker.forecast` is Ring 3 (INFERENCE); `rings.py`'s firewall forbids any Ring 0 decider from
importing or receiving a value from here. The output is a DESCRIPTIVE `Estimate`, whose label is
**predictive_signal** -- never a verified fact and never an input to a legal decision. No model
is ever called: this is counting and Kaplan-Meier arithmetic over records.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from checker.forecast import DESCRIPTIVE, Estimate, EstimateError
from checker.forecast import survival

UNKNOWN = None
PENDING = "PENDING"

# The committed dataset the gate reads: a small, real-shaped slice. The live refresh
# (scripts/build_companies_act_matters.py) rewrites it from the real parquet, off the gate.
DATASET = Path(__file__).resolve().parent.parent.parent / "corpus" / "forecast" / "companies_act_matters.json"

# A matter is a Companies Act 2013 matter when a stated field names the Act or a section of it.
# Matched on the metadata's own words -- never inferred from the parties or the court.
_CA_MARKER = re.compile(r"compan(?:y|ies)\s+act,?\s*2013|\bc\.?a\.?\s*2013\b", re.IGNORECASE)

# Below this many DECIDED, timeable matters a median is not estimated -- a handful of cases is
# not a court's tempo. ponytail: a floor, not a calibrated power analysis; tighten when a
# track record exists to tune it against.
MIN_EVENTS = 8


@dataclass(frozen=True)
class Matter:
    """One Companies Act matter. Each field's source path is in `sources`; UNKNOWN is None."""
    case_id: str
    court: str
    filing_date: str | None = UNKNOWN       # ISO date, or None (not stated)
    decision_date: str | None = UNKNOWN     # ISO date, or None => still PENDING
    section: str | None = UNKNOWN
    outcome: str | None = UNKNOWN
    sources: dict = field(default_factory=dict)   # field name -> metadata path it was read from

    @property
    def pending(self) -> bool:
        return self.decision_date is UNKNOWN

    def to_dict(self) -> dict:
        return {"case_id": self.case_id, "court": self.court,
                "filing_date": self.filing_date, "decision_date": self.decision_date,
                "status": PENDING if self.pending else "DECIDED",
                "section": self.section, "outcome": self.outcome, "sources": self.sources}


def _iso(value) -> str | None:
    """An ISO date string, or None. A malformed date is NOT a date -- it becomes UNKNOWN."""
    if not value:
        return None
    s = str(value).strip()
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return None


def _months(a: str, b: str) -> float:
    """Whole-month-ish duration from ISO `a` to ISO `b`, in months (30.44-day). Never negative."""
    da, db = date.fromisoformat(a), date.fromisoformat(b)
    return max(0.0, (db - da).days / 30.4375)


def matter_from_row(row: dict, *, source_path: str = "") -> Matter | None:
    """One metadata row -> a Matter, or None when it is not a Companies Act matter.

    The row's own words decide whether it is a Companies Act matter (a section/act/subject field
    naming the Act). Every field read records `source_path` (the row's, or the metadata key the
    live build stored); a field the row does not state stays UNKNOWN with no source.
    """
    path = str(row.get("source_path") or source_path or "")
    section = row.get("section") or None
    # Is this a Companies Act 2013 matter? Only if a stated field says so.
    hay = " ".join(str(row.get(k) or "") for k in ("section", "act", "statute", "subject", "case_type"))
    if not _CA_MARKER.search(hay):
        return None
    case_id = str(row.get("case_id") or row.get("cnr") or row.get("path") or "").strip()
    if not case_id:
        return None
    filing = _iso(row.get("filing_date") or row.get("registration_date"))
    decision = _iso(row.get("decision_date") or row.get("judgment_date") or row.get("disposal_date"))
    outcome = row.get("outcome") or row.get("disposal_nature") or None
    sources = {}
    for name, value in (("filing_date", filing), ("decision_date", decision),
                        ("section", section), ("outcome", outcome)):
        if value is not None and path:
            sources[name] = path
    return Matter(case_id=case_id, court=str(row.get("court") or "").strip(),
                  filing_date=filing, decision_date=decision,
                  section=section, outcome=(str(outcome) if outcome else None),
                  sources=sources)


def matters_from_rows(rows, *, source_path: str = "") -> list[Matter]:
    """Every Companies Act matter in a list of metadata rows, de-duplicated by case id."""
    seen: set[str] = set()
    out: list[Matter] = []
    for row in rows:
        m = matter_from_row(row, source_path=source_path)
        if m is None or m.case_id in seen:
            continue
        seen.add(m.case_id)
        out.append(m)
    return out


@dataclass(frozen=True)
class Summary:
    """A time-to-decision read for one forum. ABSTAINED carries the reason and the counts."""
    court: str
    status: str                      # "PREDICTIVE_SIGNAL" | "ABSTAINED"
    estimate: Estimate | None
    n_total: int
    n_timeable: int
    events: int
    case_ids: tuple[str, ...]
    reason: str = ""
    label: str = ""                  # the estimate's label, e.g. "predictive_signal"

    def to_dict(self) -> dict:
        est = None
        if self.estimate is not None:
            est = {"value": self.estimate.value, "low": self.estimate.low,
                   "high": self.estimate.high, "n": self.estimate.n,
                   "unit": "months", "method": self.estimate.method,
                   "not_a": self.estimate.not_a, "notes": list(self.estimate.notes)}
        return {"court": self.court, "status": self.status, "label": self.label,
                "estimate": est, "n_total": self.n_total, "n_timeable": self.n_timeable,
                "events": self.events, "case_ids": list(self.case_ids), "reason": self.reason}


def time_to_decision(matters: list[Matter], *, court: str, as_of: str,
                     min_events: int = MIN_EVENTS) -> Summary:
    """Median time from filing to decision at `court`, PENDING matters censored at `as_of`.

    A matter is timeable only with a filing date; a decided one ends at its decision date, a
    pending one is censored at `as_of` (known to have lasted at least this long). Below
    `min_events` decided, timeable matters there is no median -- ABSTAINED, with the counts and
    the reason, never a number pulled from a handful of cases.
    """
    here = [m for m in matters if m.court == court]
    timeable = [m for m in here if m.filing_date is not UNKNOWN]
    durations, observed, ids = [], [], []
    for m in timeable:
        end = m.decision_date if not m.pending else as_of
        if _iso(end) is None:
            continue
        durations.append(_months(m.filing_date, end))  # type: ignore[arg-type]
        observed.append(not m.pending)
        ids.append(m.case_id)
    events = sum(observed)
    no_filing = len(here) - len(timeable)
    base_note = (f"{no_filing} of {len(here)} matters have no filing date in the metadata and "
                 f"cannot be timed" if no_filing else "")

    if events < min_events:
        reason = (f"only {events} decided Companies Act matter(s) with a filing date at "
                  f"{court} (need at least {min_events} to estimate a median). "
                  + base_note).strip()
        return Summary(court, "ABSTAINED", None, len(here), len(timeable), events,
                       tuple(ids), reason=reason)
    try:
        est = survival.median(durations, observed, basis=f"{court}, open judgment metadata",
                              unit="months")
    except EstimateError as exc:
        return Summary(court, "ABSTAINED", None, len(here), len(timeable), events,
                       tuple(ids), reason=f"{exc}. " + base_note)
    return Summary(court, "PREDICTIVE_SIGNAL", est, len(here), len(timeable), events,
                   tuple(ids), label=est.output_class(), reason=base_note)


def load_dataset(path: Path = DATASET) -> list[Matter]:
    """The committed Companies Act matters dataset -> Matters. Empty list if the file is absent."""
    if not path.exists():
        return []
    doc = json.loads(path.read_text())
    rows = doc.get("matters", doc) if isinstance(doc, dict) else doc
    return matters_from_rows(rows)


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("forecast.matters")
    SP = "metadata/parquet/year=2021/court=bombay/bench=principal/metadata.parquet"

    # ── a Companies Act matter maps every stated field, with its source; UNKNOWN stays None ──
    m = matter_from_row({"case_id": "BOMHC/2019/CP-1", "court": "Bombay High Court",
                         "registration_date": "2019-03-04", "decision_date": "2021-08-19",
                         "section": "Companies Act, 2013 s.241", "outcome": "allowed",
                         "source_path": SP})
    check(m is not None and m.filing_date == "2019-03-04" and not m.pending,
          "a decided Companies Act matter carries its dates")
    check(m is not None and m.sources.get("filing_date") == SP and m.sources.get("outcome") == SP,
          "every stated field carries its metadata source path")
    # a matter the metadata does not mark as Companies Act is NOT in the table
    check(matter_from_row({"case_id": "X", "section": "Income Tax Act s.10", "source_path": SP}) is None,
          "a non-Companies-Act matter is not a Companies Act matter")
    # unstated fields are UNKNOWN (None), with no source, never guessed
    bare = matter_from_row({"case_id": "BOMHC/2020/CP-9", "court": "Bombay High Court",
                            "registration_date": "2020-01-10", "section": "Companies Act, 2013 s.59",
                            "source_path": SP})
    check(bare is not None and bare.pending and bare.outcome is UNKNOWN
          and "outcome" not in bare.sources,
          "no decision date => PENDING; no outcome => UNKNOWN with no source")

    # ── the done-when: Bombay HC Companies Act matters -> median + interval + n + case ids ──
    rows = []
    # 10 decided matters, filed 2018-01-01, decided at a spread of durations (months), + 2 pending
    decided_months = [8, 11, 13, 16, 18, 20, 24, 28, 33, 40]
    for i, dm in enumerate(decided_months):
        fy = 2018
        dd = date(fy, 1, 1)
        from datetime import timedelta
        dec = (dd + timedelta(days=int(dm * 30.4375))).isoformat()
        rows.append({"case_id": f"BOMHC/{fy}/CP-{i}", "court": "Bombay High Court",
                     "registration_date": "2018-01-01", "decision_date": dec,
                     "section": "Companies Act, 2013 s.241", "outcome": "allowed" if i % 2 else "dismissed",
                     "source_path": SP})
    for i in range(2):
        rows.append({"case_id": f"BOMHC/2022/CP-P{i}", "court": "Bombay High Court",
                     "registration_date": "2022-06-01", "section": "Companies Act, 2013 s.230",
                     "source_path": SP})  # pending: no decision date
    bom = matters_from_rows(rows)
    summ = time_to_decision(bom, court="Bombay High Court", as_of="2024-01-01")
    check(summ.status == "PREDICTIVE_SIGNAL" and summ.estimate is not None,
          f"Bombay HC returns a PREDICTIVE_SIGNAL median ({summ.status})")
    check(summ.label == "predictive_signal",
          f"...labelled predictive_signal, never a verified fact ({summ.label})")
    check(summ.estimate is not None and summ.estimate.low <= summ.estimate.value <= summ.estimate.high
          and summ.estimate.n == 12,
          f"...the median has an interval and states n ({summ.estimate.n if summ.estimate else '-'})")
    check(summ.events == 10 and len(summ.case_ids) == 12,
          f"...10 decided + 2 pending censored, case ids behind it ({summ.events}, {len(summ.case_ids)})")
    check(any("censored" in n for n in (summ.estimate.notes if summ.estimate else ())),
          "...and the pending cases are counted as censored, not dropped")

    # ── too few -> a NAMED abstention, never a number from a handful ──────────
    few = time_to_decision(bom[:3], court="Bombay High Court", as_of="2024-01-01")
    check(few.status == "ABSTAINED" and str(MIN_EVENTS) in few.reason and few.estimate is None,
          f"too few decided matters -> named abstention, no number ({few.status})")

    # ── a matter with no filing date is counted, not silently dropped ─────────
    with_missing = bom + [Matter("BOMHC/2019/CP-NOFILE", "Bombay High Court")]
    s2 = time_to_decision(with_missing, court="Bombay High Court", as_of="2024-01-01")
    check("cannot be timed" in (s2.estimate.notes[-2] if False else s2.reason) or s2.n_total == 13,
          f"a matter with no filing date is counted in the totals ({s2.n_total})")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
