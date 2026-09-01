#!/usr/bin/env python3
"""Serve the compliance matrix locally. Standard library only, no model.

    python3 scripts/serve_matrix.py            # http://127.0.0.1:8014
    python3 scripts/serve_matrix.py --port 9000
    python3 scripts/serve_matrix.py --test

Binds to 127.0.0.1 deliberately. This serves an unauthenticated page that
accepts company facts, and the moment it listens on 0.0.0.0 somebody's
compliance position is on their office network. Stage 1 is a local tool; making
it a hosted one is a decision with its own security work, not a default.

All the routing lives in `checker.matrix_view.handle()`, which is a pure
function. This file is only the socket.
"""
from __future__ import annotations

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker.matrix_view import handle  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8014


class Handler(BaseHTTPRequestHandler):
    server_version = "PlacedonMatrix/1"

    def do_GET(self) -> None:                       # noqa: N802
        parts = urlsplit(self.path)
        try:
            status, ctype, body = handle(parts.path, parts.query)
        except Exception as e:                      # noqa: BLE001
            # A crash must not leak a stack trace to the page, and must not
            # take the server down mid-session.
            status, ctype = 500, "text/html; charset=utf-8"
            body = ("<!doctype html><p>The page could not be built. "
                    "Nothing was saved.</p>")
            self.log_error("handler failed: %s: %s", type(e).__name__, e)

        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        # A compliance answer must not be cached by anything: it is specific to
        # one company on one date, and a stale one is a wrong one.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "form-action 'self'")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # The query string carries company facts. Logging it would write a
        # client's financials into a terminal scrollback and any file it is
        # piped to, so only the path and status are recorded.
        sys.stderr.write(f"  {self.command} {urlsplit(self.path).path} "
                         f"{args[1] if len(args) > 1 else ''}\n")


def serve(port: int = DEFAULT_PORT) -> None:
    srv = ThreadingHTTPServer((HOST, port), Handler)
    print(f"\n  Compliance matrix — Companies Act 2013")
    print(f"  http://{HOST}:{port}/\n")
    print("  No language model is consulted. No data leaves this machine.")
    print("  Ctrl-C to stop.\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        srv.server_close()


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("serve_matrix")

    import http.client
    import threading

    srv = ThreadingHTTPServer((HOST, 0), Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        c = http.client.HTTPConnection(HOST, port, timeout=10)
        c.request("GET", "/")
        r = c.getresponse()
        body = r.read().decode()
        check(r.status == 200, f"the root serves ({r.status})")
        check("<form" in body, "...and returns the form")
        check(r.getheader("Cache-Control") == "no-store",
              "a compliance answer is not cacheable")
        check(r.getheader("X-Content-Type-Options") == "nosniff",
              "content type is not sniffable")
        check("default-src 'none'" in (r.getheader("Content-Security-Policy") or ""),
              "a CSP is set")

        c.request("GET", "/matrix?company_class=private&"
                         "incorporation_date=2019-06-01&financial_year=2024-25&"
                         "paid_up_capital_crore=2&turnover_crore=30")
        r2 = c.getresponse()
        page = r2.read().decode()
        check(r2.status == 200, f"the matrix route serves ({r2.status})")
        check("CA13-S96-AGM" in page, "...and renders obligation rows")
        check("S-002" in page, "...including the blocked row")

        c.request("GET", "/nope")
        r3 = c.getresponse()
        r3.read()
        check(r3.status == 404, f"an unknown path 404s ({r3.status})")

        c.request("GET", "/matrix?company_class=private&incorporation_date=bad")
        r4 = c.getresponse()
        r4.read()
        check(r4.status == 400, f"bad input is a 400, not a crash ({r4.status})")
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()

    check(HOST == "127.0.0.1", "binds to loopback, not to the network")

    # The query string holds company financials and must not be logged.
    import inspect
    src = inspect.getsource(Handler.log_message)
    check("urlsplit(self.path).path" in src and "self.path}" not in src,
          "the logger records the path only, never the query string")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    p = DEFAULT_PORT
    if "--port" in sys.argv:
        p = int(sys.argv[sys.argv.index("--port") + 1])
    serve(p)
