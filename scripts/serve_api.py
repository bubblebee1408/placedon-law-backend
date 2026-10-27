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
# P2: every urlopen in this repository carries a timeout, with no exception list --
# scripts/hardening.py asserts it. These three are a test client against this module's
# own in-process server, so the risk is a hung GATE rather than a hung request.
SELFTEST_TIMEOUT = 30
DEFAULT_PORT = 8020
MAX_BODY = 256 * 1024        # a company payload is small; cap to refuse abuse
# After refusing an oversized body, read and discard at most DRAIN_LIMIT of it, for at most
# DRAIN_SECONDS in total, before closing. Closing with unread bytes makes the kernel RESET a
# client that is still sending, which then sees "connection reset" instead of the 413.
DRAIN_LIMIT = 8 * 1024 * 1024
DRAIN_SECONDS = 5.0


class BodyTooLarge(Exception):
    """The Content-Length is over MAX_BODY. Answered with 413, never read or parsed."""

    def __init__(self, length: int) -> None:
        super().__init__(f"request body of {length} bytes is over the {MAX_BODY}-byte cap")
        self.length = length


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
            raise BodyTooLarge(length)
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        status, body = handle("GET", self.path, None, generated_at=self._now())
        self._respond(status, body)

    def _drain(self, length: int) -> None:
        """Discard the unread body, bounded by size and a TOTAL deadline. Nothing is kept."""
        import time
        remaining = min(length, DRAIN_LIMIT)
        deadline = time.monotonic() + DRAIN_SECONDS
        try:
            while remaining > 0:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.connection.settimeout(left)
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def do_POST(self) -> None:
        try:
            body = self._read_body()
        except BodyTooLarge as e:
            self.close_connection = True
            self._respond(413, {"error": "payload_too_large",
                                "detail": f"the body is {e.length} bytes; the limit is {MAX_BODY}"})
            self._drain(e.length)
            return
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
        with urllib.request.urlopen(base + "/v1/health", timeout=SELFTEST_TIMEOUT) as r:
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
        with urllib.request.urlopen(req, timeout=SELFTEST_TIMEOUT) as r:
            body = json.loads(r.read())
        check(r.status == 200 and "rows" in body, "POST /v1/compliance-pack returns a pack")
        check(r.getheader("Cache-Control") == "no-store", "responses are no-store")

        # a bad body -> 400
        req2 = urllib.request.Request(base + "/v1/compliance-pack", data=b"not json",
                                      headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req2, timeout=SELFTEST_TIMEOUT)
            check(False, "an invalid JSON body is refused")
        except urllib.error.HTTPError as e:
            check(e.code == 400, "an invalid JSON body returns 400")

        # An oversized body is refused from its Content-Length. Closing with the body unread
        # made the kernel RESET a client still sending, so it saw "connection reset" instead
        # of the refusal (the same defect serve_ask.py had). At 2 MiB it is not a race.
        import http.client
        import socket
        import time as _time

        def post_raw(body: bytes):
            conn = http.client.HTTPConnection(HOST, port, timeout=SELFTEST_TIMEOUT)
            try:
                conn.request("POST", "/v1/compliance-pack", body,
                             {"Content-Type": "application/json"})
                r = conn.getresponse()
                return r.status, r.read()
            except OSError as e:
                return type(e).__name__, b""
            finally:
                conn.close()
        st, _ = post_raw(b"x" * (2 * 1024 * 1024))
        check(st == 413, f"a body far beyond the cap gets 413, never a connection reset ({st})")

        # The drain has a TOTAL deadline: a client trickling a huge body cannot hold the thread.
        global DRAIN_SECONDS
        saved_drain, DRAIN_SECONDS = DRAIN_SECONDS, 0.5
        try:
            slow = socket.create_connection((HOST, port), timeout=10)
            slow.sendall(f"POST /v1/compliance-pack HTTP/1.1\r\nHost: {HOST}:{port}\r\n"
                         f"Content-Type: application/json\r\n"
                         f"Content-Length: {3 * 1024 * 1024}\r\n\r\n".encode())
            t0, closed, reply = _time.monotonic(), False, b""
            while _time.monotonic() - t0 < 5:
                try:
                    slow.sendall(b"x")
                except OSError:
                    closed = True
                    break
                slow.settimeout(0.2)
                try:
                    data = slow.recv(65536)
                    if data == b"" and reply:
                        closed = True
                        break
                    reply += data
                except socket.timeout:
                    pass
                except OSError:
                    # A reset or broken pipe once the server has answered and stopped
                    # draining IS the close this check waits for, not a failure.
                    closed = True
                    break
            took = _time.monotonic() - t0
            slow.close()
        finally:
            DRAIN_SECONDS = saved_drain
        check(b" 413 " in reply[:20], f"a trickled oversized body is answered 413 ({reply[:20]!r})")
        check(closed and took < 3, f"...and the drain stops at its total deadline ({took:.1f}s)")
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
