#!/usr/bin/env python3
"""Two drafts, built from a run that already happened. The model may join sentences, not make them.

Job 3. H3 gave drafts a history; this gives them content. Two templates:

    client_email    a note to the client about a REVIEW_CONTRACT result
    research_memo   a memo recording a RESEARCH_QUESTION answer

## The one rule

**A statement of law comes from a verified citation in the source run, verbatim, or it does
not appear.** Not "is flagged", not "is marked unverified" -- does not appear. The model's
job here is joining prose: "Three clauses differ from your standard. The first is this one."
Sentences like that become MODEL_SUGGESTION slots, which `checker/provenance_slots.py`
already makes block approval until a person accepts or edits them.

So a sentence reaches the draft by one of three routes:

    from a citation    the quote, verbatim, as SOURCE_QUOTE with its citation id
    model prose        no legal assertion in it -> MODEL_SUGGESTION, blocks approval
    model prose        a legal assertion carrying a citation id the run really holds ->
                       MODEL_SUGGESTION, blocks approval, and the id travels with it

and by no other. **A model sentence that asserts law with no citation, or with an id the
run does not hold, is DROPPED**, and `dropped` reports it with the reason. A fluent sentence
about a duty nobody can check is the single most dangerous thing this product could emit,
and leaving it in with a warning label is how it reaches a client anyway.

## Why a contract review's email contains no law at all

`review_contract` produces findings against a company PLAYBOOK, and `law_not_held` says in
terms that the Contract Act, the Arbitration Act and stamp duty are declared and not held.
So there is nothing for a SOURCE_QUOTE to come from, and the honest email says "these
clauses differ from your standard" and never "this clause is unenforceable". The template
puts that sentence in the draft itself, as TEMPLATE_TEXT, so it is not left to the covering
email.

## What `asserts_law` is, and what it is not

A deliberately blunt detector: a statutory reference, or duty/validity language. It
over-fires -- "the agreement must be signed by both parties" is a fact about a document, not
a claim about law, and it will be caught. That direction is the safe one: a dropped
connecting sentence costs a person one edit, and an admitted uncited legal claim costs a
client. `_test` pins both directions, including sentences it must NOT catch.

Run: PYTHONPATH=. python3 checker/draft_templates.py --test
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.provenance_slots import (MODEL_SUGGESTION, SOURCE_QUOTE, TEMPLATE_TEXT,
                                      UNKNOWN, Slot)

__all__ = ["asserts_law", "admit", "client_email", "research_memo", "Built",
           "TemplateError"]


class TemplateError(ValueError):
    """A template that cannot be built. Never a warning."""


# A statutory reference: "s.173", "section 42", "Companies Act", "the Act".
_STATUTE = re.compile(
    r"\b(?:s\.\s*\d|section\s+\d|sub-?section|companies\s+act|contract\s+act|"
    r"arbitration\s+act|the\s+act\b|rule\s+\d|regulation\s+\d|schedule\s+[IVX\d])",
    re.IGNORECASE)
# Duty, prohibition and validity language -- the shapes a legal claim takes.
_DUTY = re.compile(
    r"\b(?:must|shall|is\s+required|are\s+required|is\s+obliged|mandatory|"
    r"unlawful|illegal|void|voidable|unenforceable|enforceable|liable|"
    r"is\s+entitled|are\s+entitled|prohibited|permitted\s+by\s+law|"
    r"under\s+law|statutor)", re.IGNORECASE)


def asserts_law(sentence: str) -> bool:
    """Does this sentence make a claim about the law? Blunt on purpose -- see the docstring."""
    text = sentence or ""
    return bool(_STATUTE.search(text) or _DUTY.search(text))


@dataclass(frozen=True)
class Built:
    title: str
    body: str
    kind: str = ""               # the template that built it; the draft's `kind` column
    slots: tuple = ()
    citations: tuple = ()
    dropped: tuple = ()          # ({text, reason},) -- reported, never silent

    def to_dict(self) -> dict:
        return {"title": self.title, "body": self.body, "kind": self.kind,
                "slots": [s.to_dict() for s in self.slots],
                "citations": list(self.citations),
                "dropped": [dict(d) for d in self.dropped],
                "dropped_count": len(self.dropped)}


def admit(prose, known_citation_ids) -> tuple[list, list]:
    """(slots, dropped) for the model's connecting prose.

    `prose` is `[{"text": ..., "citation_ids": [...]}]` -- the same shape the answer
    envelope's `text_blocks` uses, so a model's output travels one way through the system.
    """
    known = set(known_citation_ids or ())
    slots, dropped = [], []
    for i, block in enumerate(prose or ()):
        text = str((block or {}).get("text") or "").strip()
        if not text:
            continue
        ids = [str(c) for c in ((block or {}).get("citation_ids") or ())]
        unknown = [c for c in ids if c not in known]
        if asserts_law(text):
            if not ids:
                dropped.append({
                    "text": text,
                    "reason": ("it states something about the law and carries no citation. "
                               "A statement of law in this product comes from a verified "
                               "quote or it does not appear")})
                continue
            if unknown:
                dropped.append({
                    "text": text,
                    "reason": (f"it cites {unknown}, which this run does not hold. A "
                               f"citation id that does not resolve is worse than none: it "
                               f"looks checkable and is not")})
                continue
        elif unknown:
            # Not a legal claim, but it points at a citation that does not exist. Keep the
            # sentence, lose the dangling reference -- a footnote marker with no footnote.
            ids = [c for c in ids if c in known]
        slots.append(Slot(name=f"prose_{i + 1}", value=text, slot_type=MODEL_SUGGESTION,
                          note=("written by a model; accept or edit it before approval"
                                + (f" (cites {', '.join(ids)})" if ids else ""))))
    return slots, dropped


def _citation_slots(citations) -> tuple[list, list]:
    """A SOURCE_QUOTE per citation, plus the citation strings for the draft's legal basis."""
    slots, basis = [], []
    for c in citations or ():
        quote = str((c or {}).get("quote") or "").strip()
        cid = str((c or {}).get("id") or "").strip()
        prov = str((c or {}).get("provision") or "").strip()
        inst = str((c or {}).get("instrument") or "").strip()
        if not quote or not cid:
            # A citation with no quote cannot be a SOURCE_QUOTE: provenance_slots would
            # refuse it, and it is better refused here with a reason than there with a
            # stack trace.
            continue
        where = " ".join(x for x in (inst, prov) if x) or cid
        slots.append(Slot(name=f"law_{cid}", value=quote, slot_type=SOURCE_QUOTE,
                          source=f"{where} [{cid}]"))
        basis.append(f"{where} [{cid}]")
    return slots, basis


