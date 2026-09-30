"""research_question, end to end: a question about the Companies Act, answered or refused.

This is the first intent in `agents/plans.py` that actually runs. Everything under it
already existed and was wired to nothing:

    checker/ask_scope.py           which bodies of law a question reaches
    checker/structural_retrieve.py provisions for a query, or an abstention
    checker/quoted_span.py         a sentence traces to a span, or it is dropped
    checker/public_only.py         nothing uncleared reaches a free-tier model
    checker/router.py              which model, and whether it degraded

What is added here is the order they run in, and -- the part that is not plumbing -- the
rule for turning what comes back into one of three answers.

## ANSWERED, PARTIAL, REFUSED, and why PARTIAL has to exist

    ANSWERED   every sentence the model wrote traced to a span of the Act
    PARTIAL    some traced, some were dropped. The traced ones are served, and the
               count of dropped ones is served with them
    REFUSED    nothing is served, and the code says which kind of nothing

The temptation is two states. It is wrong in both directions. Calling a partial answer
ANSWERED hides that the model wrote four sentences and one was a fabrication we caught --
the reader gets three good sentences and no idea that a fourth existed. Calling it REFUSED
throws away three sentences that traced to the Act, which is the answer the user asked
for. So PARTIAL is served WITH its own count, and `Summary.prose()` already prints that
count in the body rather than in a footnote.

REFUSED carries a code, and two of the codes are easy to confuse:

    NO_EVIDENCE     retrieval abstained. No model was called. We did not look it up.
    NOTHING_TRACED  a model answered and every sentence failed. We did look it up, and
                    would not repeat what came back.

## Why this is NARRATION and not EXTRACTION

`router.Task(..., purpose=NARRATION)`. The provisions are selected by deterministic
retrieval and the sentences are checked against them afterwards; the model's only job is
to say, in a sentence, what a span it was handed says. That is the row PROVIDER_DECISION
§4 describes -- "obedience, not creativity" -- and it is why running it on a free tier is
a cost decision rather than a correctness one. An EXTRACTION route would refuse without
Anthropic credit, correctly, because extraction decides what the facts are.

Run: PYTHONPATH=. python3 agents/research_question.py
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agents.state import (ANSWERED, FAILED, NO_EVIDENCE, NO_MODEL, NOTHING_TRACED,
                          OUT_OF_SCOPE_LAW, PARTIAL, REFUSED)
from checker import (ask_scope, claim_bodies, model_cascade as mc, public_only,
                     quoted_span, router, scope, section_index)
from backend.budget import FREE_TIER_RPD_PER_MODEL
from checker.gemini_model import ModelBusy, ModelRateLimited
from checker.ollama_runner import ModelUnavailable as OllamaUnavailable
from checker.ollama_runner import OllamaRunner
from checker.lawyer_summary import STATUTE, Call, Source, Summary, check_blocks
from checker.retrieve import ROUTE_ABSTAIN
from checker.sarvam_model import html_to_text
from checker.structural_retrieve import structural_retrieve

CORPUS = public_only.ROOT / "corpus" / "companies_act"

MAX_PROVISIONS = 6          # a prompt of six provisions, not the whole Act

_SYSTEM = """\
You answer a question about the Companies Act, 2013, using only the provisions given.

Rules, and a sentence that breaks one is thrown away rather than corrected:

- Every sentence must be drawn from, and quote, the provision you read it from.
- One proposition per sentence. Keep sentences short.
- Introduce no date, no rupee figure and no section number that is absent from the text
  you quote for that sentence.
