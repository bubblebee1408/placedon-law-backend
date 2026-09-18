#!/usr/bin/env python3
"""The /v1/ask response contract (placedon.ask/0): a validator, and fixtures built from the engine.

The Ask section (docs/PLAN_13_ASSISTANT_UX_PLAN.md) renders three server-decided states --
answered, partial, out_of_scope -- and nothing else. The prototype is static and sends nothing, so
it renders fixtures. Two failures that would make a prototype lie are designed out here:

1. **A fixture that says something the route would not.** Every fixture is a REQUEST put through
   `checker.ask.answer()` -- the same function `POST /v1/ask` calls (ASK-1), which itself only
   calls deterministic modules (retrieval, evidence packs, prescribed thresholds, the scope
   register, the compliance pack, the document check). Nothing legal is typed by hand, nothing is
   assembled here, and the test rebuilds the fixtures and requires them to equal what is on disk --
   so the prototype and the route cannot drift apart.
2. **A response that breaks a design rule.** `validate()` rejects: a state that is not one of the
   three; a figure with no instrument or no in-force date; a citation outside the evidence pack; an
   `answered` citing an unusable provision; any `confidence` or `coverage` field (C4 -- the coverage
   frame is carried as `scope_frame`); `answered` from a model path (today only deterministic
   results can truthfully be answered: claim_verifier never returns SUPPORTED); a `partial` with
   nothing not confirmed; an `out_of_scope` about a body we hold; stages the engine did not emit; and
   section text carrying an in-force date -- which would make "current consolidation as ingested"
   look like a point-in-time answer.

Contract prose: web/assistant/contract.md. The validator itself is checker/ask_contract.py.

Run:  python3 scripts/assistant_contract.py --write    # rebuild web/assistant/fixtures/
      python3 scripts/assistant_contract.py --test     # offline self-test
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The validator lives in the package so the route can run it on its own responses; it is
# re-exported here, where its tests and the fixtures they run against live.
from checker.ask_contract import (FORBIDDEN_KEYS, SCHEMA, STAGE_NAMES, STATES,  # noqa: E402,F401
                                  validate)

FIXTURE_DIR = ROOT / "web" / "assistant" / "fixtures"
# The same fixtures, embedded for a page opened from disk (file:// cannot fetch local JSON).
FIXTURE_JS = ROOT / "web" / "assistant" / "fixtures.js"
FIXTURE_JS_PREFIX = "window.PLACEDON_ASK_FIXTURES = "
# Fixed so that a rebuild is byte-stable and the on-disk fixtures can be compared with it.
AS_OF = "2026-09-15"
GENERATED_AT = "2026-09-15T00:00:00Z"


# ── fixtures, built from the engine ───────────────────────────────────────────
# Every fixture is a REQUEST put through checker.ask.answer(), the same function the
# /v1/ask route calls. Nothing is assembled here, so a fixture cannot say something the
# route would not: a change in the engine or in the mapping shows up as a fixture diff
# (the self-test requires the files on disk to equal a fresh rebuild), never as a
# prototype that renders a shape no caller can obtain.
FACTS = {"company_class": "private", "incorporation_date": "2019-06-01", "as_of": AS_OF,
         "financial_year": "2025-26", "paid_up_capital_rupees": 120000000,
         "turnover_rupees": 800000000}
DOC_FACTS = {"document_date": "2024-06-01", "as_of": AS_OF, "company_class": "private",
             "incorporation_date": "2019-06-01", "financial_year": "2023-24",
             "paid_up_capital_rupees": 30000000, "turnover_rupees": 300000000}
CAP = "small_company.paid_up_capital.prescribed"
TURNOVER = "small_company.turnover.prescribed"

# The user's questions are illustrative. What each turn READS is named by the request --
# the provisions and the prescribed figures -- because the engine does not parse a
# sentence for meaning (checker/ask.py); everything legal in the response is engine output.
REQUESTS: dict[str, dict] = {
    # The empty-confirmed partial the design says will dominate (red team L3): retrieve()
    # cannot resolve rule 2(1)(t) of the Definition Details Rules (audit E20), so the pack
    # is empty and says why.
    "partial_nothing_confirmed": {"question": "What does rule 2(1)(t) prescribe?",
                                  "as_of": AS_OF, "provisions": ["rule 2(1)(t)"]},
    "answered_small_company": {"question": "Is this company a small company?",
                               "as_of": AS_OF, "context": {"kind": "general"},
                               "facts": FACTS, "provisions": ["s.2(85)"],
                               "figures": [CAP, TURNOVER]},
    "partial_s173_s16": {"question": "What does s.173 require, and does s.16 apply here?",
                         "as_of": AS_OF, "provisions": ["s.173", "s.16"]},
    "out_of_scope_fema": {"question": "What must we report to RBI for this share allotment "
                                      "to a foreign investor?", "as_of": AS_OF},
    "document_context_2024": {"question": "Is the law this document relies on still current?",
                              "as_of": AS_OF,
                              "context": {"kind": "document",
                                          "document_date": DOC_FACTS["document_date"]},
                              "facts": DOC_FACTS},
    # A follow-up turn. No conversation state exists (FEATURES.md:120), so the request
    # names what it reads again and carries the id of the turn it follows.
    "followup_turnover": {"question": "And the turnover limit?", "as_of": AS_OF,
                          "figures": [TURNOVER], "provisions": ["s.2(85)"]},
}


def build_fixtures() -> dict[str, dict]:
    """Every fixture, from the route's own answer() at a fixed as_of."""
    from checker.ask import answer

    out = {name: answer(req, generated_at=GENERATED_AT) for name, req in REQUESTS.items()}
    out["followup_turnover"] = answer(
        REQUESTS["followup_turnover"] | {"parent_turn_id": out["answered_small_company"]["turn_id"]},
        generated_at=GENERATED_AT)
    return out


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
