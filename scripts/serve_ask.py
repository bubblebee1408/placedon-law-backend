#!/usr/bin/env python3
"""The local demo server for the Ask prototype: web/assistant/ plus POST /v1/ask, one origin.

    python3 scripts/serve_ask.py                 # then open http://127.0.0.1:8021
    python3 scripts/serve_ask.py --port 9001
    python3 scripts/serve_ask.py --test

It is the one client /v1/ask is wired to (web/assistant/contract.md, the notice): the founder
approved a local demo. The page is served from the same origin as the route, so no CORS header
is ever sent, and a request that names another Host or comes from another Origin is refused
before anything runs (DNS rebinding, a cross-site form POST).

The security posture is scripts/serve_api.py's: bound to 127.0.0.1 only and never another
address (there is no host option); the question arrives in the POST body and is never logged;
every response is no-store and nosniff. Static files are read-only, from web/assistant/ only:
no directory listing, no dot-files, no path that resolves outside the directory (`..`, encoded,
absolute, backslash, NUL, symlink). A port already in use is refused, never shared.

POST /v1/ask goes to checker.api.handle in-process, so its 200s, 400s and its withheld 500
(`contract_violation`) keep the api's own shapes. The route lets an engine failure propagate
(contract §6 D12); here it becomes a 500 with no `state` -- never an answer or an abstention.
"""
import errno
import json
import socket
import socketserver
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.api import handle  # noqa: E402 -- after the path insert, as in serve_api.py

HOST = "127.0.0.1"
DEFAULT_PORT = 8021
ROOT = Path(__file__).resolve().parent.parent / "web" / "assistant"
MAX_BODY = 256 * 1024         # serve_api.py's cap: a question is small
ROUTE = "/v1/ask"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".md": "text/plain; charset=utf-8"}
# The page runs its own scripts and styles and talks to its own origin, nothing else. Links out
# (the eGazette copy of a figure) are navigations, which this does not restrict.
PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'")
ENGINE_FAILURE = {"error": "engine_failure",
                  "detail": "The engine failed on this request. No answer, partial or "
                            "otherwise, was produced."}


class PortInUse(OSError):
    """The port already has a listener. Refused rather than shared or silently moved."""


def static_path(root: Path, target: str) -> Path | None:
    """The file a request target names inside `root`, or None. Never a path outside it."""
    if not target.startswith("/"):
        return None                              # absolute-form or garbage
    path = target.split("?", 1)[0].split("#", 1)[0]
    try:
        path = unquote(path, errors="strict")    # decoded once; "%252e" stays the name "%2e"
    except UnicodeDecodeError:
        return None
    if "\x00" in path or "\\" in path:
        return None
    parts = path.split("/")[1:]
    if parts == [""]:
        parts = ["index.html"]
    # An empty part (//x, x/) is a directory or a doubled slash; a leading dot is ., .. or a
    # dot-file. None of them names a file this server serves.
    if any(not p or p.startswith(".") for p in parts):
        return None
    base = root.resolve()
    candidate = base.joinpath(*parts).resolve()  # resolve() follows symlinks, so a link out fails
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate if candidate.suffix in TYPES else None


