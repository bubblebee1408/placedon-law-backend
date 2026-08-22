"""
Controlled drafting: a document assembled from typed slots, never written free-hand.

The distinction this module exists to hold: a draft is not a piece of prose that mentions the law,
it is a set of values each of which came from somewhere. The exported document reads normally. The
provenance panel behind it says, for every legal or derived value, where it came from and whether
anyone may rely on it.

Only ONE template is implemented -- the AGM notice. That is deliberate. A broad drafting suite built
before a single template has been used by a professional would be guessing at what they need, and
every template added multiplies the ways an unsupported value can reach a filed document.

**Approval is blocked, not warned.** A draft containing any MODEL_SUGGESTION or UNKNOWN slot cannot
be approved: `approve()` raises. Most first drafts WILL be blocked, because a real notice needs
facts a matter does not yet hold -- the meeting time, the venue, the business to be transacted. That
is the mechanism working. A draft that silently rendered "[TBD]" and let itself be approved would be
worse than one that refuses.

No model is wired in. MODEL_SUGGESTION exists in the vocabulary so that when one is, its output
arrives already labelled as unsupported rather than being retrofitted into the type system later.

Run: python3 checker/drafting.py
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.provenance_slots import (DERIVED_FACT, SOURCE_QUOTE, TEMPLATE_TEXT, UNKNOWN,
                                      USER_FACT, Slot, SlotError, blocking_slots,
                                      provenance_panel, ready_for_approval)

__all__ = ["Draft", "DraftError", "draft_agm_notice"]


class DraftError(ValueError):
    """An attempt to approve or export a draft that is not supported."""


@dataclass(frozen=True)
class Draft:
    title: str
    body: str                       # rendered, with {slot} placeholders already substituted
    slots: tuple[Slot, ...]
    citations: tuple[str, ...]
    review_notes: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return ready_for_approval(self.slots)

    def blockers(self) -> tuple[Slot, ...]:
        return blocking_slots(self.slots)

    def approve(self, reviewer: str, at: str) -> dict:
        """Record a human's approval. Raises while anything in the draft is unsupported."""
        if not reviewer.strip():
            raise DraftError("approval requires a named reviewer -- an unattributed approval is "
                             "not an approval")
        if not self.ready:
            names = ", ".join(f"{s.name} ({s.slot_type})" for s in self.blockers())
            raise DraftError(
                f"cannot approve: {len(self.blockers())} slot(s) are unsupported -- {names}. "
                "Fill them with sourced values, or the document states things nobody stands behind.")
        return dict(title=self.title, reviewer=reviewer, approved_at=at,
                    citations=list(self.citations),
                    slots=[s.to_dict() for s in self.slots])

    def render(self) -> str:
        """The document as a reader sees it, plus the reviewer's panel beneath."""
        out = [self.title, "=" * len(self.title), "", self.body, ""]
        if self.citations:
            out += ["LEGAL BASIS", *[f"  - {c}" for c in self.citations], ""]
        if self.review_notes:
            out += ["FOR REVIEW", *[f"  - {n}" for n in self.review_notes], ""]
        out += [provenance_panel(self.slots)]
        return "\n".join(out)


