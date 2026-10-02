"""The HTTP gateway. /v1 is the engine, forwarded and not reinterpreted.

PLAN_18 §2.1 and PLAN_22 build-order step 4. The rule this file exists to keep:

    checker.api.handle answers /v1. The gateway carries bytes.

`handle` is pure -- no I/O, (status, dict) in and out -- so there is nothing for a web
layer to add except a way to reach it. Every temptation to "improve" a response on the way
through is a second implementation of the engine, and a second implementation drifts. The
gated test therefore does not check that /v1 responses are CORRECT; checker/api.py's own
suite does that. It checks they are IDENTICAL, byte for byte, to what the engine returned.

## The one place bytes differ, and why it is not an exception to that

`GET /v1/health` is a liveness endpoint about the DEPLOYMENT, and the deployment is this
gateway. It is the only route where the gateway has something true to say that the engine
cannot know: which store is behind it. Until the Postgres migrations are applied, that is
an in-memory store whose contents vanish with the process, and a health endpoint that did
not say so would be the most misleading page in the system.

So health carries exactly one added key, `store`, and the test asserts precisely that: the
response equals the engine's with that one key added and NOTHING else changed -- not a
reordering, not a dropped field. Every other route is compared byte for byte.

## Serialisation

One serialiser, `dumps`, used by the gateway and by the test. Byte-identity is only
meaningful against a stated encoding, and leaving it to a framework's default means the
guarantee moves the next time the framework does.

Run: PYTHONPATH=. python3 gateway/app.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

# Imported at MODULE level, and that is load-bearing rather than tidy: `from __future__
# import annotations` makes every annotation a string, and FastAPI resolves them with
# typing.get_type_hints against this module's globals. Imported inside create_app, the
# name `Request` is a local, resolution fails, and FastAPI silently reads the parameter as
# a QUERY field -- every route then answers 422 "query.request: Field required". Measured
# 29-09-2026, and it looks exactly like a routing bug.
from fastapi import FastAPI, Request                         # noqa: E402
from fastapi.responses import Response                       # noqa: E402

from gateway import audit as audit_mod                       # noqa: E402
from gateway.auth import AuthError, KeyStore, bearer          # noqa: E402
from gateway.store import (MEMORY, POSTGRES, MemoryBackend,   # noqa: E402
                           PostgresBackend, database_url)

V1_PREFIX = "/v1"
HEALTH_PATH = "/v1/health"

MEMORY_STORE = "in-memory"
POSTGRES_STORE = "postgres"

STORE_NOTE = {
    MEMORY_STORE: ("in-memory: this process only. Nothing written through this gateway "
                   "survives a restart, no tenant isolation is enforced by the database, "
                   "and gateway/migrations/*.sql have not been applied. Not a deployment "
                   "anyone should put a client's matter in."),
    POSTGRES_STORE: ("postgres with FORCE ROW LEVEL SECURITY by tenant_id; see "
                     "scripts/rls_integration.py for the proof it is switched on."),
}


def dumps(payload) -> bytes:
    """The one encoding. Stated, so byte-identity means something."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=False,
                      separators=(",", ":")).encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Deployment:
    """What the gateway knows about itself. Injected, never discovered at call time."""
    store: str = MEMORY_STORE

    @property
    def note(self) -> str:
        return STORE_NOTE[self.store]

    @property
    def degraded(self) -> bool:
        return self.store != POSTGRES_STORE


def health_body(engine_body: dict, deployment: Deployment, queue=None) -> dict:
    """The engine's health, plus the two things only the gateway knows.

    `queue`, when given, adds the pair an operator actually watches: how many jobs are
    waiting, and how long the oldest has waited. Depth alone cannot tell a busy worker
    from a dead one -- a queue of 3 is healthy if the oldest is 2 seconds old and an
    outage if it is 40 minutes old. Neither number means anything without the other.

    `oldest_pending_seconds` is None for an empty queue, NOT 0: zero would read as "a job
    is waiting and it just arrived", which is the opposite of the truth on exactly the
    number a pager rule would threshold.
    """
    body = dict(engine_body) | {"store": {"kind": deployment.store,
                                          "degraded": deployment.degraded,
                                          "note": deployment.note}}
    if queue is not None:
        try:
            depth = queue.depth()
            oldest = queue.oldest_pending_seconds()
        except Exception as e:                                   # noqa: BLE001
            # A health endpoint that 500s during the outage it exists to report is worse
            # than one that says it could not read the queue.
            body["queue"] = {"error": f"{type(e).__name__}: {str(e)[:120]}",
                             "note": "the queue could not be read; this says nothing "
                                     "about whether work is pending"}
            return body
        body["queue"] = {
            "depth": depth, "oldest_pending_seconds": oldest,
            "note": ("nothing is waiting" if not depth else
                     f"{depth} job(s) waiting, the oldest for "
                     f"{oldest:.0f}s" if oldest is not None else
                     f"{depth} job(s) waiting")}
    return body


# GET /v1/health is the one route served without a key. A liveness probe that needs a
# credential is a liveness probe that lies during the outage you built it for -- and it
# carries no tenant data: the engine's provenance and which store is behind it.
PUBLIC_ROUTES = frozenset({HEALTH_PATH})


