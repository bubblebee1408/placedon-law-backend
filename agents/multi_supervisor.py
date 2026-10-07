"""F2 — the supervisor: one researcher per (body of law, State), run in parallel, synthesised.

A compound question ("office leases in Bengaluru and Mumbai, and a share allotment to a
Singapore investor") reaches several bodies of law at once — some we hold, some we do not,
some Central, some per-State. The supervisor splits it by (body, State), researches ONLY the
bodies we hold, refuses the rest BY NAME, runs the held researchers in parallel, and lets
code — not a model — assemble the pieces into one PARTIAL answer.

## The split, and why refusals are not workers

`checker/jurisdiction` routes each topic to its bodies; `checker/scope` says which bodies we
hold. A HELD body (the Companies Act) becomes a worker: a `research_question` call that reads
the held text and quotes it. A NOT-HELD body (FEMA, a State's stamp duty) becomes a NAMED
REFUSAL — not a worker, because there is nothing to read, and sending a question about law we
do not hold to a model is how a confident guess gets made. A State topic with no State or no
date is NEED_FACT, from `jurisdiction.resolve`, never a guess.

## Parallel, verified, then synthesised by code

The held workers run in parallel (an injected executor; the production one rides the gateway
job queue, the gate one is a thread pool or a deterministic map). Each result is VERIFIED
before it reaches the blackboard — `agents/multi_runner` already enforces "only verified
results merge". Synthesis is code: the merged held answer, plus the named refusals, plus any
case-law **supporting authority** (never VERIFIED — a judgment may support an answer, never
make one). The model only phrases a held answer inside its worker; it decides nothing here.

The plan the supervisor builds is validated by `agents/multi_plan.validate` (registered
agents only, ≤8 workers, depth 1, budget reserved) — the validator is code, as F2 requires.
"""
from __future__ import annotations

import concurrent.futures as _futures
from dataclasses import dataclass, field

from agents import multi_plan as mp
from agents import multi_runner as mr
from checker import jurisdiction, scope

# The agent every held-body worker runs. Must be registered in multi_plan.WORKER_AGENTS, or
# the plan validator refuses it (UNKNOWN_AGENT) -- which is the point of naming it here.
RESEARCHER = "research_question"

PARTIAL = "PARTIAL"
ANSWERED = "ANSWERED"
NEED_FACT = "NEED_FACT"
REFUSED = "REFUSED"


@dataclass(frozen=True)
class SubQuestion:
    """One (body, State) slice of the compound question, and whether we can research it."""
    body: str                    # scope.py body key
    text: str                    # the sub-question a worker is asked
    held: bool                   # is the body in the corpus? held -> worker; else -> refusal
    state: str | None = None     # the State, for a State-qualified topic
    topic: str = ""              # the jurisdiction topic it came from
    need_fact: str | None = None # set => cannot even be asked; a NEED_FACT refusal


@dataclass(frozen=True)
class Refusal:
    """A named refusal for a body we do not hold (or a fact we are missing). Never silent."""
    body: str
    name: str
    reason: str
    state: str | None = None
    kind: str = "NOT_HELD"       # NOT_HELD | NEED_FACT


@dataclass(frozen=True)
class Outcome:
    status: str
    answer: str = ""                         # the merged, verified held answer (phrased)
    refusals: tuple[Refusal, ...] = ()       # FEMA, each State's stamp duty, NEED_FACTs
    support: tuple[dict, ...] = ()           # case law, SUPPORTING only — never VERIFIED
    gaps: tuple[str, ...] = ()
    sections: tuple[dict, ...] = ()          # ONE per (body, State), each with its own status
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"status": self.status, "answer": self.answer,
                "refusals": [r.__dict__ for r in self.refusals],
                "support": list(self.support), "gaps": list(self.gaps),
                "sections": list(self.sections), "detail": self.detail}


def _cities_in(text: str) -> tuple[str, ...]:
    """The known cities named in the question, in first-seen order. Routing, not parsing."""
    low = (text or "").lower()
    seen: list[str] = []
    # Longest names first so "new delhi" wins over "delhi".
    for city in sorted(jurisdiction.CITY_STATE, key=len, reverse=True):
        if city in low and jurisdiction.CITY_STATE[city] not in seen:
            seen.append(jurisdiction.CITY_STATE[city])
    return tuple(seen)


