"""The JSON API over the compliance engine. Zero dependencies, pure and testable.

`handle(method, path, body)` is a pure function — (status, response dict) — so it is
unit-testable without a socket; `scripts/serve_api.py` wraps it in the stdlib HTTP
server. One real endpoint today:

    POST /v1/compliance-pack   company facts (JSON) -> the cited evidence pack (JSON)
    POST /v1/ask               one question -> a placedon.ask/0 turn (checker/ask.py)
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


def _typed(payload: dict, key: str, kind: type, *, non_negative: bool = False):
    """A scalar fact of the declared type, or None. A wrong type is a 400 naming the
    field -- never a TypeError three modules later (director_count="many" was a crash)."""
    v = payload.get(key)
    if v is None:
        return None
    if not isinstance(v, kind) or isinstance(v, bool) or (non_negative and v < 0):
        want = f"a non-negative {kind.__name__}" if non_negative else f"a {kind.__name__}"
        raise BadRequest(f"{key!r} must be {want} or omitted, got {v!r}")
    return v


def _profile(payload: dict) -> CompanyProfile:
    cls = _req(payload, "company_class")
    if cls not in ("private", "public", "opc"):
        raise BadRequest(f"company_class must be private/public/opc, got {cls!r}")
    fy = _typed(payload, "financial_year", str)
    return CompanyProfile(
        company_class=cls,
        incorporation_date=_date(payload, "incorporation_date", required=True),
        as_of=_date(payload, "as_of", required=True),
        cin=_typed(payload, "cin", str),
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
        director_count=_typed(payload, "director_count", int, non_negative=True))


# ── the evidence schema: declared once, typed strictly, used by every route ───
# ONE table. EVIDENCE_KEYS is derived from it, _evidence() builds from it, and checker/ask.py
# refuses by it -- so no field can be read by one and ignored or coerced by another.
# calendar_year was the field that proved the need: it was read untyped, "2025" compared
# unequal to every meeting's int year, no meeting was counted, and s.173 reported a defect
# in a company that held all four (ASK-1 round 3, finding 3).

def _calendar_year(ev: dict, key: str, as_of: date):
    """A calendar year the engine can actually evaluate s.173 against, or a 400.

    First: the first calendar year wholly under the Companies Act 2013, from
    checker/as_of.COMMENCEMENT (01-04-2014, when the bulk of the Act commenced) -- 2014
    itself straddles the 1956 Act. Last: the last calendar year that has ENDED on the read
    date. s.173 sets a minimum "every year" and s173_slice counts meetings without knowing
    the date it is read on, so a year still running would be reported short of four
    meetings in September -- another false defect.
    """
    from checker.as_of import COMMENCEMENT
    year = _typed(ev, key, int)
    if year is None:
        return None
    first = COMMENCEMENT.year + 1
    last = as_of.year if (as_of.month, as_of.day) == (12, 31) else as_of.year - 1
    if not first <= year <= last:
        raise BadRequest(
            f"'calendar_year' {year} cannot be evaluated: this engine checks s.173 for "
            f"calendar years {first}-{last} -- from the first year wholly under the Act "
            f"(commenced {COMMENCEMENT.isoformat()}) to the last year ended by the read date "
            f"{as_of.isoformat()}")
    return year


def _resident_days(ev: dict, key: str, as_of: date):
    """Days in India in one financial year: 0 to 366. A financial year runs to 31 March
    (s.2(41)), so a full one has 365 or 366 days; a longer first year falls under
    s.149(3)'s proportionate proviso, which this engine does not compute."""
    days = _typed(ev, key, int, non_negative=True)
    if days is not None and days > 366:
        raise BadRequest(f"{key!r} {days} is more days than a financial year has (366)")
    return days


_EVIDENCE_FIELDS = {
    "agm_dates": lambda ev, k, as_of: _dates(ev, k),
    "financial_year_end": lambda ev, k, as_of: _date(ev, k),
    "board_meetings": lambda ev, k, as_of: _dates(ev, k),
    "calendar_year": _calendar_year,
    "aoc4_filed_on": lambda ev, k, as_of: _date(ev, k),
    "annual_return_filed_on": lambda ev, k, as_of: _date(ev, k),
    "resident_director_days": _resident_days,
    "first_financial_year_end": lambda ev, k, as_of: _date(ev, k),
}
EVIDENCE_KEYS = frozenset(_EVIDENCE_FIELDS)


