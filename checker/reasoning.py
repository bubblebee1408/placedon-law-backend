"""The model contract: what a model may propose, and what happens when it doesn't.

Layer 1. Every other layer of this system is deterministic; this is the boundary
where something probabilistic is allowed to speak, and the only place it is.

## The contract

MAY propose:
  * an intent -- which declared capability this request wants
  * facts, each with the verbatim span it was read from
  * narration -- phrasing of results that have ALREADY been verified

MAY NOT:
  * decide whether a law applies
  * supply a date, a figure or a citation that is not in the verified material
  * name a capability the registry does not declare
  * assert a conclusion the deterministic layer did not reach

## Why this is a module and not a prompt

`model_adapter.py` puts it plainly: a prompt is not a safety mechanism. A prompt
is a request; this is a check that runs on what came back. The distinction matters
because the measured failure rates are not small -- the safest tool-using agent in
a published evaluation still failed 23.9% of the time, production legal-RAG tools
hallucinate 17-33%, and models cannot reliably tell when they are doing it.

So the design target is not "the model does not err". That is unachievable and
claiming it is how vendors get embarrassed. The target is:

    **No model error reaches the user as an assertion.**

Every violation below either refuses or is dropped, and the accepted result
contains ONLY what survived. Partial acceptance is the point: a proposal with one
good fact and one invented one yields the good fact and a named refusal, never
both and never neither.

## What each check actually catches, honestly

  * Ungrounded facts, invented dates, invented figures, invented citations:
    caught precisely, because each is a lexical comparison against material we
    hold.
  * Asserted conclusions: caught by pattern, which is narrower. A model that
    invents a NOVEL way to phrase "this company is compliant" can evade it. That
    is a real limit, and it is why narration is the LAST thing to be wired and
    runs in shadow mode first -- not a gap to paper over here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# ── violations ────────────────────────────────────────────────────────────────
INTENT_NOT_DECLARED = "INTENT_NOT_DECLARED"
FACT_WITHOUT_SPAN = "FACT_WITHOUT_SPAN"
FACT_NOT_GROUNDED = "FACT_NOT_GROUNDED"
DATE_INVENTED = "DATE_INVENTED"
FIGURE_INVENTED = "FIGURE_INVENTED"
CITATION_OUTSIDE_PACK = "CITATION_OUTSIDE_PACK"
CONCLUSION_ASSERTED = "CONCLUSION_ASSERTED"

VIOLATIONS = (INTENT_NOT_DECLARED, FACT_WITHOUT_SPAN, FACT_NOT_GROUNDED,
              DATE_INVENTED, FIGURE_INVENTED, CITATION_OUTSIDE_PACK,
              CONCLUSION_ASSERTED)


@dataclass(frozen=True)
class Refusal:
    violation: str
    detail: str
    offending: str = ""


@dataclass(frozen=True)
class Proposal:
    """Everything a model is permitted to put forward, and nothing else."""
    intent: str | None = None
    facts: dict = field(default_factory=dict)      # name -> {"value","span"}
    narration: str | None = None
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Review:
    """What survived, and what was refused. Never one without the other."""
    intent: str | None
    facts: dict
    narration: str | None
    citations: tuple[str, ...]
    refusals: tuple[Refusal, ...]

    @property
    def clean(self) -> bool:
        return not self.refusals

    def refused(self, violation: str) -> tuple[Refusal, ...]:
        return tuple(r for r in self.refusals if r.violation == violation)


# ── detectors ─────────────────────────────────────────────────────────────────
_DATE_TOKENS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b"),
    re.compile(r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+\d{4}\b", re.I),
)
# A rupee amount, in digits or in the crore/lakh idiom.
_FIGURE = re.compile(
    r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?(?:\s*(?:crore|crores|lakh|lakhs))?"
    r"|\b[\d,]+(?:\.\d+)?\s*(?:crore|crores|lakh|lakhs)\b", re.I)
# s.96, s.2(85), section 188, G.S.R. 880(E)
_CITATION = re.compile(
    r"\bs\.\s*\d{1,3}[A-Z]{0,2}(?:\(\d{1,2}\))?|\bsection\s+\d{1,3}[A-Z]{0,2}\b"
    r"|\bG\.?\s*S\.?\s*R\.?\s*\d{1,4}\s*\(\s*E\s*\)", re.I)

# Phrases that assert a legal conclusion. Only the deterministic layer may reach
# one; a model repeating a verdict it was GIVEN is fine, which is why each is
# checked against the verified text rather than banned outright.
_CONCLUSIONS = (
    re.compile(r"\bis (?:a |not a )?small compan(?:y|ies)\b", re.I),
    re.compile(r"\b(?:does not apply|is not applicable|applies to)\b", re.I),
    re.compile(r"\bis (?:in )?complian(?:t|ce)\b", re.I),
    re.compile(r"\bis in breach\b", re.I),
    re.compile(r"\b(?:must|is required to) (?:appoint|hold|file|constitute)\b", re.I),
    re.compile(r"\bno (?:breach|default) (?:was )?found\b", re.I),
)


def _norm(t: str) -> str:
    return " ".join(t.split()).lower()


def _tokens(text: str, patterns) -> list[str]:
    out: list[str] = []
    for p in (patterns if isinstance(patterns, tuple) else (patterns,)):
        out += [m.group(0) for m in p.finditer(text)]
    return out


# ── the review ────────────────────────────────────────────────────────────────
def review(proposal: Proposal, *, declared_intents: tuple[str, ...],
           document: str = "", pack_ids: tuple[str, ...] = (),
           verified_text: str = "") -> Review:
    """Check a proposal against what we hold. Drops what fails; names why.

    `verified_text` is the deterministic layer's own output -- the only material
    narration may draw a date, a figure, a citation or a conclusion from.
    """
    refusals: list[Refusal] = []
    vnorm = _norm(verified_text)
    dnorm = _norm(document)

    # 1. intent must be declared. No nearest match -- see bundles.route().
    intent = proposal.intent
    if intent is not None and intent not in declared_intents:
        refusals.append(Refusal(
            INTENT_NOT_DECLARED,
            f"no bundle declares {intent!r}; a model may name a capability, never "
            f"widen the set. Declared: {', '.join(declared_intents) or '(none)'}",
            intent))
        intent = None

    # 2/3. every fact must quote itself, and the quote must be in the document.
    facts: dict = {}
    for name, item in (proposal.facts or {}).items():
        if not isinstance(item, dict) or "span" not in item:
            refusals.append(Refusal(
                FACT_WITHOUT_SPAN,
                f"{name}: proposed without the span it was read from; a value that "
                f"does not quote its source cannot be checked", name))
            continue
        span = item.get("span") or ""
        if not span.strip() or _norm(span) not in dnorm:
            refusals.append(Refusal(
                FACT_NOT_GROUNDED,
                f"{name}: the quoted span is not in the document", span[:60]))
            continue
        facts[name] = item

    # 4/5/6. narration may not introduce a date, a figure or a citation that is
    # not already in the verified material. These are the failures with teeth:
    # an invented figure or citation is exactly what a reader cannot check.
    narration = proposal.narration
    if narration:
        for tok in _tokens(narration, _DATE_TOKENS):
            if _norm(tok) not in vnorm:
                refusals.append(Refusal(
                    DATE_INVENTED,
                    f"narration states a date absent from the verified result: {tok}. "
                    f"A model never supplies a date", tok))
        for tok in _tokens(narration, _FIGURE):
            if _norm(tok) not in vnorm:
                refusals.append(Refusal(
                    FIGURE_INVENTED,
                    f"narration states a figure absent from the verified result: "
                    f"{tok}", tok))
        for tok in _tokens(narration, _CITATION):
            if _norm(tok) not in vnorm:
                refusals.append(Refusal(
                    CITATION_OUTSIDE_PACK,
                    f"narration cites {tok}, which the verified result does not. "
                    f"Rejected, not repaired", tok))
        # 7. a conclusion the deterministic layer did not reach
        for pat in _CONCLUSIONS:
            m = pat.search(narration)
            if m and _norm(m.group(0)) not in vnorm:
                refusals.append(Refusal(
                    CONCLUSION_ASSERTED,
                    f"narration asserts a legal conclusion the system did not reach: "
                    f"{m.group(0)!r}. A model phrases verified results; it does not "
                    f"decide", m.group(0)))
        if any(r.violation in (DATE_INVENTED, FIGURE_INVENTED,
                               CITATION_OUTSIDE_PACK, CONCLUSION_ASSERTED)
               for r in refusals):
            narration = None          # dropped whole; a half-trusted sentence is worse

    # 6b. explicit citations must be in the pack.
    cites: list[str] = []
    for c in proposal.citations or ():
        if c not in pack_ids:
            refusals.append(Refusal(
                CITATION_OUTSIDE_PACK,
                f"cited evidence id {c!r} is not in the pack. A citation to something "
                f"absent is the signature of a fabricated one", c))
            continue
        cites.append(c)

    return Review(intent, facts, narration, tuple(cites), tuple(refusals))


# ── the deliberately misbehaving model ────────────────────────────────────────
def misbehaving_model(violation: str) -> Proposal:
    """A stub that commits exactly one violation. The contract's real test.

    Written before anything was wired to a real model, because a contract nobody
    has attacked is a hope. Each proposal below is what a plausible-looking bad
    output actually looks like -- not gibberish, which any check would catch.
    """
    ok_fact = {"value": "private", "span": "is a private company"}
    if violation == INTENT_NOT_DECLARED:
        return Proposal(intent="document.review_contract", facts={"company_class": ok_fact})
    if violation == FACT_WITHOUT_SPAN:
        return Proposal(facts={"company_class": "private"})
    if violation == FACT_NOT_GROUNDED:
        return Proposal(facts={"paid_up_capital_rupees":
                               {"value": 40000000, "span": "capital is Rs. 4,00,00,000"}})
    if violation == DATE_INVENTED:
        return Proposal(narration="The AGM was held on 2024-09-30.")
    if violation == FIGURE_INVENTED:
        return Proposal(narration="The paid-up capital limit is Rs. 4 crore.")
    if violation == CITATION_OUTSIDE_PACK:
        return Proposal(narration="This follows from s.149(3).")
    if violation == CONCLUSION_ASSERTED:
        return Proposal(narration="On these facts the company is a small company.")
    raise ValueError(f"no stub for {violation!r}")


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

    print("reasoning")
    from checker.bundles import capabilities

    DOC = ("The Company is a private company incorporated on 2015-04-01. Its paid up "
           "share capital is Rs. 6,00,00,000.")
    VERIFIED = ("CA13-S2-85-SMALL CANNOT_DETERMINE — the prescribed limit in force on "
                "2026-09-10 is set by G.S.R. 880(E). s.2(85).")
    PACK = ("E1", "E2")
    INTENTS = capabilities()

    # ── every violation is caught, one at a time ─────────────────────────────
    for v in VIOLATIONS:
        r = review(misbehaving_model(v), declared_intents=INTENTS,
                   document=DOC, pack_ids=PACK, verified_text=VERIFIED)
        check(bool(r.refused(v)),
              f"{v} is caught ({[x.violation for x in r.refusals] or 'nothing refused'})")

    # ── and each refusal explains itself ─────────────────────────────────────
    r_int = review(misbehaving_model(INTENT_NOT_DECLARED), declared_intents=INTENTS,
                   document=DOC, pack_ids=PACK, verified_text=VERIFIED)
    check("never widen the set" in r_int.refusals[0].detail,
          "...the intent refusal states the rule it enforces")
    check(r_int.intent is None, "...and the undeclared intent is dropped, not passed on")
    check("company_class" in r_int.facts,
          "...while the good fact in the same proposal survives — partial acceptance")

    # ── a clean proposal passes whole ────────────────────────────────────────
    good = Proposal(
        intent=INTENTS[0],
        facts={"company_class": {"value": "private", "span": "is a private company"},
               "incorporation_date": {"value": "2015-04-01",
                                      "span": "incorporated on 2015-04-01"}},
        narration="s.2(85) could not be determined; G.S.R. 880(E) governs it.",
        citations=("E1",))
    rg = review(good, declared_intents=INTENTS, document=DOC, pack_ids=PACK,
                verified_text=VERIFIED)
    check(rg.clean, f"a proposal within the contract passes whole ({rg.refusals})")
    check(rg.narration is not None and len(rg.facts) == 2 and rg.citations == ("E1",),
          "...with its intent, facts, narration and citations intact")

    # ── narration is dropped WHOLE, never half-trusted ───────────────────────
    mixed = Proposal(narration="s.2(85) could not be determined. The limit is Rs. 4 crore.")
    rm = review(mixed, declared_intents=INTENTS, document=DOC, pack_ids=PACK,
                verified_text=VERIFIED)
    check(rm.narration is None,
          "a sentence with one invented figure drops the WHOLE narration")

    # ── a model REPEATING a verdict it was given is fine ─────────────────────
    v2 = VERIFIED + " The company is a small company."
    rr = review(Proposal(narration="On these facts the company is a small company."),
                declared_intents=INTENTS, document=DOC, pack_ids=PACK, verified_text=v2)
    check(rr.clean,
          "a conclusion the deterministic layer DID reach may be repeated")

    # ── boundary cases the checks must not fire on ───────────────────────────
    rq = review(Proposal(narration="The position could not be established."),
                declared_intents=INTENTS, document=DOC, pack_ids=PACK,
                verified_text=VERIFIED)
    check(rq.clean, "ordinary prose with no dates, figures or citations passes")

    # a date PRESENT in the verified result is fine
    rd = review(Proposal(narration="As at 2026-09-10 the basis is G.S.R. 880(E)."),
                declared_intents=INTENTS, document=DOC, pack_ids=PACK,
                verified_text=VERIFIED)
    check(rd.clean, "a date and citation drawn FROM the verified result pass")

    # ── the stub itself must be plausible, not gibberish ─────────────────────
    check(all(isinstance(misbehaving_model(v), Proposal) for v in VIOLATIONS),
          "a stub exists for every violation")
    check("Rs. 4 crore" in (misbehaving_model(FIGURE_INVENTED).narration or ""),
          "...and the figure stub proposes the SUPERSEDED figure — the realistic "
          "error, not a random number")

    # ── MUTATION: each check must be the thing doing the catching ────────────
    # A test suite where every stub is refused proves nothing on its own -- the
    # refusals could come from an unrelated path. Disable one detector at a time
    # and confirm its violation walks straight through.
    # sys.modules[__name__], NOT `import checker.reasoning` -- run as a script this
    # module is __main__, and importing it by name patches a SECOND copy while
    # review() goes on reading the first. That is the third time this trap has been
    # hit in this repo; it is silent, and it makes a mutation test pass by doing
    # nothing at all.
    import sys as _sys
    _self = _sys.modules[__name__]

    held = _self._CONCLUSIONS
    _self._CONCLUSIONS = ()
    r_mut = review(misbehaving_model(CONCLUSION_ASSERTED), declared_intents=INTENTS,
                   document=DOC, pack_ids=PACK, verified_text=VERIFIED)
    _self._CONCLUSIONS = held
    check(not r_mut.refused(CONCLUSION_ASSERTED),
          "with the conclusion patterns emptied, the assertion gets through — so it "
          "is those patterns catching it, not something incidental")
    check(bool(review(misbehaving_model(CONCLUSION_ASSERTED), declared_intents=INTENTS,
                      document=DOC, pack_ids=PACK,
                      verified_text=VERIFIED).refused(CONCLUSION_ASSERTED)),
          "...and restoring them catches it again")

    held_f = _self._FIGURE
    _self._FIGURE = re.compile(r"(?!x)x")            # matches nothing
    r_mut2 = review(misbehaving_model(FIGURE_INVENTED), declared_intents=INTENTS,
                    document=DOC, pack_ids=PACK, verified_text=VERIFIED)
    _self._FIGURE = held_f
    check(not r_mut2.refused(FIGURE_INVENTED),
          "with the figure detector disabled, the invented Rs 4 crore gets through")
    check(r_mut2.narration is not None,
          "...and the narration survives — which is exactly the failure mode: a "
          "confident sentence carrying a superseded figure")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
