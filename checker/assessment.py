"""
Three axes, because one status cannot carry three questions.

`applicability.py` (the HR-era evaluator, still live for PoSH/ESI) answers with exactly three
words: APPLIES, DOES_NOT_APPLY, INSUFFICIENT_DATA. That vocabulary has no way to say **"I could
not assess this"**, and the gap is not academic. Right now every one of the 15 Board Powers rules
exists, is held on disk, and is withheld pending human review. Asked whether one of them bites, the
old vocabulary can only answer:

    DOES_NOT_APPLY      -- a FALSE STATEMENT OF LAW. The rule may well apply; we simply have not
                           been allowed to look at it.
    INSUFFICIENT_DATA   -- blames the user's document for a gap that is OURS.

Both are wrong, and they are wrong in opposite directions. "This does not apply to you" closes a
question. "I could not assess this" says the question is open and says why. To a lawyer those are
opposite answers, and conflating them is the most damaging thing this layer could do.

So three orthogonal vocabularies:

    PROVISION_STATUS      can we see the law at all?          (a fact about OUR corpus)
    APPLICABILITY_STATUS  does the law apply to these facts?  (a fact about the LAW and the DOCUMENT)
    OBLIGATION_STATUS     what must someone do?               (a fact about the CONSEQUENCE)

The rule this module exists to enforce, made impossible to violate through the public API:

    **A provision that is not ADMITTED can NEVER yield DOES_NOT_APPLY.**

It is enforced in `Assessment.__post_init__`, not only in `assess()`. A caller who hand-builds the
dataclass to route around the constructor gets an exception, because a rule that only holds on the
happy path is not an invariant -- it is a convention, and conventions decay.

No I/O beyond reading the pack handed in. Immutable results. Every Assessment carries `reasons` in
words a reviewer can act on, because a status nobody can explain is a status nobody can fix.

Run: PYTHONPATH=. python3 checker/assessment.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parent.parent

# Mirrors checker/evidence_pack.py: this module is run both as a bare file and through
# scripts/run_tests.sh (which exports PYTHONPATH). Without this, `python3 checker/assessment.py`
# puts checker/ on sys.path rather than the repo root and `import checker.x` dies.
if __package__ in (None, ""):  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(ROOT))

from checker.evidence_pack import (  # noqa: E402
    EP_RECORD_MISSING, EP_TEXT_EMPTY, SD_002,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from checker.evidence_pack import EvidencePack

__all__ = [
    "Assessment", "AssessmentError", "assess", "assess_from_pack", "servable_conclusion",
    "PROVISION_STATUSES", "APPLICABILITY_STATUSES", "OBLIGATION_STATUSES",
    "NOT_RETRIEVED", "RETRIEVED", "ADMITTED", "LIMITED", "WITHHELD", "SUSPENDED", "REJECTED",
    "APPLIES", "DOES_NOT_APPLY", "POSSIBLY_APPLIES", "INSUFFICIENT_FACTS", "NOT_ASSESSABLE",
    "CONFLICTING_EVIDENCE",
    "IDENTIFIED", "NOT_IDENTIFIED", "UNKNOWN",
]

# --- axis 1: PROVISION_STATUS -- can we see the law at all? --------------------------------------
# Strings rather than an Enum, following checker/admission.py: these ride into JSON audit trails
# and must survive the round trip unchanged.
NOT_RETRIEVED = "NOT_RETRIEVED"   # nothing by this key came back at all
RETRIEVED = "RETRIEVED"           # named, but its text was never loaded or is empty
ADMITTED = "ADMITTED"             # a reviewer approved it for model use, unrestricted
LIMITED = "LIMITED"               # approved WITH restrictions (e.g. SD-001's editorial tail)
WITHHELD = "WITHHELD"             # exists, held back pending review -- the 15 Board Powers rules
SUSPENDED = "SUSPENDED"           # was admitted, pulled after a defect (e.g. SD-002's s.16)
REJECTED = "REJECTED"             # terminally refused

PROVISION_STATUSES = (NOT_RETRIEVED, RETRIEVED, ADMITTED, LIMITED, WITHHELD, SUSPENDED, REJECTED)

# The only status from which a closed answer may be derived. LIMITED is deliberately NOT in here:
# a restriction bounds which part of the provision may be served, and the part we may not serve is
# exactly where an applicability trigger could be hiding.
CONCLUSIVE_STATUSES = (ADMITTED,)

# --- axis 2: APPLICABILITY_STATUS -- does the law apply to these facts? --------------------------
APPLIES = "APPLIES"
DOES_NOT_APPLY = "DOES_NOT_APPLY"
POSSIBLY_APPLIES = "POSSIBLY_APPLIES"
INSUFFICIENT_FACTS = "INSUFFICIENT_FACTS"       # the LAW is here; the DOCUMENT does not say enough
NOT_ASSESSABLE = "NOT_ASSESSABLE"               # the gap is OURS, not the document's
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"   # the facts point both ways; do not average them

APPLICABILITY_STATUSES = (APPLIES, DOES_NOT_APPLY, POSSIBLY_APPLIES, INSUFFICIENT_FACTS,
                          NOT_ASSESSABLE, CONFLICTING_EVIDENCE)

# --- axis 3: OBLIGATION_STATUS -- what must someone do? ------------------------------------------
IDENTIFIED = "IDENTIFIED"
NOT_IDENTIFIED = "NOT_IDENTIFIED"
UNKNOWN = "UNKNOWN"
# NOT_ASSESSABLE is shared with axis 2 on purpose: it is the same claim about the same gap.
OBLIGATION_STATUSES = (IDENTIFIED, NOT_IDENTIFIED, UNKNOWN, NOT_ASSESSABLE)


class AssessmentError(ValueError):
    """An unsupportable assessment. Raised rather than downgraded to a plausible answer."""


@dataclass(frozen=True)
class Assessment:
    """One provision, assessed on all three axes, with the reasoning that produced it.

    Frozen and self-validating. The validation is not defensive programming -- it is the product
    rule. Constructing a DOES_NOT_APPLY from anything but an ADMITTED provision is a false
    statement of law, so the dataclass refuses to hold one.
    """
    provision_key: str
    provision_status: str
    applicability: str
    obligation: str
    reasons: tuple[str, ...] = ()
    blocking_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.provision_key).strip():
            raise AssessmentError("an assessment must name the provision it is about")
        if self.provision_status not in PROVISION_STATUSES:
            raise AssessmentError(f"{self.provision_status!r} is not a provision status")
        if self.applicability not in APPLICABILITY_STATUSES:
            raise AssessmentError(f"{self.applicability!r} is not an applicability status")
        if self.obligation not in OBLIGATION_STATUSES:
            raise AssessmentError(f"{self.obligation!r} is not an obligation status")
        if not self.reasons:
            raise AssessmentError(
                f"{self.provision_key}: an assessment with no stated reason cannot be reviewed, "
                "and an unreviewable conclusion is not servable")

        # THE invariant. See the module docstring.
        if self.applicability == DOES_NOT_APPLY and self.provision_status not in CONCLUSIVE_STATUSES:
            raise AssessmentError(
                f"{self.provision_key}: DOES_NOT_APPLY requires provision_status ADMITTED, not "
                f"{self.provision_status}. Saying a provision we cannot fully see does not apply "
                f"is a false statement of law; the honest answer is {NOT_ASSESSABLE}.")
        if self.applicability == DOES_NOT_APPLY and self.blocking_sources:
            raise AssessmentError(
                f"{self.provision_key}: DOES_NOT_APPLY cannot stand while "
                f"{len(self.blocking_sources)} source(s) block assessment: "
                f"{', '.join(self.blocking_sources)}")
        if self.provision_status == LIMITED and self.applicability == APPLIES:
            raise AssessmentError(
                f"{self.provision_key}: a restricted provision cannot yield a bare APPLIES. "
                f"The restricted part of the text is unread; {POSSIBLY_APPLIES} is the ceiling.")

    @property
    def assessable(self) -> bool:
        return self.applicability != NOT_ASSESSABLE

    def to_dict(self) -> dict:
        return {"provision_key": self.provision_key, "provision_status": self.provision_status,
                "applicability": self.applicability, "obligation": self.obligation,
                "servable_conclusion": servable_conclusion(self),
                "reasons": list(self.reasons), "blocking_sources": list(self.blocking_sources)}


# --- why each non-admitted status cannot support a conclusion ------------------------------------
# One sentence per status, addressed to a reviewer who has to decide what to do next. "Not
# assessable" without this text is just a shrug with a longer name.
_UNASSESSABLE_REASON: dict[str, str] = {
    NOT_RETRIEVED:
        "no provision under this key was retrieved, so nothing is known about what it says. This "
        "is a gap in our retrieval, NOT a finding that the provision is silent or inapplicable.",
    RETRIEVED:
        "the provision was located by reference but its text was never loaded, so its content is "
        "unknown. An empty record is not an empty provision.",
    WITHHELD:
        "the provision exists and is held, but has not been admitted for use pending human "
        "review. Whether it applies is unknown to us, not answered in the negative.",
    SUSPENDED:
        "the provision was admitted and then suspended after a defect was found in its text "
        "(see docs/SOURCE_DEFECTS.md). Superseded wording cannot settle a question either way.",
    REJECTED:
        "the provision was refused admission, so no statement may be built on it. Refusing the "
        "source is not a finding about the law it carries.",
}

_NEXT_ACTION: dict[str, str] = {
    NOT_RETRIEVED: "next action: confirm the reference, then ingest it.",
    RETRIEVED: "next action: load or re-ingest the corpus record for this provision.",
    WITHHELD: "next action: put this provision through review (checker/review_queue.py).",
    SUSPENDED: "next action: resolve the source defect against an independent publisher.",
    REJECTED: "next action: none available -- rejection is terminal (checker/admission.py).",
}


def _obligation_for(applicability: str, provision_status: str,
                    obligation_identified: bool | None) -> str:
    """The obligation axis follows applicability, and is capped where the law is only partly ours.

    Under LIMITED the ceiling is UNKNOWN even when the caller says an obligation was identified:
    the restriction says part of the provision may not be served, and a duty read out of the part
    we did serve is not safe to state as the duty the provision imposes.
    """
    if applicability == NOT_ASSESSABLE:
        return NOT_ASSESSABLE
    if applicability in (INSUFFICIENT_FACTS, CONFLICTING_EVIDENCE):
        return UNKNOWN
    if applicability == DOES_NOT_APPLY:
        # The provision does not bite, so it imposes nothing here. That is a finding, not a gap.
        return NOT_IDENTIFIED
    if provision_status == LIMITED:
        return UNKNOWN
    if obligation_identified is None:
        return UNKNOWN
    return IDENTIFIED if obligation_identified else NOT_IDENTIFIED


def assess(provision_key: str, *, provision_status: str, facts_established: bool | None,
           blocking_sources: tuple[str, ...] = (), obligation_identified: bool | None = None,
           facts_conflict: bool = False) -> Assessment:
    """Assess one provision on all three axes.

    `facts_established` is tri-state and the three states are NOT interchangeable:
        True  -- the document establishes the facts the provision turns on
        False -- the document establishes that those facts are ABSENT
        None  -- the document does not say (the only honest default)

    `blocking_sources` are things that exist and prevent assessment -- typically a withheld Rule.
    Any blocking source forces NOT_ASSESSABLE regardless of everything else, because a conclusion
    reached while a relevant provision is unread is a conclusion reached on a partial statute book.
    """
    if provision_status not in PROVISION_STATUSES:
        raise AssessmentError(f"{provision_status!r} is not a provision status "
                              f"(one of: {', '.join(PROVISION_STATUSES)})")
    if facts_established is not None and not isinstance(facts_established, bool):
        raise AssessmentError(
            f"{provision_key}: facts_established must be True, False or None. A truthy value that "
            f"is not a bool ({facts_established!r}) hides which of the three it meant.")

    blocking = tuple(s for s in blocking_sources if str(s).strip())
    reasons: list[str] = []

    # 1. Blocking sources win over everything, including an ADMITTED provision.
    if blocking:
        reasons.append(
            f"{provision_key}: {len(blocking)} relevant source(s) exist and could not be read, so "
            f"any conclusion here would rest on a partial statute book.")
        reasons += [f"blocked by: {s}" for s in blocking]
        return Assessment(provision_key, provision_status, NOT_ASSESSABLE, NOT_ASSESSABLE,
                          tuple(reasons), blocking)

    # 2. Anything we cannot fully see cannot close the question -- in either direction.
    if provision_status not in (ADMITTED, LIMITED):
        reasons.append(f"{provision_key}: {_UNASSESSABLE_REASON[provision_status]}")
        reasons.append(_NEXT_ACTION[provision_status])
        reasons.append(
            f"this is {NOT_ASSESSABLE}, not {DOES_NOT_APPLY}: the question is open, not answered.")
        return Assessment(provision_key, provision_status, NOT_ASSESSABLE, NOT_ASSESSABLE,
                          tuple(reasons), ())

    if provision_status == LIMITED:
        reasons.append(
            f"{provision_key}: admitted WITH RESTRICTIONS. Part of this provision's text may not "
            f"be served, so no reading of it is complete.")

    # 3. Contradictory facts are reported as contradictory, never averaged into a conclusion.
    if facts_conflict:
        reasons.append(
            f"{provision_key}: the document supports and contradicts the same triggering fact. "
            f"Resolve the contradiction before this provision can be applied either way.")
        return Assessment(provision_key, provision_status, CONFLICTING_EVIDENCE,
                          _obligation_for(CONFLICTING_EVIDENCE, provision_status, None),
                          tuple(reasons), ())

    if provision_status == LIMITED:
        if facts_established is True:
            reasons.append(
                f"the document establishes the triggering facts, so this provision POSSIBLY "
                f"applies. It cannot be raised to {APPLIES} while the restriction stands.")
            app = POSSIBLY_APPLIES
        elif facts_established is False:
            # Not DOES_NOT_APPLY: the unserved part of the text is exactly where a further
            # trigger could sit, so absence of the facts we could check settles nothing.
            reasons.append(
                f"the facts we could check are absent, but the restricted text is unread and may "
                f"carry a further trigger. Absence of a checked fact is not absence of the law.")
            app = NOT_ASSESSABLE
        else:
            reasons.append(
                f"the document does not establish the triggering facts AND the provision is "
                f"restricted. Part of this gap is ours, so it is not reported as a document gap.")
            app = NOT_ASSESSABLE
        return Assessment(provision_key, provision_status, app,
                          _obligation_for(app, provision_status, obligation_identified),
                          tuple(reasons), ())

    # 4. ADMITTED -- the only branch that may close the question.
    if facts_established is None:
        reasons.append(
            f"{provision_key}: the law is admitted and readable, but the document does not "
            f"establish the facts this provision turns on. The gap is in the document, not in us.")
        app = INSUFFICIENT_FACTS
    elif facts_established is False:
        reasons.append(
            f"{provision_key}: the law is admitted and readable, and the document establishes "
            f"that the facts this provision turns on are absent.")
        app = DOES_NOT_APPLY
    else:
        reasons.append(
            f"{provision_key}: the law is admitted and readable, and the document establishes the "
            f"facts this provision turns on.")
        app = APPLIES

    obligation = _obligation_for(app, provision_status, obligation_identified)
    if obligation == UNKNOWN and app == APPLIES:
        reasons.append("the provision applies but the obligation it imposes has not been "
                       "identified; do not report the absence of a duty.")
    return Assessment(provision_key, provision_status, app, obligation, tuple(reasons), ())


# --- deriving the provision status from a real evidence pack -------------------------------------

# checker/admission.blocked_reason() writes "<key> exists in state SUSPENDED but is not admitted
# for model use". The state is the whole point of the notice, so it is read back rather than
# flattened to a generic "withheld" -- a reviewer needs to know whether to review it or to fix a
# source defect, and those are different queues.
_STATE_IN_NOTICE = re.compile(r"exists in state ([A-Z_]+)")

_ADMISSION_STATE_TO_PROVISION_STATUS: dict[str, str] = {
    "SUSPENDED": SUSPENDED,
    "REJECTED": REJECTED,
}

# Blocking defects say WHY the text is unusable, and the reviewer's next step differs by cause.
_DEFECT_TO_PROVISION_STATUS: dict[str, str] = {
    SD_002: SUSPENDED,              # confirmed pre-amendment wording
    EP_RECORD_MISSING: RETRIEVED,   # named by retrieval, text never loaded
    EP_TEXT_EMPTY: RETRIEVED,
}


def _names_key(text: str, provision_key: str) -> bool:
    """Does this notice name exactly this provision?

    Boundary-aware on purpose: a plain substring test makes ...:S1 match ...:S188, which would
    silently attribute s.188's withholding to s.1.
    """
    return re.search(r"(?<![\w:])" + re.escape(provision_key) + r"(?![\w])", text) is not None


def assess_from_pack(pack: "EvidencePack", provision_key: str, *,
                     facts_established: bool | None = None,
                     obligation_identified: bool | None = None,
                     facts_conflict: bool = False) -> Assessment:
    """Derive the provision status from a real pack, then assess.

    Reads only the pack it is handed -- no disk, no network, no admission lookups. The pack already
    attests to its own mode and carries every withholding notice, so re-deriving admissibility here
    would be a second opinion that could disagree with the boundary that actually served it.
    """
    for p in pack.provisions:
        if p.key != provision_key:
            continue
        codes = tuple(d.code for d in p.defects)
        if p.usable_for_answering:
            if p.defects:
                status = LIMITED
                extra = tuple(f"restriction {d.code}: {d.summary} {d.warning}".strip()
                              for d in p.defects)
            else:
                status = ADMITTED
                extra = (f"{provision_key} is admitted for model use "
                         f"(evidence state {p.claim.state}); its text was served in full.",)
            a = assess(provision_key, provision_status=status,
                       facts_established=facts_established,
                       obligation_identified=obligation_identified,
                       facts_conflict=facts_conflict)
            return Assessment(a.provision_key, a.provision_status, a.applicability, a.obligation,
                              extra + a.reasons, a.blocking_sources)

        # Present and unusable. The pack already computed why; carry its words through rather
        # than paraphrasing them into something a reviewer cannot match back to the pack.
        status = next((_DEFECT_TO_PROVISION_STATUS[c] for c in codes
                       if c in _DEFECT_TO_PROVISION_STATUS), WITHHELD)
        a = assess(provision_key, provision_status=status, facts_established=facts_established,
                   blocking_sources=(f"{provision_key} was located but its text may not be used: "
                                     f"{p.unusable_reason()}",))
        return Assessment(a.provision_key, a.provision_status, a.applicability, a.obligation,
                          a.reasons, a.blocking_sources)

    # Not served. It may still be NAMED in the pack's gap list -- and "named as withheld" is a
    # completely different fact from "never heard of it".
    for notice in pack.missing:
        if not _names_key(notice, provision_key):
            continue
        m = _STATE_IN_NOTICE.search(notice)
        state = m.group(1) if m else ""
        status = _ADMISSION_STATE_TO_PROVISION_STATUS.get(state, WITHHELD)
        return assess(provision_key, provision_status=status,
                      facts_established=facts_established, blocking_sources=(notice,))

    reasons_tail = ("the pack carried no provision at all, so this is an empty-pack gap."
                    if not pack.provisions else
                    f"the pack carried {len(pack.provisions)} other provision(s); this key was not "
                    f"among them and was not recorded as withheld either.")
    a = assess(provision_key, provision_status=NOT_RETRIEVED, facts_established=facts_established)
    return Assessment(a.provision_key, a.provision_status, a.applicability, a.obligation,
                      a.reasons + (reasons_tail,), a.blocking_sources)


def servable_conclusion(a: Assessment) -> bool:
    """May this assessment be stated to a user as a conclusion?

    Deliberately narrow: only a definite answer from a fully admitted provision. POSSIBLY_APPLIES,
    INSUFFICIENT_FACTS and NOT_ASSESSABLE are all reportable -- their `reasons` are exactly what
    the user should be shown -- but none of them is a conclusion, and this function is the gate
    that keeps them from being rendered as one.
    """
    if a.blocking_sources:
        return False
    if a.provision_status not in CONCLUSIVE_STATUSES:
        return False
    return a.applicability in (APPLIES, DOES_NOT_APPLY)


# --- self-test -----------------------------------------------------------------------------------

def _test() -> None:
    from itertools import product

    from checker.retrieve import MODE_MODEL, retrieve

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    # --- 1. the invariant, by exhaustion ---------------------------------------------------------
    # Three examples would prove three cases. Enumerating the product proves the rule.
    combos = list(product(PROVISION_STATUSES, (None, True, False), ((), ("a withheld rule",)),
                          (False, True), (None, True, False)))
    violations = []
    produced: dict[str, int] = {}
    for status, facts, blockers, conflict, oblig in combos:
        a = assess("ACT:X:S1", provision_status=status, facts_established=facts,
                   blocking_sources=blockers, facts_conflict=conflict, obligation_identified=oblig)
        produced[a.applicability] = produced.get(a.applicability, 0) + 1
        if a.applicability == DOES_NOT_APPLY and a.provision_status != ADMITTED:
            violations.append((status, facts, blockers, conflict, oblig))
    check(not violations,
          f"exhaustive: {len(combos)} input combinations, 0 produce DOES_NOT_APPLY without "
          f"ADMITTED (found {len(violations)})")
    check(produced.get(DOES_NOT_APPLY, 0) > 0,
          "...and DOES_NOT_APPLY is still reachable, so the invariant is not vacuous")
    check(all(a_status == ADMITTED for a_status, f, b, c, o in combos
              if assess("ACT:X:S1", provision_status=a_status, facts_established=f,
                        blocking_sources=b, facts_conflict=c,
                        obligation_identified=o).applicability == DOES_NOT_APPLY),
          "every DOES_NOT_APPLY in the enumeration came from an ADMITTED provision")
    check(all(assess("ACT:X:S1", provision_status=s, facts_established=f, blocking_sources=("x",),
                     facts_conflict=c).applicability == NOT_ASSESSABLE
              for s, f, c in product(PROVISION_STATUSES, (None, True, False), (False, True))),
          "a blocking source forces NOT_ASSESSABLE regardless of every other input")
    check(all(assess("ACT:X:S1", provision_status=LIMITED, facts_established=f,
                     facts_conflict=c).applicability != APPLIES
              for f, c in product((None, True, False), (False, True))),
          "LIMITED never reaches a bare APPLIES")

    # The dataclass itself refuses the violation, so bypassing assess() does not bypass the rule.
    for bad in (WITHHELD, SUSPENDED, NOT_RETRIEVED, REJECTED, RETRIEVED, LIMITED):
        try:
            Assessment("ACT:X:S1", bad, DOES_NOT_APPLY, NOT_IDENTIFIED, ("hand-built",))
            check(False, f"hand-built {bad}+DOES_NOT_APPLY must raise")
            break
        except AssessmentError:
            pass
    else:
        check(True, "hand-building DOES_NOT_APPLY from a non-ADMITTED status raises")
    try:
        Assessment("ACT:X:S1", ADMITTED, DOES_NOT_APPLY, NOT_IDENTIFIED, ("r",), ("blocker",))
        check(False, "DOES_NOT_APPLY beside a blocking source must raise")
    except AssessmentError:
        check(True, "DOES_NOT_APPLY cannot coexist with a blocking source")
    try:
        Assessment("ACT:X:S1", LIMITED, APPLIES, IDENTIFIED, ("r",))
        check(False, "LIMITED+APPLIES must raise")
    except AssessmentError:
        check(True, "a restricted provision cannot be hand-built into APPLIES")
    try:
        Assessment("ACT:X:S1", ADMITTED, APPLIES, IDENTIFIED, ())
        check(False, "a reasonless assessment must raise")
    except AssessmentError:
        check(True, "an assessment with no stated reason is refused")
    try:
        assess("ACT:X:S1", provision_status="MAYBE", facts_established=None)
        check(False, "an unknown provision status must raise")
    except AssessmentError:
        check(True, "an unknown provision status is rejected rather than defaulted")

    # --- 2. the three ADMITTED transitions --------------------------------------------------------
    a = assess("ACT:X:S1", provision_status=ADMITTED, facts_established=None)
    check(a.applicability == INSUFFICIENT_FACTS and a.obligation == UNKNOWN,
          "ADMITTED + facts unknown -> INSUFFICIENT_FACTS (the document's gap, named as such)")
    a = assess("ACT:X:S1", provision_status=ADMITTED, facts_established=False)
    check(a.applicability == DOES_NOT_APPLY and a.obligation == NOT_IDENTIFIED,
          "ADMITTED + facts absent -> DOES_NOT_APPLY, the only route to it")
    a = assess("ACT:X:S1", provision_status=ADMITTED, facts_established=True,
               obligation_identified=True)
    check(a.applicability == APPLIES and a.obligation == IDENTIFIED,
          "ADMITTED + facts present -> APPLIES, obligation IDENTIFIED")
    check(assess("ACT:X:S1", provision_status=ADMITTED, facts_established=True).obligation
          == UNKNOWN,
          "an applying provision whose duty was not identified reports UNKNOWN, not NOT_IDENTIFIED")
    a = assess("ACT:X:S1", provision_status=ADMITTED, facts_established=True, facts_conflict=True)
    check(a.applicability == CONFLICTING_EVIDENCE,
          "contradictory facts are reported as CONFLICTING_EVIDENCE, not averaged")

    # --- 3. every non-admitted status abstains, and says why --------------------------------------
    for status in (NOT_RETRIEVED, RETRIEVED, WITHHELD, SUSPENDED, REJECTED):
        a = assess("RULE:BOARD_POWERS:R15", provision_status=status, facts_established=False)
        check(a.applicability == NOT_ASSESSABLE and a.obligation == NOT_ASSESSABLE
              and len(a.reasons) >= 2,
              f"{status} + facts absent -> NOT_ASSESSABLE with a stated reason")
    check("has not been admitted" in " ".join(
        assess("R", provision_status=WITHHELD, facts_established=None).reasons),
          "a WITHHELD provision explains that WE withheld it, not that the document is thin")
    check("review" in " ".join(
        assess("R", provision_status=WITHHELD, facts_established=None).reasons).lower(),
          "...and names the next action a reviewer can take")

    # --- 4. servable_conclusion -------------------------------------------------------------------
    check(servable_conclusion(assess("S", provision_status=ADMITTED, facts_established=True)),
          "an ADMITTED APPLIES may be stated to a user")
    check(servable_conclusion(assess("S", provision_status=ADMITTED, facts_established=False)),
          "an ADMITTED DOES_NOT_APPLY may be stated to a user")
    check(not servable_conclusion(assess("S", provision_status=ADMITTED, facts_established=None)),
          "INSUFFICIENT_FACTS is reportable but is not a conclusion")
    check(not servable_conclusion(assess("S", provision_status=LIMITED, facts_established=True)),
          "POSSIBLY_APPLIES from restricted law is not a conclusion")
    check(not any(servable_conclusion(assess("S", provision_status=s, facts_established=f))
                  for s in (NOT_RETRIEVED, RETRIEVED, WITHHELD, SUSPENDED, REJECTED)
                  for f in (None, True, False)),
          "no unadmitted provision ever yields a servable conclusion")

    # --- 5. real packs, via checker.retrieve ------------------------------------------------------
    pack, _ = retrieve("s.173", mode=MODE_MODEL)
    a = assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S173")
    check(a.provision_status == ADMITTED, "real pack: s.173 derives ADMITTED")
    check(a.applicability == INSUFFICIENT_FACTS,
          "real pack: s.173 with no facts -> INSUFFICIENT_FACTS (the law is here; the doc is not)")
    check(assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S173",
                           facts_established=False).applicability == DOES_NOT_APPLY,
          "real pack: s.173 with facts established absent -> DOES_NOT_APPLY")

    pack, _ = retrieve("s.16", mode=MODE_MODEL)
    a = assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S16", facts_established=False)
    check(a.provision_status == SUSPENDED,
          "real pack: s.16 (SD-002 pre-amendment text) derives SUSPENDED")
    check(a.applicability == NOT_ASSESSABLE,
          "real pack: s.16 is NOT_ASSESSABLE even when the facts point to DOES_NOT_APPLY")
    check(a.blocking_sources and "S16" in a.blocking_sources[0],
          "real pack: s.16 names its own withholding as the blocking source")
    check(not servable_conclusion(a), "real pack: nothing about s.16 may be stated as a conclusion")

    pack, _ = retrieve("s.1", mode=MODE_MODEL)
    a = assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S1", facts_established=True)
    check(a.provision_status == LIMITED, "real pack: s.1 (SD-001 editorial tail) derives LIMITED")
    check(a.applicability == POSSIBLY_APPLIES,
          "real pack: s.1 reaches POSSIBLY_APPLIES at most, never APPLIES")
    check(any("SD-001" in r for r in a.reasons),
          "real pack: the SD-001 restriction appears in the reasons")
    check(assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S1").applicability == NOT_ASSESSABLE,
          "real pack: s.1 with unknown facts is NOT_ASSESSABLE -- part of that gap is ours")

    pack, _ = retrieve("related party transactions", mode=MODE_MODEL)
    a188 = assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S188", facts_established=True)
    check(a188.provision_status == ADMITTED and a188.applicability == APPLIES,
          "real pack: s.188 is admitted and applies on established facts")
    r15 = assess_from_pack(pack, "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R15",
                           facts_established=True)
    check(r15.provision_status == WITHHELD, "real pack: r.15 derives WITHHELD from pack.missing")
    check(r15.applicability == NOT_ASSESSABLE and r15.obligation == NOT_ASSESSABLE,
          "real pack: the withheld rule is NOT_ASSESSABLE on both axes")
    check(r15.blocking_sources and "R15" in r15.blocking_sources[0],
          "real pack: the withheld rule is named as the blocking source")
    check(servable_conclusion(a188) and not servable_conclusion(r15),
          "real pack: the Act section is servable, the withheld rule is not -- same pack")

    # The boundary case the substring bug would break: s.1 must not inherit s.188's notices.
    check(assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S1").provision_status == NOT_RETRIEVED,
          "real pack: key matching is boundary-aware -- S1 does not match S188 or S177")

    pack, _ = retrieve("what colour is the sky", mode=MODE_MODEL)
    a = assess_from_pack(pack, "ACT:COMPANIES_ACT_2013:S173", facts_established=False)
    check(a.provision_status == NOT_RETRIEVED, "real pack: a nonsense query derives NOT_RETRIEVED")
    check(a.applicability == NOT_ASSESSABLE,
          "real pack: nothing retrieved -> NOT_ASSESSABLE, never DOES_NOT_APPLY")
    check(any("empty-pack" in r for r in a.reasons),
          "real pack: the empty pack is named as the reason, not the user's document")

    # --- 6. immutability and serialisation --------------------------------------------------------
    base = assess("S", provision_status=ADMITTED, facts_established=True)
    try:
        base.applicability = DOES_NOT_APPLY          # type: ignore[misc]
        check(False, "Assessment must be immutable")
    except Exception:
        check(True, "an Assessment cannot be mutated after construction")
    d = base.to_dict()
    check(d["applicability"] == APPLIES and d["servable_conclusion"] is True
          and isinstance(d["reasons"], list),
          "to_dict carries all three axes plus servability, JSON-ready")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