def research_memo(result: dict, *, prose=(), title: str = "") -> Built:
    """A memo from a RESEARCH_QUESTION run. Law comes from the run's citations, verbatim."""
    question = str(result.get("question") or "").strip()
    cits = result.get("citations") or []
    law_slots, basis = _citation_slots(cits)
    known = [str((c or {}).get("id")) for c in cits if (c or {}).get("id")]
    prose_slots, dropped = admit(prose, known)

    head = Slot(name="question", value=question or "(no question recorded)",
                slot_type=TEMPLATE_TEXT if question else UNKNOWN,
                note=("the question as it was asked" if question else
                      "no question was recorded on the run, so the memo cannot say what "
                      "was asked"))
    standing = Slot(
        name="standing", slot_type=TEMPLATE_TEXT,
        value=("Every statement of law below is quoted from the provision cited beside "
               "it. Anything not so quoted is a drafting note and is marked as one."),
        note="fixed wording; it describes how this memo is built")
    slots = [head, standing] + law_slots + prose_slots
    body_lines = [f"Question: {question or '(not recorded)'}", ""]
    for s in law_slots:
        body_lines += [f"{s.source}", f"    “{s.value}”", ""]
    for s in prose_slots:
        body_lines += [s.value, ""]
    if not law_slots:
        body_lines += [("No provision was cited by the underlying answer, so this memo "
                        "states no law."), ""]
    return Built(title=(title or f"Memo: {question[:60]}" if question else "Memo"),
                 kind="research_memo",
                 body="\n".join(body_lines).rstrip(), slots=tuple(slots),
                 citations=tuple(basis), dropped=tuple(dropped))


