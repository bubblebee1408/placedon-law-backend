"""The Operation Model — turning an observation into work, never into an answer.

THEMIS V0 milestone 6 (master build plan §12, §85). The brain above the engine:
it does not decide anything, it decides **what must happen**.

## The one sentence that defines this module

A Gazette instrument appearing is **not** a finding that the law changed for a
company. It is a reason for someone to look. Everything here produces QUESTIONS
addressed to a specialist or a human; nothing here produces a legal conclusion,
and there is no field in which one could be recorded.

That is why an `Operation` has requirements and not results, why every
`Requirement` carries a `question` rather than a `finding`, and why the terminal
state of the graph is `HUMAN_REVIEW` rather than `DONE`.

## Where the work comes from — the register, not invention

The requirements are not authored here. Each obligation in
`checker/obligations.py` already declares `evidence_needed` -- the facts that
would settle it -- and `checker/currency.affected_by()` already answers "which
obligations does this instrument touch". Measured 2026-09-23:

    affected_by("880")        -> ['CA13-S2-85-SMALL']
    affected_by("G.S.R. 700") -> ['CA13-S2-85-SMALL']

So an instrument lands, the reverse index names the obligations, and each
obligation's own `evidence_needed` becomes the requirements. A requirement this
module invented would be a requirement no obligation asked for.

## Routing, and what happens when routing is unsure

Three specialist types, per §85: `LEGAL_RESEARCH`, `CORPORATE_DATA`,
`FINANCIAL_DATA`. Routing reads the evidence phrase and is frankly a keyword
heuristic -- `_ROUTING` below is the whole of it.

**An unroutable requirement goes to `HUMAN_REVIEW`, never to a guess.** A
misrouted requirement is work sent to someone who cannot do it, and it comes back
as silence rather than as an error. Failing to the human is the only safe default
for a heuristic that will meet phrasings nobody anticipated.

## The evidence budget is a count, not a score

`EvidenceBudget` reports how many requirements are satisfied, how many are
blocking, and which ones are unmet **by name**. It is deliberately not a
percentage or a confidence: L-15 and `checker/calibration_contract.py` govern
anything numeric that could be read as a measurement of the world, and "73%
ready" is exactly such a number. A count of named open questions composes,
orders, explains, and cannot be misread.

## Ring

Ring 2. It reads observations (Ring 2) and the obligation register and currency
index (Ring 0) -- downward and sideways, both permitted. No Ring 0 decider may
import it, which `checker/rings.py` enforces by test rather than by convention.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from checker.currency import acquisition_for, affected_by
from checker.obligations import REGISTER

__all__ = ["Requirement", "Operation", "EvidenceBudget", "Watchlist", "WatchedCompany",
           "operation_for_instrument", "operation_for_gazette_item", "instrument_in",
           "SPECIALISTS", "CRITICALITY", "STATUS"]

# §85: three specialist task types, plus the human, who is a first-class execution
# target and not a fallback queue.
LEGAL_RESEARCH = "LEGAL_RESEARCH"
CORPORATE_DATA = "CORPORATE_DATA"
FINANCIAL_DATA = "FINANCIAL_DATA"
HUMAN_REVIEW = "HUMAN_REVIEW"
SPECIALISTS = (LEGAL_RESEARCH, CORPORATE_DATA, FINANCIAL_DATA, HUMAN_REVIEW)

BLOCKING = "BLOCKING"      # the operation cannot be closed while this is open
IMPORTANT = "IMPORTANT"    # the answer is materially worse without it
CONTEXT = "CONTEXT"        # useful, not load-bearing
CRITICALITY = (BLOCKING, IMPORTANT, CONTEXT)

OPEN = "OPEN"
SATISFIED = "SATISFIED"
BLOCKED = "BLOCKED"        # cannot be satisfied: the source is not held or not permitted
STATUS = (OPEN, SATISFIED, BLOCKED)

# The routing heuristic, in full. Order matters: the first phrase that matches wins,
# so the more specific financial terms are tested before the generic corporate ones.
_ROUTING: tuple[tuple[tuple[str, ...], str], ...] = (
    (("paid-up", "paid up", "capital", "turnover", "net worth", "net profit",
      "free reserves", "securities premium", "borrowing", "loan", "investment",
      "financial statement"), FINANCIAL_DATA),
    (("director", "board meeting", "agm", "annual general meeting", "resolution",
      "shareholding", "member", "kmp", "auditor", "registered office", "charge",
      "annual return", "filed", "incorporat", "subsidiary", "holding company",
      "related party", "contract", "counterpart"), CORPORATE_DATA),
    (("rule", "notification", "instrument", "provision", "section", "threshold",
      "prescribed", "gazette", "amendment", "class of compan"), LEGAL_RESEARCH),
)


def _route(evidence_phrase: str) -> str:
    """Which specialist can answer this, or HUMAN_REVIEW when the phrasing is new."""
    text = evidence_phrase.casefold()
    for needles, specialist in _ROUTING:
        if any(n in text for n in needles):
            return specialist
    return HUMAN_REVIEW


def _rid(*parts: str) -> str:
    return "r_" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]


@dataclass(frozen=True)
class Requirement:
    """One question that must be answered before the operation can close.

    `question`, never `finding`: this type has no field in which a legal
    conclusion could be stored, which is the point.
    """

    requirement_id: str
    question: str
    obligation_id: str
    provision: str
    specialist: str
    criticality: str
    minimum_evidence: str            # the evidence state below which this cannot close
    depends_on: tuple[str, ...] = ()
    status: str = OPEN
    note: str = ""

    def __post_init__(self) -> None:
        if self.specialist not in SPECIALISTS:
            raise ValueError(f"{self.specialist!r} is not a specialist type; one of {SPECIALISTS}")
        if self.criticality not in CRITICALITY:
            raise ValueError(f"{self.criticality!r} is not a criticality; one of {CRITICALITY}")
        if self.status not in STATUS:
            raise ValueError(f"{self.status!r} is not a status; one of {STATUS}")
        if not self.question.strip():
            raise ValueError("a requirement with no question is not a requirement")


@dataclass(frozen=True)
class EvidenceBudget:
    """What is answered, what is open, and which open items block closing.

    A count with names, not a score. See the module docstring.
    """

    total: int
    satisfied: int
    blocking_open: tuple[str, ...]
    open_by_specialist: dict[str, int]

    @property
    def can_close(self) -> bool:
        return not self.blocking_open

    def sentence(self) -> str:
        if self.can_close:
            return f"{self.satisfied} of {self.total} requirements satisfied; nothing blocking."
        n = len(self.blocking_open)
        return (f"{self.satisfied} of {self.total} requirements satisfied; "
                f"{n} blocking requirement{'s' if n != 1 else ''} still open. "
                "This operation cannot be closed, and no conclusion may be drawn from it.")


@dataclass(frozen=True)
class Operation:
    """Work created by an observation. Carries no answer, by construction."""

    operation_id: str
    intent: str
    trigger: dict                       # the observation that caused this, verbatim
    requirements: tuple[Requirement, ...]
    created_at: str
    companies: tuple[str, ...] = ()     # CINs from the watchlist, if any
    what_this_is_not: str = (
        "An operation is work to be done, not a finding. The instrument that triggered it "
        "has not been read against any company's facts, and nothing here states that an "
        "obligation changed, applies, or was breached."
    )

    def budget(self) -> EvidenceBudget:
        by_spec: dict[str, int] = {}
        for r in self.requirements:
            if r.status != SATISFIED:
                by_spec[r.specialist] = by_spec.get(r.specialist, 0) + 1
        return EvidenceBudget(
            total=len(self.requirements),
            satisfied=sum(1 for r in self.requirements if r.status == SATISFIED),
            blocking_open=tuple(r.requirement_id for r in self.requirements
                                if r.criticality == BLOCKING and r.status != SATISFIED),
            open_by_specialist=by_spec,
        )

    def tasks_for(self, specialist: str) -> tuple[Requirement, ...]:
        if specialist not in SPECIALISTS:
            raise ValueError(f"{specialist!r} is not a specialist type")
        return tuple(r for r in self.requirements
                     if r.specialist == specialist and r.status != SATISFIED)

    def to_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "intent": self.intent,
            "trigger": self.trigger,
            "companies": list(self.companies),
            "created_at": self.created_at,
            "what_this_is_not": self.what_this_is_not,
            "budget": {
                "total": self.budget().total,
                "satisfied": self.budget().satisfied,
                "blocking_open": list(self.budget().blocking_open),
                "can_close": self.budget().can_close,
                "sentence": self.budget().sentence(),
            },
            "requirements": [dict(r.__dict__, depends_on=list(r.depends_on))
                             for r in self.requirements],
        }


@dataclass(frozen=True)
class WatchedCompany:
    """A company someone is watching, and the CIN that identifies it."""

    cin: str
    name: str = ""

    def __post_init__(self) -> None:
        if not self.cin.strip():
            raise ValueError("a watched company must carry a CIN -- an unnamed watch is not a watch")


@dataclass
class Watchlist:
    companies: list[WatchedCompany] = field(default_factory=list)

    def add(self, cin: str, name: str = "") -> None:
        if any(c.cin == cin for c in self.companies):
            return
        self.companies.append(WatchedCompany(cin=cin, name=name))

    def cins(self) -> tuple[str, ...]:
        return tuple(c.cin for c in self.companies)


def _deadline(days: int, *, now: date) -> str:
    return (now + timedelta(days=days)).isoformat()


def operation_for_instrument(instrument: str, *, trigger: dict,
                             watchlist: Watchlist | None = None,
                             now: datetime | None = None) -> Operation | None:
    """An instrument landed. What work does it create?

    Returns None when the reverse index names no obligation -- an instrument that
    touches nothing we hold creates no work, and inventing a requirement for it
    would be manufacturing the very signal this system exists to earn.

    `trigger` is the observation verbatim (a `GazetteItem.__dict__`, say). It is
    stored, not interpreted: the operation records what was seen, so a reviewer can
    disagree with the reason they were called.
    """
    obligation_ids = affected_by(instrument)
    if not obligation_ids:
        return None

    now = now or datetime.now(timezone.utc)
    today = now.date()
    by_id = {o.obligation_id: o for o in REGISTER}
    reqs: list[Requirement] = []

    # R0: has anyone actually read the instrument? Every other requirement below is
    # downstream of this one, because the reverse index matched a NAME, not a text.
    # `affected_by` matches an instrument string against declared thresholds; it does
    # not open the Gazette.
    #
    # PLAN_17 M1.3: this requirement used to be created UNCONDITIONALLY. G.S.R. 880(E)
    # was acquired, hashed and attested by a named reviewer on 2026-09-10, and every
    # operation raised on it still opened with a blocking demand to go and acquire it.
    # Work a person has already done, demanded again, is not caution -- it is a queue
    # nobody can ever empty, and it teaches a reviewer to close requirements without
    # reading them. Asked rather than assumed, through the same gate as everywhere else.
    read_id = _rid(instrument, "read")
    acq = acquisition_for(instrument)
    if acq is None or not acq.read:
        reqs.append(Requirement(
            requirement_id=read_id,
            question=(f"Acquire and attest {instrument}: does its text in fact change the "
                      "threshold the register attributes to it, and from what date?"),
            obligation_id="(instrument)",
            provision=instrument,
            specialist=LEGAL_RESEARCH,
            criticality=BLOCKING,
            minimum_evidence="the instrument acquired from the Gazette, hashed, and human-attested",
            note=("The reverse index matched this instrument by NAME against declared "
                  "thresholds. Nobody has read it yet."),
        ))

    for oid in obligation_ids:
        ob = by_id.get(oid)
        if ob is None:
            # The index named an obligation the register does not hold. Reported as a
            # requirement rather than skipped: a dangling id is a defect a person
            # should see, not a row to drop quietly.
            reqs.append(Requirement(
                requirement_id=_rid(instrument, oid, "dangling"),
                question=(f"The currency index names obligation {oid} as affected, but the "
                          "register does not contain it. Which is wrong?"),
                obligation_id=oid, provision="(unknown)", specialist=HUMAN_REVIEW,
                criticality=BLOCKING, minimum_evidence="a person reconciles index and register",
                depends_on=(read_id,)))
            continue

        for phrase in ob.evidence_needed:
            reqs.append(Requirement(
                requirement_id=_rid(instrument, oid, phrase),
                question=f"For {ob.obligation_id} ({ob.provision}): establish {phrase}.",
                obligation_id=ob.obligation_id,
                provision=ob.provision,
                specialist=_route(phrase),
                criticality=IMPORTANT,
                minimum_evidence="a dated fact from a named source, or a recorded refusal",
                depends_on=(read_id,),
            ))

    # The terminal requirement. A human decides; the engine does not close its own
    # operation. Depends on everything, so the graph has one sink.
    reqs.append(Requirement(
        requirement_id=_rid(instrument, "review"),
        question=("Review the assembled evidence and decide what, if anything, follows for "
                  "each watched company. This operation states nothing on its own."),
        obligation_id="(review)",
        provision=instrument,
        specialist=HUMAN_REVIEW,
        criticality=BLOCKING,
        minimum_evidence="a named reviewer records a decision and a reason",
        depends_on=tuple(r.requirement_id for r in reqs),
    ))

    cins = watchlist.cins() if watchlist else ()
    payload = json.dumps({"instrument": instrument, "trigger": trigger,
                          "companies": list(cins)}, sort_keys=True, default=str)
    return Operation(
        operation_id="op_" + hashlib.sha256(payload.encode()).hexdigest()[:12],
        intent=f"Assess what {instrument} requires, for {len(cins) or 'no'} watched compan"
               f"{'y' if len(cins) == 1 else 'ies'}",
        trigger=dict(trigger),
        requirements=tuple(reqs),
        created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        companies=cins,
    )


# A Gazette listing does NOT name the instrument it contains. Measured live
# 2026-09-23: all six listed items had no G.S.R./S.O. number anywhere in the
# subject column -- extraordinary items read "Publication of Notification..."
# (truncated by the site), weeklies read "This Gazette may contains Multiple
# Subjects". The number lives inside the PDF.
#
# So the watcher can say "the Ministry of Corporate Affairs published something
# today" and cannot say what. That is a real gap, and the only honest handling is
# to make IDENTIFYING the instrument the first piece of work, rather than guessing
# a number and matching the reverse index against the guess.
_INSTRUMENT = re.compile(r"(?:G\.?\s?S\.?\s?R\.?|S\.?\s?O\.?)\s*\d+\s*\(?E?\)?", re.I)


def instrument_in(text: str) -> str | None:
    """The instrument number named in `text`, or None. Never guesses."""
    m = _INSTRUMENT.search(text or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def operation_for_gazette_item(item: dict, *, watchlist: Watchlist | None = None,
                               now: datetime | None = None) -> Operation:
    """Work created by one Gazette listing row.

    The row names a ministry and a date; it does not name the instrument (see
    `_INSTRUMENT` above). So:

    * If the subject happens to name an instrument, the full operation is built
      from the reverse index, exactly as `operation_for_instrument` would.
    * Otherwise the operation carries ONE blocking requirement -- open the PDF and
      identify the instrument -- and states plainly that no obligation has been
      matched. It does not list obligations "that might" be affected, because the
      index has been given nothing to match on.

    A multi-ministry weekly is included rather than skipped: `corporate_affairs is
    None` means UNKNOWN, and an unknown ministry may still carry an MCA instrument.
    """
    now = now or datetime.now(timezone.utc)
    named = instrument_in(f"{item.get('subject', '')} {item.get('gazette_id', '')}")
    if named:
        op = operation_for_instrument(named, trigger=item, watchlist=watchlist, now=now)
        if op is not None:
            return op

    gid = item.get("gazette_id", "(unidentified gazette)")
    ministry = item.get("ministry", "")
    unknown_ministry = item.get("corporate_affairs") is None
    reqs = (
        Requirement(
            requirement_id=_rid(gid, "identify"),
            question=(f"Open {item.get('pdf_url') or gid} and identify which instrument it "
                      "contains (the G.S.R./S.O. number), and whether it amends the Companies "
                      "Act 2013 or rules under it."),
            obligation_id="(unidentified)",
            provision=gid,
            specialist=LEGAL_RESEARCH,
            criticality=BLOCKING,
            minimum_evidence="the instrument number read from the Gazette PDF itself",
            note=("The listing does not name the instrument: the subject column is truncated by "
                  "the site" + (", and this row names no single ministry" if unknown_ministry else "")
                  + ". No obligation has been matched, because the index has been given nothing "
                    "to match on."),
        ),
        Requirement(
            requirement_id=_rid(gid, "review"),
            question=("Decide whether this Gazette item concerns any watched company at all. "
                      "Nothing has been established by its appearance here."),
            obligation_id="(review)", provision=gid, specialist=HUMAN_REVIEW,
            criticality=BLOCKING,
            minimum_evidence="a named reviewer records a decision and a reason",
            depends_on=(_rid(gid, "identify"),),
        ),
    )
    cins = watchlist.cins() if watchlist else ()
    payload = json.dumps({"gazette": gid, "companies": list(cins)}, sort_keys=True, default=str)
    return Operation(
        operation_id="op_" + hashlib.sha256(payload.encode()).hexdigest()[:12],
        intent=f"Identify what {gid} contains" + (f" ({ministry})" if ministry else ""),
        trigger=dict(item), requirements=reqs,
        created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), companies=cins,
    )


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    trigger = {"gazette_id": "CG-DL-E-01122025-268124", "ministry": "Ministry of Corporate Affairs",
               "pdf_url": "https://egazette.gov.in/WriteReadData/2025/268124.pdf"}
    wl = Watchlist()
    wl.add("U72200KA2019PTC123456", "Acme Holdings Private Limited")
    wl.add("U72200KA2019PTC123456", "duplicate")      # idempotent

    op = operation_for_instrument("880", trigger=trigger, watchlist=wl)
    check(op is not None, "a known instrument creates an operation")
    check(len(wl.companies) == 1, "the watchlist does not double-add a CIN")

    # ---- it creates work, and names it -----------------------------------------
    ids = {r.obligation_id for r in op.requirements}
    check("CA13-S2-85-SMALL" in ids,
          f"the affected obligation drives the requirements ({sorted(ids)})")
    check(all(r.question.strip() for r in op.requirements), "every requirement asks a question")
    check(not any(hasattr(r, "finding") for r in op.requirements),
          "no requirement has anywhere to record a legal conclusion")

    # ---- 'has anyone read it' is ASKED, not assumed ------------------------------
    # PLAN_17 M1.3. This block used to assert the acquire-and-attest requirement was
    # always created and always first. G.S.R. 880(E) was acquired, hashed and
    # attested by a named reviewer on 2026-09-10, and every operation raised on it
    # still opened by demanding someone go and acquire it. A queue that regrows work
    # already done teaches a reviewer to close requirements without reading them.
    from checker.prescribed_thresholds import all_acquired, none_acquired

    with none_acquired():
        unread = operation_for_instrument("880", trigger=trigger, watchlist=wl)
    first = unread.requirements[0]
    check(first.criticality == BLOCKING and "Acquire and attest" in first.question,
          "an UNACQUIRED instrument still opens with a blocking acquire-and-attest")
    check("matched this instrument by NAME" in first.note,
          "...and it says the index matched a name, not a text")

    with all_acquired():
        done = operation_for_instrument("880", trigger=trigger, watchlist=wl)
    check(not any("Acquire and attest" in r.question for r in done.requirements),
          "an ATTESTED instrument creates no requirement to go and acquire it")
    check(len(done.requirements) == len(unread.requirements) - 1,
          f"...exactly one requirement fewer, not a reshuffle "
          f"({len(done.requirements)} vs {len(unread.requirements)})")
    check(not done.budget().can_close,
          "...and the operation still cannot close: the terminal human review remains")
    check(any(r.specialist == HUMAN_REVIEW and r.criticality == BLOCKING
              for r in done.requirements),
          "...because a person still has to decide what follows, which is the point")

    # ---- three specialist types, and the human is one of them -------------------
    used = {r.specialist for r in op.requirements}
    check(HUMAN_REVIEW in used, "a human is a first-class execution target")
    check(len(used & {LEGAL_RESEARCH, CORPORATE_DATA, FINANCIAL_DATA}) >= 2,
          f"work is routed to more than one specialist ({sorted(used)})")
    check(all(r.specialist in SPECIALISTS for r in op.requirements), "every route is a known type")
    check(_route("paid-up share capital") == FINANCIAL_DATA, "capital routes to FINANCIAL_DATA")
    check(_route("dates of every board meeting in the year") == CORPORATE_DATA,
          "board meetings route to CORPORATE_DATA")
    check(_route("the prescribed class under Rule 6") == LEGAL_RESEARCH,
          "a prescribed class routes to LEGAL_RESEARCH")
    check(_route("whatever the registrar thinks about the weather") == HUMAN_REVIEW,
          "an unroutable phrase goes to a HUMAN, never to a guess")

    # ---- the evidence budget ----------------------------------------------------
    b = op.budget()
    check(b.total == len(op.requirements) and b.satisfied == 0, "a fresh operation has nothing satisfied")
    check(not b.can_close, "...and cannot be closed")
    check("no conclusion may be drawn" in b.sentence(),
          "the budget sentence refuses a conclusion while blocking work is open")
    # 880(E) is attested, so the only blocker left is the terminal human review --
    # and that is the correct answer, not a weakened one. The two-blocker case is
    # asserted where it is real: on an instrument nobody has read.
    check(isinstance(b.blocking_open, tuple) and b.blocking_open,
          f"the budget names its blockers by id, not merely counts them ({b.blocking_open})")
    check(set(b.blocking_open) <= {r.requirement_id for r in op.requirements},
          "...and every id it names is a requirement of this operation")
    with none_acquired():
        b2 = operation_for_instrument("880", trigger=trigger, watchlist=wl).budget()
    check(len(b2.blocking_open) == len(b.blocking_open) + 1,
          f"an unread instrument blocks on the acquire AND the review ({len(b2.blocking_open)})")
    check(sum(b.open_by_specialist.values()) == b.total - b.satisfied,
          "open work is accounted for per specialist")

    # ---- the sink ---------------------------------------------------------------
    last = op.requirements[-1]
    check(last.specialist == HUMAN_REVIEW and last.criticality == BLOCKING,
          "the terminal requirement is a human review, and it blocks")
    check(len(last.depends_on) == len(op.requirements) - 1,
          "...and it depends on every other requirement -- one sink")
    check("states nothing on its own" in last.question, "...and says the operation states nothing")

    # ---- satisfying work moves the budget, and only closes when nothing blocks ---
    done = tuple(Requirement(**{**r.__dict__, "status": SATISFIED}) for r in op.requirements)
    op2 = Operation(**{**op.__dict__, "requirements": done})
    check(op2.budget().can_close and op2.budget().satisfied == b.total,
          "an operation with every requirement satisfied can close")
    part = tuple(Requirement(**{**r.__dict__,
                                "status": SATISFIED if r.criticality != BLOCKING else OPEN})
                 for r in op.requirements)
    check(not Operation(**{**op.__dict__, "requirements": part}).budget().can_close,
          "satisfying everything EXCEPT the blocking work does not let it close")

    # ---- an instrument that touches nothing creates nothing ---------------------
    check(operation_for_instrument("G.S.R. 9999(E)", trigger=trigger) is None,
          "an instrument the index does not know creates NO operation, rather than empty work")

    # ---- the trigger is stored verbatim, and the disclaimer travels with it ------
    check(op.trigger["gazette_id"] == trigger["gazette_id"], "the observation is stored verbatim")
    d = op.to_dict()
    check("has not been read against any company's facts" in d["what_this_is_not"],
          "the serialised operation carries what it is not")
    check(d["budget"]["can_close"] is False and d["requirements"],
          "the serialised form carries the budget and the work")
    check(json.dumps(d)[:1] == "{", "the operation serialises to JSON")

    # ---- tasks_for ---------------------------------------------------------------
    check(all(r.specialist == FINANCIAL_DATA for r in op.tasks_for(FINANCIAL_DATA)),
          "tasks_for returns only that specialist's open work")
    try:
        op.tasks_for("ASTROLOGY"); check(False, "an unknown specialist must raise")
    except ValueError:
        check(True, "an unknown specialist raises rather than returning nothing")

    # ---- the type refuses nonsense ------------------------------------------------
    for bad in ({"specialist": "NOPE"}, {"criticality": "URGENT"}, {"status": "MAYBE"},
                {"question": "   "}):
        try:
            Requirement(**{**op.requirements[1].__dict__, **bad})
            check(False, f"a Requirement with {bad} must raise")
        except ValueError:
            check(True, f"a Requirement refuses {list(bad)[0]}={list(bad.values())[0]!r}")
    try:
        WatchedCompany(cin="  "); check(False, "a watch with no CIN must raise")
    except ValueError:
        check(True, "a watched company with no CIN raises")

    # ---- a Gazette row does not name its instrument (measured 2026-09-23) --------
    check(instrument_in("G.S.R. 880(E) dated 1 December 2025") == "G.S.R. 880(E)",
          "an instrument number in the text is found")
    check(instrument_in("Publication of Notification...") is None,
          "a truncated subject yields None, not a guess")
    check(instrument_in("This Gazette may contains Multiple Subjects") is None,
          "a multi-subject weekly yields None")

    live_shape = {"gazette_id": "CG-DL-E-23092026-276437", "kind": "EXTRAORDINARY",
                  "ministry": "Ministry of Corporate Affairs", "subject": "Publication of Notification...",
                  "pdf_url": "https://egazette.gov.in/WriteReadData/2026/276437.pdf",
                  "corporate_affairs": True}
    g = operation_for_gazette_item(live_shape, watchlist=wl)
    check(len(g.requirements) == 2, "an unidentified gazette row creates exactly two requirements")
    check("identify which instrument" in g.requirements[0].question,
          "...the first is to open the PDF and identify the instrument")
    check(g.requirements[0].specialist == LEGAL_RESEARCH
          and g.requirements[0].criticality == BLOCKING, "...routed to legal research, blocking")
    check(all(r.obligation_id in ("(unidentified)", "(review)") for r in g.requirements),
          "...and NO obligation is claimed to be affected, because none was matched")
    check("nothing to match on" in g.requirements[0].note,
          "...the note says why no obligation was matched")
    check(not g.budget().can_close, "an unidentified gazette operation cannot be closed")

    weekly = {**live_shape, "gazette_id": "CG-DL-W-23092026-276420", "kind": "WEEKLY",
              "ministry": "This Gazette may contains Multiple Ministries",
              "subject": "This Gazette may contains Multiple Subjects", "corporate_affairs": None}
    gw = operation_for_gazette_item(weekly, watchlist=wl)
    check("names no single ministry" in gw.requirements[0].note,
          "a multi-ministry weekly is included, and says its ministry is unknown")

    named = {**live_shape, "subject": "Companies (Specification of definitions) Amendment "
                                      "Rules vide G.S.R. 880(E)"}
    gn = operation_for_gazette_item(named, watchlist=wl)
    check(any(r.obligation_id == "CA13-S2-85-SMALL" for r in gn.requirements),
          "a row that DOES name its instrument gets the full reverse-index operation")

    # ---- the ring boundary ---------------------------------------------------------
    from checker import rings
    check(rings.ring_of("checker.operations") == rings.RING_2, "this module is Ring 2")
    check(not [v for v in rings.violations() if "operations" in v],
          "no Ring 0 or Ring 1 module imports it")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
