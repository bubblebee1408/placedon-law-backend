"""
The only file that talks to Anthropic. Every paid call goes through here.

Corrections against the spec, each load-bearing:

  * **Model.** The spec names `claude-3-5-sonnet-20241022`, which retired 2025-10-28 and
    returns 404. We route to `claude-haiku-4-5` (DECISIONS D-3) — safe here precisely because
    the LLM never decides anything: `applicability.py` decides, and every number in the output
    is checked verbatim against source afterward. Model choice is a cost lever, not a
    correctness lever.

  * **FX.** The spec hardcodes $1 = ₹83. It is ₹95.23 (2026-08-06), so every cost the spec
    computes is ~13% under-reported. We use the rate in `backend/budget.py`, in one place.

  * **Cost.** The spec budgets ₹3–5 per answer, which is Opus-tier pricing applied to a
    mid-tier model. Measured on Haiku 4.5 at ~6,700 in / ~700 out: **₹0.97**.

  * **Budget.** The spec tracks spend and raises after the fact. `BudgetTracker.can_make_call()`
    runs *before* the request, so an exhausted budget degrades to template mode rather than
    discovering the overrun in a log.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.budget import DEFAULT_MODEL, BudgetTracker, cost_inr  # noqa: E402

log = logging.getLogger("placedon.llm")

MAX_OUTPUT_TOKENS = 800
MAX_PROVISION_CHARS = 1_000


# Which backend generates the explanation. The prompt, the citation enforcer and the
# number-checker are identical either way — that is the point. Swapping the model must not
# change what is allowed through, only how often something gets through at all.
#
#   anthropic  production. Haiku 4.5, measured ₹0.97/answer, budget-gated before the call.
#   ollama     local, ₹0, DEV ONLY. Ollama is a persistent daemon needing GBs of RAM; it cannot
#              run on Vercel serverless, so it must never become the deployed default.
#
# It exists because the LLM path had never executed even once — the corpus is unverified, so the
# gate closes before any call. That left the Source Prison prompt and both output checks tested
# only against strings written by hand. A local model exercises the whole pipeline for nothing,
# today, without waiting on a lawyer.
PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


class BudgetExceededError(RuntimeError):
    """Raised before a call that would breach the cap. Callers degrade; they do not retry."""


SYSTEM_PROMPT = """You are Placedon, an HR compliance assistant for Indian SMEs.

You are not deciding anything. A deterministic rules engine has already decided what the law
requires and which provisions apply. Your only job is to explain the text you are given.

CRITICAL RULES:
1. Answer ONLY using the provided legal text. Do not use outside knowledge, even if you are
   confident it is correct.
2. If the answer is not in the text, say "I don't have verified information on this."
3. Cite the exact section number for every claim, in square brackets.
4. Never state a number — a threshold, a deadline, a penalty, a headcount — unless that exact
   number appears in the provided text. Every figure you write is checked against the source
   afterward, and a figure that is not there causes the whole answer to be discarded.
5. Do not generalise. "Usually", "typically", "in most states" are forbidden.
6. Use simple language. The reader is an HR manager, not a lawyer.
7. Format: direct answer, then the citation, then the action if there is one.

You are NOT giving legal advice. You are relaying cited information from verified sources."""


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_inr: float
    model: str
    degraded: bool = False


def _call_ollama(prompt: str, *, model: str, timeout: float = 180.0) -> LLMResult:
    """
    Local generation. No key, no cost, no budget gate — there is nothing to meter.

    Deliberately stdlib-only (urllib, not httpx or the ollama package): adding a dependency for a
    dev-only path would put it in requirements.txt and therefore into the production function,
    which is how jinja2 took the site down.
    """
    import json as _json                                   # noqa: PLC0415
    import urllib.error                                    # noqa: PLC0415
    import urllib.request                                  # noqa: PLC0415

    body = _json.dumps({
        "model": model,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        # Low temperature reduces drift off the supplied text. It does not prevent it — that is
        # what the enforcer downstream is for.
        "options": {"temperature": 0.1, "num_predict": MAX_OUTPUT_TOKENS},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_HOST}/api/generate", data=body,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 — localhost only
            payload = _json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        log.exception("llm.ollama_failed model=%s", model)
        return LLMResult(f"Local model unavailable ({e}). Is `ollama serve` running?",
                         0, 0, 0.0, f"ollama/{model}", degraded=True)

    return LLMResult(
        payload.get("response", ""),
        int(payload.get("prompt_eval_count") or 0),
        int(payload.get("eval_count") or 0),
        0.0,                                              # local inference is free
        f"ollama/{model}",
    )


def _build_context(provisions: list[dict]) -> str:
    return "\n\n".join(
        f"[{p.get('citation', '?')}] {(p.get('text_display') or p.get('text', ''))[:MAX_PROVISION_CHARS]}"
        for p in provisions
    )


def explain_provisions(question: str, provisions: list[dict], company: dict,
                       *, tracker: BudgetTracker | None = None,
                       model: str = DEFAULT_MODEL) -> LLMResult:
    """
    Explain a pre-verified evidence packet. Never asked to decide applicability.

    Raises BudgetExceededError *before* spending if the cap would be breached.
    """
    tracker = tracker or BudgetTracker()

    context = _build_context(provisions)
    prompt = (
        f"Company: {company.get('employee_count', '?')} employees in "
        f"{company.get('state', '?')}\n\n"
        f"Legal text:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )
    if PROVIDER == "ollama":
        # No budget gate: nothing is spent, so there is nothing to protect. Every other guard —
        # the pre-flight abstention, the citation enforcer, the number-checker — still applies,
        # because those are about correctness rather than cost.
        return _call_ollama(prompt, model=OLLAMA_MODEL)

    est_in = len(SYSTEM_PROMPT + prompt) // 4          # ~4 chars/token, close enough to gate on
    verdict = tracker.can_make_call(model=model, input_tokens=est_in,
                                    output_tokens=MAX_OUTPUT_TOKENS)
    if not verdict.allowed:
        raise BudgetExceededError(verdict.reason)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    try:
        from anthropic import Anthropic
    except ImportError as e:                              # pragma: no cover
        raise RuntimeError("pip install anthropic") from e

    client = Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:                                     # noqa: BLE001 — deliberate boundary
        log.exception("llm.call_failed model=%s", model)
        # Degrade, never guess. A failed call is not billed and must not become an answer.
        return LLMResult(
            "Service temporarily unavailable. Please try again.",
            0, 0, 0.0, model, degraded=True,
        )

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    inp, out = resp.usage.input_tokens, resp.usage.output_tokens
    spent = cost_inr(model, inp, out)
    tracker.record_call(spent)
    after = tracker.can_make_call(model=model)
    log.info("llm.call model=%s ₹%.4f in=%d out=%d | month ₹%.2f",
             model, spent, inp, out, after.spent_month)
    return LLMResult(text, inp, out, spent, model)
