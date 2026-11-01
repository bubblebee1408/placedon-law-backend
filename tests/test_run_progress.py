"""Live progress for a pending Ask turn (031, gateway/progress.py). Offline, no provider."""
from dataclasses import replace
import unittest
from unittest.mock import patch
import uuid

from gateway import progress, verbs, worker
from gateway.jobs import MemoryQueue
from gateway.store import MemoryBackend

QUESTION = "How many meetings of the Board must a company hold under section 173?"
TODAY = "2026-10-10T00:00:00Z"


class RunProgress(unittest.TestCase):
    def setUp(self):
        self.store = MemoryBackend()
        self.queue = MemoryQueue()
        self.ctx = verbs.Context(store=self.store, queue=self.queue, clock=lambda: TODAY)
        self.sent = verbs._conversation_send(
            {"text": QUESTION, "request_id": str(uuid.uuid4())}, self.ctx)

    def pending(self):
        got = verbs._conversation_get({"conversation_id": self.sent["conversation_id"]}, self.ctx)
        return got["messages"][1]

    def test_pending_turn_shows_current_and_done_steps_while_the_worker_runs(self):
        seen = []

        def handler(_args):
            progress.mark(progress.UNDERSTANDING)
            seen.append(self.pending().get("progress"))
            progress.mark(progress.SEARCHING)
            progress.mark(progress.SEARCHING)   # repeating a step is not a new step
            seen.append(self.pending().get("progress"))
            return [], {"status": "PARTIAL", "answer": "Limited evidence."}

        self.assertNotIn("progress", self.pending(), "queued, not started: no progress yet")
        worker.run_one(queue=self.queue, store=self.store,
                       handlers={"research_question": handler})
        self.assertEqual(seen, [
            {"current": progress.UNDERSTANDING, "done": []},
            {"current": progress.SEARCHING, "done": [progress.UNDERSTANDING]}])
        done = self.pending()
        self.assertEqual(done["envelope"]["status"], "PARTIAL", "answer logic unchanged")
        self.assertNotIn("progress", done, "a finished turn carries its answer, not progress")

    def test_late_progress_write_does_not_touch_a_finished_run(self):
        worker.run_one(queue=self.queue, store=self.store, handlers={
            "research_question": lambda _: ([], {"status": "PARTIAL", "answer": "x"})})
        self.store.set_run_progress(self.sent["run_id"], {"current": "late", "done": []})
        self.assertIsNone(self.store.read_run_progress(self.sent["run_id"]))

    def test_a_failing_progress_write_never_fails_the_answer(self):
        def handler(_args):
            progress.mark(progress.WRITING)
            return [], {"status": "PARTIAL", "answer": "Limited evidence."}

        with patch.object(self.store, "set_run_progress", side_effect=RuntimeError("db")):
            out = worker.run_one(queue=self.queue, store=self.store,
                                 handlers={"research_question": handler})
        self.assertEqual(out.status, "PARTIAL")

    def test_mark_outside_a_worker_is_a_no_op(self):
        progress.mark(progress.UNDERSTANDING)   # no writer installed: nothing to raise
        self.assertIsNone(self.store.read_run_progress(self.sent["run_id"]))

    def test_ask_marks_its_steps_in_order(self):
        from agents import research_question as rq
        srcs = tuple(s for s, _o in rq.evidence(QUESTION))
        self.assertTrue(srcs, "fixture question must retrieve held law")
        marks = []
        with patch.object(progress, "mark", side_effect=marks.append):
            out = verbs._ask({"question": QUESTION}, replace(
                self.ctx, store=None, queue=None,
                model_for=lambda _o: rq.quoting_model(srcs)))
        self.assertIn(out["status"], ("ANSWERED", "PARTIAL"))
        self.assertEqual(marks, [progress.UNDERSTANDING, progress.SEARCHING,
                                 progress.WRITING, progress.CHECKING])


if __name__ == "__main__":
    unittest.main()
