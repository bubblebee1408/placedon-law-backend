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
import subprocess
import urllib.error
import urllib.request

from checker.anthropic_model import ModelRefused, ModelUnavailable, _parse
from checker.reasoning import Proposal

# Pinned to an exact version, never to `gemini-flash-latest`: an alias that moves
# underneath a benchmark makes every recorded number unreproducible.
#
# 2.5-flash was the original pin and is now DEAD for new API keys -- the /models
# endpoint still lists it, but generateContent returns 404 saying it "is no longer
# available to new users". Measured 14-09-2026 on a fresh key. A capability list
# that advertises what the call refuses is worth knowing about.
FLASH = "gemini-3.6-flash"

# FLASH_LITE pointed at `gemini-2.5-flash-lite` from the day it was written and was
# referenced by nothing, so nothing ever ran it. It has been dead the whole time:
# measured 28-09-2026 on this key it returns **HTTP 404, "This model
# models/gemini-2.5-flash-lite is no longer available to new users"** -- the same
# retirement the FLASH comment above records for 2.5-flash, which we noticed only
# because that constant was actually called.
#
# Repointed to the only Flash-Lite that answered. The full sweep, same key, same
# minute, `generateContent` with a two-word prompt:
#
#     gemini-2.5-flash-lite       404  retired for new keys  <- the old pin
#     gemini-3.1-flash-lite       200  'ok'                  <- the new pin
#     gemini-3.5-flash-lite       503  high demand
#     gemini-flash-lite-latest    503  high demand
#     gemini-3.6-flash            200  'ok'   (503 under load minutes later)
#     gemini-3.7-flash            200  'ok'
#
# 3.5-flash-lite is newer and may well be the better model; it is not pinned because
# a 503 is not a measurement. A pin here means "this answered", and only 3.1 did.
FLASH_LITE = "gemini-3.1-flash-lite"

# 404 and 503 arrived in the same sweep and mean opposite things, and `_post` raised
# the same exception for both. A caller cannot act on that: retrying a retired model
# never succeeds however long it waits, and abandoning a busy one throws away a route
# that works. Split, because the free-tier fallback in router.py has to tell "this
# model is gone, a person must repoint it" from "come back in a minute".
class ModelRetired(ModelUnavailable):
    """The pinned model is gone for this key. Retrying cannot fix it; a person must."""


class ModelBusy(ModelUnavailable):
    """Capacity, not configuration. The identical call may succeed a minute later."""


class ModelRateLimited(ModelUnavailable):
    """The free tier's quota, which is a fact about the plan rather than about the call.

    Split from ModelBusy because the two want opposite responses. A 503 is this model
    being loaded, and the next model in the row will very likely answer -- so retry
    sideways. A 429 is the project's quota for this model, measured at 20 requests per
    day (backend/budget.FREE_TIER_RPD_PER_MODEL), and retrying sideways spends the next
    model's 20 as well. Waiting is the only thing that helps, and `retryDelay` in the
    body says how long.
    """

_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")

# Vertex AI: the same generateContent call, billed to a Cloud project and signed
# with the caller's own Google login. Selected by GOOGLE_CLOUD_PROJECT.
_VERTEX_ENDPOINT = ("https://{host}/v1/projects/{project}/locations/{loc}/"
                    "publishers/google/models/{model}:generateContent")
# Both values are interpolated into a URL, so both are checked before use.
_PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
_LOCATION = re.compile(r"[a-z0-9-]{2,40}")

RATE_NOTE = ("Free tier is Flash and Flash-Lite only (Pro lost it April 2026). "
             "The binding limit is tokens-per-minute, not requests-per-day. "
             "Check ai.google.dev/gemini-api/docs/rate-limits before capacity "
             "planning -- an earlier plan here was off by ~50x by reading RPD.")

# Same instruction as the Anthropic extractor. Deliberately identical, so a
# difference in the shadow scores is a difference in the MODEL and not in what
# it was asked to do.
from checker.anthropic_model import _EXTRACT_SYSTEM
from checker.prompt_safety import (UNTRUSTED_CLAUSE, carries_clause,
                                   contains_untrusted_block, wrap_untrusted)


# A key in .env must reach a fresh process; `export` at a prompt does not
# survive the shell that ran it. checker.env never overwrites a real
# environment variable, so deployment still wins.
from checker.env import load as _load_env  # noqa: E402
_load_env()


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
                or os.getenv("GOOGLE_CLOUD_PROJECT"))


def _key() -> str:
    k = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not k:
        raise ModelUnavailable(
            "GEMINI_API_KEY is not set. This refuses rather than returning an "
            "empty extraction, because a blank result is indistinguishable from "
            "a document with nothing in it.")
    return k