def _segments(question: str) -> tuple[str, ...]:
    """Split a compound question into clauses on commas, semicolons and a topic-joining 'and'.

    A segment is asked to ONE body, so a held worker researches its own slice ("a share
    allotment to a Singapore investor") rather than the whole question, which retrieves
    nothing on point. 'Bengaluru and Mumbai' is NOT split -- the 'and' joins two cities under
    one lease, and both are picked up as States of the same stamp-duty segment.
    """
    import re
    parts = re.split(r"[;,]|\band\s+(?=a\b|an\b|the\b)", question or "")
    return tuple(p.strip(" .") for p in parts if p.strip(" ."))


def decompose(question: str, *, as_of: str | None) -> tuple[SubQuestion, ...]:
    """Split a compound question into (body, State) sub-questions. Nothing is guessed.

    Per segment: a held Central body becomes one sub-question asked that segment; a State
    topic becomes one sub-question per State named in the segment (via its city); a State
    topic with no State/date becomes a single NEED_FACT sub-question rather than a silent drop.
    De-duplicated on (body, State) so the same body named twice is researched once.
    """
    subs: list[SubQuestion] = []
    seen: set[tuple[str, str | None]] = set()

    for segment in _segments(question) or (question,):
        topics = jurisdiction.topics_in(segment)
        cities_states = _cities_in(segment)
        for tkey in topics:
            t = jurisdiction.topic(tkey)
            states = (cities_states or (None,)) if t.needs_state else (None,)
            for st in states:
                res = jurisdiction.resolve(tkey, state=st, as_of=as_of) if t.needs_state \
                    else None
                for body in t.bodies:
                    key = (body, st)
                    if key in seen:
                        continue
                    seen.add(key)
                    b = scope.body(body)
                    subs.append(SubQuestion(
                        body=body, text=segment, held=b.answerable, state=st, topic=tkey,
                        need_fact=(res.need_fact if res else None)))
    return tuple(subs)


def plan(question: str, *, as_of: str | None) -> tuple[mp.MultiPlan, tuple[Refusal, ...],
                                                       tuple[SubQuestion, ...]]:
    """(plan of HELD-body workers, named refusals, all sub-questions).

    Held, researchable bodies become workers. Everything else — a body we do not hold, or a
    State topic missing its State/date — becomes a named refusal, recorded now so synthesis
    can state it rather than drop it.
    """
    subs = decompose(question, as_of=as_of)
    workers: list[mp.Task] = []
    refusals: list[Refusal] = []
    for s in subs:
        if s.need_fact:
            refusals.append(Refusal(s.body, scope.body(s.body).name, s.need_fact,
                                    state=s.state, kind=NEED_FACT))
        elif s.held:
            workers.append(mp.Task(RESEARCHER, s.text))
        else:
            refusals.append(Refusal(s.body, scope.body(s.body).name,
                                    scope.refusal_for(s.body), state=s.state, kind="NOT_HELD"))
    return mp.MultiPlan(goal=question, workers=tuple(workers)), tuple(refusals), subs


def _parallel_call(worker, tasks, *, max_workers: int):
    """Run `worker(task)` for every task CONCURRENTLY, once; cache (text | exception) by task.

    Returned is a `call(task)` the runner uses: it hands back the pre-computed result, raising
    the cached exception on a transport failure. The model calls therefore happen in parallel
    (the expensive, I/O-bound part), while the runner's verify/settle/merge stay ordered and
    deterministic. The production executor enqueues each worker on the gateway job queue; this
    thread-pool one is the same shape without a database.
    """
    cache: dict[int, object] = {}
    if tasks:
        with _futures.ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as ex:
            futs = {ex.submit(worker, t): i for i, t in enumerate(tasks)}
            for fut, i in futs.items():
                try:
                    cache[i] = fut.result()
                except Exception as e:                           # noqa: BLE001
                    cache[i] = e
    index = {id(t): i for i, t in enumerate(tasks)}

    def call(task):
        res = cache[index[id(task)]]
        if isinstance(res, Exception):
            raise res
        return res
    return call


