"""Intent `review_document` — a corporate filing against the SS-1 / SS-2 checks.

PLAN_23 O1. The deterministic sibling of `agents/review_contract.py`, and the differences
are the point:

    review_contract   a CONTRACT against a company playbook. A model reads the clauses.
                      Findings are POTENTIAL_ISSUEs against a standard nobody enacted.
    review_document   a FILING against Secretarial Standards. NO MODEL IS CALLED at all.
                      `checker/ss/defects.py` is regex and arithmetic, and every rule in it
                      traces to a real ROC adjudication order.

**No model means no residency question.** `review_contract` needs `test_data` because a
client contract may not be sent to UAE North (PLAN_22 D3). Nothing here leaves the process,
so this verb takes no such flag -- and adding one "for symmetry" would teach a caller that
ticking it is what makes a document safe to send, which is not what it means.

## The rule this module exists to enforce

**Classify first, then check, and never the other way round.** `checker/ss/defects.py`
records why in its own header: running minutes checks against a NOTICE produced
false-positive rates of 80-93% against genuinely compliant filings, because an AGM notice is
issued BEFORE the meeting and cannot record when the meeting concluded, whether a quorum was
present, or when the minutes were entered in the book. `APPLICABILITY` already gates this;
this module surfaces the gate rather than flattening it, so a caller can see that a check did
not apply instead of seeing a silent PASS.

## Why an unknown type is not a clean bill of health

If `classify` cannot tell what the document is, `scan` marks every gated check `N/A` -- which
is correct, and which renders as a page of rows saying nothing is wrong. That is the most
dangerous screen this system could draw: a document nobody identified, reported as having no
defects.

So an unclassified document returns **no findings at all** and a stated
`CLASSIFICATION_UNCERTAIN`. The uncertainty is the answer. It is not a refusal -- the request
was well formed and we did the work -- and it is not a result, because there is no document
type to have a result about.

## The type is decided by code, and cannot be passed in

There is deliberately no `doc_type` input. A caller who could declare "this is minutes" could
turn every minutes check on a notice back on, which is the exact failure the classifier was
added to stop. PLAN_23 §3: code decides the plan, the status, the authority and the date.

Run: PYTHONPATH=. python3 agents/review_document.py
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from checker.ss import defects as ss

# The statuses `checker/ss/defects.py` returns, restated here so a new one breaks a test
# rather than reaching a screen no one designed for it.
PASS = "PASS"
DEFECT = "DEFECT"
NEEDS_BOOK = "NEEDS_BOOK"
NOT_APPLICABLE = "N/A"
STATUSES = (PASS, DEFECT, NEEDS_BOOK, NOT_APPLICABLE)

# The one status a person has to resolve. NEEDS_BOOK is this intent's NEEDS_LAWYER: code has
# looked and cannot decide from the text, because the fact lives in the physical book.
HUMAN_GATED = (NEEDS_BOOK,)

ANSWERED = "ANSWERED"
UNCLASSIFIED = "UNCLASSIFIED"
CLASSIFICATION_UNCERTAIN = "CLASSIFICATION_UNCERTAIN"

KNOWN_TYPES = ("minutes", "notice", "outcome")
MEETING_KINDS = ("board", "general")


class BadRequest(ValueError):
    """The caller's input cannot be used. Raised before any check runs."""


@dataclass(frozen=True)
class Item:
    """One check, as it is served. `rule_id`, `source` and `quoted_span` are required by
    PLAN_23 O1 and are never empty -- when a check found nothing, the span says what was
    looked for and not found, which is evidence about the document too."""

    rule_id: str
    status: str
    source: str
    defect: str
    quoted_span: str
    precedent: str
    applies: bool
    advisory_only: bool = False

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "status": self.status, "source": self.source,
                "defect": self.defect, "quoted_span": self.quoted_span,
                "precedent": self.precedent, "applies": self.applies,
                "advisory_only": self.advisory_only,
                "needs_human": self.status in HUMAN_GATED}


@dataclass(frozen=True)
class Review:
    doc_type: str
    status: str
    items: tuple[Item, ...] = ()
    note: str = ""
    code: str | None = None
    meeting_kind: str = "board"

    @property
    def defects(self) -> tuple[Item, ...]:
        return tuple(i for i in self.items if i.status == DEFECT)

    @property
    def needs_human(self) -> tuple[Item, ...]:
        return tuple(i for i in self.items if i.status in HUMAN_GATED)

    @property
    def requires_review(self) -> bool:
        """True whenever a person must look before this is relied on."""
        return self.status != ANSWERED or bool(self.needs_human) or bool(self.defects)

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "status": self.status,
            "code": self.code,
            "note": self.note,
            "meeting_kind": self.meeting_kind,
            "requires_review": self.requires_review,
            "checks_run": len(self.items),
            "defect_count": len(self.defects),
            "needs_human_count": len(self.needs_human),
            "findings": [i.to_dict() for i in self.items],
        }


