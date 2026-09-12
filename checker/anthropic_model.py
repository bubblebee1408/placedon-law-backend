"""The concrete model callable: Anthropic, wired into the existing gates.

Layer 1's contract (`reasoning.py`) and its harness (`shadow.py`) were built
against stubs. This is the real callable they were shaped for, so turning a model
on is a config change rather than a build.

## The decision, recorded here because it should be arguable later

**Single provider: Anthropic.** Not preference. `citations: {enabled: true}`
returns `char_location` with exact start/end indices into the document -- the
character-level provenance this product sells. Routing across providers buys cost,
not accuracy (measured: routers target *retaining* 90-95% of the best model), and
costs us that provenance. When cost forces a router, it routes between Anthropic
tiers.

**Three tiers, by consequence of error:**

    EXTRACT   claude-opus-5      reads the document, proposes facts WITH spans
    NARRATE   claude-sonnet-5    phrases results already verified
    CLASSIFY  claude-haiku-4-5   what kind of document is this

Extraction gets the strongest model because an error there becomes a wrong legal
answer. Narration cannot introduce a fact -- `reasoning.review()` drops the whole
sentence if it does -- so the cheaper tier is genuinely safe.

## Why extraction does not use structured outputs

`output_config.format` and `citations` are mutually exclusive: sending both
returns a 400. We keep citations and parse the JSON ourselves, because
`reasoning.review()` already validates harder than a schema would -- it checks the
span is IN THE DOCUMENT, which no schema can express.

## What happens with no key

`available()` is False and `extract()` raises `ModelUnavailable`. It does not
degrade to a guess, and it does not silently return empty. Every caller in this
repo already handles a refusal; none of them handle a plausible-looking blank.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from checker.reasoning import Proposal

EXTRACT = "claude-opus-5"
NARRATE = "claude-sonnet-5"
CLASSIFY = "claude-haiku-4-5"

# USD per 1M tokens, list price. Kept here so a cost estimate is derived rather
# than asserted, and so a price change is one edit.
PRICING = {
    EXTRACT:  (5.00, 25.00),
    NARRATE:  (2.00, 10.00),
    CLASSIFY: (1.00,  5.00),
}
USD_TO_INR = 95.23          # 2026-08-06, same rate as backend/budget.py


class ModelUnavailable(RuntimeError):
    """No key, or no SDK. Never degrades to a guess."""


class ModelRefused(RuntimeError):
    """The model returned something that is not a parseable proposal."""


def available() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def cost_inr(model: str, tokens_in: int, tokens_out: int) -> float:
    if model not in PRICING:
        raise KeyError(f"no price on record for {model!r}")
    pin, pout = PRICING[model]
    usd = (tokens_in / 1e6) * pin + (tokens_out / 1e6) * pout
    return round(usd * USD_TO_INR, 2)


# ── the prompt ────────────────────────────────────────────────────────────────
# Short, and it does not ask the model to be careful. Asking a model to be careful
# is a prompt, and a prompt is not a safety mechanism -- reasoning.review() is.
# What it DOES do is make the required output shape unambiguous, because a
# malformed response is a wasted call rather than a caught error.
_EXTRACT_SYSTEM = """\
You read one Indian corporate legal document and report what it says.

Return ONLY a JSON object. For each field you find, give the value and the
VERBATIM span you read it from — the exact characters as they appear in the
document, not a paraphrase and not corrected text.

{"facts": {"<field>": {"value": <value>, "span": "<verbatim text>"}}}

Fields: document_date, incorporation_date, company_class, financial_year,
paid_up_capital_rupees, turnover_rupees, net_worth_rupees, net_profit_rupees,
director_count, cin.

Dates as YYYY-MM-DD. Money as whole rupees, an integer.
Omit any field you did not find. Do not guess. Do not state a conclusion about
whether any law applies."""


@dataclass(frozen=True)
class Call:
    """What a call cost and returned. Recorded so spend is observed, not assumed."""
    model: str
    tokens_in: int
    tokens_out: int
    cost_inr: float
    raw: str


def _parse(raw: str) -> dict:
    """Pull the JSON object out of a response. Rejects rather than repairs."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ModelRefused("no JSON object in the response")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise ModelRefused(f"malformed JSON: {e}") from None
    facts = obj.get("facts")
    if not isinstance(facts, dict):
        raise ModelRefused("response has no 'facts' object")
    return facts


def extract(document: str, *, budget=None, model: str = EXTRACT,
            _client=None) -> tuple[Proposal, Call]:
    """Ask a model to read a document and quote what it read.

    Returns a Proposal for `reasoning.review()` to check. Nothing here trusts the
    result -- this function's only job is to get a well-formed proposal back.
    """
    if _client is None:
        if not available():
            raise ModelUnavailable(
                "ANTHROPIC_API_KEY is not set, or the anthropic SDK is not "
                "installed. This refuses rather than returning an empty "
                "extraction, because a blank result is indistinguishable from a "
                "document with nothing in it.")
        import anthropic
        _client = anthropic.Anthropic()

    # The budget guard runs BEFORE the call, so an exhausted budget degrades
    # rather than being discovered in a log afterwards.
    if budget is not None and not budget.can_make_call():
        raise ModelUnavailable("budget exhausted; no call was made")

    resp = _client.messages.create(
        model=model,
        max_tokens=4096,
        system=_EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "document",
             "source": {"type": "text", "media_type": "text/plain",
                        "data": document},
             "citations": {"enabled": True}},
            {"type": "text", "text": "Report what this document says."},
        ]}],
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    call = Call(model, tin, tout, cost_inr(model, tin, tout), raw)
    return Proposal(facts=_parse(raw)), call