def _evidence(payload: dict, as_of: date) -> Evidence:
    """The evidence, every field typed by the one schema above. An undeclared field is a
    400: read by nothing, it would change no row and the caller would never know."""
    ev = payload.get("evidence") or {}
    if not isinstance(ev, dict):
        raise BadRequest("'evidence' must be an object")
    unknown = set(ev) - EVIDENCE_KEYS
    if unknown:
        raise BadRequest(f"unknown evidence field(s): {', '.join(sorted(unknown))}. "
                         f"Declared: {', '.join(sorted(EVIDENCE_KEYS))}")
    return Evidence(**{k: read(ev, k, as_of) for k, read in _EVIDENCE_FIELDS.items()})


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
    _reject_unknown(payload, PROFILE_KEYS | {"evidence"}, "request")
    profile = _profile(payload)
    pack = build_pack(profile, _evidence(payload, profile.as_of), generated_at=generated_at)
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


# ── F1: document currency check ───────────────────────────────────────────────
# The question this answers is NOT "is this company compliant" -- that is
# /v1/compliance-pack. It is: **a document was made on one date and is being read
# on another. Has the law it rests on moved in between?**
#
# A board resolution dated June 2024 relying on the Rs 4 crore small-company limit
# was correct when it was signed. The identical document read today is not, because
# G.S.R. 880(E) moved the limit on 01-12-2025. Nothing else on the Indian market
# tells a lawyer that, and it is invisible to any check that only looks at today.

DOC_CHECK_ESTABLISHES = (
    "whether the law each obligation rests on moved between the document's date "
    "and the date you are reading it",
    "which instrument moved it, and when it took effect",
    "what could not be checked, and the reference for acquiring it",
)
# The company facts _profile() reads -- the engine's declared fact names.
PROFILE_KEYS = frozenset({
    "as_of", "company_class", "incorporation_date", "cin",
    "financial_year", "is_listed", "is_section_8", "is_holding_company",
    "is_subsidiary_company", "governed_by_special_act", "director_count",
    "paid_up_capital_rupees", "turnover_rupees", "net_worth_rupees",
    "net_profit_rupees",
})
_DOC_CHECK_KEYS = PROFILE_KEYS | {"document_date"}

DOC_CHECK_DOES_NOT_ESTABLISH = (
    "that the document is valid, correctly drafted, or legally effective",
    "that the obligations named here are the whole of the Act that applies",
    "that a row marked verified is compliant -- only that its legal basis is current",
)


