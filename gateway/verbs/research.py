"""research.multi (F2), the sources report, sources.list/search, research.cases/web, forecast (Lane B)."""
from __future__ import annotations

from gateway.verbs.core import Context, _refuse, _today
from gateway.verbs.model_access import _ledger_for
from gateway.verbs.run_records import _persist_run


def _vault_hits(question: str, ctx: Context) -> int:
    """How many vault/client documents the question matched. 0 when no vault, never an error."""
    try:
        from checker.sources.base import load
        from checker.sources.client import ClientDocuments
        return len(load(ClientDocuments(ctx.documents or {})).search(question))
    except Exception:                                            # noqa: BLE001
        return 0


def _sources_report(picked, resolved, ev, question: str, ctx: Context) -> dict:
    """What each picked source did: SEARCHED_HITS / SEARCHED_EMPTY / NOT_SEARCHED (+ named state).

    `ask` grounds answers in the held corpus. Vault retrieval is not connected to this
    answer path, so it must not advertise a search over client documents. Every other
    picked source is NOT_SEARCHED and says why: its availability
    state (KEY_MISSING / NOT_ACQUIRED / BLOCKED) when it cannot be switched on, or that live
    retrieval for it is served by sources.search, not ask, when it can. searched-empty (a search
    ran, nothing matched) is reported apart from not-searched (no search ran) on purpose.
    """
    from checker import source_picker as _sp
    picked_ids = tuple(dict.fromkeys(picked or _sp.DEFAULT))
    searchable = set(resolved.searchable)
    unavailable = {u["id"]: u for u in resolved.unavailable}

    def _tier(sid: str) -> str:
        try:
            return _sp.source(sid).tier
        except Exception:                                        # noqa: BLE001
            return _sp.PUBLIC

    searched, rows = [], []
    for sid in picked_ids:
        if sid == _sp.HELD_ID and sid in searchable:
            searched.append(sid)
            rows.append({"id": sid, "tier": _sp.HELD, "status": _sp.AVAILABLE,
                         "outcome": "SEARCHED_HITS" if ev else "SEARCHED_EMPTY",
                         "hits": len(ev), "reason": ""})
        elif sid == _sp.VAULT_ID and sid in searchable:
            rows.append({"id": sid, "tier": _sp.PUBLIC, "status": _sp.AVAILABLE,
                         "outcome": "NOT_SEARCHED", "hits": 0,
                         "reason": "Vault grounding is not connected to legal research. Use document review for an attached file."})
        elif sid in unavailable:
            u = unavailable[sid]
            rows.append({"id": sid, "tier": _tier(sid), "status": u["status"],
                         "outcome": "NOT_SEARCHED", "hits": 0, "reason": u["reason"]})
        else:
            rows.append({"id": sid, "tier": _tier(sid), "status": _sp.AVAILABLE,
                         "outcome": "NOT_SEARCHED", "hits": 0,
                         "reason": "available, but ask searches the held corpus; "
                                   "use sources.search for this source"})
    return {"picked": list(picked_ids), "searched": searched, "report": rows,
            "note": ("searched-empty is not not-searched: an empty search ran; a not-searched "
                     "source did not. Only HELD rows can make an answer VERIFIED.")}


# ── F2: research.multi, the multi-body path ───────────────────────────────────
#
# A dedicated verb, NOT a branch inside `ask`: `conversation.send` calls `ask` and derives
# its body table from `ask`'s shape via `_bodies_from_ask` (which re-reads `ask_scope`, a
# body-level authority with no per-State notion), so re-shaping `ask` for a compound,
# per-State question would break that contract. `research.multi` is its own verb on the one
# table (REST, MCP-read, CLI) and leaves `ask`/`conversation.send` untouched.
#
# `agents/multi_supervisor` is the orchestrator. The held worker/verifier are its
# deterministic held-corpus stand-ins -- no model, no key, a real BYTE-MATCHED quote of the
# Companies Act. The served model that only PHRASES that quote is wired in B1; until then
# this serves the verified quote as-is and says so (ponytail: stand-in phrasing until
# Bedrock lands).

