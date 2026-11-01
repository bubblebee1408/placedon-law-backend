"""Live progress for a queued run: which step is running now, which are done.

The trace (`run_steps`) is written only after the handler returns (A-022), so a user
waiting on an answer saw nothing until the end. This records a small, coarse `progress`
value on the run row WHILE the handler runs, for the conversation read to show.

The worker installs a writer for the job it is running (`recording`); handlers call
`mark(LABEL)` at their boundaries. Outside a worker -- the synchronous verb path, tests
-- `mark` does nothing. A progress write can never fail the work: it is display only.

The labels are the user-facing text, plain English, and live only here.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
from typing import Callable

UNDERSTANDING = "Understanding the question"
SEARCHING = "Searching the Companies Act"
WRITING = "Writing the answer"
CHECKING = "Checking quotes"

_writer: contextvars.ContextVar[Callable[[str], None] | None] = contextvars.ContextVar(
    "placedon_progress_writer", default=None)


def mark(label: str) -> None:
    """The step now running. The previous one is recorded as done."""
    write = _writer.get()
    if write is not None:
        write(label)


@contextlib.contextmanager
def recording(store, run_id: str):
    """Within this block, `mark` writes `{"current", "done"}` to the run via the store."""
    state = {"current": None, "done": []}

    def write(label: str) -> None:
        if state["current"] == label:
            return
        if state["current"] is not None:
            state["done"] = [*state["done"], state["current"]]
        state["current"] = label
        try:
            store.set_run_progress(run_id, {"current": label, "done": list(state["done"])})
        except Exception:                                         # noqa: BLE001
            # Display only. A store without the column (031 not applied) or a transient
            # error must never stop the answer the user is waiting for.
            logging.getLogger(__name__).warning("progress_write_failed",
                                                extra={"run_id": run_id})

    token = _writer.set(write)
    try:
        yield
    finally:
        _writer.reset(token)
