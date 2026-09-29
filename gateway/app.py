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


def health_body(engine_body: dict, deployment: Deployment) -> dict:
    """The engine's health, plus the one thing only the gateway knows."""
    return dict(engine_body) | {"store": {"kind": deployment.store,
                                          "degraded": deployment.degraded,
                                          "note": deployment.note}}


def create_app(*, deployment: Deployment | None = None, clock=None, handler=None):
    """The FastAPI app. Every dependency injected so the test reaches no network or clock."""
    dep = deployment or Deployment()
    now = clock or utc_now
    handle = handler
    if handle is None:
        from checker.api import handle as handle       # noqa: PLW0127

    app = FastAPI(title="Placedon gateway", docs_url=None, redoc_url=None)
    app.state.deployment = dep

    @app.api_route("/v1/{rest:path}", methods=["GET", "POST"])
    async def v1(rest: str, request: Request) -> Response:
        body = None
        if request.method == "POST":
            raw = await request.body()
            if raw:
                try:
                    body = json.loads(raw)
                except ValueError:
                    # Refused here rather than handed to the engine as None, which would
                    # read as "no body given" and produce a different, misleading refusal.
                    return Response(content=dumps(
                        {"error": "bad_request", "detail": "body is not valid JSON"}),
                        status_code=400, media_type="application/json")
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        status, payload = handle(request.method, path, body, generated_at=now())
        if request.url.path.rstrip("/") == HEALTH_PATH and status == 200:
            payload = health_body(payload, dep)
        return Response(content=dumps(payload), status_code=status,
                        media_type="application/json")

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

    GEN = "2026-09-10T00:00:00Z"
    app = create_app(deployment=Deployment(MEMORY_STORE), clock=lambda: GEN)
    client = TestClient(app)

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

    pg = TestClient(create_app(deployment=Deployment(POSTGRES_STORE), clock=lambda: GEN))
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

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