def draft_agm_notice(*, company_name: str, deadline, provision_text: str,
                     meeting_date: date | None = None, meeting_time: str = "",
                     venue: str = "", business: tuple[str, ...] = ()) -> Draft:
    """Assemble an AGM notice from typed slots.

    `deadline` is a checker.agm.AGMDeadline. Its binding date enters as a DERIVED_FACT carrying its
    working, never as a bare string -- a date in a legal notice with no derivation behind it is
    indistinguishable from a guess.
    """
    slots: list[Slot] = [
        Slot("heading", "NOTICE OF ANNUAL GENERAL MEETING", TEMPLATE_TEXT),
        Slot("company_name", company_name, USER_FACT),
    ]

    if deadline.binding is not None:
        c = deadline.binding
        slots.append(Slot("statutory_interval", c.interval_text, SOURCE_QUOTE,
                          source="Companies Act 2013, s.96(1)"))
        slots[-1].verify_quote(provision_text)
        slots.append(Slot("agm_deadline", c.deadline.isoformat(), DERIVED_FACT,
                          source="Companies Act 2013, s.96(1)", working=c.working(),
                          inputs=(f"{c.anchor_label}: {c.anchor.isoformat()}",
                                  f"interval: {c.interval_text}"),
                          note=f"binding limb: {c.label}"))
    else:
        # No deadline could be established. The notice cannot assert one, and saying "to be
        # confirmed" in a legal document is how an unresolved question becomes a filed statement.
        slots.append(Slot("agm_deadline", "", UNKNOWN,
                          note="no binding deadline could be established; "
                               + "; ".join(deadline.missing_facts)))

    slots.append(Slot("meeting_date", meeting_date.isoformat() if meeting_date else "",
                      USER_FACT if meeting_date else UNKNOWN,
                      note="" if meeting_date else "the date the meeting will actually be held"))
    slots.append(Slot("meeting_time", meeting_time, USER_FACT if meeting_time else UNKNOWN,
                      note="" if meeting_time else
                      "s.96(2) requires business hours, 9 a.m. to 6 p.m., on a non-national-holiday"))
    slots.append(Slot("venue", venue, USER_FACT if venue else UNKNOWN,
                      note="" if venue else "s.96(2) constrains where the meeting may be held"))
    slots.append(Slot("business", "; ".join(business) if business else "",
                      USER_FACT if business else UNKNOWN,
                      note="" if business else "the business to be transacted must be stated"))

    body_lines = [
        f"NOTICE is hereby given that the Annual General Meeting of {company_name} will be held",
        f"on {meeting_date.isoformat() if meeting_date else '[MEETING DATE — NOT SUPPLIED]'}"
        f" at {meeting_time or '[TIME — NOT SUPPLIED]'}",
        f"at {venue or '[VENUE — NOT SUPPLIED]'} to transact the following business:",
        "",
    ]
    body_lines += [f"  {i}. {b}" for i, b in enumerate(business, 1)] or \
                  ["  [BUSINESS TO BE TRANSACTED — NOT SUPPLIED]"]

    notes = [
        "This notice is a DRAFT. Every value is labelled by origin in the panel below.",
        "The statutory deadline shown is derived from a quoted interval and a fact you supplied; "
        "it appears nowhere in the Act.",
    ]
    if deadline.binding and meeting_date and meeting_date > deadline.binding.deadline:
        notes.append(
            f"THE MEETING DATE ({meeting_date.isoformat()}) IS AFTER THE STATUTORY DEADLINE "
            f"({deadline.binding.deadline.isoformat()}). Check this before proceeding.")
    notes.extend(deadline.notes)

    return Draft("NOTICE OF ANNUAL GENERAL MEETING", "\n".join(body_lines), tuple(slots),
                 ("Companies Act 2013, s.96(1)",), tuple(notes))


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    from checker.agm import compute
    from checker.retrieve import MODE_MODEL, retrieve

    pack, _ = retrieve("s.96", mode=MODE_MODEL)
    src = pack.usable[0].reading_text or pack.usable[0].raw_text
    dl = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=False,
                 previous_agm=date(2025, 9, 20))

    # A first draft with only the facts a matter holds. It SHOULD be blocked.
    thin = draft_agm_notice(company_name="ABC Private Limited", deadline=dl, provision_text=src)
    check(not thin.ready, "a draft missing the meeting facts is NOT ready for approval")
    names = {s.name for s in thin.blockers()}
    check({"meeting_date", "meeting_time", "venue", "business"} <= names,
          f"...and the unsupplied facts are the blockers ({sorted(names)})")
    try:
        thin.approve("counsel-1", "2026-08-22T00:00:00Z")
        check(False, "approving a blocked draft must raise")
    except DraftError as e:
        check("cannot approve" in str(e), "approving a blocked draft is refused, not warned about")

    # Fully supplied: approval becomes available.
    full = draft_agm_notice(company_name="ABC Private Limited", deadline=dl, provision_text=src,
                            meeting_date=date(2026, 9, 15), meeting_time="11:00",
                            venue="Registered office, Bengaluru",
                            business=("Adoption of financial statements",
                                      "Appointment of auditor"))
    check(full.ready, "a fully supplied draft is ready for approval")
    rec = full.approve("counsel-1", "2026-08-22T00:00:00Z")
    check(rec["reviewer"] == "counsel-1" and rec["approved_at"],
          "approval records who and when")
    check(any(s["type"] == DERIVED_FACT for s in rec["slots"]),
          "the approval record carries the typed slots, not just the text")
    try:
        full.approve("", "2026-08-22T00:00:00Z")
        check(False, "an unattributed approval must raise")
    except DraftError:
        check(True, "approval requires a named reviewer")

    # The derived date carries its working, and the quote is real.
    dd = next(s for s in full.slots if s.name == "agm_deadline")
    check(dd.slot_type == DERIVED_FACT and "six months" in dd.working,
          "the deadline is a DERIVED_FACT carrying its working")
    sq = next(s for s in full.slots if s.name == "statutory_interval")
    check(sq.slot_type == SOURCE_QUOTE and " ".join(sq.value.split()).lower() in
          " ".join(src.split()).lower(), "the quoted interval is verbatim in s.96")

    # A meeting scheduled after the deadline must be called out, not quietly drafted.
    late = draft_agm_notice(company_name="ABC Private Limited", deadline=dl, provision_text=src,
                            meeting_date=date(2026, 10, 20), meeting_time="11:00",
                            venue="Registered office", business=("Adoption of accounts",))
    check(any("AFTER THE STATUTORY DEADLINE" in n for n in late.review_notes),
          "a meeting date past the deadline is flagged in the draft")
    check(late.ready, "...and it is still 'ready' -- the flag informs the human, it does not "
                      "decide for them")

    # No deadline established -> the notice cannot assert one.
    nodl = compute(source_text=src, financial_year_end=date(2026, 3, 31), is_first_agm=False)
    blocked = draft_agm_notice(company_name="ABC Private Limited", deadline=nodl,
                               provision_text=src, meeting_date=date(2026, 9, 15),
                               meeting_time="11:00", venue="Office", business=("Accounts",))
    dd2 = next(s for s in blocked.slots if s.name == "agm_deadline")
    check(dd2.slot_type == UNKNOWN and not blocked.ready,
          "with no binding deadline the slot is UNKNOWN and blocks approval")
    check("previous annual general meeting" in dd2.note,
          "...and names the fact that would unblock it")

    rendered = full.render()
    check("PROVENANCE" in rendered and "SOURCE_QUOTE" in rendered,
          "the rendering shows the provenance panel")
    check("appears nowhere in the Act" in rendered,
          "...and states plainly that the derived date is not statutory text")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
