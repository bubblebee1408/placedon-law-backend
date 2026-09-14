"""A deliberately weak local model, because the good one was not stressing anything.

Gemini came back 9 correct out of 10 and produced no friction at all. That is a
fine result for Gemini and a poor one for a test: an adversarial set that the
subject passes cleanly has not been calibrated against anything.

`gemma3:1b` is 0.8 GB and answers in about four seconds. Its first reply in this
project echoed the literal placeholder `"span":"<verbatim>"` instead of quoting
the document -- an ungrounded span produced spontaneously, without being asked to
misbehave. That is the point of using it.

## What this measures, and what it does not

It does NOT measure how the product will perform. Nobody would serve a 1B model
here, and `router.py` routes nothing to it.

It measures whether the GATES hold when the model behind them is bad. Every test
of `reasoning.review()` until now used `misbehaving_model()` -- stubs written by
the same hand as the detectors, failing in the ways their author imagined. This
fails in ways nobody chose, which is the only kind of failure worth testing
against.

No quota, no cost, no network. The free Gemini tier is 20 requests per day per
model, which the 18-case set exhausts in one run.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from checker.anthropic_model import ModelUnavailable
from checker.reasoning import Proposal

BASE = "http://localhost:11434"
MODEL = "gemma3:1b"
KNOWN_FIELDS = ("document_date", "incorporation_date", "company_class",
                "financial_year", "paid_up_capital_rupees", "turnover_rupees",
                "net_worth_rupees", "net_profit_rupees", "director_count", "cin")


def available() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE}/api/tags", timeout=4) as r:
            return r.status == 200
    except Exception:                                           # noqa: BLE001
        return False


def _prompt(document: str) -> str:
    from checker.anthropic_model import _EXTRACT_SYSTEM
    from checker.prompt_safety import wrap_untrusted
    return (_EXTRACT_SYSTEM + "\n\nDOCUMENT:\n"
            + wrap_untrusted(document, "uploaded document")
            + "\n\nReturn ONLY the JSON object.")


def extract(document: str, *, model: str = MODEL, timeout: int = 120):
    """Same contract as gemini_model.extract: (Proposal, meta)."""
    body = json.dumps({"model": model, "stream": False,
                       "options": {"temperature": 0, "num_predict": 700},
                       "prompt": _prompt(document)}).encode()
    req = urllib.request.Request(f"{BASE}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelUnavailable(f"ollama unreachable: {e}") from None

    # A reply that never finished is a SERVER failure, not a model answer. A model
    # too big for GPU memory makes Ollama return HTTP 200 with done=false and an
    # empty response; parsed, that is an empty Proposal from a case that "ran".
    if data.get("error") or data.get("done") is not True:
        raise ModelUnavailable(
            f"ollama did not finish: {data.get('error') or 'done=false'}")

    proposal, parse, raw = parse_reply(data.get("response", "") or "")
    meta = {"model": model, "parse": parse}
    if parse != "OK":
        return proposal, meta | {"raw": raw[:200]}
    return proposal, meta | {"tokens_out": data.get("eval_count"),
                             "ms": round(data.get("total_duration", 0) / 1e6)}


def parse_reply(raw: str) -> tuple[Proposal, str, str]:
    """A model's reply text -> (Proposal, parse status, raw text).

    Shared by every adapter, so a difference between two providers is a
    difference in what the models said and never in how their replies were read.
    """
    # The model's output is UNTRUSTED and frequently malformed -- fenced, doubled
    # braces, trailing prose. Parsing failure is a refusal, never a repair: a
    # harness that fixes up a model's JSON is measuring its own leniency.
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return Proposal(), "NO_JSON", raw
    try:
        obj = json.loads(m.group())
    except json.JSONDecodeError:
        return Proposal(), "BAD_JSON", raw

    facts = obj.get("facts") if isinstance(obj, dict) else None
    if not isinstance(facts, dict):
        return Proposal(), "NO_FACTS", raw

    # Pass through WHAT THE MODEL SAID, in the shape review expects. The first
    # version dropped any fact that was not already a {"value","span"} object --
    # which is exactly what gemma3:1b returns, flat values with no spans at all.
    # Dropping them made the adapter do the gate's job and hid three real
    # failures in a single reply: a figure wrong by 10x (Rs 4,00,00,000 read as
    # 400000000 rather than 40000000 -- Indian digit grouping misread), an
    # invented company_class, and no spans anywhere.
    #
    # An adapter that filters a model's output before the checker sees it is
    # measuring its own strictness. A flat value becomes {"value": v, "span":
    # None}, so the missing span is refused by reasoning.review as
    # FACT_WITHOUT_SPAN, where it belongs.
    clean = {}
    for k, v in facts.items():
        if k not in KNOWN_FIELDS or v is None:
            continue
        if isinstance(v, dict):
            clean[k] = {"value": v.get("value"), "span": v.get("span")}
        else:
            clean[k] = {"value": v, "span": None}
    return Proposal(facts=clean), "OK", raw
