"""Mistral AI models on Azure AI Foundry.

Three models, three jobs:
  Large 4    — complex legal reasoning, synthesis, HIGH-consequence extraction
  Small 4    — routine classification, first-pass document review, LOW-consequence
  OCR 4.1    — scanned agreements, PDFs, structured document extraction

All three are deployed on Azure AI Foundry and called through the same
OpenAI-compatible chat endpoint as `azure_model.py`. The only differences are
the deployment names, the completion budgets, and OCR's ability to accept
image inputs.

PLAN_22 D3: model inference goes through Azure AI Foundry, not direct vendor
APIs. These are Mistral weights deployed ON Azure, which is what the user
approved.

Run: PYTHONPATH=. python3 checker/mistral_model.py --test
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

# ── deployment names on Azure AI Foundry ────────────────────────────────────
LARGE = "mistral-large-4"
SMALL = "mistral-small-4"
OCR = "mistral-ocr-4-1"

# ── budgets ─────────────────────────────────────────────────────────────────
LARGE_BUDGET = 4096
SMALL_BUDGET = 1024
OCR_BUDGET = 2048

DEFAULT_TIMEOUT = 180

# ── host allowlist — same Azure hosts, separate env vars ────────────────────
_AZURE_HOSTS = (".openai.azure.com", ".services.ai.azure.com",
                ".cognitiveservices.azure.com")


def available() -> bool:
    return bool(os.getenv("MISTRAL_AZURE_API_KEY") and os.getenv("MISTRAL_AZURE_ENDPOINT"))


def _url() -> str:
    base = os.getenv("MISTRAL_AZURE_ENDPOINT") or ""
    u = urlparse(base)
    if u.scheme != "https" or not (u.hostname or "").endswith(_AZURE_HOSTS):
        raise ModelUnavailable(
            f"MISTRAL_AZURE_ENDPOINT={base!r} is not an https Azure AI host")
    return f"https://{u.hostname}/openai/v1/chat/completions"


def _budget(deployment: str) -> int:
    if deployment == LARGE:
        return LARGE_BUDGET
    if deployment == OCR:
        return OCR_BUDGET
    return SMALL_BUDGET


def chat_body(prompt: str, deployment: str, *,
              max_tokens: int | None = None) -> dict:
    budget = max_tokens or _budget(deployment)
    return {
        "model": deployment,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": budget,
        "temperature": 0,
    }


def chat_body_with_image(prompt: str, image_b64: str, deployment: str = OCR, *,
                         max_tokens: int | None = None) -> dict:
    budget = max_tokens or _budget(deployment)
    return {
        "model": deployment,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }],
        "max_tokens": budget,
        "temperature": 0,
    }


def reply_text(data: dict) -> str:
    try:
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError):
        raise ModelUnavailable(
            f"no choice in the Mistral reply: {json.dumps(data)[:200]}") from None
    finish = choice.get("finish_reason")
    if finish == "content_filter":
        raise ModelRefused("Mistral content filter stopped the reply")
    if finish != "stop":
        raise ModelUnavailable(
            f"Mistral reply did not finish (finish_reason={finish!r})")
    return text


def _call(body: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    key = os.getenv("MISTRAL_AZURE_API_KEY") or ""
    if not key:
        raise ModelUnavailable("MISTRAL_AZURE_API_KEY not set")
    from checker.robots import ssl_context
    ctx = ssl_context()
    if ctx is None:
        raise ModelUnavailable("no CA trust store")
    req = urllib.request.Request(
        _url(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", "replace")[:200]
        if e.code == 429:
            from checker.azure_model import RateLimited
            raise RateLimited(f"Mistral Azure HTTP 429: {body_text}") from None
        raise ModelUnavailable(f"Mistral Azure HTTP {e.code}: {body_text}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelUnavailable(f"Mistral Azure unreachable: {e}") from None


def generate(prompt: str, *, deployment: str = SMALL,
             max_tokens: int | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    body = chat_body(prompt, deployment, max_tokens=max_tokens)
    return reply_text(_call(body, timeout))


def ocr(prompt: str, image_b64: str, *,
        max_tokens: int | None = None, timeout: int = DEFAULT_TIMEOUT) -> str:
    body = chat_body_with_image(prompt, image_b64, OCR, max_tokens=max_tokens)
    return reply_text(_call(body, timeout))


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("mistral_model")

    # ── deployment names are consistent ───────────────────────────────────
    check(LARGE == "mistral-large-4", f"LARGE deployment ({LARGE})")
    check(SMALL == "mistral-small-4", f"SMALL deployment ({SMALL})")
    check(OCR == "mistral-ocr-4-1", f"OCR deployment ({OCR})")

    # ── chat_body builds the right shape ──────────────────────────────────
    body = chat_body("test", LARGE)
    check(body["model"] == LARGE, "body uses correct deployment")
    check(body["max_tokens"] == LARGE_BUDGET, f"LARGE gets {LARGE_BUDGET} tokens")
    check(body["temperature"] == 0, "temperature is 0")

    body_s = chat_body("test", SMALL)
    check(body_s["max_tokens"] == SMALL_BUDGET, f"SMALL gets {SMALL_BUDGET} tokens")

    # ── image body for OCR ────────────────────────────────────────────────
    img_body = chat_body_with_image("extract text", "AAAA", OCR)
    check(img_body["model"] == OCR, "OCR body uses OCR deployment")
    content = img_body["messages"][0]["content"]
    check(isinstance(content, list) and len(content) == 2, "OCR message has text + image")
    check(content[1]["type"] == "image_url", "second content block is image_url")

    # ── reply_text extracts correctly ─────────────────────────────────────
    good = {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}
    check(reply_text(good) == "hello", "reply_text extracts content")

    bad_finish = {"choices": [{"message": {"content": "hi"}, "finish_reason": "length"}]}
    try:
        reply_text(bad_finish)
        check(False, "truncated reply raises")
    except ModelUnavailable:
        check(True, "truncated reply raises ModelUnavailable")

    bad_filter = {"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}
    try:
        reply_text(bad_filter)
        check(False, "content filter raises")
    except ModelRefused:
        check(True, "content filter raises ModelRefused")

    # ── availability depends on env vars ──────────────────────────────────
    import os as _o
    saved = (_o.environ.pop("MISTRAL_AZURE_API_KEY", None),
             _o.environ.pop("MISTRAL_AZURE_ENDPOINT", None))
    check(not available(), "unavailable without env vars")
    _o.environ["MISTRAL_AZURE_API_KEY"] = "test"
    _o.environ["MISTRAL_AZURE_ENDPOINT"] = "https://test.openai.azure.com"
    check(available(), "available with both env vars")
    if saved[0] is not None:
        _o.environ["MISTRAL_AZURE_API_KEY"] = saved[0]
    else:
        _o.environ.pop("MISTRAL_AZURE_API_KEY", None)
    if saved[1] is not None:
        _o.environ["MISTRAL_AZURE_ENDPOINT"] = saved[1]
    else:
        _o.environ.pop("MISTRAL_AZURE_ENDPOINT", None)

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
