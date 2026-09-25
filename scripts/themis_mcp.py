#!/usr/bin/env python3
"""Serve Themis to an MCP client over stdio.

    python3 scripts/themis_mcp.py            # serve (what an MCP client launches)
    python3 scripts/themis_mcp.py --test     # offline self-test
    python3 scripts/themis_mcp.py --tools    # list the tools and exit

To register with Claude Code:

    claude mcp add themis -- python3 /ABS/PATH/scripts/themis_mcp.py

Identity is taken from THEMIS_ACTOR / THEMIS_TENANT / THEMIS_MATTER /
THEMIS_PURPOSE, or from `_actor`/`_tenant`/`_matter`/`_purpose` arguments on each
call. Both are CLAIMS: this process does not authenticate, and
`checker/mcp/policy.py` says so. Put identity in front of it before a multi-tenant
deployment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker.mcp.server import serve                      # noqa: E402
from checker.mcp.tools import TOOLS, list_tools           # noqa: E402


def _test() -> int:
    from checker.mcp import policy, server, tools
    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    check(len(TOOLS) == 13, f"thirteen tools are exposed ({len(TOOLS)})")
    check({t.name for t in TOOLS} == set(policy.KNOWN_TOOLS),
          "the registry and the policy list agree")
    check(all(t["name"].startswith("themis.") for t in list_tools()),
          "every tool is namespaced themis.*")
    check(server.PROTOCOL_VERSION and server.SERVER_INFO["name"] == "themis",
          "the server declares a protocol version and a name")
    # Nothing here writes, attests or submits. A submit tool existed for part of
    # 2026-09-25 and was removed after RT-10: this surface cannot establish who is
    # calling it, so it grants nothing that could change stored state. See
    # docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md and PLAN_17 M6.
    check(not any("submit" in t.name or "write" in t.name or "attest" in t.name
                  for t in TOOLS),
          "no exposed tool submits, writes or attests")
    for action in (policy.WRITE, policy.ATTEST):
        check(not any(policy.decide(policy.Request(tool=t.name, action=action,
                                                   actor="a", purpose="p")).allowed
                      for t in TOOLS),
              f"no exposed tool permits {action}")
    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--test" in sys.argv:
        return _test()
    if "--tools" in sys.argv:
        print(json.dumps(list_tools(), indent=1))
        return 0
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
