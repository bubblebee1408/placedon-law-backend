"""The JSON API over the compliance engine. Zero dependencies, pure and testable.

`handle(method, path, body)` is a pure function — (status, response dict) — so it is
unit-testable without a socket; `scripts/serve_api.py` wraps it in the stdlib HTTP
server. One real endpoint today:

    POST /v1/compliance-pack   company facts (JSON) -> the cited evidence pack (JSON)
    GET  /v1/health            liveness + provenance

No model is consulted (the register is deterministic), so this API never emits a
guess. Input is validated at the boundary and rejected with a clear 400; unknown
figures stay unknown (never coerced to 0). The response carries the five-state
rows, the "what could not be verified" list, the law-currency watch, the provenance
block, and the explicit what-this-is / what-it-is-not boundary — the same discipline
as the rendered pack, in machine-readable form.
"""
from __future__ import annotations

from datetime import date

from checker.company_profile import CompanyProfile, Figure, Money
from checker.diligence_pack import DOES_NOT_ESTABLISH, ESTABLISHES, build_pack
from checker.obligations import Evidence


class BadRequest(ValueError):
    """Input failed validation at the boundary."""


def _req(payload: dict, key: str):
    if key not in payload or payload[key] in (None, ""):
        raise BadRequest(f"missing required field: {key!r}")
    return payload[key]


def _date(payload: dict, key: str, *, required: bool = False) -> date | None:
    v = payload.get(key)
    if v in (None, ""):
        if required:
            raise BadRequest(f"missing required date: {key!r}")
        return None
    try:
        return date.fromisoformat(v)
    except (ValueError, TypeError):
        raise BadRequest(f"{key!r} must be an ISO date (YYYY-MM-DD), got {v!r}")


def _dates(payload: dict, key: str) -> tuple[date, ...] | None:
    v = payload.get(key)
    if v is None:
        return None
    if not isinstance(v, list):
        raise BadRequest(f"{key!r} must be a list of ISO dates")
    out = []
    for item in v:
        try:
            out.append(date.fromisoformat(item))
        except (ValueError, TypeError):
            raise BadRequest(f"{key!r} contains a non-date: {item!r}")
    return tuple(out)


def _figure(payload: dict, key: str, fy: str | None) -> Figure | None:
    """A rupee figure bound to the financial year. Accepts <key>_rupees (int)."""
    v = payload.get(f"{key}_rupees")
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise BadRequest(f"{key}_rupees must be a non-negative whole-rupee integer, got {v!r}")
    if fy is None:
        raise BadRequest(f"{key}_rupees was given but financial_year is missing")
    return Figure(Money(v), fy)


def _bool(payload: dict, key: str) -> bool | None:
    v = payload.get(key)
    if v is None:
        return None
    if not isinstance(v, bool):
        raise BadRequest(f"{key!r} must be true/false or omitted, got {v!r}")
    return v


def _profile(payload: dict) -> CompanyProfile:
    cls = _req(payload, "company_class")
    if cls not in ("private", "public", "opc"):
        raise BadRequest(f"company_class must be private/public/opc, got {cls!r}")
    fy = payload.get("financial_year")
    return CompanyProfile(
        company_class=cls,
        incorporation_date=_date(payload, "incorporation_date", required=True),
        as_of=_date(payload, "as_of", required=True),
        cin=payload.get("cin"),
        latest_financial_year=fy,
        is_listed=_bool(payload, "is_listed"),
        is_section_8=_bool(payload, "is_section_8"),
        is_holding_company=_bool(payload, "is_holding_company"),
        is_subsidiary_company=_bool(payload, "is_subsidiary_company"),
        governed_by_special_act=_bool(payload, "governed_by_special_act"),
        paid_up_capital=_figure(payload, "paid_up_capital", fy),
        turnover=_figure(payload, "turnover", fy),
        net_worth=_figure(payload, "net_worth", fy),
        net_profit=_figure(payload, "net_profit", fy),
        director_count=payload.get("director_count"))


def _evidence(payload: dict) -> Evidence:
    ev = payload.get("evidence") or {}
    if not isinstance(ev, dict):
        raise BadRequest("'evidence' must be an object")
    return Evidence(
        agm_dates=_dates(ev, "agm_dates"),
        financial_year_end=_date(ev, "financial_year_end"),
        board_meetings=_dates(ev, "board_meetings"),
        calendar_year=ev.get("calendar_year"),
        aoc4_filed_on=_date(ev, "aoc4_filed_on"),
        annual_return_filed_on=_date(ev, "annual_return_filed_on"),
        resident_director_days=ev.get("resident_director_days"),
        first_financial_year_end=_date(ev, "first_financial_year_end"))