def research(question: str, *, as_of: str | None, worker, verify, merge,
             budget=None, support=(), max_parallel: int = mp.MAX_WORKERS) -> Outcome:
    """Decompose, plan, run the held workers in parallel, synthesise by code.

    `worker(task) -> text` researches one held sub-question (it phrases; the gate injects a
    deterministic stand-in). `verify(text, task) -> text` byte-checks the quote and raises
    `multi_runner.Rejected` to refuse it. `merge(results) -> str` is the code synthesis of the
    verified held answers. `support` is case-law supporting authority, attached NEVER as a
    verified finding.
    """
    the_plan, refusals, subs = plan(question, as_of=as_of)

    # No held body to research: the whole question is refusals (and/or NEED_FACT). That is a
    # REFUSED outcome that NAMES every body, not an empty answer.
    def _refusal_sections() -> list:
        return [{"body": r.body, "name": r.name, "state": r.state,
                 "status": r.kind, "reason": r.reason} for r in refusals]

    if not the_plan.workers:
        status = NEED_FACT if any(r.kind == NEED_FACT for r in refusals) else REFUSED
        return Outcome(status, "", refusals, tuple(support), (),
                       sections=tuple(_refusal_sections()),
                       detail={"reason": "no held body of law is engaged; every part is "
                                         "named above", "subs": len(subs)})

    call = _parallel_call(worker, the_plan.workers, max_workers=max_parallel)
    run_out = mr.run(the_plan, call=call, verify=verify, merge=merge, budget=budget)

    gaps = tuple(run_out.gaps)
    # Code synthesis of the overall status. A held answer plus any named refusal is PARTIAL:
    # part was answered, part is not held, and saying so is the whole point.
    if run_out.status == mr.ANSWERED and refusals:
        status = PARTIAL
    elif run_out.status == mr.ANSWERED:
        status = ANSWERED
    elif run_out.status == mr.PARTIAL:
        status = PARTIAL
    else:                                    # NEEDS_LAWYER / REFUSED from the runner
        status = run_out.status

    # One section per (body, State). Held workers map to the held sub-questions in order
    # (plan() appends a worker per held sub, so worker i IS held_subs[i]); refusals follow.
    held_subs = [x for x in subs if x.held and not x.need_fact]
    by_index = {r.index: r for r in run_out.results}
    sections: list = []
    for i, sub in enumerate(held_subs):
        wr = by_index.get(i)
        answered = wr is not None and wr.state == mr.W_OK
        sections.append({"body": sub.body, "name": scope.body(sub.body).name,
                         "state": sub.state, "status": (ANSWERED if answered else "NEEDS_LAWYER"),
                         "text": (wr.text if answered else ""),
                         "reason": ("" if answered else (wr.reason if wr else "no result"))})
    sections.extend(_refusal_sections())

    return Outcome(status, run_out.merged, refusals, tuple(support), gaps,
                   sections=tuple(sections),
                   detail={"held_workers": len(the_plan.workers),
                           "runner_status": run_out.status,
                           "verified": run_out.detail.get("verified")})


# ── gate stand-ins: a deterministic held-body researcher and verifier, no model, no network ──
def _held_researcher(quote_source=None):
    """A worker that reads the held corpus and QUOTES it, standing in for the model's phrasing.

    It uses `research_question.evidence`/`quoting_model` so the quote BYTE-MATCHES real held
    text — the gate's answer is a real Companies Act quote, not invented prose. No key, no
    network: `quoting_model` is a pure function of the retrieved sources.
    """
    from agents import research_question as rq

    def worker(task: mp.Task) -> str:
        srcs = tuple(s for s, _o in rq.evidence(task.task))
        if not srcs:
            # Nothing on point in the held corpus: let the verifier refuse it, rather than
            # inventing an answer. Returning "" makes verify raise Rejected below.
            return ""
        model = rq.quoting_model(srcs)
        return model(task.task)
    return worker


def _byte_match_verify(text: str, task: mp.Task) -> str:
    """Admit a worker result only if it carries a quote that byte-matches the held corpus.

    The quote lives between quoted_span's tags; it must appear verbatim in the sub-question's
    own retrieved sources. A result with no such quote is Rejected -- the same rule the
    research path enforces, applied here before the blackboard.
    """
    from agents import research_question as rq
    from checker import quoted_span
    if not (text or "").strip():
        raise mr.Rejected("the worker returned nothing to verify")
    pairs = quoted_span.parse(text)
    if not pairs:
        raise mr.Rejected("the result carries no SENTENCE/QUOTE block to check")
    sources = " ".join(" ".join(s.text.split()) for s, _o in rq.evidence(task.task))
    for _sentence, quote in pairs:
        needle = " ".join((quote or "").split())
        if needle and needle in sources:
            return text
    raise mr.Rejected("the result's quote does not byte-match the held corpus")


def supporting_case_law(index, query: str, *, limit: int = 3) -> tuple[dict, ...]:
    """Judgments that SUPPORT an answer, from the open-eCourts case-law index. Never VERIFIED.

    Every hit is tier LICENSED at the source (checker/sources/case_law), which `tiers` forbids
    from making an answer VERIFIED. They are attached to the Outcome as `support` so a reader
    sees the authority behind the held answer, not folded into it as a finding.
    """
    return tuple(h.to_dict() for h in index.search(query, limit=limit))


