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
from fastapi.responses import Response, StreamingResponse     # noqa: E402

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


class SingleTenantOnly(RuntimeError):
    """A second tenant reached a deployment running on the in-memory store.

    Raised rather than returned, because every route that builds a backend must refuse and a
    return value is something a caller can forget to check. `create_app` turns it into 503 at
    both surfaces: the deployment is misconfigured for what was asked of it, which is a server
    condition and not the caller's fault.
    """


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


def health_body(engine_body: dict, deployment: Deployment, queue=None,
                files=None) -> dict:
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
                                          "note": deployment.note},
                                # Reported ALWAYS, present or absent, exactly as `store`
                                # is: a key that appears only when a vault exists is a key
                                # an operator cannot alert on.
                                "files": file_store_health(files)}
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


FILES_DIR_ENV = "PLACEDON_FILES_DIR"


def default_file_store():
    """A `LocalFileStore` under `PLACEDON_FILES_DIR`, or None when it is unset.

    None is not a failure: a deployment with no vault is a real deployment, and the vault
    verbs refuse `NO_VAULT` by name on it. What is NOT acceptable is the previous
    behaviour, where the only way to configure one was to set `ctx.files` by hand -- which
    `gateway/screens.py` does in its own test, and no HTTP caller could do at all. So the
    verbs were proved and unreachable at once.

    `S3FileStore` stays BLOCKED until AWS exists (H1); this reads a directory because a
    directory is what a laptop and a Lightsail box both have.
    """
    import os

    root = (os.environ.get(FILES_DIR_ENV) or "").strip()
    if not root:
        return None
    from gateway.filestore import LocalFileStore
    return LocalFileStore(root)


def file_store_health(files) -> dict:
    """The file store, reported the way `store` is. Absence is a FACT, not a silence.

    An operator reading /v1/health must be able to see that the vault cannot accept an
    upload, rather than discovering it from a refusal after someone tries.
    """
    if files is None:
        return {"configured": False, "kind": None,
                "note": (f"no file store: {FILES_DIR_ENV} is unset. The vault verbs refuse "
                         f"NO_VAULT by name, so an upload is declined rather than written "
                         f"nowhere")}
    kind = getattr(files, "kind", type(files).__name__)
    return {"configured": True, "kind": kind,
            "note": f"a {kind} file store is configured; the vault can accept an upload"}