class Handler(BaseHTTPRequestHandler):
    server_version = "PlacedonAsk/1"

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _send(self, status: int, payload: bytes, ctype: str, csp: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", csp)
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except ConnectionError:
            # The client went away mid-reply -- which is exactly what the page's own Cancel
            # button does (AbortController). Without this, socketserver prints a traceback
            # carrying this file's absolute path. There is nobody left to answer, so the
            # only correct action is to stop quietly.
            self.close_connection = True

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body, indent=1, ensure_ascii=False).encode("utf-8")
        self._send(status, payload, "application/json; charset=utf-8", "default-src 'none'")

    def _same_origin(self) -> bool:
        """The Host is this server's own, and an Origin, if sent, is too."""
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in hosts}

    def do_GET(self) -> None:
        if not self._same_origin():
            self._json(403, {"error": "forbidden", "detail": "not this server's origin"})
            return
        path = static_path(self.server.root, self.path)
        if path is None:
            self._json(404, {"error": "not_found", "detail": "no such file"})
            return
        self._send(200, path.read_bytes(), TYPES[path.suffix], PAGE_CSP)

    do_HEAD = do_GET

    def do_POST(self) -> None:
        if not self._same_origin():
            self._json(403, {"error": "forbidden", "detail": "not this server's origin"})
            return
        if self.path.split("?", 1)[0].rstrip("/") != ROUTE:
            self._json(404, {"error": "not_found",
                             "detail": f"this server forwards POST {ROUTE} only"})
            return
        try:
            body = self._read_body()
        except (ValueError, UnicodeDecodeError) as e:   # JSONDecodeError is a ValueError
            self._json(400, {"error": "bad_request", "detail": f"invalid JSON body: {e}"})
            return
        try:
            status, resp = handle("POST", ROUTE, body, generated_at=self._now())
        except BaseException as e:  # noqa: BLE001 -- D12: the route lets every engine failure out
            # BaseException, not Exception: an engine that raises SystemExit or
            # KeyboardInterrupt otherwise left the client with no reply at all and printed a
            # traceback carrying this path. The caller is answered first; a shutdown signal
            # is then re-raised so the server still stops.
            # The type only: the message could quote the request, and the log never does.
            sys.stderr.write(f"engine failure on POST {ROUTE}: {type(e).__name__}\n")
            self._json(500, dict(ENGINE_FAILURE))
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            return
        self._json(status, resp)

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        if length > MAX_BODY:
            raise ValueError("request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def handle_error(self, request, client_address) -> None:
        """socketserver's default prints a traceback with this file's absolute path.
        A dropped connection is ordinary here (Cancel); anything else is logged by type."""
        exc = sys.exc_info()[1]
        if not isinstance(exc, ConnectionError):
            sys.stderr.write(f"connection error from {client_address[0]}: {type(exc).__name__}\n")

    def log_message(self, fmt: str, *args) -> None:
        # Method and path only, never the query or the body (the question lives there).
        # A request line too broken to parse has no command or path yet.
        path = str(getattr(self, "path", "") or "").split("?")[0]
        sys.stderr.write(f"{getattr(self, 'command', None) or '-'} {path}\n")


class AskServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_port = False     # SO_REUSEPORT would let two servers share the port

    def server_bind(self) -> None:
        # HTTPServer.server_bind does a reverse DNS lookup of the host; loopback needs none.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = HOST, self.server_address[1]


def _listener_on(port: int) -> bool:
    """Whether something already accepts connections on 127.0.0.1:port (incl. a 0.0.0.0 bind)."""
    try:
        with socket.create_connection((HOST, port), timeout=0.5):
            return True
    except OSError:
        return False


def make_server(port: int, root: Path = ROOT) -> AskServer:
    """Bound to 127.0.0.1:port, or PortInUse. Port 0 picks a free port (tests)."""
    if port and _listener_on(port):
        raise PortInUse(errno.EADDRINUSE, f"127.0.0.1:{port} is already in use")
    try:
        srv = AskServer((HOST, port), Handler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            raise PortInUse(errno.EADDRINUSE, f"127.0.0.1:{port} is already in use") from e
        raise
    srv.root = root
    return srv


def serve(port: int = DEFAULT_PORT) -> int:
    try:
        srv = make_server(port)
    except PortInUse:
        print(f"Port {port} on 127.0.0.1 is already in use, so the demo server did not start.\n"
              f"Stop whatever is using it, or pick another port: "
              f"python3 scripts/serve_ask.py --port {port + 1}", file=sys.stderr)
        return 1
    print(f"Placedon Ask (local demo) on http://{HOST}:{port}  -- the page and POST {ROUTE}.\n"
          f"Answers come from deterministic engine calls on this machine; no model is called.\n"
          f"Ctrl-C stops it.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


# ── tests ────────────────────────────────────────────────────────────────────
def _test() -> int:
    import http.client
    import inspect
    import socket
    import tempfile
    import threading

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if cond:
            ok += 1
        else:
            fail += 1

    def start(root: Path = ROOT):
        srv = make_server(0, root)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    def raw(port: int, method: str, target: str, body: bytes | None = None,
            headers: dict | None = None) -> tuple[int, dict, bytes]:
        """One request with the target sent byte-for-byte: no client-side normalisation."""
        conn = http.client.HTTPConnection(HOST, port, timeout=30)
        try:
            conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
            hdrs = {"Host": f"{HOST}:{port}", **(headers or {})}
            if body is not None:
                hdrs.setdefault("Content-Type", "application/json")
                hdrs["Content-Length"] = str(len(body))
            for k, v in hdrs.items():
                if v is not None:
                    conn.putheader(k, v)
            conn.endheaders(body)
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def ask(port: int, body: dict | bytes, headers: dict | None = None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        st, h, b = raw(port, "POST", "/v1/ask", data, headers)
        try:
            return st, h, json.loads(b)
        except ValueError:
            return st, h, {"_raw": b[:200]}

    print("serve_ask")
    from checker.ask_contract import validate

    # ── binding ──────────────────────────────────────────────────────────────
    check(HOST == "127.0.0.1", "the server's one host is the loopback address")
    check("host" not in inspect.signature(serve).parameters
          and "host" not in inspect.signature(make_server).parameters,
          "no caller can choose another host (no host parameter to serve or make_server)")
    srv = start()
    port = srv.server_address[1]
    try:
        check(srv.server_address[0] == "127.0.0.1",
              f"it binds 127.0.0.1, never 0.0.0.0 ({srv.server_address[0]})")

        # A port already taken is refused, not shared.
        try:
            make_server(port).server_close()
            check(False, "a port another server is listening on is refused")
        except PortInUse:
            check(True, "a port another server is listening on is refused (PortInUse)")
        except Exception as e:  # noqa: BLE001 -- the test reports what it got
            check(False, f"a taken port raises PortInUse, not {type(e).__name__}")
        blocker = socket.socket()
        blocker.bind((HOST, 0))
        blocker.listen(1)
        try:
            make_server(blocker.getsockname()[1]).server_close()
            check(False, "a port a foreign listener holds is refused")
        except PortInUse:
            check(True, "a port a foreign (non-HTTP) listener holds is refused")
        except Exception as e:  # noqa: BLE001
            check(False, f"a foreign listener's port raises PortInUse, not {type(e).__name__}")
        finally:
            blocker.close()

        # ── static files ─────────────────────────────────────────────────────
        index = (ROOT / "index.html").read_bytes()
        st, h, b = raw(port, "GET", "/")
        check(st == 200 and b == index and h.get("content-type", "").startswith("text/html"),
              f"GET / serves index.html ({st}, {h.get('content-type')})")
        st, h, b = raw(port, "GET", "/index.html")
        check(st == 200 and b == index, f"GET /index.html serves index.html ({st})")
        check(h.get("cache-control") == "no-store" and h.get("x-content-type-options") == "nosniff",
              "static responses are no-store and nosniff")
        csp = h.get("content-security-policy", "")
        check("default-src 'self'" in csp and "frame-ancestors 'none'" in csp
              and "unsafe-inline" not in csp,
              f"the page is served with a same-origin CSP and no inline script ({csp[:60]})")
        st, h, b = raw(port, "HEAD", "/index.html")
        check(st == 200 and b == b"" and h.get("content-length") == str(len(index)),
              f"HEAD answers with the length and no body ({st})")
        import re
        assets = re.findall(r'(?:src|href)="([^"#:]+)"', index.decode())
        served = {a: raw(port, "GET", "/" + a)[0] for a in assets}
        check(assets and all(s == 200 for s in served.values()),
              f"every asset index.html names is served ({served})")
        st, h, b = raw(port, "GET", "/app.js")
        check(st == 200 and "javascript" in h.get("content-type", ""),
              f"a script is served as JavaScript ({h.get('content-type')})")

        # No directory listing.
        for target in ("/fixtures/", "/fixtures", "/tools/"):
            st, h, b = raw(port, "GET", target)
            check(st == 404 and b"answered_small_company" not in b and b"accept" not in b,
                  f"{target} is a 404, not a listing ({st})")

        # No path escapes: every spelling of "outside web/assistant" is a 404 that carries
        # nothing from the file it aimed at.
        claude = (ROOT.parent.parent / "CLAUDE.md").resolve()
        marker = b"Non-negotiable rules"
        assert marker in claude.read_bytes()
        escapes = [
            "/../../CLAUDE.md", "/../README.md", "/fixtures/../../../CLAUDE.md",
            "/%2e%2e/%2e%2e/CLAUDE.md", "/%2E%2E%2F%2E%2E%2FCLAUDE.md", "/..%2f..%2fCLAUDE.md",
            "/%252e%252e/%252e%252e/CLAUDE.md", "/.%2e/.%2e/CLAUDE.md",
            "/..\\..\\CLAUDE.md", "/%5c..%5c..%5cCLAUDE.md",
            "//etc/passwd", "/%2Fetc%2Fpasswd", "/etc/passwd",
            "/" + str(claude).lstrip("/"), "/%2F" + str(claude).lstrip("/").replace("/", "%2F"),
            str(claude), f"http://{HOST}:{port}/../../CLAUDE.md",
            "/index.html%00.js", "/index.html/", "/.git/HEAD", "/%2e/index.html",
            "/tools/accept.mjs", "/contract.md/..",
        ]
        leaked = []
        for target in escapes:
            try:
                st, h, b = raw(port, "GET", target)
            except (http.client.HTTPException, OSError) as e:
                st, b = f"refused ({type(e).__name__})", b""
            if st == 200 or marker in b or b"root:" in b:
                leaked.append((target, st))
        check(not leaked, f"{len(escapes)} path-escape spellings are all refused ({leaked})")

        # A symlink inside the served root that points outside it is not followed.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "site"
            root.mkdir()
            (root / "index.html").write_text("<p>inside</p>")
            (Path(td) / "secret.html").write_text("<p>outside</p>")
            (root / "link.html").symlink_to(Path(td) / "secret.html")
            s2 = start(root)
            try:
                p2 = s2.server_address[1]
                st_in = raw(p2, "GET", "/index.html")[0]
                st, h, b = raw(p2, "GET", "/link.html")
                check(st_in == 200 and st == 404 and b"outside" not in b,
                      f"a symlink out of the root is a 404 ({st_in}, {st})")
            finally:
                s2.shutdown()
                s2.server_close()

        # Same origin only: a request that names another host or comes from another origin is
        # refused before anything runs (DNS rebinding, cross-site POST).
        st, h, b = raw(port, "GET", "/index.html", headers={"Host": f"evil.example:{port}"})
        check(st == 403 and b"Placedon" not in b, f"a foreign Host header is refused ({st})")
        st, h, r = ask(port, {"question": "What does s.173 require?"},
                       headers={"Origin": "http://evil.example"})
        check(st == 403 and "state" not in r, f"a cross-origin POST is refused ({st})")
        st, h, r = ask(port, {"question": "What does s.173 require?"},
                       headers={"Origin": f"http://localhost:{port}"})
        check(st == 200, f"the page's own origin (localhost spelling) is accepted ({st})")
        st, _, _ = raw(port, "PUT", "/index.html", b"x")
        check(st in (405, 501), f"PUT is not a method this server takes ({st})")
        st, h, b = raw(port, "POST", "/v1/compliance-pack", b"{}")
        check(st == 404 and "state" not in json.loads(b),
              f"only /v1/ask is forwarded; other API routes are a 404 here ({st})")

        # ── POST /v1/ask: three real questions, answered in-process ───────────
        facts = {"company_class": "private", "incorporation_date": "2019-06-01",
                 "as_of": "2026-09-15", "financial_year": "2024-25",
                 "paid_up_capital_rupees": 120000000, "turnover_rupees": 800000000}
        st, h, r = ask(port, {"question": "Is this company a small company?", "as_of": "2026-09-15",
                              "context": {"kind": "general"}, "facts": facts,
                              "provisions": ["s.2(85)"],
                              "figures": ["small_company.paid_up_capital.prescribed",
                                          "small_company.turnover.prescribed"]})
        figs = r.get("figures") or []
        check(st == 200 and r.get("schema") == "placedon.ask/0" and r.get("state") == "answered"
              and validate(r) == [] and len(figs) == 2
              and all("880(E)" in f["instrument"] and f["source_url"].startswith("https://egazette")
                      for f in figs),
              f"small company, with facts -> answered on G.S.R. 880(E), valid "
              f"({st}, {r.get('state')}, {[f.get('amount') for f in figs]})")
        check(h.get("content-type", "").startswith("application/json")
              and h.get("cache-control") == "no-store", "the answer is JSON and no-store")

        st, h, r = ask(port, {"question": "What must we report to RBI for this share allotment "
                                          "to a foreign investor?", "context": {"kind": "general"}})
        body_ = r.get("body") or {}
        check(st == 200 and r.get("state") == "out_of_scope" and body_.get("key") == "FEMA1999"
              and body_.get("scope_status") == "DECLARED" and validate(r) == [],
              f"a DECLARED body's question -> out_of_scope with that body ({st}, {r.get('state')}, "
              f"{body_.get('key')}, {body_.get('scope_status')})")

        st, h, r = ask(port, {"question": "What does s.173 require?",
                              "context": {"kind": "general"}})
        refs = [c.get("ref") for c in r.get("confirmed") or []]
        s173 = next((c for c in r.get("confirmed") or [] if c.get("ref") == "ACT:COMPANIES_ACT_2013:S173"), {})
        check(st == 200 and r.get("state") == "partial" and validate(r) == []
              and "Board" in (s173.get("verbatim") or "") and not r.get("rows"),
              f"a text-only s.173 question -> partial with s.173's text, no row decided "
              f"({st}, {r.get('state')}, {refs})")
        check(r.get("uses_model") is False, "no model was used")

        # ── errors keep the api's shapes and never carry a state ──────────────
        st, h, r = ask(port, b"{not json")
        check(st == 400 and r.get("error") == "bad_request" and "state" not in r,
              f"a malformed body is a 400 in the api's shape ({st}, {r.get('error')})")
        st, h, r = ask(port, {"context": {"kind": "general"}})
        check(st == 400 and r.get("error") == "bad_request" and "question" in r.get("detail", ""),
              f"a body with no question is the api's own 400 ({st})")
        st, h, r = ask(port, b"x" * (300 * 1024))
        check(st in (400, 413) and "state" not in r, f"an oversized body is refused ({st})")

        import checker.ask as ask_mod
        saved = ask_mod.answer

        def boom(body, generated_at):
            raise RuntimeError("engine exploded")
        ask_mod.answer = boom
        try:
            st, h, r = ask(port, {"question": "What does s.173 require?"})
        finally:
            ask_mod.answer = saved
        check(st == 500 and "state" not in r and "schema" not in r and r.get("error")
              and "Traceback" not in json.dumps(r),
              f"an engine exception is a 500 with no state, no traceback ({st}, {sorted(r)})")

        ask_mod.answer = lambda body, generated_at: {"schema": "placedon.ask/0",
                                                     "state": "answered", "confidence": "HIGH"}
        try:
            st, h, r = ask(port, {"question": "x"})
        finally:
            ask_mod.answer = saved
        check(st == 500 and r.get("error") == "contract_violation" and "state" not in r,
              f"a contract violation stays the api's withheld 500 ({st}, {r.get('error')})")

        # The question is never written to the log.
        import io
        err, sys.stderr = sys.stderr, io.StringIO()
        try:
            ask(port, {"question": "Secret-ish question about s.173?"})
            logged = sys.stderr.getvalue()
        finally:
            sys.stderr = err
        check("Secret-ish" not in logged and "POST /v1/ask" in logged,
              f"the log names the route, never the question ({logged.strip()[:60]!r})")
    finally:
        srv.shutdown()
        srv.server_close()

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        raise SystemExit(_test())
    if len(sys.argv) == 3 and sys.argv[1] == "--port" and sys.argv[2].isdigit():
        raise SystemExit(serve(int(sys.argv[2])))
    if len(sys.argv) != 1:
        raise SystemExit("usage: python3 scripts/serve_ask.py [--port N | --test]")
    raise SystemExit(serve())
