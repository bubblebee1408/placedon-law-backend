"""ask: the research question path, and its bounded decomposition (O5)."""
from __future__ import annotations

from gateway.verbs import model_access
from gateway.verbs.answers import _citations_from_summary
from gateway.verbs.ask_layers import (_apply_critic, _cache_lookup, _cache_store,
    _critic_enabled)
from gateway.verbs.company import PROFILE_SOURCE, _company_facts, _profile_facts
from gateway.verbs.core import Context, _affirmed, _law_date, _long_date, _refuse
from gateway.verbs.model_access import _provider_not_ready, task_providers
from gateway.verbs.research import _research_cases, _sources_report
from gateway.verbs.run_records import _persist_run


def _ask(args: dict, ctx: Context) -> dict:
    """`ask`, with the firm's stored company profile shown when the caller sent no facts.

    The profile facts are attached AFTER the answer, so they never enter the answer cache
    (whose key does not carry facts) and a cache hit still shows the current profile. Like
    facts sent with the request, they are recorded and shown and do not steer the answer.
    """
    d = _ask_answer(args, ctx)
    if args.get("company_facts") is not None or d.get("status") == "REFUSED":
        return d
    facts = _profile_facts(ctx)
    if not facts:
        return d
    return dict(d, user_facts=[f.to_dict() for f in facts],
                user_facts_from=PROFILE_SOURCE,
                user_facts_note=(
                    "From your company profile, as confirmed there. Shown so you can see "
                    "what we hold; they did not change this answer, which is read from "
                    "the held Act. No company fact is ever VERIFIED."))


