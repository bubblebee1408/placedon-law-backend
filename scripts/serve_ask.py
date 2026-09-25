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

GET /v1/ask/documents and POST /v1/ask/document (D3) check ONE OF THIS REPOSITORY'S PUBLIC
TEST DOCUMENTS. They live under /v1/ask because what they return is a `placedon.ask/0` turn
-- the contract /v1/ask already serves -- and NOT at /v1/document, which sits one character
from checker/api.py's existing /v1/document-check, a different request and a different shape.
They also belong to this server rather than to the api: they read files under corpus/testdocs/,
and checker/api.py has no filesystem document access and must not gain one.

**There is no upload, and there will not be one.** The founder's rule is that no client or
confidential document goes anywhere; an upload box in a demo invites exactly that, and a demo
is where a lawyer would first try it. A body carrying document text is refused with NO_UPLOAD
and nothing is read from it.
"""
import errno
import json
import socket
import socketserver
import threading
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import document_date  # noqa: E402 -- after the path insert, as in serve_api.py
from checker.api import handle  # noqa: E402
from checker.orchestrator import NO_DOCUMENT_DATE  # noqa: E402
# D5's enumerator, imported read-only and never edited here. ONE list answers "is this
# document public": a second copy would be a second answer to the only question that
# keeps a confidential document out, and it refuses any path outside corpus/testdocs/.
from eval.prelabel.corpus import load_all as load_public_documents  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8021
ROOT = Path(__file__).resolve().parent.parent / "web" / "assistant"
MAX_BODY = 256 * 1024         # serve_api.py's cap: a question is small
ROUTE = "/v1/ask"
DOC_ROUTE = "/v1/ask/document"          # check one public test document -> a document turn
DOC_LIST_ROUTE = "/v1/ask/documents"    # the list the page offers; the only way in
POST_ROUTES = (ROUTE, DOC_ROUTE)
DOC_REQUEST_KEYS = frozenset({"document_id", "question"})
DEFAULT_DOC_QUESTION = "Is the law this document relies on still current?"
NO_UPLOAD = (
    "There is no upload here, by design. This demo checks the public documents held in "
    "this repository (corpus/testdocs/) and nothing else: no client document, nothing "
    "confidential and nothing you hold is sent anywhere by this page. Choose one of the "
    "listed documents instead.")
# A body naming any of these is trying to send a document, whatever it holds. Refused by the
# NAME, before the value is looked at, so the refusal cannot depend on reading what arrived.
UPLOAD_FIELDS = frozenset({"document", "documents", "text", "content", "body", "file",
                           "filename", "path", "upload", "pdf", "base64", "data", "url"})
# checker/api.py's document check needs a company profile to decide which obligations are in
# the frame: api._profile requires company_class and incorporation_date. These filings state no
# incorporation date, so the profile is a DECLARED PLACEHOLDER, named as one everywhere.
#
# It was claimed here -- and in the README, the commit body and the note the page draws -- that
# it could not decide anything. **That was false, and the D3 verifier proved it.** Measured:
#
#   company_class absent  -> 400 "missing required field: 'company_class'"
#   company_class public  -> 200, decides s.2(85) DOES_NOT_APPLY, "a public company is never
#                            a small company"
#   company_class private -> 200, decides nothing
#
# So there are exactly two choices, and "supply no class" is not one of them without changing
# api._profile, which is another job's file and a contract change.
#
# **`public` is kept and the false claim is dropped instead.** Counted, after collapsing
# whitespace (three of them tab-separate the words, which a naive grep misses): all 9 documents
# that declare a date -- the only ones this profile is ever applied to -- name BSE Limited and
# the National Stock Exchange of India Limited on their own face, and 2 of those 9 also carry
# an L.....PLC...... CIN, which is a listed public company's. So `public` is the class the
# reachable documents support. Switching to `private` would buy a quieter card by supplying a
# class contradicted by every document the check can actually reach, so that an obligation
# resolves the way that looks tidier. That is the failure this product exists to detect, and it
# would be this repository committing it.
#
# Narrower than it was, and deliberately (D3 verifier round 2, finding 2). It used to say
# "each document is addressed to" the two exchanges and "FALSE of every document on the list".
# Neither reaches that far: 3 of the 18 real filings name neither exchange -- the Board's
# Report extracts, which are not exchange filings -- and 11 of the 29 on the list are ICSI
# specimens for which neither class is established. None of those 14 declares a date, so none
# is ever checked, which is why the conclusion survives the correction and the quantifier
# does not.
#
# What was wrong was the sentence, not the class. `_profile_decides()` now COMPUTES which rows
# the profile decided on its own and the note names them, so the claim cannot drift from the
# register: if s.2(85) stops resolving, the sentence changes with it.
PLACEHOLDER_PROFILE = {"company_class": "public", "incorporation_date": "2014-04-01"}
# The only two row states that decide nothing about anybody. Anything else is a decision, and
# a decision reached from the placeholder alone has to be named as one.
UNDECIDED = ("APPLIES_UNDETERMINED", "CANNOT_DETERMINE")
_PROFILE_SUPPLIED = (
    "The company profile used for this check was supplied by this demo, not read from the "
    "document: these filings state no incorporation date. No company facts beyond the class "
    "and no evidence were sent with it. ")
# Not "the law the document rests on" (finding 5): nothing here established what law it rests
# on. Its date chose which two register snapshots were compared, and that comparison is the
# whole of what this turn decides.
_WHAT_IS_DECIDED = (
    "What is decided here is whether the legal basis of each obligation moved between the date "
    "this document declares and today.")


def _profile_decides(turn: dict) -> list[dict]:
    """The rows the placeholder profile decided on its own, with the engine's own basis.

    Nothing the document says reached these. No evidence was sent, so the only input that
    could have decided them is the profile this demo supplied, and a card that shows them has
    to say so.
    """
    rows = (turn.get("rows") or []) + (turn.get("confirmed") or [])
    return [{"provision": r.get("provision"), "duty": r.get("duty"),
             "state": r.get("state"), "basis": r.get("basis")}
            for r in rows if r.get("state") not in UNDECIDED]


def _profile_note(decides: list[dict]) -> str:
    """What the placeholder is, and exactly what it decided -- never a claim that it decided
    nothing, which is the sentence that was false."""
    if not decides:
        return (_PROFILE_SUPPLIED + "No row below is decided about any company \u2014 each is "
                "undetermined. " + _WHAT_IS_DECIDED)
    many = len(decides) != 1
    named = "; ".join(f"{d['provision']} \u2014 {d['basis']}" for d in decides)
    return (_PROFILE_SUPPLIED + f"{len(decides)} row{'s' if many else ''} below "
            f"{'are' if many else 'is'} decided by that profile alone, and by nothing this "
            f"document says: {named}. Every other row is undetermined. " + _WHAT_IS_DECIDED)


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


_CATALOGUE: dict[str, dict] | None = None


def _entry(doc) -> dict:
    """One public document as the page sees it: what it is, and the date it declares.

    `date_line` is the line in the FILE, which is the only number a reader can open. It is not
    what document_date.read() returns: that counts lines in the text it is handed, and what it
    is handed has had this repository's own `#` provenance header stripped by
    corpus.read_document -- so the raw number is short by the header. The D3 verifier proved
    what that costs: tcpl_62nd showed line 1114, the date is on 1121, and 1114 reads "Devices
    or Tablets or through Laptop connecting via"; on the three board outcomes the pointer
    landed INSIDE our own header, at `# https://routemobile.com/...`. A locator that opens a
    line saying something else is worse than no locator. corpus.Document keeps `line_map` for
    exactly this, and this file's test now opens every dated file and checks the line against
    what is written there.
    """
    reading = document_date.read(doc.text)
    line = (doc.line_map[reading.line - 1]
            if reading.line and reading.line <= len(doc.line_map) else None)
    return {"id": doc.doc_id, "title": doc.title, "kind": doc.kind, "source": doc.source,
            "path": doc.path, "chars": doc.chars,
            "date": reading.value.isoformat() if reading.value else None,
            "date_line": line, "date_quote": reading.quote,
            "declarations_unread": reading.unread,
            "why_no_date": reading.why}


def catalogue() -> dict[str, dict]:
    """Every public test document, by id. Read once: the files do not change under a run."""
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = {d.doc_id: _entry(d) for d in load_public_documents()}
    return _CATALOGUE


def document_turn(body, *, generated_at: str) -> tuple[int, dict]:
    """POST /v1/ask/document -> (status, payload). No model is called on this path.

    200 is `{"document": <the entry, plus the placeholder profile>, "turn": <placedon.ask/0>}`.
    The turn is exactly what /v1/ask returns and carries no key the contract does not
    describe; this demo's own metadata rides beside it, never inside it.
    """
    if not isinstance(body, dict):
        return 400, {"error": "bad_request", "detail": "request body must be a JSON object"}
    sending = sorted(set(body) & UPLOAD_FIELDS)
    if sending:
        return 400, {"error": "upload_refused", "detail": NO_UPLOAD, "fields": sending}
    unknown = sorted(set(body) - DOC_REQUEST_KEYS)
    if unknown:
        return 400, {"error": "bad_request",
                     "detail": f"unknown field(s): {', '.join(unknown)}. This route takes "
                               f"{', '.join(sorted(DOC_REQUEST_KEYS))}"}
    doc_id = body.get("document_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        return 400, {"error": "bad_request",
                     "detail": "'document_id' names one of the documents "
                               f"GET {DOC_LIST_ROUTE} lists"}
    entry = catalogue().get(doc_id)
    if entry is None:
        # The id, not the value of anything read: an unknown id is a client bug, and this
        # message must never become a way to ask whether a path exists on this machine.
        return 404, {"error": "not_found",
                     "detail": f"no public test document is named {doc_id!r}. "
                               f"GET {DOC_LIST_ROUTE} lists every one this demo will check"}
    if entry["date"] is None:
        # The engine's own words for this refusal, not this file's: the orchestrator will not
        # run without a document date, and a guessed one would silently move the law the
        # check is run against. `reason` is what the reader found, which is a different fact.
        return 422, {"error": "no_document_date", "detail": NO_DOCUMENT_DATE,
                     "reason": entry["why_no_date"], "document": entry}
    request = {"question": body.get("question", DEFAULT_DOC_QUESTION),
               "as_of": generated_at[:10],
               "context": {"kind": "document", "document_date": entry["date"]},
               "facts": dict(PLACEHOLDER_PROFILE, document_date=entry["date"],
                             as_of=generated_at[:10])}
    status, turn = handle("POST", ROUTE, request, generated_at=generated_at)
    if status != 200:
        return status, turn          # the api's own 400 / withheld 500, unchanged
    decides = _profile_decides(turn)
    return 200, {"document": dict(entry, profile=dict(PLACEHOLDER_PROFILE),
                                  profile_decides=decides,
                                  profile_note=_profile_note(decides)),
                 "turn": turn}


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
        if self.path.split("?", 1)[0].rstrip("/") == DOC_LIST_ROUTE:
            self._json(200, {"documents": list(catalogue().values()), "no_upload": NO_UPLOAD})
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
        route = self.path.split("?", 1)[0].rstrip("/")
        if route not in POST_ROUTES:
            self._json(404, {"error": "not_found",
                             "detail": "this server takes POST "
                                       + " and ".join(POST_ROUTES) + " only"})
            return
        try:
            body = self._read_body()
        except ClientGone:
            self.close_connection = True
            return
        except (ValueError, UnicodeDecodeError) as e:   # JSONDecodeError is a ValueError
            self._json(400, {"error": "bad_request", "detail": f"invalid JSON body: {e}"})
            return
        try:
            status, resp = (document_turn(body, generated_at=self._now())
                            if route == DOC_ROUTE
                            else handle("POST", ROUTE, body, generated_at=self._now()))
        except BaseException as e:  # noqa: BLE001 -- D12: the route lets every engine failure out
            # BaseException, not Exception: an engine that raises SystemExit or
            # KeyboardInterrupt otherwise left the client with no reply at all and printed a
            # traceback carrying this path. The caller is answered first; a shutdown signal
            # is then re-raised so the server still stops.
            # The type only: the message could quote the request, and the log never does.
            sys.stderr.write(f"engine failure on POST {route}: {type(e).__name__}\n")
            self._json(500, dict(ENGINE_FAILURE))
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                # Answer first, then stop -- but by ASKING the server to stop rather than
                # re-raising: re-raising escaped the worker thread and the default excepthook
                # printed a traceback naming this file, which is the very thing this handler
                # exists to prevent (D2 verifier, minor 2). shutdown() must not run on the
                # serving thread, so it goes on its own.
                sys.stderr.write("shutdown requested by the engine; stopping\n")
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._json(status, resp)

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        if length > MAX_BODY:
            raise ValueError("request body too large")
        try:
            raw = self.rfile.read(length)
        except ConnectionError as e:
            # Headers arrived, the body never did: the client vanished mid-request. There is
            # nobody to answer, so this is not an error to report -- it is the other half of
            # the Cancel case, and _send's guard does not cover it.
            raise ClientGone() from e
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:
        # Method and path only, never the query or the body (the question lives there).
        # A request line too broken to parse has no command or path yet.
        path = str(getattr(self, "path", "") or "").split("?")[0]
        sys.stderr.write(f"{getattr(self, 'command', None) or '-'} {path}\n")


class ClientGone(Exception):
    """The client disconnected before it could be answered. Not a failure of ours."""


class AskServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_port = False     # SO_REUSEPORT would let two servers share the port

    def handle_error(self, request, client_address) -> None:
        """socketserver's default prints a traceback carrying this file's absolute path.
        It calls this on the SERVER, not the handler -- an override on the handler (86d23d6)
        never ran, which the D2 verifier proved by identity against BaseServer's. A dropped
        connection is ordinary here (Cancel, or a client that vanishes after its headers);
        anything else is recorded by type only, because the message could quote the request.
        """
        exc = sys.exc_info()[1]
        if not isinstance(exc, (ConnectionError, ClientGone)):
            sys.stderr.write(f"request from {client_address[0]} failed: {type(exc).__name__}\n")

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

        # ── the public document list, and checking one (D3) ───────────────────
        # There is no upload and no way to reach a file this repository does not hold.
        st, h, r = raw(port, "GET", "/v1/ask/documents")
        docs = json.loads(r) if st == 200 else {}
        listed = {d["id"]: d for d in docs.get("documents", [])}
        public = {d.doc_id for d in load_public_documents()}
        check(st == 200 and listed and set(listed) == public,
              f"the list is every public corpus document and nothing else "
              f"({st}, {len(listed)} listed, {len(public)} public)")
        check("no upload" in docs.get("no_upload", "").lower()
              or "There is no upload" in docs.get("no_upload", ""),
              "the list carries the refusal the page shows if anyone tries to upload")
        check(bool(listed) and all(d["path"].startswith("corpus/testdocs/") for d in listed.values()),
              "every listed document lives under corpus/testdocs/")
        check(bool(listed) and not any(k in d for d in listed.values()
                                       for k in ("text", "content", "body")),
              "the list carries no document text -- it is a menu, not a copy")

        # A document that declares its date is checked against that date.
        DATED = "agm_notices/tcpl_62nd_agm_notice_2025"
        check(listed.get(DATED, {}).get("date") == "2025-04-23",
              f"the list shows the date the document itself declares "
              f"({listed.get(DATED, {}).get('date')})")
        st, h, r = raw(port, "POST", "/v1/ask/document",
                       json.dumps({"document_id": DATED}).encode())
        r = json.loads(r)
        turn = r.get("turn") or {}
        check(st == 200 and turn.get("schema") == "placedon.ask/0" and validate(turn) == [],
              f"checking a public document returns a valid placedon.ask/0 turn "
              f"({st}, {validate(turn)})")
        check(turn.get("context", {}).get("kind") == "document"
              and turn["context"].get("document_date") == "2025-04-23",
              f"...a DOCUMENT turn, dated by the document itself ({turn.get('context')})")
        check(bool(turn.get("scope_frame")) and turn["scope_frame"].get("checked_count"),
              "...carrying the scope frame: what was checked, and what was not")
        lv = turn.get("law_version") or {}
        check(lv.get("point_in_time_requested") == "2025-04-23"
              and lv.get("point_in_time_verified") is False
              and "not the law as it stood" in lv.get("statement", "").lower()
              or "Do not treat any text below as the law as it stood" in lv.get("statement", ""),
              "...and the law-version line, which says this is not the law at the document's date")
        check(any("880(E)" in (x.get("governs_now") or "") for x in turn.get("superseded") or []),
              f"...and the instrument that moved under this document "
              f"({[x.get('governs_now', '')[:20] for x in turn.get('superseded') or []]})")
        check(turn.get("uses_model") is False, "no model is called on the document path")
        # NOT "the profile decides nothing about any company": it decides s.2(85) on a 2026
        # document, and the single 2025 document this test used to run made that claim look
        # true, because there s.2(85) lands in `superseded` instead. The claim is replaced by
        # the invariant that survives a changing register -- whatever it decides is NAMED --
        # checked across four documents spanning both years (D3 verifier, finding 2).
        spans = ["agm_notices/tcpl_62nd_agm_notice_2025",            # 2025: s.2(85) superseded
                 "agm_notices/routemobile_22nd_agm_notice_2026",     # 2026: s.2(85) decided
                 "agm_notices/tataelxsi_37th_agm_notice_2026",
                 "board_outcomes/routemobile_outcome_board_meeting_2024-05-29"]
        unnamed, silent, ever = [], [], False
        for doc_id in spans:
            st, _, rr = raw(port, "POST", "/v1/ask/document",
                            json.dumps({"document_id": doc_id}).encode())
            rr = json.loads(rr)
            t2, d2 = rr.get("turn") or {}, rr.get("document") or {}
            rows = (t2.get("rows") or []) + (t2.get("confirmed") or [])
            got = {(x.get("provision"), x.get("state")) for x in rows
                   if x.get("state") not in UNDECIDED}
            named = {(x.get("provision"), x.get("state"))
                     for x in d2.get("profile_decides") or []}
            ever = ever or bool(got)
            if st != 200 or got != named:
                unnamed.append((doc_id, sorted(got), sorted(named)))
            if ("decided by that profile alone" in d2.get("profile_note", "")) != bool(got):
                silent.append((doc_id, len(got)))
        check(not unnamed,
              f"every row the placeholder decides is named as one, in both years ({unnamed[:2]})")
        check(not silent,
              f"...and the note says so exactly when there is something to say ({silent[:2]})")
        check(ever, "at least one document in the span really does have a row decided by the "
                    "profile -- otherwise this check would pass on a register deciding nothing")
        check("the law the document rests on" not in json.dumps(r),
              "the note does not claim to have established what law the document rests on")
        doc = r.get("document") or {}
        check(doc.get("id") == DATED and doc.get("profile") == PLACEHOLDER_PROFILE
              and "supplied by this demo" in doc.get("profile_note", ""),
              "the response names the document and says the profile was the demo's own")
        check(bool(r.get("turn")) and "state" not in r and "schema" not in r,
              "the demo's own metadata rides beside the turn, never inside it")
        st, h, r2 = raw(port, "POST", "/v1/ask/document",
                        json.dumps({"document_id": DATED,
                                    "question": "Which of these rules moved?"}).encode())
        check(st == 200 and json.loads(r2)["turn"]["question"] == "Which of these rules moved?",
              "a typed question is the turn's question, verbatim")

        # The line number is a locator a reader opens. It must be the line in the FILE, and
        # never a line of this repository's own provenance header (D3 verifier, finding 1).
        # Every dated document, not one: the single-document test passed while 9 of 9 were wrong.
        root = Path(__file__).resolve().parent.parent
        dated = [d for d in listed.values() if d["date"]]
        astray = []
        for d in dated:
            lines = (root / d["path"]).read_text(encoding="utf-8", errors="replace").splitlines()
            at = d["date_line"] or 0
            got = lines[at - 1] if 0 < at <= len(lines) else ""
            # Both halves: the line is the one the quote came from, AND it declares the date
            # that was served. Quote-only would catch a future change that sourced date_quote
            # from the wrong line on just 3 of the 9 (D3 verifier round 2).
            again = document_date.read(got)
            if (got.strip() != d["date_quote"] or got.startswith("#")
                    or again.value is None or again.value.isoformat() != d["date"]):
                astray.append((d["id"], at, got[:40],
                               again.value.isoformat() if again.value else None))
        check(len(dated) >= 9 and not astray,
              f"every date_line opens the line its quote came from and that line declares the "
              f"served date, in its own file, never the provenance header "
              f"({len(dated)} dated; {astray[:3]})")

        # ── no date, no check: the engine's own refusal, never a guessed date ──
        for undated, what in (("icsi_specimens/09_minutes_agm_annexXVI", "a specimen with blanks"),
                              ("board_outcomes/routemobile_outcome_board_meeting_2025-11-03",
                               "a filing that bears two dates")):
            st, h, r = raw(port, "POST", "/v1/ask/document",
                           json.dumps({"document_id": undated}).encode())
            r = json.loads(r)
            check(st == 422 and r.get("error") == "no_document_date"
                  and r.get("detail") == NO_DOCUMENT_DATE
                  and "state" not in r and "turn" not in r,
                  f"{what} is refused in the engine's own words ({st}, {r.get('error')})")
        st, h, r = raw(port, "POST", "/v1/ask/document",
                       json.dumps({"document_id":
                                   "board_outcomes/routemobile_outcome_board_meeting_2025-11-03"}
                                  ).encode())
        r = json.loads(r)
        check("2025-11-03" in r.get("reason", "") and "2025-11-04" in r.get("reason", ""),
              f"...and the two-dated filing's reason names both dates ({r.get('reason', '')[:50]})")

        # ── no upload, and no way to reach a file off the list ─────────────────
        for field in ("text", "document", "file", "path", "base64", "url"):
            st, h, r = raw(port, "POST", "/v1/ask/document",
                           json.dumps({"document_id": DATED,
                                       field: "PRIVATE BOARD MINUTES"}).encode())
            r = json.loads(r)
            check(st == 400 and r.get("error") == "upload_refused"
                  and r.get("detail") == NO_UPLOAD and "turn" not in r
                  and "PRIVATE" not in json.dumps(r),
                  f"a body carrying {field!r} is refused, and the text is never echoed ({st})")
        for bad in ("../../CLAUDE.md", "/etc/passwd", "corpus/testdocs/MANIFEST.md", "",
                    "agm_notices/../../../CLAUDE", 7, None):
            st, h, r = raw(port, "POST", "/v1/ask/document",
                           json.dumps({"document_id": bad}).encode())
            r = json.loads(r)
            check(st in (400, 404) and "turn" not in r and "Non-negotiable" not in json.dumps(r)
                  and "root:" not in json.dumps(r),
                  f"document_id {bad!r} reaches nothing ({st})")
        st, h, r = raw(port, "POST", "/v1/ask/document",
                       json.dumps({"document_id": DATED, "facts": {"company_class": "opc"}}).encode())
        check(st == 400 and json.loads(r).get("error") == "bad_request",
              f"a field this route does not take is refused, not ignored ({st})")

        # An engine failure on this route is a 500 with no state, like /v1/ask's.
        import checker.ask as _ask
        _saved = _ask.answer

        def _boom(body, generated_at):
            raise RuntimeError("engine exploded")
        _ask.answer = _boom
        try:
            st, h, r = raw(port, "POST", "/v1/ask/document",
                           json.dumps({"document_id": DATED}).encode())
        finally:
            _ask.answer = _saved
        r = json.loads(r)
        check(st == 500 and "state" not in r and "turn" not in r
              and "Traceback" not in json.dumps(r),
              f"an engine failure on the document route is a 500 with no state ({st})")

        # The document id is a path; the log must not carry it either.
        import io as _io
        _err, sys.stderr = sys.stderr, _io.StringIO()
        try:
            raw(port, "POST", "/v1/ask/document", json.dumps({"document_id": DATED}).encode())
            logged = sys.stderr.getvalue()
        finally:
            sys.stderr = _err
        check("tcpl" not in logged and "POST /v1/ask/document" in logged,
              f"the log names the route, never the document ({logged.strip()[:60]!r})")

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
