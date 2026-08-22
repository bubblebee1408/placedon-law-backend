"""
Section 96 AGM deadline — the proof artifact for this system's core thesis.

s.96 is the right test because it is the smallest problem that exercises everything: an admitted
source, a quoted interval, a fact the user supplies, arithmetic the statute cannot contain, and a
result that must never be presented as text lifted from the Act.

**Why this is not one interval.** s.96(1) carries three, and the naive reading picks the wrong one.
Feeding the whole section to `derived_date.parse_interval` returns "fifteen months" -- the first
match in the text -- and computes 30 June 2027 for a 31 March 2026 year end. The correct ordinary
answer is 30 September 2026. A nine-month error on a statutory deadline, produced by code that looks
like it works.

The three limbs:

    first AGM        within NINE months from the close of the FIRST financial year
    any other case   within SIX months from the close of the financial year
    every AGM        not more than FIFTEEN months between one AGM and the next

For a subsequent AGM both of the last two bind, and the deadline is the EARLIER. Reporting only the
six-month limb is wrong whenever the previous AGM was late, which is exactly when a company is
already in difficulty and most needs the right date.

**Missing facts are reported, never assumed.** A subsequent AGM cannot be computed without the
previous AGM's date: the fifteen-month limb is uncheckable and the answer might be earlier than the
six-month one. This module returns the constraints it could evaluate and names the fact it lacks,
rather than quietly returning the six-month date as though it were the deadline.

**The Registrar's extension is not applied.** s.96 lets the Registrar extend by up to three months
for special reason, other than for a first AGM. That is a discretionary act that may or may not have
happened; treating it as automatic would invent a three-month grace no company is entitled to. It is
surfaced as an available fact for a human.

Run: python3 checker/agm.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from checker.derived_date import _add_months

__all__ = ["Constraint", "AGMDeadline", "compute", "FIRST_AGM_LIMB", "ORDINARY_LIMB", "GAP_LIMB"]

CITATION = "Companies Act 2013, s.96(1)"

# Each limb names the phrase that MUST appear verbatim in the provision. If the section is ever
# amended and a phrase disappears, compute() raises rather than silently using a stale interval --
# the same principle as derived_date: verify the interval against source, never the result.
FIRST_AGM_LIMB = ("first AGM", "nine months", 9,
                  "within a period of nine months from the date of closing of the first financial "
                  "year")
ORDINARY_LIMB = ("ordinary", "six months", 6,
                 "within a period of six months, from the date of closing of the financial year")
GAP_LIMB = ("gap since previous AGM", "fifteen months", 15,
            "not more than fifteen months shall elapse between the date of one annual general "
            "meeting of a company and that of the next")

_EXTENSION = "extend the time within which any annual general meeting, other than the first"


class SourceMismatch(ValueError):
    """A limb's interval is absent from the provision text. The section may have been amended."""


@dataclass(frozen=True)
class Constraint:
    label: str
    interval_text: str          # verbatim from the provision
    months: int
    anchor: date
    anchor_label: str
    deadline: date

    def working(self) -> str:
        return (f"{self.anchor.isoformat()} ({self.anchor_label}, supplied by you)\n"
                f"  + {self.interval_text}  — verbatim from {CITATION}\n"
                f"  = {self.deadline.isoformat()}")


@dataclass(frozen=True)
class AGMDeadline:
    constraints: tuple[Constraint, ...]
    binding: Constraint | None
    missing_facts: tuple[str, ...]
    notes: tuple[str, ...]
    complete: bool              # every applicable limb was evaluable

    def to_dict(self) -> dict:
        return dict(
            citation=CITATION,
            binding_deadline=self.binding.deadline.isoformat() if self.binding else None,
            binding_limb=self.binding.label if self.binding else None,
            complete=self.complete,
            constraints=[dict(label=c.label, interval_text=c.interval_text,
                              anchor=c.anchor.isoformat(), anchor_label=c.anchor_label,
                              deadline=c.deadline.isoformat()) for c in self.constraints],
            missing_facts=list(self.missing_facts), notes=list(self.notes))

    def render(self) -> str:
        out = [f"AGM DEADLINE — {CITATION}", ""]
        for c in self.constraints:
            mark = "  <= BINDING" if self.binding and c is self.binding else ""
            out += [f"[{c.label}]{mark}", "  " + c.working().replace("\n", "\n  "), ""]
        if self.binding:
            out += [f"DEADLINE: {self.binding.deadline.isoformat()}"
                    f"  ({self.binding.label} limb is the earlier)"
                    if len(self.constraints) > 1 else
                    f"DEADLINE: {self.binding.deadline.isoformat()}", ""]
        else:
            out += ["DEADLINE: NOT DETERMINABLE — see missing facts", ""]
        if self.missing_facts:
            out += ["MISSING FACTS (the answer above is incomplete without these):"]
            out += [f"  - {m}" for m in self.missing_facts] + [""]
        if self.notes:
            out += ["NOTES:"] + [f"  - {n}" for n in self.notes] + [""]
        out += ["This deadline is DERIVED. The interval above is quoted from the provision; the",
                "date is arithmetic on a fact you supplied and appears nowhere in the Act.",
                "Requires human verification before it is relied on."]
        return "\n".join(out)


def _require(source_text: str, phrase: str, label: str) -> str:
    """The interval phrase, verified present in the provision. Raises if the source no longer says it."""
    flat = " ".join(source_text.split())
    if phrase.lower() not in flat.lower():
        raise SourceMismatch(
            f"{label}: {phrase!r} is not in the provision text. s.96 may have been amended, or the "
            "wrong provision was supplied. Refusing to compute from an interval the source does "
            "not state.")
    return phrase


