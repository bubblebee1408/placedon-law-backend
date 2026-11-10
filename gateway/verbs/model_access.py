"""Budget ledger and model-provider routing: which provider may serve which task."""
from __future__ import annotations

from gateway.verbs.core import Context, _refuse


def _ledger():
    """The real rupee/request ledger, or None if it cannot be read.

    A missing guard is not permission to spend. Serving boundaries must refuse real
    model calls when this returns None; injected offline models do not use the ledger.
    """
    try:
        from backend.budget import default_tracker
        return default_tracker()
    except (OSError, ValueError):
        return None


def _ledger_for(ctx: "Context"):
    """`_ledger()` bound to the caller's firm and person, or None.

    Every model call that starts at the gateway goes through this, so each hold, gate and
    settlement is charged to `ctx.tenant` and capped by TENANT_MONTHLY_CAP_INR. A context
    with no tenant gets a tracker that REFUSES to spend rather than one that spends
    unattributed (see `BudgetTracker.attributed`). A test double without `attributed` is
    passed through unchanged.
    """
    ledger = _ledger()
    bind = getattr(ledger, "attributed", None)
    return bind(ctx.tenant, ctx.actor) if callable(bind) else ledger


def _provider_not_ready():
    """The typed access-pending exception (B1), imported lazily so verbs.py never pulls
    bedrock_model -- or boto3 -- in at module load; the keyless gate imports neither."""
    from checker.bedrock_model import ProviderNotReady
    return ProviderNotReady


# Which provider may serve each model task, declared per task -- never inferred from which
# credentials happen to resolve. router.py's NARRATION table lists Bedrock above Azure, so
# without this, adding AWS credentials silently moved research from Azure to Bedrock. Each
# entry is the provider the call site's text is CLEARED for (public_only.clear_matter(...,
# provider=...)), so a clearance and the route can no longer disagree. An unavailable
# provider is a refusal, never a substitute. Changing an entry is a data-residency
# decision (PLAN_22 D3): document summaries carry client documents and stay India-only.
# Tasks that may use the on-device model. Not a public_only.MATTER_PROVIDERS entry on
# purpose: that set is global, and adding "ollama" there let any caller (contract review)
# hand client text to an Ollama URL nobody checked. Here the only path is
# gateway/models.serve, which calls loopback alone and never a `:cloud` model.
ON_DEVICE_TASKS = frozenset({"ask"})

TASK_PROVIDERS: dict[str, tuple[str, ...]] = {
    # Owner decision 2026-10-28: the typed question goes to India (Bedrock) or stays on
    # this machine (on-device Ollama). Azure UAE never answered it: refuse_unconfirmed_region
    # refused every typed question there, so Ask could not answer at all.
    "ask": ("bedrock", "ollama"),       # research narration; the question is client text
    "critic": ("azure",),               # public corpus sentences
    "decompose": ("azure",),            # the user's question, cleared for azure
    "intake.classify": ("azure",),      # the user's typed words, cleared for azure
    "draft_prose": ("azure",),          # cleared for azure
    "review_contract": ("azure",),      # cleared for azure; the adapter refuses client
                                        # text on an unconfirmed region by default
    "review_grid_cell": ("azure",),     # cleared for azure
    "document_summary": ("bedrock",),   # client documents: India region only
}

# Client-text tasks that may ALSO use Azure, but only after the operator accepts its region
# (PLACEDON_ACCEPT_REGION names azure_model.DEPLOYMENT_REGION). Unset, these routes are
# exactly TASK_PROVIDERS. Owner decision 2026-10-28: Bedrock is blocked on the free AWS plan.
AZURE_OPT_IN_TASKS = frozenset({"ask", "document_summary"})


# The narration tasks (purpose=NARRATION at every call site). With PLACEDON_ANSWER_MODEL=gemini
# they are served by Gemini on Vertex asia-south1 ONLY -- no other provider behind it.
GEMINI_ANSWER_TASKS = frozenset({"ask", "critic", "draft_prose"})


def task_providers(task: str) -> tuple[str, ...]:
    """TASK_PROVIDERS[task], with Azure placed after Bedrock when its region is accepted."""
    from checker import azure_model, router
    from gateway.models import gemini_answers
    if task in GEMINI_ANSWER_TASKS and gemini_answers():
        return (router.GEMINI,)
    declared = TASK_PROVIDERS.get(task, ())
    if task not in AZURE_OPT_IN_TASKS or "azure" in declared or not azure_model.region_accepted():
        return declared
    head = tuple(p for p in declared if p == "bedrock")
    return head + ("azure",) + tuple(p for p in declared if p != "bedrock")