def _ask_answer(args: dict, ctx: Context) -> dict:
    from agents import research_question as rq
    from checker import router
    from gateway import progress as _progress
    q = (args.get("question") or "").strip()
    if not q:
        return _refuse("BAD_REQUEST", "question is required")
    _progress.mark(_progress.UNDERSTANDING)
    # A past date reads each section as it stood then (checker/as_of.py), behind a flag.
    law_date, refusal = _law_date(args.get("as_of"), ctx)
    if refusal:
        return refusal
    if law_date and _affirmed(args.get("decompose")):
        return _refuse("BAD_REQUEST", "decompose cannot be combined with a past as_of yet")

    # The RESOURCE router (not `checker/router.py`, which picks the MODEL). A conservative,
    # deterministic, no-model-call text classifier: CASE routes to judgment discovery
    # instead of the held statute; STATUTE and UNSURE fall straight through to the
    # unchanged path below -- UNSURE is treated exactly like STATUTE on purpose, so an
    # ambiguous query never silently loses the statute search it would otherwise get.
    allowed = args.get("available")
    if allowed is not None and not (isinstance(allowed, (list, tuple))
                                    and all(isinstance(p, str) for p in allowed)):
        return _refuse("BAD_REQUEST", "available must be a list of provider names")
    # A caller may NARROW the task's providers, never widen them, and an empty or
    # disallowed list narrows to nothing -- a refusal, not the default route.
    providers = task_providers("ask") if allowed is None else tuple(
        p for p in task_providers("ask") if p in allowed)

    from checker import resource_route
    _route = resource_route.classify(q)
    if _route.resource == resource_route.CASE:
        return _ask_case(q, _route, ctx)

    user_facts, refusal = _company_facts(args.get("company_facts"))
    if refusal:
        return refusal

    # O5. Decompose BEFORE the cache: each sub-question is cached on its own, which is
    # where the reuse actually is -- "what notice is required" recurs across many compound
    # questions that are each asked once.
    if _affirmed(args.get("decompose")):
        return _ask_decomposed(q, args, ctx)

    # O9. The cache is consulted ONLY when no company facts were supplied: a fact-dependent
    # answer is an answer about one company, and the key does not carry the facts, so a hit
    # would serve one company's answer to a question asked about another.
    hit, cache_key = (None, None)
    # Never for a past date: the cache gate re-verifies against today's text.
    if ctx.store is not None and not user_facts and law_date is None:
        hit, cache_key = _cache_lookup(q, "RESEARCH_QUESTION", args.get("sources"), ctx)
    if hit is not None:
        return hit

    # The source picker. Retrieval searches ONLY the picked sources; the default is the held
    # corpus plus the vault. Only HELD is connected to this answer path; the report names
    # the unavailable vault grounding and external retrieval explicitly.
    from checker import source_picker as _sp
    _picked = args.get("sources")
    _resolved = _sp.resolve(_picked)
    _held_searched = _sp.HELD_ID in _resolved.searchable
    if _held_searched:
        _progress.mark(_progress.SEARCHING)
    ev = rq.evidence(q, as_of=law_date) if _held_searched else ()
    # The per-source report is built once, from the retrieval that actually ran, and travels
    # on EVERY return path -- including a NO_MODEL refusal -- so "which sources were searched"
    # is answered even when no model was available to phrase the answer.
    _report = _sources_report(_picked, _resolved, ev, q, ctx)
    # `ask` answers only from the held statute. If the held corpus was not picked, it reads
    # nothing to answer from and ABSTAINS -- rather than letting the answer path re-retrieve
    # the held corpus and quietly ignore the caller's pick. The report still records every
    # picked source's state without pretending a selected source was used as evidence.
    if not _held_searched:
        rid = _persist_run(ctx, intent="research_question", status="ABSTAINED",
                           steps=[{"capability": "intake", "status": "ANSWERED"},
                                  {"capability": "research", "status": "ABSTAINED"}],
                           propositions=[])
        return {"status": "ABSTAINED", "answer": "", "citations": [],
                "abstained_reason": (
                    "the held corpus was not among the picked sources, and `ask` reads the "
                    "held statute, so nothing was read. This is not a finding that no "
                    "obligation exists. Each picked source's state is in `sources`."),
                "run_id": rid, "sources": _report}
    law_as_of = None
    if law_date is not None:
        sections = rq.law_as_of(q, law_date)
        law_as_of = {"date": law_date.isoformat(),
                     "rebuilt": any(x["rebuilt"] for x in sections),
                     "sections": sections}
        if sections and not ev:
            # Retrieval found the provisions; none has recoverable wording on that date.
            why = " ".join(f"{x['provision']}: {x['note'] or 'not yet in the Act on that date.'}"
                           for x in sections)
            return {"status": "REFUSED", "code": "AS_OF_NOT_RECOVERABLE",
                    "detail": (f"The wording of {', '.join(x['provision'] for x in sections)} "
                               f"as it stood on {_long_date(law_date)} cannot be recovered "
                               f"from India Code's amendment notes, so no answer is given "
                               f"for that date. {why}"),
                    "law_as_of": law_as_of, "sources": _report,
                    "run_id": _persist_run(
                        ctx, intent="research_question", status="REFUSED",
                        refusal_code="AS_OF_NOT_RECOVERABLE",
                        steps=[{"capability": "intake", "status": "ANSWERED"},
                               {"capability": "research", "status": "REFUSED"}],
                        propositions=[])}
    origins = tuple(o for _, o in ev)
    served, refusal = (None, None)
    if origins:
        typed, blocked = model_access._typed_text_origin(q, name="research question", task="ask", ctx=ctx)
        if blocked:
            blocked["run_id"] = _persist_run(
                ctx, intent="research_question", status="REFUSED", refusal_code=blocked["code"],
                steps=[{"capability": "intake", "status": "ANSWERED"},
                       {"capability": "research", "status": "REFUSED"}],
                propositions=[])
            blocked["sources"] = _report
            return blocked
        origins = origins + (typed,)
        served, refusal = model_access._served_or_refusal(origins, name="ask",
                                             purpose=router.NARRATION, ctx=ctx,
                                             allowed_providers=providers)
        if refusal:
            refusal["run_id"] = _persist_run(
                ctx, intent="research_question", status="REFUSED",
                refusal_code=refusal["code"],
                steps=[{"capability": "intake", "status": "ANSWERED"},
                       {"capability": "research", "status": "REFUSED"}],
                propositions=[])
            refusal["sources"] = _report
            return refusal

    try:
        from gateway import models as _models
        # The provider serve() chose, not the declared list (a test stub keeps the list): rq re-routes over `available`
        # to record which model answered, and the declared list would record Bedrock.
        _progress.mark(_progress.WRITING)
        out = rq.answer(q, model=served.call if served else None,
                        available=((served.provider,) if served and served.provider
                                   in _models.SERVEABLE else providers),
                        as_of=law_date)
    except _provider_not_ready() as e:                           # B1
        # PROVIDER_NOT_READY is its OWN typed state: the model provider (Bedrock) is not
        # ready yet -- the account is being verified, or model access is pending. That is
        # neither a transport FAILURE (we did not break) nor a NOT_FOUND nor an abstention
        # (we read the law and did not decline it). No answer was produced, so no run is
        # recorded -- a judgement in the audit record where there was none would be worse.
        return {"status": "PROVIDER_NOT_READY", "code": "PROVIDER_NOT_READY",
                "detail": f"{type(e).__name__}: {str(e)[:200]}",
                "note": "the India model provider is not ready yet (account verification or "
                        "model access pending). This is a provider state, not a refusal of "
                        "the question and not an abstention; retry once it is ready."}
    except Exception as e:                                       # noqa: BLE001
        # FAILED, not REFUSED: we tried and the attempt broke. Only a transport error
        # reaches here -- a decision not to call is handled above.
        rid = _persist_run(ctx, intent="research_question", status="FAILED",
                           steps=[{"capability": "research", "status": "FAILED"}],
                           propositions=[])
        return {"status": "FAILED", "error": f"{type(e).__name__}: the provider request could not finish",
                "run_id": rid, "sources": _report}

    _progress.mark(_progress.CHECKING)
    d = out.to_dict()
    # The traced spans, as citations. `to_dict()` carries the provision NAMES and not the
    # spans, so the conversation layer had nothing to build citations[] from and shipped it
    # empty for every task. The Summary has them; this is where they leave.
    cite_index: dict = {}
    if out.summary is not None:
        d["citations"] = _citations_from_summary(out.summary, ev, index_out=cite_index)
    if user_facts:
        # PLAN_26 S2-alt: accepted, labelled "you told us", never presented as verified.
        # They are RECORDED AND SHOWN and they do not steer the answer -- the answer is
        # built from the held statute by deterministic engine calls, and threading an
        # unverified company fact into that is a Ring 0 change this step did not make.
        # Said in the payload rather than left for a reader to discover.
        d["user_facts"] = [f.to_dict() for f in user_facts]
        d["user_facts_note"] = (
            "Recorded as you told them to us, and shown back so you can see what we hold. "
            "They did not change this answer: it is read from the held Act. No company "
            "fact is ever VERIFIED.")
    # The ANSWER, with its citations. to_dict() carries the verdict and the provisions but
    # not the prose, so the verb returned everything about an answer except the answer.
    # Summary.prose() is the served form: traced sentences with their spans, and the count
    # of any that were dropped stated in the body rather than a footnote.
    d["answer"] = out.served
    if (_affirmed(args.get("critic")) or _critic_enabled()) and out.summary is not None:
        d = _apply_critic(d, out.summary, ctx, cite_index=cite_index)
    fields = served.step_fields() if served else {}
    d["run_id"] = _persist_run(
        ctx, intent="research_question", status=out.status,
        refusal_code=out.code if out.status == "REFUSED" else None,
        steps=[{"capability": "intake", "status": "ANSWERED"},
               {"capability": "research", "engine_capability": "law.acquisition_exposure",
                "status": out.status, **fields}],
        propositions=[{"status": "VERIFIED" if s.traced else "UNVERIFIED",
                       "source_ref": (s.citation.source_id
                                      if getattr(s, "citation", None) else None),
                       "span_start": None, "span_end": None}
                      for s in (out.summary.sentences if out.summary else ())],
        # Held law read -- not the cleared question (a client-text origin has no blob).
        law_versions={o.path: o.blob for o in origins if o.basis != "MATTER"},
        # CAL-1. `entailed` is None on this path, so the score is not computed and the
        # note records which half is missing -- see `nonconformity_for`.
        traced=len(out.summary.traced) if out.summary else 0,
        sentences=len(out.summary.sentences) if out.summary else 0)
    d["sources"] = _report
    if law_as_of is not None:
        d["law_as_of"] = law_as_of
        if d.get("status") == "ANSWERED" and any(
                x["fidelity"] == "PARTIAL" for x in law_as_of["sections"]):
            d["status"] = "PARTIAL"     # part of the wording on that date is not known
    _cache_store(cache_key, q, "RESEARCH_QUESTION", args.get("sources"), d, ctx)
    return d


