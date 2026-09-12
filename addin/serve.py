#!/usr/bin/env python3
"""Dev server for the task pane: serves the add-in AND proxies the API.

Two things make this necessary rather than optional.

**HTTPS.** Word will not load a task pane over http. This generates a
self-signed certificate on first run and serves over https on localhost, which
Word accepts once the certificate is trusted (see README).

**CORS.** The task pane is a web page in a webview and is bound by the
same-origin policy exactly as a browser tab is. Rather than configure CORS on the
engine, this serves the pane and the API from ONE origin, so there is no
cross-origin request to allow. Simpler, and it keeps the engine unaware it is
being called from a browser.

The proxy is deliberately thin: it accepts /v1/* and hands the body to
`checker.api.handle`, the same pure function the tests exercise. No model, no
network, no state.
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

CERT = HERE / "localhost.pem"
PORT = 3000


def ensure_cert() -> None:
    if CERT.is_file():
        return
    print("generating a self-signed certificate for localhost…")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(CERT), "-out", str(CERT), "-days", "365",
        "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
    ], check=True, capture_output=True)
    print(f"wrote {CERT}")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):          # quieter
        sys.stderr.write(f"  {self.command} {self.path}\n")

    def _json(self, status: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.startswith("/v1/"):
            return self._json(404, {"error": "not_found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"error": "bad_request", "detail": str(e)})
        from checker.api import handle
        gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            status, body = handle("POST", self.path, payload, generated_at=gen)
        except Exception as e:                  # never leak a stack to the pane
            return self._json(500, {"error": "engine_error", "detail": str(e)})
        return self._json(status, body)

    def do_GET(self):
        if self.path.startswith("/v1/"):
            from checker.api import handle
            gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            status, body = handle("GET", self.path, None, generated_at=gen)
            return self._json(status, body)
        return super().do_GET()


def main() -> None:
    ensure_cert()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(CERT))
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"\n  https://localhost:{PORT}/taskpane.html")
    print(f"  engine: POST https://localhost:{PORT}/v1/document-check")
    print("\n  Ctrl-C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