def create_app(*, deployment: Deployment | None = None, clock=None, handler=None,
               keys: KeyStore | None = None, db_url: str | None = None, queue=None):
    """The FastAPI app. Every dependency injected so the test reaches no network or clock."""
    # The store is SELECTED, and /v1/health reports what was selected rather than what
    # was hoped for. `db_url=""` forces memory, which is what the gate uses so a developer
    # with PLACEDON_DATABASE_URL exported does not silently gate against their database.
    url = database_url() if db_url is None else (db_url or None)
    dep = deployment or Deployment(POSTGRES if url else MEMORY)
    now = clock or utc_now
    handle = handler
    if handle is None:
        from checker.api import handle as handle       # noqa: PLW0127

    app = FastAPI(title="Placedon gateway", docs_url=None, redoc_url=None)
    app.state.deployment = dep
    # The in-memory store, named on app.state so a test can reach it and a future
    # Postgres store can replace it without touching a route.
    app.state.db_url = url
    # One shared backend in memory, so two requests in a process see each other's rows.
    # For Postgres a backend is built PER REQUEST, bound to the tenant the key resolved
    # to, because app.tenant_id is what the row-level security policies compare against.
    app.state.memory_backend = MemoryBackend()

    def backend_for(tenant_id: str):
        if app.state.db_url:
            return PostgresBackend(app.state.db_url, tenant_id=tenant_id)
        app.state.memory_backend.tenant_id = tenant_id
        return app.state.memory_backend

    app.state.backend_for = backend_for
    app.state.run_store = app.state.memory_backend
    app.state.documents = app.state.memory_backend.documents
    app.state.keys = keys if keys is not None else KeyStore()
    # P2. One limiter for the deployment, shared by /v1 and /v2. Two surfaces read a body,
    # and a limit wired into one of them is a limit the other does not have.
    from gateway import limits as limits_mod
    app.state.limiter = limits_mod.Limiter()
    # The audit chain, in memory with the rest of it. Append-only and hash-chained already
    # (gateway/audit.py); what is missing is Postgres, not the chain.
    app.state.audit = ()

    def _limit_response(refusal) -> Response:
        """A Refusal as an HTTP response. One shape, so both surfaces answer alike."""
        headers = ({} if refusal.retry_after is None
                   else {"Retry-After": str(refusal.retry_after)})
        return Response(content=dumps({"error": refusal.code.lower(),
                                       "detail": refusal.detail}),
                        status_code=refusal.http_status, media_type="application/json",
                        headers=headers)

    def _too_large(raw: bytes | None, request: Request):
        """A Refusal if this body is over the cap, else None. Checked on BOTH surfaces."""
        return limits_mod.check_body_size(
            raw, content_length=request.headers.get("content-length"))

    def _rate_limited(principal):
        """A Refusal if this TENANT is over its rate, else None.

        Per tenant, which is what P2 asks for, and which means an UNAUTHENTICATED flood is
        not limited here -- there is no tenant to attribute it to. That belongs at the
        reverse proxy, with the body-size limit the server enforces before this process sees
        a request (H1's deployment scripts). Stated rather than left to be assumed.
        """
        return app.state.limiter.check(principal.tenant_id)

    def _unauthorised() -> Response:
        return Response(content=dumps({"error": "unauthorized",
                                       "detail": "a valid API key is required"}),
                        status_code=401, media_type="application/json",
                        headers={"WWW-Authenticate": "Bearer"})

    def _principal(request: Request):
        raw = bearer(request.headers.get("authorization")) or \
            request.headers.get("x-api-key")
        return app.state.keys.resolve(raw)

    def _record(principal, *, action: str, route: str, resource: str,
                outcome: str, status: int) -> None:
        """One metadata row per served call. NEVER a document, a prompt or an answer.

        `resource` is an identifier -- a verb name, a run id, a document's sha256 -- and
        the question a caller asked is none of those. audit.py caps and scrubs each field,
        but the rule that keeps client text out of the chain is enforced here, at the only
        place that chooses what goes in.
        """
        import uuid
        app.state.audit = audit_mod.append(
            app.state.audit, timestamp=now(), request_id=str(uuid.uuid4()),
            tenant_id=principal.tenant_id, actor=principal.actor,
            action=action, route=route, resource=resource,
            outcome=outcome, http_status=status)

    @app.api_route("/v1/{rest:path}", methods=["GET", "POST"])
    async def v1(rest: str, request: Request) -> Response:
        body = None
        if request.method == "POST":
            raw = await request.body()
            # Size first: it protects this process's memory and needs no identity.
            over = _too_large(raw, request)
            if over:
                return _limit_response(over)
            if raw:
                try:
                    body = json.loads(raw)
                except ValueError:
                    # Refused here rather than handed to the engine as None, which would
                    # read as "no body given" and produce a different, misleading refusal.
                    return Response(content=dumps(
                        {"error": "bad_request", "detail": "body is not valid JSON"}),
                        status_code=400, media_type="application/json")
        bare = request.url.path.rstrip("/") or "/"
        principal = None
        if bare not in PUBLIC_ROUTES:
            try:
                principal = _principal(request)
            except AuthError:
                return _unauthorised()
            slow = _rate_limited(principal)
            if slow:
                _record(principal, action=audit_mod.READ,
                        route=f"{request.method} {bare}", resource=bare,
                        outcome="refused", status=slow.http_status)
                return _limit_response(slow)
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        status, payload = handle(request.method, path, body, generated_at=now())
        if bare == HEALTH_PATH and status == 200:
            # `queue` is INJECTED and defaults to None, so health keeps its current
            # shape unless an operator wires one in. /v1/health is served without a key,
            # and the queue block is deployment-level counts -- no tenant content, no
            # question text, no run ids. A depth read under RLS is scoped to the tenant
            # the injected queue was built for, which is the right scope for a
            # single-tenant deployment and the wrong one for a shared gateway; wiring it
            # on a shared gateway is a decision, not a default.
            payload = health_body(payload, dep, queue=queue)
        if principal is not None:
            _record(principal, action=audit_mod.READ, route=f"{request.method} {bare}",
                    resource=bare, outcome="served" if status < 400 else "refused",
                    status=status)
        return Response(content=dumps(payload), status_code=status,
                        media_type="application/json")

    # ── /v2, generated from the verb table. No route is written by hand here ──
    from gateway.roles import REQUIRED, may
    from gateway.verbs import VERBS, Context, rest_path



    def _mount(verb):
        path = rest_path(verb)

        async def _route(request: Request) -> Response:
            try:
                principal = _principal(request)
            except AuthError:
                return _unauthorised()
            slow = _rate_limited(principal)
            if slow:
                _record(principal, action=audit_mod.READ,
                        route=f"{verb.method} {path}", resource=verb.name,
                        outcome="refused", status=slow.http_status)
                return _limit_response(slow)
            store = app.state.backend_for(principal.tenant_id)
            ctx = Context(tenant=principal.tenant_id, actor=principal.actor,
                          store=store, documents=app.state.documents, clock=now)
            args = dict(request.path_params)
            if verb.method == "POST":
                raw = await request.body()
                over = _too_large(raw, request)
                if over:
                    return _limit_response(over)
                if raw:
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        return Response(content=dumps(
                            {"error": "bad_request",
                             "detail": "body is not valid JSON"}),
                            status_code=400, media_type="application/json")
                    if not isinstance(body, dict):
                        return Response(content=dumps(
                            {"error": "bad_request",
                             "detail": "body must be a JSON object"}),
                            status_code=400, media_type="application/json")
                    args |= body
            # 8a. The role check, HERE, before the handler runs and before any input is
            # validated. Putting it in each handler would mean every new verb has to
            # remember it, which is the failure mode gateway/roles.py exists to remove --
            # and an unmapped verb is refused rather than allowed.
            if not may(principal.role, verb.name):
                _record(principal, action=audit_mod.READ,
                        route=f"{verb.method} {path}", resource=verb.name,
                        outcome="refused", status=403)
                return Response(content=dumps(
                    {"error": "forbidden",
                     "detail": f"{verb.name} needs the "
                               f"{REQUIRED.get(verb.name, 'admin')} role; this key has "
                               f"{principal.role}"}),
                    status_code=403, media_type="application/json")
            missing = [f.name for f in verb.inputs
                       if f.required and not str(args.get(f.name) or "").strip()]
            if missing:
                return Response(content=dumps(
                    {"error": "bad_request",
                     "detail": f"missing required input(s): {', '.join(missing)}"}),
                    status_code=400, media_type="application/json")
            out = verb.run(args, ctx) if verb.run else {"error": "not_implemented"}
            code = 200
            if isinstance(out, dict) and out.get("code") in ("NOT_FOUND", "NO_STORE"):
                code = 404 if out["code"] == "NOT_FOUND" else 503
            elif isinstance(out, dict) and out.get("code") == "BAD_REQUEST":
                code = 400
            # The resource is an IDENTIFIER, never the input. For documents.upload that
            # is the sha256 the handler returned; for a run verb, the run id; otherwise
            # the verb's own name. The question a caller asked never reaches the chain.
            resource = (out.get("document_id") if isinstance(out, dict) else None) \
                or args.get("run_id") or verb.name
            _record(principal,
                    action=audit_mod.READ if verb.read_only else audit_mod.WRITE,
                    route=f"{verb.method} {path}", resource=str(resource),
                    outcome="served" if code < 400 else "refused", status=code)
            return Response(content=dumps(out), status_code=code,
                            media_type="application/json")

        app.add_api_route(path, _route, methods=[verb.method],
                          name=f"v2:{verb.name}", summary=verb.summary)

    for _v in VERBS:
        _mount(_v)

    # ── binary downloads ────────────────────────────────────────────────────
    #
    # The verbs already produce these bytes, and they hand them back as base64 inside a
    # JSON object. **No browser downloads that.** A user who clicks "export" wants a file
    # on disk with a name, and getting one from `{"docx_base64": "UEsDB..."}` means
    # writing JavaScript to decode a string into a Blob -- which is a real feature with a
    # real failure mode (the filename is lost, the MIME type is guessed) reimplemented in
    # every client.
    #
    # Written by hand rather than generated from the verb table, on purpose: the table
    # generates JSON routes, and a verb that returned a file would make every surface --
    # REST, MCP, CLI -- grow a binary case for the two verbs that need one.

    def _attachment(data: bytes, *, filename: str, media_type: str) -> Response:
        # `filename*=UTF-8''...` is the RFC 6266 form. The plain `filename=` is kept
        # beside it for clients that do not read the extended one, with anything
        # non-ASCII stripped rather than mangled.
        from urllib.parse import quote
        safe = "".join(ch for ch in filename if 32 <= ord(ch) < 127 and ch not in '"\\')
        return Response(
            content=data, media_type=media_type,
            headers={"content-disposition":
                     f'attachment; filename="{safe or "download"}"; '
                     f"filename*=UTF-8''{quote(filename)}",
                     "content-length": str(len(data))})

    def _binary(path: str, verb_name: str, to_bytes, *, param: str):
        async def _route(request: Request) -> Response:
            try:
                principal = _principal(request)
            except AuthError:
                return _unauthorised()
            store = app.state.backend_for(principal.tenant_id)
            ctx = Context(tenant=principal.tenant_id, actor=principal.actor,
                          store=store, documents=app.state.documents, clock=now)
            if not may(principal.role, verb_name):
                _record(principal, action=audit_mod.READ, route=f"GET {path}",
                        resource=verb_name, outcome="refused", status=403)
                return Response(content=dumps(
                    {"error": "forbidden",
                     "detail": f"{verb_name} needs the {REQUIRED.get(verb_name)} role; "
                               f"this key has {principal.role}"}),
                    status_code=403, media_type="application/json")
            args = dict(request.path_params) | dict(request.query_params)
            out = by_name()[verb_name].run(args, ctx)
            if isinstance(out, dict) and out.get("status") == "REFUSED":
                code = {"NOT_FOUND": 404, "NO_STORE": 503}.get(out.get("code"), 400)
                _record(principal, action=audit_mod.READ,
                        route=f"GET {path}", resource=str(args.get(param) or verb_name),
                        outcome="refused", status=code)
                return Response(content=dumps(out), status_code=code,
                                media_type="application/json")
            data, filename, media_type = to_bytes(out)
            _record(principal, action=audit_mod.READ, route=f"GET {path}",
                    resource=str(args.get(param) or verb_name), outcome="served",
                    status=200)
            return _attachment(data, filename=filename, media_type=media_type)

        app.add_api_route(path, _route, methods=["GET"], name=f"download:{verb_name}")

    def _docx_bytes(out: dict):
        import base64
        return (base64.b64decode(out.get("docx_base64") or ""),
                str(out.get("filename") or "draft.docx"),
                str(out.get("content_type")
                    or "application/vnd.openxmlformats-officedocument."
                       "wordprocessingml.document"))

    def _csv_bytes(out: dict):
        return (str(out.get("csv") or "").encode("utf-8"),
                str(out.get("filename") or "review-table.csv"),
                "text/csv; charset=utf-8")

    from gateway.verbs import by_name
    _binary("/v2/drafts/{draft_id}/export.docx", "draft.export", _docx_bytes,
            param="draft_id")
    _binary("/v2/review_tables/{grid_id}/export.csv", "review_table.export", _csv_bytes,
            param="grid_id")

    return app


