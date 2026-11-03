"""Runs: runs.get/trace/approve/reject/submit/cancel/preview, and the durable queue path (O2)."""
from __future__ import annotations

from gateway import access
from gateway.verbs.ask import _ask
from gateway.verbs.core import Context, MIN_REASON_CHARS, _affirmed, _refuse
from gateway.verbs.documents import _document_summary_job
from gateway.verbs.model_access import _ledger_for
from gateway.verbs.review import _review_contract, _review_document
from gateway.verbs.review_table import _review_grid_cell
from gateway.verbs.vault import _vault_ingest_job


def _runs_get(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no run store is configured on this deployment")
    row = ctx.store.read(args["run_id"])
    if row is None or not access.row_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no run {args['run_id']!r}")
    return {k: v for k, v in row.items() if k != "steps"}


def _runs_trace(args: dict, ctx: Context) -> dict:
    if ctx.store is None:
        return _refuse("NO_STORE", "no run store is configured on this deployment")
    row = ctx.store.read(args["run_id"])
    if row is None or not access.row_allowed(ctx, row):
        return _refuse("NOT_FOUND", f"no run {args['run_id']!r}")
    # `critic_enabled` travels with the trace (016). A trace is what someone reads to
    # work out why an answer says what it says, and "a layer that may REMOVE sentences was
    # running" belongs there rather than only in a column nobody queries. NULL is NOT
    # RECORDED -- every run from before 016 -- and is reported as such, not as false.
    enabled = row.get("critic_enabled")
    return {"run_id": row.get("id"), "steps": row.get("steps", []),
            "critic_enabled": enabled,
            "critic_note": ("not recorded for this run: it predates the setting being "
                            "stored, and false would claim we looked"
                            if enabled is None else
                            "the critic was ON when this run was written; a sentence it "
                            "removed is in the steps" if enabled else
                            "the critic was OFF when this run was written, so nothing was "
                            "removed by it")}


def _decide(args: dict, ctx: Context, *, decision: str) -> dict:
    """One human decision on one item, stored as labelled data (PLAN_23 rule 5).

    Refuses more than it accepts, on purpose. Every refusal here is a way the label could
    have been recorded meaninglessly, and a meaningless label is worse than none: it is
    counted later as evidence a person agreed.
    """
    import uuid

    run_id = (args.get("run_id") or "").strip()
    item_ref = (args.get("item_ref") or "").strip()
    reason = (args.get("reason") or "").strip()
    quoted_span = (args.get("quoted_span") or "").strip()
    quote_viewed = _affirmed(args.get("quote_viewed"))

    if not run_id:
        return _refuse("BAD_REQUEST", "run_id is required")
    if not item_ref:
        return _refuse("BAD_REQUEST",
                       "item_ref is required: a decision about a run is not a decision, "
                       "because a run has many findings and a reviewer judged one of them")
    if len(reason) < MIN_REASON_CHARS:
        return _refuse(
            "REASON_REQUIRED",
            f"a written reason of at least {MIN_REASON_CHARS} characters is required to "
            f"{decision.lower()} an item. A decision with no reason records that somebody "
            f"clicked, which is the automation bias this gate exists to prevent -- and it "
            f"is a label that teaches a later evaluation nothing.")
    if not quoted_span:
        return _refuse(
            "QUOTE_REQUIRED",
            "quoted_span is required: it is the text the reviewer was looking at when they "
            "decided. Without it the label is attached to nothing a person can be shown to "
            "have read.")
    # PLAN_23 §1.8: the quote is viewed before a finding can be ACCEPTED (Goddard et al.,
    # JAMIA 2012, automation bias). A rejection without it is still recorded, as not viewed:
    # it withholds a finding rather than clearing one. The flag is attested by the surface
    # that showed the quote, the same standing as quoted_span; O6's UI is what enforces it.
    if decision == "APPROVED" and not quote_viewed:
        return _refuse(
            "QUOTE_NOT_VIEWED",
            "quote_viewed must be true to approve: the reviewer has to have seen the quoted "
            "text before accepting the finding. An approval without it is a click, and it "
            "would be stored as a person's agreement.")
    if ctx.store is None:
        return _refuse("NO_STORE",
                       "there is no store configured, so this decision could not be kept. "
                       "A human decision that is not stored is one that was not made.")

    run = ctx.store.read_run(run_id)
    if run is None or not access.row_allowed(ctx, run):
        return _refuse("NOT_FOUND", f"no run {run_id!r}")
    # 028. Signing off a finding in a matter is a write on that matter.
    if not access.row_allowed(ctx, run, access.WRITE):
        return _refuse("FORBIDDEN", access.READ_ONLY)

    # The item must exist IN THAT RUN. Without this a reviewer could label an item that
    # was never served, and the label would be about nothing.
    refs = {p.get("source_ref") for p in run.get("propositions", [])}
    if item_ref not in refs:
        return _refuse("NOT_FOUND",
                       f"run {run_id} has no item {item_ref!r}. It served "
                       f"{len(refs)} item(s); a decision on one it did not serve would be "
                       f"a label about nothing.")

    from gateway.store import DecisionExists
    row = {"decision_id": str(uuid.uuid4()), "run_id": run_id, "item_ref": item_ref,
           "decision": decision, "reason": reason, "quoted_span": quoted_span,
           "quote_viewed": quote_viewed,
           # Copied from the RUN, never taken from the caller: the versions a decision
           # was made against are the ones the finding was computed against.
           "law_versions": run.get("law_versions"),
           "actor_id": ctx.actor,
           "decided_at": ctx.clock() if ctx.clock else None}
    try:
        stored = ctx.store.write_decision(row)
    except DecisionExists as e:
        return _refuse("ALREADY_DECIDED", str(e))
    return {"status": "RECORDED", **stored}


def _runs_approve(args: dict, ctx: Context) -> dict:
    return _decide(args, ctx, decision="APPROVED")


def _runs_reject(args: dict, ctx: Context) -> dict:
    return _decide(args, ctx, decision="REJECTED")


# ── the durable path (PLAN_23 O2) ────────────────────────────────────────────

# Which intents a run may be submitted for. Deliberately a subset, and deliberately named:
# every one of these is served by the SAME handler the synchronous verb calls, so a queued
# run and a request-path run cannot answer differently.
QUEUED_INTENTS: dict[str, str] = {
    "review_document": "_review_document",
    "review_contract": "_review_contract",
    "research_question": "_ask",
    # H4: one cell of a review grid. Unlike the three above, this handler WRITES -- the
    # cell is the product, not a run record -- so `queue_handlers` hands it the real
    # context. See the comment there.
    "review_grid_cell": "_review_grid_cell",
    # V1: ingest one uploaded vault document. `vault.upload` has always enqueued this and
    # nothing could run it -- the worker found no handler, dead-lettered the job as not
    # retryable, and the document stayed PENDING having been "queued for ingestion".
    # Writes, like a grid cell: an ingested document is the product, not a run record.
    "vault_ingest": "_vault_ingest_job",
    # D1: bounded client-document synthesis in the conversation job lane.
    "document_summary": "_document_summary_job",
}

# Intents whose handler needs the STORE, because what they produce is not a run record.
# Everything else runs store-less so it cannot write a second run.
STORE_WRITING_INTENTS = frozenset({"review_grid_cell", "vault_ingest", "document_summary"})

# Intents only the server enqueues. `vault.upload` queues `vault_ingest` with the row it
# just wrote; a client that could submit one could name any content hash, and the file
# store is content-addressed and shared, so a hash alone would read anyone's file.
INTERNAL_INTENTS = frozenset({"vault_ingest"})


def queue_handlers(ctx: "Context") -> dict:
    """{intent: handler(args) -> (steps, result)} for gateway/worker.py.

    Each one runs the request-path handler against a STORE-LESS context, so it builds its
    steps and its answer without writing a second run, then hands both back. The worker owns
    the persistence; the handler owns the meaning. One implementation, two callers.
    """
    from dataclasses import replace as _replace

    def wrap(fn, *, keep_store: bool = False):
        def run(args: dict):
            # Store-less by default: a handler that could write a run would write a SECOND
            # one, and the worker already owns that record.
            #
            # `keep_store` is the exception, and it is narrow. A review-grid cell's answer
            # is not a run record -- it is the product, one row of the table the user is
            # waiting for -- and the worker persists runs, not cells. So the cell handler
            # gets the real store and writes its own row, idempotently
            # (`write_grid_cell(if_pending=True)`), while the worker persists the run as
            # it does for every other intent.
            inner = ctx if keep_store else _replace(ctx, store=None, last_steps=[])
            inner = _replace(inner, last_steps=[])
            result = fn(args, inner)
            return list(inner.last_steps), result
        return run

    by_name = {"_review_document": _review_document,
               "_review_contract": _review_contract,
               "_ask": _ask,
               "_review_grid_cell": _review_grid_cell,
               "_vault_ingest_job": _vault_ingest_job,
               "_document_summary_job": _document_summary_job}
    return {intent: wrap(by_name[fn], keep_store=(intent in STORE_WRITING_INTENTS))
            for intent, fn in QUEUED_INTENTS.items()}


def _runs_submit(args: dict, ctx: Context) -> dict:
    """Accept work and return a run id. The answer arrives later, from a worker.

    This is the verb PLAN_23 layer 3 asks for: the run is durable as soon as this returns,
    and it is durable because it is in the database, not because the socket stayed open.
    """
    import uuid

    intent = (args.get("intent") or "").strip()
    if intent not in QUEUED_INTENTS or intent in INTERNAL_INTENTS:
        return _refuse("BAD_REQUEST",
                       f"{intent!r} is not an intent a run may be submitted for; one of "
                       f"{sorted(set(QUEUED_INTENTS) - INTERNAL_INTENTS)}. An intent nobody declared is not an "
                       f"intent with an empty plan.")
    payload = args.get("args")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return _refuse("BAD_REQUEST", "args must be an object")
    if ctx.store is None or ctx.queue is None:
        return _refuse("NO_STORE",
                       "this deployment has no durable queue, so a submitted run could not "
                       "survive the process that accepted it. Use the synchronous verb, or "
                       "configure PLACEDON_DATABASE_URL.")

    from gateway.jobs import QueueError, QueueFull
    # 028. Whatever the payload names -- a matter, a conversation, documents -- this
    # actor must be allowed to work on, checked before anything is written or queued.
    if not access.args_allowed(ctx, payload):
        return _refuse("NOT_FOUND", "Something this run names is unavailable to you.")
    run_id = str(uuid.uuid4())
    # The run row FIRST. A job pointing at a run that does not exist is a foreign-key error
    # on Postgres and a dangling id in memory, and the poller would get NOT_FOUND for work
    # that was accepted.
    ctx.store.write({"id": run_id, "intent": intent, "status": "PLANNED",
                     "actor_id": ctx.actor,
                     "matter_id": (str(payload.get("matter_id") or "").strip() or None),
                     "refusal_code": None, "steps": [], "propositions": []})
    try:
        # A1. INTERACTIVE: this is the path a person is watching a spinner on.
        from gateway.jobs import INTERACTIVE as _LANE_INTERACTIVE
        job = ctx.queue.enqueue(run_id=run_id, intent=intent, args=payload,
                                lane=_LANE_INTERACTIVE)
    except QueueFull:
        ctx.store.set_run(run_id, status="FAILED", result={"error": "Queue capacity reached; no job was added."})
        return _refuse("BUSY", "The work queue is full. Retry shortly.")
    except QueueError as e:
        ctx.store.set_run(run_id, status="FAILED", result={"error": "The job could not be queued."})
        return _refuse("BAD_REQUEST", str(e))
    return {"status": "PLANNED", "run_id": run_id, "job_id": job.job_id,
            "intent": intent,
            "note": "accepted and queued. Poll runs.get for the status; it moves "
                    "PLANNED -> RUNNING -> ANSWERED, REFUSED or FAILED."}


def _runs_cancel(args: dict, ctx: Context) -> dict:
    """Ask a run to stop at its next step boundary.

    A REQUEST, not a kill. There is no way to stop a step mid-flight and there should not
    be: a half-written step with no record of why is worse than one more step. What is
    already done stays in the trace — PLAN_23 layer 3 says a cancellation compensates, it
    does not delete.
    """
    run_id = (args.get("run_id") or "").strip()
    if not run_id:
        return _refuse("BAD_REQUEST", "run_id is required")
    if ctx.queue is None:
        return _refuse("NO_STORE", "this deployment has no queue, so there is no running "
                                   "job to cancel.")
    # 028. The queue is service-scoped and would cancel any run in the firm, so the
    # caller's own access to the run is checked here, and refused with the same answer
    # as a run that has nothing to cancel.
    if ctx.store is not None and not access.row_allowed(
            ctx, ctx.store.read(run_id), access.WRITE):
        return _refuse("NOT_CANCELLABLE",
                       f"run {run_id} has no job that is still running. A finished run is "
                       f"not cancelled retroactively — its trace is what happened.")
    if ctx.queue.request_cancel(run_id):
        return {"status": "CANCEL_REQUESTED", "run_id": run_id,
                "note": "the run will stop at its next step boundary. Everything already "
                        "done stays in the trace, marked CANCELLED where it stopped."}
    # Not found and already-finished are one answer on purpose: both mean there is nothing
    # running to stop, and telling them apart would leak whether a run id exists.
    return _refuse("NOT_CANCELLABLE",
                   f"run {run_id} has no job that is still running. A finished run is not "
                   f"cancelled retroactively — its trace is what happened.")


def _runs_preview(args: dict, ctx: Context) -> dict:
    """T4: what a fan-out WOULD do, and what it would cost, before anything runs. Read-only.

    The lawyer sees the plan, its agents, and a real price -- not an estimate. The price is
    real because it is produced by actually calling `budget.reserve` for every worker, which
    is the same arithmetic the runner will do, rather than by multiplying a per-call figure
    somebody wrote down. A quote computed a second way is a quote that can disagree with the
    bill.

    ## It reserves, and then RELEASES

    Immediately, before returning. A preview that held its reservations would leak the firm's
    cap every time somebody looked at a plan and thought better of it -- which is A-016
    exactly, measured at 58 leaked reservations worth ₹115.99 against a ₹116.67 cap. So the
    figure is a QUOTE and the response says so in those words: nothing is held, and the
    runner reserves again when it starts.

    The cost of that choice is honest and stated: between the preview and the start, another
    run may take the headroom, and the start can then be refused NO_BUDGET for a plan the
    preview priced. That is better than a preview that quietly spends the cap.
    """
    from agents import multi_plan as mp

    goal = (args.get("goal") or "").strip()
    raw = args.get("workers") or []
    if not isinstance(raw, list):
        return _refuse("BAD_REQUEST", "workers must be a list of {agent, task} objects")
    try:
        workers = tuple(mp.Task(str(w.get("agent") or ""), str(w.get("task") or ""))
                        for w in raw if isinstance(w, dict))
    except Exception as e:                                       # noqa: BLE001
        return _refuse("BAD_REQUEST", f"workers: {e}")
    if len(workers) != len(raw):
        return _refuse("BAD_REQUEST", "every worker must be an object with agent and task")

    plan = mp.MultiPlan(goal, workers)
    ledger = _ledger_for(ctx)
    verdict = mp.validate(plan, budget=ledger)

    quoted = 0.0
    if verdict.ok and verdict.reservations:
        quoted = verdict.reserved_inr
        # RELEASED at once. See the docstring: a preview that held would be A-016.
        for rid in verdict.reservations:
            # No provider request ran during a preview, so release reserved request quota too.
            ledger.settle(rid, 0.0, actual_calls=0)

    body = {"plan": plan.to_dict(),
            "agents": sorted({w.agent for w in workers}),
            "registered_agents": list(mp.WORKER_AGENTS),
            "max_workers": mp.MAX_WORKERS,
            "would_run": verdict.ok,
            "quoted_inr": (quoted if verdict.ok and quoted else None),
            "held_inr": 0.0,
            "reason": verdict.reason,
            "note": ("A QUOTE, not a hold. Nothing is reserved by a preview: a preview that "
                     "held its reservations would leak the firm's daily cap every time "
                     "somebody looked at a plan and thought better of it. The runner "
                     "reserves again when it starts, so between this and that another run "
                     "may take the headroom and the start can be refused NO_BUDGET for a "
                     "plan priced here.")}
    if not verdict.ok:
        # A refusal is a PRODUCT state here, not an error: "this plan would not run, and
        # here is why" is the whole purpose of a preview. So it comes back 200 with
        # `would_run: false` rather than as a 4xx a caller has to catch.
        body["refusal_code"] = verdict.code
        body["detail"] = verdict.detail
        body["quoted_inr"] = None
    return body
