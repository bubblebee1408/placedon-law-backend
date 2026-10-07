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
SERVEABLE = frozenset({router.AZURE, router.BEDROCK})  # B1: Bedrock is the CLIENT-data provider


def available_providers(credit_exhausted=None) -> tuple[str, ...]:
    """What router.py offers, narrowed to what this gateway can actually call."""
    return tuple(p for p in router.providers_available(credit_exhausted=credit_exhausted)
                 if p in SERVEABLE)


def serve(origins, *, name: str, purpose: str, consequence: str = router.LOW,
          budget=None, available: tuple[str, ...] | None = None,
          sleep=None, transport=None, breaker=None) -> Served:
    """The route for this task, as a callable. Raises NotServed with a code, never None.

    `origins` is the public_only clearance the model call will be made under; it is bound
    here so the returned callable cannot be used against a different document.
    """
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

    if route.provider not in SERVEABLE:
        # A route to a provider we have no callable for would be a correct route we then
        # refuse -- adding one silently is how a matter document ends up at a free tier.
        raise NotServed(NO_MODEL,
                        f"the route chose {route.provider}/{route.model}, and the gateway "
                        f"serves {sorted(SERVEABLE)} today (PLAN_22 D3). No call was made.")

    usage: list = []
    if route.provider == router.BEDROCK:
        # B1: the CLIENT-data provider, ap-south-1. Its own adapter, its own India region.
        from checker import bedrock_model
        region = bedrock_model.REGION
        inner = (transport if transport is not None
                 else bedrock_model.as_text_model(origin=origins, model=route.model,
                                                  budget=budget, on_usage=usage.append))
        call = bedrock_model.with_backoff(inner, sleep=sleep or time.sleep)
    else:
        # Azure UAE: test-only for CLIENT data -- azure_model.refuse_unconfirmed_region blocks
        # a client document here -- and the public-text fallback when Bedrock is unavailable.
        region = REGION
        inner = (transport if transport is not None
                 else azure_model.as_text_model(origin=origins, model=route.model,
                                                budget=budget, on_usage=usage.append))
        call = azure_model.with_backoff(inner, sleep=sleep or time.sleep)

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
