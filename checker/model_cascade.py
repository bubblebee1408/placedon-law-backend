"""The verified cascade: deterministic -> small model -> large model.

PLAN_23 layer 5 and O3. PLAN_22 D2 is why the stages take injected callables rather than
naming providers: the interface is the asset, and a model is promoted only by bake-off plus
a person editing the table.

## Why this file is not `checker/cascade.py`

That name is taken, by a DIFFERENT cascade: the entailment-module composition
E6 -> E5 -> E4 -> E3, imported by `checker/metric_policy.py`, `checker/entailment_gate.py`
and `checker/ground_span.py`, registered in `checker/rings.py` and scored by the release
gate. Putting a model-tier cascade in the same module would make "cascade" mean two
different things to four importers, and overwriting it would delete what the gate measures.
Two cascades, two files, two names.

## The one rule that makes this a VERIFIED cascade

**Escalation happens when the L0 verifier rejects, and on nothing else.**

Huang et al. (ICLR 2024) found no intrinsic self-correction: a model asked whether it is
right does not reliably know. FrugalGPT and RouteLLM (ICLR 2025) get their savings by
escalating on an EXTERNAL signal. Escalating on a model's own confidence would be that
unreliable self-assessment used as a spending decision -- twice wrong.

This is enforced structurally, not by discipline. A stage callable is
`Callable[[str], str]`: text in, text out. There is no confidence field, no score, no
`certainty` key -- so there is nothing for this module to read even if a later author
wanted to. What decides is `quoted_span`, which searches the sources for the quote the
model claims to have copied. A test asserts a stage that SAYS it is certain and invents its
quote is still rejected and still escalates.

## FAILED is transport, and transport never escalates

An exception out of a stage callable is a network or 5xx error. Nobody decided anything, so
it is not an abstention -- and escalating on it would spend a large model's tokens on a
socket problem. The run stops, FAILED, with the error attached. `agents/state.py` refuses
to construct a FAILED run carrying a refusal code at all.

## Body status, and why the answer takes the MINIMUM

`checker/scope.py` is the authority. A claim records the body it rests on and that body's
status, and the answer is only as strong as its weakest body:

    IN_CORPUS (HELD) > CURRENT_ONLY > DECLARED

An answer touching a DECLARED body is PARTIAL and carries `scope.refusal_for` for that
body -- what it covers and what we would have to acquire. It is never silently dropped,
because a silence where a refusal belongs reads as "no obligation found", and those are
opposite answers.

Run: PYTHONPATH=. python3 checker/model_cascade.py
"""
from __future__ import annotations

from dataclasses import dataclass

from checker import scope

# ── stages, in order ─────────────────────────────────────────────────────────
DETERMINISTIC = "deterministic"
SMALL = "small_model"
LARGE = "large_model"
STAGE_ORDER = (DETERMINISTIC, SMALL, LARGE)

# ── what a stage did ─────────────────────────────────────────────────────────
ACCEPTED = "ACCEPTED"       # the verifier admitted it; the cascade stops here
REJECTED = "REJECTED"       # the verifier refused it; escalate
NO_ANSWER = "NO_ANSWER"     # the stage had nothing to say; escalate, nothing spent
FAILED = "FAILED"           # transport. Stop. Never escalate, never abstain
OUTCOMES = (ACCEPTED, REJECTED, NO_ANSWER, FAILED)

# ── what the cascade concluded ───────────────────────────────────────────────
ANSWERED = "ANSWERED"
PARTIAL = "PARTIAL"
NEEDS_LAWYER = "NEEDS_LAWYER"   # every stage rejected: abstain, and say so
RESULT_STATUSES = (ANSWERED, PARTIAL, NEEDS_LAWYER, FAILED)

# Strongest first. `scope.py` owns the names; PLAN_23 writes IN_CORPUS as "HELD" and the
# two are the same thing said twice, so the mapping lives here rather than in prose.
STATUS_RANK = {scope.IN_CORPUS: 3, scope.CURRENT_ONLY: 2, scope.DECLARED: 1,
               scope.OUT_OF_SCOPE: 0}
