"""Backtest: run the register over a real company and compare with what a
professional certified about it.

`README.md` concedes the two things that block trust: no practising lawyer has
reviewed any output, and there is no real-document benchmark. Hiring a lawyer closes
the first. This module attacks the second for nothing, using a source the source
policy already permits -- public listed-company disclosures.

## The mechanism

A listed company's annual report states, on the record, the facts the obligation
register consumes: board composition, meeting dates, AGM date, CSR applicability,
audit-committee constitution, KMP, related-party transactions. The **secretarial audit
report (Form MR-3)** carries a Company Secretary's signed opinion on compliance with
those same provisions.

So the engine can be run over the disclosed facts and compared against a professional's
certification of the same company, in the same year.

## Why a mismatch is not automatically our error

This is the part that makes the exercise worth doing rather than merely reassuring.
A disagreement has three possible causes, and they are NOT collapsed:

  - **ENGINE_DEFECT** — we are wrong. A bug, a misread provision, a missing limb.
  - **SOURCE_FINDING** — the certification is wrong, or the disclosure contradicts it.
    This is the ICSI-specimen finding again, on a real company, and it is the most
    persuasive artifact this project can put in front of a practitioner.
  - **UNDERSPECIFIED** — the filing does not carry the facts the provision needs, so
    neither party is wrong and the engine should have abstained.

Classifying a mismatch is a **legal judgement** and this module will not make it. It
records the mismatch, states the three candidate causes, and marks it
`NEEDS_REVIEW`. Auto-classifying would be the labelling trap in a new costume: the
system grading its own homework and scoring itself well.

## What this is NOT

Not an accuracy claim. A run produces a `Scorecard` whose headline number is the
**agreement rate**, explicitly not "accuracy", because the comparator is a
professional's opinion rather than adjudicated truth. `Scorecard.accuracy_claim()`
exists solely to refuse, in words, and name what would be needed instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Cause(str, Enum):
    ENGINE_DEFECT = "ENGINE_DEFECT"
    SOURCE_FINDING = "SOURCE_FINDING"
    UNDERSPECIFIED = "UNDERSPECIFIED"


class Outcome(str, Enum):
    AGREE = "AGREE"                 # engine and certification say the same thing
    MISMATCH = "MISMATCH"           # they differ — cause unclassified, needs review
    ENGINE_ABSTAINED = "ENGINE_ABSTAINED"   # engine refused; certification asserted
    NOT_CERTIFIED = "NOT_CERTIFIED"  # the filing says nothing about this provision


@dataclass(frozen=True)
class Certified:
    """One assertion read off a public filing. Evidence, never truth.

    `locator` is mandatory and must point into the document (page, note, para). An
    assertion nobody can find again is not evidence, and the whole value of this
    exercise is that a sceptical reader can check every line.
    """
    obligation_id: str
    complied: bool | None          # None = the filing addresses it but is equivocal
    locator: str                   # e.g. "MR-3 p.2 para 4" / "AR FY24-25 p.118 note 31"
    quote: str = ""

    def __post_init__(self) -> None:
        if not self.locator.strip():
            raise ValueError(
                "a certified assertion needs a locator into the document — an "
                "assertion nobody can find again is not evidence")


@dataclass(frozen=True)
class Comparison:
    obligation_id: str
    engine_state: str
    engine_basis: str
    certified: Certified | None
    outcome: Outcome
    candidate_causes: tuple[Cause, ...] = ()
    note: str = ""

    @property
    def needs_review(self) -> bool:
        return self.outcome in (Outcome.MISMATCH, Outcome.ENGINE_ABSTAINED)


# States the engine can emit that mean "I did not decide".
_ABSTAINED = {"CANNOT_DETERMINE", "APPLIES_UNDETERMINED", "UNVERIFIED"}
# States that mean "the duty is discharged".
_SATISFIED = {"APPLIES_SATISFIED"}
# States that mean "it is not".
_NOT_SATISFIED = {"APPLIES_NOT_SATISFIED"}


def compare(obligation_id: str, engine_state: str, engine_basis: str,
            certified: Certified | None) -> Comparison:
    """Compare one engine row against one certified assertion. Classifies NOTHING."""
    if certified is None:
        return Comparison(obligation_id, engine_state, engine_basis, None,
                          Outcome.NOT_CERTIFIED,
                          note="the filing does not address this provision; no comparison "
                               "is possible and none is invented")

    if engine_state in _ABSTAINED:
        return Comparison(
            obligation_id, engine_state, engine_basis, certified,
            Outcome.ENGINE_ABSTAINED,
            candidate_causes=(Cause.UNDERSPECIFIED, Cause.ENGINE_DEFECT),
            note="the engine declined where a professional was willing to certify. "
                 "Either the filing lacks facts the provision needs (abstention correct) "
                 "or the engine is over-refusing (a defect). A human decides which.")

    if certified.complied is None:
        return Comparison(obligation_id, engine_state, engine_basis, certified,
                          Outcome.NOT_CERTIFIED,
                          note="the filing is equivocal; it is not a comparator")

    engine_says_ok = engine_state in _SATISFIED
    engine_says_not = engine_state in _NOT_SATISFIED
    if not (engine_says_ok or engine_says_not):
        return Comparison(obligation_id, engine_state, engine_basis, certified,
                          Outcome.NOT_CERTIFIED,
                          note=f"engine state {engine_state!r} is not comparable to a "
                               "compliance certification")

    if engine_says_ok == certified.complied:
        return Comparison(obligation_id, engine_state, engine_basis, certified,
                          Outcome.AGREE)

    return Comparison(
        obligation_id, engine_state, engine_basis, certified, Outcome.MISMATCH,
        candidate_causes=(Cause.ENGINE_DEFECT, Cause.SOURCE_FINDING, Cause.UNDERSPECIFIED),
        note="engine and certification disagree. This is NOT scored as an engine error: "
             "it is unclassified until a human reads both. If the certification is the "
             "one at fault, this is the finding the product exists to produce.")


@dataclass
class Scorecard:
    company: str
    financial_year: str
    comparisons: list[Comparison] = field(default_factory=list)

    def _count(self, o: Outcome) -> int:
        return sum(1 for c in self.comparisons if c.outcome is o)

    @property
    def comparable(self) -> int:
        return self._count(Outcome.AGREE) + self._count(Outcome.MISMATCH)

    @property
    def agreement_rate(self) -> float | None:
        """Agreement with a professional's opinion. Deliberately NOT 'accuracy'."""
        return None if not self.comparable else self._count(Outcome.AGREE) / self.comparable

    def review_queue(self) -> list[Comparison]:
        """Everything a human must look at, mismatches first — those are the ones
        that are either a bug or a sellable finding."""
        return sorted((c for c in self.comparisons if c.needs_review),
                      key=lambda c: c.outcome is not Outcome.MISMATCH)

    def accuracy_claim(self) -> str:
        """Refuses, in words, and names what would be needed instead."""
        return (
            "No accuracy claim is made. The comparator is a Company Secretary's "
            "certification, which is a professional opinion and not adjudicated truth; "
            "agreement with it is therefore agreement, not correctness. An accuracy "
            "figure would require a gold set built to the two-annotator, adjudicated "
            "standard in checker/annotation.py. Until then this scorecard reports where "
            "the engine and a professional differ, and who must look at each.")

    def render(self) -> str:
        rate = self.agreement_rate
        head = (f"BACKTEST — {self.company}, FY {self.financial_year}\n"
                f"  comparable rows : {self.comparable}\n"
                f"  agreement       : "
                + ("n/a (nothing comparable)" if rate is None
                   else f"{self._count(Outcome.AGREE)}/{self.comparable} = {rate:.2f}")
                + f"\n  engine abstained: {self._count(Outcome.ENGINE_ABSTAINED)}"
                  f"\n  not certified   : {self._count(Outcome.NOT_CERTIFIED)}\n")
        lines = [head, "  REVIEW QUEUE (a human decides each):"]
        for c in self.review_queue():
            lines.append(f"    {c.outcome.value:17} {c.obligation_id}")
            lines.append(f"      engine: {c.engine_state}")
            if c.certified:
                lines.append(f"      filing: complied={c.certified.complied} "
                             f"@ {c.certified.locator}")
            lines.append(f"      causes: {', '.join(x.value for x in c.candidate_causes)}")
        if not self.review_queue():
            lines.append("    (none)")
        lines.append("\n  " + self.accuracy_claim())
        return "\n".join(lines)