def _row_json(r) -> dict:
    from checker.obligation_citations import structural_cites
    return {
        "obligation_id": r.obligation_id,
        "duty": r.duty,
        "provision": r.provision,
        "state": r.state,
        "basis": r.basis,
        "missing_facts": list(r.missing_facts),
        "blocked_by": r.blocked_by or None,
        "cited_spans": [{"path": c.path, "sha256": c.sha256, "resolved": c.resolved}
                        for c in structural_cites(r.obligation_id)],
    }


def compliance_pack(payload: dict, *, generated_at: str) -> dict:
    """Build the pack from a validated payload and serialise it to JSON."""
    if not isinstance(payload, dict):
        raise BadRequest("request body must be a JSON object")
    pack = build_pack(_profile(payload), _evidence(payload), generated_at=generated_at)
    return {
        "company_class": pack.company_class,
        "cin": pack.cin,
        "as_of": pack.as_of.isoformat(),
        "financial_year": pack.financial_year,
        "generated_at": pack.generated_at,
        "provenance": pack.provenance,
        "summary": {
            "not_satisfied": len(pack.not_satisfied),
            "undetermined": len(pack.undetermined),
            "cannot_determine": len(pack.cannot_determine),
            "satisfied": len(pack.satisfied),
            "not_applicable": len(pack.not_applicable),
        },
        "rows": [_row_json(r) for r in pack.rows],
        "unverified": [{"obligation_id": oid, "to_settle": need}
                       for oid, need in pack.unverified()],
        "law_currency_watch": [{"obligation_id": f.obligation_id, "status": f.status,
                                "instrument": f.instrument, "detail": f.detail}
                               for f in pack.currency_flags],
        "what_this_is": ESTABLISHES,
        "what_it_is_not": DOES_NOT_ESTABLISH,
    }


def _query(raw: str) -> dict[str, str]:
    """Parse a query string. Unknown keys are the caller's business; we only read
    the ones we document, and a malformed value fails closed at the reader."""
    from urllib.parse import parse_qsl
    return dict(parse_qsl(raw, keep_blank_values=False))


def _event_json(e) -> dict:
    return {
        "id": e.id,
        "at": e.at.isoformat(),
        "known_at": e.known_at.isoformat(),
        "kind": e.kind,
        "subtype": e.subtype,
        "title": e.title,
        "output_class": e.output_class,
        "currency_state": e.currency_state,
        "obligation_id": e.obligation_id,
        "consequence": e.consequence,
        "verified_by": e.verified_by,
        "source": {"instrument": e.source.instrument,
                   "as_at": e.source.as_at.isoformat() if e.source.as_at else None,
                   "sha256": e.source.sha256,
                   "url": e.source.url},
    }


# v0 serves LAW-CHANGE events only. Company-fact events (directors, charges,
# status) need the licensed registry feed, so the response says so rather than
# implying an empty company history means a company with no history.
_V0_SCOPE = ("law_change_only — company-fact events require the licensed registry "
             "feed and are not served in v0; an absence here is not evidence that "
             "nothing happened to this company")


def _events_route(cin: str, qs: dict, *, generated_at: str) -> tuple[int, dict]:
    from checker.event_log import events_for
    as_of = _date(qs, "as_of") or date.fromisoformat(generated_at[:10])
    since = _date(qs, "since")
    if since is not None and since > as_of:
        raise BadRequest(f"'since' ({since}) is after 'as_of' ({as_of})")
    kind = qs.get("kind")
    if kind is not None and kind not in ("law", "company"):
        raise BadRequest(f"'kind' must be 'law' or 'company', got {kind!r}")
    klass = qs.get("class")
    _CLASSES = {"fact": "VERIFIED_FACT", "consequence": "DETERMINISTIC_CONSEQUENCE",
                "signal": "SIGNAL"}
    if klass is not None and klass not in _CLASSES:
        raise BadRequest(f"'class' must be one of {sorted(_CLASSES)}, got {klass!r}")

    events = events_for(as_of, since=since)
    if kind == "company":
        events = []
    if klass is not None:
        events = [e for e in events if e.output_class == _CLASSES[klass]]
    return 200, {
        "cin": cin,
        "as_of": as_of.isoformat(),
        "since": since.isoformat() if since else None,
        "generated_at": generated_at,
        "scope": _V0_SCOPE,
        "events": [_event_json(e) for e in events],
        "no_model": True,
    }