def document_check(payload: dict, *, generated_at: str) -> dict:
    """Compare an obligation's legal basis at the document's date vs the read date.

    Pure and deterministic. No model is consulted, and none could be: every input
    is a date or a company fact, and every output is a lookup against instruments
    we hold. Fails closed -- an obligation whose basis cannot be established at
    EITHER date lands in `cannot_verify`, never in `verified`.
    """
    from checker import currency
    from checker.obligations import build

    # Reject unknown keys. _figure() returns None when its <key>_rupees is absent,
    # so a caller who writes "paid_up_capital" instead of "paid_up_capital_rupees"
    # gets a row that refuses for a completely different reason -- a wrong answer
    # wearing the costume of a cautious one. Fail loudly on the typo instead.
    unknown = set(payload) - _DOC_CHECK_KEYS
    if unknown:
        raise BadRequest(
            f"unknown field(s): {', '.join(sorted(unknown))}. Money fields take the "
            "suffix _rupees (e.g. paid_up_capital_rupees) and require financial_year")

    doc_date = _date(payload, "document_date", required=True)
    as_of = _date(payload, "as_of") or date.fromisoformat(generated_at[:10])
    if doc_date > as_of:
        raise BadRequest(
            f"'document_date' ({doc_date}) is after 'as_of' ({as_of}) — a document "
            "cannot be read before it was made")

    # The profile is dated to the DOCUMENT, so applicability is decided on the law
    # the document lived under, not today's.
    profile = _profile({**payload, "as_of": doc_date.isoformat()})
    rows = {r.obligation_id: r for r in build(profile)}
    # ...and again at the read date, purely to learn what is blocking a row TODAY.
    # The document-date row cannot carry that: on 01-06-2024 nothing was blocked,
    # which is exactly why the supersession is invisible from one date alone.
    rows_now = {r.obligation_id: r
                for r in build(_profile({**payload, "as_of": as_of.isoformat()}))}

    at_doc = {f.obligation_id: f for f in currency.report(doc_date)}
    at_read = {f.obligation_id: f for f in currency.report(as_of)}

    superseded, cannot_verify, verified = [], [], []
    for oid, row in rows.items():
        was, now = at_doc.get(oid), at_read.get(oid)
        if was is None or now is None:            # not in the currency map at all
            cannot_verify.append({"obligation_id": oid, "duty": row.duty,
                                  "provision": row.provision,
                                  "detail": "no declared currency basis",
                                  "reference": None})
            continue

        # What counts as "moved" is a CHANGE OF GOVERNING INSTRUMENT, not a
        # degraded status. Comparing status alone worked only while the newer
        # instrument was unheld: once G.S.R. 880(E) was attested, both dates read
        # CURRENT and the check stopped firing on precisely the case the feature
        # exists for -- a 2024 document resting on a limit that has since moved.
        # Holding the new instrument makes the answer BETTER (we can say what it
        # moved to), so it must not make the detection worse.
        instrument_changed = (was.instrument or "") != (now.instrument or "")
        degraded = was.status == currency.CURRENT and now.status != currency.CURRENT
        if instrument_changed or degraded:
            superseded.append({
                "obligation_id": oid, "duty": row.duty, "provision": row.provision,
                "was_at_document_date": was.status,
                "is_at_read_date": now.status,
                "governed_then": was.instrument,
                "governs_now": now.instrument,
                "instrument": now.instrument,
                "detail": now.detail,
                "reference": (rows_now.get(oid).blocked_by or None
                              if rows_now.get(oid) else None),
            })
        elif now.status != currency.CURRENT:
            # It was already not current when the document was made. Different
            # finding, and saying so matters: nothing changed under the author.
            cannot_verify.append({
                "obligation_id": oid, "duty": row.duty, "provision": row.provision,
                "detail": now.detail, "instrument": now.instrument,
                "already_open_at_document_date": True,
                "reference": (rows_now.get(oid).blocked_by or None
                              if rows_now.get(oid) else None),
            })
        else:
            verified.append({"obligation_id": oid, "duty": row.duty,
                             "provision": row.provision, "state": row.state,
                             "basis": row.basis})

    # The scope frame. Two practitioner personas in different registers demanded
    # this independently (objection_sim O-02, O-03): one feared her staff would
    # read silence as clearance, the other that his paralegal would read thirteen
    # ticks as clean. Both are the same defect -- an answer that does not carry
    # its own scope -- and it is fixed by NAMING what was not checked, every time,
    # rather than by reporting a ratio.
    from checker.coverage import Report, Unchecked
    from checker import staleness

    def _blocker(entry: dict) -> str:
        """Name the instrument, from the engine's own inventory.

        The row's blocked_by is preferred because it is what actually happened.
        Where a row refuses without naming one, staleness.DEPENDENCIES knows which
        instrument governs that obligation -- and "an unnamed instrument" is the
        vagueness the practising CS objected to, so it is the last resort, not the
        first.
        """
        named = entry.get("reference")
        oid = entry.get("obligation_id")
        for dep in staleness.DEPENDENCIES:
            # An internal rule id ("S-177-RULES") is meaningless to the reader this
            # frame exists for. Expand it to the instrument, with its acquisition
            # state, so "not held" and "held but unread" are visibly different.
            if named == dep.rule_id or (not named and oid in dep.governs):
                return f"{dep.instrument} [{dep.state()}]"
        if named:
            return str(named)
        return "an instrument this obligation does not name — report this"

    cov = Report(
        checked=tuple(v["duty"] for v in verified)
                + tuple(x["duty"] for x in superseded),
        unchecked=tuple(Unchecked(
            c["duty"], "its governing instrument is not held or not yet reviewed",
            acquire=_blocker(c),
            state="CANNOT_VERIFY") for c in cannot_verify),
        corpus="Companies Act 2013", as_of=as_of.isoformat())

    return {
        "document_date": doc_date.isoformat(),
        "as_of": as_of.isoformat(),
        "generated_at": generated_at,
        "summary": {"superseded": len(superseded),
                    "cannot_verify": len(cannot_verify),
                    "verified": len(verified)},
        "coverage": cov.to_json(),
        "superseded": superseded,
        "cannot_verify": cannot_verify,
        "verified": verified,
        "what_this_is": DOC_CHECK_ESTABLISHES,
        "what_it_is_not": DOC_CHECK_DOES_NOT_ESTABLISH,
        "no_model": True,
    }


# ── POST /v1/mca-strip ───────────────────────────────────────────────────────

