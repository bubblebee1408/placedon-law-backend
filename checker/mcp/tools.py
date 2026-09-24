"""The tool surface an orchestrator may call. Thin, read-only, refusal-preserving.

Integration plan §3 asked for 12-15 high-value tools rather than 100. This is
thirteen.

## The design rule that makes this thin

**A tool is a name, a schema, and a call into something that already exists.**
Almost every one dispatches into `checker.api.handle()` -- the same pure function
`scripts/serve_api.py` serves over HTTP -- so an agent and an HTTP client get
byte-identical answers, including the refusals. A tool that computed its own
answer would be a second implementation of the engine, free to drift from it, and
the first drift nobody notices is a refusal quietly becoming an answer.

## What every tool returns

The engine's own response, untouched, plus two fields this layer adds:

    _policy      the ALLOW/DENY record for the call
    _boundary    what this result is not

`_boundary` is not decoration. An agent that receives `{"state": "partial"}` with
no further context will summarise it as an answer; a sentence saying "this states
no legal conclusion" survives into the agent's own output far more often than a
status enum does.

## What is deliberately absent

- **No `submit_evidence`, no `attest`, no write of any kind.** `policy.py` refuses
  the action; this module never offers the tool. Two independent guards.
- **No `get_document`/`get_source` returning raw client files.** This repo holds no
  client data (PLAN_07), and a tool that implies otherwise invites someone to put
  it there.
- **No OpenAI-backed tool.** No OpenAI integration is wired in this repository, and
  naming one here would be inventing a capability.

## How a lawyer actually reaches this

They do not. The orchestrator calls these; the lawyer reads one sentence built out
of the results (`themis.get_instrument_impact`). The tools exist so that sentence
can be assembled from evidence rather than from a model's memory.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from checker import api
from checker.mcp.policy import READ, Decision, Request, decide

__all__ = ["TOOLS", "Tool", "call", "list_tools"]

_BOUNDARY = ("This is evidence and engine output, not a legal conclusion. Where the "
             "engine could not establish something it says so, and that refusal is "
             "part of the answer.")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict                    # JSON Schema for the arguments
    run: Callable[[dict], dict]

    def mcp_descriptor(self) -> dict:
        """The shape `tools/list` returns, per the MCP spec."""
        return {"name": self.name, "description": self.description,
                "inputSchema": self.schema}


def _obj(props: dict, required: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "properties": props,
            "required": list(required), "additionalProperties": False}


_STR = {"type": "string"}


def _via_api(method: str, path: str, body: dict | None = None) -> dict:
    """Dispatch into the engine's own router, returning its payload UNTOUCHED.

    The HTTP status goes under `_http`, not `status`. `/v1/health` legitimately
    answers `{"status": "ok"}`, and an earlier version of this function merged the
    transport status into the same key -- so the engine's own field was silently
    overwritten by a number. Caught by this module's own test. The engine's answer
    is the product; nothing in this layer may shadow a field of it.
    """
    code, payload = api.handle(method, path, body, generated_at=_now())
    body_out = payload if isinstance(payload, dict) else {"result": payload}
    return {"_http": code, **body_out}


# ── the thirteen ─────────────────────────────────────────────────────────────

def _health(_: dict) -> dict:
    return _via_api("GET", "/v1/health")


def _scope(_: dict) -> dict:
    """What law is actually held. The first thing an honest orchestrator asks.

    An earlier version called `scope.report()` behind a `hasattr` guard. No such
    function exists, so the guard returned `{}` -- an empty scope, served as if it
    were an answer, by the very tool that exists to say what is NOT held. Caught by
    driving a real MCP session rather than by a unit test, which is why the test
    below now asserts the content and not merely the shape.
    """
    from checker import scope
    return {"_http": 200,
            "coverage": scope.coverage(),
            "held": [{"key": b.key, "name": b.name, "status": b.status, "answerable": b.answerable}
                     for b in scope.in_corpus()],
            "consolidation_only": [{"key": b.key, "name": b.name} for b in scope.current_only()],
            "declared_not_held": [{"key": b.key, "name": b.name} for b in scope.declared_unheld()],
            "note": "A body of law that is DECLARED but not HELD refuses and says what "
                    "it would need. That is not the same answer as 'no obligation applies'."}


def _ask(args: dict) -> dict:
    return _via_api("POST", "/v1/ask", {k: v for k, v in args.items() if v is not None})


def _obligations(args: dict) -> dict:
    return _via_api("POST", "/v1/compliance-pack", args)


def _search_law(args: dict) -> dict:
    """Retrieval over the held statute. Spans, with where each came from."""
    from checker.chunk_retrieval import rank
    from checker.structural_index import chunks_for_corpus
    q = args.get("query", "")
    k = int(args.get("limit", 5))
    try:
        hits = rank(q, chunks_for_corpus(), limit=k)
    except Exception as exc:                                  # noqa: BLE001
        return {"_http": 500, "error": f"retrieval unavailable: {exc}"}
    return {"_http": 200, "query": q,
            "spans": [{"path": getattr(h, "path", None) or getattr(h, "chunk", None),
                       "score": getattr(h, "score", None),
                       "text": (getattr(h, "text", "") or "")[:1200]} for h in hits],
            "note": "BM25 over structural chunks. A span is where to look, not a holding."}


def _law_version(args: dict) -> dict:
    """What the corpus holds for a provision, and whether that record is current."""
    from checker.corpus_currency import report as currency_report
    out: dict = {"_http": 200, "section": args.get("section", "")}
    try:
        out["corpus_currency"] = str(currency_report())
    except Exception as exc:                                  # noqa: BLE001
        out["corpus_currency"] = f"unavailable: {exc}"
    out["note"] = ("EXACT means every amendment we HOLD is applied -- not that we hold "
                   "every amendment that was made.")
    return out


def _amendments(args: dict) -> dict:
    from checker.currency import affected_by
    frag = args.get("instrument", "")
    return {"_http": 200, "instrument": frag, "affected_obligations": affected_by(frag),
            "note": "Matched by instrument NAME against declared thresholds. Nobody has "
                    "read the instrument's text."}


def _instrument_impact(args: dict) -> dict:
    """The lawyer sentence: what landed, what it touches, and what is not yet known."""
    from checker.currency import affected_by
    from checker.obligations import REGISTER
    frag = args.get("instrument", "")
    ids = affected_by(frag)
    by_id = {o.obligation_id: o for o in REGISTER}
    # F1 (bug sweep 2026-09-25): getattr(..., "") turned an id the REGISTER does not
    # hold into a plausible empty duty. `affected_by` reads currency.DEPENDENCIES, a
    # separately maintained list; currency.report() guards the direction
    # "obligation with no dependency" but nothing guards this one. The two agree
    # today (15 ids, symmetric difference empty), so the bug was dormant -- and the
    # sentence still said "touches 2 obligation(s)" while naming one. An unknown id
    # is now said out loud.
    touched = []
    unknown: list[str] = []
    for i in ids:
        ob = by_id.get(i)
        if ob is None:
            unknown.append(i)
            touched.append({"obligation_id": i, "duty": None, "provision": None,
                            "error": "named by the currency index but absent from the "
                                     "obligation register -- one of the two is wrong"})
        else:
            touched.append({"obligation_id": i, "duty": ob.duty, "provision": ob.provision})
    if not ids:
        sentence = (f"{frag} is not matched to any obligation this system holds. That is "
                    "not a finding that it changes nothing -- it means the index has no "
                    "threshold attributed to it.")
    else:
        duties = "; ".join(t["duty"] for t in touched if t["duty"])
        named = len(ids) - len(unknown)
        sentence = (f"{frag} touches {named} obligation(s) this system tracks: {duties}. "
                    "Nobody has read the instrument yet, so nothing follows from it until "
                    "someone acquires and attests it.")
        if unknown:
            sentence += (f" WARNING: {len(unknown)} further id(s) ({', '.join(unknown)}) are "
                         "named by the currency index but absent from the obligation "
                         "register. That is a defect in this system, not a finding about "
                         "the instrument.")
    out = {"_http": 200, "instrument": frag, "affected": touched,
           "sentence_for_a_lawyer": sentence}
    if unknown:
        out["register_mismatch"] = unknown
    return out


def _company_events(args: dict) -> dict:
    cin = args.get("cin", "")
    return _via_api("GET", f"/v1/company/{cin}/events")


def _live_events(args: dict) -> dict:
    """The newest Gazette listing. An observation, never a legal event."""
    from checker.feeds.egazette import EGazetteFeed
    from checker.provenance import ACCESSIBLE
    feed = EGazetteFeed()
    r = feed.fetch()
    obs = feed.parse(r, observed_at=_now())
    if obs.source_behaviour != ACCESSIBLE:
        return {"_http": 503, "source_behaviour": obs.source_behaviour,
                "note": "the source did not answer; this is not 'nothing was published'"}
    p = obs.payload
    return {"_http": 200, "listed": p.get("listed", 0),
            "items": p.get("items", [])[: int(args.get("limit", 10))],
            "blindness": obs.blindness, "licence": obs.licence,
            "note": p.get("absence_means") or
                    "A listing is a subset of what was published. Absence is not evidence."}


def _create_operation(args: dict) -> dict:
    from checker.operations import Watchlist, operation_for_instrument
    wl = Watchlist()
    for cin in args.get("watchlist", []) or []:
        wl.add(str(cin))
    op = operation_for_instrument(args.get("instrument", ""),
                                  trigger=args.get("trigger") or {}, watchlist=wl)
    if op is None:
        return {"_http": 200, "operation": None,
                "note": "no obligation is matched to this instrument, so no work was "
                        "created. Inventing a requirement would manufacture a signal."}
    return {"_http": 200, "operation": op.to_dict()}


def _get_operation(args: dict) -> dict:
    # Operations are not persisted yet (no store). Saying so beats returning an
    # empty result that reads like "this operation does not exist".
    return {"_http": 501, "operation_id": args.get("operation_id", ""),
            "error": "operations are not persisted yet: create_operation returns the "
                     "operation in full, and nothing stores it between calls. Recorded "
                     "as a gap rather than answered with an empty result."}


def _get_tasks(args: dict) -> dict:
    from checker.operations import (SPECIALISTS, Watchlist, operation_for_instrument)
    spec = args.get("specialist")
    if spec is not None and spec not in SPECIALISTS:
        return {"_http": 400, "error": f"{spec!r} is not a specialist; one of {list(SPECIALISTS)}"}
    wl = Watchlist()
    for cin in args.get("watchlist", []) or []:
        wl.add(str(cin))
    op = operation_for_instrument(args.get("instrument", ""),
                                  trigger=args.get("trigger") or {}, watchlist=wl)
    if op is None:
        return {"_http": 200, "tasks": [], "note": "no obligation matched; no work created"}
    reqs = op.tasks_for(spec) if spec else op.requirements
    return {"_http": 200, "operation_id": op.operation_id,
            "budget": op.budget().sentence(),
            "tasks": [{"requirement_id": r.requirement_id, "question": r.question,
                       "specialist": r.specialist, "criticality": r.criticality,
                       "minimum_evidence": r.minimum_evidence, "status": r.status}
                      for r in reqs]}


TOOLS: tuple[Tool, ...] = (
    Tool("themis.health", "Liveness and provenance: corpus version, commit, whether a "
         "model was consulted.", _obj({}), _health),
    Tool("themis.scope", "Which bodies of Indian corporate law are HELD versus merely "
         "DECLARED. Ask this before trusting any other answer.", _obj({}), _scope),
    Tool("themis.ask", "One grounded question against the held statute. Returns cited "
         "spans, an evidence state, and out_of_scope when it reaches past what is held.",
         _obj({"question": _STR, "as_of": _STR}, ("question",)), _ask),
    Tool("themis.search_law", "Retrieve statutory spans for a query (BM25 over "
         "structural chunks). Returns where to look, not a holding.",
         _obj({"query": _STR, "limit": {"type": "integer"}}, ("query",)), _search_law),
    Tool("themis.get_law_version", "What the corpus holds for a provision, and whether "
         "that record is itself current.", _obj({"section": _STR}), _law_version),
    Tool("themis.get_amendments", "Which obligations an instrument is indexed against.",
         _obj({"instrument": _STR}, ("instrument",)), _amendments),
    Tool("themis.get_instrument_impact", "What an instrument touches, rendered as one "
         "sentence a lawyer can read, including what is not yet known.",
         _obj({"instrument": _STR}, ("instrument",)), _instrument_impact),
    Tool("themis.get_obligations", "The compliance matrix for a company's facts: one row "
         "per obligation, each APPLIES / CANNOT_DETERMINE with what would settle it.",
         _obj({"company_class": _STR, "incorporation_date": _STR, "as_of": _STR,
               "financial_year": _STR}), _obligations),
    Tool("themis.get_company_events", "The dated, sourced event log for a company.",
         _obj({"cin": _STR}, ("cin",)), _company_events),
    Tool("themis.get_live_events", "The newest Gazette listing. Observations, never "
         "legal events.", _obj({"limit": {"type": "integer"}}), _live_events),
    Tool("themis.create_operation", "Turn an instrument into routed work: requirements "
         "derived from the obligation register, none of them answered.",
         _obj({"instrument": _STR, "watchlist": {"type": "array", "items": _STR},
               "trigger": {"type": "object"}}, ("instrument",)), _create_operation),
    Tool("themis.get_operation", "Fetch a stored operation by id.",
         _obj({"operation_id": _STR}, ("operation_id",)), _get_operation),
    Tool("themis.get_tasks", "The open work on an operation, optionally for one "
         "specialist.", _obj({"instrument": _STR, "specialist": _STR,
                              "watchlist": {"type": "array", "items": _STR},
                              "trigger": {"type": "object"}}, ("instrument",)), _get_tasks),
)

_BY_NAME = {t.name: t for t in TOOLS}


def list_tools() -> list[dict]:
    return [t.mcp_descriptor() for t in TOOLS]


def call(name: str, arguments: dict | None, *, actor: str = "", tenant: str = "",
         matter: str = "", purpose: str = "") -> dict:
    """Policy-decide, then run. A DENY never reaches the tool."""
    req = Request(tool=name, action=READ, actor=actor, tenant=tenant,
                  matter=matter, purpose=purpose)
    d: Decision = decide(req)
    if not d.allowed:
        return {"_http": 403, "error": d.reason, "_policy": d.record}
    tool = _BY_NAME.get(name)
    if tool is None:
        # policy.KNOWN_TOOLS and TOOLS must agree; if they ever drift, say which.
        return {"_http": 404, "error": f"{name} is policy-known but not registered here",
                "_policy": d.record}
    try:
        result = tool.run(arguments or {})
    except Exception as exc:                                   # noqa: BLE001
        return {"_http": 500, "error": f"{type(exc).__name__}: {exc}", "_policy": d.record}
    return {**result, "_policy": d.record, "_boundary": _BOUNDARY}


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    from checker.mcp.policy import KNOWN_TOOLS

    who = dict(actor="orchestrator", tenant="t1", matter="M-1", purpose="test")

    # ---- the registry and the policy list must agree ----------------------------
    names = {t.name for t in TOOLS}
    check(names == set(KNOWN_TOOLS),
          f"every registered tool is policy-known and vice versa "
          f"(only in one: {names ^ set(KNOWN_TOOLS) or 'none'})")
    check(len(TOOLS) == 13, f"thirteen tools, not a hundred (got {len(TOOLS)})")
    check(all(t.description.strip() and t.schema.get("type") == "object" for t in TOOLS),
          "every tool has a description and an object schema")
    check(all(t.mcp_descriptor()["inputSchema"]["additionalProperties"] is False
              for t in TOOLS), "no tool accepts undeclared arguments")

    # ---- policy is enforced HERE, not just available ----------------------------
    r = call("themis.health", {}, **{**who, "actor": ""})
    check(r["_http"] == 403 and "actor" in r["error"],
          "an unattributed call is refused before the tool runs")
    r = call("themis.health", {}, **{**who, "purpose": ""})
    check(r["_http"] == 403, "a call with no purpose is refused")
    r = call("themis.not_a_tool", {}, **who)
    check(r["_http"] == 403 and "default deny" in r["error"], "an unknown tool is refused")

    # ---- a real call carries the policy record and the boundary ------------------
    r = call("themis.health", {}, **who)
    check(r["_http"] == 200, f"health answers ({r.get('_http')})")
    check(r["_policy"]["verdict"] == "ALLOW" and r["_policy"]["matter"] == "M-1",
          "the policy record travels with the result")
    check("not a legal conclusion" in r["_boundary"], "so does the boundary sentence")

    # ---- refusals reach the caller unsmoothed ------------------------------------
    r = call("themis.ask", {"question": "What are the FEMA reporting rules for FDI?"}, **who)
    check(r.get("state") == "out_of_scope",
          f"a question past the held scope comes back out_of_scope (got {r.get('state')})")
    r = call("themis.ask", {"question": "What does s.173 require?"}, **who)
    check(r.get("state") in ("answered", "partial") and r.get("confirmed"),
          "a held question returns cited spans")
    check(r.get("uses_model") is False, "...and says no model was consulted")

    # ---- scope must answer with CONTENT, not an empty object ---------------------
    r = call("themis.scope", {}, **who)
    check(r["held"] and any(b["key"] == "CA2013" for b in r["held"]),
          f"scope names the held body of law (got {[b.get('key') for b in r.get('held', [])]})")
    check(len(r["declared_not_held"]) >= 5,
          f"...and the bodies declared but NOT held ({len(r.get('declared_not_held', []))})")
    check(r["coverage"].strip(), "...and a coverage sentence")

    # ---- the lawyer sentence ------------------------------------------------------
    r = call("themis.get_instrument_impact", {"instrument": "880"}, **who)
    check(r["affected"] and r["affected"][0]["obligation_id"] == "CA13-S2-85-SMALL",
          "a known instrument names the obligation it touches")
    check("Nobody has read the instrument yet" in r["sentence_for_a_lawyer"],
          "...and the lawyer sentence says nothing follows until someone reads it")
    # F1: an id the currency index names but the register does not hold must be SAID,
    # not rendered as an empty duty. Dormant today (the two agree), so the guard is
    # the only thing that would catch them drifting apart.
    import checker.currency as _cur
    _real = _cur.affected_by
    try:
        _cur.affected_by = lambda frag: ["CA13-DOES-NOT-EXIST", "CA13-S96-AGM"]
        bad = call("themis.get_instrument_impact", {"instrument": "G.S.R. 700(E)"}, **who)
    finally:
        _cur.affected_by = _real
    check(bad.get("register_mismatch") == ["CA13-DOES-NOT-EXIST"],
          f"an id absent from the register is named as a mismatch ({bad.get('register_mismatch')})")
    check("WARNING" in bad["sentence_for_a_lawyer"] and "defect in this system" in
          bad["sentence_for_a_lawyer"],
          "...and the lawyer sentence calls it a defect in this system, not a finding")
    check("touches 1 obligation" in bad["sentence_for_a_lawyer"],
          f"...and counts only the obligations it can actually name")
    check(any(t.get("error") for t in bad["affected"]),
          "...and the unknown row carries an error rather than an empty duty")

    r = call("themis.get_instrument_impact", {"instrument": "G.S.R. 9999(E)"}, **who)
    check("not a finding that it changes nothing" in r["sentence_for_a_lawyer"],
          "an unmatched instrument is not reported as harmless")

    # ---- work, and the gap that is admitted rather than faked ---------------------
    r = call("themis.get_tasks", {"instrument": "880", "specialist": "FINANCIAL_DATA"}, **who)
    check(r["tasks"] and all(t["specialist"] == "FINANCIAL_DATA" for t in r["tasks"]),
          "tasks can be fetched for one specialist")
    check("cannot be closed" in r["budget"], "...with the budget's refusal attached")
    r = call("themis.get_tasks", {"instrument": "880", "specialist": "ASTROLOGY"}, **who)
    check(r["_http"] == 400, "an unknown specialist is a 400, not an empty list")
    r = call("themis.get_operation", {"operation_id": "op_x"}, **who)
    check(r["_http"] == 501 and "not persisted yet" in r["error"],
          "an unbuilt capability says so, rather than returning an empty result")

    # ---- no write path exists at all ---------------------------------------------
    check(not any("submit" in n or "attest" in n or "write" in n or "delete" in n
                  for n in names), "no tool offers a write, a submit, or an attest")

    from checker import rings
    check(rings.ring_of("checker.mcp.tools") == rings.RING_2, "this module is Ring 2")
    check(not [v for v in rings.violations() if "mcp" in v],
          "no Ring 0 or Ring 1 module imports the MCP surface")

    check(json.dumps(list_tools())[:1] == "[", "the tool list serialises for tools/list")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