HELD = scope.IN_CORPUS


class CascadeError(ValueError):
    """The cascade was asked for something it must not do. Raised, never recorded."""


@dataclass(frozen=True)
class Claim:
    """One sentence the cascade is prepared to serve, and the body it rests on.

    `body_id` is a key from `checker/scope.py` and `body_status` is read from the register
    at record time -- not copied by hand, because a hand-copied status goes stale the day
    the register changes.
    """

    text: str
    body_id: str
    quote: str = ""
    source_id: str = ""
    span: tuple[int, int] | None = None
    # The repo-relative path of the committed file this claim's quote was cleared against
    # -- `public_only.Origin.path`. `checker/claim_bodies.py` reads THIS to set `body_id`,
    # not `source_id`: a source_id is a human label written by whatever built the evidence
    # and can say anything, while the path is established against a file with a git blob id.
    evidence_path: str = ""

    @property
    def body_status(self) -> str:
        return scope.body(self.body_id).status

    def to_dict(self) -> dict:
        return {"text": self.text, "body_id": self.body_id,
                "body_status": self.body_status, "quote": self.quote,
                "source_id": self.source_id, "evidence_path": self.evidence_path,
                "span": list(self.span) if self.span else None}


@dataclass(frozen=True)
class Attempt:
    """One stage, what it cost, and why it was not enough."""

    stage: str
    outcome: str
    reason: str = ""
    model: str | None = None
    cost_inr: float | None = None
    cost_note: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise CascadeError(f"{self.outcome!r} is not a stage outcome; one of {OUTCOMES}")
        if self.outcome in (REJECTED, FAILED) and not self.reason:
            raise CascadeError(
                f"a {self.outcome} stage must say WHY. A rejection with no reason cannot be "
                f"counted in a rejection rate, and scripts/cascade_report.py exists to "
                f"count them.")
        # UNPRICED is null WITH a reason, exactly as a run step is. A blank beside a null is
        # indistinguishable from a cost nobody bothered to record.
        if self.cost_inr is None and not self.cost_note:
            raise CascadeError(
                f"stage {self.stage!r} has no cost and no reason for it. UNPRICED is a null "
                f"plus a reason; a bare null is a gap.")
        if self.cost_inr is not None and self.cost_inr < 0:
            raise CascadeError("a stage cost cannot be negative")

    def to_dict(self) -> dict:
        return {"stage": self.stage, "outcome": self.outcome, "reason": self.reason,
                "model": self.model, "cost_inr": self.cost_inr,
                "cost_note": self.cost_note}


@dataclass(frozen=True)
class Result:
    """What the cascade concluded, and the whole record of how it got there."""

    status: str
    attempts: tuple[Attempt, ...] = ()
    claims: tuple[Claim, ...] = ()
    refusals: tuple[tuple[str, str], ...] = ()      # (body_id, its named refusal)
    error: str | None = None
    # Every body the answer TOUCHES, as `bodies_for` reported it. Recorded rather than
    # derived from the claims: an answer can reach a body it cannot claim FROM, which is
    # the whole FEMA case -- the question went there, we hold nothing, and the refusal says
    # so. Deriving this from `claims` lost exactly the body the refusal was about.
    touched: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise CascadeError(f"{self.status!r} is not a cascade status")
        if self.status == FAILED and not self.error:
            raise CascadeError("FAILED must carry the transport error it reports")
        if self.status != FAILED and self.error:
            raise CascadeError(
                "only a FAILED result carries a transport error. A refusal is a decision "
                "and a failure is not, and blurring them is what this repository refuses.")

    @property
    def body_ids(self) -> tuple[str, ...]:
        """Every body touched. Falls back to the claims' own bodies only when nothing was
        recorded, which is the case for a FAILED or fully-rejected run."""
        if self.touched:
            return self.touched
        seen: list[str] = []
        for c in self.claims:
            if c.body_id not in seen:
                seen.append(c.body_id)
        return tuple(seen)

    @property
    def stages_tried(self) -> tuple[str, ...]:
        return tuple(a.stage for a in self.attempts)

    @property
    def total_cost_inr(self) -> float | None:
        """The priced stages, summed. None when NOTHING was priced -- which is UNPRICED,
        not free, and a caller that rendered it as 0 would be claiming a free call."""
        priced = [a.cost_inr for a in self.attempts if a.cost_inr is not None]
        return sum(priced) if priced else None

    def to_dict(self) -> dict:
        return {"status": self.status, "error": self.error,
                "stages_tried": list(self.stages_tried),
                "body_ids": list(self.body_ids),
                "attempts": [a.to_dict() for a in self.attempts],
                "claims": [c.to_dict() for c in self.claims],
                "refusals": [{"body": b, "refusal": r} for b, r in self.refusals],
                "total_cost_inr": self.total_cost_inr}