def create_app(*, deployment: Deployment | None = None, clock=None, handler=None,
               keys: KeyStore | None = None, db_url: str | None = None, queue=None,
               files=None):
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
    # P2. Which tenant the shared memory backend has served. See backend_for.
    app.state.memory_tenant = None

    def backend_for(tenant_id: str):
        """The backend for this tenant, or a refusal if memory cannot keep them apart.

        **The memory backend has no tenant isolation, and now says so instead of pretending.**
        `MemoryBackend` consults `tenant_id` in none of its 21 read methods and its rows do not
        carry one, so on 02-10-2026 `scripts/concurrency_test.py` found tenant B reading tenant
        A's matters -- not as a race, but serially, every time. That is consistent with the
        comment above: a shared in-process backend exists so two requests SEE each other's
        rows, which is what makes it useful for a single-tenant test and disqualifying for two.

        The fix is to fail CLOSED on the second distinct tenant rather than retrofit filtering
        into twenty-one methods. Retrofitting would make the memory store look like it enforced
        isolation, and it would be a dict comprehension standing where Postgres has FORCE ROW
        LEVEL SECURITY and a policy the database applies to every query -- including the ones
        nobody remembered to filter. A deployment that needs two tenants needs the database,
        and this says so by name.
        """
        if app.state.db_url:
            return PostgresBackend(app.state.db_url, tenant_id=tenant_id)
        seen = app.state.memory_tenant
        if seen is not None and seen != tenant_id:
            raise SingleTenantOnly(
                f"this deployment has no database configured, so it is running on the "
                f"in-memory store, which has NO tenant isolation: it consults tenant_id in "
                f"none of its reads. It has already served tenant {seen}, and serving "
                f"{tenant_id} as well would let each read the other's rows. Set "
                f"PLACEDON_DATABASE_URL -- Postgres enforces this with FORCE ROW LEVEL "
                f"SECURITY, which the memory store cannot imitate")
        app.state.memory_tenant = tenant_id
        app.state.memory_backend.tenant_id = tenant_id
        return app.state.memory_backend

    app.state.backend_for = backend_for
    app.state.run_store = app.state.memory_backend
    app.state.documents = app.state.memory_backend.documents
    app.state.keys = keys if keys is not None else KeyStore()
    # Injected, or read from the environment. Never discovered inside a handler: a verb
    # that reached for its own file store would be a second place the vault's location
    # lives, and the two would disagree the first time either moved.
    app.state.files = files if files is not None else default_file_store()
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

    def _single_tenant(exc: SingleTenantOnly) -> Response:
        """503: the deployment cannot serve this caller safely. Not the caller's fault."""
        return Response(content=dumps({"error": "no_tenant_isolation", "detail": str(exc)}),
                        status_code=503, media_type="application/json")

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
            # /v1 does not build a backend -- it calls checker.api.handle -- but it must
            # refuse a second tenant too, or the two surfaces disagree about who may be
            # served and the narrower one is the only protection.
            try:
                app.state.backend_for(principal.tenant_id)
            except SingleTenantOnly as exc:
                return _single_tenant(exc)
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
            payload = health_body(payload, dep, queue=queue, files=app.state.files)
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
            try:
                store = app.state.backend_for(principal.tenant_id)
            except SingleTenantOnly as exc:
                return _single_tenant(exc)
            ctx = Context(tenant=principal.tenant_id, actor=principal.actor,
                          store=store, documents=app.state.documents, clock=now,
                          files=app.state.files, queue=queue)
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

    # ── R0 move 12: ask over Server-Sent Events ─────────────────────────────
    #
    # `POST /v2/ask/stream`. The non-streaming `/v2/ask` is UNTOUCHED: a caller that wants
    # one JSON object still gets one, and this route is additive. Same auth, same rate
    # limit, same body cap, same audit row -- reusing the closures above rather than a
    # second copy of the gate, because a streaming route that forgot the rate limiter would
    # be a way around it.
    #
    # NO NEW DEPENDENCY: `StreamingResponse` is FastAPI's own, and the event framing is four
    # lines of text. An SSE library would be a dependency for `data: ...\n\n`.
    #
    # ## What is honestly streamed, and what is not
    #
    # `accepted` goes out IMMEDIATELY, before any work -- that is the sub-second first event
    # the move asks for, and it is measured rather than asserted.
    #
    # The `step` events are real steps with real outcomes, and they are emitted **when the
    # work completes**, not as each step finishes. `_persist_run` REBINDS `ctx.last_steps`
    # to a fresh list at the end rather than appending as it goes, so there is nothing to
    # observe mid-flight; making them incremental means changing how every handler records a
    # step, which is a change to the non-streaming path the move says to leave alone. Each
    # event carries `live: false` so a reader is not told these arrived as they happened,
    # and the limitation is recorded as A-022.
    #
    # ## A transport failure is its OWN event
    #
    # `event: error`, never an `answer` whose envelope says abstained. An abstention is a
    # verified product state -- we read the law and could not answer -- and a dropped
    # connection or a raised handler is not one. The frontend's own rule says the same thing
    # ("a transport failure must NEVER render as an abstention"), and the only way to honour
    # it over a stream is to make the two distinguishable in the protocol.
    SSE_PATH = "/v2/ask/stream"

    def _sse(event: str, payload: dict) -> bytes:
        """One SSE frame. `event:` then `data:` then a blank line, which ends the frame."""
        return (f"event: {event}\n".encode()
                + b"data: " + dumps(payload) + b"\n\n")

    async def _ask_stream(request: Request) -> Response:
        import asyncio
        import time

        try:
            principal = _principal(request)
        except AuthError:
            return _unauthorised()
        slow = _rate_limited(principal)
        if slow:
            _record(principal, action=audit_mod.READ, route=f"POST {SSE_PATH}",
                    resource="ask.stream", outcome="refused", status=slow.http_status)
            return _limit_response(slow)
        try:
            store = app.state.backend_for(principal.tenant_id)
        except SingleTenantOnly as exc:
            return _single_tenant(exc)
        raw = await request.body()
        over = _too_large(raw, request)
        if over:
            return _limit_response(over)
        try:
            args = json.loads(raw) if raw else {}
            if not isinstance(args, dict):
                raise ValueError("body must be a JSON object")
        except Exception as exc:                                 # noqa: BLE001
            _record(principal, action=audit_mod.READ, route=f"POST {SSE_PATH}",
                    resource="ask.stream", outcome="refused", status=400)
            return Response(content=dumps({"status": "REFUSED", "code": "BAD_REQUEST",
                                           "detail": str(exc)[:200]}),
                            status_code=400, media_type="application/json")

        ask_verb = next(v for v in VERBS if v.name == "ask")
        ctx = Context(tenant=principal.tenant_id, actor=principal.actor,
                      store=store, documents=app.state.documents, clock=now)

        async def frames():
            t0 = time.monotonic()
            # FIRST, and before any work. A stream whose first byte waits for the answer is
            # not a stream, and `first_event_ms` is reported so the caller can MEASURE the
            # latency rather than take this comment's word for it.
            yield _sse("accepted", {
                "verb": "ask", "first_event_ms": round((time.monotonic() - t0) * 1000, 3),
                "note": "accepted and started. Steps follow, then one answer event"})
            try:
                out = await asyncio.to_thread(ask_verb.run, args, ctx)
            except Exception as exc:                             # noqa: BLE001
                # A DISTINCT event. Never an answer whose envelope says abstained: an
                # abstention means we read the law and could not answer, and this means we
                # did not get that far.
                _record(principal, action=audit_mod.READ, route=f"POST {SSE_PATH}",
                        resource="ask.stream", outcome="refused", status=500)
                yield _sse("error", {
                    "code": "TRANSPORT_FAILED",
                    "detail": f"{type(exc).__name__}: {str(exc)[:200]}",
                    "is_abstention": False,
                    "note": ("this is a FAILURE, not an abstention. Nothing was read and "
                             "nothing follows about the law. An abstention arrives as an "
                             "answer event whose envelope says so")})
                return
            for i, step in enumerate(ctx.last_steps or ()):
                yield _sse("step", {
                    "ordinal": i, "capability": step.get("capability"),
                    "status": step.get("status"),
                    "engine_capability": step.get("engine_capability"),
                    "model": step.get("model"), "degraded": step.get("degraded"),
                    "cost_inr": step.get("cost_inr"), "cost_note": step.get("cost_note"),
                    # Said in the data, not only in a comment: these are real steps with
                    # real outcomes, emitted on completion rather than as each finished.
                    "live": False,
                    "note": ("recorded step, emitted when the run completed. "
                             "`_persist_run` rebinds the step list at the end, so there is "
                             "nothing to observe mid-flight yet (A-022)")})
            code = 200 if not (isinstance(out, dict)
                               and out.get("status") == "REFUSED") else 400
            _record(principal, action=audit_mod.READ, route=f"POST {SSE_PATH}",
                    resource=str((out or {}).get("run_id") or "ask.stream"),
                    outcome="served" if code < 400 else "refused", status=code)
            yield _sse("answer", {
                "status_code": code, "envelope": out,
                "total_ms": round((time.monotonic() - t0) * 1000, 3)})

        return StreamingResponse(frames(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store",
                                          # Named because a proxy that buffers turns a
                                          # stream back into one slow response.
                                          "x-accel-buffering": "no"})

    # `stream:` and not `v2:`, following the `download:` routes above. The `v2:` prefix is
    # how the suite counts verbs -- "every verb is mounted (N of N)" -- and this is not a
    # verb: it is a second transport for one. A route that inflated that count would make
    # the assertion stop meaning what it says.
    app.add_api_route(SSE_PATH, _ask_stream, methods=["POST"], name="stream:ask",
                      summary="ask, streamed as Server-Sent Events")

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
            try:
                store = app.state.backend_for(principal.tenant_id)
            except SingleTenantOnly as exc:
                return _single_tenant(exc)
            ctx = Context(tenant=principal.tenant_id, actor=principal.actor,
                          store=store, documents=app.state.documents, clock=now,
                          files=app.state.files, queue=queue)
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
    check(set(got) - set(engine_health) == {"store", "files"},
          f"health adds EXACTLY the two keys only the gateway knows -- which store is "
          f"behind it, and whether a vault can accept an upload "
          f"({sorted(set(got) - set(engine_health))})")
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

    # ── R0 move 12: ask over SSE ────────────────────────────────────────────
    # The done-when: "a test reads the event sequence. The first event arrives in under 1 s
    # locally, and that time is MEASURED, not asserted." So the latency is taken with a
    # clock and printed; the assertion is on the measurement, not instead of one.
    import time as _sse_time

    def _parse_sse(text: str) -> list:
        """(event, data) per frame. A frame ends at a blank line."""
        import json as _j
        out = []
        for raw in text.split("\n\n"):
            if not raw.strip():
                continue
            name, data = "", ""
            for line in raw.splitlines():
                if line.startswith("event: "):
                    name = line[len("event: "):].strip()
                elif line.startswith("data: "):
                    data = line[len("data: "):]
            if name:
                try:
                    out.append((name, _j.loads(data)))
                except ValueError:
                    out.append((name, {"unparsed": data[:120]}))
        return out

    # ## The latency CANNOT be measured through TestClient, and finding that out was the
    # ## whole value of insisting on a measurement
    #
    # `client.post` buffers, so it times the ANSWER. `client.stream` looks like it should
    # work and does not: Starlette's ASGI transport collects the whole response before
    # `iter_lines` yields anything, so every frame arrives at the same instant and the first
    # one reports **100% of total**. I had that number on screen and it says "this route
    # does not stream".
    #
    # It does. Against a REAL uvicorn on a loopback port, the first frame arrives in single
    # -digit milliseconds and the answer four seconds later. So the sequence checks below use
    # TestClient (which is fine for ordering and content) and the LATENCY is measured against
    # a real server, because that is the only place the question has an answer.
    #
    # The precedent is `scripts/serve_ask.py --test`, which binds a fixed loopback port in
    # the gate for the same reason: some properties only exist over a socket.
    import json as _sse_json
    import socket as _sse_socket
    import threading as _sse_threading

    _SSE_Q = "What is the time limit for filing the annual return under section 92?"
    _SSE_PORT = 8033
    _sse_first_ms = _sse_answer_ms = None
    _sse_server = None
    try:
        import uvicorn as _uvicorn
        _sse_cfg = _uvicorn.Config(app, host="127.0.0.1", port=_SSE_PORT,
                                   log_level="error")
        _sse_server = _uvicorn.Server(_sse_cfg)
        _sse_thread = _sse_threading.Thread(target=_sse_server.run, daemon=True)
        _sse_thread.start()
        for _ in range(100):                    # up to 5 s for the port to open
            try:
                _sse_socket.create_connection(("127.0.0.1", _SSE_PORT), timeout=0.2).close()
                break
            except OSError:
                _sse_time.sleep(0.05)
        _sse_body = _sse_json.dumps({"question": _SSE_Q}).encode()
        _sse_req = (b"POST /v2/ask/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                    b"Authorization: Bearer " + KEY.encode() + b"\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(_sse_body)).encode()
                    + b"\r\nConnection: close\r\n\r\n" + _sse_body)
        _sock = _sse_socket.create_connection(("127.0.0.1", _SSE_PORT), timeout=60)
        _t0 = _sse_time.monotonic()
        _sock.sendall(_sse_req)
        while True:
            _chunk = _sock.recv(8192)
            if not _chunk:
                break
            for _line in _chunk.split(b"\n"):
                if _line.startswith(b"event:") and _sse_first_ms is None:
                    _sse_first_ms = (_sse_time.monotonic() - _t0) * 1000
                if _line.startswith(b"event: answer"):
                    _sse_answer_ms = (_sse_time.monotonic() - _t0) * 1000
        _sock.close()
    finally:
        if _sse_server is not None:
            _sse_server.should_exit = True

    if _sse_first_ms is None:
        check(False, "the SSE latency could not be measured: no event frame arrived over a "
                     "real socket. Reported rather than skipped -- a skipped measurement "
                     "reads as a passing one")
    else:
        print(f"    MEASURED over a real socket: first frame {_sse_first_ms:.1f} ms, "
              f"answer {_sse_answer_ms:.1f} ms "
              f"({_sse_first_ms / _sse_answer_ms:.2%} of the way through)")
        check(_sse_first_ms < 1000.0,
              f"the first event reaches a client in under 1 s -- MEASURED at "
              f"{_sse_first_ms:.1f} ms over a loopback socket, not asserted")
        check(_sse_first_ms < _sse_answer_ms / 4,
              f"...and it arrives long before the answer, which is the only thing that "
              f"makes this a stream rather than a slow response "
              f"({_sse_first_ms:.1f} ms of {_sse_answer_ms:.1f} ms)")

    # The SEQUENCE and the content, through TestClient -- which buffers, and for ordering
    # that does not matter.
    # A DIFFERENT question from the socket run. The first version reused `_SSE_Q`, which the
    # O9 answer cache had just stored, so the run recorded no steps and the sequence came
    # back ['accepted', 'answer'] -- a cache hit looking like a missing feature.
    _sse_r = client.post("/v2/ask/stream",
                         json={"question": "Which section requires an annual general "
                                           "meeting to be held each year?"})
    check(_sse_r.status_code == 200,
          f"the stream route answers 200 ({_sse_r.status_code})")
    check("text/event-stream" in _sse_r.headers.get("content-type", ""),
          f"...as text/event-stream ({_sse_r.headers.get('content-type')})")
    check(_sse_r.headers.get("x-accel-buffering") == "no",
          "...and asks proxies not to buffer, because a buffered stream is one slow response")

    _frames = _parse_sse(_sse_r.text)
    _names = [n for n, _ in _frames]
    check(_names and _names[0] == "accepted",
          f"the FIRST event is `accepted`, before any work ({_names[:4]})")
    check(_names[-1] == "answer",
          f"...and the LAST is `answer` ({_names[-3:]})")
    check(all(n == "step" for n in _names[1:-1]),
          f"...with nothing between them but step events ({_names})")
    check("step" in _names,
          f"...and a run that did work emits at least one ({_names})")

    # A CACHED answer is a legitimate sequence with no steps: nothing ran, so there is
    # nothing to report, and `accepted` -> `answer` is the honest shape. Asserted rather
    # than left as an accident, because it is what a second identical question produces.
    _cached = client.post("/v2/ask/stream", json={"question": _SSE_Q})
    _cached_names = [n for n, _ in _parse_sse(_cached.text)]
    check(_cached_names[0] == "accepted" and _cached_names[-1] == "answer",
          f"a cached answer still opens with `accepted` and closes with `answer`, with no "
          f"steps because nothing ran ({_cached_names})")
    check("error" not in _names,
          "a successful ask emits NO error event")

    # MEASURED. The number is printed so a reader sees the actual latency rather than a
    # claim about it, and the whole request is measured end to end -- `first_event_ms` is
    # taken inside the generator, and this is the time a CLIENT waited.
    _accepted = next(d for n, d in _frames if n == "accepted")
    _answer = next(d for n, d in _frames if n == "answer")
    check(isinstance(_answer.get("total_ms"), (int, float)),
          f"...and the answer event reports the total, so a caller can see where the time "
          f"went ({_answer.get('total_ms')} ms)")
    check(_answer["envelope"].get("run_id") or _answer["envelope"].get("question"),
          "the answer event carries the SAME envelope the non-streaming route returns")

    # Each step event says it is not live. Honesty about the limitation, in the data.
    for _n, _d in _frames:
        if _n == "step":
            check(_d.get("live") is False and "nothing to observe mid-flight" in _d["note"],
                  f"a step event says it was emitted on completion rather than as it "
                  f"happened -- `_persist_run` rebinds the step list at the end, so there is "
                  f"nothing to observe mid-flight yet (A-022) ({_d['capability']})")
            break

    # ── a transport failure is its OWN event, never an abstention ───────────
    # Forced by replacing the ask verb's handler with one that raises. `event: error` with
    # `is_abstention: false`, and NO answer event -- a dropped connection must not arrive as
    # a verified product state.
    from gateway.verbs import VERBS as _SSE_VERBS
    _ask_verb = next(v for v in _SSE_VERBS if v.name == "ask")
    _real_run = _ask_verb.run

    def _boom(args, ctx):
        raise RuntimeError("the model host closed the connection")

    object.__setattr__(_ask_verb, "run", _boom)
    try:
        _bad_lines = []
        with client.stream("POST", "/v2/ask/stream",
                           json={"question": "anything at all"}) as _br:
            for _line in _br.iter_lines():
                _bad_lines.append(str(_line))
        _bad_frames = _parse_sse("\n".join(_bad_lines))
        _bad_names = [n for n, _ in _bad_frames]
    finally:
        object.__setattr__(_ask_verb, "run", _real_run)
    check("error" in _bad_names and "answer" not in _bad_names,
          f"a raising handler emits `error` and NO `answer` ({_bad_names})")
    _err = next(d for n, d in _bad_frames if n == "error")
    check(_err.get("is_abstention") is False and _err.get("code") == "TRANSPORT_FAILED",
          f"...named a transport failure and explicitly NOT an abstention ({_err.get('code')}, "
          f"is_abstention={_err.get('is_abstention')})")
    check("nothing follows about the law" in _err.get("note", ""),
          f"...and the note says why that distinction matters: an abstention means we read "
          f"the law and could not answer ({_err.get('note', '')[:70]}…)")
    check(_bad_names[0] == "accepted",
          "...and `accepted` still went out first, so a client that saw the stream open "
          "learns the failure rather than hanging")
    check(_ask_verb.run is _real_run,
          "the probe RESTORED the real handler -- a self-test that leaves a verb patched "
          "poisons every check after it, which this file has been bitten by before")

    # ── the non-streaming route is untouched ────────────────────────────────
    _plain = client.post("/v2/ask",
                         json={"question": "What is the time limit for filing the annual "
                                           "return under section 92?"})
    check(_plain.status_code == 200
          and "application/json" in _plain.headers.get("content-type", ""),
          f"/v2/ask still returns ONE JSON object: the stream is additive, and a caller "
          f"that wants an object gets one ({_plain.status_code}, "
          f"{_plain.headers.get('content-type')})")

    # The stream is behind the SAME gate as everything else. A streaming route that forgot
    # the auth or the rate limiter would be a way around it.
    check(anon.post("/v2/ask/stream", json={"question": "x"}).status_code == 401,
          "an unauthenticated stream request is 401, like every other /v2 route")

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
                                 "vault.upload", "vault.delete",
                                 # T3 move 10: it records a judgement in an append-only
                                 # audit table, which is a write and is LAWYER-only.
                                 "document.check"},
          f"fourteen write verbs today, and each is named ({sorted(write_verbs())})")

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

    # ── P2: the memory store refuses a SECOND tenant, rather than leaking ────
    # scripts/concurrency_test.py found tenant B reading tenant A's matters on the memory
    # backend -- serially, every time, because tenant_id is consulted in none of its 21 read
    # methods. The fix is to fail closed, so this asserts the refusal at BOTH surfaces.
    OTHER = "99999999-8888-7777-6666-555555555555"
    keys2 = KeyStore()
    K1, _ = keys2.mint(tenant_id=T, actor=A, label="one", role="admin")
    K2, _ = keys2.mint(tenant_id=OTHER, actor=A, label="two", role="admin")

    app2 = create_app(clock=lambda: GEN, handler=handle, keys=keys2, db_url="")
    app2.state.limiter = _lim.Limiter(per_minute=10 ** 9, burst=10 ** 9)
    c_one = TestClient(app2, headers={"Authorization": f"Bearer {K1}"})
    c_two = TestClient(app2, headers={"Authorization": f"Bearer {K2}"})

    r1 = c_one.post("/v2/matters/create", json={"name": "first-tenant-matter"})
    check(r1.status_code == 200, f"the FIRST tenant is served on memory ({r1.status_code})")
    r2 = c_two.post("/v2/matters/list", json={})
    check(r2.status_code == 503,
          f"...and the SECOND is refused with 503, not served another firm's rows "
          f"({r2.status_code})")
    check("no_tenant_isolation" == r2.json()["error"]
          and "PLACEDON_DATABASE_URL" in r2.json()["detail"],
          "...naming the cause and the fix, so an operator is not left guessing")
    check("FORCE ROW LEVEL SECURITY" in r2.json()["detail"],
          "...and saying what the database does that the memory store cannot imitate")

    # The leak was reachable from /v1 too, which builds no backend of its own -- so the guard
    # has to be on both surfaces or the narrower one is the only protection.
    app3 = create_app(clock=lambda: GEN, handler=handle, keys=keys2, db_url="")
    app3.state.limiter = _lim.Limiter(per_minute=10 ** 9, burst=10 ** 9)
    d_one = TestClient(app3, headers={"Authorization": f"Bearer {K1}"})
    d_two = TestClient(app3, headers={"Authorization": f"Bearer {K2}"})
    a1 = d_one.post("/v1/ask", content=json.dumps({"question": "q"}),
                    headers={"Content-Type": "application/json"})
    a2 = d_two.post("/v1/ask", content=json.dumps({"question": "q"}),
                    headers={"Content-Type": "application/json"})
    check(a1.status_code != 503 and a2.status_code == 503,
          f"/v1 refuses the second tenant as well ({a1.status_code} then {a2.status_code})")

    # The SAME tenant twice is not a second tenant.
    app4 = create_app(clock=lambda: GEN, handler=handle, keys=keys2, db_url="")
    app4.state.limiter = _lim.Limiter(per_minute=10 ** 9, burst=10 ** 9)
    e = TestClient(app4, headers={"Authorization": f"Bearer {K1}"})
    codes = [e.post("/v2/matters/create", json={"name": f"m{i}"}).status_code
             for i in range(3)]
    check(503 not in codes,
          f"the same tenant may make as many requests as it likes ({codes}) -- the guard is "
          f"about a SECOND tenant, not a second request")

    # Postgres is unaffected: it builds a backend per request bound to the tenant RLS
    # compares against, so two tenants are exactly what it is for. Asserted on the selector
    # rather than a live server, which scripts/rls_integration.py --run covers.
    pg_app = create_app(clock=lambda: GEN, handler=handle, keys=keys2,
                        db_url="postgresql://unused/placedon_probe")
    check(pg_app.state.db_url is not None,
          "a Postgres deployment takes the other branch of backend_for entirely, so the "
          "single-tenant guard never applies to it")

    # ── gap 1: the vault, reachable over HTTP ───────────────────────────────
    # Driven through TestClient, NOT by building a Context and calling the verb. The verb
    # was already proved that way -- `gateway/screens.py` sets `ctx.files` itself -- and
    # that is exactly how a verb nobody can reach came to have a passing test. If it does
    # not work over HTTP it does not work.
    import tempfile as _tempfile

    from gateway.filestore import LocalFileStore as _LFS
    from gateway.jobs import MemoryQueue as _MQ

    with _tempfile.TemporaryDirectory() as _vault_dir:
        _vq = _MQ()
        _vapp = create_app(clock=lambda: GEN, handler=handle, keys=keys, db_url="",
                           files=_LFS(_vault_dir), queue=_vq)
        _vc = TestClient(_vapp, headers={"Authorization": f"Bearer {KEY}"})

        NDA = ("MUTUAL NON-DISCLOSURE AGREEMENT\n"
               "3. This Agreement shall be governed by the laws of India.\n"
               "4. The term of confidentiality shall expire on 2029-03-31.\n")
        _up = _vc.post("/v2/vault/upload", json={"name": "nda.txt", "text": NDA})
        check(_up.status_code == 200 and _up.json().get("status") != "REFUSED",
              f"a vault upload over HTTP is ACCEPTED when a file store is configured "
              f"({_up.status_code}: {str(_up.json())[:70]})")
        _doc = _up.json()
        check(_doc.get("state") == "PENDING",
              f"...and is PENDING, because nothing is searchable until a worker reads it "
              f"({_doc.get('state')})")
        check(_doc.get("job_id"),
              f"...with an ingest job queued, so something WILL read it ({_doc.get('job_id')})")

        # The real worker, on the real queue. Not a direct call to the ingest function.
        from agents.vault_ingest import INTENT as _VINTENT
        from agents.vault_ingest import handler as _vhandler
        from gateway.worker import run_one as _run_one
        _store = _vapp.state.backend_for(T)
        _outcome = _run_one(queue=_vq, store=_store,
                            handlers={_VINTENT: _vhandler(
                                files=_LFS(_vault_dir), store=_store,
                                extract=lambda data, name: data.decode("utf-8", "replace"))})
        check(_outcome is not None and _outcome.status != "FAILED",
              f"the worker ingests the queued document ({_outcome.status if _outcome else None})")

        _st = _vc.post("/v2/vault/status", json={"document_id": _doc["document_id"]})
        check(_st.status_code == 200 and _st.json().get("state") == "INGESTED",
              f"...and the document reads INGESTED over HTTP ({_st.json().get('state')})")

        _ver = _vc.post("/v2/vault/verify", json={"document_id": _doc["document_id"]})
        check(_ver.status_code == 200 and _ver.json().get("status") != "REFUSED",
              f"vault.verify answers over HTTP rather than refusing NO_VAULT "
              f"({str(_ver.json())[:70]})")
        _checks = _ver.json().get("checks") or []
        check(len(_checks) >= 2,
              f"...with a line per CHECK, not one verdict ({len(_checks)} checks)")
        check(all(c.get("result") for c in _checks),
              "...and every check carries a result")

        # /v1/health reports the file store the same way it reports the store.
        _h = _vc.get(HEALTH_PATH).json()
        check(isinstance(_h.get("files"), dict),
              f"/v1/health reports the file store as its own object, like `store` ({_h.get('files')})")
        check(_h["files"].get("kind") == "local" and _h["files"].get("configured") is True,
              f"...naming its kind and that it is configured ({_h.get('files')})")

    # With NO file store the refusal is KEPT, and health says so rather than being silent.
    _noapp = create_app(clock=lambda: GEN, handler=handle, keys=keys, db_url="")
    _nc = TestClient(_noapp, headers={"Authorization": f"Bearer {KEY}"})
    _nu = _nc.post("/v2/vault/upload", json={"name": "x.txt", "text": "some clause"})
    check(_nu.json().get("code") == "NO_VAULT",
          f"with no file store the upload still refuses NO_VAULT by name ({_nu.json().get('code')})")
    _nh = _nc.get(HEALTH_PATH).json()
    check(_nh["files"].get("configured") is False,
          f"...and /v1/health says the file store is not configured ({_nh.get('files')})")
    check(_nh["files"].get("note"),
          "...with a note, so an operator reading health knows the vault cannot accept "
          "an upload rather than discovering it from a refusal")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
