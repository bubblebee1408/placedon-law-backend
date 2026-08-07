"""
Vercel entry point.

The checker is pure compute — no database, no LLM, no state — so it runs fine as a serverless
function. Vercel supplies the ASGI server; we export `app`.

The one wrinkle: Vercel's rewrite hands the function a path that may carry the function's own
mount point (`/api/index`) rather than the user-visible path. Rather than depend on which,
we normalise the path in middleware so the same app serves correctly both locally and on
Vercel. `/__whoami` reports what the runtime actually delivered, which turns a deploy-cycle
guessing game into one request.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.responses import JSONResponse  # noqa: E402
from starlette.types import Receive, Scope, Send  # noqa: E402

from checker.app import app as _checker  # noqa: E402

_MOUNT_PREFIXES = ("/api/index", "/api")


async def app(scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await _checker(scope, receive, send)
        return

    raw = scope.get("path", "/") or "/"

    if raw.rstrip("/").endswith("__whoami"):
        await JSONResponse({
            "received_path": raw,
            "root_path": scope.get("root_path", ""),
            "raw_path": (scope.get("raw_path") or b"").decode("utf-8", "replace"),
            "routes": sorted(
                r.path for r in _checker.routes if getattr(r, "path", None)
            ),
        })(scope, receive, send)
        return

    path = raw
    for prefix in _MOUNT_PREFIXES:
        if path == prefix:
            path = "/"
            break
        if path.startswith(prefix + "/"):
            path = path[len(prefix):]
            break

    scope = dict(scope)
    scope["path"] = path or "/"
    scope["root_path"] = ""
    await _checker(scope, receive, send)