# ── the body arithmetic ──────────────────────────────────────────────────────

def weakest(body_ids) -> str | None:
    """The MINIMUM status across these bodies. None for no bodies at all."""
    ranked = [(STATUS_RANK.get(scope.body(b).status, 0), scope.body(b).status)
              for b in body_ids]
    return min(ranked)[1] if ranked else None


def answer_status(body_ids) -> str:
    """ANSWERED only if every body touched is held. Anything weaker is PARTIAL.

    Deliberately not "PARTIAL only when a DECLARED body appears": CURRENT_ONLY is held text
    with no history, so an answer resting on one is also less than fully supported. Calling
    it ANSWERED would put a consolidation where point-in-time evidence belongs, which is the
    retracted mistake in docs/RETRACTIONS.md.
    """
    w = weakest(body_ids)
    if w is None:
        return NEEDS_LAWYER
    return ANSWERED if w == HELD else PARTIAL


def refusals_for(body_ids) -> tuple[tuple[str, str], ...]:
    """The named refusal for every body touched that cannot carry an obligation.

    Never omitted, and that is the point: a silence where a refusal belongs reads as "no
    obligation found", and those are opposite answers.
    """
    out = []
    for b in body_ids:
        if not scope.body(b).answerable:
            out.append((b, scope.refusal_for(b)))
    return tuple(out)


# ── the cascade ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Stage:
    """One rung. `call` is text-in/text-out -- there is NO confidence channel, so no later
    author can escalate on one without changing this signature in review."""

    name: str
    call: object = None                  # Callable[[str], str] | None
    model: str | None = None
    price: object = None                 # Callable[[str], float] | None
    unpriced_note: str = ""

    def __post_init__(self) -> None:
        if self.name not in STAGE_ORDER:
            raise CascadeError(f"{self.name!r} is not a declared stage; one of {STAGE_ORDER}")


