"""`POST /v1/ask` — one turn of the Ask surface, answered from deterministic calls alone.

`answer(request)` returns a `placedon.ask/0` response (contract:
`web/assistant/contract.md`, validator `scripts/assistant_contract.py`). Every field in it
is produced by an engine module that decides by lookup: retrieval and the evidence pack,
the prescribed-threshold table, the scope register, the obligation register through
`api.compliance_pack`, and the document currency check through `api.document_check`.

**No model is called here, and none can be.** `uses_model` is `False` on every response and
the test asserts the module imports no model or network library. That is not a limitation
waiting to be lifted: `answered` is only truthful from a deterministic path today, because
`claim_verifier` never returns SUPPORTED (contract §3).

## What this module will not do

It does not read the question. A deterministic engine cannot know which provision a
sentence means, and guessing would put a citation under words nobody asked us to
interpret — the Act-versus-Rule collision `checker/retrieve.py` exists to prevent. So the
request may NAME what it wants read (`provisions`, `figures`), each validated against what
the engine declares; where it names nothing, retrieval runs on the user's own words and
`retrieve()` decides the route, which is the only record of what was tried (UX spec §7.12).

The one thing the question itself decides is **scope** (`checker/ask_scope.py`, contract §6
D2): a question that names a body of law `checker/scope.py` declares and does not hold is
refused in the register's own words; one that names such a body next to held law is MIXED —
the held part is read and the unheld part refused. A wrong refusal of held law is the worse
error, so the held Act's own vocabulary never refuses. A body the register does not declare is
NOT out_of_scope — there is no refusal text to serve and writing one would be inventing law.

Run: PYTHONPATH=. python3 checker/ask.py
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):                      # run as a file by scripts/run_tests.sh
    sys.path.insert(0, str(ROOT))

from checker import ask_scope, obligations
from checker import prescribed_thresholds as pt
from checker import scope
from checker.api import BadRequest, _date, document_check
from checker.provenance_slots import USER_FACT
from checker.retrieve import retrieve

SCHEMA = "placedon.ask/0"
ANSWERED, PARTIAL, OUT_OF_SCOPE = "answered", "partial", "out_of_scope"

# Everything a request may carry. Unknown keys are refused rather than ignored, for the
# reason document_check gives: a mistyped field silently changes the answer.
REQUEST_KEYS = frozenset({"question", "context", "facts", "figures", "provisions",
                          "as_of", "parent_turn_id"})
CONTEXT_KEYS = frozenset({"kind", "document_date"})

# Supplied facts that place the company in time rather than decide anything about it. They
# are USED (the profile cannot be built without them) and not echoed as facts: the envelope
# already carries as_of, and every row carries the financial year its figures are bound to.
FRAME_FACTS = frozenset({"as_of", "incorporation_date", "financial_year"})

# The engine's own statement when a turn reached nothing. It is a statement about what this
# system did, never about the law: "we decided nothing" is not "nothing applies".
NOTHING_DECIDED = ("no obligation row, prescribed figure or admitted provision was reached "
                   "for this question. That is a statement about what this system read, not "
                   "a finding that no obligation applies")
NOTHING_REACHED = ("the document check reached no obligation in the register, so nothing "
                   "about this document was verified or flagged")


# ── the envelope ──────────────────────────────────────────────────────────────
def _turn_id(question: str, as_of: str, kind: str, document_date: str | None) -> str:
    """Stable for the same question at the same date. No clock, no randomness — a rebuilt
    fixture and a live response for the same turn carry the same id."""
    return "t_" + hashlib.sha256(
        f"{question}|{as_of}|{kind}|{document_date}".encode()).hexdigest()[:12]


def _envelope(question: str, *, as_of: str, generated_at: str, kind: str,
              document_date: str | None, parent: str | None) -> dict:
    env = {"schema": SCHEMA, "turn_id": _turn_id(question, as_of, kind, document_date),
           "question": question, "generated_at": generated_at, "as_of": as_of,
           "context": {"kind": kind, "document_date": document_date}, "uses_model": False,
           "scope": {"held": [b.name for b in scope.in_corpus()],
                     "sentence": scope.coverage()}}
    if parent is not None:
        env["parent_turn_id"] = parent
    return env


def _as_json(v):
    """What the engine returned, in JSON types. A tuple becomes a list; a string stays a
    string -- list() on a string is how a sentence becomes 455 characters."""
    return list(v) if isinstance(v, tuple) else v


# ── engine readers ────────────────────────────────────────────────────────────
def _pack(query: str) -> tuple[dict, str]:
    pack, route = retrieve(query)
    return pack.to_dict(), route


def _citation(p: dict) -> dict:
    return {"ref": p["ref"], "cite": p["cite"], "title": p["title"],
            "evidence_state": p["evidence_state"],
            "usable_for_answering": p["usable_for_answering"],
            "unusable_reason": p["unusable_reason"] or None,
            "defects": p["defects"],
            "retrieved_on": sorted({s["retrieved_on"] for s in p["sources"]
                                    if s.get("retrieved_on")}),
            "source_url": next((s["source_url"] for s in p["sources"]
                                if s.get("source_url")), None)}


def _law_version(d: dict) -> dict:
    a = d["as_of"]
    return {k: a[k] for k in ("basis", "point_in_time_verified", "corpus_fetched",
                              "statement")}


def _law_version_at(provisions: list[str], requested: str) -> dict:
    """The engine's own basis statement for a past date, over the provisions a turn cites.

    Built by evidence_pack's statement builder, never written here: it is the sentence that
    says no statement is about the law as it stood on that date.
    """
    from checker import evidence_pack
    sections = sorted({m for p in provisions for m in re.findall(r"s\.(\d+[A-Z]?)", p)},
                      key=lambda x: (int(re.match(r"\d+", x).group()), x))
    pack, _ = _pack(" and ".join(f"s.{n}" for n in sections))
    fetched = tuple(pack["as_of"]["corpus_fetched"])
    a = evidence_pack._build_as_of(fetched, date.fromisoformat(requested)).to_dict()
    return {k: a[k] for k in ("basis", "point_in_time_verified", "point_in_time_requested",
                              "corpus_fetched", "statement")}


def _pack_summary(d: dict, route: str) -> dict:
    return {"retrieval_query": d["query"], "route": route, "usable_keys": d["usable_keys"],
            "unusable_keys": d["unusable_keys"], "missing": d["missing"],
            "insufficient_evidence": d["insufficient_evidence"]}


def _figure(key: str, as_of: date) -> dict:
    t = pt.lookup(key, as_of)
    return {"key": key, "amount": str(t.amount), "rupees": t.amount.rupees,
            "instrument": t.instrument, "effective_from": t.effective_from.isoformat(),
            "effective_to": t.effective_to.isoformat() if t.effective_to else None,
            "evidence_state": t.state, "source_url": t.source_url}


def _cites(provision: str, cite: str) -> bool:
    """Does this obligation's provision name the citation the request asked to read?
    The lookahead keeps s.16 out of s.186 -- a provision number is never a prefix."""
    return re.search(rf"{re.escape(cite)}(?![0-9])", provision, re.I) is not None


# ── the two answering paths ───────────────────────────────────────────────────
def _general_turn(question: str, *, as_of: date, generated_at: str, facts: dict | None,
                  provisions: list[str], figures: list[str],
                  refusal: dict | None = None) -> dict:
    """Retrieval, the threshold table and the obligation register, over one question.

    `refusal` is set on a MIXED turn (D2): the question also names an unheld body by its
    title. The held part is read; the unheld part is refused in the register's words; and
    no row is decided, because a row would be Companies Act reasoning applied to a matter
    the unheld body may govern -- an LLP is not a company.
    """
    not_confirmed: list[dict] = [refusal] if refusal else []
    served: list[dict] = []
    for key in figures:
        try:
            served.append(_figure(key, as_of))
        except pt.ThresholdUnavailable as e:
            # A prescribed amount we are not willing to serve is a refusal that says why,
            # in the table's own words. It is never replaced by the statutory floor.
            not_confirmed.append({"kind": "cannot_verify", "ref": key, "detail": str(e)})

    # What was read. Where the request named provisions, they are the query; otherwise the
    # user's own words are, and retrieve() decides the route -- the only record of what was
    # tried, which the client renders as "Looked up …".
    pack, route = _pack(" and ".join(provisions) if provisions else question)

    rows: list[dict] = []
    fact_block: dict = {}
    what_it_is_not = None
    if facts is not None and refusal is None:
        from checker.api import compliance_pack
        pack_json = compliance_pack({"as_of": as_of.isoformat(), **facts},
                                    generated_at=generated_at)
        what_it_is_not = _as_json(pack_json["what_it_is_not"])
        fact_block = {k: {"value": v, "provenance": USER_FACT}
                      for k, v in facts.items() if k not in FRAME_FACTS}
        for row in pack_json["rows"]:
            if provisions and not any(_cites(row["provision"], c) for c in provisions):
                continue                       # not the obligation this turn is about
            if (row["missing_facts"] or row["blocked_by"]
                    or row["state"] in (obligations.APPLIES_UNDETERMINED,
                                        obligations.CANNOT_DETERMINE)):
                not_confirmed.append({"kind": "cannot_verify", "ref": row["obligation_id"],
                                      "duty": row["duty"], "provision": row["provision"],
                                      "detail": row["basis"],
                                      "missing_facts": row["missing_facts"],
                                      "blocked_by": row["blocked_by"]})
            else:
                rows.append(row)

    not_confirmed += [{"kind": "pack_missing", "detail": m} for m in pack["missing"]]
    not_confirmed += [{"kind": "unusable", "ref": p["ref"], "reason": p["unusable_reason"],
                       "defects": p["defects"]}
                      for p in pack["provisions"] if not p["usable_for_answering"]]

    out: dict = {"state": ANSWERED if (served or rows) and not not_confirmed else PARTIAL}
    if fact_block:
        out["facts"] = fact_block
    if rows:
        out["rows"] = rows
    if served:
        out["figures"] = served
    if out["state"] == ANSWERED:
        out["citations"] = [_citation(p) for p in pack["provisions"]]
    else:
        out["confirmed"] = [_citation(p) | {"verbatim": p["reading_text"]}
                            for p in pack["provisions"] if p["usable_for_answering"]]
        out["not_confirmed"] = not_confirmed or [{"kind": "cannot_verify",
                                                  "detail": NOTHING_DECIDED}]
        if out["confirmed"] and not_confirmed:
            out["demand_signal"] = {"action": "tell_us_blocking"}
    out["law_version"] = _law_version(pack)
    out["evidence_pack"] = _pack_summary(pack, route)
    if what_it_is_not is not None:
        out["what_it_is_not"] = what_it_is_not
    return out


def _document_turn(check: dict) -> dict:
    """The state-bearing fields of a document turn, from one document_check result.

    Pure, so the branches the register cannot currently reach are still tested rather
    than left undefined.
    """
    verified, superseded = check["verified"], check["superseded"]
    cannot = check["cannot_verify"]
    out = {"superseded": superseded, "scope_frame": check["coverage"],
           # Red team L2: document_check reports Act-only rows CURRENT by construction,
           # against the CURRENT consolidation. The turn carries the engine's statement
           # for the document's own date so that cannot be read as the law in that year.
           "law_version": _law_version_at(
               [x.get("provision", "") for x in verified + cannot + superseded],
               check["document_date"]),
           "what_it_is_not": _as_json(check["what_it_is_not"])}
    if cannot:
        return out | {"state": PARTIAL, "confirmed": verified,
                      "not_confirmed": [{"kind": "cannot_verify"} | item for item in cannot]}
    if verified:
        # Everything the check reached was placed: current, or moved and listed as moved.
        return out | {"state": ANSWERED, "rows": verified}
    if superseded:
        return out | {"state": PARTIAL, "confirmed": [],
                      "not_confirmed": [{"kind": "cannot_verify", "ref": s["obligation_id"],
                                         "duty": s["duty"], "provision": s["provision"],
                                         "detail": s["detail"]} for s in superseded]}
    return out | {"state": PARTIAL, "confirmed": [],
                  "not_confirmed": [{"kind": "cannot_verify", "detail": NOTHING_REACHED}]}


def _with_refusal(turn: dict, item: dict) -> dict:
    """A document turn that also named an unheld body by title: never answered."""
    if turn["state"] == ANSWERED:
        turn = ({k: v for k, v in turn.items() if k != "rows"}
                | {"state": PARTIAL, "confirmed": turn["rows"], "not_confirmed": []})
    return turn | {"not_confirmed": turn["not_confirmed"] + [item]}


# ── the request ───────────────────────────────────────────────────────────────
def _strings(request: dict, key: str) -> list[str]:
    v = request.get(key)
    if v is None:
        return []
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise BadRequest(f"{key!r} must be a list of non-empty strings")
    return list(v)


def answer(request: dict, *, generated_at: str) -> dict:
    """One `placedon.ask/0` turn, from deterministic engine calls only.

    Request:
        {"question":  the user's words, rendered verbatim and never parsed for meaning,
         "context":   {"kind": "general" | "document", "document_date": ISO},
         "as_of":     ISO date; defaults to the day in `generated_at`,
         "facts":     general -> what /v1/compliance-pack takes;
                      document -> what /v1/document-check takes,
         "provisions": citations to read, e.g. ["s.173", "s.16"],
         "figures":   prescribed-threshold keys, e.g. ["small_company.turnover.prescribed"],
         "parent_turn_id": the turn this follows}

    Raises BadRequest on anything malformed. Everything else propagates: an engine or
    transport failure is NOT a legal state and must never reach a client wearing one
    (CLAUDE.md; the frontend's AGENTS.md:62).
    """
    if not isinstance(request, dict):
        raise BadRequest("request body must be a JSON object")
    unknown = set(request) - REQUEST_KEYS
    if unknown:
        raise BadRequest(f"unknown field(s): {', '.join(sorted(unknown))}. "
                         f"Known: {', '.join(sorted(REQUEST_KEYS))}")
    question = request.get("question")
    if not isinstance(question, str) or not question.strip():
        raise BadRequest("missing required field: 'question'")

    ctx = request.get("context") or {}
    if not isinstance(ctx, dict):
        raise BadRequest("'context' must be an object")
    unknown = set(ctx) - CONTEXT_KEYS
    if unknown:
        raise BadRequest(f"unknown field(s) in context: {', '.join(sorted(unknown))}")
    kind = ctx.get("kind") or "general"
    if kind not in ("general", "document"):
        raise BadRequest(f"context.kind must be general or document, got {kind!r}")

    as_of = _date(request, "as_of") or date.fromisoformat(generated_at[:10])
    facts = request.get("facts")
    if facts is not None and not isinstance(facts, dict):
        raise BadRequest("'facts' must be an object")
    if facts and facts.get("as_of") and facts["as_of"] != as_of.isoformat():
        raise BadRequest(f"facts.as_of ({facts['as_of']!r}) contradicts the turn's as_of "
                         f"({as_of.isoformat()!r})")
    provisions, figures = _strings(request, "provisions"), _strings(request, "figures")
    declared = {t.key for t in pt.all_thresholds()}
    for key in figures:
        if key not in declared:
            raise BadRequest(f"no prescribed figure is keyed {key!r}. This engine serves "
                             f"only what it declares: {', '.join(sorted(declared))}")
    parent = request.get("parent_turn_id")
    if "parent_turn_id" in request and (not isinstance(parent, str) or not parent.strip()):
        raise BadRequest("a follow-up must name the turn it follows")

    document_date = None
    if kind == "document":
        in_ctx, in_facts = ctx.get("document_date"), (facts or {}).get("document_date")
        if in_ctx and in_facts and in_ctx != in_facts:
            raise BadRequest(f"context.document_date ({in_ctx!r}) contradicts "
                             f"facts.document_date ({in_facts!r})")
        document_date = in_ctx or in_facts
        if not document_date:
            raise BadRequest("missing required date: 'context.document_date' — a document "
                             "turn is read against the date the document was made")
        _date({"document_date": document_date}, "document_date", required=True)
        if provisions or figures:
            raise BadRequest("'provisions' and 'figures' are read on the general path; a "
                             "document turn is decided by the currency check")
    elif ctx.get("document_date"):
        raise BadRequest("a document_date belongs to a document-context turn")

    env = _envelope(question, as_of=as_of.isoformat(), generated_at=generated_at, kind=kind,
                    document_date=document_date, parent=parent)

    # Scope first (D2). A question about law we do not hold is refused in the register's own
    # words -- silence there would read as "no obligation found". A question that ALSO names
    # held law is mixed: the held part is read and the unheld part refused, not the whole.
    reading = ask_scope.read(question, provisions)
    if reading.refuse:
        body = reading.body
        return env | {"state": OUT_OF_SCOPE,
                      "body": {"key": body.key, "name": body.name,
                               "regulator": body.regulator, "covers": body.covers,
                               "scope_status": body.status},
                      "reason": scope.refusal_for(body.key),
                      "held": [b.name for b in scope.in_corpus()]}
    refusal = ({"kind": "cannot_verify", "ref": reading.body.key,
                "detail": scope.refusal_for(reading.body.key)} if reading.mixed else None)

    if kind == "document":
        if not isinstance(facts, dict):
            raise BadRequest("a document turn takes the /v1/document-check fields as 'facts'")
        check = document_check({**facts, "document_date": document_date,
                                "as_of": as_of.isoformat()}, generated_at=generated_at)
        turn = _document_turn(check)
        return env | (_with_refusal(turn, refusal) if refusal else turn)

    return env | _general_turn(question, as_of=as_of, generated_at=generated_at, facts=facts,
                               provisions=provisions, figures=figures, refusal=refusal)

def _contract_validator():
    """The contract validator, loaded from the file it lives in.

    `validate()` lives beside the contract prose in scripts/assistant_contract.py, which is
    not an importable package. Loading it by path here keeps ONE validator: a second copy in
    the package would drift from the contract it is supposed to enforce. Test-only.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "assistant_contract", ROOT / "scripts" / "assistant_contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate


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

    print("ask")
    from checker import api
    validate = _contract_validator()
    GEN = "2026-09-15T00:00:00Z"
    AS_OF = "2026-09-15"
    FACTS = {"company_class": "private", "incorporation_date": "2019-06-01",
             "as_of": AS_OF, "financial_year": "2025-26",
             "paid_up_capital_rupees": 120000000, "turnover_rupees": 800000000}
    CAP = "small_company.paid_up_capital.prescribed"
    TURN = "small_company.turnover.prescribed"
    served = []

    def ask(req: dict) -> dict:
        r = answer(req, generated_at=GEN)
        served.append(r)
        return r

    # ── answered: a deterministic row and servable figures ───────────────────
    a = ask({"question": "Is this company a small company?", "as_of": AS_OF,
             "context": {"kind": "general"}, "facts": FACTS,
             "provisions": ["s.2(85)"], "figures": [CAP, TURN]})
    check(a["state"] == ANSWERED and validate(a) == [],
          f"a row plus servable figures is answered, and it validates "
          f"({a['state']}, {validate(a)})")
    check([r["obligation_id"] for r in a["rows"]] == ["CA13-S2-85-SMALL"],
          f"...serving the row the named provision decides, not the whole register "
          f"({[r['obligation_id'] for r in a['rows']]})")
    check([f["key"] for f in a["figures"]] == [CAP, TURN]
          and a["figures"][0]["instrument"] == pt.lookup(CAP, date.fromisoformat(AS_OF)).instrument,
          "...and the figures are the engine's thresholds, named by the request")
    check(a["evidence_pack"]["retrieval_query"] == "s.2(85)",
          f"...read against the provision the request named ({a['evidence_pack']['retrieval_query']})")
    check("not_confirmed" not in a and "confirmed" not in a,
          "an answered turn carries citations, not a confirmed/not-confirmed split")

    # ── facts are used only as supplied ──────────────────────────────────────
    check(sorted(a["facts"]) == ["company_class", "paid_up_capital_rupees", "turnover_rupees"]
          and all(v["provenance"] == "USER_FACT" for v in a["facts"].values())
          and a["facts"]["turnover_rupees"]["value"] == FACTS["turnover_rupees"],
          f"the facts block echoes the supplied values verbatim, labelled USER_FACT "
          f"({sorted(a['facts'])})")
    no_figures = {k: v for k, v in FACTS.items()
                  if k not in ("paid_up_capital_rupees", "turnover_rupees")}
    b = ask({"question": "Is this company a small company?", "as_of": AS_OF,
             "facts": no_figures, "provisions": ["s.2(85)"], "figures": [CAP, TURN]})
    check(b["state"] == PARTIAL and "turnover_rupees" not in b.get("facts", {})
          and "rows" not in b,
          f"a figure that was not supplied is not invented -- the row cannot be decided "
          f"and the turn goes partial ({b['state']})")
    item = next((i for i in b["not_confirmed"] if i.get("ref") == "CA13-S2-85-SMALL"), None)
    check(item is not None and item["missing_facts"] and validate(b) == [],
          f"...and it is named as not confirmed, with the facts it needed "
          f"({(item or {}).get('missing_facts')}, {validate(b)})")

    # ── partial: something read, something not ───────────────────────────────
    p = ask({"question": "What does s.173 require, and does s.16 apply here?",
             "as_of": AS_OF, "provisions": ["s.173", "s.16"]})
    check(p["state"] == PARTIAL and validate(p) == [], f"a mixed pack is partial ({validate(p)})")
    check([c["ref"] for c in p["confirmed"]] == ["ACT:COMPANIES_ACT_2013:S173"]
          and p["confirmed"][0]["verbatim"],
          "...the admitted provision is confirmed, with the text that was read")
    check(p["not_confirmed"] and all(i["kind"] in ("pack_missing", "unusable", "cannot_verify")
                                     for i in p["not_confirmed"]),
          f"...and what was not admitted is not confirmed, by a kind the client renders "
          f"({[i['kind'] for i in p['not_confirmed']]})")

    # ── partial with nothing confirmed, and partial is never empty-handed ────
    n = ask({"question": "What does rule 2(1)(t) prescribe?", "as_of": AS_OF,
             "provisions": ["rule 2(1)(t)"]})
    check(n["state"] == PARTIAL and n["confirmed"] == [] and n["not_confirmed"]
          and validate(n) == [], f"an abstained retrieval is a partial with nothing "
                                 f"confirmed ({n['state']}, {validate(n)})")
    bare = ask({"question": "Hello", "as_of": AS_OF})
    check(bare["state"] == PARTIAL and bare["not_confirmed"] and validate(bare) == [],
          f"a turn that reached nothing still says so -- a partial is never empty-handed "
          f"({validate(bare)})")

    # ── out_of_scope, in the register's own words ────────────────────────────
    o = ask({"question": "What must we report to RBI for this share allotment to a "
                         "foreign investor?", "as_of": AS_OF})
    check(o["state"] == OUT_OF_SCOPE and o["body"]["key"] == "FEMA1999"
          and validate(o) == [], f"a question naming RBI is refused as FEMA ({o['state']})")
    check(o["reason"] == scope.refusal_for("FEMA1999"),
          "...in scope.refusal_for's words, never copy written here")
    check(o["held"] == [b.name for b in scope.in_corpus()],
          "...and it names what we do hold")
    # D2 (fix round 1): a declared body's title named next to held law is MIXED -- the
    # held part is read, the unheld part refused in the register's words, and no row is
    # decided, because a row about an LLP would be Companies Act reasoning applied to it.
    both = ask({"question": "Is our LLP a small company?", "as_of": AS_OF, "facts": FACTS,
                "provisions": ["s.2(85)"], "figures": [CAP, TURN]})
    refusal = [i for i in both.get("not_confirmed", []) if i.get("ref") == "LLP2008"]
    check(both["state"] == PARTIAL and "rows" not in both and validate(both) == [],
          f"an LLP question is never answered as a company, even with facts and a "
          f"Companies Act provision named ({both['state']}, rows={'rows' in both})")
    check(refusal and refusal[0]["detail"] == scope.refusal_for("LLP2008")
          and "facts" not in both,
          "...the LLP limb is refused in scope.refusal_for's words, and the facts are "
          "not applied to anything")
    mixed = ask({"question": "Does s.173 apply to a Limited Liability Partnership Act "
                             "entity?", "as_of": AS_OF, "provisions": ["s.173"]})
    check(mixed["state"] == PARTIAL
          and [c["ref"] for c in mixed["confirmed"]] == ["ACT:COMPANIES_ACT_2013:S173"]
          and any(i.get("ref") == "LLP2008" for i in mixed["not_confirmed"]),
          f"...and the held provision the request named is still read, not refused with "
          f"the rest ({mixed['state']})")

    # ── the held Act's own vocabulary is never refused (verifier finding 1) ──
    for q in ("Which MCA form do we file after the AGM under s.137?",
              "Do we need NCLT approval to reduce share capital under section 66?",
              "What are the board composition rules under s.149 for a private company?",
              "What are our annual filings under the Companies Act, 2013?",
              "Does a further issue of capital need a special resolution under s.62?",
              "Must our Internal Committee report under the s.177 vigil mechanism?"):
        r = ask({"question": q, "as_of": AS_OF})
        check(r["state"] != OUT_OF_SCOPE and "reason" not in r and validate(r) == [],
              f"not refused: {q[:56]!r} ({r['state']})")

    # ── an undeclared body is NOT out_of_scope ───────────────────────────────
    tax = ask({"question": "How much TDS must we deduct under the Income-tax Act on this "
                           "payment?", "as_of": AS_OF})
    check(tax["state"] != OUT_OF_SCOPE and "body" not in tax and "reason" not in tax,
          f"a body the register does not declare is not refused -- there is no refusal "
          f"text to serve, and writing one would be inventing law ({tax['state']})")
    check(validate(tax) == [], f"...and the turn it does return validates ({validate(tax)})")

    # ── the document path ────────────────────────────────────────────────────
    doc_facts = {"document_date": "2024-06-01", "as_of": AS_OF, "company_class": "private",
                 "incorporation_date": "2019-06-01", "financial_year": "2023-24",
                 "paid_up_capital_rupees": 30000000, "turnover_rupees": 300000000}
    d = ask({"question": "Is the law this document relies on still current?", "as_of": AS_OF,
             "context": {"kind": "document", "document_date": "2024-06-01"},
             "facts": doc_facts})
    check(d["state"] == PARTIAL and validate(d) == [],
          f"a 2024 document with an obligation we cannot verify is partial ({validate(d)})")
    check(d["law_version"]["point_in_time_requested"] == "2024-06-01"
          and d["law_version"]["point_in_time_verified"] is False,
          "...carrying the engine's basis statement for the document's own date (L2)")
    check(any(s["obligation_id"] == "CA13-S2-85-SMALL" for s in d["superseded"]),
          "...and the basis that moved under it")
    check("evidence_pack" not in d,
          "...with no evidence pack, because the document path runs no retrieval")
    undated = {k: v for k, v in doc_facts.items() if k != "document_date"}
    try:
        answer({"question": "Is this still current?",
                "context": {"kind": "document"}, "facts": undated}, generated_at=GEN)
        check(False, "a document turn without a date is refused")
    except BadRequest as e:
        check("document_date" in str(e), f"a document turn without a date is refused ({e})")

    # A check that verified everything and flagged nothing: unreachable with the register
    # as it stands, so it is exercised on the pure assembler rather than left undefined.
    clean = dict(document_check(doc_facts, generated_at=GEN),
                 superseded=[], cannot_verify=[])
    env = _envelope("Is this document's law current?", as_of=AS_OF, generated_at=GEN,
                    kind="document", document_date="2024-06-01", parent=None)
    whole = env | _document_turn(clean)
    check(whole["state"] == ANSWERED and whole["rows"] and validate(whole) == [],
          f"a document check that flags nothing is answered, on its rows ({validate(whole)})")
    empty = env | _document_turn(dict(clean, verified=[]))
    check(empty["state"] == PARTIAL and empty["not_confirmed"] and validate(empty) == [],
          f"...while one that reached nothing says that, and is not an answer "
          f"({validate(empty)})")

    # ── a follow-up names the turn it follows ────────────────────────────────
    f = ask({"question": "And the turnover limit?", "as_of": AS_OF, "figures": [TURN],
             "provisions": ["s.2(85)"], "parent_turn_id": a["turn_id"]})
    check(f["parent_turn_id"] == a["turn_id"] and f["state"] == ANSWERED
          and validate(f) == [], f"a follow-up carries its parent and validates ({validate(f)})")
    check(_turn_id("And the turnover limit?", AS_OF, "general", None) == f["turn_id"],
          "a turn id is derived from the turn, so the same question at the same date "
          "rebuilds to the same id")

    # ── an unheld figure is a refusal, never a number ────────────────────────
    with pt.none_acquired():
        u = ask({"question": "Is this company a small company?", "as_of": AS_OF,
                 "facts": FACTS, "provisions": ["s.2(85)"], "figures": [CAP, TURN]})
    check(u["state"] == PARTIAL and not u.get("figures") and validate(u) == [],
          f"while the instrument is unheld no figure is served ({u['state']}, {validate(u)})")
    check(any(i.get("ref") == CAP and "cannot" in i.get("detail", "")
              for i in u["not_confirmed"]),
          f"...and the turn says why, in the threshold table's own words "
          f"({[i.get('detail', '')[:40] for i in u['not_confirmed']]})")

    # ── the request fails closed ─────────────────────────────────────────────
    for bad, why in (({}, "a request with no question"),
                     ({"question": ""}, "an empty question"),
                     ({"question": "x", "figures": ["no.such.key"]},
                      "a figure key the engine does not declare"),
                     ({"question": "x", "provisions": "s.173"},
                      "provisions that are not a list"),
                     ({"question": "x", "parent_turn_id": ""},
                      "a follow-up that names no parent"),
                     ({"question": "x", "questoin": "y"}, "a mistyped field"),
                     ({"question": "x", "context": {"kind": "chat"}}, "a fourth context kind"),
                     ({"question": "x", "as_of": "not-a-date"}, "a malformed as_of")):
        try:
            answer(bad, generated_at=GEN)
            check(False, f"{why} is refused")
        except BadRequest as e:
            check(True, f"{why} is refused ({str(e)[:46]})")

    # ── an engine failure is never an abstention ─────────────────────────────
    # AGENTS.md:62 and CLAUDE.md: a transport or engine failure must NEVER render as an
    # abstention. It is not a legal state, so it must not reach the client wearing one.
    # Both copies of this module: it is imported as checker.ask by the route and run as
    # __main__ by the harness, and patching one would leave the other answering normally.
    import checker.ask as _pkg
    def _down(*a, **k):
        raise RuntimeError("engine unavailable")
    saved, saved_pkg = globals()["retrieve"], _pkg.retrieve
    globals()["retrieve"] = _down
    _pkg.retrieve = _down
    try:
        answer({"question": "What does s.173 require?", "as_of": AS_OF,
                "provisions": ["s.173"]}, generated_at=GEN)
        check(False, "an engine failure is not rendered as a state")
    except RuntimeError:
        check(True, "an engine failure raises rather than returning a state")
    except BadRequest:
        check(False, "an engine failure is not a bad request either")
    try:
        api.handle("POST", "/v1/ask", {"question": "What does s.173 require?",
                                       "provisions": ["s.173"]}, generated_at=GEN)
        check(False, "...and the route does not turn it into a 200 abstention")
    except RuntimeError:
        check(True, "...and the route does not turn it into a 200 abstention")
    finally:
        globals()["retrieve"] = saved
        _pkg.retrieve = saved_pkg

    # ── no model, on any path ────────────────────────────────────────────────
    check(all(r["uses_model"] is False for r in served),
          f"every response this suite produced states that no model was used ({len(served)})")
    check(all(validate(r) == [] for r in served),
          "every response this suite produced passes the contract validator")
    import ast
    roots = set()
    for node in ast.walk(ast.parse(Path(__file__).read_text())):
        if isinstance(node, ast.Import):
            roots.update(al.name.split(".")[0] for al in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    check(not (roots & {"openai", "anthropic", "google", "requests", "httpx", "urllib"}),
          f"this module imports no model or network library ({sorted(roots)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
