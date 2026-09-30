"""Which bodies of law a corporate EVENT engages, and what we can say about each.

PLAN_23. `checker/scope.py` is the authority on what we hold; `checker/model_cascade.py`
owns the arithmetic that turns a set of bodies into a status. This module owns one thing
only: the **fixed table** from an event to the bodies it engages, each entry with a written
reason.

## Why a table and not a model

A model asked "which laws does a share allotment engage?" answers fluently and is wrong
in a way nobody can audit. The engagement of a body is a fact about Indian corporate
practice, it changes rarely, and when it changes a person should edit a line here and be
seen to have done it. PLAN_23 §3: code decides the plan, the status, the authority and the
date.

## The rule this module exists to keep: silence is forbidden

Every body an event engages produces SOMETHING in the result. Never an omission.

    IN_CORPUS (HELD)  the obligation engine runs and returns its rows
    CURRENT_ONLY      the current text, LABELLED as having no point-in-time answer
    DECLARED          the named refusal from scope.py, via model_cascade.refusals_for

A body engaged and then left out of the output reads as "no obligation found", which is the
opposite of "we hold nothing here". That inversion is the entire reason `scope.py` has a
DECLARED state at all, and it would be undone by a single missing row.

## What this module may NOT say

**No statutory figure, deadline or section number for any body that is not HELD.** The
reasons below say WHY a body is engaged, never what it requires. "A foreign subscriber
brings the foreign-investment regime into play" is a fact about which regulator has an
interest; "file within 30 days" would be a legal claim resting on an instrument nobody has
acquired. A test scans this table for section, rule, regulation and figure forms and fails
on any of them.

Stamp duty is the sharpest case and is handled explicitly: rates vary across 25+ States and
Union Territories, so an answer with no State named is not a cautious answer, it is wrong by
construction. Engaged without a `state` fact, STAMP returns CLASSIFICATION UNCERTAINTY -- we
cannot even say which regime applies -- rather than a guess or a national average.

Run: PYTHONPATH=. python3 checker/events.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

from checker import model_cascade as mc
from checker import scope

# ── how a body was handled ───────────────────────────────────────────────────
DECIDED = "DECIDED"                  # HELD: the obligation engine ran
CURRENT_TEXT_ONLY = "CURRENT_TEXT_ONLY"   # CURRENT_ONLY: today's text, no history
REFUSED = "REFUSED"                  # DECLARED: the named refusal
UNCLASSIFIED = "UNCLASSIFIED"        # we cannot even say which regime applies
HANDLINGS = (DECIDED, CURRENT_TEXT_ONLY, REFUSED, UNCLASSIFIED)

# Facts an event may carry that add or remove a body.
FACTS = ("foreign_investor", "listed", "state")


class EventError(ValueError):
    """The table or the caller is wrong. Raised at import or at call, never recorded."""


@dataclass(frozen=True)
class Engagement:
    """One body an event engages, and why. The reason is for a reader, not a machine."""

    body_id: str
    reason: str

    def __post_init__(self) -> None:
        # The table is checked against the register at construction, so a renamed body
        # breaks at import rather than producing a silent gap at the first question.
        scope.body(self.body_id)
        if len(self.reason) < 25:
            raise EventError(
                f"{self.body_id} is engaged with no real reason. An entry a reader cannot "
                f"evaluate is one nobody can correct.")


@dataclass(frozen=True)
class Event:
    """One corporate event and the bodies it engages, before and after its facts."""

    key: str
    name: str
    always: tuple[Engagement, ...]
    # (fact, required_value) -> engagements added when the fact holds.
    when: tuple[tuple[str, object, tuple[Engagement, ...]], ...] = ()

    def __post_init__(self) -> None:
        for fact, _value, _adds in self.when:
            if fact not in FACTS:
                raise EventError(f"{fact!r} is not a declared event fact; one of {FACTS}")

    def engagements(self, facts: dict | None = None) -> tuple[Engagement, ...]:
        """Every body this event engages given these facts, in table order, deduplicated."""
        f = dict(facts or {})
        out: list[Engagement] = list(self.always)
        for fact, value, adds in self.when:
            if f.get(fact) == value:
                out.extend(adds)
        seen: dict[str, Engagement] = {}
        for e in out:
            seen.setdefault(e.body_id, e)
        return tuple(seen.values())


# ── the table ────────────────────────────────────────────────────────────────
# Eight events. Every reason says why the body has an INTEREST, never what it requires --
# see the module docstring on what may not be said here.

_CONTRACT = Engagement(
    "CONTRACT1872",
    "the transaction is an agreement, so formation, consideration and free consent are "
    "questions that can be asked about it")
_STAMP = Engagement(
    "STAMP",
    "an instrument is executed, and instrument stamping is a State subject that attaches "
    "to the document itself")

EVENTS: tuple[Event, ...] = (
    Event("share_allotment", "Allotment of shares",
          (Engagement("CA2013",
                      "allotment, the register of members and the return a company files "
                      "after it are Companies Act matters"),
           _STAMP),
          (("foreign_investor", True,
            (Engagement("FEMA1999",
                        "a non-resident subscriber brings the foreign-investment regime "
                        "into play, including its sectoral limits and its reporting"),)),
           ("listed", True,
            (Engagement("SEBI_OTHER",
                        "issue of capital by a listed entity is governed by SEBI's own "
                        "regulations in addition to the Act"),
             Engagement("SEBI_LODR",
                        "a listed entity's continuous-disclosure obligations attach to a "
                        "change in its capital"))))),

    Event("foreign_investment_received", "Foreign investment received",
          (Engagement("FEMA1999",
                      "receiving investment from a non-resident is the subject matter of "
                      "the foreign-exchange regime"),
           Engagement("CA2013",
                      "the company's own records, allotment and filings remain Companies "
                      "Act matters whoever the investor is"),
           _STAMP),
          (("listed", True,
            (Engagement("SEBI_LODR",
                        "a listed entity discloses changes in its shareholding under its "
                        "continuous-disclosure obligations"),)),)),

    Event("director_appointment", "Appointment of a director",
          (Engagement("CA2013",
                      "appointment, qualification, consent and the filings that follow are "
                      "Companies Act matters"),),
          (("listed", True,
            (Engagement("SEBI_LODR",
                        "board composition of a listed entity is governed by the listing "
                        "regulations as well as the Act"),)),)),

    Event("related_party_contract", "Contract with a related party",
          (Engagement("CA2013",
                      "related-party transactions are approved and recorded under the "
                      "Companies Act, and the engine decides those limbs it holds"),
           _CONTRACT, _STAMP),
          (("listed", True,
            (Engagement("SEBI_LODR",
                        "a listed entity's related-party approval and reporting run in "
                        "parallel with the Act's"),)),)),

    Event("borrowing_or_charge", "Borrowing, or creation of a charge",
          (Engagement("CA2013",
                      "borrowing powers and the registration of charges are Companies Act "
                      "matters"),
           _CONTRACT, _STAMP),
          (("foreign_investor", True,
            (Engagement("FEMA1999",
                        "borrowing from a non-resident lender engages the foreign-exchange "
                        "regime as well as the Act"),)),)),

    Event("insolvency_application", "Insolvency application",
          (Engagement("IBC2016",
                      "an insolvency application is made under, and decided by, the "
                      "insolvency regime"),
           Engagement("CA2013",
                      "the company's records and its directors' conduct remain Companies "
                      "Act matters alongside the insolvency process"),)),

    Event("listed_material_event", "Material event at a listed company",
          (Engagement("SEBI_LODR",
                      "what a listed entity must disclose, and when, is the subject matter "
                      "of the listing regulations"),
           Engagement("CA2013",
                      "the underlying corporate action is still governed by the Act"),)),

    Event("commercial_contract", "Execution of a commercial contract",
          (_CONTRACT, _STAMP,
           Engagement("ARBITRATION1996",
                      "a dispute-resolution clause appears in almost every commercial "
                      "contract, which brings the arbitration regime into scope"),)),
)

BY_KEY = {e.key: e for e in EVENTS}


def event(key: str) -> Event:
    if key not in BY_KEY:
        raise EventError(f"{key!r} is not a declared event; one of {sorted(BY_KEY)}")
    return BY_KEY[key]


# ── what we can say about one engaged body ───────────────────────────────────

@dataclass(frozen=True)
class BodyFinding:
    """What this engine can say about ONE body an event engaged. Never empty."""

    body_id: str
    body_status: str
    handling: str
    reason: str                       # why the body was engaged, from the table
    text: str                         # what we can say. Never blank.
    rows: tuple = field(default_factory=tuple)   # obligation rows, HELD bodies only

    def __post_init__(self) -> None:
        if self.handling not in HANDLINGS:
            raise EventError(f"{self.handling!r} is not a declared handling")
        # THE invariant of this module, enforced where it cannot be forgotten.
        if not self.text.strip():
            raise EventError(
                f"{self.body_id} was engaged and has nothing to say. Silence about an "
                f"engaged body reads as 'no obligation found', which is the opposite of "
                f"what a DECLARED body means.")
        if self.rows and self.body_status != scope.IN_CORPUS:
            raise EventError(
                f"{self.body_id} is {self.body_status} and carries obligation rows. No "
                f"obligation may be decided against a body that is not held.")

    def to_dict(self) -> dict:
        return {"body_id": self.body_id, "body_status": self.body_status,
                "handling": self.handling, "reason": self.reason, "text": self.text,
                "row_count": len(self.rows)}


@dataclass(frozen=True)
class EventResult:
    event_key: str
    status: str                       # from model_cascade.answer_status — never recomputed
    findings: tuple[BodyFinding, ...]
    facts: dict = field(default_factory=dict)

    @property
    def body_ids(self) -> tuple[str, ...]:
        return tuple(f.body_id for f in self.findings)

    @property
    def refusals(self) -> tuple[BodyFinding, ...]:
        return tuple(f for f in self.findings if f.handling == REFUSED)

    @property
    def unclassified(self) -> tuple[BodyFinding, ...]:
        return tuple(f for f in self.findings if f.handling == UNCLASSIFIED)

    def to_dict(self) -> dict:
        return {"event": self.event_key, "status": self.status,
                "facts": dict(self.facts), "body_ids": list(self.body_ids),
                "findings": [f.to_dict() for f in self.findings]}


def bodies_for_event(event_key: str, facts: dict | None = None) -> tuple[str, ...]:
    """The production `bodies_for` that `checker/model_cascade.run` takes.

    Signature note: the cascade calls `bodies_for(claims)`, so a caller wires this in as
    `lambda claims: bodies_for_event(key, facts)` -- the event and its facts are known
    before the cascade runs, and the claims do not change which bodies the EVENT engaged.

    **Claim-level attribution is still the caller's responsibility.** This returns the
    bodies the EVENT engages, which is a fact about the transaction. It does NOT say which
    body any individual sentence rests on. A caller that needs per-claim `body_id` -- and
    `model_cascade.Claim` has one -- must set it from the evidence that claim was traced to,
    not from this tuple. Using this as a per-claim attribution would label every sentence
    with every body the event touched, which would make the weakest body contaminate claims
    that never rested on it.
    """
    return tuple(e.body_id for e in event(event_key).engagements(facts))


def assess(event_key: str, facts: dict | None = None, *,
           profile=None, evidence=None, register=None) -> EventResult:
    """Every body this event engages, each with something said about it.

    `profile` is a `checker.company_profile.CompanyProfile`. Without one the held body is
    still reported -- as engaged, with the obligation engine not run and said so -- because
    dropping it would be the silence this module forbids.
    """
    ev = event(event_key)
    f = dict(facts or {})
    findings: list[BodyFinding] = []

    for eng in ev.engagements(f):
        b = scope.body(eng.body_id)

        if b.status == scope.IN_CORPUS:
            findings.append(_held(eng, b, profile, evidence, register))
        elif b.status == scope.CURRENT_ONLY:
            findings.append(BodyFinding(
                eng.body_id, b.status, CURRENT_TEXT_ONLY, eng.reason,
                text=(f"{b.name} is engaged and its CURRENT text is held. This answers what "
                      f"the position is now and NOTHING about any earlier date: the text "
                      f"held is the regulator's own consolidation, which is one snapshot. A "
                      f"dated question about this body is refused until the discrete "
                      f"amending notifications are acquired.")))
        elif eng.body_id == "STAMP" and not f.get("state"):
            # Not a refusal and not an answer: we cannot say WHICH regime applies.
            findings.append(BodyFinding(
                eng.body_id, b.status, UNCLASSIFIED, eng.reason,
                text=("Stamp duty is engaged and no State was given, so this cannot even be "
                      "classified: stamping is a State subject and the applicable regime "
                      "depends on where the instrument is executed. A single national answer "
                      "would be wrong by construction, not merely imprecise. Supply the "
                      "State and this becomes a named refusal for that State's regime, "
                      "which is a different and more useful thing than a guess.")))
        else:
            named = dict(mc.refusals_for([eng.body_id]))
            findings.append(BodyFinding(
                eng.body_id, b.status, REFUSED, eng.reason, text=named[eng.body_id]))

    # The status arithmetic is model_cascade's. Reimplementing it here would be a second
    # opinion about what PARTIAL means, and two would drift.
    status = mc.answer_status([x.body_id for x in findings])
    return EventResult(ev.key, status, tuple(findings), f)


def _held(eng: Engagement, b, profile, evidence, register) -> BodyFinding:
    """A held body: run the obligation engine, or say why it did not run."""
    if profile is None:
        return BodyFinding(
            eng.body_id, b.status, DECIDED, eng.reason,
            text=(f"{b.name} is held and this event engages it, but no company profile was "
                  f"supplied, so no obligation was decided. That is a missing input, not a "
                  f"finding that nothing applies."))
    from checker import obligations
    rows = obligations.build(profile, register or obligations.REGISTER, evidence)
    attention = [r for r in rows if r.needs_attention]
    return BodyFinding(
        eng.body_id, b.status, DECIDED, eng.reason,
        text=(f"{b.name} is held. The obligation engine decided {len(rows)} row(s) for this "
              f"company, {len(attention)} of which need attention."),
        rows=tuple(rows))


# ── self-test ────────────────────────────────────────────────────────────────

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

    import re
    from datetime import date

    from checker.company_profile import CompanyProfile

    # CompanyClass is a Literal, not an enum: the value IS the string.
    PROFILE = CompanyProfile(company_class="private",
                             incorporation_date=date(2020, 4, 1),
                             as_of=date(2026, 9, 30))

    # ── every body_id in the table exists in scope.py ───────────────────────
    ids = sorted({e.body_id for ev in EVENTS for e in ev.engagements()}
                 | {e.body_id for ev in EVENTS for _f, _v, adds in ev.when for e in adds})
    unknown = [i for i in ids if i not in {b.key for b in scope.BODIES}]
    check(not unknown, f"every body_id in the table exists in scope.py {unknown}")
    check(len(EVENTS) == 8, f"the eight declared events are present ({len(EVENTS)})")
    check(len(BY_KEY) == len(EVENTS), "...each declared once")

    # ── silence is forbidden ────────────────────────────────────────────────
    combos = [{}, {"listed": True}, {"foreign_investor": True},
              {"state": "Maharashtra"},
              {"listed": True, "foreign_investor": True, "state": "Karnataka"}]
    empty = []
    for ev in EVENTS:
        for f in combos:
            res = assess(ev.key, f, profile=PROFILE)
            engaged = set(bodies_for_event(ev.key, f))
            reported = {x.body_id for x in res.findings}
            if engaged != reported:
                empty.append((ev.key, sorted(engaged - reported)))
            for x in res.findings:
                if not x.text.strip():
                    empty.append((ev.key, x.body_id))
    check(not empty,
          f"NO event leaves an engaged body out of its result, under any fact combination "
          f"{empty[:3]}")
    check(all(assess(ev.key, {}, profile=PROFILE).findings for ev in EVENTS),
          "...and no event returns an empty result at all")

    # ── the scope invariant ─────────────────────────────────────────────────
    offenders = []
    for ev in EVENTS:
        for f in combos:
            for x in assess(ev.key, f, profile=PROFILE).findings:
                if x.rows and scope.body(x.body_id).status != scope.IN_CORPUS:
                    offenders.append((ev.key, x.body_id))
                if x.handling == DECIDED and not scope.body(x.body_id).answerable:
                    offenders.append((ev.key, x.body_id))
    check(not offenders,
          f"no obligation is decided against an unheld body {offenders[:3]}")
    check(all(x.handling in (REFUSED, UNCLASSIFIED, CURRENT_TEXT_ONLY)
              for ev in EVENTS for f in combos
              for x in assess(ev.key, f, profile=PROFILE).findings
              if not scope.body(x.body_id).answerable),
          "...every unheld body is refused, unclassified or current-text-only — never "
          "decided")

    # ── stamp duty with no State: uncertainty, not a guess ──────────────────
    no_state = assess("commercial_contract", {}, profile=PROFILE)
    stamp = next(x for x in no_state.findings if x.body_id == "STAMP")
    check(stamp.handling == UNCLASSIFIED,
          f"stamp duty with no State is CLASSIFICATION UNCERTAINTY ({stamp.handling})")
    check("wrong by construction" in stamp.text and "State" in stamp.text,
          "...saying a national answer would be wrong by construction, not merely "
          "imprecise")
    check(not re.search(r"\d+\s*%|\bRs\b|₹|\bper cent\b", stamp.text),
          f"...and quoting NO rate, because there is no national rate to quote")
    with_state = assess("commercial_contract", {"state": "Maharashtra"}, profile=PROFILE)
    stamp2 = next(x for x in with_state.findings if x.body_id == "STAMP")
    check(stamp2.handling == REFUSED,
          f"...while a named State turns it into a named refusal ({stamp2.handling}), "
          f"which is more useful than a guess and still not an answer")

    # ── share allotment with a foreign investor ─────────────────────────────
    fi = assess("share_allotment", {"foreign_investor": True}, profile=PROFILE)
    check("FEMA1999" in fi.body_ids,
          f"share allotment with foreign_investor=True engages FEMA1999 {fi.body_ids}")
    check(fi.status == mc.PARTIAL, f"...and the result is PARTIAL ({fi.status})")
    fema = next(x for x in fi.findings if x.body_id == "FEMA1999")
    check(fema.handling == REFUSED and "Foreign Exchange Management Act" in fema.text,
          "...carrying FEMA's named refusal, never omitting it")
    check("acquire" in fema.text.lower(),
          "...which says what would have to be acquired")
    plain = assess("share_allotment", {}, profile=PROFILE)
    check("FEMA1999" not in plain.body_ids,
          f"...while a domestic allotment does not engage it {plain.body_ids}")

    # ── status comes from model_cascade, not from here ──────────────────────
    for ev in EVENTS:
        for f in combos:
            res = assess(ev.key, f, profile=PROFILE)
            check_status = mc.answer_status(list(res.body_ids))
            if res.status != check_status:
                check(False, f"{ev.key} status disagrees with model_cascade")
                break
    else:
        check(True, "every event's status is model_cascade.answer_status of its bodies, "
                    "never a second opinion about what PARTIAL means")
    check(assess("director_appointment", {}, profile=PROFILE).status == mc.ANSWERED,
          "an event engaging only the held body is ANSWERED")
    check(assess("listed_material_event", {}, profile=PROFILE).status == mc.PARTIAL,
          "...and one reaching the current-only body is PARTIAL")

    # ── NO statutory figure, deadline or section for a non-HELD body ────────
    # Scanned on THIS table's reasons and on the text this module writes. scope.py's own
    # refusal prose is excluded: it is the authority's description of its own coverage,
    # and rewriting it here would be this module overruling the register.
    forbidden = re.compile(
        r"\b(section\s*\d|s\.\s*\d|rule\s*\d|regulation\s*\d|clause\s*\d+\(|"
        r"within\s+\d+\s+(day|month|year)|\d+\s*%|₹|\bRs\b|\d{1,2}\s*(days|months))",
        re.I)
    bad = []
    for ev in EVENTS:
        for eng in ev.engagements({"listed": True, "foreign_investor": True}):
            if scope.body(eng.body_id).status != scope.IN_CORPUS \
                    and forbidden.search(eng.reason):
                bad.append((ev.key, eng.body_id, eng.reason[:50]))
    check(not bad, f"no reason for a non-HELD body states a figure, deadline or section "
                   f"{bad[:2]}")
    written = []
    for ev in EVENTS:
        for f in combos:
            for x in assess(ev.key, f, profile=PROFILE).findings:
                if x.handling in (UNCLASSIFIED, CURRENT_TEXT_ONLY) \
                        and forbidden.search(x.text):
                    written.append((x.body_id, x.text[:50]))
    check(not written,
          f"...nor does any text this module writes for one {written[:2]}")
    # The scanner must be able to fire, or it proves nothing.
    check(forbidden.search("file within 30 days") and forbidden.search("section 42")
          and forbidden.search("0.1% of the value"),
          "...and the scanner catches a deadline, a section and a rate when one is present")

    # ── bodies_for_event, the cascade's production hook ─────────────────────
    check(bodies_for_event("insolvency_application") == ("IBC2016", "CA2013"),
          f"bodies_for_event returns the engaged bodies in table order "
          f"({bodies_for_event('insolvency_application')})")
    check(set(bodies_for_event("share_allotment", {"listed": True}))
          >= {"CA2013", "SEBI_OTHER", "SEBI_LODR"},
          "...and facts add bodies")
    check("claim-level attribution is still the caller" in
          (bodies_for_event.__doc__ or "").lower().replace("**", ""),
          "...and its docstring says claim-level attribution remains the caller's")
    from checker.model_cascade import run as cascade_run
    r = cascade_run("q", stages=[mc.Stage(mc.SMALL, lambda _p: "x", model="m")],
                    verify=lambda _raw: (True, "", ()),
                    bodies_for=lambda _claims: bodies_for_event("share_allotment",
                                                                {"foreign_investor": True}))
    check(r.status == mc.PARTIAL and dict(r.refusals).get("FEMA1999"),
          f"...and it drops into model_cascade.run unchanged, giving PARTIAL with FEMA's "
          f"refusal ({r.status})")

    # ── the held body runs the real obligation engine ───────────────────────
    held = next(x for x in plain.findings if x.body_id == "CA2013")
    check(held.handling == DECIDED and held.rows,
          f"the held body runs the obligation engine ({len(held.rows)} rows)")
    no_profile = next(x for x in assess("share_allotment", {}).findings
                      if x.body_id == "CA2013")
    check(no_profile.rows == () and "missing input" in no_profile.text,
          "...and with no profile it is reported as a MISSING INPUT, not as a finding that "
          "nothing applies")

    # ── shapes that must not be constructible ───────────────────────────────
    for bad_call, why in (
        (lambda: BodyFinding("CA2013", scope.IN_CORPUS, DECIDED, "r" * 30, ""),
         "an engaged body with nothing to say"),
        (lambda: BodyFinding("FEMA1999", scope.DECLARED, REFUSED, "r" * 30, "t",
                             rows=(1,)),
         "obligation rows against an unheld body"),
        (lambda: BodyFinding("CA2013", scope.IN_CORPUS, "GUESSED", "r" * 30, "t"),
         "an undeclared handling"),
        (lambda: Engagement("CA2013", "short"), "an engagement with no real reason"),
        (lambda: Engagement("NOT_A_BODY", "a reason long enough to pass the length check"),
         "a body that is not in the register"),
        (lambda: event("no_such_event"), "an undeclared event"),
        (lambda: Event("x", "X", (), (("colour", True, ()),)), "an undeclared fact"),
    ):
        try:
            bad_call()
            check(False, f"{why} is refused")
        except (EventError, LookupError):
            check(True, f"refused at construction: {why}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
