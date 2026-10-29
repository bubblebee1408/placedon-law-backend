"""Conversation regression tests. No provider keys, network, or paid calls are used."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from gateway import envelope, verbs, worker
from gateway.filestore import LocalFileStore
from gateway.jobs import MemoryQueue
from gateway.store import MemoryBackend, TurnConflict

QUESTION = "What is the quorum under section 174 of the Companies Act?"
TODAY = "2026-10-10T00:00:00Z"


class ConversationReliability(unittest.TestCase):
    def setUp(self):
        self.store = MemoryBackend()
        self.queue = MemoryQueue()
        self.ctx = verbs.Context(store=self.store, queue=self.queue, clock=lambda: TODAY)

    def send(self, **changes):
        return verbs._conversation_send({"text": QUESTION, "request_id": str(uuid.uuid4()), **changes}, self.ctx)

    def test_concurrent_duplicate_submissions_reserve_one_pair_and_one_job(self):
        args = {"text": QUESTION, "request_id": "same-request-001"}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: verbs._conversation_send(args, self.ctx), range(48)))
        self.assertEqual(len({r["conversation_id"] for r in results}), 1)
        self.assertEqual(len({r["message_id"] for r in results}), 1)
        self.assertEqual(len(self.queue.jobs), 1)
        messages = self.store.read_messages(results[0]["conversation_id"])
        self.assertEqual([(m["ordinal"], m["role"]) for m in messages], [(0, "user"), (1, "assistant")])

    def test_parallel_distinct_turns_get_adjacent_unique_ordinals(self):
        cid = self.send()["conversation_id"]
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: self.send(conversation_id=cid), range(24)))
        self.assertTrue(all(r.get("run_id") for r in results))
        messages = self.store.read_messages(cid)
        self.assertEqual([m["ordinal"] for m in messages], list(range(50)))
        self.assertTrue(all(m["role"] == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(messages)))

    def test_changed_payload_conflicts_without_another_turn(self):
        first = self.send(request_id="retry-id-001")
        repeat = self.send(request_id="retry-id-001")
        conflict = self.send(request_id="retry-id-001", text="What is section 173?")
        self.assertEqual(first["message_id"], repeat["message_id"])
        self.assertEqual(conflict["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(len(self.store.read_messages(first["conversation_id"])), 2)

    def test_capacity_does_not_block_retry_or_save_new_turn(self):
        with patch.dict("os.environ", {"PLACEDON_CONVERSATION_QUEUE_LIMIT": "1"}):
            first = self.send(request_id="capacity-001")
            duplicate = self.send(request_id="capacity-001")
            blocked = self.send()
        self.assertEqual(first["message_id"], duplicate["message_id"])
        self.assertEqual(blocked["code"], "BUSY")
        self.assertEqual(len(self.store.conversations), 1)
        self.assertEqual(len(self.store.messages[first["conversation_id"]]), 2)

    def test_worker_and_reload_preserve_partial_result_and_source_report(self):
        response = self.send()
        report = {"picked": ["held"], "searched": ["held"], "report": [], "note": "test"}
        worker.run_one(queue=self.queue, store=self.store, handlers={
            "research_question": lambda _: ([], {"status": "PARTIAL", "answer": "Limited evidence.", "sources": report})})
        self.assertEqual(self.store.read(response["run_id"])["status"], "PARTIAL")
        # A fresh Context stands in for a restarted web process.
        reopened = verbs._conversation_get({"conversation_id": response["conversation_id"]}, replace(self.ctx, documents={}))
        assistant = reopened["messages"][1]
        self.assertEqual(assistant["envelope"]["status"], "PARTIAL")
        self.assertEqual(assistant["metadata"]["sources"], report)
        self.assertEqual(envelope.errors(assistant["envelope"]), [])
        self.assertEqual(self.store.read_messages(response["conversation_id"])[1]["metadata"], assistant["metadata"])

    def test_abstention_and_lawyer_outcomes_survive_queue_and_reload(self):
        for status, run_status in [("ABSTAINED", "REFUSED"), ("NEEDS_LAWYER", "AWAITING_HUMAN")]:
            with self.subTest(status=status):
                self.setUp()
                response = self.send()
                worker.run_one(queue=self.queue, store=self.store, handlers={
                    "research_question": lambda _: ([], {"status": status, "answer": "Review required."})})
                self.assertEqual(self.store.read(response["run_id"])["status"], run_status)
                result = verbs._conversation_get({"conversation_id": response["conversation_id"]}, self.ctx)
                self.assertEqual(result["messages"][1]["envelope"]["status"], status)

    def test_retrying_worker_failure_keeps_pending_until_terminal_failure(self):
        response = self.send()
        def crash(_):
            raise RuntimeError("secret provider address must not appear in UI")
        worker.run_one(queue=self.queue, store=self.store, handlers={"research_question": crash})
        self.assertIsNone(verbs._conversation_get({"conversation_id": response["conversation_id"]}, self.ctx)["messages"][1]["envelope"])
        job = self.queue.get(response["run_id"])
        self.queue.fail(job.job_id, "provider unavailable", retryable=False)
        result = verbs._conversation_get({"conversation_id": response["conversation_id"]}, self.ctx)
        env = result["messages"][1]["envelope"]
        self.assertEqual(env["status"], "FAILED")
        self.assertNotIn("secret provider", str(env))

    def test_artifact_metadata_is_saved_and_replayed(self):
        draft_id = str(uuid.uuid4())
        fake = replace(verbs.by_name()["draft.create"], run=lambda a, c: {"status": "ANSWERED", "draft_id": draft_id, "version": 1})
        real = verbs.by_name()
        with patch("gateway.verbs.by_name", return_value={**real, "draft.create": fake}):
            result = self.send(text="Prepare a draft", task_override="DRAFT", request_id="draft-request-01")
        self.assertEqual(result["metadata"]["artifacts"], [{"type": "draft", "id": draft_id, "version": 1}])
        replay = self.send(text="Prepare a draft", task_override="DRAFT", request_id="draft-request-01")
        self.assertEqual(replay["draft_id"], draft_id)
        self.assertEqual(replay["version"], 1)

    def test_8000_limit_and_invalid_types_leave_no_half_turn(self):
        for changes in ({"text": "a" * 8001}, {"request_id": "short"}, {"as_of": "2026-02-31"}, {"sources": [3]}):
            with self.subTest(changes=str(changes)[:60]):
                self.assertEqual(self.send(**changes)["code"], "BAD_REQUEST")
        self.assertFalse(self.store.messages)
        self.assertIn("envelope", self.send(text="a" * 8000, task_override="COMPANY_STANDING"))

    def test_existing_matter_is_stable_and_unknown_matter_is_rejected(self):
        first_matter, other = str(uuid.uuid4()), str(uuid.uuid4())
        self.store.write_matter({"matter_id": first_matter, "name": "First"}, owner="unknown")
        self.store.write_matter({"matter_id": other, "name": "Other"}, owner="unknown")
        first = self.send(matter_id=first_matter)
        self.assertEqual(self.send(conversation_id=first["conversation_id"], matter_id=other)["code"], "MATTER_CONFLICT")
        self.assertEqual(self.send(matter_id=str(uuid.uuid4()))["code"], "NOT_FOUND")
        self.assertEqual(len(self.store.read_messages(first["conversation_id"])), 2)

    def test_unreadable_file_never_reviews_the_instruction_instead(self):
        result = self.send(text="Review this document", file_ids=[str(uuid.uuid4())], task_override="REVIEW_DOCUMENT")
        self.assertEqual(result["envelope"]["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(result["envelope"]["files"][0]["state"], "CANNOT_READ")
        self.assertFalse(self.queue.jobs)

    def test_selected_vault_document_resolves_after_process_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            files = LocalFileStore(Path(folder))
            content = b"MINUTES OF THE BOARD MEETING. Present: three directors."
            sha = files.put(content)
            did = str(uuid.uuid4())
            self.store.write_vault_document({"uploaded_by": "unknown", "document_id": did, "sha256": sha, "name": "board.txt", "byte_count": len(content), "state": "INGESTED"})
            self.ctx = replace(self.ctx, files=files, documents={})
            result = self.send(text="Review these minutes", file_ids=[did], task_override="REVIEW_DOCUMENT")
            self.assertIsNone(result["envelope"])
            self.assertEqual(self.queue.get(result["run_id"]).args["text"], content.decode())
            self.assertEqual(result["files"][0]["state"], "READING")

    def test_cross_matter_file_rejected_before_message_write(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        self.store.write_matter({"matter_id": a, "name": "A"}, owner="unknown")
        self.store.write_matter({"matter_id": b, "name": "B"}, owner="unknown")
        did = str(uuid.uuid4())
        self.store.write_vault_document({"uploaded_by": "unknown", "document_id": did, "matter_id": b, "sha256": "1"*64, "name": "secret.txt", "state": "INGESTED"})
        result = self.send(matter_id=a, file_ids=[did])
        self.assertEqual(result["code"], "DOCUMENT_SCOPE_MISMATCH")
        self.assertFalse(self.store.messages)

    def test_deleting_one_tenants_doc_preserves_shared_bytes_for_other(self):
        with tempfile.TemporaryDirectory() as folder:
            files = LocalFileStore(Path(folder))
            content = b"Both tenants legally hold this same document."
            sha = files.put(content)
            other = MemoryBackend(tenant_id=str(uuid.uuid4()))
            a, b = str(uuid.uuid4()), str(uuid.uuid4())
            for store, did in ((self.store, a), (other, b)):
                store.write_vault_document({"uploaded_by": "unknown", "document_id": did, "sha256": sha, "name": "shared.txt", "state": "INGESTED"})
                store.write_vault_chunks(did, [content.decode()])
            result = verbs._vault_delete({"document_id": a}, replace(self.ctx, files=files))
            self.assertFalse(result["bytes_destroyed"])
            self.assertTrue(result["deleted"])
            self.assertEqual(files.get(sha), content)
            self.assertEqual(other.read_vault_document(b)["state"], "INGESTED")
            self.assertTrue(other.read_vault_chunks())
            self.assertFalse(self.store.read_vault_chunks())

    def test_unknown_matter_upload_writes_no_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            files = LocalFileStore(Path(folder))
            result = verbs._vault_upload({"name": "x.txt", "text": "private", "matter_id": str(uuid.uuid4())}, replace(self.ctx, files=files))
            self.assertEqual(result["code"], "NOT_FOUND")
            self.assertFalse(list(Path(folder).glob("**/*")))

    def test_ambiguous_followup_does_not_synthesize_prior_ai_answer(self):
        first = self.send()
        result = self.send(text="Does that apply to it?", conversation_id=first["conversation_id"])
        self.assertEqual(result["envelope"]["status"], "NEEDS_CLARIFICATION")
        self.assertEqual(len(self.queue.jobs), 1)

    def test_followup_that_names_its_subject_is_researched_on_its_own_words(self):
        # Regression: every follow-up starting "And ..." was sent back for clarification, even
        # "And what happens if that quorum is not present at the meeting?".
        first = self.send()
        result = self.send(text="And what happens if that quorum is not present at the meeting?",
                           conversation_id=first["conversation_id"])
        self.assertNotEqual((result.get("envelope") or {}).get("status"), "NEEDS_CLARIFICATION")
        self.assertEqual(len(self.queue.jobs), 2, "queued as research, like a first question")

    def test_named_subject_rule_is_narrow(self):
        self.assertTrue(verbs._names_own_subject("And what happens if that quorum is not present at the meeting?"))
        self.assertTrue(verbs._names_own_subject("Also, what is the notice period for a board meeting?"))
        for vague in ("Does that apply to it?", "And what about that?", "Can it be done?", "Explain that please",
                      "And how?", "What about this one then?"):
            self.assertFalse(verbs._names_own_subject(vague), vague)

    def test_vault_picker_reports_not_searched_when_ungrounded(self):
        from checker import source_picker
        report = verbs._sources_report(["held", "vault"], source_picker.resolve(["held", "vault"]), (), QUESTION, self.ctx)
        self.assertEqual(report["searched"], ["held"])
        self.assertEqual(next(r for r in report["report"] if r["id"] == "vault")["outcome"], "NOT_SEARCHED")

    def test_atomic_queue_capacity_rolls_back_all_new_rows(self):
        self.queue.max_pending = 1
        first = self.send()
        self.assertEqual(self.send()["code"], "BUSY")
        self.assertEqual(len(self.store.conversations), 1)
        self.assertEqual(len(self.store.runs), 1)
        self.assertEqual(len(self.store.messages[first["conversation_id"]]), 2)
        self.assertEqual(len(self.store.turn_requests), 1)

    def test_missing_vault_bytes_are_explicitly_unreadable(self):
        with tempfile.TemporaryDirectory() as folder:
            files = LocalFileStore(Path(folder))
            did = str(uuid.uuid4())
            self.store.write_vault_document({"uploaded_by": "unknown", "document_id": did, "sha256": "1" * 64,
                                            "name": "missing.txt", "state": "INGESTED"})
            self.ctx = replace(self.ctx, files=files)
            result = self.send(text="Review this", file_ids=[did], task_override="REVIEW_DOCUMENT")
            self.assertEqual(result["envelope"]["status"], "NEEDS_CLARIFICATION")
            self.assertEqual(result["envelope"]["files"][0]["state"], "CANNOT_READ")
            self.assertFalse(self.queue.jobs)

    def test_stale_snapshot_cannot_overwrite_completed_sync_reply(self):
        request = "stale-request-001"
        cid, mid = str(uuid.uuid4()), str(uuid.uuid4())
        metadata = {"accepted_at": "2026-10-09T00:00:00Z", "as_of": "2026-10-09"}
        pending, _ = self.store.reserve_turn({"conversation_id": cid},
            {"message_id": str(uuid.uuid4()), "role": "user", "text": "draft"},
            {"message_id": mid, "role": "assistant", "task": "DRAFT", "metadata": metadata},
            request_id=request, payload_digest="a" * 64)
        completed = envelope.build(status="ANSWERED", task="DRAFT", as_of="2026-10-09",
            text_blocks=[{"text": "Draft created.", "citation_ids": []}], bodies=[], citations=[], files=[])
        self.store.update_message(mid, task="DRAFT", run_id=None, envelope=completed, metadata=metadata)
        result = verbs._reconcile_message(pending, self.ctx)
        self.assertEqual(result["envelope"]["status"], "ANSWERED")
        self.assertEqual(self.store.read_messages(cid)[1]["envelope"], completed)

    def test_abandoned_sync_reservation_becomes_failed_without_redispatch(self):
        cid, mid = str(uuid.uuid4()), str(uuid.uuid4())
        self.store.reserve_turn({"conversation_id": cid, "actor_id": "unknown"},
            {"message_id": str(uuid.uuid4()), "role": "user", "text": "draft"},
            {"message_id": mid, "role": "assistant", "task": "DRAFT", "metadata":
             {"accepted_at": "2026-10-09T00:00:00Z", "as_of": "2026-10-09"}},
            request_id="interrupted-request-1", payload_digest="a" * 64)
        result = verbs._conversation_get({"conversation_id": cid}, self.ctx)
        self.assertEqual(result["messages"][1]["envelope"]["status"], "FAILED")
        self.assertFalse(self.queue.jobs)
        self.assertFalse(self.store.drafts)

    def test_retry_completion_cannot_persist_previous_failed_attempt(self):
        response = self.send()
        mid = response["message_id"]
        self.store.set_run(response["run_id"], status="FAILED", result={"error": "old attempt"})
        original_get = self.queue.get
        def completing_get(run_id):
            self.store.set_run(run_id, status="PARTIAL", result={"status": "PARTIAL", "answer": "Recovered."})
            job = original_get(run_id)
            self.queue.finish(job.job_id, "DONE")
            return original_get(run_id)
        with patch.object(self.queue, "get", side_effect=completing_get):
            result = verbs._conversation_get({"conversation_id": response["conversation_id"]}, self.ctx)
        self.assertEqual(next(m for m in result["messages"] if m["message_id"] == mid)["envelope"]["status"], "PARTIAL")

    def test_cancel_before_execution_does_not_call_handler(self):
        response = self.send()
        self.queue.request_cancel(response["run_id"])
        called = []
        worker.run_one(queue=self.queue, store=self.store, handlers={
            "research_question": lambda _: (called.append(True) or [], {"status": "ANSWERED"})})
        self.assertFalse(called)
        self.assertEqual(self.store.read(response["run_id"])["refusal_code"], "CANCELLED")
        self.assertTrue(any(step["status"] == "CANCELLED"
                            for step in self.store.read(response["run_id"])["steps"]))

    def test_failed_envelope_never_discloses_provider_error(self):
        result = verbs._envelope_for("RESEARCH_QUESTION", {"status": "FAILED", "error": "Bearer secret-token patient-text"},
                                     as_of="2026-10-10", ctx=self.ctx)
        self.assertEqual(result["status"], "FAILED")
        self.assertNotIn("secret-token", str(result))
        self.assertNotIn("patient-text", str(result))

    def test_legacy_cached_vault_claim_is_not_replayed(self):
        row = {"lookup_key": "old", "content_key": "old", "payload": {
            "status": "ANSWERED", "answer": "cached", "sources": {
                "picked": ["held", "vault"], "searched": ["held", "vault"],
                "report": [{"id": "vault", "outcome": "SEARCHED_HITS", "hits": 5}], "note": "old"}}}
        with patch.object(self.store, "read_cache_entry", return_value=row), patch("checker.answer_cache.servable", return_value=(True, "test")):
            result, _ = verbs._cache_lookup(QUESTION, "RESEARCH_QUESTION", None,
                                            replace(self.ctx, actor="a" * 8))
        self.assertEqual(result["sources"]["searched"], ["held"])
        self.assertEqual(result["sources"]["report"][0]["outcome"], "NOT_SEARCHED")
        self.assertIn("no new search ran", result["sources"]["note"])

    def test_contract_documents_are_not_implicitly_marked_as_fixtures(self):
        from checker import public_only
        args = verbs._task_args("REVIEW_CONTRACT", "private NDA contents", [], self.ctx, {})
        self.assertIs(args["test_data"], False)
        for value in (None, False, "false", "unspecified"):
            with self.subTest(value=value), patch("checker.public_only.clear_matter", side_effect=public_only.NotPublic("test gate")) as cleared:
                verbs._review_contract({"text": "private NDA contents", "test_data": value}, self.ctx)
                self.assertIs(cleared.call_args.kwargs["test_data"], False)
        # A request's own word marks nothing; only an in-process test context may.
        for value in (True, "fixture", "synthetic"):
            for ctx, want in ((self.ctx, False), (replace(self.ctx, synthetic_fixtures=True), True)):
                with self.subTest(value=value, want=want), patch("checker.public_only.clear_matter", side_effect=public_only.NotPublic("test gate")) as cleared:
                    verbs._review_contract({"text": "synthetic NDA contents", "test_data": value}, ctx)
                    self.assertIs(cleared.call_args.kwargs["test_data"], want)

    def test_idempotent_retry_after_date_rollover_returns_original_turn(self):
        first = self.send(request_id="date-rollover-001", as_of="2026-10-10")
        tomorrow = replace(self.ctx, clock=lambda: "2026-10-11T00:00:00Z")
        replay = verbs._conversation_send({"text": QUESTION, "request_id": "date-rollover-001", "as_of": "2026-10-10"}, tomorrow)
        self.assertEqual(first["message_id"], replay["message_id"])


if __name__ == "__main__":
    unittest.main()