def _ask_case(question: str, route, ctx: Context) -> dict:
    """A case-shaped question (`resource_route.CASE`), answered from judgment DISCOVERY
    instead of the held statute.

    Reuses `_research_cases` wholesale -- same index, same terms gate, same tier-LICENSED
    rows -- rather than a second call into `judgment_index.discover`, so there is exactly
    one place that decides which judgment sources are permitted. The shape returned here
    matches `_ask`'s own success/abstain shape (`status`/`answer`/`citations`/`run_id`/
    `sources`) so it flows through `_envelope_for` unchanged, plus two additive fields
    (`judgments`, `resource`) nothing downstream reads yet.

    Tier LICENSED (CLAUDE.md): a judgment may SUPPORT, never VERIFY. So this never builds a
    `citations` entry (every one needs a byte-matched `quote`, which would mean fetching and
    quoting the PDF here -- the verbatim read belongs to `judgments_open.OpenJudgments` on
    OPEN, not to this list) and never touches the obligation register. `resource="case"`
    tells `_bodies_from_ask` the held corpus was never searched, not that it was searched
    and found nothing -- the distinction R-018 exists to keep honest.
    """
    found = _research_cases({"query": question}, ctx)
    judgments = found.get("judgments") or []
    status = "PARTIAL" if judgments else "ABSTAINED"
    rid = _persist_run(
        ctx, intent="research_question", status=status,
        steps=[{"capability": "intake", "status": "ANSWERED"},
               {"capability": "case_discovery", "status": status}],
        propositions=[])
    sources = {"picked": ["held"], "searched": [],
               "report": [{"id": "held", "tier": "HELD", "status": "available",
                          "outcome": "NOT_SEARCHED", "hits": 0,
                          "reason": ("the resource router read this as a case-law lookup "
                                     f"({route.rule}), so the held statute was not "
                                     "searched")}],
               "judgments": judgments, "not_searched": found.get("not_searched") or [],
               "note": found.get("note") or ""}
    if judgments:
        lines = [
            f"- {j['title']} ({j.get('court') or 'Supreme Court'}, {j['year']}) -- "
            f"parties: {', '.join(j.get('parties') or []) or 'not recorded'}."
            for j in judgments]
        answer = (
            f"Found {len(judgments)} judgment(s) by party/case name that may support this "
            f"(tier LICENSED: supporting authority, never a verified statutory answer, and "
            f"no obligation rests on it):\n" + "\n".join(lines) +
            "\nOpen one to read a verbatim, byte-quoted passage -- nothing above is a "
            "citation.")
    else:
        answer = (
            "No judgment matched this by party, case title, or year. We searched the "
            "judgment index (the licensed Supreme Court / High Court eCourts metadata, "
            "not the Companies Act), and this is not a finding about the law: a case we "
            "did not find is not a case that does not exist. Discovery matches on party "
            "and case names, not legal topic -- naming a party, or the year, is most "
            "likely to find it.")
    return {"status": status, "answer": answer, "citations": [], "judgments": judgments,
            "resource": "case", "resource_rule": route.rule, "run_id": rid,
            "sources": sources}


