"""Review tables (H4): create, status, export, list, cancel, and the per-cell job."""
from __future__ import annotations

from gateway import access
from gateway.verbs import model_access
from gateway.verbs.core import Context, _refuse
from gateway.verbs.model_access import _ledger_for


# ── H4: review tables ────────────────────────────────────────────────────────
#
# The verbs are `review_table.*` because that is what a user calls it; the code is
# `review_grid` because `checker/review_table.py` is an older, unrelated module. One
# feature, three names, written down in docs/START_HERE.md §5.

# Every cell is a RUN (gateway/jobs.py refuses two jobs for one run), so a grid is a
# multiplier on the queue and on the bill: 40 documents x 6 columns is 240 runs. The cap is
# a declared number rather than a judgement at call time, and it is checked BEFORE anything
# is enqueued -- a half-enqueued grid is the worst outcome, because the user is billed for
# the part that ran and has no table.
MAX_GRID_CELLS = 500


_CONTENT_HASH = __import__("re").compile(r"[0-9a-f]{64}")


MAX_DOCUMENT_NAME = 255


def _grid_document_names(ctx: Context, document_ids: list) -> dict:
    """034. {sha256: file name} for a new grid, read from this process's uploads or the
    vault document this actor may read. Never from the caller: a name is what the firm
    stored, not what a request claims. A hash with no readable name is left out."""
    names: dict = {}
    for raw in document_ids:
        d = raw.strip()
        name = str((ctx.documents.get(d) or {}).get("name") or "").strip()
        # Same order as access.content_allowed: this process's upload, else the vault.
        if d not in ctx.documents and ctx.store is not None:
            rows = [r for r in ctx.store.vault_documents_by_sha256(d)
                    if access.document_allowed(ctx, r)]
            name = str((rows[0] if rows else {}).get("name") or "").strip()
        if name:
            names[d] = name[:MAX_DOCUMENT_NAME]
    return names


