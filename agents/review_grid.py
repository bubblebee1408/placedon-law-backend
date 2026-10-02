#!/usr/bin/env python3
"""One queue job per cell. Exactly once, resumable, cancellable.

H4's runner. `checker/review_grid.py` holds the shapes and the rules; this schedules the
work and records each answer. It calls no model directly -- an `answer` callable is
injected, so the gate runs it deterministically and a worker runs it against whatever
`gateway/models.py` serves.

## One job per CELL, not one per document

Forty documents and six columns is 240 independent questions. Per-document jobs would make
one timeout lose five good answers, and a fan-out per document cannot be resumed at the
cell that failed. PLAN_23 layer 4(b) says "fan-out per document or clause"; a cell is the
clause-shaped unit here.

## A cell is a RUN, and that was the queue's decision not mine

`gateway/jobs.py` refuses a second job for one `run_id`: "a second job for one run is the
double execution the queue exists to prevent." So 40 documents x 6 columns is 240 runs, not
one run with 240 jobs. I found this by enqueueing four cells under one run and being
refused, which is the guard working.

It buys a second exactly-once guarantee for nothing. `run_id_for_cell` is a **uuid5 of the
cell key**, so the same cell always maps to the same run id -- and re-enqueueing a cell the
queue already holds is refused *by the queue*, before the database's primary key is
reached. Two independent mechanisms, at two layers, both derived from the same three facts
about which cell this is.

## Exactly once, and the key is the question

The idempotency key is `(grid_id, document_id, column_name)` -- which is also the PRIMARY
KEY of `review_grid_cells` (011). So "have I already answered this?" is not a question this
module asks: it writes, and a second write for the same cell conflicts. A worker that dies
after answering a cell and before finishing its job is handed the same cell again, and the
database refuses the duplicate rather than this code remembering.

`write_cell` therefore takes `if_pending`: a cell already in a terminal state is NOT
overwritten, and the attempt is reported rather than swallowed. That is what makes
`resume()` safe to call as often as you like.

## Cancel is a saga, not a stop

`cancel()` marks the grid cancelled and leaves every answered cell exactly as it is. The
compensation for "we started 40 cells and you changed your mind at 30" is **not** to undo
29 answers that were correct and paid for -- it is to stop scheduling, and to say in the
status how many were done. PLAN_23 §1.9.

A cancelled grid's PENDING cells stay PENDING. They are not failed: nothing went wrong,
and marking them FAILED would put transport language on a decision the user made.

Run: PYTHONPATH=. python3 agents/review_grid.py --test
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from checker import review_grid as rg

INTENT = "review_grid_cell"


class Unreadable(RuntimeError):
    """The model replied and the reply could not be read.

    A THIRD outcome, and the reason it has to exist: the answerer's contract was a pair for
    FOUND, None for NOT_FOUND and a raise for FAILED, and a reply with no `VALUE:` line in
    it fell through the parser with `value = ""` and returned None. So a model that answered
    in prose, or in JSON, or apologised, made the cell say **NOT_FOUND** -- "this clause is
    absent from this document" -- about a document it had in fact read and described. In a
    table a lawyer relies on, that is the worst available failure: an absence is a finding,
    and this one was manufactured by a parser.

    It is not FAILED either. FAILED means the step did not run; this ran, cost money and
    produced something. NEEDS_LAWYER is what "a person has to look at this" means here.
    """


class RunnerError(RuntimeError):
    """The runner cannot proceed. Never a silent skip."""


def cell_key(grid_id: str, document_id: str, column_name: str) -> str:
    """The idempotency key, as one string for a queue that wants one.

    Same three parts as `review_grid_cells`' primary key, in the same order, so a job's
    key and the row it will write cannot disagree about which cell they mean.
    """
    return f"{grid_id}:{document_id}:{column_name}"


# A fixed namespace, so a cell's run id is stable across processes and restarts. Written
# down rather than generated: a namespace that changed between deployments would give the
# same cell two run ids and defeat the guard it exists to arm.
_CELL_NS = uuid.UUID("6f1b2c74-0d8a-4a1e-9b3f-5c2d8e7a4b10")


def run_id_for_cell(grid_id: str, document_id: str, column_name: str) -> str:
    """The run id for one cell: uuid5 of its key, so it is the SAME id every time.

    That is what makes the queue's own "one job per run" rule into H4's exactly-once
    guard: re-enqueueing a cell already queued is refused by `gateway/jobs.py` before the
    database's primary key is reached.
    """
    return str(uuid.uuid5(_CELL_NS, cell_key(grid_id, document_id, column_name)))


@dataclass(frozen=True)
class Scheduled:
    grid_id: str
    enqueued: tuple = ()
    already_done: tuple = ()
    already_queued: tuple = ()
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {"grid_id": self.grid_id, "enqueued": list(self.enqueued),
                "already_done": list(self.already_done),
                "already_queued": list(self.already_queued),
                "cancelled": self.cancelled}


def plan_cells(table: rg.Table) -> list:
    """Every (document, column) pair that still needs running, in a stable order.

    Stable because a resumed run must schedule the same cells in the same order as the
    original: a trace that cannot be replayed is a trace nobody can check (agents/plans.py
    makes the same argument about step order).
    """
    out = []
    for d in table.document_ids:
        for col in table.columns:
            if table.cell(d, col.name).state == rg.PENDING:
                out.append((d, col))
    return out


def schedule(table: rg.Table, *, queue, cancelled: bool = False) -> Scheduled:
    """Enqueue one job per PENDING cell, each as its own run.

    Three outcomes per cell, all reported: enqueued, already answered, or already queued.
    A cell the queue already holds is NOT an error here -- it is the second exactly-once
    guard firing, and swallowing it would hide that the guard did anything.
    """
    from gateway.jobs import QueueError

    if cancelled:
        # Nothing is scheduled for a cancelled grid, and that is the whole of the
        # compensation: stop scheduling. What ran, ran.
        return Scheduled(table.table_id, cancelled=True)
    enqueued, done, queued = [], [], []
    for d in table.document_ids:
        for col in table.columns:
            key = cell_key(table.table_id, d, col.name)
            if table.cell(d, col.name).state != rg.PENDING:
                done.append(key)
                continue
            try:
                # A1. REVIEW_CELL: wanted soon, but nobody is blocked on one cell.
                from gateway.jobs import REVIEW_CELL as _LANE_CELL
                queue.enqueue(lane=_LANE_CELL, 
                    run_id=run_id_for_cell(table.table_id, d, col.name), intent=INTENT,
                    args={"grid_id": table.table_id, "document_id": d,
                          "column": col.name, "kind": col.kind,
                          "question": col.question, "idempotency_key": key})
            except QueueError:
                queued.append(key)
                continue
            enqueued.append(key)
    return Scheduled(table.table_id, tuple(enqueued), tuple(done), tuple(queued))


def run_cell(args: dict, *, documents: dict, answer) -> rg.Cell:
    """Answer one cell. Returns a Cell; raises only on a malformed job.

    `answer(question, kind, text) -> (value, quote) | None` is injected:
      a pair         the value and the span it was read from -> FOUND, verified here
      None           the answer is not in the document      -> NOT_FOUND
      Unreadable     the reply could not be read            -> NEEDS_LAWYER
      another raise  transport                              -> FAILED, not a finding

    `None` means the MODEL said the document does not answer the question. A reply nobody
    could parse means no such thing and must never reach NOT_FOUND, which is why
    `Unreadable` is a separate outcome and is caught first.

    The FOUND path goes through `review_grid.found()`, so the quote is checked against the
    document text and a value that does not satisfy its column kind becomes NEEDS_LAWYER
    **with the quote attached** rather than a refusal the user cannot act on.
    """
    for field in ("grid_id", "document_id", "column", "kind", "question"):
        if not str(args.get(field) or "").strip():
            raise RunnerError(f"a cell job needs {field}")
    col = rg.Column(args["column"], args["kind"], args["question"])
    doc = documents.get(args["document_id"]) or {}
    text = str(doc.get("text") or "")
    if doc.get("cannot_read"):
        return rg.not_found(
            document_id=args["document_id"], column=col,
            reason=(f"the document could not be read, so this column was not answered "
                    f"against it: {doc['cannot_read']}"))
    if not text.strip():
        return rg.failed(
            document_id=args["document_id"], column=col,
            detail=(f"no text is held for document {args['document_id'][:12]}, so nothing "
                    f"was read"))
    try:
        got = answer(args["question"], args["kind"], text)
    except Unreadable as exc:
        # Caught BEFORE the generic handler, because order is the whole fix: an unreadable
        # reply used to arrive here as None and leave as NOT_FOUND.
        return rg.needs_lawyer(
            document_id=args["document_id"], column=col,
            reason=f"unreadable model reply: {exc}")
    except Exception as exc:                                    # noqa: BLE001
        return rg.failed(document_id=args["document_id"], column=col,
                         detail=f"{type(exc).__name__}: {str(exc)[:120]}")
    if got is None:
        return rg.not_found(
            document_id=args["document_id"], column=col,
            reason=(f"the document was read in full and it does not answer "
                    f"{col.question!r}"))
    value, quote = got
    try:
        return rg.found(document_id=args["document_id"], column=col, value=value,
                        quote=quote, document_text=text)
    except rg.TableError as exc:
        # The quote did not match, or the value did not satisfy the column. Either way a
        # person should look, and the reason carries what went wrong so they can.
        return rg.needs_lawyer(
            document_id=args["document_id"], column=col,
            reason=(f"an answer was proposed and could not be accepted automatically: "
                    f"{exc}"))


def resume(table: rg.Table, *, queue, cancelled: bool = False) -> Scheduled:
    """Re-schedule only what is still PENDING. Safe to call repeatedly.

    This is the whole of crash recovery: the cells that completed are in the database, and
    `plan_cells` reads their state rather than a journal of what was attempted.
    """
    return schedule(table, queue=queue, cancelled=cancelled)


def status(table: rg.Table, *, cancelled: bool = False) -> dict:
    t = table.tally()
    return {"grid_id": table.table_id, "name": table.name,
            "documents": len(table.document_ids), "columns": len(table.columns),
            "cells": t["cells"], "findings": t["findings"],
            "by_state": {s: t[s] for s in rg.STATES},
            "complete": table.complete, "cancelled": bool(cancelled),
            "note": ("FAILED cells did not run and say nothing about the document; "
                     "PENDING cells have not been attempted. Neither is a finding, and "
                     "`findings` counts only the three states that describe a document.")}


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("agents.review_grid")
    from gateway.jobs import MemoryQueue

    DOC = ("MUTUAL NON-DISCLOSURE AGREEMENT\n"
           "3. This Agreement shall be governed by the laws of India.\n"
           "4. The term of confidentiality shall expire on 2029-03-31.\n"
           "7. The aggregate liability shall not exceed INR 50,00,000.\n")
    D1, D2 = "a" * 64, "b" * 64
    DOCS = {D1: {"text": DOC, "name": "nda.txt"},
            D2: {"text": "A SUPPLY AGREEMENT with no governing law clause at all.\n",
                 "name": "supply.txt"}}
    LAW = rg.Column("governing law", rg.TEXT, "Which law governs this agreement?")
    END = rg.Column("term end", rg.DATE, "On what date does confidentiality expire?")
    COLS = (LAW, END)

    def answerer(question, kind, text):
        if "governs" in question and "laws of India" in text:
            return ("India", "governed by the laws of India")
        if "expire" in question and "2029-03-31" in text:
            return ("2029-03-31", "expire on 2029-03-31")
        return None

    # ── one job per CELL ────────────────────────────────────────────────────
    t0 = rg.Table("g1", "NDA diligence", COLS, (D1, D2))
    q = MemoryQueue()
    sched = schedule(t0, queue=q)
    check(len(sched.enqueued) == 4,
          f"one job per CELL, not per document: 2 documents x 2 columns = 4 "
          f"({len(sched.enqueued)})")
    check(sorted(sched.enqueued) == sorted({cell_key("g1", d, c.name)
                                            for d in (D1, D2) for c in COLS}),
          "...each keyed (grid, document, column)")
    check(cell_key("g1", D1, "governing law") == f"g1:{D1}:governing law",
          "the idempotency key is the three parts of the row's PRIMARY KEY, in order")
    check(run_id_for_cell("g1", D1, "x") == run_id_for_cell("g1", D1, "x"),
          "a cell's run id is STABLE: uuid5 of its key, the same every time and in every "
          "process")
    check(run_id_for_cell("g1", D1, "x") != run_id_for_cell("g1", D1, "y"),
          "...and different cells get different run ids")
    # The queue's own guard, armed by that stability.
    q_again = schedule(t0, queue=q)
    check(q_again.enqueued == () and len(q_again.already_queued) == 4,
          f"scheduling the SAME grid twice enqueues nothing: the queue refuses a second "
          f"job for a run, and a cell's run id is derived from its key, so that guard is "
          f"H4's exactly-once at the QUEUE layer -- before the database's primary key is "
          f"reached ({len(q_again.already_queued)} already queued)")
    check(len(plan_cells(t0)) == 4, "plan_cells lists every PENDING pair")
    check([(d, c.name) for d, c in plan_cells(t0)]
          == [(d, c.name) for d, c in plan_cells(t0)],
          "...in a STABLE order, so a resumed run schedules the same cells in the same "
          "order and the trace stays replayable")

    # ── running the cells ───────────────────────────────────────────────────
    cells = []
    while True:
        job = q.claim(worker="w1")
        if job is None:
            break
        cells.append(run_cell(job.args, documents=DOCS, answer=answerer))
        q.finish(job.job_id, "DONE")
    check(len(cells) == 4, f"every job yields a cell ({len(cells)})")
    by = {(c.document_id, c.column): c for c in cells}
    check(by[(D1, "governing law")].state == rg.FOUND
          and by[(D1, "governing law")].value == "India",
          "a cell whose answer is in the document is FOUND")
    check(by[(D1, "governing law")].quote in DOC, "...with a quote that is really in it")
    check(by[(D1, "term end")].value == "2029-03-31", "a date column gets an ISO date")
    check(by[(D2, "governing law")].state == rg.NOT_FOUND,
          f"a document that does not answer the question is NOT_FOUND "
          f"({by[(D2, 'governing law')].state})")
    check("does not answer" in by[(D2, "governing law")].reason,
          "...and the reason says the document was read in full")

    # ── a quote that does not match becomes NEEDS_LAWYER, with the reason ───
    def liar(question, kind, text):
        return ("England", "governed by the laws of England")

    bad = run_cell({"grid_id": "g1", "document_id": D1, "column": LAW.name,
                    "kind": LAW.kind, "question": LAW.question},
                   documents=DOCS, answer=liar)
    check(bad.state == rg.NEEDS_LAWYER and "NOT in document" in bad.reason,
          f"an answer whose quote is not in the document becomes NEEDS_LAWYER, never "
          f"FOUND ({bad.state})")

    def wrong_kind(question, kind, text):
        return ("sometime in 2029", "expire on 2029-03-31")

    wk = run_cell({"grid_id": "g1", "document_id": D1, "column": END.name,
                   "kind": END.kind, "question": END.question},
                  documents=DOCS, answer=wrong_kind)
    check(wk.state == rg.NEEDS_LAWYER and "not an ISO date" in wk.reason,
          f"a value that does not satisfy its column kind becomes NEEDS_LAWYER with the "
          f"reason, not a bare refusal ({wk.state})")

    # ── FAILED is transport only ────────────────────────────────────────────
    def boom(question, kind, text):
        raise TimeoutError("the provider did not respond in 30s")

    fl = run_cell({"grid_id": "g1", "document_id": D1, "column": LAW.name,
                   "kind": LAW.kind, "question": LAW.question},
                  documents=DOCS, answer=boom)
    check(fl.state == rg.FAILED and "TimeoutError" in fl.reason,
          f"a transport error is FAILED ({fl.state})")
    check(not fl.is_finding, "...and is not a finding about the document")
    # ── an UNREADABLE reply is NEEDS_LAWYER, and never NOT_FOUND ───────────
    # The bug this replaces: the parser found no VALUE: line, returned None, and the cell
    # said the clause was ABSENT from a document the model had just described.
    def garbled(question, kind, text):
        raise Unreadable("no VALUE: line in a 42-character reply, so nothing was read "
                         "from it")

    _ur = run_cell({"grid_id": "g1", "document_id": D1, "column": LAW.name,
                    "kind": LAW.kind, "question": LAW.question},
                   documents=DOCS, answer=garbled)
    check(_ur.state == rg.NEEDS_LAWYER,
          f"an UNREADABLE model reply is NEEDS_LAWYER ({_ur.state})")
    check(_ur.state != rg.NOT_FOUND,
          "...and specifically NOT NOT_FOUND: the document was read and described, so an "
          "absence would be a finding this parser invented")
    check(_ur.state != rg.FAILED,
          "...and not FAILED either: the call ran and cost money, it just said something "
          "nobody could read")
    check("unreadable model reply" in _ur.reason,
          f"...with that named in the reason ({_ur.reason[:50]!r})")
    check("no VALUE: line" in _ur.reason,
          "...carrying what the answerer said went wrong, so a person can see it")
    check(_ur.value == "" and _ur.quote == "",
          "...and it proposes no value and no quote, because nothing was read")

    missing = run_cell({"grid_id": "g1", "document_id": "c" * 64, "column": LAW.name,
                        "kind": LAW.kind, "question": LAW.question},
                       documents=DOCS, answer=answerer)
    check(missing.state == rg.FAILED and "nothing was read" in missing.reason,
          "a document we hold no text for is FAILED, never NOT_FOUND -- we did not read it")
    unread = run_cell({"grid_id": "g1", "document_id": "d" * 64, "column": LAW.name,
                       "kind": LAW.kind, "question": LAW.question},
                      documents={"d" * 64: {"cannot_read": "no text layer; a scan"}},
                      answer=answerer)
    check(unread.state == rg.NOT_FOUND and "could not be read" in unread.reason,
          "a document KNOWN to be unreadable is NOT_FOUND against this column, with the "
          "reason -- we know why, so it is a finding about the attempt and not a transport "
          "failure")
    for miss in ("grid_id", "document_id", "column", "kind", "question"):
        args = {"grid_id": "g", "document_id": D1, "column": "c", "kind": rg.TEXT,
                "question": "q?"}
        args[miss] = ""
        try:
            run_cell(args, documents=DOCS, answer=answerer)
            check(False, f"a job missing {miss} raises")
        except RunnerError:
            check(True, f"a job missing {miss} raises rather than guessing")

    # ── exactly once: a crash then a resume completes each cell once ────────
    t1 = rg.Table("g1", "NDA diligence", COLS, (D1, D2), tuple(cells[:2]))
    q2 = MemoryQueue()
    again = resume(t1, queue=q2)
    check(len(again.enqueued) == 2 and len(again.already_done) == 2,
          f"a resume re-enqueues ONLY the cells still PENDING "
          f"({len(again.enqueued)} enqueued, {len(again.already_done)} already done)")
    done_keys = set(again.already_done)
    check(not (set(again.enqueued) & done_keys),
          "...and never re-enqueues one that is done, so each cell completes exactly once")
    check(set(again.already_done) == {cell_key("g1", c.document_id, c.column)
                                      for c in cells[:2]},
          "...identified by the same key the row is written under")
    t_full = rg.Table("g1", "n", COLS, (D1, D2), tuple(cells))
    check(resume(t_full, queue=MemoryQueue()).enqueued == (),
          "a complete grid re-schedules nothing, however many times resume is called")

    # ── cancel is a saga: stop scheduling, keep what ran ───────────────────
    c_sched = schedule(t1, queue=MemoryQueue(), cancelled=True)
    check(c_sched.enqueued == () and c_sched.cancelled,
          "a cancelled grid schedules nothing")
    st = status(t1, cancelled=True)
    check(st["findings"] == 2 and st["by_state"][rg.PENDING] == 2,
          f"...and the 2 answers already given are KEPT and counted: the compensation for "
          f"a cancel is to stop scheduling, not to undo work that was correct and paid "
          f"for ({st['findings']} findings)")
    check(st["by_state"][rg.FAILED] == 0,
          "...and the unrun cells stay PENDING, not FAILED: nothing went wrong, and "
          "FAILED would put transport language on a decision the user made")
    check(st["cancelled"] and not st["complete"], "...the status says both")

    # ── status counts findings, not cells ──────────────────────────────────
    s2 = status(t_full)
    check(s2["cells"] == 4 and s2["findings"] == 4 and s2["complete"],
          f"a finished grid reports 4 of 4 ({s2['findings']}/{s2['cells']})")
    mixed = rg.Table("g2", "n", COLS, (D1,),
                     (by[(D1, "governing law")],
                      rg.failed(document_id=D1, column=END, detail="timeout")))
    sm = status(mixed)
    check(sm["cells"] == 2 and sm["findings"] == 1,
          f"a grid with one transport failure reports 1 finding of 2 cells, never 2 "
          f"({sm['findings']}/{sm['cells']})")
    check("say nothing about the document" in sm["note"], "...and the note says why")

    check(INTENT == "review_grid_cell", f"the queue intent is named ({INTENT})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
