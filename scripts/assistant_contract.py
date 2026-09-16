#!/usr/bin/env python3
"""The /v1/ask response contract (placedon.ask/0): a validator, and fixtures built from the engine.

The Ask section (docs/PLAN_13_ASSISTANT_UX_PLAN.md) renders three server-decided states --
answered, partial, out_of_scope -- and nothing else. The route does not exist yet, so the UI is
prototyped against fixtures. Two failures that would make a prototype lie are designed out here:

1. **A fixture that says something the engine cannot.** Every fixture is BUILT by calling the
   engine's own deterministic modules (retrieval, evidence packs, prescribed thresholds, the scope
   register, the compliance pack, the document check). Nothing legal is typed by hand, and the test
   rebuilds the fixtures and requires them to equal what is on disk.
2. **A response that breaks a design rule.** `validate()` rejects: a state that is not one of the
   three; a figure with no instrument or no in-force date; a citation outside the evidence pack; an
   `answered` citing an unusable provision; any `confidence` or `coverage` field (C4 -- the coverage
   frame is carried as `scope_frame`); `answered` from a model path (today only deterministic
   results can truthfully be answered: claim_verifier never returns SUPPORTED); a `partial` with
   nothing not confirmed; an `out_of_scope` about a body we hold; stages the engine did not emit; and
   section text carrying an in-force date -- which would make "current consolidation as ingested"
   look like a point-in-time answer.

Contract prose: web/assistant/contract.md.

Run:  python3 scripts/assistant_contract.py --write    # rebuild web/assistant/fixtures/
      python3 scripts/assistant_contract.py --test     # offline self-test
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCHEMA = "placedon.ask/0"
STATES = ("answered", "partial", "out_of_scope")
FIXTURE_DIR = ROOT / "web" / "assistant" / "fixtures"
# The same fixtures, embedded for a page opened from disk (file:// cannot fetch local JSON).
FIXTURE_JS = ROOT / "web" / "assistant" / "fixtures.js"
FIXTURE_JS_PREFIX = "window.PLACEDON_ASK_FIXTURES = "
# checker/orchestrator.py step() names. A stage the engine does not emit is not a stage.
STAGE_NAMES = ("capability", "date", "model", "review", "correction", "abstain")
# C4: no confidence, ever. `coverage` is refused because ClaimVerification.coverage is a float that
# reads as confidence; the document-check coverage frame travels as `scope_frame` instead (K8).
FORBIDDEN_KEYS = ("confidence", "coverage")
# Fixed so that a rebuild is byte-stable and the on-disk fixtures can be compared with it.
AS_OF = "2026-09-15"
GENERATED_AT = "2026-09-15T00:00:00Z"


# ── validation ────────────────────────────────────────────────────────────────
def _keys(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, f"{path}.{k}"
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _keys(v, f"{path}[{i}]")


def _lists(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _lists(v, f"{path}.{k}")
    elif isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from _lists(v, f"{path}[{i}]")


def _as_json(v):
    """What the engine returned, in JSON types. A tuple becomes a list; a string stays a
    string -- list() on a string is how a sentence becomes 455 characters."""
    return list(v) if isinstance(v, tuple) else v


def validate(r: dict) -> list[str]:
    """Every way this response breaks the contract. Empty means it may be rendered."""
    if not isinstance(r, dict):
        return ["the response is not a JSON object"]
    errs: list[str] = []
    if r.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    state = r.get("state")
    if state not in STATES:
        return errs + [f"state {state!r} is not one of {', '.join(STATES)} -- the client never "
                       f"infers one"]
    for k in ("turn_id", "question", "generated_at", "as_of", "context", "uses_model", "scope"):
        if k not in r:
            errs.append(f"missing {k}")
    for k, p in _keys(r):
        if k in FORBIDDEN_KEYS:
            errs.append(f"{p}: a '{k}' field is forbidden (C4)")
    for p, v in _lists(r):
        # A sentence that went through list() arrives as its own characters. It reads as
        # a list to every check that only counts items, and as nothing to a reader.
        if len(v) > 2 and all(isinstance(x, str) and len(x) == 1 for x in v):
            errs.append(f"{p}: {len(v)} single-character items -- this is a string that "
                        f"was split, not a list the engine returned")

    ctx = r.get("context") or {}
    kind = ctx.get("kind")
    if kind not in ("document", "general"):
        errs.append("context.kind must be document or general")
    if kind == "document" and not ctx.get("document_date"):
        errs.append("a document-context turn needs its document_date")
    if "stages" in r:
        if kind != "document":
            errs.append("stages exist only on the document path -- a general turn has none (K9)")
        for s in r.get("stages") or []:
            if not isinstance(s, dict) or s.get("what") not in STAGE_NAMES:
                errs.append(f"stage {s!r} is not one the orchestrator emits")
    if "parent_turn_id" in r and not r["parent_turn_id"]:
        errs.append("a follow-up must name the turn it follows")

    pack = r.get("evidence_pack") or {}
    in_pack = set(pack.get("usable_keys", [])) | set(pack.get("unusable_keys", []))
    for cit in r.get("citations", []):
        if cit.get("ref") not in in_pack:
            errs.append(f"citation {cit.get('ref')} is outside the evidence pack")
        if "effective_from" in cit:
            errs.append(f"citation {cit.get('ref')}: section text carries no in-force date")
        if state == "answered" and not cit.get("usable_for_answering"):
            errs.append(f"answered cites {cit.get('ref')}, which is not usable for answering")
    for fig in r.get("figures", []):
        for k in ("amount", "instrument", "effective_from"):
            if not fig.get(k):
                errs.append(f"figure {fig.get('key')} has no {k}")
    # A turn that shows rows or section text must say what law they were read against. On a
    # document turn, "current" means current consolidation -- not the law at the document date.
    if (state != "out_of_scope"
            and any(r.get(k) for k in ("rows", "confirmed", "superseded", "citations"))
            and not r.get("law_version")):
        errs.append("a turn that renders rows or legal text needs law_version -- what law it "
                    "was checked against")

    if state == "answered":
        if r.get("uses_model") is not False:
            errs.append("answered is only truthful from a deterministic path today "
                        "(claim_verifier never returns SUPPORTED)")
        if not (r.get("figures") or r.get("rows")):
            errs.append("answered needs a figure or an obligation row")
    elif state == "partial":
        if not r.get("not_confirmed"):
            errs.append("partial needs at least one thing not confirmed")
        for item in r.get("confirmed", []):
            if "effective_from" in item:
                errs.append("confirmed section text carries no in-force date -- current "
                            "consolidation is not a point-in-time answer")
            if item.get("ref") and in_pack and item["ref"] not in in_pack:
                errs.append(f"confirmed {item['ref']} is outside the evidence pack")
    else:
        body = r.get("body") or {}
        if body.get("scope_status") in (None, "IN_CORPUS"):
            errs.append("out_of_scope must name a body of law we do not hold")
        if not r.get("reason"):
            errs.append("out_of_scope needs the register's reason")
    return errs


# ── fixtures, built from the engine ───────────────────────────────────────────
def _envelope(question: str, *, kind: str = "general", document_date: str | None = None,
              parent: str | None = None) -> dict:
    from checker import scope
    turn = hashlib.sha256(f"{question}|{AS_OF}|{kind}|{document_date}".encode()).hexdigest()[:12]
    env = {"schema": SCHEMA, "turn_id": f"t_{turn}", "question": question,
           "generated_at": GENERATED_AT, "as_of": AS_OF,
           "context": {"kind": kind, "document_date": document_date}, "uses_model": False,
           "scope": {"held": [b.name for b in scope.in_corpus()], "sentence": scope.coverage()}}
    if parent is not None:
        env["parent_turn_id"] = parent
    return env


def _pack(query: str) -> tuple[dict, str]:
    from checker.retrieve import retrieve
    pack, route = retrieve(query)
    return pack.to_dict(), route


def _citation(p: dict) -> dict:
    return {"ref": p["ref"], "cite": p["cite"], "title": p["title"],
            "evidence_state": p["evidence_state"],
            "usable_for_answering": p["usable_for_answering"],
            "unusable_reason": p["unusable_reason"] or None,
            "defects": p["defects"],
            "retrieved_on": sorted({s["retrieved_on"] for s in p["sources"] if s.get("retrieved_on")}),
            "source_url": next((s["source_url"] for s in p["sources"] if s.get("source_url")), None)}


def _law_version(d: dict) -> dict:
    a = d["as_of"]
    return {k: a[k] for k in ("basis", "point_in_time_verified", "corpus_fetched", "statement")}


def _law_version_at(provisions: list[str], requested: str) -> dict:
    """The engine's own basis statement for a past date, over the provisions a turn cites.

    Built by evidence_pack's statement builder, never written here: it is the sentence that
    says no statement is about the law as it stood on that date.
    """
    import re
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


def _figure(key: str) -> dict:
    from checker import prescribed_thresholds as pt
    t = pt.lookup(key, date.fromisoformat(AS_OF))
    return {"key": key, "amount": str(t.amount), "rupees": t.amount.rupees,
            "instrument": t.instrument, "effective_from": t.effective_from.isoformat(),
            "effective_to": t.effective_to.isoformat() if t.effective_to else None,
            "evidence_state": t.state, "source_url": t.source_url}


def build_fixtures() -> dict[str, dict]:
    """Every fixture, assembled from deterministic engine calls. No legal text is typed here."""
    from checker import api, scope

    facts = {"company_class": "private", "incorporation_date": "2019-06-01", "as_of": AS_OF,
             "financial_year": "2025-26", "paid_up_capital_rupees": 120000000,
             "turnover_rupees": 800000000}
    pack_json = api.compliance_pack(facts, generated_at=GENERATED_AT)
    small = next(row for row in pack_json["rows"] if row["obligation_id"] == "CA13-S2-85-SMALL")
    s285, route285 = _pack("s.2(85)")
    answered = _envelope("Is this company a small company?") | {
        "state": "answered",
        "facts": {k: {"value": facts[k], "provenance": "USER_FACT"}
                  for k in ("company_class", "paid_up_capital_rupees", "turnover_rupees")},
        "rows": [small],
        "figures": [_figure("small_company.paid_up_capital.prescribed"),
                    _figure("small_company.turnover.prescribed")],
        "citations": [_citation(p) for p in s285["provisions"]],
        "law_version": _law_version(s285),
        "evidence_pack": _pack_summary(s285, route285),
        "what_it_is_not": _as_json(pack_json["what_it_is_not"]),
    }

    mixed, route_mixed = _pack("s.173 and s.16")
    partial = _envelope("What does s.173 require, and does s.16 apply here?") | {
        "state": "partial",
        "confirmed": [_citation(p) | {"verbatim": p["reading_text"]}
                      for p in mixed["provisions"] if p["usable_for_answering"]],
        "not_confirmed": ([{"kind": "pack_missing", "detail": m} for m in mixed["missing"]]
                          + [{"kind": "unusable", "ref": p["ref"], "reason": p["unusable_reason"],
                              "defects": p["defects"]}
                             for p in mixed["provisions"] if not p["usable_for_answering"]]),
        "law_version": _law_version(mixed),
        "evidence_pack": _pack_summary(mixed, route_mixed),
        "demand_signal": {"action": "tell_us_blocking"},
    }

    fema = scope.body("FEMA1999")
    out_of_scope = _envelope("What must we report to RBI for this share allotment to a "
                             "foreign investor?") | {
        "state": "out_of_scope",
        "body": {"key": fema.key, "name": fema.name, "regulator": fema.regulator,
                 "covers": fema.covers, "scope_status": fema.status},
        "reason": scope.refusal_for("FEMA1999"),
        "held": [b.name for b in scope.in_corpus()],
    }

    doc_payload = {"document_date": "2024-06-01", "as_of": AS_OF, "company_class": "private",
                   "incorporation_date": "2019-06-01", "financial_year": "2023-24",
                   "paid_up_capital_rupees": 30000000, "turnover_rupees": 300000000}
    check = api.document_check(doc_payload, generated_at=GENERATED_AT)
    document = _envelope("Is the law this document relies on still current?", kind="document",
                         document_date=doc_payload["document_date"]) | {
        "state": "partial" if check["cannot_verify"] else "answered",
        "superseded": check["superseded"],
        "confirmed": check["verified"],
        "not_confirmed": [{"kind": "cannot_verify"} | item for item in check["cannot_verify"]],
        "scope_frame": check["coverage"],
        # Red team L2: document_check says CURRENT for Act-only rows by construction, against
        # the current consolidation. The turn carries the engine's statement for the
        # document's own date so that "current" cannot be read as the law in 2024.
        "law_version": _law_version_at(
            [x.get("provision", "") for x in check["verified"] + check["cannot_verify"]
             + check["superseded"]],
            doc_payload["document_date"]),
        # api returns a tuple here; a fixture is JSON, so it must hold JSON types or a rebuild
        # compares unequal to the file it was written as. _as_json leaves a string alone.
        "what_it_is_not": _as_json(check["what_it_is_not"]),
    }

    followup = _envelope("And the turnover limit?", parent=answered["turn_id"]) | {
        "state": "answered",
        "figures": [_figure("small_company.turnover.prescribed")],
        "citations": [_citation(p) for p in s285["provisions"]],
        "law_version": _law_version(s285),
        "evidence_pack": _pack_summary(s285, route285),
    }

    # Red team L3: the partial the design says will dominate -- a retrieval that abstained, so
    # nothing is confirmed. retrieve() cannot resolve rule 2(1)(t) of the Definition Details
    # Rules (audit E20), so the pack is empty and says why.
    absent, route_absent = _pack("rule 2(1)(t)")
    nothing = _envelope("What does rule 2(1)(t) prescribe?") | {
        "state": "partial",
        "confirmed": [],
        "not_confirmed": [{"kind": "pack_missing", "detail": m} for m in absent["missing"]],
        "law_version": _law_version(absent),
        "evidence_pack": _pack_summary(absent, route_absent),
    }

    return {"partial_nothing_confirmed": nothing,
            "answered_small_company": answered, "partial_s173_s16": partial,
            "out_of_scope_fema": out_of_scope, "document_context_2024": document,
            "followup_turnover": followup}


def write_fixtures() -> list[Path]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = build_fixtures()
    written = []
    for name, resp in fixtures.items():
        errs = validate(resp)
        if errs:
            raise SystemExit(f"{name} does not validate: {errs}")
        path = FIXTURE_DIR / f"{name}.json"
        path.write_text(json.dumps(resp, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
        written.append(path)
    # Written from the same validated dict in the same pass, so the two copies cannot diverge.
    FIXTURE_JS.write_text(FIXTURE_JS_PREFIX
                          + json.dumps(fixtures, indent=1, ensure_ascii=False, sort_keys=True)
                          + ";\n")
    written.append(FIXTURE_JS)
    return written


def _test() -> None:
    ok = fail = 0

    def c(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("assistant_contract")
    import copy

    fx = build_fixtures()
    c(set(fx) >= {"answered_small_company", "partial_s173_s16", "out_of_scope_fema", "partial_nothing_confirmed",
                  "document_context_2024", "followup_turnover"},
      f"fixtures cover every state plus a document turn and a follow-up ({sorted(fx)})")
    for name, resp in fx.items():
        c(validate(resp) == [], f"{name} validates ({validate(resp)})")
    c({r["state"] for r in fx.values()} == set(STATES),
      "all three states are represented")

    # ── the fixtures say only what the engine says ──────────────────────────
    from datetime import date
    from checker import prescribed_thresholds as pt, scope
    ans = fx["answered_small_company"]
    t = pt.lookup("small_company.paid_up_capital.prescribed", date.fromisoformat(ans["as_of"]))
    fig = next(f for f in ans["figures"] if f["key"] == "small_company.paid_up_capital.prescribed")
    c(fig["amount"] == str(t.amount) and fig["instrument"] == t.instrument
      and fig["effective_from"] == t.effective_from.isoformat(),
      f"the answered figure is the engine's threshold, verbatim ({fig['amount']}, {fig['effective_from']})")
    oos = fx["out_of_scope_fema"]
    c(oos["reason"] == scope.refusal_for("FEMA1999"),
      "the out_of_scope reason is scope.refusal_for, not written copy")
    c(all(r["uses_model"] is False for r in fx.values()),
      "every fixture comes from a deterministic path -- no model was called")
    c(FIXTURE_DIR.is_dir() and {p.stem for p in FIXTURE_DIR.glob("*.json")} == set(fx)
      and all(json.loads((FIXTURE_DIR / f"{n}.json").read_text()) == r for n, r in fx.items()),
      "the fixtures on disk equal a fresh rebuild -- none was edited by hand "
      "(run --write after an engine change)")
    # A page opened from disk cannot fetch() local JSON (Chromium blocks file:// requests), so
    # the prototype reads an embedded copy. It is written by the same builder, never by hand.
    js = FIXTURE_JS.read_text() if FIXTURE_JS.is_file() else ""
    c(js.startswith(FIXTURE_JS_PREFIX)
      and json.loads(js[len(FIXTURE_JS_PREFIX):].rstrip().rstrip(";")) == fx,
      "fixtures.js embeds exactly the rebuilt fixtures, for a page opened from disk")

    # ── a string is never a list of characters ──────────────────────────────
    # The design agent found it while binding the spec to this contract:
    # api.compliance_pack returns what_it_is_not as a STRING, list() split it into
    # 455 single characters, and the fixture carried a sentence the engine never
    # said in a shape no renderer could show. The fix is the type rule, and the
    # validator so the shape cannot come back.
    ans = fx["answered_small_company"]
    from checker import api as _api
    engine_says = _api.compliance_pack(
        {"company_class": "private", "incorporation_date": "2019-06-01", "as_of": AS_OF,
         "financial_year": "2025-26", "paid_up_capital_rupees": 120000000,
         "turnover_rupees": 800000000}, generated_at=GENERATED_AT)["what_it_is_not"]
    c(ans["what_it_is_not"] == engine_says,
      f"what_it_is_not is what the engine returned, not a split of it "
      f"({type(ans['what_it_is_not']).__name__}, "
      f"{len(ans['what_it_is_not'])} item(s) vs engine {type(engine_says).__name__})")
    c(validate(copy.deepcopy(ans) | {"what_it_is_not": list("a sentence")}),
      "a field holding a list of single characters is refused -- that is a string "
      "someone split, and no renderer can show it as a list")
    c(validate(copy.deepcopy(ans) | {"what_it_is_not": ["a", "b"]}) == [],
      "...while a short genuine list of one-letter items is not blocked by length "
      "alone -- the rule needs more than two items to fire")


    # ── what the validator refuses ──────────────────────────────────────────
    def broken(name: str, mutate) -> list[str]:
        r = copy.deepcopy(fx[name])
        mutate(r)
        return validate(r)

    c(broken("answered_small_company", lambda r: r.pop("state")),
      "a response with no state is refused -- the client never infers one")
    c(broken("answered_small_company", lambda r: r.update(state="verified")),
      "a fourth state is refused")
    c(broken("answered_small_company", lambda r: r["figures"][0].pop("effective_from")),
      "a figure with no in-force date is refused")
    c(broken("answered_small_company", lambda r: r["figures"][0].pop("instrument")),
      "a figure with no instrument is refused")
    c(broken("answered_small_company",
             lambda r: r["citations"].append({"ref": "ACT:COMPANIES_ACT_2013:S999",
                                              "evidence_state": "CORROBORATED",
                                              "usable_for_answering": True})),
      "a citation outside the evidence pack is refused")
    c(broken("answered_small_company",
             lambda r: r["citations"][0].update(usable_for_answering=False)),
      "an answered response citing an unusable provision is refused")
    c(broken("answered_small_company", lambda r: r["figures"][0].update(confidence="HIGH")),
      "a confidence field anywhere is refused (C4)")
    c(broken("partial_s173_s16", lambda r: r.update(coverage={"checked": []})),
      "a field named coverage is refused -- the coverage frame travels as scope_frame (K8)")
    c(broken("answered_small_company", lambda r: r.update(uses_model=True)),
      "answered from a model path is refused -- nothing can establish SUPPORTED today")
    c(broken("partial_s173_s16", lambda r: r.update(not_confirmed=[])),
      "a partial with nothing not confirmed is refused")
    c(broken("out_of_scope_fema", lambda r: r["body"].update(scope_status="IN_CORPUS")),
      "an out_of_scope about a body we hold is refused")
    c(broken("partial_s173_s16",
             lambda r: r.update(stages=[{"n": 1, "what": "model", "detail": "x"}])),
      "stages on a general-context turn are refused -- only the document path emits them (K9)")
    c(broken("document_context_2024",
             lambda r: r.update(stages=[{"n": 1, "what": "thinking", "detail": "x"}])),
      "a stage the orchestrator does not define is refused -- no client-invented captions")
    c(broken("document_context_2024", lambda r: r["context"].update(document_date=None)),
      "a document-context turn without a document date is refused")
    c(broken("partial_s173_s16",
             lambda r: r["confirmed"][0].update(effective_from="2013-09-12")),
      "section text carrying an in-force date is refused -- the two as-of truths stay distinct")
    c(broken("followup_turnover", lambda r: r.update(parent_turn_id="")),
      "a follow-up names the turn it follows")

    # ── a document turn says what law it was checked against (red team L2) ──
    # document_check reports Act-only obligations CURRENT by construction
    # (currency.py), against a corpus that is the CURRENT consolidation. On a 2024
    # document that reads as the law in 2024. The turn must carry the engine's own
    # statement of the basis, with the document date as the requested point in time.
    doc = fx["document_context_2024"]
    lv = doc.get("law_version") or {}
    c(lv.get("point_in_time_requested") == doc["context"]["document_date"]
      and lv.get("point_in_time_verified") is False
      and "no statement here is a statement about the law as it stood" in lv.get("statement", ""),
      "the document turn carries the engine's basis statement for the document's own "
      "date -- current consolidation, not the law as it stood")
    c(broken("document_context_2024", lambda r: r.pop("law_version")),
      "a turn that renders rows or superseded items without a law_version is refused")
    c(broken("partial_s173_s16", lambda r: r.pop("law_version")),
      "...and so is one that renders confirmed section text without it")
    c(validate(copy.deepcopy(fx["out_of_scope_fema"])) == [],
      "an out_of_scope turn renders no legal text and needs no law_version")

    # ── the partial that will dominate: nothing confirmed (red team L3) ─────
    emp = fx.get("partial_nothing_confirmed") or {}
    c(emp.get("state") == "partial" and emp.get("confirmed") == []
      and emp.get("not_confirmed") and emp.get("evidence_pack", {}).get("route") == "abstain",
      "a fixture covers the empty-confirmed partial, built from a retrieval that abstained")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
        raise SystemExit(0)
    if "--write" in sys.argv:
        for p in write_fixtures():
            print(f"wrote {p.relative_to(ROOT)}")
        raise SystemExit(0)
    print(__doc__)