def _review_table_create(args: dict, ctx: Context) -> dict:
    """Define a grid and enqueue one job per cell. Refuses above the cell cap.

    A WRITE verb: it creates a grid and queues work, so `mcp_tools()` keeps it off MCP.
    """
    import uuid
    from agents import review_grid as rgr
    from checker import review_grid as rg

    name = (args.get("name") or "").strip()
    if not name:
        return _refuse("BAD_REQUEST", "a review table needs a name")
    raw_docs = args.get("document_ids") or []
    raw_cols = args.get("columns") or []
    if not isinstance(raw_docs, list) or not all(isinstance(d, str) for d in raw_docs):
        return _refuse("BAD_REQUEST", "document_ids must be a list of strings")
    if not isinstance(raw_cols, list):
        return _refuse("BAD_REQUEST", "columns must be a list of objects")
    if not raw_docs:
        return _refuse("BAD_REQUEST", "a review table needs at least one document")
    # `review_grid_cells.document_id` is CHECKed against `^[0-9a-f]{64}$` (011): a grid
    # addresses documents by CONTENT HASH, so the same bytes are the same row and a table is
    # replayable. A vault `document_id` is a uuid, and passing one used to reach the database
    # and come back as a 500 -- a well-formed request answered with a stack trace. The vault
    # reports each document's `sha256` in `vault.status`, which is the value to pass.
    bad = [d for d in raw_docs if not _CONTENT_HASH.fullmatch(d.strip())]
    if bad:
        return _refuse("BAD_REQUEST",
                       f"a review table addresses documents by CONTENT HASH -- a 64-character "
                       f"sha256, so that the same bytes are always the same row and the table "
                       f"can be replayed. {len(bad)} of {len(raw_docs)} id(s) are not one "
                       f"(first: {bad[0][:24]!r}). A vault document's hash is the `sha256` "
                       f"field of `vault.status`; its `document_id` is a uuid and names the "
                       f"vault record, not the bytes.")
    if not raw_cols:
        return _refuse("BAD_REQUEST",
                       "a review table with no columns asks nothing of its documents")

    try:
        columns = tuple(rg.Column(str(c.get("name") or ""), str(c.get("kind") or ""),
                                  str(c.get("question") or ""))
                        for c in raw_cols if isinstance(c, dict))
    except rg.TableError as e:
        return _refuse("BAD_REQUEST", str(e))
    if len(columns) != len(raw_cols):
        return _refuse("BAD_REQUEST", "every column must be an object")

    # ── the cost guard, before anything is enqueued ──────────────────────────
    cells = len(raw_docs) * len(columns)
    if cells > MAX_GRID_CELLS:
        return _refuse("GRID_TOO_LARGE",
                       f"{len(raw_docs)} document(s) x {len(columns)} column(s) = "
                       f"{cells} cells, and the cap is {MAX_GRID_CELLS}. Every cell is a "
                       f"separate run and a separate model call, so this is a bill and a "
                       f"queue depth, not just a big table. Narrow the documents or the "
                       f"columns, or raise the cap deliberately.")
    ledger = _ledger_for(ctx)
    if ledger is None:
        return _refuse("NO_BUDGET", "budget ledger unavailable; no table was saved or cell enqueued")
    verdict = ledger.can_make_call()
    if not verdict.allowed:
        return _refuse("NO_BUDGET",
                       f"{verdict.reason} No cell was enqueued, so nothing was spent "
                       f"on this table.")

    store = ctx.store
    if store is None:
        return _refuse("NO_STORE",
                       "a review table is durable work: it needs a store, and returning "
                       "one that vanishes on restart would be a lie about what was saved")
    grid_id = (args.get("grid_id") or "").strip() or str(uuid.uuid4())
    table = rg.Table(grid_id, name, columns, tuple(raw_docs))
    # 028. A cell reads bytes by hash straight from the file store, so the hash itself
    # must belong to a document this actor may read -- or a hash is a key to any file.
    if not all(access.content_allowed(ctx, d.strip()) for d in raw_docs):
        return _refuse("NOT_FOUND", "A selected document is unavailable to you.")
    store.write_grid({"grid_id": grid_id, "name": name, "actor_id": ctx.actor,
                      "columns": [{"name": c.name, "kind": c.kind,
                                   "question": c.question} for c in columns],
                      "document_ids": list(raw_docs),
                      "document_names": _grid_document_names(ctx, raw_docs)})

    sched = rgr.Scheduled(grid_id)
    if ctx.queue is not None:
        # The budget is PASSED, so each cell's worst case is reserved before it is
        # dispatched. It was not, until move 2: `schedule()` reserves only when a budget is
        # supplied and this call supplied none, so A1's per-cell reservation was wired and
        # unreachable -- the same shape as the vault's file store in move 1.
        sched = rgr.schedule(
            table, queue=ctx.queue, budget=ledger,
            # Same reason as the vault upload above: the cell's run row has to exist before
            # its job can reference it.
            ensure_run=lambda rid: ctx.store.write(
                {"id": rid, "intent": rgr.INTENT, "status": "PLANNED", "actor_id": ctx.actor,
                 "refusal_code": None, "steps": [], "propositions": []}))
        if sched.paused_budget:
            # Persisted, because `create` returns this ONCE. A caller that did not keep the
            # response -- a reloaded page, the CLI, an MCP tool -- has no other way to learn
            # it, and the cells cannot say: a cell never dispatched and a cell waiting its
            # turn are both PENDING. 022, and DECISION_grid_budget_state.md.
            store.pause_grid(grid_id, reason=sched.pause_reason,
                             not_dispatched=len(sched.not_scheduled))
    out = {"grid_id": grid_id, "name": name, "cells": cells,
           "documents": len(raw_docs), "columns": len(columns),
           "scheduled": sched.to_dict(),
           "cap": MAX_GRID_CELLS,
           # UNPRICED stays UNPRICED: a grid's cost is the sum of calls that have not
           # happened, and a number here would be an estimate presented as a price. The
           # per-call ledger prices each cell when it runs.
           "estimated_cost_inr": None,
           "cost_note": ("UNPRICED: every cell is a separate model call and none has run "
                         "yet. The ledger prices each one as it happens; a figure here "
                         "would be a guess wearing a currency symbol."),
           "note": ("One run per cell. Poll review_table.status; nothing is answered until "
                    "a worker has run it, and a PENDING cell is not a NOT_FOUND one.")}
    return out


