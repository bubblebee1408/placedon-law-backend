"""Voyage AI: a legal embedding model and a reranker, wired as retrieval CANDIDATES.

Nothing here is on the answer path. `checker/router.py` lists Voyage as a candidate,
never as preferred: the preference changes only after `scripts/bakeoff_retrieval.py`
shows a win whose Wilson interval does not overlap the incumbent's (RRF fusion,
p@1 0.80 / recall@5 0.97 on the frozen 70-case eval, docs/ABLATION_CORRECTED.md).

## What was pinned, from which page, on which date

Fetched 2026-09-18 as raw markdown (`<url>.md`, the docs' own export), not through a
summariser, so every field below is copied rather than paraphrased.

    V1  https://docs.voyageai.com/reference/embeddings-api.md   (page updatedAt 2025-12-10)
    V2  https://docs.voyageai.com/reference/reranker-api.md     (page updatedAt 2025-12-10)
    V3  https://docs.voyageai.com/docs/embeddings.md            (page updatedAt 2026-08-10)
    V4  https://docs.voyageai.com/docs/reranker.md              (page updatedAt 2026-09-01)
    V5  https://docs.voyageai.com/docs/pricing.md               (page updatedAt 2026-08-26)
    V6  https://docs.voyageai.com/docs/faq.md                   (page updatedAt 2026-08-03)
    V7  https://docs.voyageai.com/docs/error-codes.md

SOURCED (stated on the page named):
- `POST https://api.voyageai.com/v1/embeddings`, body `input` (str or list, <= 1,000
  items), `model`, `input_type` (null | query | document), `truncation` (default true),
  `output_dimension`, `output_dtype`, `encoding_format`. Response `{object, data:
  [{object, embedding, index}], model, usage: {total_tokens}}` (V1).
- `POST https://api.voyageai.com/v1/rerank`, body `query`, `documents` (<= 1,000),
  `model`, `top_k`, `return_documents` (default false), `truncation` (default true).
  Response `{object, data: [{index, relevance_score, document?}], model, usage}`,
  "sorted by the descending order of relevance scores" (V2).
- Auth header `Authorization: Bearer <key>`; 4XX body `{detail}` (V1, V2).
- `voyage-law-2`: in the CURRENT model table, 16,000-token context, 1,024 dimensions,
  "Optimized for legal retrieval and RAG"; 120K tokens per request list (V1, V3).
- `rerank-2.5` and `rerank-2.5-lite`: current, 32,000-token context (V4). `rerank-3`
  and `rerank-3-lite` are listed "(In Preview)" and are deliberately NOT pinned: a
  preview model moving under a bake-off makes its number unreproducible.
- Price per 1M tokens: voyage-law-2 $0.12 (50M free tokens), rerank-2.5 $0.05,
  rerank-2.5-lite $0.02 (V5).
- "For Voyage-hosted model API endpoints, customers can opt-out from Voyage storing
  and using their data for future model training"; opting out needs a payment method
  and an org Admin (V6). **So the default is that Voyage stores and trains on what we
  send.**
- 400 / 401 / 403 / 429 / 5XX meanings (V7).

UNVERIFIED / CONTRADICTED:
- Free tokens for rerank-2.5: V5's paragraph says "The first 200 million tokens for
  rerank-2.5 … are free"; V5's own table says 0. Costs below are therefore at LIST
  price with no free allowance deducted -- the conservative reading.
- voyage-law-2's "Indian jurisdiction" coverage and its NDCG claims are vendor copy
  (docs/PLAN_10_ADOPTION_REVIEW.md rows 108-110). Nothing here relies on them; the
  bake-off is what decides.
- Whether the live API echoes `model` exactly as the requested ID. This module
  refuses a mismatch; `scripts/smoke_adapters.py` records what it actually returns.

## Fail closed, in the dense_index.py sense

- No `VOYAGE_API_KEY` -> `VoyageUnavailable`. There is no fallback to BM25 or MiniLM,
  because Voyage-labelled numbers produced by another retriever would answer a
  question nobody asked and invalidate the bake-off (see `DenseUnavailable`).
- HTTP error, timeout, unreachable host -> `VoyageServiceError`. Never an empty list:
  "no ranking came back" and "nothing is relevant" must not look alike, and in a
  compliance tool the second reads as "no obligation found".
- A response that does not match the documented shape -> `VoyageBadResponse`.
- `truncation` is sent as **false** on both endpoints, so an over-length input is a
  400 rather than a silent cut. The default (true) would embed a truncated section
  and report it as the section.

## Data use

Because of V6, only PUBLIC text goes to Voyage from this repo today: statute text
from `corpus/` and our own authored eval questions. Nothing here enforces that for
client text -- there is no client-text caller -- and that is recorded rather than
assumed away: before any client question reaches `embed()` or `rerank()`, the org
must be opted out (V6) and a guard like `sarvam_model.privacy_check` added here.

## No dependency

Standard-library `urllib`, like `gemini_model.py`. TLS goes through
`robots.ssl_context()`, which verifies or refuses; it never falls back to an
unverified context. The key is read only from the environment (loaded from `.env`
by `checker.env`), sent only in the Authorization header, and redacted from every
error message this module raises.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from checker.anthropic_model import USD_TO_INR, ModelRefused, ModelUnavailable
from checker.env import load as _load_env

_load_env()

BASE = "https://api.voyageai.com/v1"

LAW = "voyage-law-2"
RERANK = "rerank-2.5"
RERANK_LITE = "rerank-2.5-lite"
EMBED_MODELS = (LAW,)
RERANK_MODELS = (RERANK, RERANK_LITE)

# USD per 1M tokens, list price (V5). Free allowances deliberately not deducted.
PRICING_USD_PER_M = {LAW: 0.12, RERANK: 0.05, RERANK_LITE: 0.02}

# The dimension each embedding model documents. A vector of another width is refused:
# mutual consistency is not enough, because a silently re-dimensioned model would pass
# a whole bake-off arm as if nothing had changed (D6 verifier, finding 2).
DOCUMENTED_DIM = {LAW: 1024}


def _stub_vec(*head: object) -> list:
    """A self-test vector of the documented width. Only the tests use it: parse_embeddings
    refuses any other width, so a 3-float stub would fail the very rule it is checking."""
    return [*head] + [0.0] * (DOCUMENTED_DIM[LAW] - len(head))

INPUT_TYPES = ("query", "document")
MAX_ITEMS = 1_000          # embeddings `input` list and rerank `documents` (V1, V2)
TIMEOUT_S = 60

DOC_URLS = {
    "embeddings": "https://docs.voyageai.com/reference/embeddings-api.md",
    "rerank": "https://docs.voyageai.com/reference/reranker-api.md",
    "rate_limits": "https://docs.voyageai.com/docs/rate-limits",
}


class VoyageError(ModelUnavailable):
    """Base for every Voyage refusal. A ModelUnavailable, so callers that already
    handle a refused model handle this without learning a new type."""


class VoyageUnavailable(VoyageError):
    """No key, or no way to authenticate the endpoint. Never a fallback retriever."""


class VoyageServiceError(VoyageError):
    """The call was made and failed: HTTP error, timeout, unreachable. Never an
    empty result, never an abstention."""


class VoyageBadResponse(ModelRefused):
    """The response does not have the documented shape. Refused, not repaired."""


@dataclass(frozen=True)
class VoyageCall:
    """What one call used and cost. Recorded so spend is observed, not assumed."""
    endpoint: str
    model: str
    total_tokens: int
    cost_inr: float


_ENDPOINTS = ("embeddings", "rerank")


def available() -> bool:
    return bool((os.getenv("VOYAGE_API_KEY") or "").strip())


def _key() -> str:
    # Stripped: a whitespace-only key read from a shell export made `available()` true and
    # the header "Bearer    " (D6 verifier, finding 1). checker/env.py already strips .env.
    k = (os.getenv("VOYAGE_API_KEY") or "").strip()
    if not k:
        raise VoyageUnavailable(
            "VOYAGE_API_KEY is not set. This refuses rather than fall back to BM25 or "
            "MiniLM: numbers from another retriever under Voyage's name would answer a "
            "question nobody asked (see dense_index.DenseUnavailable).")
    return k


def cost_inr(model: str, total_tokens: int) -> float:
    """List price, no free allowance deducted (V5 contradicts itself on rerank-2.5)."""
    if model not in PRICING_USD_PER_M:
        raise KeyError(f"no price on record for {model!r}")
    return round(total_tokens / 1e6 * PRICING_USD_PER_M[model] * USD_TO_INR, 6)


def _redact(text: str, key: str | None) -> str:
    return text.replace(key, "<redacted>") if key else text


def build_request(endpoint: str, payload: dict, key: str) -> urllib.request.Request:
    if endpoint not in _ENDPOINTS:
        raise ValueError(f"endpoint {endpoint!r} is not one of the pinned {_ENDPOINTS}")
    return urllib.request.Request(
        f"{BASE}/{endpoint}", data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})


def _post(endpoint: str, payload: dict, timeout: int = TIMEOUT_S) -> dict:
    """The real transport. Every failure raises; nothing becomes an empty result."""
    key = _key()
    req = build_request(endpoint, payload, key)
    from checker.robots import ssl_context
    ctx = ssl_context()
    if ctx is None:
        raise VoyageUnavailable(
            "no CA trust store on this machine, so api.voyageai.com cannot be "
            "authenticated. Refusing to call it unverified.")
    service = "This is a service failure, not an empty ranking."
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        body = _redact(e.read().decode("utf-8", "replace")[:300], key)
        if e.code == 429:
            raise VoyageServiceError(
                f"Voyage rate limited (HTTP 429) on /{endpoint}; pace requests "
                f"({DOC_URLS['rate_limits']}). {service} Body: {body}") from None
        raise VoyageServiceError(
            f"Voyage HTTP {e.code} on /{endpoint}. {service} Body: {body}") from None
    except urllib.error.URLError as e:
        raise VoyageServiceError(
            f"Voyage unreachable on /{endpoint}: {_redact(str(e.reason), key)}. "
            f"{service}") from None
    except OSError as e:          # TimeoutError and socket errors raised mid-read
        raise VoyageServiceError(
            f"Voyage call on /{endpoint} failed mid-flight ({type(e).__name__}: "
            f"{_redact(str(e), key)[:120]}). {service}") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise VoyageBadResponse(
            f"Voyage /{endpoint} returned 200 with a non-JSON body ({e}); refused") from None


def _is_number(v: object) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def _check_envelope(data: object, endpoint: str, model: str) -> list:
    if not isinstance(data, dict):
        raise VoyageBadResponse(f"/{endpoint}: response is not an object")
    items = data.get("data")
    if not isinstance(items, list):
        raise VoyageBadResponse(f"/{endpoint}: response has no 'data' list")
    served = data.get("model")
    if served is not None and served != model:
        raise VoyageBadResponse(
            f"/{endpoint}: asked for {model!r}, response names {served!r}. A number "
            f"from a different model must not be recorded under the requested one.")
    return items


def _index(item: object, n: int, seen: set, endpoint: str) -> int:
    if not isinstance(item, dict):
        raise VoyageBadResponse(f"/{endpoint}: a result is not an object")
    i = item.get("index")
    if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < n or i in seen:
        raise VoyageBadResponse(
            f"/{endpoint}: index {i!r} is missing, repeated or outside 0..{n - 1}")
    seen.add(i)
    return i


def parse_embeddings(data: object, n: int, *, model: str) -> list[list[float]]:
    """Vectors in INPUT order. Refuses any deviation from the documented shape."""
    items = _check_envelope(data, "embeddings", model)
    if len(items) != n:
        raise VoyageBadResponse(f"/embeddings: {len(items)} vectors for {n} inputs")
    out: dict[int, list[float]] = {}
    seen: set = set()
    for item in items:
        i = _index(item, n, seen, "embeddings")
        vec = item.get("embedding")
        if not isinstance(vec, list) or not vec or not all(_is_number(v) for v in vec):
            raise VoyageBadResponse(
                f"/embeddings: vector {i} is empty or holds a non-finite / non-number value")
        out[i] = [float(v) for v in vec]
    dims = {len(v) for v in out.values()}
    if len(dims) != 1:
        raise VoyageBadResponse("/embeddings: vectors have different dimensions")
    want = DOCUMENTED_DIM.get(model)
    got = dims.pop()
    if want is not None and got != want:
        raise VoyageBadResponse(
            f"/embeddings: {model} returned {got}-dimensional vectors, not the documented "
            f"{want}. Refused rather than measured: a re-dimensioned model is a different "
            f"model, and a bake-off arm run on it would answer a question nobody asked.")
    return [out[i] for i in range(n)]


def parse_rerank(data: object, n_docs: int, *, model: str,
                 top_k: int | None = None) -> list[tuple[int, float]]:
    """(document index, relevance_score) best-first, ties broken by index.

    The order is re-derived from the scores rather than trusted from the list, so a
    response that is correctly scored but listed out of order cannot misrank."""
    items = _check_envelope(data, "rerank", model)
    want = top_k if top_k is not None else n_docs
    if len(items) != want:
        raise VoyageBadResponse(f"/rerank: {len(items)} results, expected {want}")
    seen: set = set()
    out = []
    for item in items:
        i = _index(item, n_docs, seen, "rerank")
        s = item.get("relevance_score")
        if not _is_number(s):
            raise VoyageBadResponse(f"/rerank: result {i} has score {s!r}")
        out.append((i, float(s)))
    return sorted(out, key=lambda t: (-t[1], t[0]))


def _usage(data: dict, endpoint: str, model: str) -> VoyageCall:
    usage = data.get("usage") if isinstance(data, dict) else None
    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise VoyageBadResponse(
            f"/{endpoint}: no usage.total_tokens in the response; refused, because a "
            f"call whose cost cannot be recorded is a call whose cost is assumed")
    return VoyageCall(endpoint, model, tokens, cost_inr(model, tokens))


def _texts(values, what: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise ValueError(f"{what} must be a list of strings, not {type(values).__name__}")
    if not values:
        raise ValueError(f"{what} is empty; there is nothing to send")
    if len(values) > MAX_ITEMS:
        raise ValueError(f"{what} has {len(values)} items; the documented limit is {MAX_ITEMS}")
    if not all(isinstance(t, str) and t.strip() for t in values):
        raise ValueError(f"{what} contains an empty or non-string item")
    return list(values)


def embed(texts, *, input_type: str, model: str = LAW,
          _transport=None) -> tuple[list[list[float]], VoyageCall]:
    """Embed texts with a pinned model. `input_type` is required, never defaulted:
    the FAQ says not to omit it for retrieval, and a query embedded as a document is
    a quiet, measurable degradation."""
    items = _texts(texts, "texts")
    if input_type not in INPUT_TYPES:
        raise ValueError(f"input_type must be one of {INPUT_TYPES}, got {input_type!r}")
    if model not in EMBED_MODELS:
        raise ValueError(f"{model!r} is not a pinned embedding model {EMBED_MODELS}")
    payload = {"input": items, "model": model, "input_type": input_type,
               "truncation": False}
    data = (_transport or _post)("embeddings", payload)
    vectors = parse_embeddings(data, len(items), model=model)
    return vectors, _usage(data, "embeddings", model)


def rerank(query: str, documents, *, model: str = RERANK, top_k: int | None = None,
           _transport=None) -> tuple[list[tuple[int, float]], VoyageCall]:
    """Rerank documents for one query with a pinned model."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is empty")
    docs = _texts(documents, "documents")
    if model not in RERANK_MODELS:
        raise ValueError(f"{model!r} is not a pinned reranker {RERANK_MODELS}")
    if top_k is not None and not 1 <= top_k <= len(docs):
        raise ValueError(f"top_k={top_k} is outside 1..{len(docs)}")
    payload = {"query": query, "documents": docs, "model": model,
               "truncation": False, "return_documents": False}
    if top_k is not None:
        payload["top_k"] = top_k
    data = (_transport or _post)("rerank", payload)
    ranked = parse_rerank(data, len(docs), model=model, top_k=top_k)
    return ranked, _usage(data, "rerank", model)


