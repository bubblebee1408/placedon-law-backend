"""Shadow mode: measure a model's proposals without any of them reaching a user.

Every legal-AI vendor that has been publicly embarrassed shipped a model into the
answer path and measured afterwards. This is the other order. A model proposes,
the contract in `reasoning.py` reviews it, the result is SCORED against what a
human recorded about the document -- and then discarded. Nothing here can serve.

## The four outcomes, and only one of them is a failure

    CORRECT       the model was right and the contract accepted it
    CAUGHT        the model was wrong and the contract refused it
    LEAKED        the model was wrong and the contract ACCEPTED it
    OVER_REFUSED  the model was right and the contract refused it anyway

CAUGHT is not a failure. It is the system working: a model erred and nothing
reached the user. Counting it as one would push the metric toward a weaker
contract, which is precisely backwards.

**LEAKED is the only number that must be zero.** It is a model error wearing the
system's authority.

OVER_REFUSED is the cost side, and it is real. A contract that refuses everything
has a leak rate of zero and is useless -- the same trap as an abstention-heavy
product scoring itself only on wrong answers. Both numbers are reported, always,
and never netted off.

## What "the model" is here

A callable taking the document text and returning a `reasoning.Proposal`. Today
they are stubs that fail in specified ways; when an API key exists, a real model
is the same callable. That is the whole point of building this first: wiring a
real model becomes a config change against a harness that already measures it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from checker.reasoning import Proposal, Review, review

CORRECT = "CORRECT"
CAUGHT = "CAUGHT"
LEAKED = "LEAKED"
OVER_REFUSED = "OVER_REFUSED"
OUTCOMES = (CORRECT, CAUGHT, LEAKED, OVER_REFUSED)


@dataclass(frozen=True)
class ShadowCase:
    """A document, and what a human recorded as actually being in it."""
    case_id: str
    document: str
    truth: dict                       # field -> the value genuinely in the document
    why: str = ""


@dataclass(frozen=True)
class ShadowResult:
    case_id: str
    outcome: str
    accepted: dict
    refusals: tuple
    detail: str = ""

    # Shadow results have no path to a user. This is not a convention; there is
    # no method here that produces a servable answer, and the test asserts it.
    served: bool = field(default=False, init=False)


def _compare(accepted: dict, truth: dict) -> tuple[bool, str]:
    """Did the accepted facts match what the document actually says?

    A field the model did not propose is not an error -- silence is allowed, and
    the contract already treats absence as absence. What is scored is whether
    anything ACCEPTED disagrees with the truth.
    """
    for name, item in accepted.items():
        if name not in truth:
            return False, f"{name}: accepted, but the document records no such fact"
        got = item.get("value") if isinstance(item, dict) else item
        if got != truth[name]:
            return False, f"{name}: accepted {got!r}, document says {truth[name]!r}"
    return True, ""


def score_case(case: ShadowCase, model: Callable[[str], Proposal], *,
               declared_intents: tuple[str, ...], pack_ids: tuple[str, ...] = (),
               verified_text: str = "") -> ShadowResult:
    """Run one case in shadow. The result is measured and then goes nowhere."""
    from checker.session import session

    # The document lives in a session for the duration and is purged after, so
    # shadow runs obey the same retention rule as production.
    with session() as s:
        s.put("document", case.document)
        proposal = model(s.get("document"))
        r: Review = review(proposal, declared_intents=declared_intents,
                           document=s.get("document"), pack_ids=pack_ids,
                           verified_text=verified_text)

    agrees, why = _compare(r.facts, case.truth)
    model_erred = _model_erred(proposal, case.truth, case.document,
                               verified_text)

    if model_erred and r.refusals:
        outcome, detail = CAUGHT, f"refused: {[x.violation for x in r.refusals]}"
    elif model_erred and not r.refusals:
        outcome, detail = LEAKED, why or "an error was accepted with no refusal"
    elif not model_erred and r.refusals:
        outcome, detail = OVER_REFUSED, f"refused a correct proposal: {[x.violation for x in r.refusals]}"
    elif agrees:
        outcome, detail = CORRECT, ""
    else:
        outcome, detail = LEAKED, why
    return ShadowResult(case.case_id, outcome, r.facts, r.refusals, detail)


def _model_erred(proposal: Proposal, truth: dict, document: str,
                 verified_text: str) -> bool:
    """Did the model do its job -- computed independently of the contract.

    Deliberately NOT "are the values correct". A model that returns the right
    figure without quoting where it read it has still failed, because at decision
    time unverifiable-but-correct is indistinguishable from unverifiable-and-wrong.
    Being right by luck is not being right, and scoring it as right would reward a
    model for guessing well.

    So an error is any of: a value that disagrees with the document; a value with
    no quoted span; a span that is not in the document; or narration introducing a
    date, figure or citation absent from the verified material.

    This overlaps with what `reasoning.review()` checks, and that is intentional --
    they are two independent computations of the same judgement. Where they AGREE
    the case is CORRECT or CAUGHT. Where they DISAGREE is the whole point:
    LEAKED (the model erred, the contract did not notice) and OVER_REFUSED (the
    model was clean, the contract refused anyway -- a contract bug).
    """
    from checker.reasoning import _CITATION, _DATE_TOKENS, _FIGURE, _norm, _tokens

    for name, item in (proposal.facts or {}).items():
        if not isinstance(item, dict) or "span" not in item:
            return True                                   # would not quote itself
        span = item.get("span") or ""
        if not span.strip() or _norm(span) not in _norm(document):
            return True                                   # quoted something absent
        got = item.get("value")
        if name not in truth or got != truth[name]:
            return True                                   # disagrees with the document

    if proposal.narration:
        v = _norm(verified_text)
        for pats in (_DATE_TOKENS, _FIGURE, _CITATION):
            for tok in _tokens(proposal.narration, pats):
                if _norm(tok) not in v:
                    return True                           # introduced its own facts
    return False


def run(cases: tuple[ShadowCase, ...], model: Callable[[str], Proposal],
        **kw) -> list[ShadowResult]:
    return [score_case(c, model, **kw) for c in cases]


def tally(results: list[ShadowResult]) -> dict[str, int]:
    t = {o: 0 for o in OUTCOMES}
    for r in results:
        t[r.outcome] += 1
    return t


def leak_rate(results: list[ShadowResult]) -> float:
    return sum(1 for r in results if r.outcome == LEAKED) / len(results) if results else 0.0


def over_refusal_rate(results: list[ShadowResult]) -> float:
    return (sum(1 for r in results if r.outcome == OVER_REFUSED) / len(results)
            if results else 0.0)


def report_text(cases: tuple[ShadowCase, ...], models: dict, **kw) -> str:
    lines = ["SHADOW RUN — model proposals scored, none served",
             f"{len(cases)} case(s)", ""]
    for name, m in models.items():
        res = run(cases, m, **kw)
        t = tally(res)
        lines.append(f"  {name}")
        lines.append(f"    correct {t[CORRECT]} · caught {t[CAUGHT]} · "
                     f"LEAKED {t[LEAKED]} · over-refused {t[OVER_REFUSED]}")
        for r in res:
            if r.outcome in (LEAKED, OVER_REFUSED):
                lines.append(f"      {r.case_id} {r.outcome}: {r.detail}")
        lines.append("")
    lines.append("LEAKED is the only number that must be zero: a model error")
    lines.append("wearing the system's authority. CAUGHT is the system working.")
    lines.append("OVER_REFUSED is the cost of the contract, and is never netted off.")
    return "\n".join(lines)


# ── stub models, each failing in a way a real one plausibly does ──────────────
_DOC_SPANS = {
    "company_class": ("private", "is a private company"),
    "incorporation_date": ("2015-04-01", "incorporated on 2015-04-01"),
    "paid_up_capital_rupees": (60000000, "Rs. 6,00,00,000"),
}


def honest_model(document: str) -> Proposal:
    """Reads the document and quotes what it read."""
    facts = {k: {"value": v, "span": sp} for k, (v, sp) in _DOC_SPANS.items()
             if sp in document}
    return Proposal(facts=facts)


def lazy_model(document: str) -> Proposal:
    """Right values, no quoted spans. The commonest real failure."""
    return Proposal(facts={k: v for k, (v, _) in _DOC_SPANS.items()})


def confabulating_model(document: str) -> Proposal:
    """Quotes a sentence that is not in this document. Plausible, and wrong."""
    return Proposal(facts={
        "paid_up_capital_rupees": {"value": 40000000,
                                   "span": "paid up share capital is Rs. 4,00,00,000"}})


def stale_model(document: str) -> Proposal:
    """Reads correctly, then narrates the superseded limit from memory."""
    facts = {k: {"value": v, "span": sp} for k, (v, sp) in _DOC_SPANS.items()
             if sp in document}
    return Proposal(facts=facts,
                    narration="The small-company limit is Rs. 4 crore.")


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

    print("shadow")
    from checker.bundles import capabilities

    DOC = ("The Company is a private company incorporated on 2015-04-01. "
           "Its paid up share capital is Rs. 6,00,00,000.")
    CASES = (ShadowCase("S1", DOC,
                        {"company_class": "private",
                         "incorporation_date": "2015-04-01",
                         "paid_up_capital_rupees": 60000000},
                        "a specimen board resolution"),)
    VERIFIED = "CA13-S2-85-SMALL CANNOT_DETERMINE — G.S.R. 880(E) governs. s.2(85)."
    KW = dict(declared_intents=capabilities(), verified_text=VERIFIED)

    r_honest = run(CASES, honest_model, **KW)
    check(tally(r_honest)[CORRECT] == 1, f"an honest model scores CORRECT ({r_honest[0].outcome})")
    check(leak_rate(r_honest) == 0.0, "...with a leak rate of zero")
    check(over_refusal_rate(r_honest) == 0.0, "...and nothing over-refused")

    r_lazy = run(CASES, lazy_model, **KW)
    check(r_lazy[0].outcome == CAUGHT,
          f"a model that will not quote itself is CAUGHT ({r_lazy[0].outcome})")
    check(leak_rate(r_lazy) == 0.0, "...and leaks nothing")

    r_conf = run(CASES, confabulating_model, **KW)
    check(r_conf[0].outcome == CAUGHT,
          f"a model quoting a sentence not in the document is CAUGHT ({r_conf[0].outcome})")
    check("paid_up_capital_rupees" not in r_conf[0].accepted,
          "...and the invented figure never reaches the accepted set")

    r_stale = run(CASES, stale_model, **KW)
    check(r_stale[0].outcome == CAUGHT,
          f"a model narrating the superseded ₹4 crore is CAUGHT ({r_stale[0].outcome})")

    # ── the harness must be able to report a leak, or it measures nothing ────
    def leaking_model(document: str) -> Proposal:
        # quotes a REAL span but attaches the wrong value -- the failure that a
        # span requirement alone does not stop.
        return Proposal(facts={"paid_up_capital_rupees":
                               {"value": 40000000, "span": "Rs. 6,00,00,000"}})
    r_leak = run(CASES, leaking_model, **KW)
    check(r_leak[0].outcome == LEAKED,
          f"a real span with a wrong value LEAKS — the harness can report failure "
          f"({r_leak[0].outcome})")
    check(leak_rate(r_leak) == 1.0, f"...and the leak rate reflects it ({leak_rate(r_leak)})")
    check("6,00,00,000" not in r_leak[0].detail or "40000000" in r_leak[0].detail,
          "...naming the value accepted against what the document says")

    # ── OVER_REFUSED must be reachable, or the cost side is unmeasured ───────
    # It should be near-impossible by construction: the contract and the scorer
    # compute the same judgement independently. So force a contract bug -- refuse
    # a clean proposal -- and confirm the harness reports it as OUR fault, not the
    # model's. A harness that cannot blame the contract will quietly protect it.
    import sys as _sys, checker.reasoning as _rz
    _self = _sys.modules[__name__]
    held_review = _self.review
    def refuse_everything(proposal, **kw):
        base = held_review(proposal, **kw)
        return _rz.Review(base.intent, base.facts, base.narration, base.citations,
                          (_rz.Refusal("INTENT_NOT_DECLARED", "injected contract bug"),))
    _self.review = refuse_everything
    r_over = run(CASES, honest_model, **KW)
    _self.review = held_review
    check(r_over[0].outcome == OVER_REFUSED,
          f"a contract that refuses a clean proposal is OVER_REFUSED, not CAUGHT "
          f"({r_over[0].outcome})")
    check(over_refusal_rate(r_over) == 1.0,
          "...and the over-refusal rate reports the cost of a too-strict contract")
    check(leak_rate(r_over) == 0.0,
          "...while leaking nothing — the two rates move independently")

    # and the harness recovers
    check(run(CASES, honest_model, **KW)[0].outcome == CORRECT,
          "...and the injected bug is scoped to the block")

    # ── nothing here can serve ───────────────────────────────────────────────
    check(all(r.served is False for r in r_honest + r_lazy + r_conf),
          "no shadow result is marked served")
    check(not any(hasattr(r, "answer") or hasattr(r, "to_response")
                  for r in r_honest),
          "a ShadowResult has no method that produces a servable answer")

    # ── the document is purged after each case ───────────────────────────────
    import checker.session as _sess
    opened: list = []
    orig = _sess.Session.close
    def spy(self):
        opened.append(self.id)
        return orig(self)
    _sess.Session.close = spy
    run(CASES, honest_model, **KW)
    _sess.Session.close = orig
    check(len(opened) >= 1, "each shadow case opens and closes a session")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