def _review_table_status(args: dict, ctx: Context) -> dict:
    """The grid, its per-state counts and whether it is complete. Read-only."""
    from agents import review_grid as rgr

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, cancelled = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    out = rgr.status(table, cancelled=cancelled)
    # 022: the budget state, from the row rather than from the cells. `table_state` sits
    # beside complete/cancelled because PAUSED_BUDGET is a STATE -- the table is resumable
    # the moment the cap is raised, and calling it an error would put transport language on
    # a deployment's spending decision.
    grid_row = ctx.store.read_grid(grid_id) or {}
    # 034: the file names stored at create; {} for a table made before then.
    out["document_names"] = dict(grid_row.get("document_names") or {})
    paused = bool(grid_row.get("paused_budget"))
    not_dispatched = int(grid_row.get("cells_not_dispatched") or 0)
    out["paused_budget"] = paused
    out["pause_reason"] = grid_row.get("pause_reason") or ""
    out["cells_not_dispatched"] = not_dispatched
    out["cells_dispatched"] = max(0, int(out.get("cells") or 0) - not_dispatched)
    out["table_state"] = ("CANCELLED" if cancelled else
                          "PAUSED_BUDGET" if paused else
                          "COMPLETE" if out.get("complete") else "RUNNING")
    # ── move 3: a PENDING cell says WHY it is pending ────────────────────────
    # "Not dispatched because nothing is running" and "dispatched, waiting its turn" are
    # both PENDING on the cell, and the difference is the whole of whether anything will
    # ever happen. A silent PENDING is a table that looks busy and is not.
    pending_cells = [c for c in ctx.store.read_grid_cells(grid_id)
                     if (c.get("state") or "") == "PENDING"]
    if ctx.queue is None:
        out["dispatch"] = {
            "queue_configured": False,
            "never_dispatched": int(out.get("cells") or 0),
            "awaiting_worker": 0, "claimed": 0,
            "note": ("not dispatched: no queue is configured on this deployment, so "
                     "nothing will run these cells. They are PENDING because nothing has "
                     "been asked to answer them, not because they are waiting their turn")}
    else:
        from agents.review_grid import run_id_for_cell
        runs = [run_id_for_cell(grid_id, c["document_id"], c["column_name"])
                for c in pending_cells]
        counts = ctx.queue.claim_counts(runs)
        never, waiting = counts["missing"], counts["unclaimed"]
        if never and not waiting and not counts["claimed"]:
            note = (f"not dispatched: {never} cell(s) have no job in the queue at all. "
                    f"Nothing will answer them until they are scheduled again")
        elif waiting and not counts["claimed"]:
            note = (f"not dispatched: no worker. {waiting} cell(s) are queued and nothing "
                    f"has claimed one. Run `python3 -m gateway.worker` against this "
                    f"deployment, or they stay PENDING indefinitely")
        elif waiting:
            note = (f"{counts['claimed']} cell(s) in flight, {waiting} queued and not yet "
                    f"claimed")
        else:
            note = (f"{counts['claimed']} cell(s) in flight; nothing is waiting unclaimed"
                    if counts["claimed"] else "no cell is pending")
        if never and (waiting or counts["claimed"]):
            note += f". {never} cell(s) have no job in the queue"
        out["dispatch"] = {
            "queue_configured": True,
            "never_dispatched": never,
            "awaiting_worker": waiting,
            "claimed": counts["claimed"],
            "note": note}

    if paused:
        out["pause_note"] = (
            f"{out['cells_dispatched']} cell(s) were dispatched and {not_dispatched} were "
            f"not. The undispatched cells stay PENDING -- they are not failures, and "
            f"nothing was charged for the reservation that was refused. Raise the cap and "
            f"create the table again: only the cells that have not run are dispatched.")
    # The running total, from the cells this verb already read -- not from 240 extra reads
    # of each cell's run steps, which is why 013 put the debit on the cell.
    out["spend"] = _grid_spend(ctx.store.read_grid_cells(grid_id))
    out["cells_detail"] = [table.cell(d, c.name).to_dict()
                           if hasattr(table.cell(d, c.name), "to_dict")
                           else {"document_id": d, "column": c.name,
                                 "state": table.cell(d, c.name).state,
                                 "value": table.cell(d, c.name).value,
                                 "quote": table.cell(d, c.name).quote,
                                 "reason": table.cell(d, c.name).reason}
                           for d in table.document_ids for c in table.columns]
    return out


