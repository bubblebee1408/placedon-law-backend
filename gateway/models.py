"""Turning a router decision into a callable, or into a NAMED refusal.

The verbs used to run with `model=None`, which is not "no model" -- it is a pipeline that
extracts nothing and then reports every clause MISSING, indistinguishable from a contract
that genuinely lacks them. This module is what stands between those two outcomes.

**No new provider code.** Everything here is composition: `checker/router.py` decides which
model, `checker/azure_model.py` calls it, `with_backoff` honours a 429, and
`backend/budget.py` says whether a call may be made at all. If this file grew an HTTP
request it would be the second Azure client, and the second one drifts.

## Why a refusal is REFUSED and not FAILED

`agents/state.py` separates them and the separation is the product:

    REFUSED   we decided not to answer, and the code says which decision
              NO_MODEL  -- no route for this task with the providers available
              NO_BUDGET -- the guard refused before any call was made
    FAILED    we tried and the attempt broke. A transport error, and nothing else

A budget refusal recorded as FAILED sends someone to look at the network. A transport error
recorded as REFUSED says the system chose this, which it did not. And neither may become a
quiet UNVERIFIED: that is a claim about the EVIDENCE, and there is no evidence when no call
happened.

## The region, carried on every step

PLAN_22 D3 permits client documents only to endpoints whose hosting region is confirmed.
These deployments are in UAE North, and whether that is acceptable for an Indian in-house
team's contracts is a buyer's decision nobody has taken. So the region travels with the
route onto every run step rather than living in a deployment note nobody reads.

Run: PYTHONPATH=. python3 gateway/models.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from backend.azure_pricing import (TABLE, Priced, Unpriced, check_recordable,
                                   price_inr)
from checker import azure_model, router
from gateway import circuit as circuit_mod

# Where the `placedon-law-eval` deployments live. Recorded per step, not per deployment.
REGION = "UAE North"

NO_MODEL = "NO_MODEL"
NO_BUDGET = "NO_BUDGET"
# A1. The per-provider circuit breaker refused. A TRANSPORT failure -- no call was made, so
# nothing was looked at -- and never a finding. gateway/circuit.py says why at length.
NO_PROVIDER = circuit_mod.CIRCUIT_OPEN


class NotServed(RuntimeError):
    """No model will be called, and `code` says which decision that was."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Served:
    """A model that WILL be called, with everything a run step has to record.

    `usage` fills in as calls are made -- `serve()` binds it as the on_usage sink -- so the
    cost recorded on a step is derived from the tokens the provider REPORTED, not from
    router.estimate_inr. That estimate is 0.0 for Azure and says so only about
    MONTHLY_CAP_INR; recording it as the step's cost was a claim the call was free.
    """
    call: Callable[[str], str]
    provider: str
    model: str
    region: str
    degraded: bool
    requires_review: bool
    est_cost_inr: float
    usage: list = field(default_factory=list)

    def cost(self) -> tuple[float | None, str]:
        """(rupees, note). None whenever the number would be a guess."""
        if not self.usage:
            return None, ("UNPRICED: no call was made on this step, so there is nothing to "
                          "price.")
        last = self.usage[-1]
        if last.get("on_device"):
            # Not billed to anyone: no provider invoice exists for this call. Zero is the
            # billed cost, and the note says it is the laptop's own compute, not "free".
            return 0.0, "on-device model: no billed provider; runs on this machine's compute"
        return price_inr(last.get("deployment") or self.model,
                         tokens_in=last.get("tokens_in"),
                         tokens_out=last.get("tokens_out"))

    def step_fields(self) -> dict:
        cost, note = self.cost()
        # The invariant, checked where the number is produced rather than where it lands:
        # a BILLED provider never records exactly 0.0.
        check_recordable(self.provider, cost)
        return {"model": f"{self.provider}/{self.model}", "provider": self.provider,
                "region": self.region, "cost_inr": cost, "cost_note": note,
                "degraded": self.degraded}


# The providers this gateway has a callable for. Anthropic is PREFERRED by router.py and
# is deliberately not here: there is no Anthropic adapter wired into the gateway, and
# PLAN_22 §3 records that the founder has no Anthropic credit. Asking the router for a
# route among providers we cannot call would produce a correct route we then refuse --
# which is what happened on 29-09-2026, reported as NO_MODEL while Azure sat available.
SERVEABLE = frozenset({router.AZURE, router.BEDROCK,   # B1: Bedrock is the CLIENT-data provider
                       router.OLLAMA})                 # on-device only, see _local_endpoint