def client_email(result: dict, *, prose=(), title: str = "") -> Built:
    """An email from a REVIEW_CONTRACT run.

    It states NO law, and says so, because `review_contract` compares a contract with a
    company playbook and `law_not_held` records that the bodies a contract question reaches
    are declared and not held. The disclaimer is TEMPLATE_TEXT inside the draft rather than
    something a covering note is trusted to add.
    """
    findings = [f for f in (result.get("findings") or ()) if isinstance(f, dict)]
    issues = [f for f in findings if str(f.get("kind") or "") == "POTENTIAL_ISSUE"]
    # A contract review carries no legal citations; `citations` is accepted so the rule is
    # the same in both templates rather than special-cased.
    law_slots, basis = _citation_slots(result.get("citations") or [])
    known = [str((c or {}).get("id")) for c in (result.get("citations") or [])
             if (c or {}).get("id")]
    prose_slots, dropped = admit(prose, known)

    bodies = [str((b or {}).get("body") or "")
              for b in (result.get("law_not_held") or ())]
    standing = Slot(
        name="standing", slot_type=TEMPLATE_TEXT,
        value=("These are differences from your own playbook, not statements of law. "
               "Whether any clause is valid, enforceable or void is a question about "
               + (", ".join(bodies) if bodies else "bodies of law")
               + " which this engine does not hold, and it is not answered here."),
        note=("fixed wording. It is inside the draft because a disclaimer in a covering "
              "note is a disclaimer the forwarded document does not carry"))
    slots = [standing]
    for i, f in enumerate(issues, 1):
        clause = str(f.get("clause") or "a clause")
        detail = str(f.get("detail") or "")
        rule = str(f.get("rule_id") or "")
        std = str(f.get("standard_text") or "")
        slots.append(Slot(
            name=f"issue_{i}", value=f"{clause}: {detail}", slot_type=TEMPLATE_TEXT,
            source=rule,
            note=(f"from playbook rule {rule}" + (f"; the standard reads: {std}" if std
                                                  else ""))))
    slots += law_slots + prose_slots
    body_lines = [standing.value, ""]
    if issues:
        body_lines.append(f"{len(issues)} clause(s) differ from the standard:")
        for i, f in enumerate(issues, 1):
            body_lines.append(f"  {i}. {f.get('clause') or 'a clause'} — "
                              f"{f.get('detail') or ''}".rstrip(" —"))
        body_lines.append("")
    else:
        body_lines += ["No clause in this contract differs from the standard on the "
                       "checks that ran.", ""]
    for s in prose_slots:
        body_lines += [s.value, ""]
    return Built(title=(title or "Note on the contract review"),
                 kind="client_email",
                 body="\n".join(body_lines).rstrip(), slots=tuple(slots),
                 citations=tuple(basis), dropped=tuple(dropped))


TEMPLATES = {"client_email": client_email, "research_memo": research_memo}