def _research_multi(args: dict, ctx: Context) -> dict:
    """A compound question answered body-by-body: one section per (body, State), own status.

    The supervisor plans one researcher per held (body, State), refuses the bodies we do not
    hold BY NAME, resolves a State topic with no date to NEED_FACT, and synthesises the held
    answers by code. The plan (workers, bodies, States) travels both in the response and, as
    one step per part, in the persisted run -- so `runs.trace` shows what was planned.
    """
    from agents import multi_supervisor as ms
    question = (args.get("question") or "").strip()
    if not question:
        return _refuse("BAD_REQUEST", "question is required")
    as_of = (args.get("as_of") or "").strip() or None
    # Source picker: the held bodies are researched only when the held corpus is picked
    # (default). Held not picked -> a no-op worker, so those parts come back NEEDS_LAWYER
    # rather than being answered from a source the caller excluded.
    from checker import source_picker as _sp
    _resolved = _sp.resolve(args.get("sources"))
    _held = _sp.HELD_ID in _resolved.searchable
    _worker = ms._held_researcher() if _held else (lambda _t: "")
    outcome = ms.research(question, as_of=as_of, worker=_worker,
                          verify=ms._byte_match_verify, merge=ms._code_merge,
                          budget=_ledger_for(ctx),
                          # This serving path still uses the deterministic held-corpus
                          # stand-in above; no provider call occurs. If it is replaced with
                          # a model worker, wire provider-reported usage here rather than
                          # retaining this explicit zero-cost declaration.
                          actual_cost=lambda _task, _result: 0.0)
    d = outcome.to_dict()

    # The plan, derived from the sections so the shape has one source of truth: a held worker
    # section is one the supervisor researched (ANSWERED / NEEDS_LAWYER); the rest are named
    # refusals (a body not held, or a missing fact).
    held_statuses = {ms.ANSWERED, "NEEDS_LAWYER"}
    workers, bodies, states = [], [], []
    for s in d["sections"]:
        if s["body"] not in bodies:
            bodies.append(s["body"])
        if s.get("state") and s["state"] not in states:
            states.append(s["state"])
        if s["status"] in held_statuses:
            workers.append({"body": s["body"], "state": s.get("state")})
    d["plan"] = {"workers": workers, "bodies": bodies, "states": states,
                 "researcher": ms.RESEARCHER}

    # The run that RECORDS the plan: one step per (body, State) so the trace shows what was
    # planned and what each part returned, not one opaque "research" step.
    steps = [{"capability": "intake", "status": "ANSWERED",
              "cost_note": f"multi-body: {len(bodies)} bodies, {len(states)} States"}]
    for s in d["sections"]:
        steps.append({"capability": f"research.{s['body']}", "status": s["status"],
                      "cost_note": f"{s.get('name') or s['body']} / "
                                   f"{s.get('state') or 'Central'}"})
    _held_ans = tuple(s for s in d["sections"] if s.get("status") == ms.ANSWERED) if _held else ()
    d["sources"] = _sources_report(args.get("sources"), _resolved, _held_ans, question, ctx)
    d["run_id"] = _persist_run(ctx, intent="research_multi", status=d["status"],
                               steps=steps, propositions=[])
    return d


def _sources_list(args: dict, ctx: Context) -> dict:
    """Every source, its tier, and whether it may be fetched — with the reason when not.

    The reason travels with the refusal on purpose. "no" on its own invites someone to try
    again with a different client; "robots: https://www.rbi.org.in BLOCKED HTTP 418" does
    not, and it is also the answer to "why has nobody built the RBI connector".
    """
    from checker.sources import terms
    from checker.sources.tiers import CLIENT, HELD, TIERS

    out = []
    for source_id in terms.SOURCE_IDS:
        rec = terms.record_for(source_id)
        fetch_ok, fetch_why = terms.may_fetch(source_id)
        cache_ok, cache_why = terms.may_cache(source_id)
        out.append({
            "source_id": source_id,
            "name": rec.name,
            "terms_url": rec.terms_url,
            "terms_read": rec.date_read or None,
            "robots": [{"origin": o.origin, "state": o.state, "http": o.http}
                       for o in rec.robots],
            "may_fetch": fetch_ok, "may_fetch_reason": fetch_why,
            "may_cache": cache_ok, "may_cache_reason": cache_why,
            "clauses": {c.topic: c.state for c in rec.clauses},
        })
    # The two adapters that exist. Neither needs a terms record and both say why.
    built_in = [{"source_id": "held", "name": "Companies Act 2013 (our corpus)",
                 "tier": HELD, "may_fetch": True,
                 "may_fetch_reason": "ours, hash-stamped; the only tier that can VERIFY"},
                {"source_id": "client", "name": "Your uploaded documents", "tier": CLIENT,
                 "may_fetch": True,
                 "may_fetch_reason": "the tenant's own document, under review"}]
    from checker import source_picker
    return {"tiers": list(TIERS), "adapters": built_in, "external": out,
            "fetchable": [r["source_id"] for r in out if r["may_fetch"]],
            "cacheable": [r["source_id"] for r in out if r["may_cache"]],
            # The @-sources picker view: one card per pickable source with its display tier
            # (HELD / LICENSED / PUBLIC), switchable status (available / KEY_MISSING /
            # NOT_ACQUIRED / BLOCKED, with the reason), and its terms record. An unavailable
            # source is listed here too, with switchable=false, so the UI can show it greyed.
            "picker": source_picker.listing(),
            # Document-management systems are not legal research sources. Keep their setup
            # state separate so choosing iManage never implies it was searched or that its
            # documents were copied into the Wall System.
            "integrations": [{
                "id": "imanage",
                "label": "iManage",
                "kind": "document_management",
                "status": "NOT_CONFIGURED",
                "message": ("A firm administrator must register and authorize Placedon in "
                            "iManage. No files have been imported."),
                "can_connect": False,
            }],
            "note": ("Only HELD can make an answer VERIFIED (PLAN_26 §2). External sources "
                     "are listed with what their own terms permit, read on the date shown; "
                     "an unread term is OPEN, and OPEN is not permission.")}