def _vertex_token() -> str:
    """An access token from the caller's own Google login. No key is stored."""
    login = "Run: gcloud auth application-default login"
    try:
        r = subprocess.run(["gcloud", "auth", "application-default",
                            "print-access-token"],
                           capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise ModelUnavailable(
            f"GOOGLE_CLOUD_PROJECT is set but no Google login is usable ({e}). "
            f"{login}") from None
    if r.returncode != 0 or not r.stdout.strip():
        raise ModelUnavailable(
            f"gcloud could not issue a token: {(r.stderr or '').strip()[:200]}. "
            f"{login}")
    return r.stdout.strip()


def _route(model: str, *, _token=None) -> tuple[str, dict]:
    """Where the call goes and how it is signed. The payload never changes."""
    headers = {"Content-Type": "application/json"}
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        return _ENDPOINT.format(model=model) + "?key=" + _key(), headers

    loc = os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
    if not _PROJECT_ID.fullmatch(project) or not _LOCATION.fullmatch(loc):
        raise ModelUnavailable(
            f"GOOGLE_CLOUD_PROJECT={project!r} / GOOGLE_CLOUD_LOCATION={loc!r} is "
            f"not a valid project ID / location; refusing to build a URL from it")
    host = ("aiplatform.googleapis.com" if loc == "global"
            else f"{loc}-aiplatform.googleapis.com")
    url = _VERTEX_ENDPOINT.format(host=host, project=project, loc=loc, model=model)
    return url, headers | {"Authorization": f"Bearer {(_token or _vertex_token)()}"}


def _classify_http(model: str, code: int, body: str) -> ModelUnavailable:
    """Which kind of unavailable. Pure, so the branches are testable without a socket.

    Returns the exception rather than raising it, so a caller reading this function can
    see that every branch produces one -- an `if` chain that raises has no such property
    and a missing `else` reads as if it simply continues.
    """
    # 429 is the free tier's TPM limit, and it is a capacity fact rather than a bug --
    # say so, so a caller does not treat it as a broken key.
    if code == 429:
        return ModelRateLimited(f"rate limited (HTTP 429). {RATE_NOTE} Body: {body}")
    if code == 503:
        return ModelBusy(
            f"{model} is busy (HTTP 503). This is capacity, not configuration: the same "
            f"call may succeed shortly, and the pin is still correct. Body: {body}")
    if code == 404:
        return ModelRetired(
            f"{model} does not answer for this key (HTTP 404). Google retires a model by "
            f"leaving it listed on /models while generateContent refuses it, so a "
            f"capability listing is not evidence the call works. No retry fixes this -- "
            f"repoint the constant in {__name__} after measuring a replacement. Body: {body}")
    return ModelUnavailable(f"Gemini HTTP {code}: {body}")


def _post(model: str, payload: dict, timeout: int = 90) -> dict:
    url, headers = _route(model)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    try:
        # A VERIFYING context, reused from robots.py rather than re-derived.
        # python.org builds on macOS ship a CA path that does not exist until the
        # bundled Install Certificates.command is run, so urllib fails where curl
        # works. The tempting fix is ssl._create_unverified_context(); for a
        # project whose whole claim is authenticated sources it is the wrong one,
        # because an unverified endpoint cannot be distinguished from anyone able
        # to answer on its behalf. robots.ssl_context() hunts for a real trust
        # store and returns None when the machine has none -- and we fail closed
        # on that rather than falling back.
        from checker.robots import ssl_context
        ctx = ssl_context()
        if ctx is None:
            raise ModelUnavailable(
                "no CA trust store on this machine, so the API endpoint cannot be "
                "authenticated. Refusing to call it unverified.")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _classify_http(model, e.code, e.read().decode("utf-8", "replace")[:300]) from None
    except urllib.error.URLError as e:
        raise ModelUnavailable(f"Gemini unreachable: {e.reason}") from None


def _payload(document: str) -> dict:
    """The request body. Split out of `extract` so its E1 properties are testable.

    `extract` now requires a public-corpus clearance, and the prompt-injection specimens
    this has to be tested against (`prompt_safety.INJECTIONS`) are synthetic -- there is
    no published file they appear in, nor should there be. Building the payload here lets
    the delimiting be proved on hostile text without inventing a clearance for it, and
    `extract` is checked separately for sending exactly what this returns.
    """
    return {
        "systemInstruction": {"parts": [{"text": _EXTRACT_SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            # E1. Gemini takes the document as a CONCATENATED STRING -- unlike
            # Anthropic, which gets its own content block -- so "DOCUMENT:" was the
            # only thing separating the document from the prompt around it, and a
            # label is not a boundary. Delimited here, and only here, because this
            # path returns no offsets into the text: there is nothing to shift.
            {"text": wrap_untrusted(document, "uploaded document")},
            {"text": "Report what this document says."},
        ]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096},
    }


def _free_quota_verdict(budget, model: str):
    """The rupee gates AND the provider's own per-model daily quota.

    The cap is passed in rather than read inside backend/budget.py, because which models
    are free-tier is this module's fact: the ledger counts calls and must not grow a table
    of Google's model names. Measured 28-09-2026 from Google's quota object --
    GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20 -- and PER MODEL, so the
    fallback row in router.py is a second bucket of 20 rather than a share of one.
    """
    from backend.budget import FREE_TIER_RPD_PER_MODEL
    # estimated_inr=0.0 explicitly, and not because zero is convenient: router.estimate_inr
    # already returns 0.0 for GEMINI (free tier, paid rates UNVERIFIED there), and these
    # model names have no tokenizer on record -- `can_make_call` would raise trying to
    # price one. Before this, the call passed NO model at all, so a Gemini request was
    # priced against DEFAULT_MODEL, an Anthropic rate, and charged to the rupee ledger at
    # a cost it never incurred. The request counter below is the gate that actually binds.
    return budget.can_make_call(0.0, model=model,
                                per_model_cap=FREE_TIER_RPD_PER_MODEL)


def extract(document: str, *, origin, budget=None, model: str = FLASH,
            _transport=None) -> tuple[Proposal, dict]:
    """Ask Gemini to read a document and quote what it read.

    Returns a Proposal for `reasoning.review()` to check. Nothing here is trusted.

    `origin` is REQUIRED and has no default, the same way `robots.Fetcher.get`'s `expect`
    is required: a keyword with a safe-looking default is a keyword nobody passes, and the
    one call site that forgets is exactly the one sending a client's board minute to a
    free tier whose terms let it be used for training. There is no bypass -- see
    `checker/public_only.py` for why a provenance LABEL would not be one either.
    """
    # Before the budget check, and before anything else. Whether text may leave at all is
    # not a question whose answer depends on how much money is left.
    from checker.public_only import refuse_matter as _refuse_matter
    from checker.public_only import verify as _verify_public
    # PLAN_22 D3: the free tier never receives a Vault or matter document. clear_matter
    # binds whoever MADE the origin; this binds whoever passes it here, so an origin
    # cleared for Azure cannot arrive at Gemini one function later.
    _refuse_matter(origin)
    _verify_public(document, origin)

    if budget is not None:
        # The verdict's own reason, not a generic one: "budget exhausted" sent a reader to
        # the rupee ledger for what is usually the provider's per-model request quota, and
        # those two have different remedies -- one needs money, the other needs tomorrow.
        _v = _free_quota_verdict(budget, model)
        if not _v.allowed:
            raise ModelUnavailable(f"no call was made -- {_v.reason}")

    data = (_transport or _post)(model, _payload(document))

    try:
        parts = data["candidates"][0]["content"]["parts"]
        raw = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        # A blocked or empty candidate is a refusal, not an empty document.
        raise ModelRefused(
            f"no usable candidate in the response: {json.dumps(data)[:200]}") from None

    usage = data.get("usageMetadata", {})
    meta = {"model": model,
            "route": "vertex" if os.getenv("GOOGLE_CLOUD_PROJECT") else "ai-studio",
            "tokens_in": usage.get("promptTokenCount", 0),
            "tokens_out": usage.get("candidatesTokenCount", 0),
            "cost_inr": 0.0,          # free tier. Paid rates UNVERIFIED here.
            "raw": raw}
    # Recorded even at ₹0.00. `can_make_call` above is the only gate this path has, and
    # `budget.DAILY_REQUEST_CAP` counts REQUESTS because a free tier is rate-limited, not
    # billed. Nothing incremented that counter before: the guard was checked on every call
    # and advanced by none, so it could never fire however many went out. Same shape as
    # BUD-F13 -- a guard that reads correctly and cannot fire.
    if budget is not None:
        budget.record_call(0.0, model=model)
    return Proposal(facts=_parse(raw)), meta


def generate(prompt: str, *, origin, model: str = FLASH, budget=None,
             _transport=None) -> str:
    """A plain text-in/text-out call, under the same clearance as `extract`.

    `extract` returns a Proposal and is the only door this module had. `quoted_span`
    needs prose back, and routing it through `_post` would be the back door the AST
    ratchet in this file exists to keep shut -- so it gets a front door instead.

    `origin` here is an Origin or a tuple of them, and the check is `verify_prompt`:
    every DELIMITED untrusted block in the prompt must clear against one of them. That
    is the multi-source form of the same rule. Everything outside the delimiters is our
    own instructions; everything inside has to be published, and a prompt with no
    delimiters at all is refused, because then nothing in it can be told apart.
    """
    from checker.public_only import refuse_matter, verify_prompt
    refuse_matter(origin)          # PLAN_22 D3 -- never a matter document, see extract()
    verify_prompt(prompt, origin)

    if budget is not None:
        # The verdict's own reason, not a generic one: "budget exhausted" sent a reader to
        # the rupee ledger for what is usually the provider's per-model request quota, and
        # those two have different remedies -- one needs money, the other needs tomorrow.
        _v = _free_quota_verdict(budget, model)
        if not _v.allowed:
            raise ModelUnavailable(f"no call was made -- {_v.reason}")

    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0, "maxOutputTokens": 4096}}
    data = (_transport or _post)(model, payload)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise ModelRefused(
            f"no usable candidate in the response: {json.dumps(data)[:200]}") from None
    if budget is not None:
        budget.record_call(0.0, model=model)
    return "".join(p.get("text", "") for p in parts)