# ── self-test. No network: urlopen is replaced for the whole run and any call fails.
def _fixture(name: str) -> dict:
    from pathlib import Path
    p = Path(__file__).resolve().parent / "fixtures" / "vendor_docs" / name
    return json.loads(p.read_text(encoding="utf-8"))


def _test() -> None:
    import io
    from unittest import mock


    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def attempt(fn):
        """Run fn; return the exception it raised, or None."""
        try:
            fn()
        except Exception as e:                       # noqa: BLE001 - the test inspects it
            return e
        return None

    print("voyage_model")
    network: list[str] = []

    def no_network(*a, **k):
        network.append(repr(a[0])[:80] if a else "?")
        raise AssertionError("a unit test tried to reach the network")

    net_guard = mock.patch.object(urllib.request, "urlopen", side_effect=no_network)
    net_guard.start()
    held_key = os.environ.pop("VOYAGE_API_KEY", None)
    try:
        _run_checks(check, attempt, network, mock, io)
    finally:
        net_guard.stop()
        if held_key is not None:
            os.environ["VOYAGE_API_KEY"] = held_key

    check(not network, f"no unit test reached the network ({len(network)} attempts)")
    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def _run_checks(check, attempt, network, mock, io) -> None:
    # ── 1. request construction, per the documented shape ───────────────────
    req = build_request("embeddings", {"input": ["a"], "model": LAW}, "vk-TEST-0001")
    check(req.full_url == "https://api.voyageai.com/v1/embeddings",
          f"embeddings go to the documented URL ({req.full_url})")
    check(req.get_method() == "POST", "...as a POST")
    check(req.get_header("Authorization") == "Bearer vk-TEST-0001",
          "...authenticated with 'Authorization: Bearer <key>' (V1 securitySchemes)")
    check(req.get_header("Content-type") == "application/json",
          "...with a JSON body")
    check(json.loads(req.data.decode("utf-8")) == {"input": ["a"], "model": LAW},
          "...whose body is the payload, byte-for-byte JSON")
    check(build_request("rerank", {}, "k").full_url == "https://api.voyageai.com/v1/rerank",
          "rerank goes to the documented URL")
    bad = attempt(lambda: build_request("../admin", {}, "k"))
    check(isinstance(bad, ValueError), "an endpoint outside the two pinned ones is refused")

    seen: dict = {}

    def emb_transport(endpoint, payload):
        seen["endpoint"], seen["payload"] = endpoint, payload
        n = len(payload["input"])
        return {"object": "list", "model": payload["model"], "usage": {"total_tokens": 7 * n},
                "data": [{"object": "embedding", "index": i, "embedding": _stub_vec(0.1 * (i + 1), 0.2, 0.3)}
                         for i in range(n)]}

    vecs, call = embed(["s.173 board meetings", "s.185 loans"], input_type="document",
                       _transport=emb_transport)
    check(seen["endpoint"] == "embeddings", "embed() calls the embeddings endpoint")
    check(seen["payload"] == {"input": ["s.173 board meetings", "s.185 loans"], "model": LAW,
                              "input_type": "document", "truncation": False},
          f"embed() sends exactly input/model/input_type/truncation=false ({seen['payload']})")
    check(len(vecs) == 2 and vecs[0][0] == 0.1 and vecs[1][0] == 0.2,
          "embed() returns one vector per input, in input order")
    check(call == VoyageCall("embeddings", LAW, 14, cost_inr(LAW, 14)),
          f"embed() records model, tokens and cost ({call})")

    def rr_transport(endpoint, payload):
        seen["endpoint"], seen["payload"] = endpoint, payload
        n = len(payload["documents"])
        k = payload.get("top_k") or n
        return {"object": "list", "model": payload["model"], "usage": {"total_tokens": 40},
                "data": [{"index": i, "relevance_score": 1.0 - 0.1 * i} for i in range(k)]}

    ranked, rcall = rerank("loans to directors", ["a", "b", "c"], top_k=2, _transport=rr_transport)
    check(seen["endpoint"] == "rerank", "rerank() calls the rerank endpoint")
    check(seen["payload"] == {"query": "loans to directors", "documents": ["a", "b", "c"],
                              "model": RERANK, "truncation": False,
                              "return_documents": False, "top_k": 2},
          f"rerank() sends query/documents/model/top_k, truncation=false, no documents back "
          f"({seen['payload']})")
    check(ranked == [(0, 1.0), (1, 0.9)], f"rerank() returns (index, score) best-first ({ranked})")
    check(rcall.endpoint == "rerank" and rcall.total_tokens == 40, "rerank() records usage")
    rerank("q", ["a", "b"], _transport=rr_transport)
    check("top_k" not in seen["payload"], "top_k is omitted, not sent as null, when not asked for")

    # ── 2. missing key -> VoyageUnavailable, before any network ─────────────
    check(not available(), "with no VOYAGE_API_KEY, available() is False")
    before = len(network)
    e = attempt(lambda: embed(["x"], input_type="query"))
    check(isinstance(e, VoyageUnavailable), f"with no key, embed() raises VoyageUnavailable ({e!r})")
    check("VOYAGE_API_KEY" in str(e) and "fall back" in str(e),
          "...naming the key, and saying it does not fall back to another retriever")
    e2 = attempt(lambda: rerank("q", ["a"]))
    check(isinstance(e2, VoyageUnavailable), "with no key, rerank() raises VoyageUnavailable")
    check(len(network) == before, "...and neither reached the network")
    check(isinstance(e, ModelUnavailable),
          "VoyageUnavailable is a ModelUnavailable, so existing refusal handling applies")

    # ── 3. documented-example payloads, stored as labelled fixtures ─────────
    fx = _fixture("voyage_embeddings_example.json")
    check(fx["_provenance"].startswith("shape copied from https://docs.voyageai.com/")
          and "not a live response" in fx["_provenance"],
          "the embeddings fixture is labelled as a doc-shape copy, not a live response")
    ex = fx["example"]
    e = attempt(lambda: parse_embeddings(ex, 2, model="voyage-4-large"))
    check(isinstance(e, VoyageBadResponse),
          "the doc example VERBATIM is refused: its vectors contain the doc's '...' "
          "elision, which is not a number")
    clean = json.loads(json.dumps(ex))
    for item in clean["data"]:
        item["embedding"] = [v for v in item["embedding"] if v != "..."]
    got = parse_embeddings(clean, 2, model="voyage-4-large")
    check(got == [[-0.016709786, 0.026996311, -0.027496673, -0.012125067],
                  [0.003613521, 0.026428301, -0.009491397, -0.028471239]],
          "with the elision removed, the documented shape parses to two vectors by index")
    e = attempt(lambda: parse_embeddings(clean, 2, model=LAW))
    check(isinstance(e, VoyageBadResponse) and "voyage-4-large" in str(e),
          "a response naming a different model than was asked for is refused")

    rx = _fixture("voyage_rerank_example.json")
    check("not a live response" in rx["_provenance"], "the rerank fixture is labelled likewise")
    check(parse_rerank(rx["example"], 2, model="rerank-2.5-lite")
          == [(0, 0.455078125), (1, 0.439453125)],
          "the documented rerank example parses to (index, relevance_score) best-first")
    check(parse_rerank({**rx["example"], "data": list(reversed(rx["example"]["data"]))}, 2,
                       model="rerank-2.5-lite")[0] == (0, 0.455078125),
          "order comes from the scores, not from trusting the response's list order")

    # ── 4. malformed responses are refused, never repaired ───────────────────
    good = {"object": "list", "model": LAW, "usage": {"total_tokens": 3},
            "data": [{"index": 0, "embedding": _stub_vec(0.5, 0.5)}, {"index": 1, "embedding": _stub_vec(0.1, 0.9)}]}

    def variant(**kw):
        d = json.loads(json.dumps(good))
        d.update(kw)
        return d

    cases = {
        "no data": variant(data=None),
        "one vector for two inputs": variant(data=good["data"][:1]),
        "duplicate index": variant(data=[good["data"][0], {"index": 0, "embedding": _stub_vec(1.0)}]),
        "index out of range": variant(data=[good["data"][0], {"index": 5, "embedding": _stub_vec(1.0)}]),
        "ragged dimensions": variant(data=[good["data"][0], {"index": 1, "embedding": [1.0]}]),
        "the wrong dimension, consistently": variant(data=[{"index": 0, "embedding": [0.5, 0.5]},
                                                           {"index": 1, "embedding": [0.1, 0.9]}]),
        "a boolean in a vector": variant(data=[good["data"][0], {"index": 1, "embedding": _stub_vec(True, 0.0)}]),
        "a NaN in a vector": variant(data=[good["data"][0], {"index": 1, "embedding": _stub_vec(float("nan"), 0.0)}]),
        "an empty vector": variant(data=[{"index": 0, "embedding": []}, {"index": 1, "embedding": []}]),
        "not an object": ["list"],
    }
    for label, payload in cases.items():
        e = attempt(lambda p=payload: parse_embeddings(p, 2, model=LAW))
        check(isinstance(e, VoyageBadResponse), f"embeddings: {label} -> refused")

    rgood = {"object": "list", "model": RERANK, "usage": {"total_tokens": 3},
             "data": [{"index": 1, "relevance_score": 0.8}, {"index": 0, "relevance_score": 0.2}]}
    rcases = {
        "fewer results than documents": {**rgood, "data": rgood["data"][:1]},
        "a repeated index": {**rgood, "data": [rgood["data"][0], {"index": 1, "relevance_score": 0.1}]},
        "an index past the list": {**rgood, "data": [rgood["data"][0], {"index": 9, "relevance_score": 0.1}]},
        "a string score": {**rgood, "data": [rgood["data"][0], {"index": 0, "relevance_score": "high"}]},
        "an infinite score": {**rgood, "data": [rgood["data"][0], {"index": 0, "relevance_score": float("inf")}]},
    }
    for label, payload in rcases.items():
        e = attempt(lambda p=payload: parse_rerank(p, 2, model=RERANK))
        check(isinstance(e, VoyageBadResponse), f"rerank: {label} -> refused")

    def no_usage(endpoint, payload):
        d = emb_transport(endpoint, payload)
        d.pop("usage")
        return d
    e = attempt(lambda: embed(["x"], input_type="query", _transport=no_usage))
    check(isinstance(e, VoyageBadResponse) and "usage" in str(e),
          "a response without usage is refused: cost is observed, not assumed")

    # ── 5. input validation happens BEFORE any call ──────────────────────────
    calls: list = []

    def spy(endpoint, payload):
        calls.append(endpoint)
        return emb_transport(endpoint, payload)

    for label, fn in {
        "no texts": lambda: embed([], input_type="query", _transport=spy),
        "a bare string instead of a list": lambda: embed("abc", input_type="query", _transport=spy),
        "an empty text": lambda: embed(["ok", "  "], input_type="query", _transport=spy),
        "input_type omitted (the FAQ says never omit it for retrieval)":
            lambda: embed(["x"], input_type=None, _transport=spy),
        "an unpinned model": lambda: embed(["x"], input_type="query", model="voyage-3", _transport=spy),
        "a preview reranker": lambda: rerank("q", ["a"], model="rerank-3", _transport=spy),
        "more than 1,000 inputs": lambda: embed(["x"] * 1001, input_type="query", _transport=spy),
        "an empty query": lambda: rerank(" ", ["a"], _transport=spy),
        "no documents": lambda: rerank("q", [], _transport=spy),
        "top_k of 0": lambda: rerank("q", ["a"], top_k=0, _transport=spy),
        "top_k past the list": lambda: rerank("q", ["a"], top_k=2, _transport=spy),
    }.items():
        e = attempt(fn)
        check(isinstance(e, ValueError), f"refused before calling: {label}")
    check(not calls, "...and none of those reached the transport")

    # ── 6. HTTP / timeout errors raise, and are never an empty result ───────
    secret = "vk-SECRET-do-not-print-9f8e"
    os.environ["VOYAGE_API_KEY"] = secret
    check(available(), "with a key set, available() is True")
    import urllib.error as ue
    from checker import robots
    ctx_patch = mock.patch.object(robots, "ssl_context", return_value=object())
    ctx_patch.start()
    try:
        def http_error(code, body):
            return ue.HTTPError(DOC_URLS["embeddings"], code, "err", {},
                                io.BytesIO(body.encode("utf-8")))

        scenarios = {
            "HTTP 401 whose body echoes the key": http_error(401, json.dumps(
                {"detail": f"Invalid API key {secret}"})),
            "HTTP 429": http_error(429, json.dumps({"detail": "rate limit"})),
            "HTTP 500": http_error(500, "upstream"),
            "an unreachable host": ue.URLError("nodename nor servname provided"),
            "a read timeout": TimeoutError("The read operation timed out"),
        }
        for label, exc in scenarios.items():
            with mock.patch.object(urllib.request, "urlopen", side_effect=exc):
                res: list = []
                e = attempt(lambda: res.append(embed(["x"], input_type="query")))
                e2 = attempt(lambda: res.append(rerank("q", ["a"])))
            check(isinstance(e, VoyageServiceError) and isinstance(e2, VoyageServiceError),
                  f"{label}: embed() and rerank() raise VoyageServiceError")
            check(not res, f"{label}: no result object at all -- not [], not an abstention")
            check(secret not in str(e) and secret not in str(e2),
                  f"{label}: the key never appears in the error")
            check(not isinstance(e, LookupError),
                  f"{label}: the error is not a 'nothing found' type")
        with mock.patch.object(urllib.request, "urlopen",
                               side_effect=http_error(429, "{}")):
            e = attempt(lambda: embed(["x"], input_type="query"))
        check("429" in str(e) and "rate" in str(e).lower(),
              "a 429 says it is a rate limit, not a broken key")

        # a 200 whose body is not JSON
        class _Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch.object(urllib.request, "urlopen", return_value=_Resp(b"<html>oops")):
            e = attempt(lambda: embed(["x"], input_type="query"))
        check(isinstance(e, VoyageBadResponse), "a 200 with a non-JSON body is refused")

        with mock.patch.object(robots, "ssl_context", return_value=None):
            e = attempt(lambda: embed(["x"], input_type="query"))
        check(isinstance(e, VoyageUnavailable) and "unverified" in str(e),
              "no CA trust store -> refuses rather than calling unverified")
    finally:
        ctx_patch.stop()
        os.environ.pop("VOYAGE_API_KEY", None)

    # ── 7. cost comes from the price table ──────────────────────────────────
    check(abs(cost_inr(LAW, 1_000_000) - 0.12 * USD_TO_INR) < 1e-9,
          f"1M voyage-law-2 tokens cost $0.12 at list (Rs {cost_inr(LAW, 1_000_000)})")
    check(cost_inr(RERANK, 0) == 0.0, "zero tokens cost nothing")
    e = attempt(lambda: cost_inr("voyage-3", 10))
    check(isinstance(e, KeyError), "an unpriced model raises rather than costing Rs 0")


if __name__ == "__main__":
    _test()
