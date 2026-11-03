"""Operator views: dead jobs and usage."""
from __future__ import annotations

from gateway import access
from gateway.verbs import model_access
from gateway.verbs.core import Context, _refuse


def _jobs_dead(args: dict, ctx: Context) -> dict:
    """Jobs that stopped trying, newest first, with the reason each stopped.

    A1. DEAD is not FAILED: FAILED is one attempt that did not work and may be retried, DEAD
    is that we gave up. Without somewhere to read them, a dead job is work that silently
    never happened -- which is the failure mode a dead-letter state exists to remove.

    `mcp=False`: a dead-job list names the runs of one firm and the errors its documents
    provoked, and no agent task needs it. Tenant-scoped by the queue's own policy, not here.
    """
    if ctx.queue is None:
        return _refuse("NO_QUEUE",
                       "no queue is configured on this deployment, so there is no "
                       "dead-letter list. That is not the same as an empty one")
    try:
        limit = max(1, min(500, int(str(args.get("limit") or 100))))
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", "limit must be a number")
    jobs = ctx.queue.dead(limit)
    # 028. A dead job's args can carry a question about a matter, and the queue is a
    # service that sees the whole firm. A lawyer sees their own; an admin sees all.
    if not access.is_admin(ctx):
        jobs = [j for j in jobs if str(getattr(j, "actor_id", "") or "") == str(ctx.actor)]
    return {"dead": [j.to_dict() for j in jobs], "count": len(jobs)}


def _usage_status(args: dict, ctx: Context) -> dict:
    """What this firm and this person have spent, and what is left.

    P2. Read-only, and `mcp=False` for two reasons that both hold on their own: a spend
    figure is the deployment's commercial position and no agent task needs it, and
    `scripts/themis_mcp.py` pins the MCP tool count -- it is a Themis file, so a new MCP
    tool cannot be added from this side anyway.

    Identity comes from `ctx`, never from `args`. A caller that could name its own tenant
    could read another firm's spend, which is the one thing this verb must not allow.
    """
    ledger = model_access._ledger()
    if ledger is None:
        return _refuse("NO_LEDGER",
                       "the budget ledger cannot be read, so no figure here would be a "
                       "balance. This is not a statement that the budget is empty")
    return ledger.usage(tenant_id=ctx.tenant, user_id=ctx.actor)