def _sources_search(args: dict, ctx: Context) -> dict:
    """Search the loadable sources and return Evidence rows, each carrying its tier.

    Today that is HELD and CLIENT. The five external sources S0 recorded either refuse us
    by robots or have unread terms, so there is nothing to call — and this returns the
    empty list with the reasons rather than pretending the sources do not exist.
    """
    from checker.sources.base import load
    from checker.sources.client import ClientDocuments
    from checker.sources.evidence import verifying
    from checker.sources.held import AsOfUnsupported, HeldCorpus
    from checker.sources.tiers import label_for
    from checker import source_picker

    query = (args.get("query") or "").strip()
    if not query:
        return _refuse("BAD_REQUEST", "query is required")
    wanted = args.get("tiers") or None
    as_of = (args.get("as_of") or "").strip() or None

    rows, refusals = [], []
    for src in (HeldCorpus(), ClientDocuments(ctx.documents)):
        if wanted and src.tier not in wanted:
            continue
        try:
            rows.extend(load(src).search(query, as_of=as_of))
        except AsOfUnsupported as exc:
            # A named refusal, not a silent fallback to current text. CLAUDE.md:
            # point-in-time reconstruction is UNVERIFIED against any external source.
            return _refuse("AS_OF_UNSUPPORTED", str(exc))
        except Exception as exc:                      # a connector that cannot load
            refusals.append({"source_id": getattr(src, "source_id", "?"),
                             "detail": str(exc)})
    from checker.sources import terms
    for source_id in terms.SOURCE_IDS:
        ok, why = terms.may_fetch(source_id)
        if not ok:
            refusals.append({"source_id": source_id, "detail": why})
    lexis = source_picker.source(source_picker.LEXIS_ID)
    refusals.append({"source_id": lexis.id, "detail": lexis.reason})

    # ── judgment DISCOVERY: find a case by a generic query (parties/title/year) ──────────
    # Reads the committed local index only -- no network -- so the gate stays socket-free.
    # These are candidates to OPEN, not Evidence: there is no quote until the PDF is fetched
    # and byte-quoted by judgments_open.OpenJudgments. Tier LICENSED: a judgment may SUPPORT
    # an answer and can never make one VERIFIED. Metadata search is by PARTY/TITLE, not topic.
    judgments: list[dict] = []
    if not wanted or "LICENSED" in wanted:
        from checker.sources.judgment_index import (
            discover as _discover, indexed_source_ids as _indexed, JUDGMENT_SOURCE_IDS)
        permitted = {sid for sid in JUDGMENT_SOURCE_IDS if terms.may_fetch(sid)[0]}
        for ref in _discover(query, limit=10):
            if ref.source_id in permitted:
                judgments.append({
                    "source_id": ref.source_id, "title": ref.title,
                    "parties": list(ref.parties), "year": ref.year, "date": ref.date,
                    "court": ref.court, "s3_key": ref.s3_key, "tier": "LICENSED"})
        # A permitted judgment source with no rows yet is said so, not silently omitted.
        for sid in sorted(permitted - _indexed()):
            refusals.append({"source_id": sid, "detail": (
                "permitted, but its judgment index is not built yet (Supreme Court only in "
                "this release)")})

    return {
        "query": query,
        "results": [{"tier": e.tier, "source": e.source, "ref": e.ref,
                     "fetched_at": e.fetched_at, "sha256": e.sha256,
                     "quoted_span": e.quoted_span, "attribution": e.attribution,
                     "label": label_for(e.tier, date=e.fetched_at[:10], source=e.source),
                     "can_verify": e.can_verify} for e in rows],
        "verified_count": len(verifying(rows)),
        "judgments": judgments,
        "not_searched": refusals,
        "note": ("Every row carries its tier. Only a HELD row may support a legal claim; "
                 "`judgments` are LICENSED case-law candidates found by party/title (open one "
                 "to read its verbatim passage); `not_searched` says which sources were not "
                 "asked and why."),
    }


