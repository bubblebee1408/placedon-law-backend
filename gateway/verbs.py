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
        law_versions={o.path: o.blob for o in origins})
    return d


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
                 law_versions: dict | None = None) -> str | None:
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
    ctx.store.write({"id": run_id, "intent": intent, "status": status,
                     "refusal_code": refusal_code, "law_versions": law_versions,
                     "steps": steps, "propositions": propositions})
    return run_id


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
    return {"run_id": row.get("id"), "steps": row.get("steps", [])}


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
}


def queue_handlers(ctx: "Context") -> dict:
    """{intent: handler(args) -> (steps, result)} for gateway/worker.py.

    Each one runs the request-path handler against a STORE-LESS context, so it builds its
    steps and its answer without writing a second run, then hands both back. The worker owns
    the persistence; the handler owns the meaning. One implementation, two callers.
    """
    from dataclasses import replace as _replace

    def wrap(fn):
        def run(args: dict):
            inner = _replace(ctx, store=None, last_steps=[])
            result = fn(args, inner)
            return list(inner.last_steps), result
        return run

    by_name = {"_review_document": _review_document,
               "_review_contract": _review_contract,
               "_ask": _ask}
    return {intent: wrap(by_name[fn]) for intent, fn in QUEUED_INTENTS.items()}


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
}

# Tasks whose work is long enough to belong on the queue rather than on the socket. Keyed
# to QUEUED_INTENTS so a task cannot be queued for an intent no worker serves.
TASK_INTENT: dict[str, str] = {
    "RESEARCH_QUESTION": "research_question",
    "REVIEW_CONTRACT": "review_contract",
    "REVIEW_DOCUMENT": "review_document",
}


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


def _bodies_from_ask(result: dict) -> list:
    """An `ask` result -> envelope bodies, read from checker/scope.py.

    The held Act is ANSWERED when anything was traced and ABSTAINED-shaped otherwise; a
    body the question named that we do not hold is NOT_HELD with the REGISTER'S OWN words,
    never a sentence composed here. That is what makes a CA2013 + FEMA question come back
    PARTIAL rather than confidently short.
    """
    from gateway import envelope as ev
    from checker import scope
    out = []
    held = scope.body("CA2013")
    traced = bool(result.get("provisions") or result.get("citations"))
    out.append(ev.body(held.key, held.name,
                       ev.B_ANSWERED if traced else ev.B_NEED_FACT,
                       "held and read" if traced else
                       "held, and nothing on point was found for this question"))
    refusal = result.get("refusal") or {}
    for key in result.get("out_of_scope_bodies") or refusal.get("bodies") or ():
        try:
            b = scope.body(key)
        except Exception:                                       # noqa: BLE001
            continue
        if b.key == held.key:
            continue
        out.append(ev.body(b.key, b.name,
                           ev.B_CURRENT_ONLY if b.status == scope.CURRENT_ONLY
                           else ev.B_NOT_HELD,
                           scope.refusal_for(b.key)))
    return out


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
                  files=(), ctx: Context) -> dict:
    """One result from one task -> one envelope. The only place a reply is shaped."""
    from gateway import envelope as ev

    trace = f"{V2}/runs/{run_id}/trace" if run_id else None
    if result.get("status") == "FAILED":
        return ev.failed(task=task, as_of=as_of,
                         detail=str(result.get("error") or "the step did not complete"),
                         run_id=run_id, trace_url=trace)

    bodies = (_bodies_from_events(result) if task == "EVENT_ASSESS"
              else _bodies_from_ask(result) if task == "RESEARCH_QUESTION" else [])
    text = (result.get("answer") or result.get("detail")
            or result.get("note") or "See the findings.")
    blocks = [{"text": str(text), "citation_ids": []}] if str(text).strip() else []
    unheld = [b for b in bodies if b["status"] in (ev.B_NOT_HELD, ev.B_CURRENT_ONLY)]
    answered = [b for b in bodies if b["status"] == ev.B_ANSWERED]
    if result.get("status") == "REFUSED":
        status = ev.ABSTAINED
    elif unheld and answered:
        status = ev.PARTIAL
    elif unheld and not answered:
        status = ev.ABSTAINED
    else:
        status = ev.ANSWERED
    return ev.build(status=status, task=task, as_of=as_of, text_blocks=blocks,
                    bodies=bodies, citations=[], files=list(files), run_id=run_id,
                    trace_url=trace)


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
    raw_ids = args.get("file_ids")
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list) or not all(isinstance(f, str) for f in raw_ids):
        return _refuse("BAD_REQUEST", "file_ids must be a list of strings")
    if not text.strip() and not raw_ids:
        return _refuse("BAD_REQUEST", "text or at least one file_id is required")
    as_of = (args.get("as_of") or "").strip() or _today(ctx)
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
        return {"conversation_id": cid, "message_id": reply_id,
                "classification": classification, "run_id": run_id,
                "envelope": None,
                "note": ("queued. The envelope is written when the worker finishes; poll "
                         "runs.get, or read the message again. `envelope: null` means the "
                         "reply has not arrived, which is not an empty answer.")}

    # 4c. short enough to answer now.
    verb = by_name()[verb_name]
    result = verb.run(_task_args(task, text, raw_ids, ctx, args), ctx)
    env = _envelope_for(task, result, as_of=as_of, run_id=result.get("run_id"),
                        files=files, ctx=ctx)
    store.append_message({"message_id": reply_id, "conversation_id": cid,
                          "ordinal": ordinal + 1, "role": "assistant", "text": "",
                          "file_ids": [], "task": task,
                          "run_id": result.get("run_id"), "envelope": env})
    return {"conversation_id": cid, "message_id": reply_id,
            "classification": classification, "run_id": result.get("run_id"),
            "envelope": env}


def _task_args(task: str, text: str, file_ids, ctx: Context, args: dict) -> dict:
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
    """One citation in full, for the source panel.

    Re-verifies the quote against the held corpus rather than trusting the stored
    envelope: the panel is where a lawyer goes to check, so it is the last place that
    should show a quote nobody re-read.
    """
    from checker.sources.held import HeldCorpus, span_matches

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
            verified, why = False, "not re-checked"
            try:
                ok = span_matches(type("E", (), {
                    "doc_id": c.get("provision_id") or "", "quoted_span": c["quote"]})())
                verified, why = bool(ok), ("re-read from the held corpus and the quote "
                                           "byte-matches" if ok else
                                           "the quote could NOT be found in the corpus "
                                           "section it names")
            except Exception as exc:                            # noqa: BLE001
                verified, why = False, f"could not re-check ({type(exc).__name__})"
            return {"citation": c, "message_id": msg["message_id"],
                    "reverified": verified, "reverified_note": why}
    return _refuse("NOT_FOUND", f"no citation {cid!r} in conversation {conv_id!r}")


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
                          "shown back, never verified, and they do not steer the answer")),
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
                          "(PLAN_22 D3)")),
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
                    "conversation.get", "citation.get"},
          f"the nineteen verbs are declared once ({sorted(names)})")
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
                                 "runs.submit", "runs.cancel", "conversation.send"},
          f"...and exactly six of them write ({sorted(write_verbs())})")
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
    check(len(VERBS) == 19 and "widgets.count" not in rest_spec(),
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
