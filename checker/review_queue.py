"""
The human review queue: what a person must check before law is served.

`checker/admission.py` says material cannot reach a model until a human approves it. This module
is the work that human does. It is deliberately not a folder of documents: a review item names one
target, asks specific answerable questions, and points at the pages to check them against. A
reviewer who is not told what to look at will confirm that a document looks fine.

Two properties this enforces that a form would not:

  - A decision that restricts or rejects REQUIRES a written reason. "Approved with limitations"
    and no note is unauditable six months later, when the limitation is what matters.
  - Resolving items is what clears the admission gate. The queue is not paperwork alongside the
    state machine; it is the thing that opens it.

Timestamps are passed in. Nothing here reads the clock, so tests are exact and a replayed audit
trail is identical.

Run: python3 checker/review_queue.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from checker import admission as adm

__all__ = ["ReviewItem", "ReviewDecision", "Finding", "ReviewError", "TEMPLATES",
           "create_items", "assign", "decide", "open_items", "apply_to_admission",
           "save_queue", "load_queue"]

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "corpus/admission/review_queue.json"

PENDING, ASSIGNED, IN_REVIEW = "PENDING", "ASSIGNED", "IN_REVIEW"
APPROVED, REJECTED, ESCALATED = "APPROVED", "REJECTED", "NEEDS_ESCALATION"
LIMITED = "LIMITED_APPROVAL"

OPEN_STATUSES = (PENDING, ASSIGNED, IN_REVIEW, ESCALATED)
DECISIONS = (APPROVED, REJECTED, ESCALATED, LIMITED)

# Questions are per scope because a reviewer checking a rule boundary and one checking an Act link
# are doing different jobs, and a single generic checklist gets skimmed.
TEMPLATES: dict[str, tuple[str, ...]] = {
    "INSTRUMENT": (
        "Is the Gazette number and date correct?",
        "Is this the principal instrument, not an amendment or consolidation?",
        "Is the commencement date correct?",
    ),
    "RULE": (
        "Is the numbered rule boundary correct?",
        "Is the heading materially faithful to the gazette?",
        "Are the page bounds correct?",
        "Is the extracted text usable for legal reasoning?",
    ),
    "LINK": (
        "Does the cited provision actually appear in the rule's text?",
        "Is MADE_UNDER vs REFERS_TO the correct relation?",
        "Does the target section exist and match the subject matter?",
    ),
    "EXTRACTION_DEFECT": (
        "Does this defect change the meaning of the operative text?",
        "Does it block serving, or only warrant a warning?",
    ),
    "FORM": (
        "Where does the operative rule text end and the Annexure begin?",
        "Should the form tail be excluded from automatic serving?",
    ),
}


class ReviewError(ValueError):
    """An invalid review action. Never downgraded to a warning."""


@dataclass(frozen=True)
class Finding:
    field_name: str
    status: str          # CONFIRMED | LIMITED | INCORRECT
    comment: str = ""

    def to_dict(self) -> dict:
        return dict(field=self.field_name, status=self.status, comment=self.comment)


@dataclass(frozen=True)
class ReviewDecision:
    decision: str
    reviewer_id: str
    at: str
    notes: str = ""
    findings: tuple[Finding, ...] = ()
    restriction_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ReviewError(f"{self.decision!r} is not a decision; one of {DECISIONS}")
        if self.decision in (REJECTED, LIMITED, ESCALATED) and not self.notes.strip():
            raise ReviewError(
                f"a {self.decision} decision requires a written reason -- an unexplained "
                "restriction is unauditable once the reviewer has moved on")
        if self.decision == LIMITED and not self.restriction_codes:
            raise ReviewError("LIMITED_APPROVAL requires machine-readable restriction codes")

    def to_dict(self) -> dict:
        return dict(decision=self.decision, reviewer_id=self.reviewer_id, at=self.at,
                    notes=self.notes, findings=[f.to_dict() for f in self.findings],
                    restriction_codes=list(self.restriction_codes))


@dataclass(frozen=True)
class ReviewItem:
    review_item_id: str
    instrument_id: str
    scope: str
    target_id: str
    priority: str = "MEDIUM"
    status: str = PENDING
    reviewer_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    note: str = ""
    questions: tuple[str, ...] = ()
    decision: ReviewDecision | None = None

    def __post_init__(self) -> None:
        if self.scope not in TEMPLATES:
            raise ReviewError(f"{self.scope!r} has no review template")
        if not self.questions:
            object.__setattr__(self, "questions", TEMPLATES[self.scope])

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def to_dict(self) -> dict:
        return dict(review_item_id=self.review_item_id, instrument_id=self.instrument_id,
                    scope=self.scope, target_id=self.target_id, priority=self.priority,
                    status=self.status, reviewer_id=self.reviewer_id,
                    page_start=self.page_start, page_end=self.page_end, note=self.note,
                    questions=list(self.questions),
                    decision=self.decision.to_dict() if self.decision else None)


def create_items(instrument_id: str, specs: list[dict]) -> list[ReviewItem]:
    """Build queue items from a list of {scope, target_id, priority, page_start, page_end, note}."""
    out = []
    for i, s in enumerate(specs, start=1):
        out.append(ReviewItem(
            review_item_id=f"ri-{instrument_id.lower()}-{i:03d}",
            instrument_id=instrument_id, scope=s["scope"], target_id=s["target_id"],
            priority=s.get("priority", "MEDIUM"), page_start=s.get("page_start"),
            page_end=s.get("page_end"), note=s.get("note", "")))
    return out


def assign(item: ReviewItem, reviewer_id: str) -> ReviewItem:
    if not item.is_open:
        raise ReviewError(f"{item.review_item_id} is {item.status}; only open items are assignable")
    return replace(item, reviewer_id=reviewer_id, status=ASSIGNED)


def decide(item: ReviewItem, decision: ReviewDecision) -> ReviewItem:
    if not item.is_open:
        raise ReviewError(f"{item.review_item_id} already resolved as {item.status}")
    status = {APPROVED: APPROVED, LIMITED: APPROVED, REJECTED: REJECTED,
              ESCALATED: ESCALATED}[decision.decision]
    return replace(item, status=status, decision=decision,
                   reviewer_id=decision.reviewer_id or item.reviewer_id)


def open_items(items: list[ReviewItem], target_id: str | None = None) -> list[str]:
    return [i.review_item_id for i in items
            if i.is_open and (target_id is None or i.target_id == target_id)]


def apply_to_admission(rec: adm.AdmissionRecord, items: list[ReviewItem], *,
                       actor: str, at: str) -> adm.AdmissionRecord:
    """Recompute a target's admission state from its review items.

    This is the join between queue and gate. It never promotes on its own judgement: it reports
    what the reviewers decided, and refuses to move while anything is unresolved.
    """
    mine = [i for i in items if i.target_id == rec.target_id]
    still_open = tuple(i.review_item_id for i in mine if i.is_open)
    rec = replace(rec, open_review_items=still_open)
    if still_open or not mine:
        return rec
    if any(i.status == REJECTED for i in mine):
        if adm.REJECTED in adm.TRANSITIONS.get(rec.state, ()):
            return adm.transition(rec, adm.REJECTED, actor=actor, at=at,
                                  reason="a reviewer rejected this target")
        return rec
    codes = tuple(sorted({c for i in mine if i.decision
                          for c in i.decision.restriction_codes}))
    if rec.state == adm.HUMAN_REVIEW_PENDING:
        rec = adm.transition(rec, adm.HUMAN_REVIEWED, actor=actor, at=at,
                             reason="all review items resolved")
    target = adm.DEFECT_FLAGGED_PRODUCTION_LIMITED if codes else adm.PRODUCTION_USABLE
    if rec.state == adm.HUMAN_REVIEWED:
        rec = adm.transition(rec, target, actor=actor, at=at,
                             reason="reviewers approved" + (" with restrictions" if codes else ""),
                             restriction_codes=codes)
    return rec


def save_queue(items: list[ReviewItem]) -> Path:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps([i.to_dict() for i in items], indent=2, ensure_ascii=False))
    return QUEUE


def load_queue() -> list[ReviewItem]:
    if not QUEUE.is_file():
        return []
    out = []
    for d in json.loads(QUEUE.read_text()):
        dec = d.get("decision")
        out.append(ReviewItem(
            review_item_id=d["review_item_id"], instrument_id=d["instrument_id"],
            scope=d["scope"], target_id=d["target_id"], priority=d["priority"],
            status=d["status"], reviewer_id=d.get("reviewer_id"),
            page_start=d.get("page_start"), page_end=d.get("page_end"), note=d.get("note", ""),
            questions=tuple(d.get("questions", ())),
            decision=ReviewDecision(
                decision=dec["decision"], reviewer_id=dec["reviewer_id"], at=dec["at"],
                notes=dec.get("notes", ""),
                findings=tuple(Finding(f["field"], f["status"], f.get("comment", ""))
                               for f in dec.get("findings", [])),
                restriction_codes=tuple(dec.get("restriction_codes", ()))) if dec else None))
    return out


def _test() -> None:
    ok = fail = 0
    T = "2026-08-21T00:00:00Z"

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    items = create_items("BR2014", [
        {"scope": "RULE", "target_id": "RULE:BR2014:R1", "page_start": 13, "page_end": 13},
        {"scope": "FORM", "target_id": "RULE:BR2014:R15", "priority": "HIGH",
         "page_start": 17, "page_end": 22, "note": "annexure tail"},
    ])
    check(len(items) == 2, "items created")
    check(items[0].questions == TEMPLATES["RULE"], "a RULE item gets the rule template")
    check(items[1].questions == TEMPLATES["FORM"], "a FORM item gets a different template")
    check(all(i.is_open for i in items), "new items are open")

    check(assign(items[0], "counsel-1").status == ASSIGNED, "assignment works")

    try:
        ReviewDecision(LIMITED, "c", T, notes="", restriction_codes=("X",))
        check(False, "LIMITED without a note must raise")
    except ReviewError as e:
        check("written reason" in str(e), "a limited approval demands a written reason")
    try:
        ReviewDecision(LIMITED, "c", T, notes="tail unbounded")
        check(False, "LIMITED without codes must raise")
    except ReviewError:
        check(True, "a limited approval demands restriction codes")
    try:
        ReviewDecision(REJECTED, "c", T)
        check(False, "REJECT without a note must raise")
    except ReviewError:
        check(True, "a rejection demands a written reason")
    check(ReviewDecision(APPROVED, "c", T).decision == APPROVED,
          "a plain approval needs no note")

    rec = adm.AdmissionRecord("INSTRUMENT", "RULE:BR2014:R1", adm.HUMAN_REVIEW_PENDING)
    held = apply_to_admission(rec, items, actor="sys", at=T)
    check(not held.production_usable, "an instrument with open items is not servable")
    check(held.open_review_items == ("ri-br2014-001",),
          "only items for THIS target block it")

    done = [decide(items[0], ReviewDecision(APPROVED, "counsel-1", T)), items[1]]
    promoted = apply_to_admission(rec, done, actor="sys", at=T)
    check(promoted.state == adm.PRODUCTION_USABLE, "resolving every item promotes the target")
    check(promoted.production_usable, "...and it becomes servable")

    ltd_items = [decide(items[0], ReviewDecision(
        LIMITED, "counsel-1", T, notes="annexure tail unbounded",
        restriction_codes=("NO_AUTO_SERVE_FORM_TAIL",)))]
    ltd = apply_to_admission(rec, ltd_items, actor="sys", at=T)
    check(ltd.state == adm.DEFECT_FLAGGED_PRODUCTION_LIMITED,
          "a limited approval lands in limited production, not full")
    check(ltd.restriction_codes == ("NO_AUTO_SERVE_FORM_TAIL",),
          "the restriction code survives into the admission record")

    rej = [decide(items[0], ReviewDecision(REJECTED, "counsel-1", T, notes="wrong instrument"))]
    out = apply_to_admission(rec, rej, actor="sys", at=T)
    check(out.state == adm.REJECTED and not out.production_usable,
          "one rejection rejects the target")

    try:
        decide(done[0], ReviewDecision(APPROVED, "c2", T))
        check(False, "re-deciding a resolved item must raise")
    except ReviewError:
        check(True, "a resolved item cannot be decided twice")

    esc = [decide(items[0], ReviewDecision(ESCALATED, "counsel-1", T, notes="needs counsel"))]
    check(apply_to_admission(rec, esc, actor="sys", at=T).open_review_items != (),
          "an escalated item still counts as open")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
