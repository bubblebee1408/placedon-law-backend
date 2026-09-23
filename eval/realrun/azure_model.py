"""Models too large for the laptop, served from Azure AI Foundry.

The laptop has 8.6 GB of unified memory. mistral-nemo (12B) ran Ollama out of GPU
memory on 14-09-2026, so the realrun probes could only ever measure models of 8B
and under. This adapter reaches larger ones -- gpt-5-mini and Llama-3.3-70B --
deployed on the `placedon-law-eval` resource (UAE North, Azure for Students).

Same contract as `local_model.extract`: (Proposal, meta). Same prompt and the
same reply parser, both imported rather than copied, so a difference between two
models is a difference in what the models said -- never in what they were asked
or how their replies were read.

Like `local_model`, this is a MEASURING adapter. `router.py` routes nothing here.

## What it refuses to turn into an answer

A reply that did not finish (`finish_reason` other than "stop") raises: a JSON
object cut off at the token limit parses as nothing, and an empty Proposal from a
case that "ran" is the error `local_model` already made once with Ollama's
out-of-memory replies. A content-filter stop is a refusal and says so.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from checker.anthropic_model import ModelRefused, ModelUnavailable  # noqa: E402
from checker.env import load as _load_env                           # noqa: E402
from checker.reasoning import Proposal                              # noqa: E402
from eval.realrun.local_model import _prompt, parse_reply           # noqa: E402

_load_env()

PREFIX = "azure:"

# Reasoning models accept only the default temperature (gpt-5-mini answers
# temperature=0 with HTTP 400 "unsupported_value") and spend hidden reasoning
# tokens against the completion limit, so they get no temperature and a larger
# budget. The temperature actually sent is recorded in meta, never assumed.
_REASONING = ("gpt-5", "o1", "o3", "o4")
REASONING_BUDGET = 4000
COMPLETION_BUDGET = 700          # the same limit local_model gives Ollama

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


def payload(document: str, deployment: str) -> dict:
    body = {"model": deployment,
            "messages": [{"role": "user", "content": _prompt(document)}]}
    if deployment.startswith(_REASONING):
        return body | {"max_completion_tokens": REASONING_BUDGET}
    return body | {"max_tokens": COMPLETION_BUDGET, "temperature": 0}


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


def extract(document: str, *, model: str, timeout: int = 180
            ) -> tuple[Proposal, dict]:
    """`model` is `azure:<deployment>`. Same contract as local_model.extract."""
    key = os.getenv("AZURE_AI_API_KEY")
    if not key:
        raise ModelUnavailable(
            "AZURE_AI_API_KEY is not set. This refuses rather than returning an "
            "empty extraction, because a blank result is indistinguishable from a "
            "document with nothing in it.")
    body = payload(document, model.removeprefix(PREFIX))
    data = _call(body, key, timeout)

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

    proposal, parse, raw = parse_reply(text)
    usage = data.get("usage") or {}
    # tokens_in as well as out: a run whose cost is reported must report the side
    # of the bill that a 60-page AGM notice actually moves. Azure returns it as
    # `prompt_tokens`; absent from a reply, it stays None rather than becoming 0,
    # because an unmeasured cost is not a zero cost.
    meta = {"model": model, "served_by": data.get("model"), "parse": parse,
            "temperature": body.get("temperature"),
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens")}
    return proposal, meta | ({"raw": raw[:200]} if parse != "OK" else {})


def _test() -> None:
    """Stubs only: no key is read from .env and no request leaves the machine."""
    import io
    from unittest import mock

    from eval.realrun import local_model

    ok = fail = 0

    def chk(cond, label):
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [ok]   {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("azure_model")
    names = ("AZURE_AI_API_KEY", "AZURE_AI_ENDPOINT")
    held = {k: os.environ.pop(k, None) for k in names}
    sent: list = []

    def replies(body: dict):
        def fake(req, timeout=None, context=None):
            sent.append(req)
            return io.BytesIO(json.dumps(body).encode())
        return mock.patch.object(urllib.request, "urlopen", side_effect=fake)

    def reply(content: str, finish: str = "stop") -> dict:
        return {"model": "Llama-3.3-70B-Instruct",
                "choices": [{"message": {"content": content},
                             "finish_reason": finish}],
                "usage": {"completion_tokens": 42}}

    good = reply('{"facts": {"cin": {"value": "U74999KA2019PTC123456", '
                 '"span": "CIN U74999KA2019PTC123456"}}}')
    trust = mock.patch("checker.robots.ssl_context", return_value=object())
    try:
        with trust:
            # ── no key: refuse, never blank ──────────────────────────────────
            try:
                with replies(good):
                    extract("doc", model="azure:llama-3-3-70b")
                chk(False, "with no key, extract() raises")
            except ModelUnavailable as e:
                chk("indistinguishable" in str(e) and not sent,
                    "with no key it refuses BEFORE any request")

            os.environ["AZURE_AI_API_KEY"] = "k-test"

            # ── the key only ever goes to an Azure host ──────────────────────
            os.environ["AZURE_AI_ENDPOINT"] = "https://collector.example.com/"
            try:
                with replies(good):
                    extract("doc", model="azure:llama-3-3-70b")
                chk(False, "a non-Azure endpoint refuses")
            except ModelUnavailable:
                chk(not sent, "a non-Azure endpoint is refused before the key "
                              "is sent anywhere")

            os.environ["AZURE_AI_ENDPOINT"] = "https://placedon-law-eval.openai.azure.com/"

            # ── same instruction as the Ollama adapter ───────────────────────
            doc = "BOARD RESOLUTION dated 14 June 2024. CIN U74999KA2019PTC123456."
            llama, gpt = payload(doc, "llama-3-3-70b"), payload(doc, "gpt-5-mini")
            chk(llama["messages"][0]["content"] == local_model._prompt(doc)
                == gpt["messages"][0]["content"],
                "every model gets the SAME prompt as the Ollama run -- a score "
                "difference is a difference in the model")
            chk(llama.get("temperature") == 0 and "max_tokens" in llama,
                "a non-reasoning model is sent temperature 0")
            chk("temperature" not in gpt and "max_completion_tokens" in gpt,
                "a reasoning model is sent NO temperature -- gpt-5-mini refuses 0")

            # ── a finished reply becomes a Proposal, spans verbatim ──────────
            with replies(good):
                p, meta = extract(doc, model="azure:llama-3-3-70b")
            req = sent[-1]
            chk(p.facts["cin"]["span"] == "CIN U74999KA2019PTC123456"
                and meta["parse"] == "OK",
                "a finished reply parses through the shared parser, span kept")
            chk(req.full_url == "https://placedon-law-eval.openai.azure.com/"
                                "openai/v1/chat/completions"
                and req.get_header("Api-key") == "k-test"
                and "k-test" not in req.full_url,
                "the key travels in a header, never in the URL")
            chk(json.loads(req.data)["model"] == "llama-3-3-70b",
                "the azure: prefix is stripped to the deployment name")
            chk(meta["temperature"] == 0 and meta["served_by"]
                == "Llama-3.3-70B-Instruct",
                "meta records the temperature sent and the model that served it")
            chk(meta["tokens_out"] == 42 and meta["tokens_in"] is None,
                "meta records both token counts, and an absent count stays None "
                "rather than becoming a zero cost")

            with replies(reply('{"facts": {"cin": "U74999KA2019PTC123456"}}')):
                p, _ = extract(doc, model="azure:gpt-5-mini")
            chk(p.facts["cin"] == {"value": "U74999KA2019PTC123456", "span": None},
                "a flat value keeps a None span, for review to refuse -- the "
                "adapter does not do the gate's job")

            with replies(reply("I found no facts.")):
                p, meta = extract(doc, model="azure:gpt-5-mini")
            chk(p.facts == {} and meta["parse"] == "NO_JSON",
                "prose is a model answer with nothing parseable, not an error")

            # ── an unfinished or failed reply is never an answer ─────────────
            try:
                with replies(reply('{"facts": {"cin": {"val', finish="length")):
                    extract(doc, model="azure:gpt-5-mini")
                chk(False, "a truncated reply raises")
            except ModelUnavailable as e:
                chk("length" in str(e),
                    "a reply cut off at the token limit raises -- it is not an "
                    "empty answer")
            try:
                with replies(reply("", finish="content_filter")):
                    extract(doc, model="azure:gpt-5-mini")
                chk(False, "a filtered reply raises")
            except ModelRefused:
                chk(True, "a content-filter stop is a refusal")

            limited = urllib.error.HTTPError(
                "u", 429, "Too Many Requests", {},
                io.BytesIO(b'{"error": {"code": "RateLimitReached"}}'))
            try:
                with mock.patch.object(urllib.request, "urlopen",
                                       side_effect=limited):
                    extract(doc, model="azure:llama-3-3-70b")
                chk(False, "HTTP 429 raises")
            except ModelUnavailable as e:
                chk("429" in str(e) and "RateLimitReached" in str(e),
                    "a rate limit is an ERROR with Azure's own reason, not a "
                    "model that said nothing")
    finally:
        for k in names:
            os.environ.pop(k, None)
        for k, v in held.items():
            if v is not None:
                os.environ[k] = v

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
