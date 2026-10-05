#!/usr/bin/env python3
"""Is this document still good? A status decided by CODE, from dates and held law.

T3, move 9. `document.verify` answers "was this signed, and by whom" (move 8). This answers
a different question that a lawyer asks in the same breath and that no signature can settle:
**is it still in force?** A perfectly signed, unaltered certificate that expired in 2023 is
genuine and useless.

Six statuses, and no seventh:

    CURRENT          in force at `as_of`, and no rule gives it an end date
    EXPIRES_ON       in force at `as_of`, and ends on a date we DERIVED and can show
    EXPIRED          that derived end date is in the past
    SUPERSEDED       a later instrument of the same kind replaced it -- SUPPLIED, never guessed
    REVOKED          withdrawn on a date -- SUPPLIED, never guessed
    NOT_DETERMINED   we cannot say, and the reason is named

## NOT_DETERMINED is the common answer, and that is the design

A status is a legal position. This module will return NOT_DETERMINED for a document whose
date it cannot read, for a document class whose validity period nobody has told it, and -- the
rule that matters -- for any rule that rests on a body of law we do not HOLD.

That last one is why `checker/scope.py` is imported here. A validity period taken from, say,
the LLP Act 2008 would be a number this repository cannot show you the provision for. Scope's
own report says it: "DECLARED is an active refusal, not a weaker form of HELD". So a rule
citing unheld law does not fire at a reduced confidence; it does not fire, and the result
NAMES the body, so a reader knows what would have to be acquired for an answer to exist.

## Nothing is inferred about supersession or revocation

`superseded_by` and `revoked_on` are arguments. This module will never decide that a document
was replaced because a newer one exists in the vault: two board resolutions about different
things are not a supersession, and guessing one would retire a live authority. A caller that
knows has to say so.

## Why the expiry is DERIVED and not stored

`checker/derived_date.derive` requires the interval to appear verbatim in the cited provision
and refuses when it does not (`IntervalNotInSource`). So an expiry here is always one a reader
can check against a quote, and `DerivedDate.working()` shows the arithmetic. A stored
`expires_on` would be a number whose origin nobody can see -- which is what makes a date
admissible or not.

Run: PYTHONPATH=. python3 checker/doc_validity.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from checker import document_date, scope

CURRENT = "CURRENT"
EXPIRES_ON = "EXPIRES_ON"
EXPIRED = "EXPIRED"
SUPERSEDED = "SUPERSEDED"
REVOKED = "REVOKED"
NOT_DETERMINED = "NOT_DETERMINED"

# Closed, and ordered as a reader meets them. A tuple so a new status is a visible edit here.
STATUSES = (CURRENT, EXPIRES_ON, EXPIRED, SUPERSEDED, REVOKED, NOT_DETERMINED)

# The statuses that assert the document is USABLE today. Named, because "not EXPIRED" is not
# the same as "in force": NOT_DETERMINED is neither, and a caller that treated it as the
# former would read "we could not tell" as "go ahead".
IN_FORCE = (CURRENT, EXPIRES_ON)


@dataclass(frozen=True)
class Rule:
    """How long a document of some class stays good, and the law that says so.

    `body` is a `checker/scope.py` key. `citation` and `quote` are the provision and its
    verbatim sentence; `derived_date.derive` checks the interval really appears in the quote,
    so a Rule cannot carry an interval its own source does not state.

    `unlimited=True` is a rule that says this class does not expire -- which is a finding, not
    an absence of one, and is what separates CURRENT from NOT_DETERMINED.
    """
    body: str
    citation: str
    quote: str
    unlimited: bool = False


@dataclass(frozen=True)
class Validity:
    status: str
    as_of: date
    document_date: date | None = None
    expires_on: date | None = None
    reason: str = ""
    # The body of law the rule rested on, and whether we hold it. `None` when no rule was
    # offered at all -- which is a different thing from a rule we could not use.
    body: str | None = None
    law_held: bool | None = None
    citation: str = ""
    working: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def in_force(self) -> bool:
        """Only CURRENT and EXPIRES_ON. NOT_DETERMINED is NOT in force and not expired."""
        return self.status in IN_FORCE

    def to_dict(self) -> dict:
        return {"status": self.status, "as_of": self.as_of.isoformat(),
                "document_date": (self.document_date.isoformat()
                                  if self.document_date else None),
                "expires_on": self.expires_on.isoformat() if self.expires_on else None,
                "in_force": self.in_force, "reason": self.reason,
                "body": self.body, "law_held": self.law_held,
                "citation": self.citation, "working": self.working}


def _held(body_key: str) -> bool:
    """Is this body of law HELD -- can an obligation be decided against it?

    `Body.answerable` is the question, not `status != OUT_OF_SCOPE`. CURRENT_ONLY holds a
    regulator's consolidation: authoritative for today and silent on every earlier date, and
    `scope.py` keeps the distinction because collapsing it is the retracted mistake in
    docs/evidence/RETRACTIONS.md. A validity period is arithmetic on a PAST date, so
    CURRENT_ONLY is not enough.
    """
    try:
        return scope.body(body_key).answerable
    except LookupError:
        return False


def decide(text: str, *, as_of: date, rule: Rule | None = None,
           superseded_by: str = "", revoked_on: date | None = None,
           document_date_override: date | None = None) -> Validity:
    """The status of one document at `as_of`. Never raises; refuses by naming a reason.

    Order matters and is deliberate. REVOKED and SUPERSEDED are decided FIRST, before any
    date arithmetic, because they are facts a caller supplied about the world: a revoked
    certificate is revoked whether or not we can read its date, and running the arithmetic
    first could return EXPIRES_ON for a document that was withdrawn last year.
    """
    detail: dict = {}

    if revoked_on is not None:
        if revoked_on <= as_of:
            return Validity(REVOKED, as_of, reason=(
                f"withdrawn on {revoked_on.isoformat()}, which is on or before the date "
                f"asked about. Decided before any date arithmetic: a revoked document is "
                f"revoked whether or not we can read the date it bears"),
                detail={"revoked_on": revoked_on.isoformat()})
        detail["revocation_pending"] = revoked_on.isoformat()

    if str(superseded_by or "").strip():
        return Validity(SUPERSEDED, as_of, reason=(
            f"replaced by {superseded_by.strip()}, as the caller stated. This module never "
            f"decides supersession for itself: two documents of one kind about different "
            f"things are not a supersession, and guessing one would retire a live authority"),
            detail={"superseded_by": superseded_by.strip()})

    reading = document_date.read(text or "")
    doc_date = document_date_override or reading.value
    if doc_date is None:
        return Validity(NOT_DETERMINED, as_of, reason=(
            f"the date this document bears could not be established, so no validity period "
            f"can be measured from anything. {reading.why}"),
            detail={"conflicting": [d.isoformat() for d in reading.conflicting],
                    "unread_declarations": reading.unread, **detail})

    if rule is None:
        return Validity(NOT_DETERMINED, as_of, document_date=doc_date, reason=(
            "this document bears a date and no rule was given for how long a document of "
            "its class stays good. An unknown validity period is not an unlimited one"),
            detail=detail)

    held = _held(rule.body)
    if not held:
        try:
            body_name = scope.body(rule.body).name
        except LookupError:
            body_name = rule.body
        return Validity(NOT_DETERMINED, as_of, document_date=doc_date, body=rule.body,
                        law_held=False, citation=rule.citation, reason=(
            f"the validity period for this document rests on {body_name}, which this "
            f"deployment does not hold as decidable law. The rule does not fire at a lower "
            f"confidence -- it does not fire. Acquiring {body_name} is what would make an "
            f"answer exist"), detail=detail)

    if rule.unlimited:
        return Validity(CURRENT, as_of, document_date=doc_date, body=rule.body,
                        law_held=True, citation=rule.citation, reason=(
            f"in force: {rule.citation} gives documents of this class no end date, and that "
            f"is a finding rather than an absence of one"), detail=detail)

    from checker import derived_date
    try:
        dd = derived_date.derive(anchor=doc_date, anchor_label="the date the document bears",
                                 source_text=rule.quote, citation=rule.citation)
    except Exception as e:                                       # noqa: BLE001
        # `IntervalNotInSource` is the expected one: the provision quote states no interval,
        # so there is nothing to derive and nothing to show. Refused rather than guessed.
        return Validity(NOT_DETERMINED, as_of, document_date=doc_date, body=rule.body,
                        law_held=True, citation=rule.citation, reason=(
            f"no validity period could be derived from {rule.citation}: "
            f"{type(e).__name__}: {str(e)[:160]}"), detail=detail)

    expires = dd.result
    if expires < as_of:
        return Validity(EXPIRED, as_of, document_date=doc_date, expires_on=expires,
                        body=rule.body, law_held=True, citation=rule.citation,
                        working=dd.working(), reason=(
            f"the period ran out on {expires.isoformat()}, before the date asked about "
            f"({as_of.isoformat()}). The arithmetic is shown, from a quote of "
            f"{rule.citation}"), detail=detail)
    return Validity(EXPIRES_ON, as_of, document_date=doc_date, expires_on=expires,
                    body=rule.body, law_held=True, citation=rule.citation,
                    working=dd.working(), reason=(
        f"in force at {as_of.isoformat()} and ends on {expires.isoformat()}, derived from a "
        f"quote of {rule.citation} rather than stored as a bare number"), detail=detail)


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

    print("doc_validity")

    AS_OF = date(2026, 10, 5)
    DATED = "CERTIFICATE OF INCORPORATION\nDate: 14 March 2024\nAcme Private Limited\n"
    UNDATED = "CERTIFICATE\nIssued by the Registrar.\nNo date line appears here.\n"

    # The held body, read from scope rather than written here: a test that hardcoded
    # "COMPANIES2013" would pass after scope stopped holding it.
    HELD_KEY = scope.in_corpus()[0].key
    UNHELD = [b for b in scope.declared_unheld()]
    check(bool(UNHELD), f"scope declares at least one UNHELD body to test against "
                        f"({len(UNHELD)})")
    UNHELD_KEY = UNHELD[0].key

    SIX_MONTHS = Rule(HELD_KEY, "Companies Act 2013, s.96",
                      "not more than six months shall elapse from the date it bears.")
    FIFTEEN_MONTHS = Rule(HELD_KEY, "Companies Act 2013, s.96",
                          "not more than fifteen months shall elapse from the date it bears.")

    # ── an EXPIRED document never returns CURRENT (the done-when) ───────────
    v = decide(DATED, as_of=AS_OF, rule=SIX_MONTHS)
    check(v.status == EXPIRED,
          f"a document dated March 2024 with a six-month period is EXPIRED at Oct 2026 "
          f"({v.status})")
    check(v.status not in (CURRENT, EXPIRES_ON) and not v.in_force,
          f"...and is NOT in force, by either name ({v.status}, in_force={v.in_force})")
    check(v.expires_on == date(2024, 9, 14),
          f"...with the end date shown, not implied ({v.expires_on})")
    check("2024-03-14" in v.working and "six months" in v.working,
          f"...and the arithmetic is shown from the provision's own words, so a reader can "
          f"check it ({v.working.splitlines()[:1]})")

    # Every rule, every length: an expired document is never CURRENT. The done-when as a
    # sweep rather than one example, because one example proves one example.
    for months, label in ((1, "one"), (3, "three"), (6, "six"), (12, "twelve")):
        r = Rule(HELD_KEY, "Companies Act 2013, s.96",
                 f"not more than {label} months shall elapse from the date it bears.")
        got = decide(DATED, as_of=AS_OF, rule=r)
        check(got.status == EXPIRED,
              f"a {months}-month period on a 2024 document is EXPIRED, never CURRENT "
              f"({got.status})")

    # ── a document still in force ───────────────────────────────────────────
    recent = "RESOLUTION\nDate: 1 September 2026\n"
    v2 = decide(recent, as_of=AS_OF, rule=FIFTEEN_MONTHS)
    check(v2.status == EXPIRES_ON and v2.in_force,
          f"a recent document under a fifteen-month period is EXPIRES_ON and in force "
          f"({v2.status})")
    check(v2.expires_on == date(2027, 12, 1),
          f"...with the derived end date ({v2.expires_on})")

    # The boundary. Expiry ON the day asked about is still in force: a period that "runs
    # out on" a date has not run out before it.
    on_the_day = decide("X\nDate: 5 April 2026\n", as_of=AS_OF, rule=SIX_MONTHS)
    check(on_the_day.status == EXPIRES_ON and on_the_day.expires_on == AS_OF,
          f"a document whose period ends ON the date asked about is still in force -- a "
          f"period that ends on a day has not ended before it "
          f"({on_the_day.status}, {on_the_day.expires_on})")
    day_after = decide("X\nDate: 4 April 2026\n", as_of=AS_OF, rule=SIX_MONTHS)
    check(day_after.status == EXPIRED,
          f"...and one day earlier is EXPIRED, so the boundary is a real edge and not a "
          f"rounding ({day_after.status}, {day_after.expires_on})")

    # ── a missing date returns NOT_DETERMINED (the done-when) ───────────────
    nd = decide(UNDATED, as_of=AS_OF, rule=SIX_MONTHS)
    check(nd.status == NOT_DETERMINED,
          f"a document that declares no date is NOT_DETERMINED ({nd.status})")
    check(not nd.in_force and nd.status != EXPIRED,
          f"...and is NEITHER in force NOR expired: 'we could not tell' is not 'go ahead' "
          f"and not 'it has run out' (in_force={nd.in_force})")
    check("no line in this document declares" in nd.reason,
          f"...and the reason is `document_date`'s own, not one written here "
          f"({nd.reason[:80]}…)")

    conflicting = "X\nDate: 1 March 2024\nY\nDate: 7 July 2025\n"
    cd = decide(conflicting, as_of=AS_OF, rule=SIX_MONTHS)
    check(cd.status == NOT_DETERMINED and len(cd.detail["conflicting"]) == 2,
          f"a document declaring TWO dates is NOT_DETERMINED and both are reported -- "
          f"picking one would be choosing which document this is ({cd.detail})")

    # ── a rule resting on UNHELD law does not fire ──────────────────────────
    unheld_rule = Rule(UNHELD_KEY, "LLP Act 2008, s.11",
                       "not more than six months shall elapse from the date it bears.")
    uv = decide(DATED, as_of=AS_OF, rule=unheld_rule)
    check(uv.status == NOT_DETERMINED and uv.law_held is False,
          f"a rule resting on a body we do not hold gives NOT_DETERMINED ({uv.status}, "
          f"law_held={uv.law_held})")
    check(scope.body(UNHELD_KEY).name in uv.reason,
          f"...NAMING the body, so a reader knows what would have to be acquired "
          f"({uv.reason[:90]}…)")
    check("does not fire at a lower confidence" in uv.reason,
          "...and says the rule does not fire at a reduced confidence, which is scope's own "
          "position: DECLARED is an active refusal, not a weaker HELD")
    check(uv.expires_on is None,
          f"...and no end date is offered, because none was derivable ({uv.expires_on})")
    check(decide(DATED, as_of=AS_OF, rule=Rule("NO_SUCH_BODY", "x", "six months")
                 ).status == NOT_DETERMINED,
          "an unknown body key is NOT_DETERMINED too, rather than raising on a typo")

    # ── supplied facts beat arithmetic, and are never inferred ──────────────
    sup = decide(recent, as_of=AS_OF, rule=FIFTEEN_MONTHS, superseded_by="BR/2026/14")
    check(sup.status == SUPERSEDED and sup.detail["superseded_by"] == "BR/2026/14",
          f"a document the caller says was replaced is SUPERSEDED even though the "
          f"arithmetic says in force ({sup.status})")
    check("never decides supersession for itself" in sup.reason,
          "...and the reason says this module never infers it")
    rev = decide(recent, as_of=AS_OF, rule=FIFTEEN_MONTHS, revoked_on=date(2026, 6, 1))
    check(rev.status == REVOKED,
          f"a revoked document is REVOKED, not EXPIRES_ON ({rev.status})")
    rev_undated = decide(UNDATED, as_of=AS_OF, revoked_on=date(2026, 6, 1))
    check(rev_undated.status == REVOKED,
          f"...and a revoked document with NO readable date is still REVOKED: that fact "
          f"does not depend on reading the date ({rev_undated.status})")
    future_rev = decide(recent, as_of=AS_OF, rule=FIFTEEN_MONTHS,
                        revoked_on=date(2027, 1, 1))
    check(future_rev.status == EXPIRES_ON
          and future_rev.detail["revocation_pending"] == "2027-01-01",
          f"a revocation AFTER the date asked about does not retire the document, and is "
          f"reported as pending ({future_rev.status}, {future_rev.detail})")

    # ── an unlimited rule is CURRENT, and that needs a rule to say so ───────
    forever = Rule(HELD_KEY, "Companies Act 2013, s.7", "no period is stated.",
                   unlimited=True)
    cv = decide(DATED, as_of=AS_OF, rule=forever)
    check(cv.status == CURRENT and cv.expires_on is None,
          f"a class the law gives no end date is CURRENT ({cv.status})")
    check("a finding rather than an absence of one" in cv.reason,
          "...and says the no-expiry rule is a finding, which is what separates CURRENT "
          "from NOT_DETERMINED")
    check(decide(DATED, as_of=AS_OF, rule=None).status == NOT_DETERMINED,
          "...while NO rule at all is NOT_DETERMINED: an unknown validity period is not an "
          "unlimited one")

    # ── a quote that states no interval is refused, not guessed ─────────────
    silent = Rule(HELD_KEY, "Companies Act 2013, s.96",
                  "Every company shall hold an annual general meeting.")
    sv = decide(DATED, as_of=AS_OF, rule=silent)
    check(sv.status == NOT_DETERMINED and sv.law_held is True,
          f"a provision quote stating NO interval gives NOT_DETERMINED, even though the law "
          f"is held ({sv.status})")
    check("IntervalNotInSource" in sv.reason,
          f"...naming `derived_date`'s own refusal, which exists so an expiry is always one "
          f"a reader can check against a quote ({sv.reason[:70]}…)")

    # ── the vocabulary is closed, and `in_force` is not `not EXPIRED` ───────
    check(len(STATUSES) == 6 and len(set(STATUSES)) == 6,
          f"six statuses and no seventh ({STATUSES})")
    check(set(IN_FORCE) == {CURRENT, EXPIRES_ON},
          f"only two statuses assert the document is usable today ({IN_FORCE})")
    for st in (EXPIRED, SUPERSEDED, REVOKED, NOT_DETERMINED):
        check(st not in IN_FORCE, f"{st} is not in force")
    seen = {decide(t, as_of=AS_OF, rule=r, superseded_by=s, revoked_on=rv).status
            for t, r, s, rv in ((DATED, SIX_MONTHS, "", None),
                                (recent, FIFTEEN_MONTHS, "", None),
                                (DATED, forever, "", None),
                                (recent, FIFTEEN_MONTHS, "x", None),
                                (recent, FIFTEEN_MONTHS, "", date(2026, 1, 1)),
                                (UNDATED, SIX_MONTHS, "", None))}
    check(seen == set(STATUSES),
          f"every one of the six statuses is REACHABLE -- a status nothing can return is a "
          f"status that does not exist ({sorted(seen)})")

    # Every return carries a reason. A status with no reason is a verdict nobody can check.
    for t, r in ((DATED, SIX_MONTHS), (UNDATED, None), (DATED, unheld_rule),
                 (DATED, forever), (DATED, silent), (recent, FIFTEEN_MONTHS)):
        got = decide(t, as_of=AS_OF, rule=r)
        check(len(got.reason) > 40 and got.to_dict()["status"] in STATUSES,
              f"{got.status} carries a reason a reader can act on "
              f"({got.reason[:50]}…)")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_test() if "--test" in sys.argv or len(sys.argv) == 1 else 0)