def _typed_text_origin(text: str, *, name: str, task: str, ctx: Context):
    """(clearance, None) or (None, NOT_PERMITTED refusal) for the user's own typed words.

    Typed text -- a research question, a drafting request -- may carry client information,
    so it is cleared as CLIENT text, and the region rule that applies to client documents
    applies to it: while the task's provider is Azure in an unaccepted region
    (azure_model.PLACEDON_ACCEPT_REGION unset), nothing is sent. Refused here, before a
    route is chosen, so the reader is told "not permitted" rather than "outage". An
    injected offline model (ctx.model_for) sends nothing anywhere, so it is not refused --
    the same exemption _served_or_refusal makes.
    """
    from checker import azure_model, public_only, router
    try:
        # Cleared for the task's own first provider, so the clearance and the route agree.
        provider = TASK_PROVIDERS.get(task, (router.AZURE,))[0]
        origin = public_only.clear_matter(text, name=name, provider=provider)
        if ctx.model_for is None and router.AZURE in TASK_PROVIDERS.get(task, ()):
            azure_model.refuse_unconfirmed_region(origin)
    except (public_only.NotPublic, azure_model.ModelRefused):
        return None, _refuse(
            "NOT_PERMITTED",
            f"Not sent: what you type may contain client information, and this task's "
            f"model is hosted in {azure_model.DEPLOYMENT_REGION}, which has not been "
            f"accepted for client data (PLAN_22 D3). No model call was made. This is not "
            f"a finding about the law.")
    return origin, None


def _served_or_refusal(origins, *, name: str, purpose: str, ctx: Context,
                       consequence: str | None = None,
                       timeout_seconds: int | None = None,
                       retry_tries: int = 3,
                       allowed_providers: tuple[str, ...] | None = None):
    """(Served|None, refusal dict|None). Never returns neither, never returns both."""
    from gateway.models import NotServed, available_providers, serve
    if ctx.model_for is not None:                     # a test or a caller-supplied model
        # A dataclass instance, not a class with `call` as a class attribute: a plain
        # function stored on a class becomes a BOUND METHOD through an instance, so
        # `served.call(prompt)` would pass `self` as the prompt. Caught on 29-09-2026.
        from gateway.models import Served
        return Served(call=ctx.model_for(origins), provider="stub", model="stub",
                      region="n/a", degraded=False, requires_review=False,
                      est_cost_inr=0.0), None
    declared = task_providers(name) if name in TASK_PROVIDERS else None
    if declared is None:
        return None, _refuse("NO_MODEL", f"No provider is declared for model task {name!r}. No call was made.")
    if allowed_providers is not None:
        declared = tuple(p for p in declared if p in allowed_providers)
    budget = _ledger_for(ctx)
    if budget is None:
        return None, _refuse("NO_BUDGET", "The spending guard is unavailable. No model call was made; retry after the budget store is restored.")
    try:
        from checker import router as _r
        from gateway.models import gemini_answers, require_gemini_config
        if name in GEMINI_ANSWER_TASKS and gemini_answers():
            require_gemini_config()     # GEMINI_NOT_CONFIGURED, not a vague NO_MODEL
        provider_scope = tuple(provider for provider in available_providers()
                               if provider in declared)
        if name in AZURE_OPT_IN_TASKS and _r.BEDROCK in provider_scope:
            # Azure is a fallback for these tasks, never a peer: the router's EXTRACTION
            # table ranks Azure above Bedrock, which would move summaries out of India.
            provider_scope = tuple(p for p in provider_scope if p != _r.AZURE)
        return serve(origins, name=name, purpose=purpose, budget=budget,
                     consequence=consequence or _r.LOW,
                     timeout_seconds=timeout_seconds, retry_tries=retry_tries,
                     available=provider_scope), None
    except NotServed as e:
        # REFUSED with the code, never a quiet UNVERIFIED: UNVERIFIED is a claim about
        # EVIDENCE, and there is no evidence when no call was made.
        return None, {"status": "REFUSED", "code": e.code, "detail": e.detail}
