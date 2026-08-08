"""
The gate. Nothing reaches a user without passing through here.

The spec's `should_abstain()` flags hedging words — "I believe", "I think", "probably". That
catches an anxious answer, not a wrong one: a confidently-worded fabricated deadline sails
straight past it. We keep the phrase list as a weak signal and make the real gate mechanical —

    **every number in the answer must appear verbatim in the retrieved source text.**

That check is the one that would have caught the fabricated s.4 quotation that three separate
generated specs propagated. It does not depend on the model being careful.

Pure functions, no I/O. Run: python3 checker/verifier.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Confidence = Literal["answer", "abstain"]

SUPPORTED_STATES = {"IN-KA", "IN-MH", "IN-DL", "IN-TG", "IN-TN", "IN-HR"}

# Weak signal, kept from the spec. Not the gate.
HEDGES = ("i believe", "i think", "probably", "might be", "i'd guess", "presumably")

# Out of scope by design — arithmetic is where a wrong answer is instantly expensive,
# and `docs/03` puts the calculation agent last for exactly this reason.
CALCULATION = ("calculate", "how much pf", "gratuity amount", "salary breakup",
               "ctc breakup", "how much will i pay", "compute")

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_CITE = re.compile(r"\bs\.\s?\d+[A-Za-z0-9()\/]*", re.I)
# Years and small ordinals appear in prose ("the 2013 Act", "three years") without being
# claims about quantities. Section numbers are checked separately, by resolution.
_BENIGN = {"2013", "1", "2", "3", "4"}


@dataclass(frozen=True)
class Verdict:
    confidence: Confidence
    reason: str
    unsupported_numbers: list[str]
    unresolved_citations: list[str]

    @property
    def abstained(self) -> bool:
        return self.confidence == "abstain"


def _source_text(provisions: list[dict]) -> str:
    return " ".join(
        (p.get("text_display") or p.get("text", "")) for p in provisions
    )


def check_hallucination(answer: str, provisions: list[dict]) -> list[str]:
    """Numbers asserted in the answer that do not appear in the source. Empty is the only pass."""
    src = _source_text(provisions)
    src_nums = {n.replace(",", "") for n in _NUM.findall(src)}
    out: list[str] = []
    for raw in _NUM.findall(answer):
        n = raw.replace(",", "")
        if n in _BENIGN or n in src_nums:
            continue
        # "fifty thousand" in the source, "50,000" in the answer is a real mismatch to surface —
        # we cannot confirm it from the text, so it does not get a free pass.
        out.append(raw)
    return sorted(set(out))


def verify_citations(answer: str, provisions: list[dict]) -> list[str]:
    """Citations in the answer that do not resolve to a retrieved provision."""
    have = {p.get("citation", "").lower().replace(" ", "") for p in provisions}
    unresolved: list[str] = []
    for c in _CITE.findall(answer):
        norm = c.lower().replace(" ", "")
        base = norm.split("(")[0]
        if not any(h.startswith(base) for h in have if h):
            unresolved.append(c)
    return sorted(set(unresolved))


def should_abstain(question: str, provisions: list[dict], answer: str | None,
                   *, state: str = "") -> Verdict:
    """
    Runs twice: once before the LLM (answer=None) and once on its output.

    The pre-LLM pass is what makes this cheap — an abstention decided before the call costs ₹0,
    which is why the engine currently spends nothing at all.
    """
    q = question.lower()

    if any(k in q for k in CALCULATION):
        return Verdict("abstain",
                       "We don't do payroll arithmetic. A wrong number there is instantly "
                       "expensive, so we'd rather send you to your CA than guess.", [], [])

    if state and state not in SUPPORTED_STATES:
        return Verdict("abstain",
                       f"We haven't ingested the rules for {state} yet. We only answer where "
                       f"we hold the text.", [], [])

    if not provisions:
        return Verdict("abstain",
                       "We don't have verified information on this yet. Every question we "
                       "can't answer tells us which part of the law to read next.", [], [])

    unverified = [p for p in provisions if not p.get("verified_by")]
    if unverified:
        cites = ", ".join(sorted({p.get("citation", "?") for p in unverified})[:4])
        return Verdict("abstain",
                       f"We hold the text for {cites}, but no lawyer has verified our reading "
                       f"of it yet — so we won't state it as an answer. This is the honest "
                       f"state of the corpus, not a bug.", [], [])

    if answer is None:                       # pre-flight passed; the caller may now spend
        return Verdict("answer", "evidence packet is verified and complete", [], [])

    bad_nums = check_hallucination(answer, provisions)
    bad_cites = verify_citations(answer, provisions)
    if bad_nums or bad_cites:
        return Verdict("abstain",
                       "Our own check rejected the drafted answer before you saw it.",
                       bad_nums, bad_cites)

    if any(h in answer.lower() for h in HEDGES):
        return Verdict("abstain",
                       "The drafted answer hedged, which means it wasn't grounded in the text.",
                       [], [])

    return Verdict("answer", "verified against source", [], [])


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    verified = [{"citation": "s.4(1)", "text_display":
                 "Every employer of a workplace shall, by an order in writing, constitute a "
                 "Committee to be known as the Internal Complaints Committee",
                 "verified_by": "Adv. Test"}]
    unverified = [{**verified[0], "verified_by": None}]

    cases = [
        ("no provisions → abstain",
         should_abstain("do I need an IC?", [], None).abstained, True),
        ("unverified corpus → abstain (this is us, today)",
         should_abstain("do I need an IC?", unverified, None).abstained, True),
        ("verified + no answer yet → clear to spend",
         should_abstain("do I need an IC?", verified, None).abstained, False),
        ("payroll arithmetic → abstain",
         should_abstain("calculate my PF liability", verified, None).abstained, True),
        ("unsupported state → abstain",
         should_abstain("do I need an IC?", verified, None, state="IN-XX").abstained, True),
        ("grounded answer passes",
         should_abstain("do I need an IC?", verified,
                        "Yes. Every employer of a workplace shall constitute a Committee "
                        "[s.4(1)].").abstained, False),
        ("fabricated number → abstain",
         should_abstain("do I need an IC?", verified,
                        "You need one at 10 or more employees [s.4(1)].").abstained, True),
        ("unresolvable citation → abstain",
         should_abstain("do I need an IC?", verified,
                        "You must display the notice [s.19].").abstained, True),
        ("hedging → abstain",
         should_abstain("do I need an IC?", verified,
                        "I think you probably need a Committee [s.4(1)].").abstained, True),
    ]

    failures = 0
    for name, got, want in cases:
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    v = should_abstain("do I need an IC?", verified,
                       "You need one at 10 or more employees by 31 January [s.4(1)].")
    caught = v.unsupported_numbers
    ok = "10" not in _BENIGN and set(caught) >= {"10", "31"}
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] names the fabricated figures: {caught}")

    total = len(cases) + 1
    print(f"\n{total - failures}/{total} passed")
    raise SystemExit(1 if failures else 0)
