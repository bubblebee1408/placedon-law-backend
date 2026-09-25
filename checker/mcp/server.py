"""MCP over stdio: JSON-RPC 2.0, standard library only.

Integration plan §22. This is what lets Claude Code, or any MCP client, reach
Themis as a set of tools rather than as a codebase.

## Why no dependency

MCP is JSON-RPC 2.0 framed as newline-delimited JSON on stdin/stdout. `json` and
`sys` are the whole requirement. Adding an SDK would put a package in
`requirements.txt` for a protocol that is three message types wide, and this
repository's one production incident from a dependency (`jinja2`) is recorded in
`backend/services/llm.py`.

## The three methods

    initialize      handshake; declares protocol version and capabilities
    tools/list      the fourteen descriptors from checker/mcp/tools.py
    tools/call      policy-decide, run, return the result as MCP content

## The identity problem, stated rather than hidden

MCP has no transport-level notion of *which lawyer, which firm, which matter*.
This server therefore takes the actor/tenant/matter from the tool arguments
(`_actor`, `_tenant`, `_matter`, `_purpose`) or from environment defaults, and
`policy.py` treats every one as a CLAIM, not a fact.

That is fine for a local developer client, where the operator is the user. It is
**not** an authorisation boundary, and a multi-tenant deployment must establish
identity in front of this process rather than inside it. Written down here because
a policy record that looks authoritative and is merely asserted is worse than one
that says what it is.

## What a client cannot do through this

Write to the corpus, or attest anything. `policy.decide` refuses `WRITE` and
`ATTEST` outright, for every actor, with no allow path.

Exactly one tool is not a read: `themis.submit_evidence` records an answer against
ONE requirement of a stored operation (`policy.SUBMIT`). It reaches the operation
store and nothing else -- never the corpus, never an instrument's admission state.
And the store independently refuses an agent closing BLOCKING work, so that
guarantee survives someone loosening the policy without reading the store.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, TextIO

from checker.mcp import tools as toolmod

__all__ = ["serve", "handle_message", "PROTOCOL_VERSION", "SERVER_INFO"]

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "themis", "version": "0"}

# Reserved argument names: caller identity, stripped before the tool sees them.
_IDENTITY = ("_actor", "_tenant", "_matter", "_purpose")


def _identity(args: dict) -> dict:
    env = os.environ
    return {
        "actor": args.get("_actor") or env.get("THEMIS_ACTOR", ""),
        "tenant": args.get("_tenant") or env.get("THEMIS_TENANT", ""),
        "matter": args.get("_matter") or env.get("THEMIS_MATTER", ""),
        "purpose": args.get("_purpose") or env.get("THEMIS_PURPOSE", ""),
    }


def _result(rpc_id: Any, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": payload}


def _error(rpc_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def handle_message(msg: dict) -> dict | None:
    """One JSON-RPC message in, one response out. None for a notification.

    Pure apart from the tools it dispatches to, so the whole protocol is testable
    without a subprocess or a socket.
    """
    if msg.get("jsonrpc") != "2.0":
        return _error(msg.get("id"), -32600, "not a JSON-RPC 2.0 message")
    method = msg.get("method")
    rpc_id = msg.get("id")
    params = msg.get("params") or {}

    # A notification (no id) expects no response. `notifications/initialized` is the
    # normal one; answering it would be a protocol error.
    if rpc_id is None:
        return None

    if method == "initialize":
        return _result(rpc_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Themis serves verified Indian corporate-law evidence. Thirteen of the "
                "fourteen tools are read-only; themis.submit_evidence records an answer "
                "against one requirement of a stored operation, and may not close "
                "BLOCKING work -- only a human reviewer can. Nothing here writes to the "
                "corpus or attests a source. Answers carry their own refusals -- "
                "out_of_scope, CANNOT_DETERMINE, NOT_ESTABLISHED -- and those refusals "
                "are part of the answer, not an error to route around. No tool returns a "
                "legal conclusion. Call themis.scope first: only one of nine in-scope "
                "bodies of law is currently held."),
        })

    if method == "tools/list":
        return _result(rpc_id, {"tools": toolmod.list_tools()})

    if method == "tools/call":
        name = params.get("name", "")
        args = dict(params.get("arguments") or {})
        who = _identity(args)
        for k in _IDENTITY:
            args.pop(k, None)
        out = toolmod.call(name, args, **who)
        # MCP content blocks. `isError` is reserved for transport/policy failure --
        # an engine refusal (out_of_scope, CANNOT_DETERMINE) is a successful call
        # whose answer happens to be "no", and marking it as an error would teach a
        # client to retry around it.
        failed = out.get("_http") in (403, 404, 500) or "error" in out
        return _result(rpc_id, {
            "content": [{"type": "text", "text": json.dumps(out, indent=1, default=str)}],
            "isError": bool(failed),
        })

    if method == "ping":
        return _result(rpc_id, {})

    return _error(rpc_id, -32601, f"method not found: {method}")


def serve(stdin: TextIO | None = None, stdout: TextIO | None = None,
          *, log: Callable[[str], None] | None = None) -> int:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    log(f"themis-mcp: serving {len(toolmod.TOOLS)} tools on stdio "
        "(read-only except themis.submit_evidence)")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError as exc:
            stdout.write(json.dumps(_error(None, -32700, f"parse error: {exc}")) + "\n")
            stdout.flush()
            continue
        try:
            resp = handle_message(msg)
        except Exception as exc:                                # noqa: BLE001
            resp = _error(msg.get("id"), -32603, f"{type(exc).__name__}: {exc}")
        if resp is not None:
            stdout.write(json.dumps(resp, default=str) + "\n")
            stdout.flush()
    return 0


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    import io

    who = {"_actor": "claude-code", "_tenant": "t1", "_matter": "M-1", "_purpose": "review"}

    # ---- handshake ---------------------------------------------------------------
    r = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check(r["result"]["protocolVersion"] == PROTOCOL_VERSION, "initialize declares a version")
    check(r["result"]["serverInfo"]["name"] == "themis", "...and names the server")
    inst = r["result"]["instructions"]
    check("read-only" in inst and "submit_evidence" in inst,
          "...and tells the client which tools are read-only and which is not")
    check("only a human reviewer can" in inst,
          "...and that BLOCKING work is human-only, before it tries")
    check("Every tool is read-only" not in inst,
          "...and no longer claims every tool is read-only, which stopped being true")
    check("refusals are part of the answer" in r["result"]["instructions"],
          "...and that a refusal is not an error to route around")

    # ---- a notification gets no reply ----------------------------------------------
    check(handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None,
          "a notification receives no response, as the protocol requires")

    # ---- tools/list -----------------------------------------------------------------
    r = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    check(len(names) == 14 and "themis.ask" in names, f"tools/list returns fourteen ({len(names)})")
    check("themis.submit_evidence" in names, "...including the one submit tool")
    check(all("inputSchema" in t for t in r["result"]["tools"]), "every descriptor has a schema")

    # ---- tools/call, and identity travelling in arguments ----------------------------
    r = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "themis.health", "arguments": dict(who)}})
    payload = json.loads(r["result"]["content"][0]["text"])
    check(r["result"]["isError"] is False, "a permitted call is not an error")
    check(payload["_policy"]["verdict"] == "ALLOW" and payload["_policy"]["actor"] == "claude-code",
          "the policy record names the claimed actor")
    check("_actor" not in payload, "identity arguments are stripped before the tool sees them")

    # ---- an engine refusal is NOT a transport error ----------------------------------
    r = handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                        "params": {"name": "themis.ask",
                                   "arguments": {"question": "What are the FEMA rules for FDI?",
                                                 **who}}})
    payload = json.loads(r["result"]["content"][0]["text"])
    check(payload.get("state") == "out_of_scope", "an out-of-scope question comes back as such")
    check(r["result"]["isError"] is False,
          "...and is NOT flagged isError -- a refusal is an answer, not a failure to retry around")

    # ---- a policy refusal IS an error ------------------------------------------------
    r = handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "themis.health", "arguments": {}}})
    payload = json.loads(r["result"]["content"][0]["text"])
    check(r["result"]["isError"] and payload["_http"] == 403,
          "an unattributed call is a policy error")

    # ---- protocol edges ---------------------------------------------------------------
    check(handle_message({"jsonrpc": "2.0", "id": 6, "method": "nope"})["error"]["code"] == -32601,
          "an unknown method is -32601")
    check(handle_message({"id": 7, "method": "initialize"})["error"]["code"] == -32600,
          "a non-2.0 message is rejected")
    check(handle_message({"jsonrpc": "2.0", "id": 8, "method": "ping"})["result"] == {},
          "ping answers")

    # ---- a whole session over pipes ----------------------------------------------------
    session = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "themis.get_instrument_impact",
                    "arguments": {"instrument": "880", **who}}},
    ]) + "\n"
    out = io.StringIO()
    serve(io.StringIO(session), out, log=lambda _m: None)
    lines = [json.loads(x) for x in out.getvalue().strip().splitlines()]
    check(len(lines) == 3, f"three requests, three responses; the notification got none ({len(lines)})")
    impact = json.loads(lines[-1]["result"]["content"][0]["text"])
    check("Nobody has read the instrument yet" in impact["sentence_for_a_lawyer"],
          "a full stdio session returns the lawyer sentence, refusal intact")

    out = io.StringIO()
    serve(io.StringIO("{not json\n"), out, log=lambda _m: None)
    check(json.loads(out.getvalue())["error"]["code"] == -32700,
          "malformed input is a parse error, not a crash")

    from checker import rings
    check(rings.ring_of("checker.mcp.server") == rings.RING_2, "this module is Ring 2")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