_STRIP_KEYS = frozenset({"as_of", "document_date", "agm_date", "allow_sole_party",
                         "parties", "registers", "document"})
_PARTY_KEYS = frozenset({"cin", "role", "span", "start", "end"})
_REGISTER_KEYS = frozenset({"cin", "fetched_at", "source", "values", "classes"})
_CLASS_KEYS = frozenset({"name", "nominal_per_share", "authorised_rupees",
                         "issued_rupees"})
_DOCFACT_KEYS = frozenset({"allotment_shares", "allotment_class", "allotment_clause",
                           "states_unencumbered", "encumbrance_clause",
                           "signatory_din"})

MCA_STRIP_DOES_NOT_ESTABLISH = (
    "that a warranty is breached -- the register shows a conflict, not a conclusion",
    "that a figure is current -- every chip carries how far back an unfiled event "
    "could reach, and in which direction",
    "that the registry record is primary evidence -- it is graded SECONDARY, and a "
    "hash proves our custody, not what MCA said",
)


def _reject_unknown(obj: dict, allowed: frozenset, where: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise BadRequest(f"unknown field(s) in {where}: {', '.join(sorted(unknown))}")


def mca_strip(payload: dict, *, generated_at: str) -> dict:
    """Reconcile a draft against the registers held for its parties.

    Deterministic; no model is consulted. The registers are supplied by the caller
    because there is no contracted aggregator -- `corporate_data` still refuses, and
    that is the honest prototype boundary rather than a missing feature.
    """
    from checker.mca_reconcile import ClassCapital
    from checker.mca_snapshot import Snapshot
    from checker.mca_strip import DocumentFacts, Register, as_json, build
    from checker.party_resolution import Party

    _reject_unknown(payload, _STRIP_KEYS, "request")
    as_of = _date(payload, "as_of") or date.fromisoformat(generated_at[:10])
    doc_date = _date(payload, "document_date")
    if doc_date and doc_date > as_of:
        raise BadRequest(f"'document_date' ({doc_date}) is after 'as_of' ({as_of}) "
                         "-- a document cannot be read before it was made")

    parties = []
    for raw in payload.get("parties") or ():
        _reject_unknown(raw, _PARTY_KEYS, "parties[]")
        try:
            parties.append(Party(_req(raw, "cin"), _req(raw, "role"),
                                 raw.get("span"), raw.get("start"), raw.get("end")))
        except ValueError as e:
            raise BadRequest(str(e)) from e

    registers = []
    for raw in payload.get("registers") or ():
        _reject_unknown(raw, _REGISTER_KEYS, "registers[]")
        fetched = _date(raw, "fetched_at", required=True)
        classes = None
        if raw.get("classes") is not None:
            classes = []
            for c in raw["classes"]:
                _reject_unknown(c, _CLASS_KEYS, "registers[].classes[]")
                classes.append(ClassCapital(_req(c, "name"),
                                            int(_req(c, "nominal_per_share")),
                                            c.get("authorised_rupees"),
                                            c.get("issued_rupees")))
            classes = tuple(classes)
        try:
            snap = Snapshot(_req(raw, "cin"), fetched, _req(raw, "source"),
                            dict(raw.get("values") or {}))
        except ValueError as e:
            raise BadRequest(str(e)) from e
        registers.append(Register(snap, classes))

    facts = dict(payload.get("document") or {})
    _reject_unknown(facts, _DOCFACT_KEYS, "document")
    document = DocumentFacts(**facts)

    strip = build(registers=tuple(registers), parties=tuple(parties),
                  document=document, as_of=as_of, document_date=doc_date,
                  agm_date=_date(payload, "agm_date"),
                  allow_sole_party=bool(payload.get("allow_sole_party", True)))

    return {**as_json(strip), "generated_at": generated_at,
            "does_not_establish": list(MCA_STRIP_DOES_NOT_ESTABLISH)}


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
    if method == "POST" and path == "/v1/ask":
        # One turn of the Ask surface. Deterministic: checker/ask.py calls retrieval, the
        # threshold table, the scope register and the two routes below, and never a model.
        from checker.ask import answer
        from checker.ask_contract import validate
        try:
            resp = answer(body or {}, generated_at=generated_at)
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}
        # The route checks its own output. A response that breaks placedon.ask/0 is a
        # server fault: withheld, with no state a client could render -- never a 200.
        violations = validate(resp)
        if violations:
            return 500, {"error": "contract_violation",
                         "detail": "the response broke placedon.ask/0 and was withheld",
                         "violations": violations}
        return 200, resp
    if method == "POST" and path == "/v1/document-check":
        try:
            return 200, document_check(body or {}, generated_at=generated_at)
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}
    if method == "POST" and path == "/v1/mca-strip":
        try:
            return 200, mca_strip(body or {}, generated_at=generated_at)
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}
    if method == "POST" and path == "/v1/compliance-pack":
        try:
            return 200, compliance_pack(body or {}, generated_at=generated_at)
        except BadRequest as e:
            return 400, {"error": "bad_request", "detail": str(e)}
    return 404, {"error": "not_found",
                 "detail": f"no route for {method} {path}",
                 "routes": ["GET /v1/health", "POST /v1/ask",
                            "POST /v1/compliance-pack",
                            "POST /v1/document-check",
                            "POST /v1/mca-strip",
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
    # ── F1: the document currency check ──────────────────────────────────────
    from checker.prescribed_thresholds import none_acquired as _none_acq_early
    _doc = {"company_class": "private", "incorporation_date": "2015-04-01",
            "is_listed": False, "paid_up_capital_rupees": 60000000,
            "turnover_rupees": 550000000, "financial_year": "2024-25",
            "director_count": 2}

    # The case the feature exists for: a 2024 document read today. Its basis was
    # current when it was written and is not now, because G.S.R. 880(E) moved it.
    st, b = handle("POST", "/v1/document-check",
                   {**_doc, "document_date": "2024-06-01", "as_of": "2026-09-10"},
                   generated_at=GEN)
    check(st == 200, f"the document check serves ({st})")
    sup = b["superseded"]
    check(len(sup) == 1 and sup[0]["obligation_id"] == "CA13-S2-85-SMALL",
          f"a 2024 document's small-company basis is flagged as moved ({[x['obligation_id'] for x in sup]})")
    check("700(E)" in (sup[0]["governed_then"] or ""),
          f"...naming the instrument that governed when it was written ({sup[0]['governed_then']})")
    check("880(E)" in (sup[0]["governs_now"] or ""),
          f"...and the one that governs now ({sup[0]['governs_now']})")

    # REGRESSION GUARD. "Moved" must mean the GOVERNING INSTRUMENT CHANGED, not
    # that the currency status degraded. Comparing status alone worked only while
    # 880(E) was unheld: the moment it was attested, both dates read CURRENT and
    # the check stopped firing on exactly the case this feature exists for.
    # Acquiring an instrument makes the answer better; it must never make the
    # detection worse.
    check(sup[0]["was_at_document_date"] == "CURRENT"
          and sup[0]["is_at_read_date"] == "CURRENT",
          "...and it is flagged even though BOTH dates read CURRENT, because the "
          "instrument changed")

    # while the instrument is unheld, the same document still flags -- for the
    # other reason -- and names the acquisition task.
    from checker.prescribed_thresholds import none_acquired as _none_acq
    with _none_acq():
        _, bu = handle("POST", "/v1/document-check",
                       {**_doc, "document_date": "2024-06-01", "as_of": "2026-09-10"},
                       generated_at=GEN)
        supu = [r for r in bu["superseded"] if r["obligation_id"] == "CA13-S2-85-SMALL"]
        check(supu and supu[0]["reference"] == "S-003",
              f"while unheld, the same row flags and names the acquisition task "
              f"({supu[0]['reference'] if supu else None!r})")

    # Read the same document before the instrument commenced: nothing has moved.
    st, b2 = handle("POST", "/v1/document-check",
                    {**_doc, "document_date": "2024-06-01", "as_of": "2025-06-01"},
                    generated_at=GEN)
    check(not b2["superseded"],
          f"read before 880(E) commenced, nothing is superseded ({len(b2['superseded'])})")

    # A document written AFTER the change is not a supersession -- nothing moved
    # under its author. It is an open gap, and the response says which.
    st, b3 = handle("POST", "/v1/document-check",
                    {**_doc, "document_date": "2026-01-01", "as_of": "2026-09-10"},
                    generated_at=GEN)
    check(not b3["superseded"],
          "a document written after the change is not reported as superseded")
    # Nothing moved under its author, and the instrument is held, so the row simply
    # answers. The "already open" path below is what happens when it is NOT held --
    # and it must be exercised under a stub, or it asserts whatever is on disk.
    check(any(r["obligation_id"] == "CA13-S2-85-SMALL" for r in b3["verified"]),
          "...it simply answers, because we hold the instrument that governs it")
    with _none_acq_early():
        _, b3u = handle("POST", "/v1/document-check",
                        {**_doc, "document_date": "2026-01-01", "as_of": "2026-09-10"},
                        generated_at=GEN)
        already = [r for r in b3u["cannot_verify"] if r.get("already_open_at_document_date")]
        check(any(r["obligation_id"] == "CA13-S2-85-SMALL" for r in already),
              "...and while unheld it is an open gap, marked as already open at "
              "the document's date -- not as a supersession, because nothing "
              "moved under its author")

    # Fails closed on inputs rather than guessing.
    st, b4 = handle("POST", "/v1/document-check", {**_doc, "paid_up_capital": 6,
                    "document_date": "2024-06-01"}, generated_at=GEN)
    check(st == 400 and "paid_up_capital" in b4["detail"],
          f"a mistyped money field is 400, not a silently unpopulated figure ({st})")
    st, _ = handle("POST", "/v1/document-check",
                   {**_doc, "document_date": "2026-09-10", "as_of": "2024-06-01"},
                   generated_at=GEN)
    check(st == 400, f"a document dated after the read date is 400 ({st})")
    st, _ = handle("POST", "/v1/document-check", {**_doc}, generated_at=GEN)
    check(st == 400, f"a missing document_date is 400 ({st})")

    # Nothing lands in `verified` on an unestablished basis.
    st, b5 = handle("POST", "/v1/document-check",
                    {**_doc, "document_date": "2024-06-01", "as_of": "2026-09-10"},
                    generated_at=GEN)
    ids_v = {r["obligation_id"] for r in b5["verified"]}
    ids_bad = {r["obligation_id"] for r in b5["superseded"]} | \
              {r["obligation_id"] for r in b5["cannot_verify"]}
    check(not (ids_v & ids_bad),
          "an obligation is in exactly one bucket -- never verified and flagged")
    check(b5["no_model"] is True, "the document check consults no model")

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

    # ── the coverage frame (objection_sim O-02, O-03) ────────────────────────
    st, r = handle("POST", "/v1/document-check",
                   {"document_date": "2024-06-14", "company_class": "private",
                    "incorporation_date": "2021-01-01"}, generated_at=GEN)
    cov = r["coverage"]
    check(st == 200 and cov["unchecked_count"] == len(r["cannot_verify"]),
          f"every answer carries a coverage frame, and it agrees with the rows "
          f"({cov['checked_count']} checked, {cov['unchecked_count']} not)")
    check(all(u["acquire"] and "unnamed" not in u["acquire"]
              for u in cov["unchecked"]),
          "every unchecked item names the INSTRUMENT that would settle it -- not "
          "an internal rule id and not 'an unnamed instrument'")
    check(any("HELD_UNREVIEWED" in u["acquire"] or "STAGED" in u["acquire"]
              or "NOT_HELD" in u["acquire"] for u in cov["unchecked"]),
          "...with its acquisition state, so 'not held' and 'held but unread' are "
          "visibly different things")
    check("silence about them is not a finding" in cov["sentence"],
          "...and the frame says what silence does not mean")
    check(cov["establishes_compliance"] is False and cov["dismissable"] is False,
          "the frame declares it establishes no compliance and is not dismissable")
    check(all(u["what"] in cov["sentence"] for u in cov["unchecked"]),
          "...and every unchecked duty is named in full, never summarised away")

    # ── POST /v1/mca-strip ───────────────────────────────────────────────────
    _cin = "U72200KA2021PTC145892"
    _strip_body = {
        "as_of": "2026-09-12", "document_date": "2026-06-14",
        "parties": [{"cin": _cin, "role": "TARGET", "span": "(the 'Target')"},
                    {"cin": _cin, "role": "ISSUER", "span": "the Company shall allot"}],
        "registers": [{"cin": _cin, "fetched_at": "2026-09-12",
                       "source": "MCA21 via contracted aggregator",
                       "values": {"charges": [{"holder": "ICICI Bank"}],
                                  "authorised_capital": 50_000_000,
                                  "paid_up_capital": 32_000_000},
                       "classes": [{"name": "equity", "nominal_per_share": 10,
                                    "authorised_rupees": 40_000_000,
                                    "issued_rupees": 32_000_000}]}],
        "document": {"allotment_shares": 1_000_000, "allotment_clause": "Cl 3.2",
                     "states_unencumbered": True, "encumbrance_clause": "Cl 5.1"}}
    st, r = handle("POST", "/v1/mca-strip", _strip_body, generated_at=GEN)
    check(st == 200 and r["severity"] == "BLOCKING",
          f"the strip route answers, and a Rs 1 Cr allotment against Rs 0.80 Cr of "
          f"equity headroom is blocking ({st}/{r.get('severity')})")
    check(all(c["blindness"] for c in r["chips"]),
          "every chip crosses the wire with its blindness attached")
    check("reconciled" not in r["headline"].lower(),
          f"the headline never claims reconciliation: {r['headline']!r}")
    check(r["evidence_grade"] == "SECONDARY" and r["no_model"] is True,
          "the payload grades its evidence and declares no model ran")
    check(any("not a conclusion" in d for d in r["does_not_establish"]),
          "...and states in the payload that a conflict is not a conclusion")

    for bad, why in (({"partys": []}, "a mistyped top-level key"),
                     ({"parties": [{"cin": _cin, "role": "TARGET", "spam": "x"}]},
                      "a mistyped key inside parties[]"),
                     ({"parties": [{"cin": _cin, "role": "COUNTERPARTY"}]},
                      "an unknown role"),
                     ({"registers": [{"cin": _cin, "fetched_at": "2026-09-12",
                                      "source": "s", "values": {"revenue": 1}}]},
                      "an unknown master-data field"),
                     ({"as_of": "2026-01-01", "document_date": "2026-06-14"},
                      "a document dated after the read date")):
        st_b, r_b = handle("POST", "/v1/mca-strip", bad, generated_at=GEN)
        check(st_b == 400, f"{why} is refused with 400, not absorbed: "
                           f"{r_b.get('detail', '')[:60]}")

    check("POST /v1/mca-strip" in handle("GET", "/nope", None,
                                         generated_at=GEN)[1]["routes"],
          "the route is advertised in the 404 route list")

    # ── POST /v1/ask ─────────────────────────────────────────────────────────
    # Served through the PACKAGE module, not this one. Running api.py as a file makes a
    # second copy of it, and checker/ask.py raises the package's BadRequest -- a different
    # class from the one caught two frames up here. The route is only ever served as
    # checker.api (scripts/serve_api.py:22), so that is what this exercises.
    from checker.api import handle as ask_handle
    from checker.ask_contract import validate as _validate
    _ask_facts = {"company_class": "private", "incorporation_date": "2019-06-01",
                  "as_of": "2026-09-05", "financial_year": "2024-25",
                  "paid_up_capital_rupees": 120000000, "turnover_rupees": 800000000}
    st, r = ask_handle("POST", "/v1/ask",
                   {"question": "Is this company a small company?", "facts": _ask_facts,
                    "provisions": ["s.2(85)"],
                    "figures": ["small_company.paid_up_capital.prescribed"]},
                   generated_at=GEN)
    check(st == 200 and r["schema"] == "placedon.ask/0" and r["state"] == "answered",
          f"the ask route answers a deterministic question ({st}/{r.get('state')})")
    check(_validate(r) == [], f"...and its response meets the contract ({_validate(r)})")
    check(r["uses_model"] is False and r["generated_at"] == GEN,
          "...stating that no model was used, stamped with the request's time")

    st, r = ask_handle("POST", "/v1/ask",
                   {"question": "What must we report to RBI for this allotment?"},
                   generated_at=GEN)
    check(st == 200 and r["state"] == "out_of_scope" and _validate(r) == [],
          f"a question about a body we do not hold is refused, not answered ({r.get('state')})")

    st, r = ask_handle("POST", "/v1/ask",
                   {"question": "Is this document current?",
                    "context": {"kind": "document"}, "facts": {"company_class": "private",
                                                               "incorporation_date": "2019-06-01"}},
                   generated_at=GEN)
    check(st == 400 and "document_date" in r["detail"],
          f"a document turn with no document date is a 400 naming the field ({st})")
    st, r = ask_handle("POST", "/v1/ask", {}, generated_at=GEN)
    check(st == 400 and "question" in r["detail"],
          f"a request with no question is a 400 ({st})")
    st, r = ask_handle("POST", "/v1/ask", {"question": "x", "figures": ["no.such.key"]},
                   generated_at=GEN)
    check(st == 400, f"a figure key the engine does not declare is a 400 ({st})")
    check("POST /v1/ask" in ask_handle("GET", "/nope", None, generated_at=GEN)[1]["routes"],
          "the ask route is advertised in the 404 route list")

    # The route checks its own response against the contract. A violation is a server
    # fault: it is withheld as a 500 that carries no state, never served as a 200.
    import checker.ask as _ask_mod
    _saved_answer = _ask_mod.answer
    _ask_mod.answer = lambda body, generated_at: {"schema": "placedon.ask/0",
                                                  "state": "answered", "confidence": "HIGH"}
    try:
        st, r = ask_handle("POST", "/v1/ask", {"question": "x"}, generated_at=GEN)
    finally:
        _ask_mod.answer = _saved_answer
    check(st == 500 and "state" not in r and r.get("violations"),
          f"a response that breaks placedon.ask/0 is withheld as a 500 with no state "
          f"({st}, {sorted(r)})")
    st, r = ask_handle("POST", "/v1/ask",
                       {"question": "Is this company a small company?",
                        "facts": {**_ask_facts, "confidence": "HIGH"},
                        "provisions": ["s.2(85)"]}, generated_at=GEN)
    check(st == 400 and "confidence" in r["detail"],
          f"an undeclared fact key is a 400 naming it, not an echoed field ({st})")

    # ── evidence is typed by one schema, strictly (ASK-1 round 3, finding 3) ─
    # calendar_year "2025" was never typed: s173_slice compared the meeting dates' int
    # years with a string, counted none, and the row said APPLIES_NOT_SATISFIED -- a
    # defect found in a company that held all four meetings. CLAUDE.md: never call a
    # finding a defect when it is not one. Now a 400, on every route.
    _meet = ["2025-01-10", "2025-04-10", "2025-07-10", "2025-10-10"]
    for label, ev in (('calendar_year "2025" (a string)',
                       {"board_meetings": _meet, "calendar_year": "2025"}),
                      ('calendar_year "x"', {"board_meetings": _meet, "calendar_year": "x"}),
                      ("calendar_year true", {"board_meetings": _meet, "calendar_year": True}),
                      ("calendar_year 2025.5", {"board_meetings": _meet, "calendar_year": 2025.5}),
                      ("calendar_year -5", {"board_meetings": _meet, "calendar_year": -5}),
                      ("calendar_year 1999 (the 1956 Act's time)",
                       {"board_meetings": _meet, "calendar_year": 1999}),
                      ("calendar_year 2014 (the Act commenced 01-04-2014, mid-year)",
                       {"board_meetings": _meet, "calendar_year": 2014}),
                      ("calendar_year 2026, not yet over on the as_of date",
                       {"board_meetings": _meet, "calendar_year": 2026}),
                      ('resident_director_days "many"', {"resident_director_days": "many"}),
                      ("resident_director_days 400", {"resident_director_days": 400}),
                      ("resident_director_days -1", {"resident_director_days": -1}),
                      ("an undeclared evidence key", {"board_meeting": _meet})):
        st, r = handle("POST", "/v1/compliance-pack",
                       {**_ask_facts, "as_of": "2026-08-31", "evidence": ev},
                       generated_at=GEN)
        check(st == 400, f"compliance-pack: {label} is a 400, never a coercion or a crash "
                         f"({st}: {r.get('detail', '')[:50]})")
    st, r = handle("POST", "/v1/compliance-pack",
                   {**_ask_facts, "as_of": "2026-08-31",
                    "evidence": {"board_meetings": _meet, "calendar_year": 2025}},
                   generated_at=GEN)
    row = next(x for x in r["rows"] if x["obligation_id"] == "CA13-S173-BOARD")
    check(st == 200 and row["state"] != "APPLIES_NOT_SATISFIED",
          f"...while four meetings in a finished 2025 are never a defect ({row['state']})")
    st, r = handle("POST", "/v1/compliance-pack", {**_ask_facts, "turnover": 5},
                   generated_at=GEN)
    check(st == 400 and "turnover" in r.get("detail", ""),
          f"an undeclared top-level fact is a 400 on compliance-pack too ({st})")

    # ── facts are typed at the boundary, on every route that takes them ──────
    for field, value in (("director_count", "many"), ("director_count", -1),
                         ("cin", ["U", "1"]), ("financial_year", 2025)):
        st, r = handle("POST", "/v1/compliance-pack",
                       {**_ask_facts, field: value}, generated_at=GEN)
        check(st == 400 and field in r.get("detail", ""),
              f"{field}={value!r} is a 400 naming the field, not a crash ({st})")

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