def compute(*, source_text: str, financial_year_end: date, is_first_agm: bool,
            previous_agm: date | None = None) -> AGMDeadline:
    """The AGM deadline, with every applicable limb shown and the binding one identified."""
    constraints: list[Constraint] = []
    missing: list[str] = []
    notes: list[str] = []

    if is_first_agm:
        _, phrase, months, _ = FIRST_AGM_LIMB
        _require(source_text, phrase, "first-AGM limb")
        constraints.append(Constraint(
            "first AGM", phrase, months, financial_year_end,
            "close of the first financial year", _add_months(financial_year_end, months)))
        notes.append("The fifteen-month limb does not apply to a first AGM: there is no previous "
                     "AGM to measure from.")
        notes.append("The Registrar's power to extend does NOT extend to a first AGM.")
    else:
        _, phrase, months, _ = ORDINARY_LIMB
        _require(source_text, phrase, "ordinary limb")
        constraints.append(Constraint(
            "six months from FY close", phrase, months, financial_year_end,
            "close of the financial year", _add_months(financial_year_end, months)))

        _, gap_phrase, gap_months, _ = GAP_LIMB
        _require(source_text, gap_phrase, "fifteen-month limb")
        if previous_agm is None:
            # Not a footnote. Without it the fifteen-month limb cannot be evaluated, and it may be
            # the earlier of the two -- so the six-month date alone is not the deadline.
            missing.append(
                "date of the previous annual general meeting — without it the fifteen-month limb "
                "cannot be checked, and it may fall EARLIER than the six-month date")
        else:
            constraints.append(Constraint(
                "fifteen months since previous AGM", gap_phrase, gap_months, previous_agm,
                "date of the previous AGM", _add_months(previous_agm, gap_months)))

        if _EXTENSION.lower() in " ".join(source_text.split()).lower():
            notes.append("The Registrar may, for special reason, extend by up to three months "
                         "(not for a first AGM). NOT applied here — an extension is a "
                         "discretionary act that must be established as a fact, not assumed.")

    complete = not missing
    binding = min(constraints, key=lambda c: c.deadline) if (constraints and complete) else None
    if constraints and not complete:
        notes.append("A provisional earliest date is shown per limb, but no binding deadline is "
                     "stated while a required fact is missing.")
    return AGMDeadline(tuple(constraints), binding, tuple(missing), tuple(notes), complete)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    from checker.retrieve import MODE_MODEL, retrieve
    pack, _ = retrieve("s.96", mode=MODE_MODEL)
    check(bool(pack.usable), "s.96 is admitted and served")
    src = pack.usable[0].reading_text or pack.usable[0].raw_text

    # The headline case, and the one the naive implementation gets wrong.
    d = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=False,
                previous_agm=date(2025, 9, 20))
    check(d.binding.deadline == date(2026, 9, 30),
          f"FY end 31-03-2026, previous AGM 20-09-2025 -> 30-09-2026 ({d.binding.deadline})")
    check(d.binding.label.startswith("six months"), "the six-month limb binds here")
    check(len(d.constraints) == 2, "both applicable limbs are shown, not just the binding one")
    check(d.complete, "the answer is complete")

    # The case that makes the fifteen-month limb matter: a late previous AGM.
    late = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=False,
                   previous_agm=date(2025, 5, 10))
    check(late.binding.deadline == date(2026, 8, 10),
          f"a late previous AGM makes fifteen months bind: {late.binding.deadline}")
    check("fifteen months" in late.binding.label,
          "...and the binding limb is named as the fifteen-month one")
    check(late.binding.deadline < date(2026, 9, 30),
          "...which is EARLIER than the six-month date -- reporting six months alone would be wrong")

    # Missing fact: refuse to state a deadline.
    unknown = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=False)
    check(unknown.binding is None, "no previous AGM date -> no binding deadline is stated")
    check(not unknown.complete, "...the answer is marked incomplete")
    check(any("previous annual general meeting" in m for m in unknown.missing_facts),
          "...and the missing fact is named")
    check("NOT DETERMINABLE" in unknown.render(), "...and the rendering says so plainly")

    # First AGM: nine months, and the gap limb must not appear.
    first = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=True)
    check(first.binding.deadline == date(2026, 12, 31),
          f"first AGM, FY end 31-03-2026 -> 31-12-2026 ({first.binding.deadline})")
    check(len(first.constraints) == 1, "only the nine-month limb applies to a first AGM")
    check(any("does not apply to a first AGM" in n for n in first.notes),
          "...and the note explains why the fifteen-month limb is absent")

    # The extension is surfaced, never applied.
    check(any("NOT applied" in n for n in d.notes),
          "the Registrar's extension is surfaced but not applied")
    check(d.binding.deadline == date(2026, 9, 30),
          "...so the deadline is not silently extended by three months")

    # Interval verification: a source that no longer says it must refuse.
    try:
        compute(source_text="a provision that says nothing about months at all",
                financial_year_end=date(2026, 3, 31), is_first_agm=False)
        check(False, "a source lacking the interval must raise")
    except SourceMismatch as e:
        check("not in the provision text" in str(e),
              "an interval absent from source refuses, rather than using a remembered number")

    # Every interval shown is verbatim in the provision.
    flat = " ".join(src.split()).lower()
    check(all(c.interval_text.lower() in flat for c in d.constraints),
          "every interval quoted is verbatim in s.96")

    # The derived date must NOT appear in the Act -- that is what makes it derived.
    check("30 september" not in flat and "2026-09-30" not in flat,
          "the derived date appears nowhere in the provision, as expected")

    check("DERIVED" in d.render() and "human verification" in d.render(),
          "the rendering states the result is derived and needs verification")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
