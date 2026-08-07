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
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.responses import JSONResponse  # noqa: E402
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
    scope["root_path"] = ""

    if scope["path"].rstrip("/").endswith("__whoami"):
        await JSONResponse({
            "resolved_path": scope["path"],
            "had_p_param": bool(original),
            "method": scope.get("method"),
            "routes": sorted(r.path for r in _checker.routes if getattr(r, "path", None)),
        })(scope, receive, send)
        return

    await _checker(scope, receive, send)
