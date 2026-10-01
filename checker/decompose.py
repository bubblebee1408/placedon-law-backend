#!/usr/bin/env python3
"""Split a compound question into at most four, answer each, and join only what was cited.

PLAN_23 O5: "No run exceeds 4 sub-questions." The bound is the feature. A decomposer that
can ask as many questions as it likes is a decomposer that can spend without limit and
produce a synthesis nobody can check, and the failure mode is not a crash -- it is a long,
fluent answer assembled from parts that were never individually verified.

## What is bounded, and what is not

    the COUNT        fixed at 4, in code, not configurable -- MAX_SUBQUESTIONS
    the DEPTH        one level. A sub-question is never itself decomposed.
    the CONTENT      not bounded here: a model proposes the splits, and `plan()` keeps
                     the first four it proposes, in order.

A model may PICK the splits and may never INVENT the answers, which is the same division
`agents/plans.py` draws between choosing a step and writing one.

## Synthesis uses verified cited claims and nothing else

A part contributes to the joined answer only when it came back ANSWERED **and carries at
least one citation**. An uncited sub-answer is dropped from the synthesis and NAMED in
`unsupported` -- it is not quietly folded in, because a sentence with no citation reads
exactly like one with a citation once they are in the same paragraph. That is the whole
risk of synthesis and the reason this module exists rather than a string join.

## One failed part makes the whole PARTIAL, and says which

Never silently dropped, and never promoted to ANSWERED by the others succeeding. A lawyer
reading four joined paragraphs cannot tell that a fifth question went unanswered unless we
say so, and "we could not answer part 3" is a different fact from "part 3 has no answer".

    every part answered and cited     ANSWERED
    some answered, some not           PARTIAL, with every gap named
    none answered                     ABSTAINED, with every gap named

Run: PYTHONPATH=. python3 checker/decompose.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["MAX_SUBQUESTIONS", "plan", "Part", "synthesise", "ANSWERED", "PARTIAL",
           "ABSTAINED", "DecomposeError"]

# PLAN_23 O5. In code, not in config: a bound that can be raised by an environment
# variable is not a bound, it is a default.
MAX_SUBQUESTIONS = 4

ANSWERED = "ANSWERED"
PARTIAL = "PARTIAL"
ABSTAINED = "ABSTAINED"


class DecomposeError(ValueError):
    """A decomposition that cannot be formed. Never a silent fallback to one question."""


def plan(question: str, *, propose) -> tuple[str, ...]:
    """The sub-questions to run, in order, at most MAX_SUBQUESTIONS of them.

    `propose(question) -> [str]` is injected, so the gate runs this without a model and
    the bound is tested on its own. A proposal that is empty, or that only repeats the
    question, yields `(question,)`: the honest result of "this does not split" is one
    question, not zero and not a pretend split.

    Truncation is SILENT ONLY IN RETURN -- `plan` tells the caller nothing -- which is why
    `synthesise` records the count it was given and `agents/` reports it. The alternative,
    raising on a five-way proposal, would turn a model being slightly over-eager into a
    failed run.
    """
    q = str(question or "").strip()
    if not q:
        raise DecomposeError("there is no question to decompose")
    try:
        raw = list(propose(q) or [])
    except Exception as e:                                       # noqa: BLE001
        # A proposer that breaks costs us the SPLIT, not the question: the caller falls
        # back to asking it whole, which is what would have happened anyway.
        raw = []
    parts: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text.lower() == q.lower():
            continue
        if text.lower() in {p.lower() for p in parts}:
            continue                       # a repeat is not a second question
        parts.append(text)
        if len(parts) >= MAX_SUBQUESTIONS:
            break
    return tuple(parts) if parts else (q,)


@dataclass(frozen=True)
class Part:
    """One sub-question and what came back for it."""
    question: str
    status: str = ""
    answer: str = ""
    citations: tuple = ()
    failure: str = ""

    @property
    def usable(self) -> bool:
        """ANSWERED, and carrying at least one citation.

        Both halves are required. An ANSWERED part with no citation has nothing behind it,
        and once its sentence sits in a joined paragraph beside cited ones, no reader can
        tell which is which.
        """
        return self.status == ANSWERED and bool(self.citations)


@dataclass(frozen=True)
class Synthesis:
    status: str
    answer: str
    citations: tuple = ()
    parts: tuple = ()
    unanswered: tuple = ()        # (question, why) for each part that failed
    unsupported: tuple = ()       # answered, but cited nothing, so not used
    proposed: int = 0             # how many splits were proposed before the bound
    note: str = ""

    def to_dict(self) -> dict:
        return {"status": self.status, "answer": self.answer,
                "citations": [dict(c) for c in self.citations],
                "parts": [{"question": p.question, "status": p.status,
                           "answer": p.answer, "used": p.usable,
                           "citations": [dict(c) for c in p.citations],
                           "failure": p.failure} for p in self.parts],
                "unanswered": [{"question": q, "why": w} for q, w in self.unanswered],
                "unsupported": list(self.unsupported),
                "sub_questions": len(self.parts), "proposed": self.proposed,
                "bound": MAX_SUBQUESTIONS, "note": self.note}


def synthesise(parts, *, proposed: int = 0) -> Synthesis:
    """Join the parts that are usable, in the order they were asked.

    Order is preserved because the order was chosen: a decomposition is a reading plan,
    and reordering it would answer a different question from the one that was planned.
    """
    parts = tuple(parts or ())
    if not parts:
        raise DecomposeError("a synthesis needs at least one part; joining nothing would "
                             "produce an empty answer that reads as 'nothing applies'")
    used = [p for p in parts if p.usable]
    unanswered = tuple((p.question, p.failure or f"the sub-question came back {p.status or 'with no status'}")
                       for p in parts if p.status != ANSWERED)
    unsupported = tuple(p.question for p in parts
                        if p.status == ANSWERED and not p.citations)

    seen, citations = set(), []
    for p in used:
        for c in p.citations:
            cid = str((c or {}).get("id") or "")
            if cid and cid not in seen:
                seen.add(cid)
                citations.append(dict(c))
    body = "\n\n".join(f"{p.question}\n{p.answer}".strip() for p in used if p.answer.strip())

    if used and not unanswered and not unsupported:
        status = ANSWERED
        note = (f"Answered in {len(parts)} part(s), each cited and each verified on its "
                f"own.")
    elif used:
        status = PARTIAL
        bits = []
        if unanswered:
            bits.append(f"{len(unanswered)} sub-question(s) were NOT answered")
        if unsupported:
            bits.append(f"{len(unsupported)} were answered with no citation and are "
                        f"therefore not included")
        note = ("; ".join(bits)
                + ". They are listed, not folded in: an uncited sentence beside cited "
                  "ones cannot be told apart once they share a paragraph.")
    else:
        status = ABSTAINED
        note = ("No sub-question produced a cited answer, so there is nothing to join. "
                "This is not a finding that no obligation exists.")
    return Synthesis(status=status, answer=body, citations=tuple(citations), parts=parts,
                     unanswered=unanswered, unsupported=unsupported,
                     proposed=proposed or len(parts), note=note)


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

    print("decompose")
    Q = "What are the quorum, notice and minute requirements for a Board meeting?"
    C1 = {"id": "c1", "provision": "s.174", "quote": "one third or two directors"}
    C2 = {"id": "c2", "provision": "s.173(3)", "quote": "seven days' notice"}

    # ── the bound is the feature ───────────────────────────────────────────
    check(MAX_SUBQUESTIONS == 4, "the bound is four (PLAN_23 O5)")
    many = plan(Q, propose=lambda q: [f"sub {i}?" for i in range(1, 10)])
    check(len(many) == 4, f"nine proposed sub-questions become FOUR ({len(many)})")
    check(many == ("sub 1?", "sub 2?", "sub 3?", "sub 4?"),
          "...the FIRST four, in the order proposed -- a decomposition is a reading plan "
          "and reordering it answers a different question")
    check(plan(Q, propose=lambda q: ["a?", "b?"]) == ("a?", "b?"),
          "fewer than four are left alone")
    check(plan(Q, propose=lambda q: []) == (Q,),
          "a proposer that splits NOTHING yields the original question, not zero")
    check(plan(Q, propose=lambda q: [Q]) == (Q,),
          "...and a 'split' that only repeats the question is not a split")
    check(plan(Q, propose=lambda q: ["a?", "A?", "a?"]) == ("a?",),
          "a repeated sub-question is not a second one")

    def boom(q):
        raise TimeoutError("the proposer did not answer")

    check(plan(Q, propose=boom) == (Q,),
          "a proposer that RAISES costs the split, not the question: it falls back to "
          "asking it whole, which is what would have happened without O5 at all")
    try:
        plan("   ", propose=lambda q: ["a?"])
        check(False, "an empty question raises")
    except DecomposeError:
        check(True, "an empty question raises rather than decomposing nothing")
    check(len(plan(Q, propose=lambda q: ["x?"] * 9)) == 1,
          "nine identical proposals are one sub-question, not four copies")

    # ── one level only ─────────────────────────────────────────────────────
    nested = plan(Q, propose=lambda q: ["a?", "b?"])
    check(all(isinstance(p, str) for p in nested),
          "a sub-question is a STRING and is never itself decomposed: the depth is one, "
          "so four is the whole budget and not four per level")

    # ── synthesis: only verified cited claims ──────────────────────────────
    good = [Part("Quorum?", ANSWERED, "One third or two.", (C1,)),
            Part("Notice?", ANSWERED, "Seven days.", (C2,))]
    s = synthesise(good)
    check(s.status == ANSWERED, f"every part answered and cited is ANSWERED ({s.status})")
    check(s.answer.index("Quorum?") < s.answer.index("Notice?"),
          "...joined in the ORDER they were asked")
    check([c["id"] for c in s.citations] == ["c1", "c2"],
          "...and every citation is carried through, de-duplicated and in order")
    dup = synthesise([Part("a?", ANSWERED, "x", (C1,)), Part("b?", ANSWERED, "y", (C1,))])
    check([c["id"] for c in dup.citations] == ["c1"],
          "...one provision cited by two parts appears ONCE")

    # THE RULE: an uncited sub-answer is dropped and named.
    mixed = [Part("Quorum?", ANSWERED, "One third or two.", (C1,)),
             Part("Minutes?", ANSWERED, "Thirty days, I think.", ())]
    m = synthesise(mixed)
    check(m.status == PARTIAL,
          f"an ANSWERED part with NO CITATION makes the whole PARTIAL ({m.status})")
    check("Thirty days" not in m.answer,
          "...its sentence is NOT in the joined answer: beside cited sentences, nobody "
          "could tell which one had nothing behind it")
    check(m.unsupported == ("Minutes?",),
          f"...and it is NAMED in unsupported, never silently dropped ({m.unsupported})")
    check(not [p for p in m.parts if p.question == "Minutes?"][0].usable,
          "...and the part itself reports that it was not used")

    # THE RULE: a failed sub-question makes it PARTIAL and is named.
    failed = [Part("Quorum?", ANSWERED, "One third or two.", (C1,)),
              Part("Stamp duty?", "REFUSED", "", (), "STAMP is declared and not held")]
    f = synthesise(failed)
    check(f.status == PARTIAL, f"one failed sub-question makes the whole PARTIAL ({f.status})")
    check(f.unanswered and f.unanswered[0][0] == "Stamp duty?",
          "...and the failed sub-question is NAMED")
    check("declared and not held" in f.unanswered[0][1],
          f"...with the reason it failed, which is the part a lawyer acts on "
          f"({f.unanswered[0][1][:40]!r})")
    check("One third" in f.answer and "Stamp duty" not in f.answer,
          "...while the part that did answer is still served")
    check(f.status != ANSWERED,
          "...and three successes NEVER promote the run to ANSWERED: a reader of joined "
          "paragraphs cannot see the question that went unanswered unless we say so")

    none = synthesise([Part("a?", "REFUSED", "", (), "not held"),
                       Part("b?", "FAILED", "", (), "transport")])
    check(none.status == ABSTAINED,
          f"no cited answer at all is ABSTAINED, not an empty ANSWERED ({none.status})")
    check("not a finding that no obligation exists" in none.note,
          "...and says so, because an empty answer reads as 'nothing applies'")
    check(len(none.unanswered) == 2, "...with both gaps named")
    try:
        synthesise([])
        check(False, "synthesising nothing raises")
    except DecomposeError:
        check(True, "synthesising NO parts raises: an empty join would read as a finding")

    d = synthesise(good, proposed=7).to_dict()
    check(d["bound"] == 4 and d["proposed"] == 7 and d["sub_questions"] == 2,
          f"to_dict reports the bound, what was proposed and what ran ({d['proposed']} "
          f"proposed, {d['sub_questions']} ran)")
    check(all("used" in p for p in d["parts"]),
          "...and every part says whether it was used in the synthesis")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
