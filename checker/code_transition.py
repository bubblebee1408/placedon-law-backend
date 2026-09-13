"""Which code governs — and why a flat `ipc_bns_map` table is the wrong shape.

The adoption plan (docs/PLAN_10_ADOPTION_REVIEW.md) proposes a `data/ipc_bns_map/`
table so that "new-code queries also reach old-code precedent". The retrieval goal is
right. The data structure is not, and the failure it produces is the exact one this
repository exists to prevent, running backwards.

## The defect

A lookup table says `IPC 302 -> BNS 103`. Ask it about a killing in 2023 and it hands
you BNS 103. But the Bharatiya Nyaya Sanhita came into force on 1 July 2024, and an
offence committed before that date is prosecuted under the Indian Penal Code. Serving
BNS 103 for a 2023 offence is serving law that did not exist when the act was done —
`prescribed_thresholds` had the same bug in the other direction, serving Rs 4 crore
after G.S.R. 880(E) had moved it, and that bug is what started this whole discipline.

So the mapping is not a table. It is a **dated supersession with a savings rule**, and
the anchor is the date of the *event*, not the date of the query.

## Substance and procedure do not share an anchor

This is the part a table cannot express at all:

    BNS   (substantive offences)  anchored on the DATE OF THE OFFENCE
    BNSS  (procedure)             anchored on the DATE PROCEEDINGS COMMENCED

A 2023 offence charged in 2025 is an IPC offence tried under BNSS procedure. One
document, two codes, two different anchors. A single map keyed on section number
cannot produce that answer, and a research tool that gets it wrong is wrong in the
way that a litigator notices immediately.

## Nothing here is served as law, because none of it is held

`scope.py` holds one body: the Companies Act 2013. IPC, BNS, BNSS, BSA, the General
Clauses Act and the Constitution are **all unheld**, so every verdict this module
returns is `INSTRUMENT_NOT_HELD`. The date arithmetic is real and tested; the legal
anchors are DECLARED, carrying the provision that would settle them and a note that
we have not read it. That is the same active refusal `scope.py` makes — the answer
names the body, what it covers, and what we would have to acquire. Never silence,
because silence reads as "no issue found".

Run: python3 checker/code_transition.py
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field
from datetime import date

# ── what the answer is anchored on ───────────────────────────────────────────
OFFENCE_DATE = "OFFENCE_DATE"          # substantive liability
PROCEEDING_DATE = "PROCEEDING_DATE"    # procedure and, generally, evidence
ANCHORS = (OFFENCE_DATE, PROCEEDING_DATE)

# ── verdicts ─────────────────────────────────────────────────────────────────
OLD_CODE = "OLD_CODE"
NEW_CODE = "NEW_CODE"
ANCHOR_DATE_MISSING = "ANCHOR_DATE_MISSING"    # we were not told the deciding date
STRADDLES = "STRADDLES"                        # a continuing act spanning the change
INSTRUMENT_NOT_HELD = "INSTRUMENT_NOT_HELD"    # the honest state of every row today

# Confidence in the ANCHOR (not in the arithmetic). Declared until read.
DECLARED = "DECLARED"        # stated from the provision named, which we have not read
HELD = "HELD"                # the provision is in the corpus and was read


@dataclass(frozen=True)
class Transition:
    """One old code superseded by one new code, and what decides which applies."""
    old: str
    new: str
    in_force: date               # the new code's commencement
    anchor: str
    basis: tuple[str, ...]       # the provisions that decide the anchor
    anchor_confidence: str = DECLARED
    old_held: bool = False
    new_held: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        if self.anchor not in ANCHORS:
            raise ValueError(f"unknown anchor {self.anchor!r}")
        if not self.basis:
            raise ValueError(
                f"{self.old} -> {self.new}: an anchor without a provision behind it "
                f"is an assertion. Name what decides it.")


@dataclass(frozen=True)
class Verdict:
    transition: Transition
    verdict: str
    code: str | None = None
    anchor_used: str | None = None
    anchor_date: date | None = None
    reason: str = ""
    acquire: tuple[str, ...] = _field(default_factory=tuple)

    @property
    def servable(self) -> bool:
        """May this be shown to a lawyer as an answer about the law?

        Never, today. Both codes are unheld, and a verdict about which unread code
        applies is a verdict about nothing.
        """
        return self.verdict in (OLD_CODE, NEW_CODE)


# ── the register. Every row unheld, and that is the point ────────────────────
#
# Commencement dates are the one fact here that is not in dispute and not
# jurisdiction-specific: the three new criminal codes replaced their predecessors
# on 1 July 2024. The ANCHORS are the contested part, and each names what settles
# it rather than asserting it.

_JULY_2024 = date(2024, 7, 1)

TRANSITIONS: tuple[Transition, ...] = (
    Transition(
        "Indian Penal Code, 1860", "Bharatiya Nyaya Sanhita, 2023", _JULY_2024,
        OFFENCE_DATE,
        basis=("Constitution of India, Article 20(1) — no conviction except for "
               "violation of a law in force at the time of the act",
               "General Clauses Act, 1897, s.6 — effect of repeal on liabilities "
               "already incurred",
               "Bharatiya Nyaya Sanhita, 2023 — repeal and savings"),
        note="substantive liability attaches at the act, so the code in force then "
             "governs; this is the strongest of the three anchors and it is "
             "constitutional, not merely a savings clause"),
    Transition(
        "Code of Criminal Procedure, 1973", "Bharatiya Nagarik Suraksha Sanhita, 2023",
        _JULY_2024, PROCEEDING_DATE,
        basis=("Bharatiya Nagarik Suraksha Sanhita, 2023 — repeal and savings for "
               "pending proceedings",
               "General Clauses Act, 1897, s.6"),
        note="procedure generally applies to proceedings from the date they are "
             "taken, so an old offence charged later is tried under the new "
             "procedure — a different anchor from the same commencement date"),
    Transition(
        "Indian Evidence Act, 1872", "Bharatiya Sakshya Adhiniyam, 2023", _JULY_2024,
        PROCEEDING_DATE,
        basis=("Bharatiya Sakshya Adhiniyam, 2023 — repeal and savings",),
        note="evidence is usually treated as procedural, but the classification is "
             "contested at the margins and we have read none of it; this anchor is "
             "the least settled of the three"),
)


def transition_for(old_or_new: str) -> Transition | None:
    key = old_or_new.strip().lower()
    for t in TRANSITIONS:
        if key in t.old.lower() or key in t.new.lower():
            return t
    return None


def governing_code(t: Transition, *, offence_date: date | None = None,
                   proceeding_date: date | None = None,
                   offence_ended: date | None = None) -> Verdict:
    """Which code governs, given the dates that actually decide it."""
    anchor_date = offence_date if t.anchor == OFFENCE_DATE else proceeding_date

    if anchor_date is None:
        wanted = "date of the offence" if t.anchor == OFFENCE_DATE \
            else "date proceedings commenced"
        return Verdict(t, ANCHOR_DATE_MISSING, anchor_used=t.anchor,
                       reason=f"{t.old} was replaced by {t.new} on "
                              f"{t.in_force.isoformat()}, and which applies turns on "
                              f"the {wanted}. That date was not given, and today's "
                              f"date is not a substitute for it.")

    # A continuing act that began under the old code and ran past commencement is not
    # settled by picking whichever date is convenient.
    if (t.anchor == OFFENCE_DATE and offence_ended is not None
            and offence_date is not None
            and offence_date < t.in_force <= offence_ended):
        return Verdict(t, STRADDLES, anchor_used=t.anchor, anchor_date=anchor_date,
                       reason=f"the conduct began {offence_date.isoformat()} and ran "
                              f"to {offence_ended.isoformat()}, spanning the "
                              f"{t.in_force.isoformat()} commencement. A continuing "
                              f"offence across a repeal is a question for a person, "
                              f"not a date comparison.",
                       acquire=tuple(t.basis))

    picked_new = anchor_date >= t.in_force
    code = t.new if picked_new else t.old
    held = t.new_held if picked_new else t.old_held

    if not held or t.anchor_confidence != HELD:
        missing = []
        if not held:
            missing.append(code)
        if t.anchor_confidence != HELD:
            missing.extend(t.basis)
        return Verdict(
            t, INSTRUMENT_NOT_HELD, code, t.anchor, anchor_date,
            reason=f"on the {t.anchor.lower().replace('_', ' ')} "
                   f"{anchor_date.isoformat()}, {code} would govern — the "
                   f"arithmetic against the {t.in_force.isoformat()} commencement is "
                   f"settled. What is not settled is the text: we hold neither the "
                   f"code nor the provision that fixes the anchor, so this names a "
                   f"body of law rather than answering from it.",
            acquire=tuple(missing))

    return Verdict(t, NEW_CODE if picked_new else OLD_CODE, code, t.anchor,
                   anchor_date, reason=f"{code} was in force on "
                                       f"{anchor_date.isoformat()}")


def both_codes(*, offence_date: date | None = None,
               proceeding_date: date | None = None) -> dict[str, Verdict]:
    """The answer a criminal matter actually needs: substance AND procedure.

    A 2023 offence charged in 2025 is an IPC offence under BNSS procedure. Any
    interface that shows one code per matter is showing half the answer.
    """
    return {t.old.split(",")[0]: governing_code(t, offence_date=offence_date,
                                                proceeding_date=proceeding_date)
            for t in TRANSITIONS}


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("code_transition")
    bns = transition_for("Bharatiya Nyaya Sanhita")
    bnss = transition_for("Bharatiya Nagarik Suraksha Sanhita")
    assert bns and bnss

    # ── the defect a lookup table has ────────────────────────────────────────
    v = governing_code(bns, offence_date=date(2023, 5, 12))
    check(v.code == "Indian Penal Code, 1860",
          f"a 2023 killing is an IPC matter, not BNS 103 — which is what a flat "
          f"map would return ({v.code})")
    check(governing_code(bns, offence_date=date(2024, 7, 1)).code
          == "Bharatiya Nyaya Sanhita, 2023",
          "commencement day itself falls on the new code (inclusive)")
    check(governing_code(bns, offence_date=date(2024, 6, 30)).code
          == "Indian Penal Code, 1860",
          "...and the day before does not")

    # ── the distinction a single map cannot express ──────────────────────────
    both = both_codes(offence_date=date(2023, 5, 12), proceeding_date=date(2025, 2, 1))
    check(both["Indian Penal Code"].code == "Indian Penal Code, 1860"
          and both["Code of Criminal Procedure"].code
          == "Bharatiya Nagarik Suraksha Sanhita, 2023",
          "one matter, two codes: a 2023 offence charged in 2025 is IPC substance "
          "under BNSS procedure")
    check(both["Indian Penal Code"].anchor_used == OFFENCE_DATE
          and both["Code of Criminal Procedure"].anchor_used == PROCEEDING_DATE,
          "...because the anchors differ, not because the dates do")

    # ── refusing rather than substituting today's date ───────────────────────
    v = governing_code(bns)
    check(v.verdict == ANCHOR_DATE_MISSING and v.code is None,
          "with no offence date it refuses rather than assuming today")
    check("today's date is not a substitute" in v.reason,
          "...and says why, because assuming today is the whole bug")
    v = governing_code(bnss, offence_date=date(2023, 5, 12))
    check(v.verdict == ANCHOR_DATE_MISSING,
          "an offence date does not answer a procedural question — BNSS needs the "
          "proceeding date and will not borrow the wrong one")

    # ── a continuing offence is not a date comparison ────────────────────────
    v = governing_code(bns, offence_date=date(2024, 3, 1),
                       offence_ended=date(2024, 9, 1))
    check(v.verdict == STRADDLES and not v.servable,
          "conduct spanning commencement is escalated, not resolved by rounding")
    check(governing_code(bns, offence_date=date(2024, 8, 1),
                         offence_ended=date(2024, 9, 1)).verdict != STRADDLES,
          "...and conduct wholly after commencement is not")

    # ── nothing is servable, because nothing is held ─────────────────────────
    for t in TRANSITIONS:
        r = governing_code(t, offence_date=date(2023, 1, 1),
                           proceeding_date=date(2023, 1, 1))
        check(r.verdict == INSTRUMENT_NOT_HELD and not r.servable,
              f"{t.new.split(',')[0]}: not servable — {len(r.acquire)} instrument(s) "
              f"to acquire")
        check(bool(r.acquire) and all(a for a in r.acquire),
              "...and the refusal names every one of them")

    # ── an anchor without a provision behind it cannot be declared ───────────
    try:
        Transition("A", "B", _JULY_2024, OFFENCE_DATE, basis=())
        check(False, "an anchor with no basis is rejected")
    except ValueError as e:
        check("an assertion" in str(e),
              "an anchor with no provision behind it is refused at construction")
    try:
        Transition("A", "B", _JULY_2024, "WHENEVER", basis=("x",))
        check(False, "an unknown anchor is rejected")
    except ValueError:
        check(True, "an unknown anchor is rejected at construction")

    # ── the arithmetic is real even while the law is not held ────────────────
    check(all(t.in_force == _JULY_2024 for t in TRANSITIONS),
          "all three codes share the 1 July 2024 commencement, and none of the "
          "three shares an answer")
    check(sum(1 for t in TRANSITIONS if t.anchor == PROCEEDING_DATE) == 2,
          "two of the three are procedural and anchored on the proceeding")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
