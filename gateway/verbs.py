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


def _ask(args: dict, ctx: Context) -> dict:
    from agents import research_question as rq
    q = (args.get("question") or "").strip()
    if not q:
        return _refuse("BAD_REQUEST", "question is required")
    model = ctx.model_for(q) if ctx.model_for else None
    out = rq.answer(q, model=model, available=args.get("available") or ("azure",))
    return out.to_dict()


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
    model = ctx.model_for(text) if ctx.model_for else None
    return rc.review(text, book=book, model=model,
                     name=args.get("name") or "contract").to_dict()


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
          Field("playbook", STRING, False, describes="repo-relative playbook path")),
         "POST", read_only=True, run=_review_contract),

    Verb("runs.get", "One run's status and result, without its steps.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_get),

    Verb("runs.trace", "Every step of one run, in order, as persisted.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_trace),

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

    check(names == {"ask", "review_contract", "runs.get", "runs.trace",
                    "documents.upload"},
          f"the five verbs are declared once ({sorted(names)})")

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
    check(len(VERBS) == 5 and "widgets.count" not in rest_spec(),
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

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
