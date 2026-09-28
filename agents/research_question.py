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

from agents.state import (ANSWERED, NO_EVIDENCE, NO_MODEL, NOTHING_TRACED,
                          OUT_OF_SCOPE_LAW, PARTIAL, REFUSED)
from checker import ask_scope, public_only, quoted_span, router, scope, section_index
from backend.budget import FREE_TIER_RPD_PER_MODEL
from checker.gemini_model import ModelBusy, ModelRateLimited
from checker.ollama_runner import ModelUnavailable as OllamaUnavailable
from checker.ollama_runner import OllamaRunner
from checker.lawyer_summary import STATUTE, Source, Summary
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


def answer(question: str, *, model=None, available=None, budget=None) -> Outcome:
    """One question, to one of ANSWERED / PARTIAL / REFUSED.

    `model` is injected -- a `Callable[[str], str]` -- so the tests reach no network. When
    it is None the route decides, and the clearance for the free-tier call is bound from
    the evidence that was just cleared.
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

    task = router.Task("research.narrate", router.TEXT, router.LOW,
                       purpose=router.NARRATION)
    have = available if available is not None else router.providers_available()

    # A busy model is not an unavailable provider. Measured on the first live run of
    # these fixtures: gemini-3.6-flash returned 503 six times running while
    # gemini-3.1-flash-lite answered throughout, and treating the 503 as a refusal threw
    # away six questions the next row could have answered. ModelBusy retries the NEXT
    # row; ModelRetired and everything else do not, because no retry fixes those.
    busy: set[str] = set()
    _last = ""
    route = summary = None
    while True:
        try:
            route = router.route(task, available=have, exclude_models=frozenset(busy))
        except router.NoRoute as e:
            return Outcome(REFUSED, question, NO_MODEL,
                           (f"every model was unavailable ({', '.join(sorted(busy))}): "
                            f"{_last} " if busy else "") + str(e),
                           provisions=names)

        call = model
        if call is None:
            if route.provider == router.GEMINI:
                from checker import gemini_model
                call = gemini_model.as_text_model(origin=origins, model=route.model,
                                                  budget=budget)
            elif route.provider == router.OLLAMA:
                # No public-corpus clearance is bound here, and that is the point rather
                # than an omission: `ollama_runner.local_model()` has already refused a
                # `:cloud` model, so the prompt does not leave this machine. The
                # clearance exists because a free tier's terms let it train on what it
                # is sent; there is no third party here to send anything to.
                                call = OllamaRunner(route.model)
            else:
                return Outcome(REFUSED, question, NO_MODEL,
                               f"no text callable is wired for {route.provider}/"
                               f"{route.model}", provisions=names, route=route)
        try:
            summary = quoted_span.summarise(
                sources, model=call, base_system=_SYSTEM, question=question,
                model_name=route.model, budget=None if call is not model else budget)
            break
        except ModelBusy:
            busy.add(route.model)
            continue
        except OllamaUnavailable as e:
            # The local server is not answering. Same shape as a 503: try the next row.
            busy.add(route.model)
            _last = str(e)
            continue
        except ModelRateLimited as e:
            # A quota, not a fault. The first version refused here, reasoning that the
            # next model has its own 20-a-day and spending it buys one question and
            # costs tomorrow's. That reasoning holds for the next FREE-TIER row and not
            # for the one after it: the last narration row is the operator's own
            # machine, which has no quota at all, and refusing a question while a local
            # model sits idle is the wrong trade however it is argued. So it falls
            # through like a 503 -- and the quota is remembered, so that if nothing
            # answers, the refusal names it rather than saying "no route".
            busy.add(route.model)
            _last = (f"the free tier's quota for {route.model} is spent "
                     f"({FREE_TIER_RPD_PER_MODEL} requests/day/model, measured); "
                     f"{str(e)[:120]}")
            continue

    traced, dropped = len(summary.traced), len(summary.refused)
    if not traced:
        return Outcome(REFUSED, question, NOTHING_TRACED,
                       summary.refusal_reason() or "nothing traced",
                       summary=summary, provisions=names, route=route, dropped=dropped)
    status = ANSWERED if not dropped else PARTIAL
    return Outcome(status, question, None,
                   "every sentence traced" if not dropped else
                   f"{traced} sentence(s) traced, {dropped} dropped as unsupported",
                   summary=summary, provisions=names, route=route, dropped=dropped)


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