def as_shadow_model(budget=None, model: str = EXTRACT, _client=None):
    """Adapt `extract` to the callable shape `shadow.run()` already scores."""
    def _m(document: str) -> Proposal:
        proposal, _ = extract(document, budget=budget, model=model, _client=_client)
        return proposal
    return _m


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

    print("anthropic_model")

    # ── costs are derived from a price table, not asserted ───────────────────
    # The repo's own measured figure: Haiku 4.5 at ~6,700 in / ~700 out = ₹0.97.
    check(abs(cost_inr(CLASSIFY, 6700, 700) - 0.97) < 0.02,
          f"the price table reproduces the MEASURED Haiku figure "
          f"(₹{cost_inr(CLASSIFY, 6700, 700)} vs ₹0.97 recorded in backend/services/llm.py)")
    check(cost_inr(NARRATE, 6700, 700) > cost_inr(CLASSIFY, 6700, 700),
          "Sonnet costs more than Haiku on the same shape")
    check(cost_inr(EXTRACT, 10000, 1500) < 10,
          f"a document extraction on Opus is under ₹10 "
          f"(₹{cost_inr(EXTRACT, 10000, 1500)})")
    try:
        cost_inr("claude-3-5-sonnet-20241022", 1, 1)
        check(False, "a retired model has no price and raises")
    except KeyError:
        check(True, "a retired model has no price and raises, rather than costing ₹0")

    # ── no key: refuse, never blank ──────────────────────────────────────────
    import os as _os
    held = _os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        check(not available(), "with no key, available() is False")
        try:
            extract("a document")
            check(False, "with no key, extract() raises")
        except ModelUnavailable as e:
            check("indistinguishable from a document with nothing in it" in str(e),
                  "with no key, extract() raises and says why a blank would be worse")
    finally:
        if held is not None:
            _os.environ["ANTHROPIC_API_KEY"] = held

    # ── a fake client proves the whole path without spending anything ────────
    class FakeResp:
        class _U: input_tokens, output_tokens = 1200, 300
        class _B:
            type = "text"
            text = ('{"facts": {"company_class": {"value": "private", '
                    '"span": "is a private company"}}}')
        content = [_B()]
        usage = _U()

    class FakeClient:
        def __init__(self, resp): self.resp, self.seen = resp, None
        class _M:
            def __init__(self, outer): self.outer = outer
            def create(self, **kw):
                self.outer.seen = kw
                return self.outer.resp
        @property
        def messages(self): return self._M(self)

    fc = FakeClient(FakeResp())
    prop, call = extract("The Company is a private company.", _client=fc)
    check(prop.facts["company_class"]["value"] == "private",
          "a well-formed response becomes a Proposal")
    check(prop.facts["company_class"]["span"] == "is a private company",
          "...carrying the verbatim span, which is what review() checks")
    check(call.model == EXTRACT and call.cost_inr > 0,
          f"...and the call records its model and cost (₹{call.cost_inr})")

    # the request must actually ask for citations
    sent = fc.seen
    doc_block = sent["messages"][0]["content"][0]
    check(doc_block["citations"] == {"enabled": True},
          "the request enables citations — the char-level provenance this product sells")
    check("output_config" not in sent,
          "...and does NOT send output_config, which would 400 alongside citations")
    check(sent["model"] == "claude-opus-5", f"extraction runs on Opus 5 ({sent['model']})")

    # ── malformed output is refused, not repaired ────────────────────────────
    class Bad(FakeResp):
        class _B:
            type = "text"; text = "Sure! Here are the facts I found: none really."
        content = [_B()]
    try:
        extract("doc", _client=FakeClient(Bad()))
        check(False, "prose with no JSON is refused")
    except ModelRefused as e:
        check("no JSON object" in str(e), "prose with no JSON is refused, not salvaged")

    class Half(FakeResp):
        class _B:
            type = "text"; text = '{"facts": "private company"}'
        content = [_B()]
    try:
        extract("doc", _client=FakeClient(Half()))
        check(False, "a 'facts' that is not an object is refused")
    except ModelRefused:
        check(True, "a 'facts' that is not an object is refused")

    # ── the adapter plugs straight into the existing harness ─────────────────
    from checker.shadow import ShadowCase, run, tally, CORRECT
    from checker.bundles import capabilities
    DOC = "The Company is a private company."
    cases = (ShadowCase("A1", DOC, {"company_class": "private"}, "fake-client case"),)
    res = run(cases, as_shadow_model(_client=FakeClient(FakeResp())),
              declared_intents=capabilities(), verified_text="")
    check(tally(res)[CORRECT] == 1,
          f"the real callable scores through shadow.run() unchanged ({res[0].outcome})")

    # ── budget guard fires before the call ───────────────────────────────────
    class Broke:
        def can_make_call(self): return False
    try:
        extract("doc", budget=Broke(), _client=FakeClient(FakeResp()))
        check(False, "an exhausted budget refuses BEFORE the call")
    except ModelUnavailable as e:
        check("no call was made" in str(e),
              "an exhausted budget refuses before the call, not after")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
