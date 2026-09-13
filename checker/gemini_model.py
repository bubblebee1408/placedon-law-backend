"""A second model callable: Gemini, on the free tier, same shape as the first.

Built so development costs nothing. `anthropic_model.py` is the production
extractor; this is the one a student with Rs 2,000 can actually run today, and it
is chosen on measured evidence rather than on price alone.

## Why Gemini specifically, and only for what it wins

On the only rigorous independent benchmark of REAL Devanagari scans (not
synthetic), Gemini 2.5 Flash scored **86.3 chrF++** -- the best of every system
tested, ahead of Claude Opus at 82.2, with EasyOCR at 58.3 and olmOCR at 40.5.
Synthetic benchmarks hide this entirely: on clean generated text every system
clusters at 91-98 and looks identical.

So this is not multi-provider routing for cost, which measurably buys nothing.
It is using the model that wins the specific modality: **Gemini for pages, Claude
for reasoning over what those pages said.**

## Why a free tier is architecturally acceptable here

The Anthropic-only decision rested on `CitationCharLocation` giving character-level
provenance. That reasoning survives scrutiny but is less binding than it looked:
`document_extract.ground()` checks the quoted span is ACTUALLY IN THE DOCUMENT,
which is stronger than a provider asserting where it read something. We verify
against the source; the citation API only reports a claim.

So provenance does not depend on the provider, and the cheapest model that
produces a well-formed proposal is a legitimate choice.

## No dependency

`checker/` has no third-party imports and this does not add one -- the REST call
goes through `urllib` from the standard library. That also means no SDK version
can break it.

## Free-tier reality, from docs/PROVIDER_DECISION.md

The free tier is **Flash and Flash-Lite only**; Pro-series lost its free tier in
April 2026. Rate limits bind on tokens per minute, not requests per day -- an
earlier plan in this project was off by roughly 50x by reading the wrong number.
Limits are not hardcoded here because they change; `RATE_NOTE` records where to
check.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from checker.anthropic_model import ModelRefused, ModelUnavailable, _parse
from checker.reasoning import Proposal

FLASH = "gemini-2.5-flash"
FLASH_LITE = "gemini-2.5-flash-lite"

_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")

RATE_NOTE = ("Free tier is Flash and Flash-Lite only (Pro lost it April 2026). "
             "The binding limit is tokens-per-minute, not requests-per-day. "
             "Check ai.google.dev/gemini-api/docs/rate-limits before capacity "
             "planning -- an earlier plan here was off by ~50x by reading RPD.")

# Same instruction as the Anthropic extractor. Deliberately identical, so a
# difference in the shadow scores is a difference in the MODEL and not in what
# it was asked to do.
from checker.anthropic_model import _EXTRACT_SYSTEM


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _key() -> str:
    k = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not k:
        raise ModelUnavailable(
            "GEMINI_API_KEY is not set. This refuses rather than returning an "
            "empty extraction, because a blank result is indistinguishable from "
            "a document with nothing in it.")
    return k


def _post(model: str, payload: dict, timeout: int = 90) -> dict:
    url = _ENDPOINT.format(model=model) + "?key=" + _key()
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        # 429 is the free tier's TPM limit, and it is a capacity fact rather than
        # a bug -- say so, so a caller does not treat it as a broken key.
        if e.code == 429:
            raise ModelUnavailable(
                f"rate limited (HTTP 429). {RATE_NOTE} Body: {body}") from None
        raise ModelUnavailable(f"Gemini HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise ModelUnavailable(f"Gemini unreachable: {e.reason}") from None


def extract(document: str, *, budget=None, model: str = FLASH,
            _transport=None) -> tuple[Proposal, dict]:
    """Ask Gemini to read a document and quote what it read.

    Returns a Proposal for `reasoning.review()` to check. Nothing here is trusted.
    """
    if budget is not None and not budget.can_make_call():
        raise ModelUnavailable("budget exhausted; no call was made")

    payload = {
        "systemInstruction": {"parts": [{"text": _EXTRACT_SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"text": "DOCUMENT:\n" + document},
            {"text": "Report what this document says."},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096},
    }
    data = (_transport or _post)(model, payload)

    try:
        parts = data["candidates"][0]["content"]["parts"]
        raw = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        # A blocked or empty candidate is a refusal, not an empty document.
        raise ModelRefused(
            f"no usable candidate in the response: {json.dumps(data)[:200]}") from None

    usage = data.get("usageMetadata", {})
    meta = {"model": model,
            "tokens_in": usage.get("promptTokenCount", 0),
            "tokens_out": usage.get("candidatesTokenCount", 0),
            "cost_inr": 0.0,          # free tier. Paid rates UNVERIFIED here.
            "raw": raw}
    return Proposal(facts=_parse(raw)), meta


def as_shadow_model(budget=None, model: str = FLASH, _transport=None):
    """Same callable shape `shadow.run()` already scores. Swap providers freely."""
    def _m(document: str) -> Proposal:
        proposal, _ = extract(document, budget=budget, model=model,
                              _transport=_transport)
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

    print("gemini_model")

    # ── the prompt is IDENTICAL to the Anthropic extractor's ─────────────────
    from checker.anthropic_model import _EXTRACT_SYSTEM as ANTH_PROMPT
    check(_EXTRACT_SYSTEM is ANTH_PROMPT,
          "both providers get the SAME instruction — so a score difference is a "
          "difference in the model, not in what it was asked")

    # ── no key: refuse, never blank ──────────────────────────────────────────
    held = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    try:
        check(not available(), "with no key, available() is False")
        try:
            extract("doc")
            check(False, "with no key, extract() raises")
        except ModelUnavailable as e:
            check("indistinguishable from a document with nothing in it" in str(e),
                  "with no key it raises, and says why a blank would be worse")
    finally:
        for k, v in held.items():
            if v is not None:
                os.environ[k] = v

    # ── a fake transport proves the path without a key or a call ─────────────
    GOOD = {"candidates": [{"content": {"parts": [{"text":
              '{"facts": {"company_class": {"value": "private", '
              '"span": "is a private company"}}}'}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 60}}
    seen = {}

    def fake(model, payload, timeout=90):
        seen["model"], seen["payload"] = model, payload
        return GOOD

    prop, meta = extract("The Company is a private company.", _transport=fake)
    check(prop.facts["company_class"]["span"] == "is a private company",
          "a well-formed response becomes a Proposal carrying its span")
    check(meta["model"] == FLASH and meta["cost_inr"] == 0.0,
          f"...on the free tier, at zero cost ({meta['model']})")
    check(seen["payload"]["generationConfig"]["temperature"] == 0,
          "temperature is 0 — extraction is not a creative task")
    check("systemInstruction" in seen["payload"],
          "the instruction is sent as a system instruction, not buried in the turn")

    # ── failure modes refuse rather than returning something plausible ───────
    def blocked(model, payload, timeout=90):
        return {"promptFeedback": {"blockReason": "SAFETY"}}
    try:
        extract("doc", _transport=blocked)
        check(False, "a blocked/empty candidate is refused")
    except ModelRefused as e:
        check("no usable candidate" in str(e),
              "a blocked or empty candidate is refused, not read as an empty document")

    def prose(model, payload, timeout=90):
        return {"candidates": [{"content": {"parts": [{"text":
                 "I could not find any structured facts, sorry!"}]}}]}
    try:
        extract("doc", _transport=prose)
        check(False, "prose with no JSON is refused")
    except ModelRefused:
        check(True, "prose with no JSON is refused, not salvaged")

    # ── budget guard fires before the call ───────────────────────────────────
    class Broke:
        def can_make_call(self): return False
    called = []
    def spy(model, payload, timeout=90):
        called.append(1); return GOOD
    try:
        extract("doc", budget=Broke(), _transport=spy)
        check(False, "an exhausted budget refuses before the call")
    except ModelUnavailable:
        check(not called, "an exhausted budget refuses BEFORE the call — none was made")

    # ── it plugs into the same harness, unchanged ────────────────────────────
    from checker.bundles import capabilities
    from checker.shadow import CORRECT, ShadowCase, run, tally
    cases = (ShadowCase("G1", "The Company is a private company.",
                        {"company_class": "private"}, "fake-transport case"),)
    res = run(cases, as_shadow_model(_transport=fake),
              declared_intents=capabilities(), verified_text="")
    check(tally(res)[CORRECT] == 1,
          f"Gemini scores through the SAME shadow harness as Anthropic "
          f"({res[0].outcome}) — providers are comparable on one scale")

    # ── the rate-limit reality is recorded, not assumed ──────────────────────
    check("tokens-per-minute" in RATE_NOTE and "50x" in RATE_NOTE,
          "the free tier's binding limit is recorded, with the 50x error that "
          "reading requests-per-day caused here before")

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