def _code_merge(results) -> str:
    """Synthesis by CODE: join the verified held answers. The model phrased each; this does not."""
    return "\n\n".join(r.text for r in results if getattr(r, "text", ""))


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("multi_supervisor")

    # ── decomposition splits the compound question by (body, State) ─────────
    Q = ("5-year office leases in Bengaluru and Mumbai, and a share allotment to a "
         "Singapore investor")
    subs = decompose(Q, as_of="2026-10-07")
    bodies = {(s.body, s.state) for s in subs}
    check(("CA2013", None) in bodies, "the share allotment is a Companies Act sub-question")
    check(("FEMA1999", None) in bodies, "the Singapore investor is a FEMA sub-question")
    check(("STAMP", "Karnataka") in bodies and ("STAMP", "Maharashtra") in bodies,
          f"the two leases are per-State stamp-duty sub-questions ({sorted(bodies)})")

    the_plan, refusals, _ = plan(Q, as_of="2026-10-07")
    check(all(w.agent == RESEARCHER for w in the_plan.workers),
          "every worker is the registered researcher agent")
    check(mp.validate(the_plan, budget=None).ok,
          "the plan passes the code validator (registered agents, <=8, depth 1)")
    rbodies = {(r.body, r.state) for r in refusals}
    check(("FEMA1999", None) in rbodies and ("STAMP", "Karnataka") in rbodies
          and ("STAMP", "Maharashtra") in rbodies,
          f"FEMA and each State's stamp duty are NAMED refusals, not workers ({sorted(rbodies)})")

    # ── the done-when: PARTIAL, CA2013 answered+quoted, the rest refused by name ──
    out = research(Q, as_of="2026-10-07", worker=_held_researcher(),
                   verify=_byte_match_verify, merge=_code_merge)
    check(out.status == PARTIAL,
          f"the compound question returns PARTIAL ({out.status})")
    check(out.answer.strip() != "",
          "the Companies Act part is answered (a real, verified, quoted held answer)")
    named = {(r.body, r.state) for r in out.refusals}
    check(("FEMA1999", None) in named,
          "FEMA is refused by name -- never guessed, never silent")
    check(("STAMP", "Karnataka") in named and ("STAMP", "Maharashtra") in named,
          f"each State's stamp duty is refused by name ({sorted(named)})")

    # ── a State topic with no State/date is NEED_FACT, not a guess ──────────
    nf = decompose("what stamp duty applies to this lease", as_of=None)
    check(any(s.need_fact for s in nf if s.body == "STAMP"),
          "a lease with no city/State/date yields a NEED_FACT stamp-duty sub-question")
    nf_out = research("what stamp duty applies to this lease", as_of=None,
                      worker=_held_researcher(), verify=_byte_match_verify, merge=_code_merge)
    check(nf_out.status == NEED_FACT and any(r.kind == NEED_FACT for r in nf_out.refusals),
          f"...and the outcome is NEED_FACT, naming what is missing ({nf_out.status})")

    # ── a plain held question answers, no refusals ──────────────────────────
    ca = research("What is the time limit for filing the annual return under section 92?",
                  as_of="2026-10-07", worker=_held_researcher(),
                  verify=_byte_match_verify, merge=_code_merge)
    check(ca.status == ANSWERED and not ca.refusals,
          f"a wholly-held question is ANSWERED with no refusals ({ca.status})")

    # ── case law rides along as SUPPORTING authority only, never VERIFIED ───
    from checker.sources.case_law import CaseLawIndex
    from checker.sources.tiers import can_verify
    _rows = [
        {"path": "1951_2_3_9", "citation_year": 1951, "nc_display": "1951INSC7",
         "case_name": "The annual return and its filing under the Companies Act"},
        {"path": "1950_1_15_25", "citation_year": 1950, "nc_display": "1950INSC1",
         "case_name": "A company must hold an annual general meeting every year"},
    ]
    _idx = CaseLawIndex("aws_sc_judgments", _rows)
    support = supporting_case_law(_idx, "annual return filing companies act")
    check(len(support) >= 1, f"the case-law index returns supporting judgments ({len(support)})")
    check(all(h["tier"] == "LICENSED" for h in support),
          "every supporting judgment is tier LICENSED at the source")
    check(all(not can_verify(h["tier"]) for h in support),
          "...and LICENSED can NEVER make an answer VERIFIED -- support, not a finding")
    sup_out = research("What is the time limit for filing the annual return under section 92?",
                       as_of="2026-10-07", worker=_held_researcher(),
                       verify=_byte_match_verify, merge=_code_merge, support=support)
    check(sup_out.status == ANSWERED and len(sup_out.support) == len(support),
          "the answer carries its supporting case law alongside, not merged into the finding")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