def _research_cases(args: dict, ctx: Context) -> dict:
    """Find case law by a generic query -- party or case name, year, court.

    The surface for "just write what you're looking for" over judgments. Tier LICENSED: a
    judgment may SUPPORT an answer and can NEVER make one VERIFIED, and this verb produces NO
    obligation (the scope.py invariant holds -- it serves authorities, not findings). Discovery
    is by PARTY/TITLE metadata, not legal topic; the verbatim passage is read on OPEN via
    judgments_open.OpenJudgments, never here. Reads the local index only -- no network.
    """
    from checker.sources.judgment_index import discover, indexed_source_ids, JUDGMENT_SOURCE_IDS
    from checker.sources import terms

    query = (args.get("query") or "").strip()
    if not query:
        return _refuse("BAD_REQUEST", "query is required")
    permitted = {sid for sid in JUDGMENT_SOURCE_IDS if terms.may_fetch(sid)[0]}
    hits = [r for r in discover(query, limit=20) if r.source_id in permitted]
    not_searched = []
    for sid in sorted(set(JUDGMENT_SOURCE_IDS) - permitted):
        ok, why = terms.may_fetch(sid)
        not_searched.append({"source_id": sid, "detail": why})
    for sid in sorted(permitted - indexed_source_ids()):
        not_searched.append({"source_id": sid, "detail": (
            "permitted, but its judgment index is not built yet (Supreme Court only in "
            "this release)")})
    return {
        "query": query,
        "judgments": [{"source_id": r.source_id, "title": r.title, "parties": list(r.parties),
                       "year": r.year, "date": r.date, "court": r.court, "s3_key": r.s3_key,
                       "tier": "LICENSED"} for r in hits],
        "not_searched": not_searched,
        "note": ("Case-law candidates found by party/title/year. LICENSED: supporting "
                 "authority only -- never a verified statutory answer and never an "
                 "obligation. Open one to read its verbatim passage. Search is by party or "
                 "case name, not legal topic."),
    }


def _research_web(args: dict, ctx: Context) -> dict:
    """Opt-in general web answer, separate from held-law and live docket workflows."""
    from checker import public_web

    query = args.get("query")
    mode = args.get("mode")
    consent = args.get("external_search_consent") is True
    return public_web.search(query, mode=mode, consent=consent)


# ── Lane B: a predictive signal, never a legal decision ───────────────────────

def _forecast_summary(args: dict, ctx: Context) -> dict:
    """Time-to-decision for Companies Act matters at a forum, as a PREDICTIVE_SIGNAL.

    Reads the committed Companies Act matters dataset (built from the open judgment metadata),
    counts the matters still PENDING as censored, and reads a Kaplan-Meier median with its
    interval and n -- or ABSTAINS, by name, when too few matters have been decided there. No
    model is called; `checker.forecast` is Ring 3 (INFERENCE) and the rings firewall forbids any
    Ring 0 decider from receiving this value. The result is labelled predictive_signal and
    carries the case ids behind it.
    """
    from checker.forecast import matters as fm
    court = (args.get("court") or "").strip()
    if not court:
        return _refuse("BAD_REQUEST", "court is required, e.g. 'Bombay High Court'")
    as_of = (args.get("as_of") or "").strip() or _today(ctx)
    not_legal = ("A predictive signal from past matters, not advice and not a statement of "
                 "law. It cannot decide your matter.")
    ds = fm.load()
    # SYNTHETIC data must never feed a user-visible number. Until a real pull writes a
    # non-synthetic dataset, this abstains by name rather than dress a fixture as a measurement.
    if ds.synthetic:
        return {"status": "ABSTAINED", "label": "predictive_signal", "court": court,
                "estimate": None, "n_total": 0, "n_timeable": 0, "events": 0, "case_ids": [],
                "as_of": as_of, "synthetic": True,
                "reason": ("the Companies Act matters dataset is SYNTHETIC (illustrative rows, "
                           "not the licensed open data), so no estimate is served from it. Pull "
                           "the real open judgment metadata with "
                           "scripts/build_companies_act_matters.py --build (needs the pyarrow "
                           "parquet engine) first."),
                "not_legal_advice": not_legal}
    known = {m.court.strip().lower(): m.court for m in ds.matters}
    canonical = known.get(court.lower())
    if canonical is None:
        return {"status": "ABSTAINED", "label": "predictive_signal", "court": court,
                "estimate": None, "n_total": 0, "n_timeable": 0, "events": 0, "case_ids": [],
                "as_of": as_of,
                "reason": (f"no Companies Act matters for {court!r} in the dataset; "
                           f"known forums: {sorted(set(known.values()))}"),
                "not_legal_advice": not_legal}
    out = fm.time_to_decision(ds.matters, court=canonical, as_of=as_of).to_dict()
    out["as_of"] = as_of
    out["not_legal_advice"] = ("A predictive signal from past matters, not advice and not a "
                               "statement of law. It cannot decide your matter.")
    return out