def run(prompt: str, *, stages, verify, bodies_for) -> Result:
    """Walk the stages until the VERIFIER accepts, or they run out.

    `verify(text) -> (accepted, reason, claims)` is L0. `bodies_for(claims) -> body_ids`
    maps admitted claims onto `checker/scope.py`. Both injected: this module decides the
    ORDER and the escalation rule, and nothing about the law.
    """
    ordered = sorted(stages, key=lambda s: STAGE_ORDER.index(s.name))
    attempts: list[Attempt] = []

    for stage in ordered:
        if stage.call is None:
            attempts.append(Attempt(
                stage.name, NO_ANSWER, reason="no callable is configured for this stage",
                model=stage.model, cost_inr=None,
                cost_note=stage.unpriced_note or "the stage did not run, so nothing was "
                                                 "spent and there is nothing to price"))
            continue

        try:
            raw = stage.call(prompt)
        except Exception as e:                                    # noqa: BLE001
            # TRANSPORT. Not a decision, so it neither escalates nor abstains: escalating
            # would spend a larger model on a socket problem, and abstaining would tell a
            # lawyer we declined their question on its merits.
            attempts.append(Attempt(
                stage.name, FAILED, reason=f"{type(e).__name__}: {e}", model=stage.model,
                cost_inr=None,
                cost_note="the call did not complete, so no cost is claimed for it"))
            return Result(FAILED, tuple(attempts), error=f"{type(e).__name__}: {e}")

        cost = stage.price(raw) if callable(stage.price) else None
        note = "" if cost is not None else (
            stage.unpriced_note
            or "no verified price is held for this stage's model, so the call is UNPRICED "
               "rather than recorded as free")

        accepted, reason, claims = verify(raw)
        if not accepted:
            # THE ONLY ESCALATION TRIGGER. The verifier rejected; the model's own view of
            # its work was never consulted and there is no field here carrying one.
            attempts.append(Attempt(
                stage.name, REJECTED,
                reason=reason or "the verifier rejected this stage's output",
                model=stage.model, cost_inr=cost, cost_note=note))
            continue

        attempts.append(Attempt(stage.name, ACCEPTED, model=stage.model,
                                cost_inr=cost, cost_note=note))
        admitted = tuple(claims)
        ids = tuple(bodies_for(admitted))
        return Result(answer_status(ids), tuple(attempts), admitted, refusals_for(ids),
                      touched=ids)

    # Every stage rejected or had nothing. Abstain, by name.
    return Result(NEEDS_LAWYER, tuple(attempts))


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

    import inspect

    from checker.lawyer_summary import Source
    from checker.quoted_span import QUOTE_TAG, SENTENCE_TAG, blocks

    SRC = (Source("ca2013-s96", "STATUTE",
                  "Every company shall in each year hold in addition to any other "
                  "meetings a general meeting as its annual general meeting."),)

    def pair(sentence: str, quote: str) -> str:
        return f"{SENTENCE_TAG} {sentence}\n{QUOTE_TAG} {quote}"

    # L0, as this module's callers actually use it: quoted_span searches the sources for the
    # quote. An invented quote is not found, and that is the rejection.
    def l0(raw: str):
        bs = blocks(raw, SRC)
        traced = [(t, c) for t, c in bs if c]
        if not traced:
            return False, (f"quoted_span refused all {len(bs)} sentence(s): the quote was "
                           f"not found in any admitted source"), ()
        return True, "", tuple(
            Claim(text=t, body_id="CA2013", quote=c[0].quoted,
                  source_id=SRC[c[0].source_index].source_id,
                  span=(c[0].start, c[0].end)) for t, c in traced)

    def ca2013(claims):
        return tuple(dict.fromkeys(c.body_id for c in claims))

    HONEST = pair("A company must hold an annual general meeting each year.",
                  "hold in addition to any other meetings a general meeting")
    INVENTED = pair("A company must hold two annual general meetings each year.",
                    "shall hold not less than two annual general meetings in each year")

    # ── an invented quote is rejected and ESCALATES ─────────────────────────
    calls = []

    def liar(_p):
        calls.append("small")
        return INVENTED

    def honest(_p):
        calls.append("large")
        return HONEST

    r = run("q", stages=[Stage(SMALL, liar, model="small-1"),
                         Stage(LARGE, honest, model="large-1")],
            verify=l0, bodies_for=ca2013)
    check(r.status == ANSWERED,
          f"the cascade ends ANSWERED once a stage verifies ({r.status})")
    check(calls == ["small", "large"],
          f"...having tried the small model FIRST and escalated to the large one {calls}")
    check(r.attempts[0].outcome == REJECTED and "not found" in r.attempts[0].reason,
          f"...because the verifier rejected the invented quote "
          f"({r.attempts[0].reason[:60]})")
    check(r.attempts[1].outcome == ACCEPTED, "...and the large model's answer was admitted")
    check(r.stages_tried == (SMALL, LARGE), f"...both stages recorded ({r.stages_tried})")

    # The model SAYING it is certain changes nothing. There is no channel for it to say so
    # on, which is the structural version of the rule.
    def confident_liar(_p):
        return INVENTED + "\nCONFIDENCE: 0.99\nI am certain."

    r_conf = run("q", stages=[Stage(SMALL, confident_liar, model="s"),
                              Stage(LARGE, honest, model="l")],
                 verify=l0, bodies_for=ca2013)
    check(r_conf.attempts[0].outcome == REJECTED,
          "a stage that DECLARES itself certain and invents its quote is still rejected: "
          "escalation reads the verifier, never the model's own view")
    sig = inspect.signature(Stage.__init__)
    check("confidence" not in sig.parameters and "score" not in sig.parameters,
          f"...and a Stage has no confidence field for a later author to escalate on "
          f"({sorted(sig.parameters)})")

    # ── every stage rejected -> NEEDS_LAWYER, not a wrong answer ────────────
    r_all = run("q", stages=[Stage(SMALL, liar, model="s"), Stage(LARGE, liar, model="l")],
                verify=l0, bodies_for=ca2013)
    check(r_all.status == NEEDS_LAWYER,
          f"every stage rejected gives NEEDS_LAWYER ({r_all.status}) -- an abstention, "
          f"named, rather than the last stage's unverified text")
    check(r_all.claims == (), "...and serves no claims at all")
    check(all(a.outcome == REJECTED and a.reason for a in r_all.attempts),
          "...with a recorded reason at EVERY stage, which is what a rejection rate counts")

    # ── a transport error neither escalates nor abstains ────────────────────
    reached = []

    def dead(_p):
        raise ConnectionError("connection reset by peer")

    def should_not_run(_p):
        reached.append("large")
        return HONEST

    r_fail = run("q", stages=[Stage(SMALL, dead, model="s"),
                              Stage(LARGE, should_not_run, model="l")],
                 verify=l0, bodies_for=ca2013)
    check(r_fail.status == FAILED, f"a transport error is FAILED ({r_fail.status})")
    check(reached == [],
          "...and does NOT escalate: spending a large model on a socket problem is paying "
          "for a fault that has nothing to do with the question")
    check(r_fail.status != NEEDS_LAWYER and not r_fail.refusals,
          "...and is NOT an abstention: nobody decided anything")
    check("ConnectionError" in (r_fail.error or ""), "...and carries the error it reports")
    check(r_fail.attempts[-1].cost_inr is None
          and "no cost is claimed" in r_fail.attempts[-1].cost_note,
          "...and claims no cost for a call that did not complete")

    # ── body status: the answer is the MINIMUM across the bodies ────────────
    check(scope.body("CA2013").status == scope.IN_CORPUS
          and scope.body("FEMA1999").status == scope.DECLARED
          and scope.body("SEBI_LODR").status == scope.CURRENT_ONLY,
          "the register is as PLAN_23 O3 describes it: CA2013 held, SEBI_LODR "
          "current-only, FEMA1999 declared")
    check(STATUS_RANK[scope.IN_CORPUS] > STATUS_RANK[scope.CURRENT_ONLY]
          > STATUS_RANK[scope.DECLARED],
          "HELD > CURRENT_ONLY > DECLARED")
    check(answer_status(["CA2013"]) == ANSWERED, "a held-only answer is ANSWERED")
    check(answer_status(["CA2013", "SEBI_LODR"]) == PARTIAL,
          "...held plus current-only is PARTIAL: a consolidation is silent on every "
          "earlier date, and calling that ANSWERED is the retracted mistake")
    check(answer_status(["CA2013", "FEMA1999"]) == PARTIAL,
          "...and held plus DECLARED is PARTIAL")
    check(weakest(["CA2013", "SEBI_LODR", "FEMA1999"]) == scope.DECLARED,
          "the weakest body decides, not the strongest")

    # An answer touching CA2013 + FEMA1999: PARTIAL, with FEMA's refusal PRESENT.
    def two_bodies(_claims):
        return ("CA2013", "FEMA1999")

    r_two = run("q", stages=[Stage(SMALL, honest, model="s")],
                verify=l0, bodies_for=two_bodies)
    check(r_two.status == PARTIAL,
          f"an answer touching CA2013 + FEMA1999 is PARTIAL ({r_two.status})")
    names = [b for b, _ in r_two.refusals]
    check(names == ["FEMA1999"],
          f"...carrying a named refusal for the declared body {names}, never silently "
          f"leaving it out")
    fema = dict(r_two.refusals)["FEMA1999"]
    check("Foreign Exchange Management Act" in fema and "acquire" in fema.lower(),
          f"...and that refusal names the body and what would have to be acquired "
          f"({fema[:70]})")
    check("CA2013" not in names,
          "...while the held body needs no refusal, so none is invented for it")
    check(r_two.body_ids == ("CA2013", "FEMA1999"),
          f"...and the record carries every body touched ({r_two.body_ids})")

    # ── the scope invariant still holds ─────────────────────────────────────
    unheld = [b.key for b in scope.BODIES if b.status != scope.IN_CORPUS]
    check(all(not scope.body(k).answerable for k in unheld),
          f"no unheld body is answerable ({len(unheld)} of {len(scope.BODIES)} bodies)")
    check(all(refusals_for([k]) for k in unheld),
          "...and every one of them produces a named refusal when an answer touches it")
    check(refusals_for(["CA2013"]) == (),
          "...while the held body produces none, because there is nothing to refuse")

    # ── the record a report is built from ───────────────────────────────────
    d = r.to_dict()
    check(set(d) >= {"status", "stages_tried", "body_ids", "attempts", "claims",
                     "refusals", "total_cost_inr"},
          f"the record carries stages, bodies, attempts and claims ({sorted(d)})")
    check(all(a["reason"] for a in d["attempts"] if a["outcome"] == REJECTED),
          "...every rejection with its reason, per stage")
    check(d["claims"][0]["body_status"] == scope.IN_CORPUS,
          "...and every claim with its body's status, read from the register rather than "
          "copied")

    # UNPRICED stays UNPRICED.
    r_unp = run("q", stages=[Stage(SMALL, honest, model="s")], verify=l0,
                bodies_for=ca2013)
    check(r_unp.attempts[0].cost_inr is None and r_unp.attempts[0].cost_note,
          "a stage with no price table is UNPRICED: null WITH a reason")
    check(r_unp.total_cost_inr is None,
          "...and a cascade where nothing was priced totals None, never 0 -- 0 would claim "
          "the calls were free")
    r_priced = run("q", stages=[Stage(SMALL, liar, model="s", price=lambda _r: 0.02),
                                Stage(LARGE, honest, model="l", price=lambda _r: 0.07)],
                   verify=l0, bodies_for=ca2013)
    check(abs((r_priced.total_cost_inr or 0) - 0.09) < 1e-9,
          f"...while priced stages sum, INCLUDING the rejected one: an escalation costs "
          f"what both calls cost ({r_priced.total_cost_inr})")

    # ── the shapes that must not be constructible ───────────────────────────
    for bad, why in (
        (lambda: Attempt(SMALL, REJECTED, reason=""), "a rejection with no reason"),
        (lambda: Attempt(SMALL, ACCEPTED, cost_inr=None, cost_note=""),
         "a null cost with no reason"),
        (lambda: Attempt(SMALL, "MAYBE", reason="x", cost_note="y"), "an unknown outcome"),
        (lambda: Result(FAILED), "FAILED with no error"),
        (lambda: Result(NEEDS_LAWYER, error="boom"), "an abstention carrying an error"),
        (lambda: Stage("medium_model"), "a stage that is not one of the three"),
    ):
        try:
            bad()
            check(False, f"{why} is refused")
        except CascadeError:
            check(True, f"refused at construction: {why}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
