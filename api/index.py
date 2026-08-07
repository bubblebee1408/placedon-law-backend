"""
Vercel entry point.

The checker is pure compute — no database, no LLM, no state — so it runs fine as a serverless
function. Vercel supplies the ASGI server; we export `app`.

The wrinkle, diagnosed the hard way: Vercel's rewrite **replaces** the request path with the
rewrite destination, so the function sees `/api/index` for every request regardless of what the
user asked for. `GET /` happened to work; `POST /check` normalised to `/` and came back 405
(method not allowed) rather than 404 — which is what gave the game away.

So `vercel.json` passes the original path through the query string as `__p`, and this wrapper
restores it before handing off. Local runs have no `__p` and use the real path, so the same code
serves correctly in both places.

(A `/__whoami` diagnostic lived here while that was being worked out. It has been removed — it
reported the route table, which is not something a public compliance product should hand out.)
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.types import Receive, Scope, Send  # noqa: E402

from checker.app import app as _checker  # noqa: E402


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await _checker(scope, receive, send)
        return

    scope = dict(scope)
    qs = (scope.get("query_string") or b"").decode("latin-1")
    pairs = parse_qsl(qs, keep_blank_values=True)

    original = next((v for k, v in pairs if k == "__p"), None)
    if original:
        scope["path"] = original if original.startswith("/") else "/" + original
        rest = [(k, v) for k, v in pairs if k != "__p"]
        scope["query_string"] = urlencode(rest).encode("latin-1")

    # Belt and braces: if the rewrite didn't supply __p (the bare "/" rule proved
    # unreliable), strip the function's own mount point so the root still resolves.
    path = scope.get("path") or "/"
    for prefix in ("/api/index", "/api"):
        if path == prefix:
            path = "/"
            break
        if path.startswith(prefix + "/"):
            path = path[len(prefix):] or "/"
            break
    scope["path"] = path or "/"
    scope["root_path"] = ""


    await _checker(scope, receive, send)