def run(engine_rows: list, certifications: list[Certified],
        company: str, financial_year: str) -> Scorecard:
    """`engine_rows` are obligation rows (anything with obligation_id/state/basis)."""
    by_id = {c.obligation_id: c for c in certifications}
    card = Scorecard(company, financial_year)
    for row in engine_rows:
        card.comparisons.append(compare(
            row.obligation_id,
            row.state if isinstance(row.state, str) else str(row.state),
            getattr(row, "basis", ""),
            by_id.get(row.obligation_id)))
    return card


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    @dataclass
    class Row:
        obligation_id: str
        state: str
        basis: str = ""

    L = "MR-3 p.2 para 4"

    # locator is mandatory
    try:
        Certified("X", True, "  "); check(False, "blank locator should raise")
    except ValueError as e:
        check("locator" in str(e), "a certified assertion without a locator is refused")

    # agreement
    c = compare("A", "APPLIES_SATISFIED", "", Certified("A", True, L))
    check(c.outcome is Outcome.AGREE, "engine satisfied + certified complied = AGREE")
    check(not c.needs_review, "...and needs no review")

    c2 = compare("B", "APPLIES_NOT_SATISFIED", "", Certified("B", False, L))
    check(c2.outcome is Outcome.AGREE, "engine not-satisfied + certified not-complied = AGREE")

    # mismatch is NOT scored as an engine error
    m = compare("C", "APPLIES_NOT_SATISFIED", "", Certified("C", True, L))
    check(m.outcome is Outcome.MISMATCH, "disagreement is a MISMATCH")
    check(Cause.SOURCE_FINDING in m.candidate_causes,
          "...and the certification being wrong is an explicit candidate cause")
    check(Cause.ENGINE_DEFECT in m.candidate_causes, "...as is our own defect")
    check("NOT scored as an engine error" in m.note,
          "...and the note refuses to pre-judge which")

    # abstention is its own outcome
    a = compare("D", "CANNOT_DETERMINE", "", Certified("D", True, L))
    check(a.outcome is Outcome.ENGINE_ABSTAINED,
          "engine abstaining where a CS certified is its own outcome, not a mismatch")
    check(Cause.UNDERSPECIFIED in a.candidate_causes,
          "...and 'the filing lacked the facts' is a candidate cause")
    check(a.needs_review, "...and it still needs review")

    # nothing invented where the filing is silent
    n = compare("E", "APPLIES_SATISFIED", "", None)
    check(n.outcome is Outcome.NOT_CERTIFIED, "silence in the filing is NOT_CERTIFIED")
    check(not n.needs_review, "...and does not enter the review queue")

    # equivocal certification is not a comparator
    eq = compare("F", "APPLIES_SATISFIED", "", Certified("F", None, L))
    check(eq.outcome is Outcome.NOT_CERTIFIED, "an equivocal filing is not a comparator")

    # scorecard
    rows = [Row("A", "APPLIES_SATISFIED"), Row("C", "APPLIES_NOT_SATISFIED"),
            Row("D", "CANNOT_DETERMINE"), Row("E", "APPLIES_SATISFIED")]
    certs = [Certified("A", True, L), Certified("C", True, L), Certified("D", True, L)]
    card = run(rows, certs, "Example Ltd", "2024-25")
    check(card.comparable == 2, "only AGREE+MISMATCH rows are comparable")
    check(abs(card.agreement_rate - 0.5) < 1e-9, "agreement rate is 1/2")
    check(card.review_queue()[0].outcome is Outcome.MISMATCH,
          "mismatches sort ahead of abstentions in the review queue")
    check(len(card.review_queue()) == 2, "both the mismatch and the abstention queue up")

    claim = card.accuracy_claim()
    check("No accuracy claim" in claim, "the scorecard refuses to claim accuracy")
    check("annotation.py" in claim, "...and names the gold-set standard that would be needed")
    check("agreement, not correctness" in claim,
          "...and states why agreement is not correctness")

    empty = run([Row("Z", "APPLIES_SATISFIED")], [], "Nil Ltd", "2024-25")
    check(empty.agreement_rate is None, "no comparable rows yields None, never 0.0 or 1.0")

    check("BACKTEST" in card.render() and "REVIEW QUEUE" in card.render(),
          "render produces a human-readable scorecard")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