def _review_table_export(args: dict, ctx: Context) -> dict:
    """The grid as CSV. Every cell non-empty, and none of them able to run as a formula."""
    from checker import review_grid as rg

    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, cancelled = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    stored = (ctx.store.read_grid(grid_id) or {}).get("document_names") or {}
    names = {d: str(stored.get(d) or (ctx.documents.get(d) or {}).get("name") or d)
             for d in table.document_ids}
    t = table.tally()
    return {"grid_id": grid_id, "filename": f"{table.name[:40] or 'review-table'}.csv",
            "content_type": "text/csv",
            "csv": rg.to_csv(table, names=names),
            "complete": table.complete, "cancelled": cancelled,
            "findings": t["findings"], "cells": t["cells"],
            "note": ("Every cell carries words, never a blank: NOT FOUND, NEEDS LAWYER, "
                     "PENDING and COULD NOT RUN each read differently, because a blank "
                     "makes 'the clause is absent' and 'we did not read it' identical. "
                     "Values beginning = + - @ are prefixed with a single quote so the "
                     "file cannot run as a formula in a spreadsheet.")}


def _review_table_list(args: dict, ctx: Context) -> dict:
    """The firm's review tables this actor may read, newest first. Names, dates, state and
    counts only: no question text and no cell value, so the list leaks nothing a table's
    own page would not. Paged with an opaque cursor, the same shape as draft.list."""
    import base64
    import json
    import uuid
    from datetime import datetime
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    try:
        limit = int(str(args.get("limit") or "20"))
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", "limit must be an integer from 1 to 50")
    if limit < 1 or limit > 50:
        return _refuse("BAD_REQUEST", "limit must be an integer from 1 to 50")
    before_created_at = before_grid_id = None
    cursor = str(args.get("cursor") or "").strip()
    if cursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if not isinstance(payload, dict) or set(payload) != {"created_at", "grid_id"}:
                raise ValueError("unexpected cursor shape")
            before_created_at = str(payload["created_at"])
            if datetime.fromisoformat(before_created_at.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("timestamp must include a timezone")
            before_grid_id = str(payload["grid_id"])
            if str(uuid.UUID(before_grid_id)) != before_grid_id:
                raise ValueError("grid id is not canonical")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return _refuse("BAD_REQUEST", f"invalid review table cursor: {exc}")
    rows = ctx.store.list_grids(limit=limit + 1, before_created_at=before_created_at,
                                before_grid_id=before_grid_id)
    # 028. Postgres filters by policy (tenant, then matter or owner); this applies the same
    # rule `review_table.status` applies, so the list never names a table its page refuses.
    rows = [r for r in rows if access.row_allowed(ctx, r)]
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        packed = json.dumps({"created_at": page[-1]["created_at"],
                             "grid_id": page[-1]["grid_id"]},
                            separators=(",", ":")).encode("utf-8")
        next_cursor = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
    tables = []
    for r in page:
        state = ("CANCELLED" if r["cancelled_at"] else
                 "PAUSED_BUDGET" if r["paused_budget"] else
                 "COMPLETE" if r["cells"] and not r["pending"] else "RUNNING")
        tables.append({"grid_id": r["grid_id"], "name": r["name"],
                       "created_at": r["created_at"], "created_by": r["actor_id"],
                       "mine": bool(r["actor_id"]) and str(r["actor_id"]) == str(ctx.actor or ""),
                       "matter_id": r["matter_id"], "table_state": state,
                       "documents": r["documents"], "columns": r["columns"],
                       "cells": r["cells"], "cells_pending": r["pending"]})
    return {"tables": tables, "next_cursor": next_cursor,
            "note": ("Review tables you may open, newest first. Names and counts only; "
                     "open one with review_table.status to read its answers.")}


def _load_grid(ctx: Context, grid_id: str):
    """(Table, cancelled) from the store, or (None, False)."""
    from checker import review_grid as rg

    row = ctx.store.read_grid(grid_id)
    if row is None or not access.row_allowed(ctx, row):
        return None, False  # 028. Someone else's table reads as no table.
    columns = tuple(rg.Column(c["name"], c["kind"], c["question"])
                    for c in row.get("columns") or ())
    cells = []
    for c in ctx.store.read_grid_cells(grid_id):
        cells.append(rg.Cell(document_id=c["document_id"], column=c["column_name"],
                             state=c["state"], value=c.get("value") or "",
                             quote=c.get("quote") or "", reason=c.get("reason") or ""))
    table = rg.Table(grid_id, row.get("name") or "", columns,
                     tuple(row.get("document_ids") or ()), tuple(cells))
    return table, bool(row.get("cancelled_at"))


def _cell_answerer(ctx: Context, debits: list | None = None):
    """`answer(question, kind, text) -> (value, quote) | None`, from the routed model.

    `debits` collects one `Served.step_fields()` per call -- the provider, the model, the
    region and the rupees derived from the tokens the provider REPORTED. A review table is
    the most expensive thing this product does (one call per cell, 240 for a 40x6 table),
    and until this list existed the only record of that spend was a sentence with no number
    in it.

    Raises when no model can be served, and that is deliberate: `agents/review_grid.run_cell`
    turns a raise into a FAILED cell ("this did not run"), which is the truth. Returning
    None would make it NOT_FOUND -- asserting the clause is absent from a document nobody
    read, in a table a lawyer will rely on.
    """
    from checker import router
    from checker.prompt_safety import UNTRUSTED_CLAUSE, wrap_untrusted

    def answer(question: str, kind: str, text: str):
        from checker import public_only
        origin = public_only.clear_matter(text, name="review grid cell",
                                          provider=router.AZURE)
        served, refusal = model_access._served_or_refusal(origin, name="review_grid_cell",
                                             purpose=router.EXTRACTION, ctx=ctx,
                                             consequence=router.LOW)
        if refusal:
            raise RuntimeError(f"no model for this cell: {refusal['code']}")
        prompt = (UNTRUSTED_CLAUSE + "\n\n"
                  + f"Answer this question about the document below, as a {kind} value.\n"
                  + f"Question: {question}\n\n"
                  + "Reply with exactly two lines:\n"
                  + "VALUE: <the answer, or NONE if the document does not answer it>\n"
                  + "QUOTE: <the sentence you read it from, verbatim>\n\n"
                  + wrap_untrusted(text, "the document"))
        try:
            raw = str(served.call(prompt) or "")
        finally:
            # In a `finally`, because the call is what costs money: a reply that then
            # fails to parse, or a transport error after the provider billed us, still
            # has to be debited. A ledger that only records successful cells
            # systematically understates the bill.
            if debits is not None:
                debits.append(served.step_fields())
        return _parse_cell_reply(raw)

    return answer


def _parse_cell_reply(raw: str):
    """The two-line reply -> (value, quote), or None for an explicit NONE.

    Raises `review_grid.Unreadable` when the reply does not follow the format, and that
    distinction is the whole function: the first version set `value = ""`, found no
    `VALUE:` line, and returned None -- which `run_cell` reads as NOT_FOUND. So a model
    that replied in prose, in JSON, or with an apology made the cell assert that the clause
    is ABSENT from a document it had just described. An absence is a finding, and that one
    was manufactured here.

    Three outcomes, and `None` is reserved for the one the MODEL stated:

        VALUE: 3 years / QUOTE: ...   -> the pair
        VALUE: NONE                   -> None, because the model said so
        anything else                 -> Unreadable -> NEEDS_LAWYER

    A `VALUE:` line that is empty is Unreadable too, not NONE: a blank is not a statement
    that the document is silent, and the model had a word for that.
    """
    from agents.review_grid import Unreadable
    value = quote = ""
    saw_value = False
    for line in (raw or "").splitlines():
        if line.upper().startswith("VALUE:"):
            saw_value = True
            value = line.split(":", 1)[1].strip()
        elif line.upper().startswith("QUOTE:"):
            quote = line.split(":", 1)[1].strip()
    if not saw_value:
        raise Unreadable(
            f"no VALUE: line in a {len(raw or '')}-character reply, so nothing was read "
            f"from it. This is NOT an absence: the reply began "
            f"{(raw or '').strip()[:80]!r}")
    if not value:
        raise Unreadable(
            "the VALUE: line was empty. A blank is not a statement that the document is "
            "silent -- the format has NONE for that -- so it is not recorded as one")
    if value.upper() == "NONE":
        return None
    return (value, quote)


def _cell_debit(debits: list, *, stubbed: bool) -> dict:
    """{provider, cost_inr, cost_note} for one cell. NEVER a zero standing in for unknown.

    Three ways a cell has no number, and they are different facts, so they get different
    notes rather than one 0.00:

        a priced call      the rupees from `Served.step_fields()`
        a call we cannot price   NULL, and the note begins "UNPRICED:"
        no billed call at all   NULL, and the note says which: a stub answerer, or a cell
                                that returned before anything was sent (an unreadable
                                document, no text held)

    `review_table.status` sums only the first kind and says how many of the others there
    were, because a total that silently included them would be a smaller number presented
    as the bill.
    """
    if debits:
        f = debits[-1]
        return {"provider": f.get("provider"), "cost_inr": f.get("cost_inr"),
                "cost_note": f.get("cost_note")}
    if stubbed:
        return {"provider": None, "cost_inr": None,
                "cost_note": ("no billed call was made: a caller-supplied answerer served "
                              "this cell. This is not a cost of zero.")}
    return {"provider": None, "cost_inr": None,
            "cost_note": ("no model was called for this cell -- it returned before "
                          "anything was sent. This is not a cost of zero.")}


def _grid_spend(rows) -> dict:
    """The grid's running total, and what the total does NOT include.

    A single number would have to choose what to do with the cells that ran and could not
    be priced, and both choices are wrong: dropping them makes the total read as the bill,
    and counting them as 0.00 claims those calls were free. So the total is the PRICED
    cells only, it is labelled a lower bound whenever anything else ran, and the counts
    that make it one are beside it.
    """
    priced = [float(r["cost_inr"]) for r in rows if r.get("cost_inr") is not None]
    ran = [r for r in rows if str(r.get("state") or "") != "PENDING"]
    unpriced = [r for r in ran if r.get("cost_inr") is None]
    pending = [r for r in rows if str(r.get("state") or "") == "PENDING"]
    total = round(sum(priced), 4) if priced else None
    if total is None:
        note = (f"UNPRICED: not one of this table's {len(rows)} cells carries a price, so "
                f"there is no total. {len(ran)} cell(s) have run. A zero here would claim "
                f"the work was free.")
    elif unpriced or pending:
        note = (f"At least Rs.{total:.4f}, over {len(priced)} priced cell(s). "
                f"{len(unpriced)} cell(s) ran and could not be priced and "
                f"{len(pending)} have not run, so the true figure is HIGHER. This is a "
                f"lower bound, not the bill.")
    else:
        note = (f"Rs.{total:.4f} over all {len(priced)} cells, every one priced from the "
                f"tokens the provider reported.")
    return {"total_inr": total, "priced_cells": len(priced),
            "unpriced_cells": len(unpriced), "pending_cells": len(pending),
            "is_lower_bound": total is not None and bool(unpriced or pending),
            "note": note}


def _review_grid_cell(args: dict, ctx: Context) -> dict:
    """Answer ONE cell and write it. The queue handler for `review_grid_cell`.

    Writes through `write_grid_cell(if_pending=True)`, so a worker handed the same cell
    twice after a crash does not overwrite the answer the first attempt gave. The write
    returning False is reported, not swallowed: it is the exactly-once guard firing.
    """
    from agents import review_grid as rgr

    if ctx.store is None:
        return {"status": "FAILED", "error": "a grid cell needs the store to write to"}
    answer = (ctx.model_for(()) if ctx.model_for is not None else None)
    stubbed = answer is not None
    debits: list = []
    if answer is None:
        answer = _cell_answerer(ctx, debits)
    # `ctx.documents` is an injected dict, and on a WORKER it is empty: the gate filled it
    # and no running process ever did, so every cell dispatched by `review_table.create`
    # died on RunnerError("no such document") -- the table was wired to a fixture. A grid's
    # document_id IS the content hash, and the file store is content-addressed, so the bytes
    # are one `get` away. Read-only, and only for the cell in hand.
    documents = ctx.documents
    did = str(args.get("document_id") or "")
    if did not in documents and ctx.files is not None:
        try:
            documents = {**documents,
                         did: {"text": ctx.files.get(did).decode("utf-8", "replace")}}
        except Exception:                                        # noqa: BLE001
            # Left absent on purpose. `run_cell` raises RunnerError for a document it cannot
            # see, which becomes a FAILED cell naming the document -- the right answer, and
            # one a fabricated empty string would have hidden behind NOT_FOUND.
            pass
    # Settlement must succeed before a completed cell is published. Failed accounting
    # leaves its hold for reconciliation rather than retrying cleanup at a zero cost.
    settled = {"done": False, "attempted": False}

    class SettlementFailed(Exception):
        pass

    def _settle(actual_inr: float | None) -> None:
        rid = (args.get("reservation_id") or "").strip() if args.get("reservation_id") else ""
        if not rid or settled["attempted"]:
            return
        settled["attempted"] = True
        try:
            ledger = _ledger_for(ctx)
            if ledger is None:
                raise SettlementFailed("budget ledger unavailable")
            verdict = ledger.settle(rid, actual_inr)
            if not verdict.allowed:
                raise SettlementFailed("budget settlement refused")
        except Exception as error:
            raise SettlementFailed("budget reconciliation required; cell result withheld") from error
        settled["done"] = True

    try:
        try:
            cell = rgr.run_cell(args, documents=documents, answer=answer)
        except rgr.RunnerError as e:
            _settle(0.0)
            return {"status": "FAILED", "error": str(e),
                    "reservation_settled": settled["done"]}
        debit = _cell_debit(debits, stubbed=stubbed)
        # Missing usage after a provider call consumes the hold, never a fabricated zero.
        _settle(debit.get("cost_inr") if debits else 0.0)
        wrote = ctx.store.write_grid_cell(
            {"grid_id": args["grid_id"], "document_id": cell.document_id,
             "column_name": cell.column, "state": cell.state, "value": cell.value,
             "quote": cell.quote, "reason": cell.reason,
             "provider": debit["provider"], "cost_inr": debit["cost_inr"],
             "cost_note": debit["cost_note"]})
        # The ledger `run_steps` has been since 003, with the same numbers. A cell is a run,
        # so this is one step per cell and the two records cannot disagree: they are built
        # from one `Served.step_fields()`.
        ctx.last_steps.append({
            "capability": "review_grid.cell",
            "status": "FAILED" if cell.state == "FAILED" else "ANSWERED",
            **debit})
        return {"status": "ANSWERED" if wrote else "ANSWERED",
                "grid_id": args["grid_id"], "document_id": cell.document_id,
                "column": cell.column, "cell_state": cell.state,
                "written": wrote, "cost_inr": debit["cost_inr"],
                "cost_note": debit["cost_note"],
                "reservation_settled": settled["done"],
                "note": (None if wrote else
                         "this cell was already answered; the earlier answer was kept. A "
                         "worker handed the same cell twice does not overwrite it.")}
    except SettlementFailed as error:
        return {"status": "FAILED", "code": "BUDGET_RECONCILIATION_REQUIRED",
                "error": str(error), "reservation_settled": False}
    except Exception:
        try:
            _settle(None)
        except SettlementFailed as error:
            return {"status": "FAILED", "code": "BUDGET_RECONCILIATION_REQUIRED",
                    "error": str(error), "reservation_settled": False}
        raise


def _review_table_cancel(args: dict, ctx: Context) -> dict:
    """Stop scheduling. Deletes nothing. A WRITE verb, so it is off MCP.

    The compensation for "you changed your mind at cell 30 of 40" is to stop, not to undo
    29 answers that were correct and paid for (PLAN_23 §1.9). Cells already answered stay
    exactly as they are; cells not yet run stay PENDING, not FAILED -- nothing went wrong,
    and FAILED would put transport language on a decision the user made.
    """
    if ctx.store is None:
        return _refuse("NO_STORE", "no store is configured")
    grid_id = (args.get("grid_id") or "").strip()
    if not grid_id:
        return _refuse("BAD_REQUEST", "grid_id is required")
    table, already = _load_grid(ctx, grid_id)
    if table is None:
        return _refuse("NOT_FOUND", f"no review table {grid_id!r} for this tenant")
    if already:
        return _refuse("ALREADY_CANCELLED",
                       f"review table {grid_id} was already cancelled; cancelling twice "
                       f"is not an error worth hiding, but it changed nothing")
    ctx.store.cancel_grid(grid_id)
    t = table.tally()
    return {"grid_id": grid_id, "cancelled": True,
            "findings_kept": t["findings"], "pending_stopped": t["PENDING"],
            "cells": t["cells"],
            "note": (f"{t['findings']} answered cell(s) are KEPT and {t['PENDING']} "
                     f"unrun cell(s) stay PENDING. Cancelling stops scheduling; it does "
                     f"not undo work that was done, and it does not mark unrun cells as "
                     f"failed.")}