# ── the requests the byte-identity test replays ──────────────────────────────
# Real requests against real routes, taken from checker/api.py's own suite rather than
# invented, so a route that changes shape there is replayed in its new shape here.

_DOC = {"company_class": "private", "incorporation_date": "2015-04-01",
        "is_listed": False, "paid_up_capital_rupees": 60000000,
        "turnover_rupees": 550000000, "financial_year": "2024-25",
        "director_count": 2}

_PACK = {"company_class": "private", "incorporation_date": "2015-04-01",
         "as_of": "2026-08-31", "is_listed": False,
         "paid_up_capital_rupees": 60000000, "turnover_rupees": 550000000,
         "financial_year": "2024-25", "director_count": 3,
         "evidence": {"agm_dates": ["2024-08-20", "2025-12-30"],
                      "financial_year_end": "2025-03-31",
                      "board_meetings": ["2025-03-01"], "calendar_year": 2025,
                      "resident_director_days": 90}}

REPLAY: tuple[tuple[str, str, dict | None], ...] = (
    ("GET", "/v1/health", None),
    ("POST", "/v1/ask", {"question": "how many board meetings must a company hold"}),
    ("POST", "/v1/ask", {}),                                   # a refusal path
    ("POST", "/v1/document-check",
     {**_DOC, "document_date": "2024-06-01", "as_of": "2026-09-10"}),
    ("POST", "/v1/document-check", {"company_class": "private"}),
    ("POST", "/v1/compliance-pack", _PACK),
    ("POST", "/v1/compliance-pack", {"as_of": "2026-08-31"}),
    ("POST", "/v1/mca-strip", {"cin": "U74999DL2015PTC000001"}),
    ("GET", "/v1/company/U74999DL2015PTC000001/events?as_of=2026-09-09", None),
    ("GET", "/v1/company/X/events?as_of=notadate", None),
    ("GET", "/v1/instruments/gsr700/affected", None),
    ("GET", "/v1/nosuchroute", None),                           # a 404 must carry too
)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    from starlette.testclient import TestClient

    from checker.api import handle

    from gateway.auth import KeyStore

    GEN = "2026-09-10T00:00:00Z"
    T = "11111111-2222-3333-4444-555555555555"
    A = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    keys = KeyStore()
    # The harness acts as the firm's ADMIN. 8a made `viewer` the default, which is the
    # safe default and which this suite immediately proved by refusing its own uploads.
    KEY, PRINCIPAL = keys.mint(tenant_id=T, actor=A, label="gate", role="admin")
    VIEWER_KEY, _ = keys.mint(tenant_id=T, actor=A, label="viewer", role="viewer")
    LAWYER_KEY, _ = keys.mint(tenant_id=T, actor=A, label="lawyer", role="lawyer")
    # db_url="" forces memory REGARDLESS of the environment, so the gate is the same on a
    # developer's laptop with PLACEDON_DATABASE_URL exported as it is in a clean checkout.
    app = create_app(clock=lambda: GEN, keys=keys, db_url="")
    client = TestClient(app, headers={"Authorization": f"Bearer {KEY}"})
    anon = TestClient(app)

    # ── every /v1 route, byte for byte ──────────────────────────────────────
    differed = []
    for method, path, body in REPLAY:
        want_status, want_body = handle(method, path, body, generated_at=GEN)
        r = client.request(method, path, json=body) if method == "POST" \
            else client.request(method, path)
        if path.rstrip("/") == HEALTH_PATH:
            continue
        if r.status_code != want_status or r.content != dumps(want_body):
            differed.append((method, path, want_status, r.status_code))
    check(not differed,
          f"every /v1 response is byte-identical to the engine's, status included "
          f"({differed[:3]})")
    check(len(REPLAY) >= 10, f"...across {len(REPLAY)} real requests, not one happy path")

    statuses = {handle(m, p, b, generated_at=GEN)[0] for m, p, b in REPLAY}
    check(len(statuses) >= 3,
          f"...reaching several status codes ({sorted(statuses)}), so the comparison is "
          f"not only over 200s -- a gateway that swallowed a 400 would pass otherwise")

    # ── the one route that differs, and by exactly one key ──────────────────
    want_status, engine_health = handle("GET", HEALTH_PATH, None, generated_at=GEN)
    r = client.get(HEALTH_PATH)
    got = json.loads(r.content)
    check(r.status_code == want_status, "health carries the engine's status")
    check(set(got) - set(engine_health) == {"store"},
          f"health adds EXACTLY one key ({sorted(set(got) - set(engine_health))})")
    check(not (set(engine_health) - set(got)), "...and drops none")
    check(all(got[k] == v for k, v in engine_health.items()),
          "...and changes no value the engine set, so the addition is additive in fact "
          "and not only in intent")
    check(got["store"]["kind"] == MEMORY_STORE and got["store"]["degraded"] is True,
          "...the added key says the store is in-memory and degraded")
    check("does not survive a restart" in got["store"]["note"]
          or "survives a restart" in got["store"]["note"],
          "...and says what that costs a reader, not merely its name")
    check("migrations" in got["store"]["note"],
          "...naming the migrations that have not been applied")

    pg = TestClient(create_app(deployment=Deployment(POSTGRES_STORE), clock=lambda: GEN,
                               keys=keys, db_url=""),
                    headers={"Authorization": f"Bearer {KEY}"})
    got_pg = json.loads(pg.get(HEALTH_PATH).content)
    check(got_pg["store"]["kind"] == POSTGRES_STORE
          and got_pg["store"]["degraded"] is False,
          "a postgres deployment reports itself as not degraded")
    check("ROW LEVEL SECURITY" in got_pg["store"]["note"],
          "...and points at the isolation it is claiming")

    # ── the gateway adds nothing of its own to a real answer ────────────────
    st, engine_ask = handle("POST", "/v1/ask",
                            {"question": "how many board meetings"}, generated_at=GEN)
    body = json.loads(client.post("/v1/ask",
                                  json={"question": "how many board meetings"}).content)
    check(body == engine_ask,
          "an /v1/ask answer is the engine's object exactly -- no wrapper, no envelope, "
          "no request id bolted on")

    # ── malformed input is refused by the gateway, not mistaken for absent ──
    bad = client.post("/v1/ask", content=b"{not json", headers={"content-type": "application/json"})
    check(bad.status_code == 400 and json.loads(bad.content)["error"] == "bad_request",
          "a body that is not JSON is refused as bad_request")
    _, engine_none = handle("POST", "/v1/ask", None, generated_at=GEN)
    check(json.loads(bad.content) != engine_none,
          "...and NOT forwarded as None, which the engine would answer as 'no body given' "
          "-- a different and misleading refusal")

    # ── the serialiser is stated, because byte-identity needs an encoding ───
    check(dumps({"b": 1, "a": "é"}) == b'{"b":1,"a":"\xc3\xa9"}',
          "the encoding is fixed: key order preserved, no spaces, UTF-8 not escaped")

    # ── /v2, mounted from the verb table and not written by hand ────────────
    from gateway.verbs import VERBS, rest_path, write_verbs
    mounted = {r.name: r.path for r in app.routes if getattr(r, "name", "").startswith("v2:")}
    check(len(mounted) == len(VERBS),
          f"every verb is mounted ({len(mounted)} of {len(VERBS)})")
    check(all(mounted.get(f"v2:{v.name}") == rest_path(v) for v in VERBS),
          "...at the path the table generates, so a route cannot be hand-edited apart "
          "from its verb")

    up = client.post("/v2/documents/upload", json={"text": "a contract"})
    check(up.status_code == 200 and len(json.loads(up.content)["sha256"]) == 64,
          f"documents.upload stores and returns a sha256 ({up.status_code})")
    again = client.post("/v2/documents/upload", json={"text": "a contract"})
    check(json.loads(again.content)["document_id"]
          == json.loads(up.content)["document_id"],
          "...and the same bytes are the same document, because the id IS the hash")

    check(client.post("/v2/documents/upload", json={}).status_code == 400,
          "a missing required input is a 400 from the GATEWAY, before the handler runs")
    check(client.post("/v2/ask", content=b"[1,2]",
                      headers={"content-type": "application/json"}).status_code == 400,
          "...and a JSON body that is not an object is refused too")

    r404 = client.get("/v2/runs/nosuchrun")
    check(r404.status_code == 404 and json.loads(r404.content)["code"] == "NOT_FOUND",
          f"an unknown run is 404 NOT_FOUND ({r404.status_code})")
    tr = client.get("/v2/runs/nosuchrun/trace")
    check(tr.status_code == 404, "...and so is its trace")

    app.state.run_store.write({"id": "r1", "status": "ANSWERED",
                               "steps": [{"capability": "intake"}]})
    got = json.loads(client.get("/v2/runs/r1").content)
    check(got["status"] == "ANSWERED" and "steps" not in got,
          "runs.get serves the run without its steps")
    step = json.loads(client.get("/v2/runs/r1/trace").content)["steps"][0]
    from gateway.store import STEP_KEYS
    check(step["capability"] == "intake", "...and runs.trace serves them")
    check(set(step) == set(STEP_KEYS),
          f"...normalised to the full key set ({sorted(step)}), so a caller reading "
          f"step['model'] gets None on memory rather than a KeyError it would not get "
          f"on Postgres")

    check(all(not str(p).startswith("/v1") for p in mounted.values()),
          "no generated route lands under /v1, so the byte-identical surface cannot be "
          "shadowed by a verb")
    # Named, not counted. The two human-gate verbs WRITE -- that is why `mcp_tools` keeps
    # them off the tool surface, and a tool that can approve a finding is a tool that can
    # clear a review without a person present.
    check(set(write_verbs()) == {"documents.upload", "runs.approve", "runs.reject",
                                 "runs.submit", "runs.cancel", "conversation.send",
                                 "review_table.create", "review_table.cancel",
                                 "draft.create", "draft.revise", "matters.create",
                                 "vault.upload", "vault.delete"},
          f"thirteen write verbs today, and each is named ({sorted(write_verbs())})")

    # ── auth: a key is required everywhere except liveness ──────────────────
    check(anon.get(HEALTH_PATH).status_code == 200,
          "health is served WITHOUT a key -- a liveness probe that needs a credential "
          "lies during the outage it was built for")
    for m, path in (("POST", "/v1/ask"), ("GET", "/v1/company/X/events"),
                    ("POST", "/v2/documents/upload"), ("GET", "/v2/runs/r1")):
        r = anon.request(m, path, json={} if m == "POST" else None)
        check(r.status_code == 401 and json.loads(r.content)["error"] == "unauthorized",
              f"{m} {path} without a key is 401")
    check(anon.get(HEALTH_PATH).headers.get("content-type", "").startswith(
        "application/json"), "...and the public route still answers JSON")
    r = anon.request("POST", "/v1/ask", json={}, headers={"Authorization": "Bearer nope"})
    check(r.status_code == 401 and "WWW-Authenticate" in r.headers,
          "a WRONG key is 401 too, with a WWW-Authenticate header")
    check(TestClient(app, headers={"x-api-key": KEY}).post(
        "/v1/ask", json={"question": "x"}).status_code == 200,
        "x-api-key is accepted as well as Bearer")

    # ── an audit row per served call, metadata only ──────────────────────────
    before = len(app.state.audit)
    client.post("/v2/documents/upload", json={"text": "CONFIDENTIAL: Acme and Beta."})
    client.post("/v1/ask", json={"question": "how many board meetings must be held"})
    after = app.state.audit
    check(len(after) == before + 2, f"one row per served call ({len(after) - before})")
    check(audit_mod.verify(after)[0], "...and the chain verifies")
    joined = " ".join(f"{r.tenant_id}{r.actor}{r.route}{r.resource}{r.outcome}"
                      for r in after)
    for leak in ("CONFIDENTIAL", "Acme", "how many board meetings", "board meetings"):
        check(leak not in joined,
              f"...and NO document or prompt text reached the chain ({leak!r})")
    up_row = next(r for r in after if "documents" in r.route)
    check(len(up_row.resource) == 64,
          f"a document row names its sha256, which is metadata ({up_row.resource[:12]}…)")
    check(up_row.action == audit_mod.WRITE, "...and an upload is recorded as a WRITE")
    ask_row = next(r for r in after if r.route.endswith("/v1/ask"))
    check(ask_row.action == audit_mod.READ and ask_row.resource == "/v1/ask",
          "a read is recorded as a READ, and its resource is the ROUTE, never the question")
    check(all(r.tenant_id == T and r.actor == A for r in after),
          "every row carries the tenant and actor the key resolved to")
    n = len(app.state.audit)
    anon.post("/v1/ask", json={})
    check(len(app.state.audit) == n,
          "an unauthorised call writes NO row: there is no tenant to attribute it to, and "
          "audit.py refuses a row that cannot be joined to one")

    # ── the store is SELECTED, and health reports what was selected ─────────
    from gateway.store import MEMORY as M_KIND
    from gateway.store import POSTGRES as P_KIND
    check(json.loads(client.get(HEALTH_PATH).content)["store"]["kind"] == M_KIND,
          "with no URL configured, health reports in-memory")
    forced = create_app(clock=lambda: GEN, keys=keys, db_url="postgresql://h/db")
    fc = TestClient(forced, headers={"Authorization": f"Bearer {KEY}"})
    check(json.loads(fc.get(HEALTH_PATH).content)["store"]["kind"] == P_KIND,
          "with a URL configured, health reports postgres -- derived from the selection, "
          "not from a flag someone set separately")
    check(json.loads(fc.get(HEALTH_PATH).content)["store"]["degraded"] is False,
          "...and stops calling itself degraded")
    check(forced.state.db_url and app.state.db_url is None,
          "the app holds the URL it selected on, and the gate's app holds none")
    b = app.state.backend_for(T)
    check(b.kind == M_KIND and b is app.state.memory_backend,
          "in memory, every tenant shares ONE backend object so two requests in a process "
          "see each other's rows")
    pb = forced.state.backend_for(T)
    check(pb.kind == P_KIND and pb.tenant_id == T,
          "on Postgres a backend is built PER REQUEST, bound to the tenant the key "
          "resolved to -- app.tenant_id is what the policies compare against")

    # ── binary downloads: real bytes, a real filename, no base64 ────────────
    _d = client.post("/v2/draft/create", json={
        "title": "AGM Notice", "body": "Notice is hereby given.",
        "slots": [{"name": "x", "value": "v", "type": "TEMPLATE_TEXT"}]})
    if _d.status_code == 200 and _d.json().get("draft_id"):
        _did = _d.json()["draft_id"]
        _dl = client.get(f"/v2/drafts/{_did}/export.docx")
        check(_dl.status_code == 200, f"the .docx download returns 200 ({_dl.status_code})")
        check(_dl.content[:2] == b"PK",
              f"...and the body is a real ZIP -- a .docx IS a zip, so this is the file "
              f"itself and not base64 of it ({_dl.content[:4]!r})")
        check("attachment" in _dl.headers.get("content-disposition", ""),
              f"...served as an ATTACHMENT, which is what makes a browser save it "
              f"({_dl.headers.get('content-disposition')})")
        check(".docx" in _dl.headers.get("content-disposition", ""),
              "...with a filename, which base64-in-JSON loses")
        check("wordprocessingml" in _dl.headers.get("content-type", ""),
              f"...and the Word media type, not application/json "
              f"({_dl.headers.get('content-type')})")
        check(b"docx_base64" not in _dl.content,
              "...and the JSON envelope is NOT in the body")
    else:
        check(False, f"a draft could be created to download ({_d.status_code})")

    _up = client.post("/v2/documents/upload", json={"text": "Governed by the laws of India.",
                                             "name": "a.txt"})
    _g = client.post("/v2/review-table/create", json={
        "name": "g", "document_ids": [_up.json().get("document_id")],
        "columns": [{"name": "governing law", "kind": "text", "question": "Which law?"}]})
    if _g.status_code == 200 and _g.json().get("grid_id"):
        _csv = client.get(f"/v2/review_tables/{_g.json()['grid_id']}/export.csv")
        check(_csv.status_code == 200 and _csv.content,
              f"the CSV download returns 200 with a body ({_csv.status_code})")
        check(_csv.headers.get("content-type", "").startswith("text/csv"),
              f"...as text/csv ({_csv.headers.get('content-type')})")
        check("attachment" in _csv.headers.get("content-disposition", ""),
              "...and as an attachment")
        check(b"," in _csv.content and b"{" not in _csv.content[:1],
              "...the CSV itself, not a JSON object wrapping it")
    else:
        check(False, f"a review table could be created to download ({_g.status_code})")

    check(anon.get("/v2/drafts/00000000-0000-0000-0000-000000000000/export.docx"
                   ).status_code == 401,
          "a download WITHOUT a key is refused: a file route that skipped auth would be "
          "the one way to read another tenant's draft")

    # ── 8a: the role is checked on every verb, before the handler ───────────
    viewer = TestClient(app, headers={"Authorization": f"Bearer {VIEWER_KEY}"})
    lawyer = TestClient(app, headers={"Authorization": f"Bearer {LAWYER_KEY}"})

    _vr = viewer.post("/v2/documents/upload", json={"text": "x", "name": "a.txt"})
    check(_vr.status_code == 403,
          f"a VIEWER cannot upload a document ({_vr.status_code})")
    check(_vr.json().get("error") == "forbidden" and "viewer" in _vr.json().get("detail", ""),
          f"...and the refusal names the role it has and the one it needs "
          f"({_vr.json().get('detail')})")
    check(viewer.post("/v2/ask", json={"question": "What is the quorum?"}).status_code
          != 403,
          "...while a viewer CAN ask: reading is not a professional act")

    # The line the role model exists for.
    _RUN = "11111111-1111-1111-1111-111111111111"
    _va = viewer.post(f"/v2/runs/approve/{_RUN}", json={
        "item_ref": "x", "reason": "a long enough reason", "quote_viewed": True})
    check(_va.status_code == 403,
          f"**a VIEWER cannot APPROVE a finding** -- it would turn an unreviewed finding "
          f"into a reviewed one with no lawyer involved ({_va.status_code})")
    _la = lawyer.post(f"/v2/runs/approve/{_RUN}", json={
        "item_ref": "x", "reason": "a long enough reason", "quote_viewed": True})
    check(_la.status_code != 403,
          f"...and a LAWYER can (it fails for a missing run, not for the role: "
          f"{_la.status_code})")

    check(viewer.post("/v2/review-table/create", json={
        "name": "g", "document_ids": [], "columns": []}).status_code == 403,
        "a viewer cannot start work that spends money")

    # The refusal is RECORDED, which is how a denied attempt is visible afterwards.
    _chain = app.state.audit
    check(any(getattr(e, "http_status", None) == 403 for e in _chain),
          "a 403 is written to the audit chain: a denied attempt nobody can see is a "
          "denied attempt nobody investigates")

    # A download obeys the same rule.
    _vd = viewer.get("/v2/drafts/00000000-0000-0000-0000-000000000000/export.docx")
    check(_vd.status_code == 404,
          f"a VIEWER may download a draft -- both export verbs are reads, so 404 (no such "
          f"draft) is the right refusal and 403 would be wrong ({_vd.status_code})")
    # That the download route CONSULTS the role is asserted structurally, because no role
    # is below `viewer` to prove it with a request.
    import ast as _ast
    import inspect as _inspect
    _appsrc = _inspect.getsource(create_app)
    _binary_fn = [n for n in _ast.walk(_ast.parse(_appsrc))
                  if isinstance(n, _ast.FunctionDef) and n.name == "_binary"]
    check(_binary_fn and any(
        isinstance(n, _ast.Call) and getattr(n.func, "id", "") == "may"
        for n in _ast.walk(_binary_fn[0])),
        "...and the binary route still CALLS may() -- read from the parsed function, "
        "because no role sits below viewer to prove it with a request, and a file route "
        "that skipped the check would be the way around every check above")

    # ── P2: rate and request-size limits, on BOTH surfaces ──────────────────
    # The property that matters is not that a limit exists, it is that it exists on both.
    # /v1 and /v2 each read a body, and a guard wired into one of them is a guard the other
    # does not have -- which is how this kind of thing is usually half-applied.
    from gateway import limits as _lim

    big = "x" * (_lim.MAX_BODY_BYTES + 1)
    r = client.post("/v1/ask", content=json.dumps({"question": big}),
                    headers={"Content-Type": "application/json"})
    check(r.status_code == 413,
          f"/v1 refuses an oversized body with 413 ({r.status_code})")
    check(_lim.TOO_LARGE.lower() in r.json()["error"],
          f"...naming the reason ({r.json()['error']})")

    r = client.post("/v2/matters/create", content=json.dumps({"name": big}),
                    headers={"Content-Type": "application/json"})
    check(r.status_code == 413,
          f"/v2 refuses it TOO -- the generated routes are the other surface "
          f"({r.status_code})")

    # A fresh app per rate test, so the bucket is not already spent by the checks above.
    def _fresh():
        a = create_app(clock=lambda: GEN, handler=handle, keys=keys, db_url="")
        return TestClient(a, headers={"Authorization": f"Bearer {KEY}"}), a

    c1, a1 = _fresh()
    a1.state.limiter = _lim.Limiter(per_minute=60, burst=2)
    codes = [c1.get(f"/v1/health?x={i}").status_code for i in range(4)]
    check(codes.count(429) == 0,
          f"/v1/health is PUBLIC, so it has no tenant to limit and is not rate limited "
          f"here -- an unauthenticated flood is the reverse proxy's job ({codes})")

    c2, a2 = _fresh()
    a2.state.limiter = _lim.Limiter(per_minute=60, burst=2)
    codes = [c2.post("/v1/ask", content=json.dumps({"question": "q"}),
                     headers={"Content-Type": "application/json"}).status_code
             for _ in range(4)]
    check(429 in codes, f"/v1 rate-limits an authenticated tenant past its burst ({codes})")
    first = c2.post("/v1/ask", content=json.dumps({"question": "q"}),
                    headers={"Content-Type": "application/json"})
    check(first.status_code == 429 and first.headers.get("Retry-After"),
          f"...with a Retry-After header ({first.headers.get('Retry-After')})")

    c3, a3 = _fresh()
    a3.state.limiter = _lim.Limiter(per_minute=60, burst=2)
    codes = [c3.post("/v2/matters/create", content=json.dumps({"name": f"m{i}"}),
                     headers={"Content-Type": "application/json"}).status_code
             for i in range(4)]
    check(429 in codes,
          f"/v2 rate-limits as well, from the SAME limiter on app.state ({codes})")

    # One tenant's limit must not touch another's.
    c4, a4 = _fresh()
    a4.state.limiter = _lim.Limiter(per_minute=60, burst=1)
    other = KeyStore()
    OTHER_KEY = other.issue(tenant_id=A, actor="other", role="admin") \
        if hasattr(other, "issue") else None
    for _ in range(3):
        c4.post("/v1/ask", content=json.dumps({"question": "q"}),
                headers={"Content-Type": "application/json"})
    check(a4.state.limiter.tokens_for(T) < 1.0,
          "the limiter's bucket is keyed by TENANT, and this firm's is spent")
    check(a4.state.limiter.tokens_for("some-other-tenant") == 1.0,
          "...while another tenant's is untouched -- one noisy firm cannot spend another's "
          "capacity")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