# Where an on-device answer was produced. Recorded on the step like any other region.
ON_DEVICE = "on-device"
# Operator narrowing: a comma list of providers this gateway may call. It can only REMOVE
# providers (e.g. `ollama` while Bedrock is blocked on the free AWS plan), never add one.
PROVIDERS_ENV = "PLACEDON_MODEL_PROVIDERS"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _operator_allows(provider: str) -> bool:
    import os
    raw = os.environ.get(PROVIDERS_ENV, "").strip()
    return not raw or provider in {p.strip() for p in raw.split(",")}


# ── PLACEDON_ANSWER_MODEL=gemini: answers from Gemini on Vertex AI, asia-south1 ──
# OFF unless the value is exactly "gemini"; off, nothing below is reached and SERVEABLE is
# what it was. On, narration tasks (model_access.GEMINI_ANSWER_TASKS) are served by Gemini
# alone: one retry on a transient error, then MODEL_BUSY. No fallback to another provider,
# because a quiet switch of provider is a quiet switch of data region.
ANSWER_MODEL_ENV = "PLACEDON_ANSWER_MODEL"
GEMINI_NOT_CONFIGURED = "GEMINI_NOT_CONFIGURED"
MODEL_BUSY = "MODEL_BUSY"
BUSY_MESSAGE = "Placedon is busy, please try again in a minute."
GEMINI_RETRY_SECONDS = 3.0


class ModelBusyError(RuntimeError):
    """Gemini failed twice on a transient error. Deliberately NOT gemini_model.ModelBusy:
    research_question treats that as "try the next model", which would be a fallback."""

    code = MODEL_BUSY

    def __init__(self, cause: str) -> None:
        super().__init__(f"{MODEL_BUSY}: {BUSY_MESSAGE}")
        self.cause = cause


def gemini_answers() -> bool:
    import os
    return os.environ.get(ANSWER_MODEL_ENV, "").strip() == "gemini"


def require_gemini_config() -> None:
    """Fail closed: the switch is on and Vertex in asia-south1 is not what is configured."""
    from checker import gemini_model
    problem = gemini_model.vertex_india_problem()
    if problem:
        raise NotServed(GEMINI_NOT_CONFIGURED,
                        f"{ANSWER_MODEL_ENV}=gemini, but {problem}. No call was made.")


def check_answer_model_at_startup() -> None:
    """Called by ops/asgi.py: a misconfigured switch stops the process, not the 1st answer."""
    if gemini_answers():
        try:
            require_gemini_config()
        except NotServed as e:
            raise SystemExit(f"{e.code}: {e.detail}") from None


def serveable() -> frozenset:
    return SERVEABLE | {router.GEMINI} if gemini_answers() else SERVEABLE


def busy_refusal() -> dict:
    """The user-presentable outcome when Gemini stayed busy through its one retry."""
    return {"status": "REFUSED", "code": MODEL_BUSY, "detail": BUSY_MESSAGE}


def _retry_once_then_busy(call, *, sleep):
    """One retry after GEMINI_RETRY_SECONDS on 429/500/503/timeout, then ModelBusyError.
    Any other error (a 4xx, a refusal) propagates on the first attempt, unretried."""
    import logging
    from checker.gemini_model import is_transient
    log = logging.getLogger(__name__)

    def _c(prompt: str) -> str:
        for attempt in (1, 2):
            try:
                return call(prompt)
            except Exception as e:                               # noqa: BLE001
                if not is_transient(e):
                    raise
                # Type and status only: the message may echo the prompt back.
                status = getattr(e, "http_status", None) or "timeout"
                if attempt == 2:
                    log.error("gemini_answer_busy status=%s type=%s", status,
                              type(e).__name__)
                    raise ModelBusyError(f"{type(e).__name__} {status}") from e
                log.warning("gemini_answer_retry status=%s type=%s", status,
                            type(e).__name__)
                sleep(GEMINI_RETRY_SECONDS)
        raise AssertionError("unreachable")                      # pragma: no cover
    return _c


def available_providers(credit_exhausted=None) -> tuple[str, ...]:
    """What router.py offers, narrowed to what this gateway can actually call."""
    allowed = serveable()
    return tuple(p for p in router.providers_available(credit_exhausted=credit_exhausted)
                 if p in allowed and _operator_allows(p))


