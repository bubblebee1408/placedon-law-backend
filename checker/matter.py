"""
The matter: the facts a legal answer stands on, held so they cannot be half-supplied.

Everything downstream of this file -- the s.96 deadline, the working shown to the user, the drafted
document -- is arithmetic and templating over facts a human typed. That makes the fact object the
weakest joint in the chain, and the one place where a plausible-looking wrong answer is cheapest to
produce. Two failures matter more than any other:

  1. **A contradictory matter that computes anyway.** "This is the first AGM" together with "the
     previous AGM was on 10 May 2025" is not a hard case; it is two mutually exclusive claims. If
     the object accepts both, `checker.agm.compute` will honour `is_first_agm` and quietly answer on
     the nine-month limb while the fifteen-month limb sits in the record unread. The output is a
     confident date that is wrong by months, and nothing in it looks wrong. So construction refuses.

  2. **A half-populated input handed to a legal calculation.** `checker.agm` already refuses to state
     a deadline for a subsequent AGM without the previous AGM's date. But by then the user has asked
     the question and been told nothing. `missing_for_agm()` lets the workspace name the gap BEFORE
     the computation is attempted, and `agm_inputs()` refuses to build a half-filled call at all.

No deadline is computed here. This module holds facts and refuses bad ones; `checker/agm.py` owns
s.96 and is the only place the intervals live. Keeping those apart is what stops a second, drifting
copy of the statutory arithmetic appearing in the fact layer.

`created_at` is passed in, never read from the clock -- the same rule as `checker/admission.py`, so
a test can assert exact values and a matter can be rebuilt from storage identically.

**Origin, not just value.** `provenance()` labels every value USER_FACT. Today that is the only
origin there is, which makes the method look like ceremony. It is not: the drafting layer prints
these values next to text quoted from the Act, and a date the user typed must never be presented
with the authority of a statute. When facts later arrive from an MCA filing or are derived by this
system, the label is the seam that keeps the three apart, and it has to exist before it is needed.

Run: PYTHONPATH=. python3 checker/matter.py
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent

# Mirrors checker/assessment.py: this module is run both as a bare file and through
# scripts/run_tests.sh (which exports PYTHONPATH).
if __package__ in (None, ""):  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(ROOT))

from checker.derived_date import _add_months  # noqa: E402

__all__ = [
    "Matter", "MatterError", "FactProvenance",
    "COMPANY_TYPES", "PRIVATE", "PUBLIC", "LISTED", "OPC", "SECTION_8",
    "USER_FACT", "FACT_ORIGINS", "MISSING_PREVIOUS_AGM",
]

# Strings rather than an Enum, following checker/admission.py: these ride into JSON and must
# survive the round trip unchanged.
PRIVATE = "PRIVATE"
PUBLIC = "PUBLIC"
LISTED = "LISTED"
OPC = "OPC"                  # One Person Company
SECTION_8 = "SECTION_8"      # not-for-profit licensed under s.8

COMPANY_TYPES = (PRIVATE, PUBLIC, LISTED, OPC, SECTION_8)

# Where a value came from. One member today, and the point of the vocabulary is that the second
# one (a fact read out of a filing, or one this system derived) cannot be added by accident.
USER_FACT = "USER_FACT"
FACT_ORIGINS = (USER_FACT,)

# The wording deliberately echoes checker/agm.py's missing-fact text, so the workspace warns in the
# same words the computation would have used had it been reached.
MISSING_PREVIOUS_AGM = (
    "date of the previous annual general meeting — this is not a first AGM, and without it the "
    "fifteen-month limb of s.96 cannot be checked; it may fall EARLIER than the six-month date")

# s.96's outer limb. Used here ONLY to reject an ordering that no sequence of AGMs could produce --
# never to compute a deadline. That arithmetic belongs to checker/agm.py and lives there alone.
_GAP_LIMB_MONTHS = 15


class MatterError(ValueError):
    """A contradictory or impossible set of facts, or a legal call attempted without them."""


@dataclass(frozen=True)
class FactProvenance:
    """One value and where it came from. Never 'the Act says' for anything in here."""
    field: str
    value: str
    origin: str

    def describe(self) -> str:
        return f"{self.field} = {self.value}  [{self.origin} — supplied by you, not stated in any Act]"

    def to_dict(self) -> dict:
        return dict(field=self.field, value=self.value, origin=self.origin)


@dataclass(frozen=True)
class Matter:
    """A corporate-law matter: the company, its financial year, and its AGM history.

    Immutable, and validated at construction rather than at use. A caller who hand-builds one with
    contradictory dates gets an exception here, not a wrong deadline three modules later.
    """
    matter_id: str
    company_name: str
    company_type: str
    financial_year_end: date
    created_at: str                       # ISO-8601, passed in; this module never reads the clock
    incorporation_date: date | None = None
    previous_agm: date | None = None
    is_first_agm: bool = False
    facts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("matter_id", "company_name"):
            if not str(getattr(self, name) or "").strip():
                raise MatterError(f"{name} is required — an unidentified matter cannot be audited")

        if self.company_type not in COMPANY_TYPES:
            # Not a warning. An unrecognised type would fall through every downstream
            # applicability test as "not one of the ones that bite", which reads as a clean bill.
            raise MatterError(
                f"{self.company_type!r} is not a company type; one of {', '.join(COMPANY_TYPES)}")

        for name in ("financial_year_end", "incorporation_date", "previous_agm"):
            v = getattr(self, name)
            if v is not None and not isinstance(v, date):
                raise MatterError(f"{name} must be a date, got {type(v).__name__}")

        try:
            datetime.fromisoformat(str(self.created_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise MatterError(
                f"created_at={self.created_at!r} is not an ISO-8601 timestamp. It is passed in "
                "rather than read from the clock, so a malformed one is a caller bug, not a "
                "value to tolerate.") from None

        if self.is_first_agm and self.previous_agm is not None:
            raise MatterError(
                f"{self.matter_id}: is_first_agm=True with previous_agm="
                f"{self.previous_agm.isoformat()} is contradictory. s.96 applies a nine-month limb "
                "to a first AGM and a six/fifteen-month pair to any other; accepting both facts "
                "would compute one limb and silently ignore the other.")

        if (self.incorporation_date is not None
                and self.financial_year_end < self.incorporation_date):
            raise MatterError(
                f"{self.matter_id}: financial_year_end {self.financial_year_end.isoformat()} is "
                f"before incorporation_date {self.incorporation_date.isoformat()} — the company "
                "did not exist for that financial year.")

        if (self.incorporation_date is not None and self.previous_agm is not None
                and self.previous_agm < self.incorporation_date):
            raise MatterError(
                f"{self.matter_id}: previous_agm {self.previous_agm.isoformat()} is before "
                f"incorporation_date {self.incorporation_date.isoformat()} — a company cannot "
                "have held a general meeting before it existed.")

        if self.previous_agm is not None:
            outer = _add_months(self.financial_year_end, _GAP_LIMB_MONTHS)
            if self.previous_agm > outer:
                # Not an arithmetic impossibility -- a legal one. The AGM for THIS financial year
                # must fall within fifteen months of the previous AGM AND within six months of this
                # year end; a previous AGM this far ahead of the year end cannot be the immediately
                # preceding one. Computing from it would produce a deadline well past the point the
                # company is already in default, presented as though it were the date to meet.
                raise MatterError(
                    f"{self.matter_id}: previous_agm {self.previous_agm.isoformat()} is more than "
                    f"fifteen months after financial_year_end "
                    f"{self.financial_year_end.isoformat()} (outer limit {outer.isoformat()}). "
                    "No AGM for this financial year could satisfy s.96 measured from it — the "
                    "dates are inconsistent, or this is not the immediately preceding AGM.")

        if not isinstance(self.facts, Mapping):
            raise MatterError(f"facts must be a mapping, got {type(self.facts).__name__}")
        for k in self.facts:
            if not isinstance(k, str) or not k.strip():
                raise MatterError(f"fact key {k!r} must be a non-empty string")
        # Copy, then freeze: a caller who keeps a reference to the dict they passed must not be
        # able to change this matter's facts after it was validated.
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))

    # --- what is missing, said before the calculation is attempted --------------------------------

    def missing_for_agm(self) -> tuple[str, ...]:
        """Facts absent for an s.96 computation. Empty when the question can be answered.

        Only what `checker.agm.compute` actually consumes is listed. Naming a fact that is not
        needed would train a user to ignore the list, which is worse than not having one.
        """
        if not self.is_first_agm and self.previous_agm is None:
            return (MISSING_PREVIOUS_AGM,)
        return ()

    def agm_inputs(self) -> dict:
        """Keyword arguments for `checker.agm.compute`, or a refusal.

        `source_text` is deliberately not supplied: the matter holds facts, never statutory text.
        Call as `compute(source_text=..., **matter.agm_inputs())`.
        """
        missing = self.missing_for_agm()
        if missing:
            raise MatterError(
                f"{self.matter_id}: cannot build s.96 inputs while {len(missing)} fact(s) are "
                "missing — " + "; ".join(missing))
        return dict(financial_year_end=self.financial_year_end,
                    is_first_agm=self.is_first_agm,
                    previous_agm=self.previous_agm)

    # --- origin ----------------------------------------------------------------------------------

    def provenance(self) -> tuple[FactProvenance, ...]:
        """Every held value, labelled with where it came from. Absent optionals are not claimed."""
        out: list[FactProvenance] = []
        for f in fields(self):
            if f.name == "facts":
                continue
            v = getattr(self, f.name)
            if v is None:
                continue
            out.append(FactProvenance(f.name, _iso(v), USER_FACT))
        for k, v in self.facts.items():
            out.append(FactProvenance(f"facts.{k}", _iso(v), USER_FACT))
        return tuple(out)

    # --- storage ----------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        return dict(
            matter_id=self.matter_id,
            company_name=self.company_name,
            company_type=self.company_type,
            financial_year_end=self.financial_year_end.isoformat(),
            created_at=self.created_at,
            incorporation_date=(self.incorporation_date.isoformat()
                                if self.incorporation_date else None),
            previous_agm=self.previous_agm.isoformat() if self.previous_agm else None,
            is_first_agm=self.is_first_agm,
            facts=dict(self.facts))

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Matter":
        try:
            return cls(
                matter_id=d["matter_id"],
                company_name=d["company_name"],
                company_type=d["company_type"],
                financial_year_end=_parse_date(d["financial_year_end"], "financial_year_end"),
                created_at=d["created_at"],
                incorporation_date=_parse_date(d.get("incorporation_date"), "incorporation_date"),
                previous_agm=_parse_date(d.get("previous_agm"), "previous_agm"),
                is_first_agm=bool(d.get("is_first_agm", False)),
                facts=d.get("facts") or {})
        except KeyError as e:
            raise MatterError(f"stored matter is missing required field {e}") from None


def _parse_date(v: Any, label: str) -> date | None:
    if v is None or isinstance(v, date):
        return v
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise MatterError(f"{label}={v!r} is not an ISO date (YYYY-MM-DD)") from None


def _iso(v: Any) -> str:
    return v.isoformat() if isinstance(v, date) else str(v)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    T = "2026-08-22T09:00:00Z"

    def make(**kw) -> Matter:
        base = dict(matter_id="M-1", company_name="Acme Widgets Private Limited",
                    company_type=PRIVATE, financial_year_end=date(2026, 3, 31), created_at=T)
        return Matter(**{**base, **kw})

    m = make(previous_agm=date(2025, 9, 20), incorporation_date=date(2019, 6, 1))
    check(m.company_type == PRIVATE and m.previous_agm == date(2025, 9, 20),
          "a well-formed matter constructs")
    check(m.missing_for_agm() == (), "a complete matter reports nothing missing")

    # --- validation that refuses ------------------------------------------------------------------
    try:
        make(is_first_agm=True, previous_agm=date(2025, 5, 10))
        check(False, "first AGM + a previous AGM must raise")
    except MatterError as e:
        check("contradictory" in str(e),
              "is_first_agm=True with a previous_agm refuses at construction")

    try:
        make(previous_agm=date(2027, 8, 1))
        check(False, "a previous AGM beyond fifteen months after FY end must raise")
    except MatterError as e:
        check("fifteen months" in str(e),
              "a previous AGM more than fifteen months after FY end is refused as inconsistent")

    edge = make(previous_agm=date(2027, 6, 30))
    check(edge.previous_agm == date(2027, 6, 30),
          "...and the boundary itself (FY end + exactly fifteen months) is still accepted")

    try:
        make(incorporation_date=date(2026, 6, 1))
        check(False, "FY end before incorporation must raise")
    except MatterError as e:
        check("did not exist" in str(e), "a financial year ending before incorporation is refused")

    try:
        make(incorporation_date=date(2025, 11, 1), previous_agm=date(2025, 9, 20))
        check(False, "an AGM before incorporation must raise")
    except MatterError as e:
        check("before it existed" in str(e), "an AGM held before incorporation is refused")

    try:
        make(company_type="LLP")
        check(False, "an unknown company type must raise")
    except MatterError as e:
        check("is not a company type" in str(e),
              "an unknown company type is refused, not passed through as harmless")

    try:
        make(company_name="   ")
        check(False, "a blank company name must raise")
    except MatterError:
        check(True, "a matter with no company name is refused")

    try:
        make(created_at="last Tuesday")
        check(False, "a malformed created_at must raise")
    except MatterError as e:
        check("ISO-8601" in str(e), "created_at is validated, never read from the clock")

    try:
        make(financial_year_end="2026-03-31")
        check(False, "a string financial_year_end must raise")
    except MatterError as e:
        check("must be a date" in str(e), "a stringly-typed date is refused at the boundary")

    # --- missing facts, named before the computation is attempted ---------------------------------
    incomplete = make()
    check(len(incomplete.missing_for_agm()) == 1,
          "a subsequent AGM with no previous AGM reports exactly one missing fact")
    check("previous annual general meeting" in incomplete.missing_for_agm()[0],
          "...and names the previous AGM, in the same words checker/agm.py would have used")

    first = make(is_first_agm=True)
    check(first.missing_for_agm() == (),
          "a first AGM needs no previous AGM, so nothing is reported missing")

    try:
        incomplete.agm_inputs()
        check(False, "agm_inputs() with a missing fact must raise")
    except MatterError as e:
        check("cannot build s.96 inputs" in str(e) and "previous annual general meeting" in str(e),
              "agm_inputs() refuses to hand a half-populated input to a legal calculation")

    check(m.agm_inputs() == dict(financial_year_end=date(2026, 3, 31), is_first_agm=False,
                                 previous_agm=date(2025, 9, 20)),
          "a complete matter yields exactly compute()'s keyword arguments")
    check("source_text" not in m.agm_inputs(),
          "...and does not carry statutory text — the matter holds facts only")

    # --- immutability ------------------------------------------------------------------------------
    supplied = {"turnover_inr": 90_000_000}
    withfacts = make(previous_agm=date(2025, 9, 20), facts=supplied)
    supplied["turnover_inr"] = 1
    check(withfacts.facts["turnover_inr"] == 90_000_000,
          "facts are copied at construction — mutating the caller's dict cannot alter the matter")
    try:
        withfacts.facts["turnover_inr"] = 2          # type: ignore[index]
        check(False, "the facts mapping must not be writable")
    except TypeError:
        check(True, "the held facts mapping is read-only")

    # --- provenance --------------------------------------------------------------------------------
    p = withfacts.provenance()
    check(all(x.origin == USER_FACT for x in p), "every value is labelled USER_FACT")
    by_field = {x.field: x.value for x in p}
    check(by_field["financial_year_end"] == "2026-03-31", "dates are rendered ISO in provenance")
    check("facts.turnover_inr" in by_field, "user-supplied extra facts carry provenance too")
    check("incorporation_date" not in by_field,
          "an absent optional is omitted rather than claimed as a fact")
    check("not stated in any Act" in p[0].describe(),
          "a user-supplied value is never presented as if it came from the Act")

    # --- round trip ---------------------------------------------------------------------------------
    d = withfacts.to_dict()
    check(d["financial_year_end"] == "2026-03-31" and d["previous_agm"] == "2025-09-20",
          "to_dict() renders dates as ISO strings")
    back = Matter.from_dict(d)
    check(back == withfacts, "to_dict() -> from_dict() round-trips to an equal matter")
    check(back.to_dict() == d, "...and back again to an identical dict")
    check(Matter.from_dict(make().to_dict()).previous_agm is None,
          "a None optional survives the round trip as None")
    try:
        Matter.from_dict({k: v for k, v in d.items() if k != "company_type"})
        check(False, "a stored matter missing a required field must raise")
    except MatterError as e:
        check("missing required field" in str(e), "an incomplete stored record is refused")
    try:
        Matter.from_dict({**d, "previous_agm": "20-09-2025"})
        check(False, "a non-ISO stored date must raise")
    except MatterError as e:
        check("is not an ISO date" in str(e), "a non-ISO stored date is refused, not guessed at")

    # --- integration: the matter actually feeds the legal engine ------------------------------------
    # The case where the fifteen-month limb binds. If agm_inputs() mislabelled or dropped a fact,
    # compute() would answer 2026-09-30 on the six-month limb and look entirely plausible.
    from checker.agm import compute
    from checker.retrieve import MODE_MODEL, retrieve

    pack, _ = retrieve("s.96", mode=MODE_MODEL)
    check(bool(pack.usable), "s.96 is admitted and served")
    src = pack.usable[0].reading_text or pack.usable[0].raw_text

    late = Matter(matter_id="M-2", company_name="Kaveri Textiles Limited", company_type=PUBLIC,
                  financial_year_end=date(2026, 3, 31), previous_agm=date(2025, 5, 10),
                  is_first_agm=False, created_at=T)
    result = compute(source_text=src, **late.agm_inputs())
    check(result.binding is not None and result.binding.deadline == date(2026, 8, 10),
          f"matter -> compute() gives the binding s.96 deadline 2026-08-10 "
          f"({result.binding.deadline if result.binding else None})")
    check("fifteen months" in result.binding.label,
          "...on the fifteen-month limb, because the previous AGM was late")
    check(result.complete and not result.missing_facts,
          "...and the answer is complete — the matter supplied every fact s.96 needed")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
