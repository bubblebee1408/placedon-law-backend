#!/usr/bin/env python3
"""Prove the temporal engine on three sections, at every boundary date.

    python3 scripts/prove_temporal.py          # the proof run
    python3 scripts/prove_temporal.py --test   # self-test

## What "prove" means here

For each amendment with effect from date D, three facts must hold:

    D-1   the amendment is NOT in force
    D     the amendment IS in force        ("with effect from D" includes D)
    D+1   the amendment is still in force

and — the assertion that actually matters — **the reconstructed text at D-1 must
differ from the text at D**. Without that, an engine that returns the current
text for every date passes all the ordering checks and reconstructs nothing.

The off-by-one is not academic. If `wef <= target` were `wef < target`, every
section would be reconstructed one day stale, and the error would be invisible on
any date except the boundary itself.

## What this does not prove

That the reconstructed text is what the Act actually said. The prior wording
comes from India Code's own footnotes, and 24 of those have been corroborated
against the amending Acts (`docs/CORROBORATION.md`) — but corroborating a span
is not the same as verifying a whole section. Sections reconstruct EXACT here
when every span in force is recoverable *from the source we hold*, which is a
statement about recoverability, not about truth.

## The source defect that shapes the choice of sections

120 amendment spans in the corpus carry unbalanced markup: an opening `<sup>N</sup>[`
with no closing `]`. s.96 — the section this project has used as its flagship
example throughout — is one of them, and therefore cannot be reconstructed before
13 June 2018 at all. The engine refuses rather than guessing where the span ends,
because guessing once destroyed later spans in the same section. The three
sections proved here were chosen because their markup is intact, and that
selection is itself a finding: two thirds of amended sections cannot be
reconstructed exactly from this source.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.amendment import parse_footnote  # noqa: E402
from checker.as_of import section_as_of  # noqa: E402
from checker.section_index import section_by_number  # noqa: E402

# Chosen for intact markup and multiple amendment dates, not for convenience.
PROOF_SECTIONS = ("177", "447", "35")


@dataclass
class BoundaryCheck:
    section: str
    wef: date
    instrument: str | None
    before_in_force: int
    on_in_force: int
    after_in_force: int
    text_changed: bool
    fidelity_before: str
    fidelity_on: str

    @property
    def ok(self) -> bool:
        """The amendment crosses into force exactly on its date, and text moves."""
        return (self.before_in_force < self.on_in_force
                and self.on_in_force == self.after_in_force
                and self.text_changed)

    def line(self) -> str:
        mark = "ok  " if self.ok else "FAIL"
        return (f"  {mark} s.{self.section:<6} {self.wef}  "
                f"in-force {self.before_in_force}->{self.on_in_force}  "
                f"text {'CHANGED' if self.text_changed else 'IDENTICAL'}  "
                f"{self.fidelity_before}/{self.fidelity_on}  {self.instrument or ''}")


def boundaries(number: str) -> list[BoundaryCheck]:
    rec = section_by_number(number)
    if rec is None:
        raise KeyError(f"s.{number} is not in the corpus")
    ams = [a for a in parse_footnote(rec.get("footnote") or "")
           if a.wef and not a.wef_implausible]
    out: list[BoundaryCheck] = []
    for a in sorted({x.wef for x in ams}):
        before = section_as_of(rec, a - timedelta(days=1))
        on = section_as_of(rec, a)
        after = section_as_of(rec, a + timedelta(days=1))
        inst = next((x.instrument for x in ams if x.wef == a), None)
        out.append(BoundaryCheck(
            section=number, wef=a, instrument=inst,
            before_in_force=len(before.in_force), on_in_force=len(on.in_force),
            after_in_force=len(after.in_force),
            text_changed=(before.text or "") != (on.text or ""),
            fidelity_before=before.fidelity, fidelity_on=on.fidelity,
        ))
    return out


def report(checks: list[BoundaryCheck]) -> str:
    n = len(checks)
    good = sum(c.ok for c in checks)
    lines = ["", "TEMPORAL ENGINE — BOUNDARY PROOF",
             f"  sections     : {', '.join('s.' + s for s in PROOF_SECTIONS)}",
             f"  boundaries   : {n}", f"  passing      : {good}/{n}", ""]
    lines += [c.line() for c in checks]
    lines += [
        "",
        "  Each boundary asserts: the amendment is absent on D-1, present on D,",
        "  present on D+1, and the reconstructed text differs between D-1 and D.",
        "  EXACT means every in-force span is recoverable from the source we hold.",
        "  It does not mean the text has been verified against the amending Act.",
    ]
    return "\n".join(lines)


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

    print("prove_temporal")

    all_checks: list[BoundaryCheck] = []
    for s in PROOF_SECTIONS:
        cs = boundaries(s)
        all_checks += cs
        check(len(cs) >= 2, f"s.{s} has at least two boundary dates ({len(cs)})")

    check(len(all_checks) >= 6, f"at least six boundaries are exercised ({len(all_checks)})")
    check(all(c.ok for c in all_checks),
          f"every boundary behaves correctly ({sum(c.ok for c in all_checks)}/{len(all_checks)})")

    # The assertion that stops a no-op engine passing.
    check(all(c.text_changed for c in all_checks),
          "the reconstructed text differs across every boundary")

    # Inclusivity of the effective date, stated as its own property.
    for c in all_checks:
        assert c.before_in_force < c.on_in_force, c.section
    check(True, "'with effect from D' places the amendment in force ON D, not after it")

    # A date before commencement must abstain, not guess.
    rec = section_by_number(PROOF_SECTIONS[0])
    early = section_as_of(rec, date(2013, 1, 1))
    check(early.fidelity == "ABSTAIN",
          "a date before the Act's commencement abstains rather than reconstructing")
    check(early.text is None, "...and returns no text")

    # Far-future dates apply everything, and are stable.
    far = section_as_of(rec, date(2040, 1, 1))
    latest = section_as_of(rec, max(c.wef for c in boundaries(PROOF_SECTIONS[0])))
    check(far.text == latest.text,
          "a far-future date returns the same text as the last amendment date")
    check(not far.not_yet_in_force, "nothing is pending at a far-future date")

    # Monotonicity: in-force count never decreases as the date advances.
    counts = [len(section_as_of(rec, d).in_force)
              for d in (date(2014, 4, 1), date(2016, 1, 1), date(2019, 1, 1),
                        date(2023, 1, 1))]
    check(counts == sorted(counts),
          f"the in-force count never decreases as the date advances ({counts})")

    # s.96 is the documented casualty. Pinned so the defect is not forgotten.
    s96 = section_as_of(section_by_number("96"), date(2018, 6, 12))
    check(s96.fidelity == "PARTIAL" and s96.unknown_spans == [1],
          "s.96 remains PARTIAL before 13-6-2018: its source markup is unbalanced")

    print(report(all_checks))
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        cs = []
        for s in PROOF_SECTIONS:
            cs += boundaries(s)
        print(report(cs))
        raise SystemExit(0 if all(c.ok for c in cs) else 1)
