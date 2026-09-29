"""Azure AI as a model host: the deployments this laptop cannot hold.

The operator's machine has 8.6 GB of unified memory. A 12B model ran Ollama out of GPU
memory on 14-09-2026, so "fall back to the local model" is not a fallback for real work --
it is a fallback to an 8B model or to nothing. Azure is where a model of a useful size
actually runs, and `router.py` therefore routes to it rather than merely measuring with
it, which is the line `eval/realrun/azure_model.py` does not cross.

## Why the HTTP core moved here

`eval/realrun/azure_model.py` called Azure first, and nothing in `checker/` may import it:
an engine module reaching into the eval harness is the import direction `rings.py` exists
to prevent. So the endpoint allowlist, the request and the reply discipline live here,
once, and the eval adapter imports them -- the direction that is allowed, and the same
shape `scripts/ingest_companies_act.py` has over `ingest_act.py`. Two copies of an
endpoint allowlist is how one of them quietly grows a host the other refuses.

## Why `narrate` is a front door and not a transport

`origin` is REQUIRED and has no default, and the prompt is cleared by
`public_only.verify_prompt` before a socket is opened. Azure is a third party. It is a
PAID deployment rather than a free tier, so the twenty-requests-a-day ceiling
(`backend/budget.FREE_TIER_RPD_PER_MODEL`) does not bind here -- but the clearance is not
about who is billed for reading the text, it is about what leaves this repository, so it
binds identically. A Vault or matter document reaching Azure is the same breach as one
reaching Gemini, and the AST sweep in `_test` reads the whole tree to say so.

## What it refuses to turn into an answer

A reply that did not finish (`finish_reason` other than "stop") raises rather than
returning the fragment: a truncated answer is not a short answer. A content-filter stop is
a refusal and says so.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

from checker.anthropic_model import ModelRefused, ModelUnavailable
from checker.env import load as _load_env

_load_env()

PREFIX = "azure:"

# Llama-3.3-70B rather than gpt-5-mini: measured 28-09-2026 on the realrun probes, the
# 70B answered 18 of 18 cases with 0 errors where gpt-5-mini errored on 1 of 17, and a
# reasoning model spends hidden tokens on a job whose whole point is obedience.
DEFAULT_DEPLOYMENT = "llama-3-3-70b"

# Reasoning models accept only the default temperature (gpt-5-mini answers temperature=0
# with HTTP 400 "unsupported_value") and spend hidden reasoning tokens against the
# completion limit, so they get no temperature and a larger budget.
_REASONING = ("gpt-5", "o1", "o3", "o4")
REASONING_BUDGET = 4000
COMPLETION_BUDGET = 700

# Narration needs its own, and 700 was measured too small on 29-09-2026: the first live
# pass of the research fixtures refused F5 (s.134, what must be attached to financial
# statements) with finish_reason='length'. 700 is the limit local_model gives Ollama for
# EXTRACTION, where the reply is one JSON object; a narration reply is a sentence and its
# verbatim quote per proposition, so a long provision answers longer than the thing it
# quotes. 4096 is what gemini_model.generate already allows, and matching it keeps a
# difference between the two providers a difference in the models rather than in what they
# were allowed to say. The refusal was correct -- a truncated answer is not a short answer
# -- so this raises the ceiling and does not soften the guard.
NARRATION_BUDGET = 4096

# A reasoning deployment is slower by construction, not by accident: it spends hidden
# reasoning tokens before it emits the first visible one. Measured 29-09-2026 -- gpt-5-mini
# answered fixtures F1 and F2 and then exceeded 180s on F3, mid-run. 180s is right for a
# 70B that starts emitting immediately and wrong for a model that thinks first, so the
# default is chosen per deployment family rather than shared. An explicit timeout= still wins.
DEFAULT_TIMEOUT = 180
REASONING_TIMEOUT = 600


def default_timeout(deployment: str) -> int:
    return REASONING_TIMEOUT if deployment.startswith(_REASONING) else DEFAULT_TIMEOUT

# The key is sent in a header, so the endpoint is checked before it is used.
_AZURE_HOSTS = (".openai.azure.com", ".services.ai.azure.com",
                ".cognitiveservices.azure.com")


def available() -> bool:
    return bool(os.getenv("AZURE_AI_API_KEY") and os.getenv("AZURE_AI_ENDPOINT"))


def _url() -> str:
    base = os.getenv("AZURE_AI_ENDPOINT") or ""
    u = urlparse(base)
    if u.scheme != "https" or not (u.hostname or "").endswith(_AZURE_HOSTS):
        raise ModelUnavailable(
            f"AZURE_AI_ENDPOINT={base!r} is not an https Azure AI host; refusing "
            f"to send the key to it")
    return f"https://{u.hostname}/openai/v1/chat/completions"


def chat_body(prompt: str, deployment: str, *,
              max_tokens: int = COMPLETION_BUDGET) -> dict:
    """The request for one prompt. Shared so eval and the engine ask identically.

    `max_tokens` defaults to the extraction budget, so the eval harness is unchanged.
    """
    body = {"model": deployment, "messages": [{"role": "user", "content": prompt}]}
    if deployment.startswith(_REASONING):
        # Hidden reasoning is billed against this limit too, so it takes whichever is
        # larger rather than the caller's figure alone.
        return body | {"max_completion_tokens": max(REASONING_BUDGET, max_tokens)}
    return body | {"max_tokens": max_tokens, "temperature": 0}


def reply_text(data: dict) -> str:
    """The text of a finished reply, or raise. A truncated reply is not an answer."""
    try:
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise ModelUnavailable(
            f"no choice in the Azure reply: {json.dumps(data)[:200]}") from None
    finish = choice.get("finish_reason")
    if finish == "content_filter":
        raise ModelRefused("Azure content filter stopped the reply")
    if finish != "stop":
        raise ModelUnavailable(
            f"the Azure reply did not finish (finish_reason={finish!r}); a "
            f"truncated reply is not an answer")
    return text


def _call(body: dict, key: str, timeout: int) -> dict:
    from checker.robots import ssl_context
    ctx = ssl_context()
    if ctx is None:
        raise ModelUnavailable("no CA trust store on this machine, so the Azure "
                               "endpoint cannot be authenticated. Refusing.")
    req = urllib.request.Request(
        _url(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace")[:200]
        raise ModelUnavailable(f"Azure HTTP {e.code}: {body_text}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelUnavailable(f"Azure unreachable: {e}") from None


def narrate(prompt: str, *, origin, model: str = DEFAULT_DEPLOYMENT, budget=None,
            timeout: int | None = None, _transport=None) -> str:
    """A plain text-in/text-out call to Azure, under `public_only` clearance.

    `origin` is an Origin or a tuple of them, and the check is `verify_prompt`: every
    DELIMITED untrusted block in the prompt must clear against one of them. Everything
    outside the delimiters is our own instructions; everything inside has to be published.
    A prompt with no delimiters at all is refused, because then nothing in it can be told
    apart. The clearance runs BEFORE the key is read and before the socket is opened, so a
    refusal costs no request and leaks nothing.
    """
    from checker.public_only import verify_prompt
    verify_prompt(prompt, origin)

    if budget is not None and not budget.can_make_call().allowed:
        raise ModelUnavailable("budget exhausted; no call was made")

    deployment = model.removeprefix(PREFIX)
    if timeout is None:
        timeout = default_timeout(deployment)
    # NARRATION_BUDGET for every deployment, reasoning ones included, and that is a
    # MEASURED choice rather than the obvious one. On a reasoning model
    # max_completion_tokens is a THINKING budget and not merely an output cap: the model
    # spends what it is given. Both settings were run over the ten research fixtures on
    # 29-09-2026 (reports/fixtures_azure_2026-09-29.json, `reasoning_budget_experiment`):
    #
    #   4096  ANSWERED 5  PARTIAL 0  dropped 0   157s   1 truncation (F4)
    #   8192  ANSWERED 3  PARTIAL 1  dropped 1  1169s   2 transport failures
    #
    # Seven and a half times the wall clock, fewer complete answers, and two connection
    # drops -- to avoid one truncation, which `reply_text` turns into a REFUSAL rather
    # than a fragment. The safe failure was cheaper than the cure. Left at 4096 until a
    # bake-off with intervals says otherwise; n=1 per setting is not a finding.
    body = chat_body(prompt, deployment, max_tokens=NARRATION_BUDGET)
    if _transport is not None:
        data = _transport(deployment, body)
    else:
        key = os.getenv("AZURE_AI_API_KEY")
        if not key:
            raise ModelUnavailable(
                "AZURE_AI_API_KEY is not set. This refuses rather than returning an "
                "empty string, because a blank answer is indistinguishable from a "
                "model that had nothing to say.")
        data = _call(body, key, timeout)

    text = reply_text(data)
    if budget is not None:
        budget.record_call(0.0)
    return text


def as_text_model(*, origin, model: str = DEFAULT_DEPLOYMENT, budget=None,
                  _transport=None):
    """`narrate` as the Callable[[str], str] that `quoted_span.summarise` takes.

    The clearance is bound once, here, by the caller that knows which published files the
    evidence came from -- the same reason `gemini_model.as_text_model` takes one.
    """
    if origin is None:
        raise TypeError("as_text_model(origin=...) is required")

    def _m(prompt: str) -> str:
        return narrate(prompt, origin=origin, model=model, budget=budget,
                       _transport=_transport)
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

    # ── the endpoint allowlist, which is why the key is safe to send ──────────
    held = {k: os.environ.pop(k, None) for k in ("AZURE_AI_API_KEY", "AZURE_AI_ENDPOINT")}
    try:
        check(not available(), "with neither key nor endpoint it is unavailable")
        os.environ["AZURE_AI_API_KEY"] = "k-test"
        check(not available(), "...a key alone is not enough: there is nowhere to send it")
        os.environ["AZURE_AI_ENDPOINT"] = "https://collector.example.com/"
        check(available(), "...key and endpoint together read as available")
        try:
            _url()
            check(False, "a non-Azure endpoint is refused")
        except ModelUnavailable as e:
            check("not an https Azure AI host" in str(e),
                  "a non-Azure endpoint is refused BEFORE the key is put in a header")
        os.environ["AZURE_AI_ENDPOINT"] = "http://placedon-law-eval.openai.azure.com/"
        try:
            _url()
            check(False, "plain http to a real Azure host is refused")
        except ModelUnavailable:
            check(True, "...and so is plain http to a real Azure host: the host is not "
                        "the only thing that protects the key")
        os.environ["AZURE_AI_ENDPOINT"] = "https://placedon-law-eval.openai.azure.com/"
        check(_url() == ("https://placedon-law-eval.openai.azure.com"
                         "/openai/v1/chat/completions"),
              "a real Azure host resolves to the chat-completions path")
    finally:
        for k, v in held.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    # ── the request, per deployment family ───────────────────────────────────
    b70 = chat_body("hello", "llama-3-3-70b")
    b5 = chat_body("hello", "gpt-5-mini")
    check(b70["temperature"] == 0 and b70["max_tokens"] == COMPLETION_BUDGET,
          "an ordinary deployment gets temperature 0 and a token cap")
    check(chat_body("hello", "llama-3-3-70b",
                    max_tokens=NARRATION_BUDGET)["max_tokens"] == NARRATION_BUDGET
          and NARRATION_BUDGET > COMPLETION_BUDGET,
          "narration asks for a larger budget than extraction: a reply that is one "
          "sentence-plus-quote per proposition runs longer than one JSON object, and 700 "
          "truncated a real answer about s.134 on 29-09-2026")
    check("temperature" not in b5 and b5["max_completion_tokens"] == REASONING_BUDGET,
          "a reasoning deployment gets NO temperature (it answers 400) and a larger "
          "budget, because its hidden reasoning is billed against the completion limit")

    # ── what is not an answer ────────────────────────────────────────────────
    good = {"choices": [{"message": {"content": "It says something."},
                          "finish_reason": "stop"}]}
    check(reply_text(good) == "It says something.", "a finished reply is its text")
    for finish, kind, why in (("length", ModelUnavailable, "a truncated reply"),
                              ("content_filter", ModelRefused, "a filtered reply")):
        cut = {"choices": [{"message": {"content": "It sa"}, "finish_reason": finish}]}
        try:
            reply_text(cut)
            check(False, f"{why} is not returned as an answer")
        except kind:
            check(True, f"{why} raises {kind.__name__} rather than returning the fragment")
    try:
        reply_text({"choices": []})
        check(False, "an empty choices list is refused")
    except ModelUnavailable:
        check(True, "an empty choices list is refused, not read as an empty answer")

    # ── the firewall: this is the reason narrate exists rather than _call ─────
    from checker import public_only
    from checker.prompt_safety import wrap_untrusted as _wrap
    _act = public_only.ROOT / "corpus" / "companies_act" / "1220.json"
    _o = public_only.clear_file(_act)
    _prov = json.loads(_act.read_text())["content"][:300]
    cleared = "Answer using only this.\n" + _wrap(_prov, "s1") + "\nWhat does it say?"

    sent: list[tuple] = []

    def spy(deployment, body):
        sent.append((deployment, body))
        return good

    out = narrate(cleared, origin=_o, _transport=spy)
    check(out == "It says something." and len(sent) == 1,
          "a prompt whose every delimited block is published goes through")
    check(sent[0][0] == DEFAULT_DEPLOYMENT,
          f"...to the measured default deployment ({DEFAULT_DEPLOYMENT})")
    sent.clear()
    narrate(cleared, origin=_o, model="gpt-5-mini", _transport=spy)
    check(sent[0][1]["max_completion_tokens"] == NARRATION_BUDGET,
          f"a reasoning deployment gets the SAME narration budget "
          f"({sent[0][1]['max_completion_tokens']}), because that limit is a thinking "
          f"budget it will spend: doubling it cost 7.5x the wall clock and two connection "
          f"drops to avoid one truncation that was already a safe refusal")
    check(chat_body("x", "gpt-5-mini")["max_completion_tokens"] == REASONING_BUDGET,
          "...while chat_body's own default is unchanged, so the eval harness still asks "
          "exactly what it asked before")
    sent.clear()
    narrate(cleared, origin=_o, _transport=spy)
    check(default_timeout("llama-3-3-70b") == DEFAULT_TIMEOUT
          and default_timeout("gpt-5-mini") == REASONING_TIMEOUT
          and REASONING_TIMEOUT > DEFAULT_TIMEOUT,
          "a reasoning deployment gets a longer default timeout: it thinks before it "
          "emits, and gpt-5-mini exceeded 180s on fixture F3 on 29-09-2026")
    check(sent[0][1]["max_tokens"] == NARRATION_BUDGET,
          f"...asking for the NARRATION budget, not the extraction one "
          f"({sent[0][1]['max_tokens']}): this is the line that was 700, and F5 came "
          f"back finish_reason='length' because of it")

    sent.clear()
    secret = "Answer using only this.\n" + _wrap(
        "PRIVILEGED memo: the board resolved to acquire Target Ltd for Rs 40 crore.",
        "s1") + "\nWhat does it say?"
    try:
        narrate(secret, origin=_o, _transport=spy)
        check(False, "an unpublished block is refused")
    except public_only.NotPublic:
        check(not sent,
              "an unpublished block is refused and NOTHING was sent -- the clearance "
              "runs before the transport, so a refusal costs no request and leaks nothing")

    sent.clear()
    try:
        narrate("no delimiters at all", origin=_o, _transport=spy)
        check(False, "an undelimited prompt is refused")
    except public_only.NotPublic:
        check(not sent, "an undelimited prompt is refused: either the evidence was "
                        "concatenated unwrapped, or there is none, and the first is what "
                        "this exists to catch")

    try:
        # public-origin: deliberate -- this call omits origin ON PURPOSE, to prove a
        # caller cannot omit it and be served. The waiver is what the sweep reads.
        narrate(cleared, _transport=spy)   # type: ignore[call-arg]  public-origin: deliberate
        check(False, "origin is required")
    except TypeError:
        check(True, "origin has no default, so a caller cannot forget it and be served")
    try:
        as_text_model(origin=None)
        check(False, "as_text_model(origin=None) is refused")
    except TypeError:
        check(True, "...and as_text_model refuses a None origin rather than binding it")

    check(as_text_model(origin=_o, _transport=spy)(cleared) == "It says something.",
          "as_text_model binds the clearance once and returns a Callable[[str], str]")

    # ── no back door: the whole tree, the same ratchet gemini_model carries ───
    import ast as _ast
    from pathlib import Path as _Path
    _root = _Path(__file__).resolve().parent.parent
    _ENTRY = {"narrate", "as_text_model"}
    _WAIVER = "public-origin: deliberate"
    offenders, swept = [], 0
    for f in sorted(_root.rglob("*.py")):
        if any(p in {".git", "__pycache__", ".venv", "venv"} for p in f.parts):
            continue
        try:
            src = f.read_text()
            tree = _ast.parse(src)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        swept += 1
        lines = src.splitlines()
        local: set[str] = set()
        azure_alias = {"azure_model"}
        for n in _ast.walk(tree):
            if isinstance(n, _ast.ImportFrom) and (n.module or "").endswith("azure_model"):
                local |= {(a.asname or a.name) for a in n.names if a.name in _ENTRY}
            if isinstance(n, _ast.Import):
                azure_alias |= {(a.asname or a.name.split(".")[-1])
                                for a in n.names if a.name.endswith("azure_model")}
            if isinstance(n, _ast.ImportFrom) and (n.module or "") == "checker":
                azure_alias |= {(a.asname or a.name)
                                for a in n.names if a.name == "azure_model"}
        if f.resolve() == _Path(__file__).resolve():
            local |= _ENTRY              # this module's own unqualified calls
        for n in _ast.walk(tree):
            if not isinstance(n, _ast.Call):
                continue
            fn = n.func
            hit = ((isinstance(fn, _ast.Name) and fn.id in local)
                   or (isinstance(fn, _ast.Attribute) and fn.attr in _ENTRY
                       and isinstance(fn.value, _ast.Name) and fn.value.id in azure_alias))
            if not hit:
                continue
            if any(k.arg == "origin" for k in n.keywords):
                continue
            line = lines[n.lineno - 1] if n.lineno - 1 < len(lines) else ""
            if _WAIVER in line:
                continue
            offenders.append(f"{f.relative_to(_root)}:{n.lineno}")
    check(swept > 150, f"the sweep read the whole tree ({swept} modules)")
    check(not offenders,
          f"every call into Azure names an origin, tree-wide: {offenders[:3]}")

    # ...and the ratchet must be able to bite, or the two checks above are decoration.
    _probe = _ast.parse("from checker.azure_model import narrate\nnarrate(p)\n")
    _bound = {"narrate"}
    _bad = [n for n in _ast.walk(_probe)
            if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
            and n.func.id in _bound and not any(k.arg == "origin" for k in n.keywords)]
    check(len(_bad) == 1,
          "a synthetic origin-less call IS caught by the same rule -- the sweep is not "
          "passing because it matches nothing")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