- Do not say whether anybody complied, and do not advise.
- If the provisions do not answer the question, say only what they do say."""


@dataclass(frozen=True)
class Outcome:
    status: str
    question: str
    code: str | None = None
    reason: str = ""
    summary: Summary | None = None
    provisions: tuple[str, ...] = ()
    route: router.Route | None = None
    dropped: int = 0

    @property
    def served(self) -> str:
        return self.summary.prose() if self.summary and self.status != REFUSED else ""

    def to_dict(self) -> dict:
        return dict(status=self.status, question=self.question, code=self.code,
                    reason=self.reason, provisions=list(self.provisions),
                    dropped=self.dropped,
                    model=f"{self.route.provider}/{self.route.model}" if self.route else None,
                    degraded=bool(self.route and self.route.degraded))


def evidence(question: str) -> tuple[tuple[Source, public_only.Origin], ...]:
    """The sections this question reaches, each with its public-corpus clearance.

    Empty when retrieval abstained. A near-miss provision is NOT offered in its place:
    `structural_retrieve` refuses that on purpose, and substituting one here would put
    the citation betrayal back two layers up.

    **A Source is a SECTION, though retrieval works in chunks, and the first draft used
    the chunk.** It was measured wrong: `verify_sentence` refuses a citation covering
    most of its source as SPAN_OVERBROAD -- correctly, since a span that size shows
    nothing about where the sentence was read -- and a retrieved chunk is often a
    99-character proviso, so ANY honest quote of it was most of the source. Four of the
    ten fixtures came back NOTHING_TRACED for that reason alone, with a stub model
    quoting verbatim. The rule was right and the evidence unit was wrong: the source is
    the provision, and the quote is the passage inside it. The chunks still decide WHICH
    sections; they are no longer what the model is shown.
    """
    chunks, route, _withheld = structural_retrieve(question)
    if route == ROUTE_ABSTAIN:
        return ()
    out, seen = [], set()
    for c in chunks:
        if c.section in seen:
            continue
        seen.add(c.section)
        if len(out) >= MAX_PROVISIONS:
            break
        rec = section_index.section_by_number(c.section)
        if not rec:
            continue        # an unindexed section is not evidence; it is a gap
        path = CORPUS / f"{rec['section_id']}.json"
        # The corpus stores provisions as HTML. Nobody should be shown markup, and a
        # quote of it would carry `<span style=...>` into the answer, so it is stripped
        # here -- `public_only._readable` accepts the stripped form as a quotation of
        # the same file, which is what lets both be true at once.
        text = html_to_text(rec.get("content") or "")
        if not text:
            continue
        try:
            origin = public_only.clear_text(text, path=path)
        except public_only.NotPublic:
            # The section text does not match the committed corpus file. That is a
            # corpus problem, not something to route around by sending it anyway.
            continue
        out.append((Source(f"Companies Act 2013, s.{c.section}", STATUTE, text), origin))
    return tuple(out)


# ── the cascade (PLAN_23 layer 5, O3) ────────────────────────────────────────

def _prompt(sources, question: str) -> str:
    """Exactly the prompt `quoted_span.summarise` builds. Split out because the cascade
    needs the model call and the verification to be two steps, and `summarise` is both."""
    return (quoted_span.system_prompt(_SYSTEM) + "\n\n"
            + quoted_span.render_sources(sources) + "\n\n"
            + (question or "Summarise these sources for a lawyer."))


def _verifier(sources, origins, holder: dict):
    """L0, unchanged: `quoted_span` searches the sources for the quote the model claims.

    Returns the cascade's `(accepted, reason, claims)`. The Summary is kept on `holder`
    because an Outcome serves its prose, and the cascade's contract has no room for it.

    Each claim carries the `evidence_path` of the source its quote was found in, so
    `checker/claim_bodies.py` can attribute it from the instrument rather than from a label.
    """
    def verify(raw: str):
        if not (raw or "").strip():
            return False, ("no model produced any text for this stage, so there was "
                           "nothing to verify"), ()
        bs = quoted_span.blocks(raw, sources)
        summary = check_blocks(bs, sources, call=Call(holder.get("model") or "unnamed",
                                                      0, 0, 0.0, raw))
        holder["summary"] = summary
        if summary.refused_entirely:
            return False, (summary.refusal_reason() or "nothing traced"), ()
        claims = []
        for sentence in summary.traced:
            cit = sentence.citations[0] if sentence.citations else None
            idx = cit.source_index if cit else 0
            claims.append(mc.Claim(
                text=sentence.text, body_id="",
                quote=cit.quoted if cit else "",
                source_id=sources[idx].source_id,
                span=(cit.start, cit.end) if cit else None,
                evidence_path=origins[idx].path if idx < len(origins) else ""))
        return True, "", tuple(claims)
    return verify


def _tier_callable(sources, question, *, route0, model, available, budget, busy: set,
                   holder: dict):
    """One cascade stage: call the best model left, falling through the busy ones.

    The retry loop lives INSIDE the stage rather than around the cascade, and that is the
    load-bearing part: a 503 or a spent free-tier quota is not a model being wrong, so it
    must not count as the verifier rejecting anything. It moves to the next model in the
    same tier. Only a real transport error escapes, and the cascade turns that into FAILED.

    When every model is exhausted the stage returns "" rather than raising, and records why.
    `NoRoute` reaching the cascade would be FAILED, but "every model was busy" is a refusal
    with a name -- which is what this returned before the cascade existed.
    """
    task = router.Task("research.narrate", router.TEXT, router.LOW,
                       purpose=router.NARRATION)

    def call(prompt: str) -> str:
        route = route0
        last = ""
        while True:
            if route is None:
                try:
                    route = router.route(task, available=available,
                                         exclude_models=frozenset(busy))
                except router.NoRoute as e:
                    holder["no_model"] = (
                        (f"every model was unavailable ({', '.join(sorted(busy))}): "
                         f"{last} " if busy else "") + str(e))
                    return ""
            holder["route"] = route
            holder["model"] = route.model
            fn = model
            if fn is None:
                if route.provider == router.GEMINI:
                    from checker import gemini_model
                    fn = gemini_model.as_text_model(origin=holder["origins"],
                                                    model=route.model, budget=budget)
                elif route.provider == router.OLLAMA:
                    fn = OllamaRunner(route.model)
                else:
                    holder["no_model"] = (f"no text callable is wired for "
                                          f"{route.provider}/{route.model}")
                    return ""
            try:
                return fn(prompt)
            except ModelBusy:
                busy.add(route.model)
            except OllamaUnavailable as e:
                busy.add(route.model)
                last = str(e)
            except ModelRateLimited as e:
                # A quota, not a fault: the next row may be the operator's own machine,
                # which has none. Remembered so the refusal can name it.
                busy.add(route.model)
                last = (f"the free tier's quota for {route.model} is spent "
                        f"({FREE_TIER_RPD_PER_MODEL} requests/day/model, measured); "
                        f"{str(e)[:120]}")
            route = None
    return call


def answer(question: str, *, model=None, available=None, budget=None,
           stages=None, event_key: str | None = None, facts: dict | None = None) -> Outcome:
    """One question, to one of ANSWERED / PARTIAL / REFUSED, through the verified cascade.

    PLAN_23 O3: deterministic -> small -> large, escalating ONLY when L0 rejects. `model` is
    injected -- a `Callable[[str], str]` -- so the tests reach no network; an injected model
    is ONE stage, because a caller who supplied one model did not ask for a cascade over it.

    `event_key` and `facts` are passed to `claim_bodies.bodies_for`, so a body the answer
    TOUCHES but cannot claim from keeps its named refusal.
    """
    reading = ask_scope.read(question)
    unheld = [b for b in getattr(reading, "unheld", ()) or ()]
    if unheld and not (getattr(reading, "held", ()) or ()):
        key = unheld[0] if isinstance(unheld[0], str) else getattr(unheld[0], "key", "")
        return Outcome(REFUSED, question, OUT_OF_SCOPE_LAW,
                       scope.refusal_for(key) if key else
                       "this question is about a body of law that is not held")

    ev = evidence(question)
    if not ev:
        return Outcome(REFUSED, question, NO_EVIDENCE,
                       "retrieval abstained: the question cited nothing this corpus "
                       "resolves, so no model was called. That is not the same as "
                       "there being no such provision.")

    sources = tuple(s for s, _ in ev)
    origins = tuple(o for _, o in ev)
    names = tuple(s.source_id for s in sources)

    have = available if available is not None else router.providers_available()
    holder: dict = {"origins": origins}
    busy: set[str] = set()

    if stages is None:
        stages = _stages(sources, question, model=model, available=have, budget=budget,
                         busy=busy, holder=holder)
        if stages is None:                      # no route at all, before anything was spent
            return Outcome(REFUSED, question, NO_MODEL, holder.get("no_model", ""),
                           provisions=names)

    result = mc.run(_prompt(sources, question), stages=stages,
                    verify=_verifier(sources, origins, holder),
                    bodies_for=lambda claims: claim_bodies.bodies_for(
                        claims, event_key=event_key, facts=facts))

    return _outcome(question, result, names, holder)


def _stages(sources, question, *, model, available, budget, busy, holder):
    """deterministic -> small -> large. None when no route exists at all.

    The deterministic stage is declared with no callable and says so: there is no
    deterministic answer path for a research question today -- retrieval picks the
    provisions and a model narrates them. Declaring it and recording NO_ANSWER is how the
    cost report can later show that the cheapest rung is empty, which a silently absent
    stage never would.
    """
    det = mc.Stage(mc.DETERMINISTIC, call=None,
                   unpriced_note="no deterministic answer path is wired for a research "
                                 "question yet, so this stage did not run and nothing was "
                                 "spent")
    if model is not None:
        # An injected model is one stage. Running the SAME callable twice would bill a
        # caller twice for a cascade they did not ask for.
        return [det, mc.Stage(mc.SMALL,
                              _tier_callable(sources, question, route0=None, model=model,
                                             available=available, budget=budget, busy=busy,
                                             holder=holder),
                              model="injected")]

    task = router.Task("research.narrate", router.TEXT, router.LOW,
                       purpose=router.NARRATION)
    try:
        first = router.route(task, available=available)
    except router.NoRoute as e:
        holder["no_model"] = str(e)
        return None
    out = [det, mc.Stage(mc.SMALL,
                         _tier_callable(sources, question, route0=first, model=None,
                                        available=available, budget=budget, busy=busy,
                                        holder=holder),
                         model=first.model)]
    try:
        second = router.route(task, available=available,
                              exclude_models=frozenset({first.model}))
    except router.NoRoute:
        second = None
    if second is not None:
        out.append(mc.Stage(mc.LARGE,
                            _tier_callable(sources, question, route0=second, model=None,
                                           available=available, budget=budget, busy=busy,
                                           holder=holder),
                            model=second.model))
    return out


def _outcome(question, result, names, holder) -> Outcome:
    """The cascade's Result, as the Outcome this intent has always returned.

    The three product states are unchanged. What is new is that REFUSED can now be reached
    after more than one model was tried, and the cascade's attempts say which.
    """
    summary = holder.get("summary")
    route = holder.get("route")
    dropped = len(summary.refused) if summary else 0

    if result.status == mc.FAILED:
        # Transport. Not an abstention: nobody decided. `agents/state.py` will not let a
        # FAILED run carry a refusal code, and this mirrors it.
        return Outcome(FAILED, question, None, result.error or "transport failure",
                       summary=None, provisions=names, route=route)

    if result.status == mc.NEEDS_LAWYER:
        # Every stage rejected, or none could run. Which refusal it is depends on WHY.
        if holder.get("no_model") and not holder.get("summary"):
            return Outcome(REFUSED, question, NO_MODEL, holder["no_model"],
                           provisions=names, route=route)
        return Outcome(REFUSED, question, NOTHING_TRACED,
                       (summary.refusal_reason() if summary else None)
                       or "nothing traced at any stage of the cascade",
                       summary=summary, provisions=names, route=route, dropped=dropped)

    traced = len(summary.traced) if summary else 0
    # PARTIAL is now reached two ways, and both are true at once: sentences dropped by L0,
    # and an answer resting on a body that is not fully held. The cascade decided the
    # second; this line keeps the first.
    status = ANSWERED if (not dropped and result.status == mc.ANSWERED) else PARTIAL
    reason = "every sentence traced" if not dropped else \
        f"{traced} sentence(s) traced, {dropped} dropped as unsupported"
    if result.status == mc.PARTIAL and not dropped:
        reason = ("every sentence traced, and the answer reaches a body of law this "
                  "corpus does not fully hold")
    return Outcome(status, question, None, reason, summary=summary, provisions=names,
                   route=route, dropped=dropped)


# ── the ten fixtures ─────────────────────────────────────────────────────────
# Four shapes on purpose, because a fixture set that is all one shape measures one thing:
#   * six answerable questions across six provisions of the Act,
#   * two that name a body of law we do not hold (the scope refusal),
#   * two that cite nothing this corpus resolves (the retrieval abstention).
FIXTURES: tuple[tuple[str, str], ...] = (
    ("F1", "What is the time limit for holding an annual general meeting under section 96?"),
    ("F2", "How many meetings of the Board must a company hold under section 173?"),
    ("F3", "What does section 149 require about the number of directors?"),
    ("F4", "What does section 92 require in the annual return?"),
    ("F5", "What does section 134 require to be attached to financial statements?"),
    ("F6", "What is a small company under section 2(85)?"),
    ("F7", "What are the penalties for insider trading under the SEBI PIT Regulations?"),
    ("F8", "What consent is required under the Digital Personal Data Protection Act 2023?"),
    ("F9", "What did the Supreme Court hold about oppression and mismanagement?"),
    ("F10", "How do I structure a slump sale to minimise stamp duty in Maharashtra?"),
)


def quoting_model(sources) -> object:
    """A stub model that answers by quoting its first source, verbatim.

    Not a mock of a good answer -- a mock of an OBEDIENT one. It is what the protocol
    asks for and nothing more, so a fixture that still comes back REFUSED is telling you
    about the pipeline rather than about the model.
    """
    def _m(prompt: str) -> str:
        src = sources[0]
        # The sentence IS the quote. A stub that adds words of its own ("The Act
        # provides as follows: ...") is refused as TERMS_NOT_IN_SPAN, correctly -- but
        # that would be measuring the stub's prose, not the pipeline.
        quote = " ".join(src.text.split())[:180]
        return (f"{quoted_span.SENTENCE_TAG} {quote}\n"
                f"{quoted_span.QUOTE_TAG} {quote}\n")
    return _m


def run_fixtures(*, model_for=None, available=("gemini",), pace=None,
                 budget=None) -> tuple[Outcome, ...]:
    """Every fixture, with a per-question model. Returns the outcomes in fixture order.

    `pace` is injected, and is what a LIVE run needs: the Gemini free tier allows
    `budget.FREE_TIER_RPM` = 5 requests per minute PER MODEL, measured off Google's own
    quota object on 28-09-2026, and ten questions fired back to back spend that in the
    first two seconds and 429 for the rest of the minute. It is injected rather than a
    `time.sleep` in here because a library that sleeps is a library that hangs a test
    suite, and the offline run passes None.
    """
    out = []
    for i, (_fid, q) in enumerate(FIXTURES):
        if pace is not None and i:
            pace()
        ev = evidence(q)
        m = None
        if model_for is not None:
            m = model_for(tuple(s for s, _ in ev)) if ev else (lambda p: "")
        out.append(answer(q, model=m, available=available, budget=budget))
    return tuple(out)


def tally(outcomes) -> dict[str, int]:
    counts = {ANSWERED: 0, PARTIAL: 0, REFUSED: 0}
    for o in outcomes:
        counts[o.status] = counts.get(o.status, 0) + 1
    return counts


def report(outcomes) -> str:
    lines = ["research_question, 10 fixtures", ""]
    for (fid, _q), o in zip(FIXTURES, outcomes):
        tag = o.code or (f"{o.dropped} dropped" if o.dropped else "all traced")
        lines.append(f"  {fid:4} {o.status:9} {tag:18} {o.question[:52]}")
    t = tally(outcomes)
    lines += ["", f"  ANSWERED {t[ANSWERED]}   PARTIAL {t[PARTIAL]}   REFUSED {t[REFUSED]}"]
    return "\n".join(lines)


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

    print("research_question")

    # ── evidence: real provisions, each cleared against the committed corpus ─
    ev = evidence(FIXTURES[0][1])
    check(len(ev) > 0, f"s.96 retrieves provisions ({len(ev)})")
    check(all(o.basis == public_only.PUBLIC_CORPUS for _, o in ev),
          "...each cleared against the corpus file it came from")
    check(all(s.kind == STATUTE for s, _ in ev),
          "...and admitted as STATUTE, not as a document reciting the law")
    check(len(ev) <= MAX_PROVISIONS,
          f"...capped at {MAX_PROVISIONS}, so the prompt is provisions and not the Act")
    check(evidence("How do I structure a slump sale to minimise stamp duty?") == (),
          "a question this corpus resolves nothing for retrieves nothing, rather than "
          "a near-miss provision")

    # ── the three outcomes, each reached on purpose ──────────────────────────
    outs = run_fixtures(model_for=quoting_model)
    t = tally(outs)
    print("\n" + report(outs) + "\n")
    check(t[ANSWERED] + t[PARTIAL] + t[REFUSED] == len(FIXTURES),
          "every fixture lands in exactly one of the three")
    check(t[ANSWERED] >= 1 and t[REFUSED] >= 1,
          f"both ANSWERED and REFUSED are reachable ({t}) -- a fixture set that only "
          f"ever reaches one of them measures nothing")
    codes = {o.code for o in outs if o.status == REFUSED}
    check(NO_EVIDENCE in codes,
          f"...and the refusals distinguish their kind ({sorted(c for c in codes if c)})")

    # ── a model that fabricates is refused, not served ───────────────────────
    ev6 = evidence(FIXTURES[0][1])
    srcs = tuple(s for s, _ in ev6)

    def liar(prompt: str) -> str:
        return (f"{quoted_span.SENTENCE_TAG} The company must hold the meeting within "
                f"forty-five days of the financial year end.\n"
                f"{quoted_span.QUOTE_TAG} within forty-five days of the financial year end\n")
    o_lie = answer(FIXTURES[0][1], model=liar, available=("gemini",))
    check(o_lie.status == REFUSED and o_lie.code == NOTHING_TRACED,
          f"an invented answer is REFUSED as NOTHING_TRACED ({o_lie.status}/{o_lie.code})")
    check("forty-five" not in o_lie.served,
          "...and the invented sentence does not reach a reader")
    check(NO_EVIDENCE != NOTHING_TRACED and o_lie.code != NO_EVIDENCE,
          "...distinguished from NO_EVIDENCE: a model WAS called and would not be repeated")

    # ── PARTIAL: some traced, some dropped, and the count is served ──────────
    def half(prompt: str) -> str:
        good = " ".join(srcs[0].text.split())[:150]
        return (f"{quoted_span.SENTENCE_TAG} {good}\n"
                f"{quoted_span.QUOTE_TAG} {good}\n"
                f"{quoted_span.SENTENCE_TAG} A penalty of five lakh rupees applies.\n"
                f"{quoted_span.QUOTE_TAG} a penalty of five lakh rupees applies\n")
    o_half = answer(FIXTURES[0][1], model=half, available=("gemini",))
    check(o_half.status == PARTIAL and o_half.dropped == 1,
          f"a half-true answer is PARTIAL, not ANSWERED ({o_half.status}, "
          f"{o_half.dropped} dropped)")
    check("five lakh" not in o_half.served,
          "...the dropped sentence is not served")
    # ── the cascade: deterministic -> small -> large (PLAN_23 O3) ───────────
    good = " ".join(srcs[0].text.split())[:150]
    honest_text = (f"{quoted_span.SENTENCE_TAG} {good}\n"
                   f"{quoted_span.QUOTE_TAG} {good}\n")
    tried = []

    def liar_stage(_p):
        tried.append("small")
        return (f"{quoted_span.SENTENCE_TAG} The company must hold it within forty-five "
                f"days.\n{quoted_span.QUOTE_TAG} within forty-five days\n")

    def honest_stage(_p):
        tried.append("large")
        return honest_text

    o_esc = answer(FIXTURES[0][1], available=("gemini",),
                   stages=[mc.Stage(mc.DETERMINISTIC, call=None,
                                    unpriced_note="no deterministic path yet"),
                           mc.Stage(mc.SMALL, liar_stage, model="small"),
                           mc.Stage(mc.LARGE, honest_stage, model="large")])
    check(tried == ["small", "large"],
          f"the small model runs FIRST and the large one only after L0 rejects {tried}")
    check(o_esc.status == ANSWERED,
          f"...and the escalated answer is served ({o_esc.status})")

    o_both = answer(FIXTURES[0][1], available=("gemini",),
                    stages=[mc.Stage(mc.SMALL, liar_stage, model="s"),
                            mc.Stage(mc.LARGE, liar_stage, model="l")])
    check(o_both.status == REFUSED and o_both.code == NOTHING_TRACED,
          f"every stage rejected is still REFUSED / NOTHING_TRACED, not served "
          f"({o_both.status}/{o_both.code})")

    # A transport error is FAILED, and is NOT an abstention.
    def dead(_p):
        raise ConnectionError("connection reset by peer")

    o_dead = answer(FIXTURES[0][1], available=("gemini",),
                    stages=[mc.Stage(mc.SMALL, dead, model="s"),
                            mc.Stage(mc.LARGE, honest_stage, model="l")])
    check(o_dead.status == FAILED and o_dead.code is None,
          f"a transport error is FAILED with NO refusal code ({o_dead.status}/"
          f"{o_dead.code}) -- nobody decided anything")
    check("ConnectionError" in o_dead.reason, "...carrying the error it reports")
    check(o_dead.served == "", "...and serves nothing")

    # An injected model is ONE stage: a caller who supplied one model did not ask for a
    # cascade over it, and running it twice would bill them twice.
    calls = []

    def once(_p):
        calls.append(1)
        return honest_text
    answer(FIXTURES[0][1], model=once, available=("gemini",))
    check(len(calls) == 1, f"an injected model is called ONCE ({len(calls)})")

    # ── claim attribution, and an event body that keeps its refusal ─────────
    o_ev = answer(FIXTURES[0][1], model=once, available=("gemini",),
                  event_key="share_allotment", facts={"foreign_investor": True})
    check(o_ev.status == PARTIAL,
          f"an answer whose EVENT reaches an unheld body is PARTIAL ({o_ev.status}), "
          f"even though every sentence traced")
    check("does not fully hold" in o_ev.reason,
          f"...and the reason says so rather than reporting a dropped sentence "
          f"({o_ev.reason[:60]})")
    check(o_ev.served and "45" not in o_ev.served,
          "...while the traced sentences are still served: PARTIAL is not a refusal")

    # The claims themselves attribute from the evidence path, not from a label.
    holder = {"origins": tuple(o for _, o in ev6)}
    v = _verifier(srcs, tuple(o for _, o in ev6), holder)
    acc, _why, claims = v(honest_text)
    check(acc and claims, "L0 admits an honest answer and produces claims")
    check(all(c.evidence_path for c in claims),
          "...each carrying the path of the corpus file its quote was found in")
    check(claim_bodies.bodies_for(claims) == ("CA2013",),
          f"...which attributes to CA2013 from the instrument, not from the source label "
          f"({claim_bodies.bodies_for(claims)})")

    check("did not trace" in o_half.served and "1 of 2" in o_half.served,
          "...and the reader is told one was dropped, in the body rather than a footnote")

    # ── refusals that never reach a model ────────────────────────────────────
    called = []
    o_ne = answer(FIXTURES[9][1], model=lambda p: called.append(1) or "",
                  available=("gemini",))
    check(o_ne.status == REFUSED and o_ne.code == NO_EVIDENCE and not called,
          f"NO_EVIDENCE refuses BEFORE any model call ({o_ne.code}, called={called})")
    o_nm = answer(FIXTURES[0][1], available=())
    check(o_nm.status == REFUSED and o_nm.code == NO_MODEL,
          f"with no provider at all it refuses as NO_MODEL ({o_nm.code})")

    # ── it is routed as NARRATION, which is why a free tier is legitimate ────
    o_ok = answer(FIXTURES[0][1], model=quoting_model(srcs), available=("gemini",))
    check(o_ok.route is not None and o_ok.route.provider == "gemini" and o_ok.route.degraded,
          f"with no Anthropic credit it runs on Gemini, MARKED DEGRADED "
          f"({o_ok.route.provider}, degraded={o_ok.route.degraded})")
    check(not o_ok.route.requires_review,
          "...and not flagged for review: narration is LOW consequence, and every "
          "sentence was checked against the Act before it was served")
    check(o_ok.to_dict()["degraded"] is True and "gemini" in o_ok.to_dict()["model"],
          "...and the degradation is in the record, not only in the log")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
