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
                      for s in (out.summary.sentences if out.summary else ())])
    return d


def _persist_run(ctx: Context, *, intent: str, status: str, steps: list,
                 propositions: list, refusal_code=None) -> str | None:
    """Write one run as runs + ordered steps + propositions. Returns the run id, or None.

    R-016's DERIVATION model, actually used: without this a verb answers and leaves no
    trace, and `runs.trace` has nothing to serve. A store that is absent is not an error
    here -- the verb still answered -- but the caller is told the id is None rather than
    handed one that resolves to nothing.
    """
    if ctx.store is None:
        return None
    import uuid
    run_id = str(uuid.uuid4())
    ctx.store.write({"id": run_id, "intent": intent, "status": status,
                     "refusal_code": refusal_code,
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
                               steps=steps, propositions=props)
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
                               steps=steps, propositions=props)
    return d


# The human gate. `runs.approve` and `runs.reject` are the only WRITING verbs besides
# documents.upload, and they are excluded from MCP by `mcp_tools` for exactly that reason --
# a tool surface that can approve a finding is a tool surface that can clear a review.
MIN_REASON_CHARS = 10


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


def _documents_upload(args: dict, ctx: Context) -> dict:
    """Store bytes under their own sha256. The identity IS the hash, not a counter."""
    import hashlib
    text = args.get("text") or ""
    if not text.strip():
        return _refuse("BAD_REQUEST", "text is required")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    ctx.documents[digest] = {"sha256": digest, "bytes": len(text.encode("utf-8")),
                             "name": args.get("name") or "document",
                             "tenant": ctx.tenant}
    return {"document_id": digest, "sha256": digest,
            "bytes": ctx.documents[digest]["bytes"],
            "stored": "memory",
            "note": ("held in this process only. gateway/migrations/*.sql are not "
                     "applied, so nothing here survives a restart and no database "
                     "enforces tenant isolation.")}


# ── the table ────────────────────────────────────────────────────────────────

VERBS: tuple[Verb, ...] = (
    Verb("ask", "One grounded research question against the held statute. Cited spans or "
                "a named refusal.",
         (Field("question", STRING, True, describes="the question, in plain English"),
          Field("available", OBJECT, False, describes="provider tuple to route over")),
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
                describes="the text the reviewer was looking at when they decided")),
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
                describes="the text the reviewer was looking at when they decided")),
         "POST", read_only=False, run=_runs_reject),

    Verb("documents.upload",
         "Store a document and return the sha256 that identifies it.",
         (Field("text", STRING, True, describes="the document text"),
          Field("name", STRING, False, describes="a label for the document")),
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

    check(names == {"ask", "review_contract", "review_document", "runs.get", "runs.trace",
                    "runs.approve", "runs.reject", "documents.upload"},
          f"the eight verbs are declared once ({sorted(names)})")
    # The two that WRITE a human decision. Named here rather than counted, so adding a
    # third write verb is a deliberate edit to this line and not a number going up.
    check(set(write_verbs()) == {"documents.upload", "runs.approve", "runs.reject"},
          f"...and exactly three of them write ({sorted(write_verbs())})")

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
    check(len(VERBS) == 8 and "widgets.count" not in rest_spec(),
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
            "quoted_span": "physical minutes book not inspected"}

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
    again = _runs_approve({**good, "reason": "Actually I changed my mind about this."}, dctx)
    check(again["code"] == "ALREADY_DECIDED",
          "...and a second decision on the same item is refused rather than overwriting the "
          "label that is the point of storing it")
    rej = _runs_reject({**good, "item_ref": "ss:T1.3",
                        "reason": "Blank pages were not scored out; the book shows three."},
                       dctx)
    check(rej["decision"] == "REJECTED" and len(dstore.read_decisions(rid)) == 2,
          "...while a rejection on a different item is a separate label")

    # NOT MCP. A tool surface that can approve a finding is one that can clear a review.
    mcp_names = {t.name for t in mcp_tools()}
    check(not {n for n in mcp_names if "approve" in n or "reject" in n},
          f"runs.approve and runs.reject are NOT exposed over MCP {sorted(mcp_names)}")
    check("runs.approve" in rest_spec() and "runs-approve" in
          {c["command"] for c in cli_spec().values()},
          "...while REST and the CLI both carry them, which is where a person acts")

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