def build(template: str, result: dict, *, prose=(), title: str = "") -> Built:
    if template not in TEMPLATES:
        raise TemplateError(f"{template!r} is not a template; one of {sorted(TEMPLATES)}")
    return TEMPLATES[template](result, prose=prose, title=title)


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

    print("draft_templates")
    from checker.provenance_slots import blocking_slots, ready_for_approval

    # The citation shape `gateway/envelope.py` and `agents/research_question.py` produce.
    CIT = {"id": "c1", "instrument": "Companies Act 2013", "provision": "s.96(1)",
           "source": "corpus/companies_act/s96.json", "sha256": "a" * 64,
           "quote": ("Every company shall in each year hold a general meeting as its "
                     "annual general meeting.")}
    ASK = {"question": "When must a company hold its AGM?",
           "answer": "In each year.", "citations": [CIT]}

    # ── asserts_law: it must be able to say NO, or it proves nothing ─────────
    for text in ("Section 96 requires an annual general meeting.",
                 "The company must hold a meeting each year.",
                 "Such a clause is void.",
                 "The indemnity is unenforceable.",
                 "Under the Companies Act, the gap may not exceed 15 months.",
                 "The shareholder is entitled to notice.",
                 "Late filing is unlawful.",
                 "Regulation 17 applies to the board's composition."):
        check(asserts_law(text), f"asserts law: {text[:46]!r}")
    for text in ("Three clauses differ from your standard; the first is below.",
                 "I have set out the review results for your contract.",
                 "Happy to walk through this on a call tomorrow.",
                 "The first point concerns the term of confidentiality.",
                 "This note summarises what the review found."):
        check(not asserts_law(text), f"...and does NOT fire on prose: {text[:40]!r}")

    # ── THE JOB'S TEST: a fabricated legal claim is dropped ─────────────────
    FABRICATED = ("Section 42 of the Companies Act requires a special resolution for "
                  "every private placement of shares.")
    built = research_memo(ASK, prose=[
        {"text": "This note records the position on the annual general meeting.",
         "citation_ids": []},
        {"text": FABRICATED, "citation_ids": []},
    ])
    check(len(built.dropped) == 1, "a fabricated legal claim with no citation is DROPPED")
    check(built.dropped[0]["text"] == FABRICATED, "...and the dropped text is reported")
    check("no citation" in built.dropped[0]["reason"], "...with a reason saying why")
    check(FABRICATED not in built.body,
          "...and it is ABSENT from the body -- not present with a warning label")
    check(all(FABRICATED not in s.value for s in built.slots),
          "...and absent from every slot, so no surface can render it")
    check(any("records the position" in s.value for s in built.slots),
          "...while the connecting sentence beside it survives")
    check(built.to_dict()["dropped_count"] == 1,
          "...and to_dict carries the count, so a UI cannot omit the drop by accident")

    # A legal claim that DOES carry a real citation id is kept, as a suggestion.
    cited = research_memo(ASK, prose=[
        {"text": "The Act requires one such meeting in each year.",
         "citation_ids": ["c1"]}])
    check(not cited.dropped, "a legal claim citing a held citation id is not dropped")
    kept = [s for s in cited.slots if s.slot_type == MODEL_SUGGESTION]
    check(len(kept) == 1 and "cites c1" in kept[0].note,
          "...it is a MODEL_SUGGESTION and the id travels with it")
    check(bool(blocking_slots(cited.slots)),
          "...and it BLOCKS approval until a person accepts or edits it")

    # An id the run does not hold is worse than no id: it looks checkable.
    ghost = research_memo(ASK, prose=[
        {"text": "The company must file within 30 days.", "citation_ids": ["c9"]}])
    check(len(ghost.dropped) == 1 and "does not hold" in ghost.dropped[0]["reason"],
          "a legal claim citing an id the run does NOT hold is dropped too")
    # ...but a dangling id on ordinary prose only loses the reference.
    dangle = research_memo(ASK, prose=[
        {"text": "I have set out the position below.", "citation_ids": ["c9"]}])
    check(not dangle.dropped
          and [s.value for s in dangle.slots if s.slot_type == MODEL_SUGGESTION]
              == ["I have set out the position below."],
          "a dangling id on non-legal prose keeps the sentence")
    check("c9" not in (dangle.slots[-1].note or ""),
          "...and drops the reference, so no footnote marker points at nothing")

    # ── law comes from the run's citations, verbatim ────────────────────────
    memo = research_memo(ASK)
    quotes = [s for s in memo.slots if s.slot_type == SOURCE_QUOTE]
    check(len(quotes) == 1 and quotes[0].value == CIT["quote"],
          "each citation becomes a SOURCE_QUOTE holding the quote VERBATIM")
    check("s.96(1)" in quotes[0].source and "[c1]" in quotes[0].source,
          "...carrying the provision and the citation id")
    check(CIT["quote"] in memo.body, "...and the quote reaches the body")
    check(memo.citations == ("Companies Act 2013 s.96(1) [c1]",),
          "...and the legal basis is listed")
    check(ready_for_approval(memo.slots),
          "a memo of quotes and template text alone is approvable")
    check(not ready_for_approval(memo.slots + tuple(
        Slot("p", "The company must do this.", MODEL_SUGGESTION) for _ in (1,))),
          "...and one model sentence makes it not approvable")

    no_cite = research_memo({"question": "Does the LLP Act require this?", "citations": []})
    check(not [s for s in no_cite.slots if s.slot_type == SOURCE_QUOTE],
          "an answer with no citations yields no SOURCE_QUOTE")
    check("states no law" in no_cite.body,
          "...and the memo SAYS it states no law rather than leaving a blank page")
    quoteless = research_memo({"question": "q", "citations": [
        {"id": "c2", "provision": "s.1", "quote": ""}]})
    check(not [s for s in quoteless.slots if s.slot_type == SOURCE_QUOTE],
          "a citation with no quote cannot become a SOURCE_QUOTE")
    anon = research_memo({"citations": [CIT]})
    check(any(s.slot_type == UNKNOWN for s in anon.slots),
          "a run with no recorded question marks that slot UNKNOWN, which blocks")

    # ── the client email states no law, and says so ─────────────────────────
    REVIEW = {"run_id": "r1", "playbook_status": "APPLIED",
              "findings": [
                  {"rule_id": "NDA-01", "clause": "Term", "status": "MISSING",
                   "kind": "POTENTIAL_ISSUE",
                   "detail": "the standard expects this clause and none was extracted",
                   "standard_text": "Confidentiality lasts no more than 3 years."},
                  {"rule_id": "NDA-02", "clause": "Governing law", "status": "PRESENT",
                   "kind": "INFORMATIONAL", "detail": "matches the standard"},
              ],
              "law_not_held": [{"body": "CONTRACT1872", "refusal": "not held"},
                               {"body": "STAMP", "refusal": "not held"}]}
    email = client_email(REVIEW)
    check(not [s for s in email.slots if s.slot_type == SOURCE_QUOTE],
          "a contract-review email contains NO statement of law...")
    check("not statements of law" in email.body,
          "...and says so in the draft itself, not in a covering note")
    check("CONTRACT1872" in email.body and "STAMP" in email.body,
          "...naming the bodies it cannot speak for, from law_not_held")
    check("1 clause(s) differ" in email.body,
          "only POTENTIAL_ISSUE findings are reported as differences")
    check(not any("matches the standard" in s.value for s in email.slots),
          "...an INFORMATIONAL finding is not dressed up as an issue")
    issue = [s for s in email.slots if s.name == "issue_1"][0]
    check(issue.slot_type == TEMPLATE_TEXT and issue.source == "NDA-01",
          "a finding is TEMPLATE_TEXT sourced to its playbook rule")
    check("3 years" in issue.note, "...and the standard's own words are in the note")
    check(ready_for_approval(email.slots),
          "an email built only from findings is approvable with no model text")
    clean = client_email({"findings": [], "law_not_held": []})
    check("No clause" in clean.body and "differs from the standard on the checks that ran"
          in clean.body,
          "a clean contract says which checks ran, not that the contract is fine")

    # The same drop rule applies to the email -- it is not special-cased.
    email2 = client_email(REVIEW, prose=[
        {"text": "Clause 4 is void for want of consideration.", "citation_ids": []}])
    check(len(email2.dropped) == 1,
          "the drop rule is the SAME in the email: an uncited legal claim goes")

    # ── build() and errors ──────────────────────────────────────────────────
    check(build("research_memo", ASK).title.startswith("Memo"), "build dispatches")
    check((build("research_memo", ASK).kind, build("client_email", REVIEW).kind)
          == ("research_memo", "client_email"),
          "...and each Built names the template that made it, which becomes draft.kind")
    try:
        build("nice_email", ASK)
        check(False, "an unknown template raises")
    except TemplateError:
        check(True, "an unknown template raises TemplateError, never a default template")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
