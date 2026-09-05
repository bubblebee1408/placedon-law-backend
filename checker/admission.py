"""
Admission control: existence is not admissibility.

A source can be acquired, hashed, classified, parsed and internally searchable and still be unsafe
to put in front of a model that will state law to a lawyer. Those are different facts and this
module refuses to let them collapse into one, because that seam is where a legal AI quietly starts
answering from material nobody approved.

The rule the whole file exists to enforce: **only PRODUCTION_USABLE material reaches a model-facing
evidence pack.** Everything else may be searched, listed and reviewed, but not served.

Two modes, deliberately asymmetric:
  MODE_REVIEW  -- a human inspecting the corpus must see unreviewed material, or review is
                  impossible.
  MODE_MODEL   -- the model must not, and a blocked item is reported as blocked rather than
                  silently dropped, so "no evidence" is never confused with "evidence withheld".

Records are immutable; a transition returns a new record and appends an audit event.

Run: python3 checker/admission.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

__all__ = [
    "AdmissionRecord", "AuditEvent", "AdmissionError",
    "transition", "servable", "blocked_reason", "load", "save",
    "MODE_MODEL", "MODE_REVIEW", "STATES", "SERVABLE_STATES",
]

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "corpus/admission"

DISCOVERED = "DISCOVERED"
ACQUIRED = "ACQUIRED"
TECHNICALLY_VERIFIED = "TECHNICALLY_VERIFIED"
STRUCTURED = "STRUCTURED"
HUMAN_REVIEW_PENDING = "HUMAN_REVIEW_PENDING"
HUMAN_REVIEWED = "HUMAN_REVIEWED"
PRODUCTION_USABLE = "PRODUCTION_USABLE"
DEFECT_FLAGGED_PRODUCTION_LIMITED = "DEFECT_FLAGGED_PRODUCTION_LIMITED"
REJECTED = "REJECTED"
NEEDS_ESCALATION = "NEEDS_ESCALATION"
SUSPENDED = "SUSPENDED"

STATES = (DISCOVERED, ACQUIRED, TECHNICALLY_VERIFIED, STRUCTURED, HUMAN_REVIEW_PENDING,
          HUMAN_REVIEWED, PRODUCTION_USABLE, DEFECT_FLAGGED_PRODUCTION_LIMITED, REJECTED,
          NEEDS_ESCALATION, SUSPENDED)

# Only these may reach a model. DEFECT_FLAGGED_PRODUCTION_LIMITED is servable but carries
# restriction codes the pack builder must honour.
SERVABLE_STATES = (PRODUCTION_USABLE, DEFECT_FLAGGED_PRODUCTION_LIMITED)

MODE_MODEL = "MODEL"
MODE_REVIEW = "REVIEW"

# A state machine, not a free-for-all. Promotion cannot skip review: STRUCTURED has exactly one
# forward edge and it leads to a human.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    DISCOVERED: (ACQUIRED, REJECTED),
    ACQUIRED: (TECHNICALLY_VERIFIED, REJECTED),
    TECHNICALLY_VERIFIED: (STRUCTURED, REJECTED),
    STRUCTURED: (HUMAN_REVIEW_PENDING, REJECTED),
    HUMAN_REVIEW_PENDING: (HUMAN_REVIEWED, REJECTED, NEEDS_ESCALATION),
    NEEDS_ESCALATION: (HUMAN_REVIEW_PENDING, HUMAN_REVIEWED, REJECTED),
    HUMAN_REVIEWED: (PRODUCTION_USABLE, DEFECT_FLAGGED_PRODUCTION_LIMITED, REJECTED),
    PRODUCTION_USABLE: (SUSPENDED, DEFECT_FLAGGED_PRODUCTION_LIMITED),
    DEFECT_FLAGGED_PRODUCTION_LIMITED: (PRODUCTION_USABLE, SUSPENDED, REJECTED),
    SUSPENDED: (HUMAN_REVIEW_PENDING, REJECTED),
    REJECTED: (),
}


class AdmissionError(ValueError):
    """An illegal transition or an unsupportable admission claim."""


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor: str
    at: str                  # passed in; this module never reads the clock, so tests are exact
    before: str
    after: str
    reason: str

    def to_dict(self) -> dict:
        return dict(event_type=self.event_type, actor=self.actor, at=self.at,
                    before=self.before, after=self.after, reason=self.reason)


@dataclass(frozen=True)
class AdmissionRecord:
    target_type: str          # INSTRUMENT | RULE | PROVISION | LINK | FORM
    target_id: str
    state: str
    restriction_codes: tuple[str, ...] = ()
    open_review_items: tuple[str, ...] = ()
    history: tuple[AuditEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise AdmissionError(f"{self.state!r} is not an admission state")
        if self.state == DEFECT_FLAGGED_PRODUCTION_LIMITED and not self.restriction_codes:
            raise AdmissionError(
                f"{self.target_id}: limited production requires machine-readable restriction "
                "codes -- an unbounded 'limited' approval is just an approval")

    @property
    def production_usable(self) -> bool:
        return self.state in SERVABLE_STATES

    @property
    def restricted_use(self) -> bool:
        return bool(self.restriction_codes)

    def to_dict(self) -> dict:
        return dict(target_type=self.target_type, target_id=self.target_id, state=self.state,
                    production_usable=self.production_usable, restricted_use=self.restricted_use,
                    restriction_codes=list(self.restriction_codes),
                    open_review_items=list(self.open_review_items),
                    history=[h.to_dict() for h in self.history])


def transition(rec: AdmissionRecord, to_state: str, *, actor: str, at: str, reason: str,
               restriction_codes: tuple[str, ...] = ()) -> AdmissionRecord:
    """Move a target to a new state, or refuse and say why.

    Promotion to a servable state is blocked while any review item is open. That is the check that
    turns the queue from paperwork into a gate.
    """
    if to_state not in STATES:
        raise AdmissionError(f"{to_state!r} is not an admission state")
    allowed = TRANSITIONS.get(rec.state, ())
    if to_state not in allowed:
        raise AdmissionError(
            f"{rec.target_id}: {rec.state} -> {to_state} is not a legal transition "
            f"(allowed: {', '.join(allowed) or 'none -- terminal'})")
    if to_state in SERVABLE_STATES and rec.open_review_items:
        raise AdmissionError(
            f"{rec.target_id}: cannot become {to_state} while {len(rec.open_review_items)} "
            f"review item(s) are open: {', '.join(rec.open_review_items)}")
    if not reason.strip():
        raise AdmissionError(f"{rec.target_id}: a state change requires a reason")

    codes = restriction_codes or (rec.restriction_codes if to_state != PRODUCTION_USABLE else ())
    event = AuditEvent("STATE_CHANGE", actor, at, rec.state, to_state, reason)
    return replace(rec, state=to_state, restriction_codes=tuple(codes),
                   history=rec.history + (event,))


def servable(rec: AdmissionRecord, mode: str) -> bool:
    """Whether this target may be returned in the given mode."""
    if mode == MODE_REVIEW:
        return rec.state != DISCOVERED       # nothing to look at before it is fetched
    if mode == MODE_MODEL:
        return rec.production_usable
    raise AdmissionError(f"{mode!r} is not a mode; use MODE_MODEL or MODE_REVIEW")


def blocked_reason(rec: AdmissionRecord, mode: str) -> str:
    """Why this target was withheld. Never empty when servable() is False.

    A blocked item must be *reported* as blocked. Dropping it silently makes 'we found no law'
    indistinguishable from 'we found law you are not allowed to see', and those call for opposite
    responses from the reader.
    """
    if servable(rec, mode):
        return ""
    if mode == MODE_MODEL:
        return (f"{rec.target_id} exists in state {rec.state} but is not admitted for model use"
                + (f" (restrictions: {', '.join(rec.restriction_codes)})"
                   if rec.restriction_codes else ""))
    return f"{rec.target_id} has not been acquired"


def path_for(target_type: str, target_id: str) -> Path:
    return STORE / f"{target_type.lower()}_{target_id.replace(':', '_')}.json"


def save(rec: AdmissionRecord) -> Path:
    STORE.mkdir(parents=True, exist_ok=True)
    p = path_for(rec.target_type, rec.target_id)
    p.write_text(json.dumps(rec.to_dict(), indent=2))
    return p


def load(target_type: str, target_id: str) -> AdmissionRecord | None:
    p = path_for(target_type, target_id)
    if not p.is_file():
        return None
    d = json.loads(p.read_text())
    return AdmissionRecord(
        target_type=d["target_type"], target_id=d["target_id"], state=d["state"],
        restriction_codes=tuple(d.get("restriction_codes", ())),
        open_review_items=tuple(d.get("open_review_items", ())),
        history=tuple(AuditEvent(**h) for h in d.get("history", [])))


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    T = "2026-08-21T00:00:00Z"
    r = AdmissionRecord("RULE", "RULE:X:R1", STRUCTURED)
    check(not r.production_usable, "STRUCTURED is not production usable")
    check(not servable(r, MODE_MODEL), "STRUCTURED is withheld from the model")
    check(servable(r, MODE_REVIEW), "...but visible to a reviewer, or review is impossible")
    check("not admitted for model use" in blocked_reason(r, MODE_MODEL),
          "a withheld item reports WHY it was withheld")

    # The gate: parsing must not reach production without passing through a human.
    try:
        transition(r, PRODUCTION_USABLE, actor="system", at=T, reason="parsed fine")
        check(False, "STRUCTURED -> PRODUCTION_USABLE must be illegal")
    except AdmissionError as e:
        check("not a legal transition" in str(e), "cannot promote straight from STRUCTURED")

    pend = transition(r, HUMAN_REVIEW_PENDING, actor="system", at=T, reason="parsing complete")
    check(pend.state == HUMAN_REVIEW_PENDING, "STRUCTURED -> HUMAN_REVIEW_PENDING is legal")
    check(len(pend.history) == 1 and pend.history[0].before == STRUCTURED,
          "the transition is recorded in the audit trail")
    check(r.state == STRUCTURED, "the original record is unchanged -- records are immutable")

    reviewed = transition(pend, HUMAN_REVIEWED, actor="counsel", at=T, reason="checked vs gazette")
    prod = transition(reviewed, PRODUCTION_USABLE, actor="counsel", at=T, reason="approved")
    check(prod.production_usable and servable(prod, MODE_MODEL), "reviewed material may be served")
    check(len(prod.history) == 3, "every hop is in the trail")

    # Open review items block promotion, which is what makes the queue a gate.
    blocked = replace(reviewed, open_review_items=("ri-1", "ri-2"))
    try:
        transition(blocked, PRODUCTION_USABLE, actor="x", at=T, reason="ship it")
        check(False, "promotion with open items must be refused")
    except AdmissionError as e:
        check("review item(s) are open" in str(e), "open review items block promotion")

    # Limited approval must be bounded by codes, or it is just approval wearing a hedge.
    try:
        AdmissionRecord("RULE", "RULE:X:R15", DEFECT_FLAGGED_PRODUCTION_LIMITED)
        check(False, "limited production without codes must raise")
    except AdmissionError as e:
        check("restriction codes" in str(e), "limited production demands restriction codes")

    ltd = transition(reviewed, DEFECT_FLAGGED_PRODUCTION_LIMITED, actor="counsel", at=T,
                     reason="annexure tail unbounded",
                     restriction_codes=("NO_AUTO_SERVE_FORM_TAIL",))
    check(ltd.production_usable and ltd.restricted_use, "limited approval is servable but marked")
    check("NO_AUTO_SERVE_FORM_TAIL" in blocked_reason(
        replace(ltd, state=SUSPENDED), MODE_MODEL), "restrictions survive into the block reason")

    # Suspension takes effect immediately.
    susp = transition(prod, SUSPENDED, actor="counsel", at=T, reason="defect found in operative text")
    check(not servable(susp, MODE_MODEL), "a suspended item leaves model retrieval at once")
    check(servable(susp, MODE_REVIEW), "...but remains inspectable for audit")

    try:
        transition(AdmissionRecord("RULE", "r", REJECTED), HUMAN_REVIEWED,
                   actor="x", at=T, reason="reconsider")
        check(False, "REJECTED is terminal")
    except AdmissionError as e:
        check("terminal" in str(e), "REJECTED is terminal")

    try:
        transition(pend, HUMAN_REVIEWED, actor="x", at=T, reason="   ")
        check(False, "a blank reason must be refused")
    except AdmissionError:
        check(True, "a state change without a reason is refused")

    try:
        servable(r, "SOMETHING")
        check(False, "an unknown mode must raise")
    except AdmissionError:
        check(True, "an unknown mode is rejected rather than defaulting")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