# ── O5: bounded decomposition ────────────────────────────────────────────────

_SPLIT_PROMPT = (
    "Split the question below into the smallest number of INDEPENDENT sub-questions that "
    "together cover it, at most {n}. Each must be answerable on its own against Indian "
    "company law. If it does not split, return it unchanged.\n"
    "Reply with one sub-question per line, numbered 1., 2., ... and nothing else.\n\n"
    "Question: {q}\n")


def _split_proposer(ctx: Context):
    """`propose(question) -> [str]` from the routed model, or one that raises.

    Raising is the designed failure: `decompose.plan` turns a proposer that raises into a
    single sub-question, which is the original. So "no model could be served" costs the
    SPLIT and never the answer.
    """
    from checker import decompose, public_only, router

    def propose(question: str):
        origin = public_only.clear_matter(question, name="question to split",
                                          provider=router.AZURE)
        served, refusal = model_access._served_or_refusal((origin,), name="decompose",
                                             purpose=router.CLASSIFICATION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            raise RuntimeError(f"no model to split the question: {refusal['code']}")
        raw = str(served.call(_SPLIT_PROMPT.format(n=decompose.MAX_SUBQUESTIONS,
                                                   q=question)) or "")
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # "1. text" or "1) text"; anything else is taken whole rather than dropped.
            parts = line.split(".", 1) if "." in line[:3] else line.split(")", 1)
            text = (parts[1] if len(parts) == 2 and parts[0].strip().isdigit()
                    else line).strip()
            if text:
                out.append(text)
        return out

    return propose


def _ask_decomposed(question: str, args: dict, ctx: Context) -> dict:
    """Split, answer each part through the FULL ask path, join only what is cited.

    Each part is a real `_ask` -- the same retrieval, the same verifier, the same cache --
    so a sub-answer is verified exactly as a whole answer is. `decompose` is not passed
    down, which is what makes the depth one and keeps four the whole budget rather than
    four per level.
    """
    from checker import decompose as dc

    subs = dc.plan(question, propose=_split_proposer(ctx))
    if len(subs) == 1 and subs[0].strip().lower() == question.strip().lower():
        # It did not split. Answer it whole rather than wrapping one part in a synthesis
        # that would report "1 sub-question" about a question nobody divided.
        return _ask({k: v for k, v in args.items() if k != "decompose"}, ctx)

    parts, run_ids = [], []
    for sub in subs:
        inner = dict(args)
        inner.pop("decompose", None)
        inner["question"] = sub
        r = _ask(inner, ctx)
        if r.get("run_id"):
            run_ids.append(r["run_id"])
        parts.append(dc.Part(
            question=sub, status=str(r.get("status") or ""),
            answer=str(r.get("answer") or ""),
            citations=tuple(r.get("citations") or ()),
            failure=str(r.get("detail") or r.get("error") or "")))
    syn = dc.synthesise(parts, proposed=len(subs))
    out = syn.to_dict()
    out["sub_run_ids"] = run_ids
    # The run that RECORDS the decomposition. Its steps name each sub-question, so
    # runs.trace shows what was asked rather than one opaque "research" step.
    out["run_id"] = _persist_run(
        ctx, intent="research_question", status=syn.status,
        steps=[{"capability": "intake", "status": "ANSWERED",
                "cost_note": "the split is one model call, priced on its own run"}]
              + [{"capability": f"research.part{i}", "status": p.status or "FAILED",
                  "cost_note": f"sub-question: {p.question[:80]}"}
                 for i, p in enumerate(parts, 1)],
        propositions=[])
    return out