def _on_device_timeout() -> int:
    """Seconds to wait for the on-device model. A laptop generates a few tokens a second, so
    the cloud-sized 120 s default refuses answers that were nearly done (seen 2026-10-28 on
    an 8 GB Mac). OLLAMA_TIMEOUT_S raises it; a bad value falls back to the default."""
    import os
    from checker import ollama_runner
    raw = os.environ.get("OLLAMA_TIMEOUT_S", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else ollama_runner.DEFAULT_TIMEOUT_S


def _local_endpoint() -> str:
    """OLLAMA_BASE_URL, only if it is this machine. Anything else is not 'local'."""
    import os
    url = os.environ.get("OLLAMA_BASE_URL", "").strip()
    # scheme://host[:port][/path] -- parsed by hand: this module opens no URL machinery of
    # its own (its self-test asserts it), it only decides whether the host is this machine.
    import re
    scheme, _, rest = url.partition("://")
    netloc = re.split(r"[/?#\\]", rest, maxsplit=1)[0]
    if scheme.lower() != "http" or "@" in netloc:
        netloc = ""          # userinfo or a non-http scheme: never treated as this machine
    host = (netloc[1:netloc.index("]")] if netloc.startswith("[") and "]" in netloc
            else netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc).lower()
    if host not in _LOOPBACK_HOSTS:
        raise NotServed(NO_MODEL,
                        f"the on-device route needs OLLAMA_BASE_URL on loopback; got "
                        f"{host or 'nothing'}. A remote Ollama is not on-device, so no call "
                        f"was made.")
    return url


def serve(origins, *, name: str, purpose: str, consequence: str = router.LOW,
          budget=None, available: tuple[str, ...] | None = None,
          sleep=None, transport=None, breaker=None, timeout_seconds: int | None = None,
          retry_tries: int = 3) -> Served:
    """The route for this task, as a callable. Raises NotServed with a code, never None.

    `origins` is the public_only clearance the model call will be made under; it is bound
    here so the returned callable cannot be used against a different document.
    """
    if timeout_seconds is not None and timeout_seconds < 1:
        raise ValueError("timeout_seconds must be positive")
    if retry_tries < 1:
        raise ValueError("retry_tries must be positive")
    providers = available_providers() if available is None else available
    if not providers:
        raise NotServed(
            NO_MODEL,
            f"no provider this gateway can call is available. It serves "
            f"{sorted(SERVEABLE)} today; router.py additionally knows "
            f"{sorted(set(router.providers_available()) - SERVEABLE)}, for which no "
            f"callable is wired here. No call was made.")
    task = router.Task(name, router.TEXT, consequence, purpose=purpose)
    try:
        route = router.route(task, available=providers)
    except router.NoRoute as e:
        raise NotServed(NO_MODEL, f"{e}") from None
    if route.provider == router.GEMINI and gemini_answers():
        require_gemini_config()          # before the breaker and the budget: nothing spent

    # A1. The breaker is consulted AFTER routing, because it is per PROVIDER and the
    # provider is not known until the route is chosen -- and BEFORE the budget, because a
    # provider we have stopped asking costs nothing and should not be priced.
    if breaker is not None:
        refusal = breaker.check(route.provider)
        if refusal is not None:
            raise NotServed(NO_PROVIDER, refusal.detail)

    if budget is not None:
        verdict = budget.can_make_call(0.0, model=route.model)
        if not verdict.allowed:
            raise NotServed(NO_BUDGET, verdict.reason)

    if route.provider not in serveable():
        # A route to a provider we have no callable for would be a correct route we then
        # refuse -- adding one silently is how a matter document ends up at a free tier.
        raise NotServed(NO_MODEL,
                        f"the route chose {route.provider}/{route.model}, and the gateway "
                        f"serves {sorted(SERVEABLE)} today (PLAN_22 D3). No call was made.")

    usage: list = []
    if route.provider == router.GEMINI:
        # Reached only with PLACEDON_ANSWER_MODEL=gemini (serveable() above). Vertex AI in
        # asia-south1, checked again inside the adapter on every call.
        from checker import gemini_model
        region = gemini_model.VERTEX_ANSWER_REGION
        inner = (transport if transport is not None
                 else gemini_model.as_vertex_answer_model(
                     origin=origins, model=route.model, budget=budget,
                     on_usage=usage.append, timeout=timeout_seconds or 90))
        call = _retry_once_then_busy(inner, sleep=sleep or time.sleep)
    elif route.provider == router.BEDROCK:
        # B1: the CLIENT-data provider, ap-south-1. Its own adapter, its own India region.
        from checker import bedrock_model
        region = bedrock_model.REGION
        inner = (transport if transport is not None
                 else bedrock_model.as_text_model(origin=origins, model=route.model,
                                                  budget=budget, on_usage=usage.append,
                                                  timeout_seconds=timeout_seconds))
        call = bedrock_model.with_backoff(inner, sleep=sleep or time.sleep,
                                          tries=retry_tries)
    elif route.provider == router.OLLAMA:
        # On-device: the prompt goes to loopback only, and router.route already refused a
        # `:cloud` model (which would leave the machine through the same localhost URL).
        from checker import ollama_runner
        region = ON_DEVICE
        if transport is not None:
            call = transport
        else:
            runner = ollama_runner.OllamaRunner(
                route.model, base_url=_local_endpoint(),
                timeout_s=timeout_seconds or _on_device_timeout())

            def call(prompt, _r=runner, _m=route.model):
                out = _r(prompt)
                usage.append({"deployment": _m, "on_device": True})
                return out
    else:
        # Azure UAE: test-only for CLIENT data -- azure_model.refuse_unconfirmed_region blocks
        # a client document here -- and the public-text fallback when Bedrock is unavailable.
        region = REGION
        inner = (transport if transport is not None
                 else azure_model.as_text_model(origin=origins, model=route.model,
                                                budget=budget, on_usage=usage.append,
                                                timeout=timeout_seconds))
        call = azure_model.with_backoff(inner, sleep=sleep or time.sleep,
                                        tries=retry_tries)

    if breaker is not None:
        # The breaker only learns anything if someone tells it the outcome, and the only
        # place that sees every outcome is the call itself. Wrapping it here means no caller
        # has to remember -- the failure mode a breaker wired by convention always has.
        def _watched(prompt, _call=call, _p=route.provider):
            try:
                out = _call(prompt)
            except Exception:
                breaker.record_failure(_p)
                raise
            breaker.record_success(_p)
            return out
        call = _watched

    return Served(call=call,
                  provider=route.provider, model=route.model, region=region,
                  degraded=route.degraded, requires_review=route.requires_review,
                  est_cost_inr=route.est_cost_inr, usage=usage)


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

    from checker import public_only
    act = public_only.ROOT / "corpus" / "companies_act" / "1220.json"
    origin = public_only.clear_file(act)
    NARR = router.NARRATION

    # ── a model that WILL be called ─────────────────────────────────────────
    s = serve(origin, name="ask", purpose=NARR, available=(router.AZURE,),
              transport=lambda p: "answered")
    check(s.provider == "azure" and s.model == "llama-3-3-70b",
          f"with Azure available the route is the served one ({s.provider}/{s.model})")
    check(s.region == REGION == "UAE North",
          f"...carrying the deployment region ({s.region})")
    check(s.degraded and not s.requires_review,
          "...marked degraded (Claude was preferred) but not requiring review: narration "
          "is LOW and every sentence is span-checked afterwards")
    f = s.step_fields()
    check(set(f) == {"model", "provider", "region", "cost_inr", "cost_note", "degraded"},
          f"a run step records provider, model, region and a cost WITH its note "
          f"({sorted(f)})")
    check(f["cost_inr"] is None and "no call was made" in f["cost_note"],
          f"before any call the cost is UNPRICED with a reason, never 0.0 "
          f"({f['cost_inr']}, {f['cost_note'][:40]})")

    # ── a BILLED provider can never record 0.0 ──────────────────────────────
    from backend.azure_pricing import BILLED_PROVIDERS, CostError
    check(s.provider in BILLED_PROVIDERS,
          f"{s.provider} is a billed provider -- these calls spend Azure for Students "
          f"credit, whatever router.estimate_inr says about the rupee cap")
    zero = Served(call=lambda p: "", provider="azure", model="llama-3-3-70b",
                  region=REGION, degraded=True, requires_review=False, est_cost_inr=0.0,
                  usage=[{"deployment": "llama-3-3-70b", "tokens_in": 0, "tokens_out": 0}])
    check(zero.cost()[0] is None and zero.cost()[1].startswith("UNPRICED:"),
          f"a call reporting ZERO tokens is UNPRICED, not free ({zero.cost()[1][:40]}…). "
          f"The reason here is the missing price rather than the zero counts, because the "
          f"table is asked first -- an unpriced deployment is unpriced whatever it used")
    try:
        Served(call=lambda p: "", provider="azure", model="m", region=REGION,
               degraded=False, requires_review=False, est_cost_inr=0.0,
               usage=[{"deployment": "m", "tokens_in": 1, "tokens_out": 1}]
               ).step_fields()
        check(True, "an unknown deployment is UNPRICED rather than 0.0, so it records fine")
    except CostError:
        check(False, "an unknown deployment should be UNPRICED, not an error")
    try:
        check_recordable("azure", 0.0)
        check(False, "0.0 from Azure is refused")
    except CostError:
        check(True, "...and a literal 0.0 from a billed provider is REFUSED before it can "
                    "reach a run step or a database")

    # after a real call, the cost comes from the tokens reported -- priced where a price is
    # on record, UNPRICED with a reason where none is.
    #
    # This asserted that llama-3-3-70b was UNPRICED "today". That was true until commit
    # 6d3ac4a added a VERIFIED Azure price for it, which made the assertion false and the
    # test wrong -- and nobody saw it, because gateway/models.py was not in
    # scripts/run_tests.sh and its twenty-five checks had never run in the gate. Both are
    # fixed: the suite is registered, and the assertion is about the BEHAVIOUR rather than
    # which models happen to be priced, so adding or removing a price cannot make it stale
    # again. CLAUDE.md records this lesson twice already about counts in prose.
    priced_model = next(k for k, v in sorted(TABLE.items()) if isinstance(v, Priced))
    s.usage.append({"deployment": priced_model, "tokens_in": 1200, "tokens_out": 300})
    c, note = s.cost()
    check(c is not None and c > 0 and not note.startswith("UNPRICED:"),
          f"a model WITH a price on record is priced from its tokens ({priced_model}: "
          f"{c} INR)")
    check("http" in note,
          f"...and the note carries the SOURCE of that price, so a rupee figure in a run "
          f"step can be checked against the vendor ({note[:60]}…)")

    unpriced_model = next((k for k, v in sorted(TABLE.items()) if isinstance(v, Unpriced)),
                          None)
    check(unpriced_model is not None,
          "the price table still holds at least one deliberately UNPRICED model, so the "
          "other branch is reachable")
    if unpriced_model is not None:
        s2 = Served(call=lambda p: "", provider="azure", model=unpriced_model, region=REGION,
                    degraded=False, requires_review=False, est_cost_inr=0.0,
                    usage=[{"deployment": unpriced_model, "tokens_in": 1200,
                            "tokens_out": 300}])
        c2, note2 = s2.cost()
        check(c2 is None and note2.startswith("UNPRICED:"),
              f"...while a model with NO price is UNPRICED rather than 0.0 -- a zero would "
              f"be a claim that the call was free ({unpriced_model}: {note2[:40]}…)")
        check("price" in note2.lower(),
              "...and its reason points at the price table, which is where the fix goes")

    # ── the two refusals, each with its own code ────────────────────────────
    try:
        serve(origin, name="ask", purpose=NARR, available=())
        check(False, "no providers is a refusal")
    except NotServed as e:
        check(e.code == NO_MODEL,
              f"no provider at all is REFUSED/{e.code}, not an empty answer")

    try:
        serve(origin, name="ask", purpose=NARR, available=(router.GEMINI,))
        check(False, "a non-Azure route is refused here")
    except NotServed as e:
        check(e.code == NO_MODEL and "bedrock" in e.detail and "azure" in e.detail,
              "a route that chose Gemini is refused rather than served by a callable this "
              "module does not have -- the refusal names the serveable set (azure, bedrock), "
              "and adding a provider silently is how a matter document reaches a free tier")

    # ── B1: a Bedrock route is served, with the India region on the step ────────
    _seen_bd: list = []
    s_bd = serve(origin, name="ask", purpose=NARR, available=(router.BEDROCK,),
                 transport=lambda _p: "phrased from the held provision",
                 sleep=lambda _s: None)
    check(s_bd.provider == router.BEDROCK and s_bd.region == "ap-south-1",
          f"a Bedrock route is served, and the step carries the INDIA region "
          f"({s_bd.provider}/{s_bd.region})")
    check(s_bd.call("prompt") == "phrased from the held provision",
          "...and its callable is the Bedrock adapter (here a transport), not Azure's")

    class Broke:
        def can_make_call(self, *a, **k):
            class V:
                allowed = False
                reason = "daily request cap reached: 20 of 20"
            return V()

    try:
        serve(origin, name="ask", purpose=NARR, available=(router.AZURE,), budget=Broke(),
              transport=lambda p: "x")
        check(False, "an exhausted budget is a refusal")
    except NotServed as e:
        check(e.code == NO_BUDGET and "20 of 20" in e.detail,
              f"an exhausted budget is REFUSED/{e.code}, carrying the ledger's own reason")
    check(router.ANTHROPIC not in SERVEABLE and router.AZURE in SERVEABLE,
          f"the gateway serves only {sorted(SERVEABLE)}: router.py PREFERS Anthropic and "
          f"there is no Anthropic callable here, so asking for a route among providers we "
          f"cannot call returns a correct route we then refuse")
    check(all(p in SERVEABLE for p in available_providers()),
          f"...so available_providers() narrows to what can be called "
          f"({available_providers()})")
    check(NO_BUDGET != NO_MODEL,
          "...and the two codes are distinct: one needs money or tomorrow, the other a "
          "provider, and a reader should not have to guess which")

    # ── the backoff is applied, not merely available ────────────────────────
    from checker.azure_model import RateLimited
    tries, waits = [], []

    def flaky(prompt: str) -> str:
        tries.append(1)
        if len(tries) < 3:
            raise RateLimited("Azure HTTP 429")
        return "eventually"

    s2 = serve(origin, name="ask", purpose=NARR, available=(router.AZURE,),
               transport=flaky, sleep=waits.append)
    check(s2.call("p") == "eventually" and len(tries) == 3,
          "the returned callable retries a 429 rather than reporting the model refused")
    check(len(waits) == 2, f"...waiting between attempts ({waits})")

    def dead(prompt: str) -> str:
        raise RuntimeError("connection reset")

    s3 = serve(origin, name="ask", purpose=NARR, available=(router.AZURE,),
               transport=dead, sleep=waits.append)
    try:
        s3.call("p")
        check(False, "a transport error propagates")
    except RuntimeError:
        check(True, "...while a transport error propagates unchanged, so the caller can "
                    "record FAILED rather than inventing a refusal we did not make")

    # ── PLACEDON_ANSWER_MODEL=gemini: Vertex asia-south1, retry once, then busy ─
    import os as _os
    from unittest import mock as _mock
    from checker import gemini_model as _gm
    from checker.prompt_safety import wrap_untrusted as _wrap
    from gateway.verbs import model_access as _ma
    _ON = {ANSWER_MODEL_ENV: "gemini", "GOOGLE_CLOUD_PROJECT": "demo-proj",
           "GOOGLE_CLOUD_LOCATION": "asia-south1"}
    _G = (router.GEMINI,)

    class _HttpErr(_gm.ModelUnavailable):
        def __init__(self, status):
            super().__init__(f"HTTP {status}")
            self.http_status = status

    def _fails(*statuses, then="answered"):
        seen = []

        def _t(prompt):
            seen.append(prompt)
            if len(seen) <= len(statuses):
                s = statuses[len(seen) - 1]
                raise TimeoutError("read timed out") if s == "timeout" else _HttpErr(s)
            return then
        return _t, seen

    # default OFF: unset, or any value but "gemini", changes nothing
    for raw in (None, "", "Gemini", "claude", "azure"):
        env = {} if raw is None else {ANSWER_MODEL_ENV: raw}
        with _mock.patch.dict(_os.environ, env, clear=False):
            if raw is None:
                _os.environ.pop(ANSWER_MODEL_ENV, None)
            check(not gemini_answers() and serveable() == SERVEABLE
                  and _ma.task_providers("ask") == _ma.TASK_PROVIDERS["ask"]
                  and _ma.task_providers("draft_prose") == _ma.TASK_PROVIDERS["draft_prose"],
                  f"{ANSWER_MODEL_ENV}={raw!r} is OFF: serveable set and task routes are "
                  f"exactly as before")
            try:
                serve(origin, name="ask", purpose=NARR, available=_G,
                      transport=lambda p: "x")
                check(False, "off, a Gemini route is still refused")
            except NotServed as e:
                check(e.code == NO_MODEL, f"...and a Gemini route is still NO_MODEL ({e.code})")
            check_answer_model_at_startup()          # off: never stops the process

    # ON + wrong region / no Vertex: refused before any call, and at start-up
    for bad in ({"GOOGLE_CLOUD_LOCATION": "us-central1"}, {"GOOGLE_CLOUD_LOCATION": ""},
                {"GOOGLE_CLOUD_PROJECT": "", "GEMINI_API_KEY": "k-test"}):
        calls = []
        with _mock.patch.dict(_os.environ, _ON | bad):
            try:
                serve(origin, name="ask", purpose=NARR, available=_G,
                      transport=lambda p: calls.append(p))
                check(False, f"{bad} is refused")
            except NotServed as e:
                check(e.code == GEMINI_NOT_CONFIGURED and not calls,
                      f"on with {bad}: REFUSED/{e.code} and no call made")
            try:
                check_answer_model_at_startup()
                check(False, f"{bad} stops start-up")
            except SystemExit as e:
                check(GEMINI_NOT_CONFIGURED in str(e),
                      f"...and the process refuses to start ({str(e)[:50]}...)")
            _s, refusal = _ma._served_or_refusal(
                (origin,), name="ask", purpose=NARR, ctx=_ma.Context())
            check(_s is None and refusal["code"] == GEMINI_NOT_CONFIGURED,
                  "...and the verb layer returns the same code, not a vague NO_MODEL")

    with _mock.patch.dict(_os.environ, _ON):
        check(_ma.task_providers("ask") == _G and _ma.task_providers("critic") == _G
              and _ma.task_providers("document_summary") == ("bedrock",),
              "on: narration tasks are Gemini ONLY; other tasks keep their routes")
        s_g = serve(origin, name="ask", purpose=NARR, available=_G, transport=lambda p: "ok",
                    sleep=lambda _s: None)
        check(s_g.provider == router.GEMINI and s_g.model == _gm.FLASH
              and s_g.region == "asia-south1",
              f"on: served by {s_g.provider}/{s_g.model} in {s_g.region} (the pinned Flash)")

        t, seen = _fails(503)
        waits = []
        s_r = serve(origin, name="ask", purpose=NARR, available=_G, transport=t,
                    sleep=waits.append)
        check(s_r.call("p") == "answered" and len(seen) == 2 and waits == [3.0],
              f"a 503 then success: exactly one retry, after 3 s ({len(seen)} calls, {waits})")
        for first in (429, 500, "timeout"):
            t, seen = _fails(first)
            serve(origin, name="ask", purpose=NARR, available=_G, transport=t,
                  sleep=lambda _s: None).call("p")
            check(len(seen) == 2, f"...{first} is transient too: retried once")

        t, seen = _fails(400)
        try:
            serve(origin, name="ask", purpose=NARR, available=_G, transport=t,
                  sleep=lambda _s: None).call("p")
            check(False, "a 400 propagates")
        except _HttpErr:
            check(len(seen) == 1, "a 400 is NOT retried (one call) and is not MODEL_BUSY")

        # two failures => MODEL_BUSY, and no other provider is ever called
        others = []
        t, seen = _fails(503, 503)
        # "gateway.models", not __name__: run as a script this file is __main__, and the
        # verb layer imports the package copy.
        with _mock.patch("gateway.models.available_providers",
                         return_value=(router.AZURE, router.BEDROCK, router.OLLAMA,
                                       router.GEMINI)), \
             _mock.patch.object(_gm, "as_vertex_answer_model", side_effect=lambda **_: t), \
             _mock.patch("checker.azure_model.as_text_model",
                         side_effect=lambda **_: others.append("azure")), \
             _mock.patch("checker.bedrock_model.as_text_model",
                         side_effect=lambda **_: others.append("bedrock")):
            _free = type("B", (), {"can_make_call": lambda self, *a, **k: type(
                "V", (), {"allowed": True, "reason": ""})()})()
            with _mock.patch("gateway.verbs.model_access._ledger_for", return_value=_free), \
                 _mock.patch("time.sleep", lambda _s: None):
                s_b, refusal = _ma._served_or_refusal((origin,), name="ask", purpose=NARR,
                                                      ctx=_ma.Context())
            check(refusal is None and s_b.provider == router.GEMINI,
                  "with every provider available, the verb layer still picks Gemini alone")
            try:
                s_b.call("p")
                check(False, "two transient failures are MODEL_BUSY")
            except RuntimeError as e:        # the package's ModelBusyError (see above)
                check(type(e).__name__ == "ModelBusyError" and e.code == MODEL_BUSY and BUSY_MESSAGE in str(e) and len(seen) == 2,
                      f"two failures => {e.code} '{BUSY_MESSAGE}' after 2 calls")
            check(not others, f"...and no other provider's adapter was built ({others})")
        check(busy_refusal() == {"status": "REFUSED", "code": MODEL_BUSY,
                                 "detail": BUSY_MESSAGE},
              "busy_refusal() is the user-presentable outcome")

        # the ask verb turns MODEL_BUSY into that outcome, with a FAILED run recorded
        from gateway import verbs as _verbs
        from gateway.store import MemoryBackend
        t, _seen = _fails(*[503] * 20)       # every call: decompose may share the stub
        s_ask = Served(call=_retry_once_then_busy(t, sleep=lambda _s: None),
                       provider=router.GEMINI, model=_gm.FLASH, region="asia-south1",
                       degraded=True, requires_review=False, est_cost_inr=0.0)
        from checker import public_only as _po
        with _mock.patch("gateway.verbs.model_access._typed_text_origin",
                         side_effect=lambda q, **_: (_po.clear_matter(
                             q, name="q", provider="bedrock"), None)), \
             _mock.patch("gateway.verbs.model_access._served_or_refusal",
                         return_value=(s_ask, None)):
            r = _verbs._ask({"question": "What notice is needed to call a board meeting "
                                         "under Section 173?"},
                            _verbs.Context(store=MemoryBackend()))
        check(r.get("code") == MODEL_BUSY and r.get("detail") == BUSY_MESSAGE
              and r.get("run_id"),
              f"ask returns MODEL_BUSY with the busy message and a run id "
              f"({r.get('status')}/{r.get('code')})")
        from gateway.verbs.answers import _envelope_for
        env_b = _envelope_for("RESEARCH_QUESTION", r, as_of="2026-11-10", ctx=_ma.Context())
        check(BUSY_MESSAGE in str(env_b), "...and the envelope shows the user the busy message")

        # spend: the real adapter reserves, settles the reported tokens, and the step is priced
        class _Ledger:
            def __init__(self):
                self.held, self.settled = [], []

            def can_make_call(self, *a, **k):
                return type("V", (), {"allowed": True, "reason": ""})()

            def reserve(self, **k):
                self.held.append(k)
                return type("R", (), {"allowed": True, "id": "r1"})()

            def settle(self, rid, actual, **k):
                self.settled.append((rid, actual, k))
                return type("S", (), {"allowed": True})()

        led = _Ledger()
        import json as _json
        prov = _json.loads(act.read_text())["content"][:300]
        prompt = "Answer from this only.\n" + _wrap(prov, "s1") + "\nWhat does it say?"
        reply = {"candidates": [{"content": {"parts": [{"text": "It says."}]}}],
                 "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 250,
                                   "thoughtsTokenCount": 50}}
        posted = []
        with _mock.patch.object(_gm, "_post",
                                side_effect=lambda m, p, t=90: posted.append(m) or reply):
            s_sp = serve(origin, name="ask", purpose=NARR, available=_G, budget=led,
                         sleep=lambda _s: None)
            out = s_sp.call(prompt)
        from backend.azure_pricing import GEMINI_TABLE
        want = GEMINI_TABLE[_gm.FLASH].inr(1200, 300)
        check(out == "It says." and posted == [_gm.FLASH],
              "the real Vertex adapter is what serve() wires (one post, the pinned Flash)")
        check(len(led.held) == 1 and led.held[0]["model"] == "vertex:" + _gm.FLASH
              and led.held[0]["amount_inr"] > 0,
              f"spend: the worst case is reserved in rupees first "
              f"(Rs {led.held[0]['amount_inr'] if led.held else None})")
        check(led.settled == [("r1", want, {"actual_calls": 1})],
              f"...and settled at the REPORTED tokens, thinking counted as output "
              f"(Rs {want})")
        fields = s_sp.step_fields()
        check(fields["cost_inr"] == want and "UNVERIFIED" in fields["cost_note"]
              and fields["region"] == "asia-south1",
              f"...and the run step carries the same rupees, marked as an estimate "
              f"({fields['cost_inr']}, {fields['cost_note'][-60:]})")

    # ── no second HTTP client ───────────────────────────────────────────────
    from pathlib import Path
    src = Path(__file__).read_text().split("def _test(")[0]
    for token in ("urllib", "requests", "httpx", "api-key", "Bearer "):
        check(token not in src,
              f"this module opens no socket of its own ({token!r} absent) -- it composes "
              f"router, azure_model and budget, and a second client would drift")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
