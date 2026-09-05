#!/usr/bin/env python3
"""The JSON API server. Wraps checker.api.handle in the stdlib HTTP server.

    python3 scripts/serve_api.py                 # http://127.0.0.1:8020
    python3 scripts/serve_api.py --port 9000
    python3 scripts/serve_api.py --test

Binds to 127.0.0.1 by design — this serves an unauthenticated compliance API. Facts
arrive in the POST body, never the URL (so a company's data is not written to access
logs). Every response is no-store with a strict CSP. Making this a hosted, authed,
rate-limited service is a deliberate deployment step with its own security work, not
a default here.
"""
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.api import handle

HOST = "127.0.0.1"
DEFAULT_PORT = 8020
MAX_BODY = 256 * 1024        # a company payload is small; cap to refuse abuse


class Handler(BaseHTTPRequestHandler):
    server_version = "PlacedonAPI/1"

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body, indent=1, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        if length > MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        status, body = handle("GET", self.path, None, generated_at=self._now())
        self._respond(status, body)

    def do_POST(self) -> None:
        try:
            body = self._read_body()
        except (ValueError, json.JSONDecodeError) as e:
            self._respond(400, {"error": "bad_request", "detail": f"invalid JSON body: {e}"})
            return
        status, resp = handle("POST", self.path, body, generated_at=self._now())
        self._respond(status, resp)

    def log_message(self, fmt, *args):
        # Log the method + path only, never the query or body (which carry facts).
        sys.stderr.write(f"{self.command} {self.path.split('?')[0]}\n")


def serve(port: int = DEFAULT_PORT) -> None:
    srv = ThreadingHTTPServer((HOST, port), Handler)
    print(f"Placedon API on http://{HOST}:{port}  (POST /v1/compliance-pack, GET /v1/health)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def _test() -> int:
    import threading
    import urllib.request

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            fail += 1
        else:
            ok += 1

    print("serve_api")
    srv = ThreadingHTTPServer((HOST, 0), Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://{HOST}:{port}"

        # GET health
        with urllib.request.urlopen(base + "/v1/health") as r:
            h = json.loads(r.read())
        check(r.status == 200 and h["status"] == "ok", "GET /v1/health serves ok")

        # POST a company payload
        payload = json.dumps({
            "company_class": "private", "incorporation_date": "2019-06-01",
            "as_of": "2026-08-31", "financial_year": "2024-25",
            "is_holding_company": False, "is_subsidiary_company": False,
            "is_section_8": False, "governed_by_special_act": False,
            "evidence": {"agm_dates": ["2025-12-30"], "financial_year_end": "2025-03-31"}
        }).encode()
        req = urllib.request.Request(base + "/v1/compliance-pack", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        check(r.status == 200 and "rows" in body, "POST /v1/compliance-pack returns a pack")
        check(r.getheader("Cache-Control") == "no-store", "responses are no-store")

        # a bad body -> 400
        req2 = urllib.request.Request(base + "/v1/compliance-pack", data=b"not json",
                                      headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req2)
            check(False, "an invalid JSON body is refused")
        except urllib.error.HTTPError as e:
            check(e.code == 400, "an invalid JSON body returns 400")
    finally:
        srv.shutdown()
        srv.server_close()

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    port = DEFAULT_PORT
    if len(sys.argv) == 3 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    serve(port)