def as_text_model(*, origin, model: str = FLASH, budget=None, _transport=None):
    """`generate` as the Callable[[str], str] that `quoted_span.summarise` takes.

    The clearance is bound once, here, by the caller that knows which published files the
    evidence came from -- the same reason `as_shadow_model` takes one.
    """
    if origin is None:
        raise TypeError("as_text_model(origin=...) is required")

    def _m(prompt: str) -> str:
        return generate(prompt, origin=origin, model=model, budget=budget,
                        _transport=_transport)
    return _m


def as_shadow_model(budget=None, model: str = FLASH, _transport=None, *, origin=None):
    """Same callable shape `shadow.run()` already scores. Swap providers freely.

    `shadow.run()` hands the callable a bare document string, so the clearance cannot be
    derived per call here. It is bound once, when the adapter is built, by the caller that
    knows which published file the cases came out of -- and it is still REQUIRED: an
    adapter built without one refuses at construction rather than at the first call, so a
    harness cannot get halfway through a run before discovering it has no clearance.
    """
    if origin is None:
        raise TypeError(
            "as_shadow_model(origin=...) is required: the callable it returns takes a bare "
            "string, so the published file the text came from has to be named here")

    def _m(document: str) -> Proposal:
        proposal, _ = extract(document, origin=origin, budget=budget, model=model,
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

    # ── every call below carries a real public-corpus clearance ──────────────
    # Not a stub. `extract` re-reads the file named in the Origin, so a fake would be
    # refused -- which is the property being relied on, and the reason these tests use a
    # slice of an actually-published file rather than the string "doc".
    from checker import public_only
    _PUB = (public_only.ROOT / "corpus" / "testdocs" / "agm_notices"
            / "tcpl_63rd_agm_notice_2026.txt")
    _full = _PUB.read_text()
    _at = _full.index("Shriram Capital Private Limited")
    DOC = _full[_at - 200:_at + 200]
    ORIGIN = public_only.clear_text(DOC, path=_PUB)

    # ── the prompt is IDENTICAL to the Anthropic extractor's ─────────────────
    from checker.anthropic_model import _EXTRACT_SYSTEM as ANTH_PROMPT
    check(_EXTRACT_SYSTEM is ANTH_PROMPT,
          "both providers get the SAME instruction — so a score difference is a "
          "difference in the model, not in what it was asked")

    # ── no key: refuse, never blank ──────────────────────────────────────────
    held = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY",
                                                  "GOOGLE_CLOUD_PROJECT")}
    try:
        check(not available(), "with no key, available() is False")
        try:
            extract(DOC, origin=ORIGIN)
            check(False, "with no key, extract() raises")
        except ModelUnavailable as e:
            check("indistinguishable from a document with nothing in it" in str(e),
                  "with no key it raises, and says why a blank would be worse")
    finally:
        for k, v in held.items():
            if v is not None:
                os.environ[k] = v

    # ── a fake transport proves the path without a key or a call ─────────────
    # The span the fake model "quotes" is a verbatim slice of DOC, because
    # `shadow.run()` scores an answer as CAUGHT when its span is not in the document --
    # correctly. A hand-written span stopped being in the document the moment these
    # tests started using real published text, which is the harness doing its job.
    _SPAN = "Shriram Capital Private Limited"
    GOOD = {"candidates": [{"content": {"parts": [{"text": json.dumps(
              {"facts": {"company_class": {"value": "private", "span": _SPAN}}})}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 60}}
    seen = {}

    def fake(model, payload, timeout=90):
        seen["model"], seen["payload"] = model, payload
        return GOOD

    prop, meta = extract(DOC, origin=ORIGIN, _transport=fake)
    check(prop.facts["company_class"]["span"] == _SPAN,
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
        extract(DOC, origin=ORIGIN, _transport=blocked)
        check(False, "a blocked/empty candidate is refused")
    except ModelRefused as e:
        check("no usable candidate" in str(e),
              "a blocked or empty candidate is refused, not read as an empty document")

    def prose(model, payload, timeout=90):
        return {"candidates": [{"content": {"parts": [{"text":
                 "I could not find any structured facts, sorry!"}]}}]}
    try:
        extract(DOC, origin=ORIGIN, _transport=prose)
        check(False, "prose with no JSON is refused")
    except ModelRefused:
        check(True, "prose with no JSON is refused, not salvaged")

    # ── budget guard fires before the call ───────────────────────────────────
    class Broke:
        # A REAL Verdict, not a bare `False`. The bare False this used to return is a type
        # BudgetTracker never produces, and returning it is what hid the fail-open: the
        # guard read `not <falsy>` here and `not <always-truthy Verdict>` in production.
        def can_make_call(self, *a, **k):
            from backend.budget import Verdict
            return Verdict(False, "budget", "monthly cap reached", 0.0, 3_500.0)
    called = []
    def spy(model, payload, timeout=90):
        called.append(1); return GOOD
    try:
        extract(DOC, origin=ORIGIN, budget=Broke(), _transport=spy)
        check(False, "an exhausted budget refuses before the call")
    except ModelUnavailable:
        check(not called, "an exhausted budget refuses BEFORE the call — none was made")

    # ── a matter document never reaches the free tier (PLAN_22 D3) ──────────
    _matter = public_only.clear_matter(
        "CONFIDENTIAL: Acme Private Limited and Beta Limited, term three years.",
        name="nda.docx", provider="azure")
    called.clear()
    try:
        extract(DOC, origin=_matter, _transport=spy)
        check(False, "extract refuses a matter origin")
    except public_only.NotPublic:
        check(not called,
              "extract() REFUSES an origin cleared for Azure and sends nothing -- the "
              "clearance was for a different provider and passing it on does not launder it")
    called.clear()
    try:
        generate("anything", origin=_matter, _transport=spy)
        check(False, "generate refuses a matter origin")
    except public_only.NotPublic:
        check(not called, "...and so does generate(), the prose door")

    # ── the free tier's own daily quota, on a REAL ledger and not a stub ─────
    from backend.budget import FREE_TIER_RPD_PER_MODEL as _RPD, BudgetTracker as _BT
    from datetime import date as _date

    class _Mem:
        def __init__(self): self.d = {}
        def read(self): return dict(self.d)
        def write(self, data): self.d = dict(data)

    _led = _BT(_Mem(), today=_date(2026, 9, 29))
    called.clear()
    extract(DOC, origin=ORIGIN, budget=_led, model=FLASH, _transport=spy)
    check(len(called) == 1, f"a first free-tier call is served and counted ({len(called)})")
    for _ in range(_RPD - 1):
        _led.record_call(0.0, model=FLASH)
    called.clear()
    try:
        extract(DOC, origin=ORIGIN, budget=_led, model=FLASH, _transport=spy)
        check(False, f"the {_RPD}th free-tier request of the day refuses")
    except ModelUnavailable as e:
        check(not called and "per-model daily quota" in str(e),
              f"at {_RPD} requests today this model refuses BEFORE the call, naming the "
              f"provider's quota -- the calls cost Rs 0 and are still refused, because the "
              f"next one returns 429 ({str(e)[:60]})")
    called.clear()
    extract(DOC, origin=ORIGIN, budget=_led, model=FLASH_LITE, _transport=spy)
    check(len(called) == 1,
          "...and the FALLBACK model is still served: the quota is per model per project, "
          "so router.py's second Gemini row is another 20, not a share of the same 20")

    # ── retired is not busy, and the old pin was retired ─────────────────────
    check(FLASH_LITE != "gemini-2.5-flash-lite",
          f"FLASH_LITE is off the pin that 404s for new keys ({FLASH_LITE})")
    retired = _classify_http(FLASH_LITE, 404, "no longer available to new users")
    busy = _classify_http(FLASH, 503, "This model is currently experiencing high demand.")
    check(isinstance(retired, ModelRetired) and not isinstance(retired, ModelBusy),
          "a 404 is a RETIRED model -- no retry fixes it")
    check(isinstance(busy, ModelBusy) and not isinstance(busy, ModelRetired),
          "a 503 is a BUSY model -- the same call may succeed shortly")
    check("repoint the constant" in str(retired),
          "...and the retired message says what a person has to do, since no retry will")
    check("the pin is still correct" in str(busy),
          "...while the busy one says the pin is fine, so nobody repoints on a blip")
    check(isinstance(retired, ModelUnavailable) and isinstance(busy, ModelUnavailable),
          "both remain ModelUnavailable, so every existing `except` still catches them")
    _rl = _classify_http(FLASH, 429, "quota")
    check(isinstance(_rl, ModelRateLimited) and "tokens-per-minute" in str(_rl),
          "429 is a rate limit, carrying RATE_NOTE")
    check(not isinstance(_rl, ModelBusy) and not isinstance(busy, ModelRateLimited),
          "...and it is NOT ModelBusy: a 503 wants a retry sideways to the next model, "
          "a 429 wants a wait, and retrying sideways spends the next model's quota too")
    check(isinstance(_rl, ModelUnavailable),
          "...while still being ModelUnavailable, so existing handlers are unchanged")
    check(type(_classify_http(FLASH, 500, "boom")) is ModelUnavailable,
          "an unclassified status is plain ModelUnavailable, not guessed into a category")

    # ── a successful free call is RECORDED, or the request cap never fires ──
    # The refusal check above proves the gate is read. It cannot prove the counter moves,
    # and a counter that never moves makes budget.DAILY_REQUEST_CAP unreachable -- the one
    # cap that binds a provider charging nothing.
    class Ledger:
        def __init__(self): self.calls = []
        def can_make_call(self, *a, **k):
            from backend.budget import Verdict
            return Verdict(True, "normal", "within budget", 0.0, 0.0)
        def record_call(self, inr, **k): self.calls.append(inr)
    led = Ledger()
    extract(DOC, origin=ORIGIN, budget=led, _transport=lambda m, pay, timeout=90: GOOD)
    check(led.calls == [0.0],
          f"a successful free call consumes one request at Rs 0.00 ({led.calls})")

    # ── it plugs into the same harness, unchanged ────────────────────────────
    from checker.bundles import capabilities
    from checker.shadow import CORRECT, ShadowCase, run, tally
    cases = (ShadowCase("G1", DOC, {"company_class": "private"}, "fake-transport case"),)
    res = run(cases, as_shadow_model(_transport=fake, origin=ORIGIN),
              declared_intents=capabilities(), verified_text="")
    check(tally(res)[CORRECT] == 1,
          f"Gemini scores through the SAME shadow harness as Anthropic "
          f"({res[0].outcome}) — providers are comparable on one scale")

    # ── the Vault/matter path: enforced, and proved shut across the repo ─────
    # A client document sent while NAMING a published file. This is the shape a
    # provenance LABEL would wave through, and it is the one that matters: the text is
    # checked against the file, so the name buys nothing.
    from checker.public_only import NotPublic
    untouched = []
    def _never(model, payload, timeout=90):
        untouched.append(1); return GOOD
    try:
        extract("The Board of Acme Private Limited resolved to acquire Beta Ltd for "
                "Rs 40 crore, subject to due diligence.", origin=ORIGIN, _transport=_never)
        check(False, "a matter document under a public Origin is refused")
    except NotPublic as e:
        check("is not in" in str(e) and not untouched,
              "a matter document sent under a real public Origin is refused, and NO "
              "call was made -- the check runs before the transport, not after")

    class _FakeOrigin:
        basis, path, blob = "PUBLIC_CORPUS", "corpus/testdocs/MANIFEST.md", "0" * 40
    try:
        extract(DOC, origin=_FakeOrigin(), _transport=_never)
        check(False, "a look-alike origin object is refused")
    except NotPublic as e:
        check("Origin is required" in str(e) and not untouched,
              "an object that merely LOOKS like an Origin is refused -- duck typing is "
              "not a clearance")

    # And the guard must not be reachable around: `origin` has no default, so a call
    # site that forgets it fails at import-time signature binding rather than sending.
    import inspect as _inspect
    _sig = _inspect.signature(extract)
    check(_sig.parameters["origin"].default is _inspect.Parameter.empty
          and _sig.parameters["origin"].kind is _inspect.Parameter.KEYWORD_ONLY,
          "origin= is keyword-only and has NO default -- a safe-looking default is a "
          "keyword nobody passes")
    try:
        as_shadow_model(_transport=fake)   # public-origin: deliberate
        check(False, "as_shadow_model without an origin is refused")
    except TypeError as e:
        check("required" in str(e),
              "as_shadow_model refuses at construction, so a harness cannot get halfway "
              "through a run before discovering it has no clearance")

    # ── the AST sweep: no call site anywhere reaches Gemini without one ──────
    # The signature above stops a forgotten keyword at runtime, on the call that runs.
    # This fails at gate time instead, for every call site in the tree at once --
    # including ones no test exercises, which is where the path would actually open.
    import ast as _ast
    from pathlib import Path as _Path
    _root = _Path(__file__).resolve().parent.parent
    _ENTRY = {"extract", "as_shadow_model", "generate", "as_text_model"}
    _WAIVER = "public-origin: deliberate"
    offenders, waived, swept = [], [], 0
    for f in sorted(_root.rglob("*.py")):
        if any(part in {".git", "__pycache__", ".claude"} for part in f.parts):
            continue
        try:
            tree = _ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        swept += 1
        # Which local names in this file mean gemini_model's entry points?
        local = set()
        gemini_alias = set()
        for n in _ast.walk(tree):
            if isinstance(n, _ast.ImportFrom) and (n.module or "").endswith("gemini_model"):
                local |= {(a.asname or a.name) for a in n.names if a.name in _ENTRY}
            if isinstance(n, _ast.Import):
                gemini_alias |= {(a.asname or a.name.split(".")[-1])
                                 for a in n.names if a.name.endswith("gemini_model")}
            if isinstance(n, _ast.ImportFrom) and (n.module or "") == "checker":
                gemini_alias |= {(a.asname or a.name) for a in n.names
                                 if a.name == "gemini_model"}
        if f.resolve() == _Path(__file__).resolve():
            local |= _ENTRY          # this module's own unqualified calls
        for n in _ast.walk(tree):
            if not isinstance(n, _ast.Call):
                continue
            fn = n.func
            hit = ((isinstance(fn, _ast.Name) and fn.id in local)
                   or (isinstance(fn, _ast.Attribute) and fn.attr in _ENTRY
                       and isinstance(fn.value, _ast.Name) and fn.value.id in gemini_alias))
            if hit and not any(k.arg == "origin" for k in n.keywords):
                where = f"{f.relative_to(_root)}:{n.lineno}"
                # One waiver marker, read off the line itself so it cannot drift from
                # the call it excuses. Ratcheted below: a second one fails the gate.
                if _WAIVER in f.read_text().splitlines()[n.lineno - 1]:
                    waived.append(where)
                    continue
                offenders.append(where)
    check(swept > 150, f"the sweep read the whole tree ({swept} modules)")
    check(len(waived) == 1 and waived[0].startswith("checker/gemini_model.py"),
          f"exactly one waiver exists, and it is the negative test above ({waived}) -- "
          f"a second one fails this check rather than passing quietly")
    check(not offenders,
          f"no call reaches a Gemini entry point without a public-corpus origin= "
          f"({len(offenders)} offender(s): {offenders[:4]})")
    # The sweep must be able to SEE an offender, or `not offenders` is vacuous.
    _probe = _ast.parse("from checker.gemini_model import extract\nextract(doc)\n")
    _calls = [n for n in _ast.walk(_probe) if isinstance(n, _ast.Call)]
    check(len(_calls) == 1 and not any(k.arg == "origin" for k in _calls[0].keywords),
          "...and the sweep's own shape detects a call written without origin=, so a "
          "clean result is a measurement rather than a pattern that matches nothing")

    # ── generate(): the front door for prose, under the same clearance ───────
    from checker.prompt_safety import wrap_untrusted as _wrap
    _act = public_only.ROOT / "corpus" / "companies_act" / "1220.json"
    _o = public_only.clear_file(_act)
    import json as _json
    _prov = _json.loads(_act.read_text())["content"][:300]
    _prompt = "Answer using only this.\n" + _wrap(_prov, "s1") + "\nWhat does it say?"
    _said = {"candidates": [{"content": {"parts": [{"text": "It says something."}]}}]}
    check(generate(_prompt, origin=_o, _transport=lambda m, p, timeout=90: _said)
          == "It says something.",
          "generate() returns prose, so quoted_span does not have to go through _post")
    _bad = ("Answer.\n" + _wrap("The Board of Acme Private Limited resolved to acquire "
                                "Beta Ltd.", "matter") + "\nWhat does it say?")
    _untouched = []
    try:
        generate(_bad, origin=_o, _transport=lambda m, p, t=90: _untouched.append(1))
        check(False, "a matter document in the prompt is refused")
    except NotPublic as e:
        check("is in none of the" in str(e) and not _untouched,
              "a matter document inside the prompt is refused, and no call was made")
    try:
        generate("Answer. " + _prov, origin=_o,
                 _transport=lambda m, p, t=90: _untouched.append(1))
        check(False, "an undelimited prompt is refused")
    except NotPublic as e:
        check("no delimited untrusted block" in str(e) and not _untouched,
              "...and evidence pasted in without delimiters is refused too, because "
              "nothing in it can be told from our own words")
    check(_inspect.signature(generate).parameters["origin"].default
          is _inspect.Parameter.empty,
          "generate()'s origin= has no default either")

    # ── the back door: _post takes a payload, so the text guard cannot see it ─
    # `extract()` is the guarded door. `_post()` is a hole beside it: it takes an
    # already-built payload, so no clearance is possible there and none is attempted.
    # That is acceptable only while every user of it is known and named. Listed here so
    # a new one fails the gate instead of quietly becoming the way round the guard.
    _POST_USERS = {"scripts/bakeoff_indic.py"}   # page IMAGES from a public benchmark
    found = set()
    for f in sorted(_root.rglob("*.py")):
        if (any(part in {".git", "__pycache__", ".claude"} for part in f.parts)
                or f.resolve() == _Path(__file__).resolve()):
            continue
        try:
            tree = _ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        # By reference, not by substring: `_PREFERENCE` and `_post_process` both contain
        # the characters and mean nothing. Only `<gemini alias>._post` or a direct
        # `from ...gemini_model import _post` counts.
        alias = set()
        for n in _ast.walk(tree):
            if isinstance(n, _ast.Import):
                alias |= {(a.asname or a.name.split(".")[-1])
                          for a in n.names if a.name.endswith("gemini_model")}
            if isinstance(n, _ast.ImportFrom):
                mod = n.module or ""
                if mod.endswith("gemini_model") and any(a.name == "_post" for a in n.names):
                    found.add(f.relative_to(_root).as_posix())
                if mod == "checker":
                    alias |= {(a.asname or a.name) for a in n.names if a.name == "gemini_model"}
        for n in _ast.walk(tree):
            if (isinstance(n, _ast.Attribute) and n.attr == "_post"
                    and isinstance(n.value, _ast.Name) and n.value.id in alias):
                found.add(f.relative_to(_root).as_posix())
    check(found == _POST_USERS,
          f"_post() is reached only from the files that are allowed to ({sorted(found)} "
          f"vs {sorted(_POST_USERS)}) -- it takes a payload, so no clearance is possible "
          f"there, and an unlisted user would be the way round extract()'s guard")

    # ── the rate-limit reality is recorded, not assumed ──────────────────────
    check("tokens-per-minute" in RATE_NOTE and "50x" in RATE_NOTE,
          "the free tier's binding limit is recorded, with the 50x error that "
          "reading requests-per-day caused here before")


    # ── E1: untrusted text is delimited, and the clause is carried ───────────
    from checker.prompt_safety import INJECTIONS
    captured = {}

    def _spy(model, payload, timeout=90):
        captured["payload"] = payload
        return {"candidates": [{"content": {"parts": [{"text": '{"facts": {}}'}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}

    hostile = ("Resolved that the Company do allot shares. "
               + INJECTIONS[0] + " Dated 14 June 2026.")
    # Proved on _payload, because hostile text has no published file to be cleared
    # against and inventing one would be the bypass this whole module exists to refuse.
    captured["payload"] = _payload(hostile)
    sent = captured["payload"]["contents"][0]["parts"][0]["text"]

    check(contains_untrusted_block(sent),
          "the document reaches Gemini inside <source> delimiters, not after a "
          "bare 'DOCUMENT:' label")
    check(INJECTIONS[0] in sent,
          "...carrying the injected instruction verbatim -- it is evidence about "
          "what the document says, and stripping it would be repairing a source")
    check(carries_clause(captured["payload"]["systemInstruction"]["parts"][0]["text"]),
          "...and the system instruction tells the model that <source> is never a "
          "command")
    check(hostile in sent,
          "the document text itself is byte-identical inside the block")
    extract(DOC, origin=ORIGIN, _transport=_spy)
    check(captured["payload"] == _payload(DOC),
          "...and extract() sends exactly what _payload() builds, so proving the "
          "delimiting there proves it on the wire")

    # ── Vertex AI: the same call, billed to a Cloud project, no API key ──────
    # The AI Studio free tier ran out mid-benchmark and blocked a re-run for a
    # day. Vertex sends the SAME payload against a project's quota instead.
    # Only the address and the credential differ -- never the prompt.
    import subprocess as _sp
    from unittest import mock

    names = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_PROJECT",
             "GOOGLE_CLOUD_LOCATION")
    held = {k: os.environ.pop(k, None) for k in names}
    tok = lambda: "ya29.test"                                          # noqa: E731
    try:
        os.environ["GOOGLE_CLOUD_PROJECT"] = "demo-proj"
        check(available(), "a Cloud project alone makes Gemini available -- no key")
        url, headers = _route(FLASH, _token=tok)
        check(url == ("https://aiplatform.googleapis.com/v1/projects/demo-proj/"
                      f"locations/global/publishers/google/models/{FLASH}"
                      ":generateContent"),
              f"with a project set, the call goes to Vertex AI, global by default "
              f"({url[:48]}...)")
        check("key=" not in url
              and headers.get("Authorization") == "Bearer ya29.test",
              "...signed with the caller's Google login; no API key in the URL")

        os.environ["GOOGLE_CLOUD_LOCATION"] = "asia-south1"
        url, _ = _route(FLASH, _token=tok)
        check(url.startswith("https://asia-south1-aiplatform.googleapis.com/v1/"
                             "projects/demo-proj/locations/asia-south1/"),
              "a regional location is sent to that region's host")

        with mock.patch.object(_sp, "run", side_effect=FileNotFoundError("gcloud")):
            try:
                _vertex_token()
                check(False, "no gcloud refuses")
            except ModelUnavailable as e:
                check("gcloud auth application-default login" in str(e),
                      "with no gcloud the Vertex route refuses, and names the login "
                      "command rather than returning a blank")
        failed = _sp.CompletedProcess(["gcloud"], 1, stdout="", stderr="reauth needed")
        with mock.patch.object(_sp, "run", return_value=failed):
            try:
                _vertex_token()
                check(False, "an expired login refuses")
            except ModelUnavailable as e:
                check("reauth needed" in str(e),
                      "an expired login refuses with gcloud's own reason")

        os.environ.pop("GOOGLE_CLOUD_PROJECT")
        os.environ.pop("GOOGLE_CLOUD_LOCATION")
        os.environ["GEMINI_API_KEY"] = "k-test"
        url, headers = _route(FLASH, _token=tok)
        check(url.startswith("https://generativelanguage.googleapis.com/")
              and url.endswith("?key=k-test") and "Authorization" not in headers,
              "with no project, the AI Studio key route is unchanged")
    finally:
        for k in names:
            os.environ.pop(k, None)
        for k, v in held.items():
            if v is not None:
                os.environ[k] = v

    print(f"\n{ok}/{ok + fail} passed")


if __name__ == "__main__":
    _test()