def handle(method: str, path: str, body: dict | None, *, generated_at: str
           ) -> tuple[int, dict]:
    """Route one request. Pure: no I/O. Returns (status, response dict)."""
    raw_path, _, raw_qs = path.partition("?")
    qs = _query(raw_qs)
    path = raw_path.rstrip("/") or "/"
    parts = [p for p in path.split("/") if p]

    # GET /v1/company/{cin}/events[/{event_id}]
    if method == "GET" and len(parts) in (4, 5) and parts[:2] == ["v1", "company"] \
            and parts[3] == "events":
        cin = parts[2]
        try:
            if len(parts) == 4:
                return _events_route(cin, qs, generated_at=generated_at)
            from checker.event_log import event_by_id
            as_of = _date(qs, "as_of") or date.fromisoformat(generated_at[:10])
            since = _date(qs, "since")
            ev = event_by_id(parts[4], as_of, since=since)
            if ev is None:
                return 404, {"error": "not_found",
                             "detail": f"no event {parts[4]!r} at as_of {as_of.isoformat()}"}
            return 200, {"cin": cin, "as_of": as_of.isoformat(),
                         "generated_at": generated_at, "event": _event_json(ev),
                         "no_model": True}
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}

    # GET /v1/instruments/{fragment}/affected
    if method == "GET" and len(parts) == 4 and parts[0] == "v1" \
            and parts[1] == "instruments" and parts[3] == "affected":
        from urllib.parse import unquote
        from checker.event_log import affected_by
        fragment = unquote(parts[2])
        if not fragment.strip():
            return 400, {"error": "bad_request", "detail": "empty instrument fragment"}
        return 200, {"instrument": fragment, "generated_at": generated_at,
                     "obligations": affected_by(fragment), "no_model": True}

    if method == "GET" and path == "/v1/health":
        from checker.release_record import provenance, ProvenanceError
        try:
            prov = provenance("v3", law_effective_date=generated_at[:10])
            block = {"benchmark_version": prov.benchmark_version,
                     "corpus_version": prov.corpus_version,
                     "checker_commit": prov.checker_commit}
        except ProvenanceError as e:
            block = {"provenance_error": str(e)}
        return 200, {"status": "ok", "no_model": True, **block}
    if method == "POST" and path == "/v1/compliance-pack":
        try:
            return 200, compliance_pack(body or {}, generated_at=generated_at)
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}
    return 404, {"error": "not_found",
                 "detail": f"no route for {method} {path}",
                 "routes": ["GET /v1/health", "POST /v1/compliance-pack",
                            "GET /v1/company/{cin}/events",
                            "GET /v1/company/{cin}/events/{event_id}",
                            "GET /v1/instruments/{fragment}/affected"]}


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

    print("api")
    GEN = "2026-09-05T00:00:00Z"

    # ── health ──────────────────────────────────────────────────────────────
    st, body = handle("GET", "/v1/health", None, generated_at=GEN)
    check(st == 200 and body["status"] == "ok", "health returns 200 ok")
    check(body["no_model"] is True, "health states no model is consulted")

    # ── a valid pack request ────────────────────────────────────────────────
    payload = {
        "company_class": "private",
        "incorporation_date": "2019-06-01",
        "as_of": "2026-08-31",
        "financial_year": "2024-25",
        "cin": "U74999KA2019PTC000000",
        "is_holding_company": False, "is_subsidiary_company": False,
        "is_section_8": False, "governed_by_special_act": False,
        "paid_up_capital_rupees": 20000000, "turnover_rupees": 300000000,
        "director_count": 3,
        "evidence": {"agm_dates": ["2024-08-20", "2025-12-30"],
                     "financial_year_end": "2025-03-31",
                     "board_meetings": ["2025-03-01"], "calendar_year": 2025,
                     "resident_director_days": 90},
    }
    st, body = handle("POST", "/v1/compliance-pack", payload, generated_at=GEN)
    check(st == 200, f"a valid request returns 200 ({st})")
    check(body["summary"]["not_satisfied"] >= 1,
          "the pack reports breaches (late AGM, resident director, etc.)")
    check(any(r["obligation_id"] == "CA13-S96-AGM" for r in body["rows"]),
          "the rows include the AGM obligation")
    agm = [r for r in body["rows"] if r["obligation_id"] == "CA13-S96-AGM"][0]
    check(agm["state"] == "APPLIES_NOT_SATISFIED", "the late AGM is NOT_SATISFIED")
    check("provenance" in body and "what_it_is_not" in body,
          "the response carries provenance and the boundary statement")
    check(isinstance(body["unverified"], list), "the unverified list is present")

    # ── validation: missing required field -> 400, not a crash ──────────────
    st, body = handle("POST", "/v1/compliance-pack", {"as_of": "2026-08-31"},
                      generated_at=GEN)
    check(st == 400 and "company_class" in body["detail"],
          "a missing company_class is a 400 naming the field")

    # ── validation: unknown figure is never coerced to 0 ────────────────────
    st, body = handle("POST", "/v1/compliance-pack",
                      {"company_class": "private", "incorporation_date": "2019-06-01",
                       "as_of": "2026-08-31", "paid_up_capital_rupees": -5}, generated_at=GEN)
    check(st == 400 and "whole-rupee" in body["detail"],
          "a negative rupee figure is rejected, not silently accepted")

    # ── a bad date -> 400 ───────────────────────────────────────────────────
    st, body = handle("POST", "/v1/compliance-pack",
                      {"company_class": "private", "as_of": "not-a-date",
                       "incorporation_date": "2019-06-01"}, generated_at=GEN)
    check(st == 400 and "ISO date" in body["detail"], "a malformed date is a 400")

    # ── unknown route -> 404 with the route list ────────────────────────────
    # ── the event log routes ─────────────────────────────────────────────────
    st, b = handle("GET", "/v1/company/U74999DL2015PTC000001/events"
                          "?as_of=2026-09-09&since=2025-01-01", None, generated_at=GEN)
    check(st == 200, f"the event stream serves ({st})")
    check(bool(b["events"]), f"...and carries events ({len(b['events'])})")
    check(all(e["source"]["instrument"] for e in b["events"]),
          "...every one naming its source")
    check([e["at"] for e in b["events"]] == sorted([e["at"] for e in b["events"]], reverse=True),
          "...newest first")
    check("law_change_only" in b["scope"],
          "...and the response says v0 serves law-change events only, so an absence "
          "is not read as 'nothing happened to this company'")

    ev_id = b["events"][0]["id"]
    st2, b2 = handle("GET", f"/v1/company/X/events/{ev_id}?as_of=2026-09-09&since=2025-01-01",
                     None, generated_at=GEN)
    check(st2 == 200 and b2["event"]["id"] == ev_id, f"one event fetches by id ({st2})")
    st3, _ = handle("GET", "/v1/company/X/events/nosuchevent?as_of=2026-09-09",
                    None, generated_at=GEN)
    check(st3 == 404, f"an unknown event id is 404, not an empty event ({st3})")

    # fails closed on every malformed input rather than guessing
    st4, b4 = handle("GET", "/v1/company/X/events?as_of=notadate", None, generated_at=GEN)
    check(st4 == 400 and "ISO date" in b4["detail"], f"a malformed as_of is 400 ({st4})")
    st5, _ = handle("GET", "/v1/company/X/events?as_of=2024-01-01&since=2026-01-01",
                    None, generated_at=GEN)
    check(st5 == 400, f"a since after as_of is 400, not an empty list ({st5})")
    st6, _ = handle("GET", "/v1/company/X/events?class=bogus", None, generated_at=GEN)
    check(st6 == 400, f"an unknown class filter is 400 ({st6})")

    st7, b7 = handle("GET", "/v1/company/X/events?as_of=2026-09-09&since=2025-01-01&class=signal",
                     None, generated_at=GEN)
    check(st7 == 200 and all(e["output_class"] == "SIGNAL" for e in b7["events"]),
          "the class filter selects exactly that output class")

    st8, b8 = handle("GET", "/v1/instruments/880(E)/affected", None, generated_at=GEN)
    check(st8 == 200 and b8["obligations"] == ["CA13-S2-85-SMALL"],
          f"the reverse index names the obligations an instrument moves ({b8.get('obligations')})")

    st9, _ = handle("GET", "/v1/company/X/events", {"as_of": "x"}, generated_at=GEN)
    check(st9 == 200, "a GET ignores a body rather than failing on it")

    st, body = handle("GET", "/v1/nope", None, generated_at=GEN)
    check(st == 404 and "routes" in body, "an unknown route 404s and lists the routes")

    # ── no model in the API path (parsed imports, not grepped) ──────────────
    import ast
    tree = ast.parse(open(__file__).read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    check(not (roots & {"openai", "anthropic", "requests", "httpx"}),
          f"the API imports no model or network library ({roots & {'openai','anthropic'} or 'clean'})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