def _parse_date(value, field: str) -> date | None:
    """A date, or None when absent. An UNREADABLE one raises rather than becoming None.

    None is meaningful here: it turns T1.4b into NEEDS_BOOK, "cannot verify the 30-day
    deadline". Silently mapping a typo'd date onto that would report "not supplied" about a
    date the caller did supply, and a reviewer would go looking for it in the minutes book.
    """
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise BadRequest(
            f"{field}={value!r} is not a date in YYYY-MM-DD form. It is not treated as "
            f"absent: 'not supplied' is a claim about the document, and this is a typo.",
        ) from None


def review(text: str, *, meeting_kind: str = "board", meeting_date=None, entry_date=None,
           pages_consecutive_across_book: bool | None = None,
           every_page_initialled: bool | None = None,
           blank_pages_scored_out: bool | None = None) -> Review:
    """One document, classified and then checked. No model, no network, no corpus.

    `meeting_kind` is recorded on the run and passed to `checker/ss/defects.py`. **No check
    currently branches on it** -- said plainly so nobody assumes minutes of a general meeting
    are treated differently from a board meeting's today.
    """
    if not (text or "").strip():
        raise BadRequest("text is required")
    if meeting_kind not in MEETING_KINDS:
        raise BadRequest(f"meeting_kind must be one of {MEETING_KINDS}, not {meeting_kind!r}")

    md = _parse_date(meeting_date, "meeting_date")
    ed = _parse_date(entry_date, "entry_date")

    # CLASSIFY FIRST. Everything below depends on the answer, including whether to run at all.
    doc_type = ss.classify(text)
    if doc_type not in KNOWN_TYPES:
        return Review(
            doc_type=doc_type, status=UNCLASSIFIED, code=CLASSIFICATION_UNCERTAIN, items=(),
            meeting_kind=meeting_kind,
            note=("This document could not be identified as minutes, a notice or an outcome "
                  "filing, so no check was run against it. That is uncertainty about the "
                  "document, NOT a finding that it is free of defects: every check here is "
                  "written for a particular document type, and one run against a document "
                  "nobody has identified would be a claim about a thing we cannot name."),
        )

    m = ss.Minutes(
        text=text, kind=meeting_kind, meeting_date=md, entry_date=ed,
        pages_consecutive_across_book=pages_consecutive_across_book,
        every_page_initialled=every_page_initialled,
        blank_pages_scored_out=blank_pages_scored_out,
        doc_type=doc_type,
    )
    items = []
    for f in ss.scan(m):
        allowed = ss.APPLICABILITY.get(f.check_id)
        items.append(Item(
            rule_id=f.check_id, status=f.status, source=f.ss_cite, defect=f.defect,
            quoted_span=f.evidence, precedent=f.precedent,
            applies=(allowed is None or doc_type in allowed),
            advisory_only=f.advisory_only,
        ))
    return Review(doc_type=doc_type, status=ANSWERED, items=tuple(items),
                  meeting_kind=meeting_kind,
                  note=("Every finding cites Secretarial Standards and a real ROC "
                        "adjudication order. A NEEDS_BOOK item is not a defect and not a "
                        "pass: it is a property of the physical minutes book that no reader "
                        "of a file can decide."))


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

    NOTICE = (
        "NOTICE OF THE 14th ANNUAL GENERAL MEETING\n\n"
        "Notice is hereby given that the 14th Annual General Meeting of the members of "
        "Acme Private Limited will be held on 30 September 2026 at the registered office.\n"
        "An explanatory statement pursuant to the Companies Act is annexed.\n"
        "A proxy form is enclosed. E-voting will be available.\n"
    )
    UNKNOWN = ("Dear Sir,\n\nPlease find enclosed the cheque for the amount discussed. "
               "Kindly acknowledge receipt at your convenience.\n\nYours faithfully\n")

    # ── classification decides everything ──────────────────────────────────
    rv_min = review(ss.CLEAN, meeting_date=date(2026, 4, 1), entry_date=date(2026, 4, 20))
    check(rv_min.doc_type == "minutes" and rv_min.status == ANSWERED,
          f"the clean specimen classifies as minutes and is checked ({rv_min.doc_type})")

    rv_not = review(NOTICE)
    check(rv_not.doc_type == "notice", f"a notice classifies as a notice ({rv_not.doc_type})")

    # THE rule. Not "few defects" -- none, from any minutes-only check.
    minutes_only = {cid for cid, allowed in ss.APPLICABILITY.items() if allowed == frozenset({"minutes"})}
    fired = [i.rule_id for i in rv_not.items
             if i.rule_id in minutes_only and i.status == DEFECT]
    check(not fired,
          f"NO minutes-only check reports a DEFECT on a notice {fired} -- an AGM notice is "
          f"issued before the meeting, so it cannot record what the meeting did")
    check(all(not i.applies for i in rv_not.items if i.rule_id in minutes_only),
          "...and every one of them is marked as not applying, rather than silently passing")
    check(any(i.applies for i in rv_not.items),
          "...while the checks that DO apply to a notice still run")

    # ── an unknown type is uncertainty, not a clean bill ────────────────────
    rv_unk = review(UNKNOWN)
    check(rv_unk.status == UNCLASSIFIED and rv_unk.code == CLASSIFICATION_UNCERTAIN,
          f"an unidentifiable document is UNCLASSIFIED with a code ({rv_unk.status})")
    check(rv_unk.items == (),
          "...and returns NO findings: a page of rows saying nothing is wrong, about a "
          "document nobody identified, is the most dangerous screen this could draw")
    check(rv_unk.to_dict()["defect_count"] == 0 and rv_unk.requires_review,
          "...and still requires review, so 0 defects cannot be read as a pass")
    check("NOT a finding that it is free of defects" in rv_unk.note,
          "...and the note says so in terms")

    # ── every finding carries rule id, source and quoted span (PLAN_23 O1) ──
    for rv, label in ((rv_min, "minutes"), (rv_not, "notice")):
        blank = [i.rule_id for i in rv.items
                 if not (i.rule_id.strip() and i.source.strip() and i.quoted_span.strip())]
        check(not blank, f"every {label} finding carries rule id, source and quoted span {blank}")

    d = rv_min.to_dict()
    check(set(d["findings"][0]) >= {"rule_id", "source", "quoted_span", "status", "needs_human"},
          "...and they survive to_dict, which is what the gateway serves")

    # ── NEEDS_BOOK is the human gate, and it is neither pass nor defect ─────
    check(all(i.rule_id in ("T1.1", "T1.2", "T1.3", "T1.4b") for i in rv_min.needs_human),
          f"NEEDS_BOOK is only the physical-book checks {[i.rule_id for i in rv_min.needs_human]}")
    check(rv_min.needs_human and all(i.status not in (PASS, DEFECT) for i in rv_min.needs_human),
          "...and a NEEDS_BOOK item is neither a pass nor a defect")
    check(all(i.to_dict()["needs_human"] for i in rv_min.needs_human),
          "...and is flagged for a person on the wire")

    # Supplying the book facts resolves them, which is what a reviewer's answer does.
    rv_book = review(ss.CLEAN, meeting_date=date(2026, 4, 1), entry_date=date(2026, 4, 20),
                     pages_consecutive_across_book=True, every_page_initialled=True,
                     blank_pages_scored_out=True)
    check(not any(i.rule_id in ("T1.1", "T1.2", "T1.3") for i in rv_book.needs_human),
          "...and once the book is inspected those three stop asking")

    # ── dates: absent is a state, unreadable is an error ────────────────────
    lag = review(ss.CLEAN, meeting_date=date(2026, 4, 1), entry_date=date(2026, 6, 1))
    t14b = next(i for i in lag.items if i.rule_id == "T1.4b")
    check(t14b.status == DEFECT and "61 days" in t14b.defect,
          f"a 61-day entry lag is a DEFECT naming the number ({t14b.defect})")
    none_dates = next(i for i in review(ss.CLEAN).items if i.rule_id == "T1.4b")
    check(none_dates.status == NEEDS_BOOK,
          "...while dates not supplied is NEEDS_BOOK, never a pass")
    try:
        review(ss.CLEAN, meeting_date="1 April 2026")
        check(False, "an unreadable date is refused")
    except BadRequest as e:
        check("not treated as absent" in str(e),
              "an unreadable date RAISES rather than becoming None -- 'not supplied' is a "
              "claim about the document, and a typo is not that claim")

    # ── the inputs code owns ───────────────────────────────────────────────
    import inspect
    # Parameters, not co_varnames -- `doc_type` is a LOCAL in review(), and the first
    # version of this check read the locals and failed on the very thing it was asserting.
    check("doc_type" not in inspect.signature(review).parameters,
          "review() takes NO doc_type parameter: a caller who could declare 'this is "
          "minutes' could turn every minutes check on a notice back on")
    for bad, why in ((("", {}), "empty text"), ((ss.CLEAN, {"meeting_kind": "agm"}),
                                                "an undeclared meeting kind")):
        try:
            review(bad[0], **bad[1])
            check(False, f"{why} is refused")
        except BadRequest:
            check(True, f"refused: {why}")

    # ── the vocabulary ─────────────────────────────────────────────────────
    check(all(i.status in STATUSES for rv in (rv_min, rv_not) for i in rv.items),
          "every status is one of the four this module declares")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
